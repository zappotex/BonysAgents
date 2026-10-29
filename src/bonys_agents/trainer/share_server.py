# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: eine Vorlage im lokalen Netz bzw. im VPN freigeben (nur in „Bony's Agents Kursleiter“).

``Share`` startet einen kleinen HTTPS-Server (nur solange freigegeben), der genau eine ``.bonys``-Datei ausliefert.
Sicherheit:

- selbstsigniertes Zertifikat (Ed25519) **pro Freigabe**; sein SHA-256-Fingerabdruck steht auf dem Bildschirm
  des Kursleiters und im QR-Code. Teilnehmer prüfen ihn (und brechen ab, wenn er nicht passt).
- Zugriff nur mit Freigabe-Code (z. B. ``4711-BONY``), Vergleich in konstanter Zeit, Sperre nach mehreren
  Fehlversuchen je Adresse, die Freigabe endet nach zu vielen Fehlversuchen insgesamt.
- nur lesend: GET/HEAD auf ``/bonys/v1/info`` und ``/bonys/v1/download`` – keine anderen Dateien erreichbar. Mit
  Kurspaket zusätzlich ``GET /bonys/v1/kurspaket`` und ``POST /bonys/v1/fortschritt`` (höchstens 1 KB: nur Lektion und
  „geschafft / noch nicht“ – nichts wird auf diesem Rechner gespeichert, nur angezeigt).
- endet automatisch nach der eingestellten Zeit; höchstens N gleichzeitige Downloads, der Rest wartet in
  einer Schlange (Antwort 503 mit Platz in der Schlange).
- passt das Kurs-Protokoll eines Teilnehmers nicht (``share.PROTOCOL``), Antwort 426 mit beiden Versionen.

Die Teilnehmer-Seite (beitreten, laden) steht in ``bonys_agents.share`` und ist in beiden Editionen enthalten.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import ssl
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from bonys_agents import __version__, bonysfile, templates, x509
from bonys_agents.trainer import announce
from bonys_agents.share import (
    API, CHUNK, CLIENT_HEADER, CODE_HEADER, CODE_LETTERS, DEFAULT_MAX_DOWNLOADS, DEFAULT_PORT, DEFAULT_TIMEOUT_MIN,
    FORTSCHRITT_MAX, LOCK_SECONDS, MAX_FAILS_PER_ADDR, MAX_FAILS_TOTAL, PROTOCOL, PROTOCOL_HEADER, VERSION_HEADER,
    WAITING_STALE, ProtocolMismatch, ShareError, check_protocol, local_addresses, normalize_code, share_link,
)
from bonys_agents.i18n import n_, tr

FIREWALL_HINTS = {
    "windows": n_("Windows fragt beim ersten Freigeben, ob Bony's Agents Verbindungen annehmen darf: „Zugriff "
                  "zulassen“ – nur für „Private Netzwerke“ (Heim-/Firmennetz), nicht für öffentliche. Ist das Netz als "
                  "„Öffentlich“ eingestuft, in den Windows-Einstellungen auf „Privat“ umstellen."),
    "macos": n_("macOS fragt ggf. „Eingehende Netzwerkverbindungen akzeptieren?“ – „Erlauben“. Ist unter "
                "Systemeinstellungen → Netzwerk → Firewall „Alle eingehenden Verbindungen blockieren“ an, finden "
                "die Teilnehmer die Freigabe nicht."),
    "linux": n_("Linux: Meist ist keine Firewall aktiv. Mit ufw den Port nur für die Schulung öffnen und danach wieder "
                "schließen: sudo ufw allow {port}/tcp … sudo ufw delete allow {port}/tcp (mDNS: 5353/udp). Mit "
                "firewalld nur vorübergehend (ohne --permanent): sudo firewall-cmd --add-port={port}/tcp."),
}



def firewall_hinweis(port: int) -> str:
    """Hinweis zur Firewall dieses Rechners (je Betriebssystem) mit eingesetztem Port, in der Sprache der App."""
    from bonys_agents import host

    text = FIREWALL_HINTS.get(host.detect().os, "")
    return tr(text, port=port) if text else ""


def new_code() -> str:
    """Zufälliger, kurzer, gut vorlesbarer Code: 4 Ziffern, Bindestrich, 4 Buchstaben (z. B. 4711-BONY)."""
    digits = "".join(secrets.choice("0123456789") for _ in range(4))
    letters = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
    return f"{digits}-{letters}"



# Zertifikate: bonys_agents.x509 (beide Editionen – auch die Steuerkanäle der Agent-PCs unter Windows nutzen es)
make_certificate = x509.make_certificate
server_context = x509.server_context


# ---------------------------------------------------------------- Zwischenspeicher der .bonys-Datei
def cache_dir(t: templates.Template) -> Path:
    return templates.templates_dir(t.library) / ".freigabe-cache"


def _cache_key(t: templates.Template) -> dict:
    st = t.disk.stat()
    return {"name": t.name, "created": t.created, "disk_size": st.st_size, "disk_mtime": int(st.st_mtime),
            "app_version": __version__}


def cached_bundle(t: templates.Template) -> tuple[Path, str] | None:
    """Schon exportierte .bonys-Datei dieser Vorlage (unverändert seitdem) samt SHA-256 – oder None."""
    d = cache_dir(t)
    meta = d / f"{t.name}.json"
    try:
        data = json.loads(meta.read_text("utf-8"))
        file = d / data["file"]
        if data.get("key") == _cache_key(t) and file.is_file() and file.stat().st_size == data.get("size") \
                and re.fullmatch(r"[0-9a-f]{64}", data.get("sha256", "")):
            return file, data["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def cache_target(t: templates.Template, version: str) -> Path:
    d = cache_dir(t)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob(f"{t.name}-*{bonysfile.SUFFIX}"):  # ältere Fassungen dieser Vorlage
        old.unlink(missing_ok=True)
    (d / f"{t.name}.json").unlink(missing_ok=True)
    return d / bonysfile.default_filename(t.name, version)


def remember_cache(t: templates.Template, file: Path, progress: Callable[[float], None] | None = None) -> str:
    """Exportierte Datei als Zwischenspeicher der Vorlage merken. Gibt die SHA-256 der ganzen Datei zurück."""
    sha = file_sha256(file, progress)
    meta = cache_dir(t) / f"{t.name}.json"
    meta.write_text(json.dumps({"key": _cache_key(t), "file": file.name, "size": file.stat().st_size,
                                "sha256": sha}), "utf-8")
    return sha


def file_sha256(path: Path, progress: Callable[[float], None] | None = None) -> str:
    return bonysfile._hash_file(path, progress)



# ---------------------------------------------------------------- Kursleiter: Server
@dataclass
class Participant:
    key: str
    name: str
    address: str
    status: str = "verbunden"     # verbunden | wartet | lädt | fertig | abgebrochen
    queue: int = 0
    done: int = 0
    total: int = 0
    started: float = 0.0
    last: float = field(default_factory=time.monotonic)
    speed: float = 0.0            # Bytes/s (geglättet)
    lektion: int = 0              # Kurspaket: aktuelle Lektion (ab 1), 0 = noch nichts gemeldet
    geschafft: bool | None = None

    @property
    def percent(self) -> float:
        return 100.0 * self.done / self.total if self.total else 0.0

    def eta(self) -> float | None:
        if self.status != "lädt" or self.speed <= 0:
            return None
        return (self.total - self.done) / self.speed


class Guarded:
    """Gemeinsame Basis der Schulungs-Server (Freigabe, Vorführung): Code mit Ratenbegrenzung, Ereignisliste,
    Zeitlimit. Unterklassen setzen ``stop()`` um."""

    def __init__(self, code: str | None = None, timeout_min: int = DEFAULT_TIMEOUT_MIN):
        self.code = normalize_code(code) if code else new_code()
        self.timeout_min = max(1, int(timeout_min))
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.fails: dict[str, list[float]] = {}
        self.fails_total = 0
        self.deadline = 0.0
        self.stopped = threading.Event()
        self.stop_reason = ""

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic()) if self.deadline else 0.0

    def _event(self, text: str) -> None:
        with self.lock:
            self.events.append(f"{datetime.now().strftime('%H:%M:%S')} {text}")
            del self.events[:-200]

    def stop(self, reason: str = "Beendet.") -> None:
        raise NotImplementedError

    def locked(self, addr: str) -> bool:
        now = time.monotonic()
        with self.lock:
            return len([t for t in self.fails.get(addr, []) if now - t < LOCK_SECONDS]) >= MAX_FAILS_PER_ADDR

    def protocol_refusal(self, headers) -> dict | None:
        """None = Kurs-Protokoll der Gegenstelle passt (Browser schicken keins → passt), sonst Antwort für 426."""
        try:
            check_protocol(headers.get(PROTOCOL_HEADER), str(headers.get(VERSION_HEADER) or "")[:20],
                           we_are="Kursleiter", ours=PROTOCOL)
        except ProtocolMismatch as e:
            self._event(str(e))
            return {"error": str(e), "protocol": PROTOCOL, "version": __version__}
        return None

    def check_code(self, addr: str, code: str) -> str | None:
        """None = in Ordnung, sonst Grund für die Ablehnung („gesperrt“/„falsch“)."""
        now = time.monotonic()
        with self.lock:
            recent = [t for t in self.fails.get(addr, []) if now - t < LOCK_SECONDS]
            self.fails[addr] = recent
            if len(recent) >= MAX_FAILS_PER_ADDR:
                return "gesperrt"
            if hmac.compare_digest(normalize_code(code).encode(), self.code.encode()):
                return None
            recent.append(now)
            self.fails_total += 1
            too_many = self.fails_total >= MAX_FAILS_TOTAL
        self._event(f"Falscher Code von {addr}.")
        if too_many:
            self.stop("Zu viele falsche Codes – zur Sicherheit beendet.")
        return "falsch"


class Share(Guarded):
    """Freigabe einer .bonys-Datei. ``start()`` … ``stop()``; Status über ``participants`` und ``events``."""

    def __init__(self, file: Path, *, port: int = DEFAULT_PORT, timeout_min: int = DEFAULT_TIMEOUT_MIN,
                 max_downloads: int = DEFAULT_MAX_DOWNLOADS, code: str | None = None, sha256: str | None = None,
                 bind: str = "", advertise: bool = True, kurspaket: tuple[bytes, dict] | None = None):
        """``kurspaket``: (gepackte Datei, Angaben ``paket_id``, ``name``, ``version``, ``lektionen``) – die
        Teilnehmer bekommen es mit der Vorlage und melden ihren Fortschritt."""
        super().__init__(code, timeout_min)
        self.kurspaket_daten = kurspaket[0] if kurspaket else b""
        self.kurspaket = {**kurspaket[1], "sha256": hashlib.sha256(kurspaket[0]).hexdigest(),
                          "groesse": len(kurspaket[0])} if kurspaket else None
        self.file = Path(file)
        self.manifest = bonysfile.read_manifest(self.file)
        self.size = self.file.stat().st_size
        self.sha256 = sha256 or file_sha256(self.file)
        self.port = port
        self.bind = bind
        self.max_downloads = max(1, int(max_downloads))
        self.cert, key = make_certificate()
        self.fingerprint = hashlib.sha256(self.cert).hexdigest()
        self._ctx = server_context(self.cert, key)
        del key
        self.participants: dict[str, Participant] = {}
        self.active = 0
        self.waiting: list[str] = []
        self.advertise = advertise
        self.advertiser: announce.Advertiser | None = None
        self.httpd: ThreadingHTTPServer | None = None
        self._threads: list[threading.Thread] = []

    # ---------- Anzeige ----------
    def addresses(self) -> list[str]:
        return [self.bind] if self.bind and self.bind not in ("0.0.0.0", "::") else local_addresses()

    def link(self, host: str | None = None) -> str:
        return share_link(host or (self.addresses() or ["127.0.0.1"])[0], self.port, self.code, self.fingerprint)

    # ---------- Lebenszyklus ----------
    def start(self) -> None:
        share = self

        class Handler(_Handler):
            pass

        Handler.share = share
        try:
            httpd = _Server((self.bind, self.port), Handler)
        except OSError as e:
            raise ShareError(tr("Port {port} ist belegt oder nicht erlaubt ({wert}). Einen anderen Port wählen (z. "
                                "B. 47111).", port=self.port, wert=e.strerror or e)) from e
        httpd.socket = self._ctx.wrap_socket(httpd.socket, server_side=True, do_handshake_on_connect=False)
        self.port = httpd.server_address[1]
        self.httpd = httpd
        self.deadline = time.monotonic() + self.timeout_min * 60
        t = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5}, name="freigabe", daemon=True)
        t.start()
        w = threading.Thread(target=self._watch, name="freigabe-ende", daemon=True)
        w.start()
        self._threads = [t, w]
        if self.advertise:
            m = self.manifest
            self.advertiser = announce.Advertiser(
                f"{m['name']} {m.get('version', '')}".strip(), self.port, self.addresses(),
                {"name": m["name"], "version": m.get("version", ""), "creator": m.get("creator", "")[:60],
                 "fp": self.fingerprint, "v": "1"})
            if not self.advertiser.start():
                self._event(self.advertiser.error)
                self.advertiser = None
        self._event(f"Freigabe gestartet auf Port {self.port} (endet nach {self.timeout_min} min).")

    def _watch(self) -> None:
        while not self.stopped.wait(1):
            if self.remaining() <= 0:
                self.stop("Zeit abgelaufen – Freigabe automatisch beendet.")
                return

    def stop(self, reason: str = "Freigabe beendet.") -> None:
        if self.stopped.is_set():
            return
        self.stop_reason = reason
        self.stopped.set()
        if self.advertiser:
            self.advertiser.stop()
            self.advertiser = None
        if self.httpd:
            threading.Thread(target=self.httpd.shutdown, daemon=True).start()
            with contextlib.suppress(OSError):
                self.httpd.server_close()
        self._event(reason)

    # ---------- Zugriff ----------
    def participant(self, addr: str, name: str) -> Participant:
        name = re.sub(r"[^\w .-]", "", name or "")[:40] or addr
        key = f"{addr}|{name}"
        with self.lock:
            p = self.participants.get(key)
            if p is None:
                p = self.participants[key] = Participant(key=key, name=name, address=addr)
                new = True
            else:
                new = False
            p.last = time.monotonic()
        if new:
            self._event(f"{name} ({addr}) ist verbunden.")
        return p

    def acquire(self, p: Participant) -> int:
        """0 = darf laden, sonst Platz in der Warteschlange."""
        now = time.monotonic()
        with self.lock:
            self.waiting = [k for k in self.waiting if k == p.key or
                            now - self.participants[k].last < WAITING_STALE]
            if p.key not in self.waiting:
                self.waiting.append(p.key)
            pos = self.waiting.index(p.key)
            free = self.max_downloads - self.active
            if pos < free:
                self.waiting.remove(p.key)
                self.active += 1
                p.queue = 0
                return 0
            p.status, p.queue = "wartet", pos - free + 1
            return p.queue

    def release(self) -> None:
        with self.lock:
            self.active = max(0, self.active - 1)

    def info(self) -> dict:
        return {"app": "bonys-agents", "api": 1, "protocol": PROTOCOL, "version": __version__,
                "manifest": self.manifest,
                "file": {"name": self.file.name, "size": self.size, "sha256": self.sha256},
                "max_downloads": self.max_downloads, "ends_in": int(self.remaining()),
                **({"kurspaket": self.kurspaket} if self.kurspaket else {})}

    def fortschritt(self, p: Participant, d) -> bool:
        """Gemeldeten Fortschritt übernehmen (nur Lektion und geschafft) – False, wenn er nicht passt."""
        if self.kurspaket is None or not isinstance(d, dict):
            return False
        lektion, geschafft = d.get("lektion"), d.get("geschafft")
        if not isinstance(lektion, int) or isinstance(lektion, bool) or not 1 <= lektion <= 100 \
                or (self.kurspaket["lektionen"] and lektion > self.kurspaket["lektionen"]) \
                or not (geschafft is None or isinstance(geschafft, bool)):
            return False
        with self.lock:
            p.lektion, p.geschafft = lektion, geschafft
        return True


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Unter Windows hieße SO_REUSEADDR: ein anderes Programm dürfte denselben Port mitbenutzen
    allow_reuse_address = sys.platform != "win32"
    request_queue_size = 32

    def handle_error(self, request, client_address) -> None:  # keine Tracebacks bei abgebrochenen Verbindungen
        pass


class _Handler(BaseHTTPRequestHandler):
    share: Share
    server_version = "BonysAgents"
    sys_version = ""
    timeout = 60
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args) -> None:  # nichts auf die Konsole (Codes stehen nie in der URL)
        pass

    def setup(self) -> None:
        super().setup()
        with contextlib.suppress(OSError, ssl.SSLError):
            self.connection.do_handshake()

    def _json(self, status: int, data: dict, headers: dict | None = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _auth(self) -> Participant | None:
        s = self.share
        addr = self.client_address[0]
        if s.stopped.is_set():
            self._json(410, {"error": "Die Freigabe ist beendet."})
            return None
        refusal = s.protocol_refusal(self.headers)
        if refusal:
            self._json(426, refusal)
            return None
        why = s.check_code(addr, self.headers.get(CODE_HEADER, ""))
        if why == "gesperrt":
            self._json(429, {"error": "Zu viele falsche Codes – bitte eine Minute warten."},
                       {"Retry-After": str(LOCK_SECONDS)})
            return None
        if why:
            self._json(403, {"error": "Falscher Freigabe-Code."})
            return None
        return s.participant(addr, self.headers.get(CLIENT_HEADER, ""))

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in (f"{API}/info", f"{API}/download", f"{API}/kurspaket") \
                or (path == f"{API}/kurspaket" and self.share.kurspaket is None):
            self._json(404, {"error": "Nicht gefunden."})
            return
        p = self._auth()
        if p is None:
            return
        if path == f"{API}/info":
            self._json(200, self.share.info())
            return
        if path == f"{API}/kurspaket":
            daten = self.share.kurspaket_daten
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(daten)
            return
        self._download(p)

    def do_POST(self) -> None:  # noqa: N802
        """Nur der Fortschritt im Kurspaket – klein, ohne Inhalte aus dem Agent-PC."""
        if urlsplit(self.path).path != f"{API}/fortschritt" or self.share.kurspaket is None:
            self._method_not_allowed()
            return
        laenge = self.headers.get("Content-Length", "")
        if not laenge.isdigit() or int(laenge) > FORTSCHRITT_MAX:
            self._json(413, {"error": "Zu groß."})
            self.close_connection = True
            return
        roh = self.rfile.read(int(laenge))
        p = self._auth()
        if p is None:
            return
        try:
            d = json.loads(roh.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            d = None
        if not self.share.fortschritt(p, d):
            self._json(422, {"error": "Fortschritt nicht verstanden."})
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self) -> None:
        self._json(405, {"error": "Nur lesend."}, {"Allow": "GET, HEAD"})

    do_PUT = do_DELETE = do_PATCH = _method_not_allowed  # noqa: N815

    def _download(self, p: Participant) -> None:
        s = self.share
        size = s.size
        start = 0
        rng = self.headers.get("Range", "")
        if rng:
            m = re.fullmatch(r"bytes=(\d+)-", rng.strip())
            if not m or int(m.group(1)) >= size:
                self._json(416, {"error": "Ungültiger Bereich."}, {"Content-Range": f"bytes */{size}"})
                return
            start = int(m.group(1))
        if self.command == "HEAD":
            self._json(200, {"size": size})
            return
        pos = s.acquire(p)
        if pos:
            self._json(503, {"queue": pos, "error": f"Warteschlange: Platz {pos}"}, {"Retry-After": "5"})
            return
        p.status, p.total, p.done, p.started = "lädt", size, start, time.monotonic()
        s._event(f"{p.name} lädt" + (f" (fortgesetzt ab {start // (1024 * 1024)} MB)." if start else "."))
        try:
            self.send_response(206 if start else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size - start))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Bonys-Sha256", s.sha256)
            if start:
                self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
            self.end_headers()
            t_last, d_last = time.monotonic(), start
            with s.file.open("rb") as f:
                f.seek(start)
                while chunk := f.read(CHUNK):
                    if s.stopped.is_set():
                        raise ConnectionAbortedError
                    self.wfile.write(chunk)
                    p.done += len(chunk)
                    p.last = now = time.monotonic()
                    if now - t_last >= 1:
                        rate = (p.done - d_last) / (now - t_last)
                        p.speed = rate if not p.speed else 0.7 * p.speed + 0.3 * rate
                        t_last, d_last = now, p.done
            p.status = "fertig"
            s._event(f"{p.name}: Download fertig.")
        except (OSError, ConnectionError, ssl.SSLError):
            p.status = "abgebrochen"
            s._event(f"{p.name}: Download abgebrochen bei {p.percent:.0f} % (kann fortgesetzt werden).")
            self.close_connection = True
        finally:
            s.release()


