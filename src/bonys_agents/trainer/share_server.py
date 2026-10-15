# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: eine Vorlage im lokalen Netz bzw. im VPN freigeben (nur in „Bony's Agents Kursleiter“).

``Share`` startet einen kleinen HTTPS-Server (nur solange freigegeben), der genau eine ``.bonys``-Datei ausliefert.
Sicherheit:

- selbstsigniertes Zertifikat (Ed25519) **pro Freigabe**; sein SHA-256-Fingerabdruck steht auf dem Bildschirm
  des Kursleiters und im QR-Code. Teilnehmer prüfen ihn (und brechen ab, wenn er nicht passt).
- Zugriff nur mit Freigabe-Code (z. B. ``4711-BONY``), Vergleich in konstanter Zeit, Sperre nach mehreren
  Fehlversuchen je Adresse, die Freigabe endet nach zu vielen Fehlversuchen insgesamt.
- nur lesend: GET/HEAD auf ``/bonys/v1/info`` und ``/bonys/v1/download`` – keine anderen Dateien erreichbar.
- endet automatisch nach der eingestellten Zeit; höchstens N gleichzeitige Downloads, der Rest wartet in
  einer Schlange (Antwort 503 mit Platz in der Schlange).
- passt das Kurs-Protokoll eines Teilnehmers nicht (``share.PROTOCOL``), Antwort 426 mit beiden Versionen.

Die Teilnehmer-Seite (beitreten, laden) steht in ``bonys_agents.share`` und ist in beiden Editionen enthalten.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import ssl
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from bonys_agents import __version__, bonysfile, signing, templates
from bonys_agents.trainer import announce
from bonys_agents.share import (
    API, CHUNK, CLIENT_HEADER, CODE_HEADER, CODE_LETTERS, DEFAULT_MAX_DOWNLOADS, DEFAULT_PORT, DEFAULT_TIMEOUT_MIN,
    LOCK_SECONDS, MAX_FAILS_PER_ADDR, MAX_FAILS_TOTAL, PROTOCOL, PROTOCOL_HEADER, VERSION_HEADER, WAITING_STALE,
    ProtocolMismatch, ShareError, check_protocol, local_addresses, normalize_code, share_link,
)

FIREWALL_HINTS = {
    "windows": "Windows fragt beim ersten Freigeben, ob Bony's Agents Verbindungen annehmen darf: „Zugriff "
               "zulassen“ – nur für „Private Netzwerke“ (Heim-/Firmennetz), nicht für öffentliche. Ist das Netz als "
               "„Öffentlich“ eingestuft, in den Windows-Einstellungen auf „Privat“ umstellen.",
    "macos": "macOS fragt ggf. „Eingehende Netzwerkverbindungen akzeptieren?“ – „Erlauben“. Ist unter "
             "Systemeinstellungen → Netzwerk → Firewall „Alle eingehenden Verbindungen blockieren“ an, finden "
             "die Teilnehmer die Freigabe nicht.",
    "linux": "Linux: Meist ist keine Firewall aktiv. Mit ufw den Port nur für die Schulung öffnen und danach wieder "
             "schließen: sudo ufw allow {port}/tcp … sudo ufw delete allow {port}/tcp (mDNS: 5353/udp). Mit "
             "firewalld nur vorübergehend (ohne --permanent): sudo firewall-cmd --add-port={port}/tcp.",
}



def new_code() -> str:
    """Zufälliger, kurzer, gut vorlesbarer Code: 4 Ziffern, Bindestrich, 4 Buchstaben (z. B. 4711-BONY)."""
    digits = "".join(secrets.choice("0123456789") for _ in range(4))
    letters = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
    return f"{digits}-{letters}"



# ---------------------------------------------------------------- Zertifikat (Ed25519, ohne Abhängigkeiten)
_ED25519 = bytes.fromhex("06032b6570")


def _der(tag: int, content: bytes) -> bytes:
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + content


def _seq(*parts: bytes) -> bytes:
    return _der(0x30, b"".join(parts))


def _time(t: datetime) -> bytes:
    return _der(0x17, t.strftime("%y%m%d%H%M%SZ").encode())


def _oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for n in parts[2:]:
        chunk = [n & 0x7F]
        while n > 0x7F:
            n >>= 7
            chunk.append(0x80 | (n & 0x7F))
        out += bytes(reversed(chunk))
    return _der(0x06, out)


def _int(n: int) -> bytes:
    return _der(0x02, n.to_bytes(n.bit_length() // 8 + 1, "big"))


# NIST P-256 (secp256r1) – Browser können kein Ed25519 im TLS-Zertifikat, deshalb ECDSA für die Seiten im Browser
_P = 2**256 - 2**224 + 2**192 + 2**96 - 1
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _ec_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        m = (3 * a[0] * a[0] - 3) * pow(2 * a[1], -1, _P) % _P
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (m * m - a[0] - b[0]) % _P
    return x, (m * (a[0] - x) - a[1]) % _P


def _ec_mul(k: int, point=_G):
    out = None
    while k:
        if k & 1:
            out = _ec_add(out, point)
        point = _ec_add(point, point)
        k >>= 1
    return out


def _ecdsa_sign(d: int, data: bytes) -> bytes:
    h = int.from_bytes(hashlib.sha256(data).digest(), "big")
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r = _ec_mul(k)[0] % _N
        sig = pow(k, -1, _N) * (h + r * d) % _N
        if r and sig:
            return _seq(_int(r), _int(sig))


def make_certificate(common_name: str = "Bony's Agents Freigabe", days: int = 2, *, kind: str = "ed25519",
                     addresses: list[str] | tuple[str, ...] = (), names: list[str] | tuple[str, ...] = (),
                     ) -> tuple[bytes, bytes]:
    """Selbstsigniertes X.509-Zertifikat → (Zertifikat DER, privater Schlüssel PKCS#8 DER).

    ``kind``: „ed25519“ (Freigabe, Gegenstelle ist Bony's Agents) oder „ec“ (ECDSA P-256 – für Seiten, die im
    Browser geöffnet werden). ``addresses``/``names`` landen als subjectAltName im Zertifikat.
    """
    if kind == "ec":
        d = secrets.randbelow(_N - 1) + 1
        x, y = _ec_mul(d)
        point = b"\4" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
        spki = _seq(_seq(_oid("1.2.840.10045.2.1"), _oid("1.2.840.10045.3.1.7")), _der(0x03, b"\0" + point))
        alg = _seq(_oid("1.2.840.10045.4.3.2"))

        def sign(data: bytes) -> bytes:
            return _ecdsa_sign(d, data)
        key = _seq(_der(0x02, b"\0"), _seq(_oid("1.2.840.10045.2.1"), _oid("1.2.840.10045.3.1.7")),
                   _der(0x04, _seq(_der(0x02, b"\1"), _der(0x04, d.to_bytes(32, "big")),
                                   _der(0xA1, _der(0x03, b"\0" + point)))))
    else:
        seed = secrets.token_bytes(32)
        alg = _seq(_ED25519)
        spki = _seq(alg, _der(0x03, b"\0" + signing.ed25519_public_key(seed)))

        def sign(data: bytes) -> bytes:
            return signing.ed25519_sign(seed, data)
        key = _seq(_der(0x02, b"\0"), alg, _der(0x04, _der(0x04, seed)))
    name = _seq(_der(0x31, _seq(_der(0x06, bytes.fromhex("550403")), _der(0x0C, common_name.encode()))))
    now = datetime.now(timezone.utc)
    serial = int.from_bytes(secrets.token_bytes(16), "big") >> 1 or 1
    alt = b""
    for a in addresses:
        with contextlib.suppress(ValueError):
            alt += _der(0x87, ipaddress.ip_address(a).packed)
    for n in names:
        if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", n):
            alt += _der(0x82, n.encode())
    exts = _seq(_oid("2.5.29.37"), _der(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1"))))  # nur Server-Authentifizierung
    if alt:
        exts += _seq(_oid("2.5.29.17"), _der(0x04, _seq(alt)))
    tbs = _seq(
        _der(0xA0, _der(0x02, b"\x02")),                                  # Version 3
        _der(0x02, serial.to_bytes((serial.bit_length() + 8) // 8, "big")),
        alg, name,
        _seq(_time(now - timedelta(hours=1)), _time(now + timedelta(days=days))),
        name,
        spki,
        _der(0xA3, _seq(exts)),
    )
    return _seq(tbs, alg, _der(0x03, b"\0" + sign(tbs))), key


def _pem(label: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode()
    return f"-----BEGIN {label}-----\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64)) \
        + f"\n-----END {label}-----\n"


def server_context(cert: bytes, key: bytes) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(prefix="bonys-share-") as d:
        cf, kf = Path(d) / "c.pem", Path(d) / "k.pem"
        fd = os.open(kf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(_pem("PRIVATE KEY", key))
        cf.write_text(_pem("CERTIFICATE", cert))
        ctx.load_cert_chain(str(cf), str(kf))
    return ctx



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
                 bind: str = "", advertise: bool = True):
        super().__init__(code, timeout_min)
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
            raise ShareError(f"Port {self.port} ist belegt oder nicht erlaubt ({e.strerror or e}). Einen anderen "
                             "Port wählen (z. B. 47111).") from e
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
                "max_downloads": self.max_downloads, "ends_in": int(self.remaining())}


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
        if path not in (f"{API}/info", f"{API}/download"):
            self._json(404, {"error": "Nicht gefunden."})
            return
        p = self._auth()
        if p is None:
            return
        if path == f"{API}/info":
            self._json(200, self.share.info())
            return
        self._download(p)

    def _method_not_allowed(self) -> None:
        self._json(405, {"error": "Nur lesend."}, {"Allow": "GET, HEAD"})

    do_POST = do_PUT = do_DELETE = do_PATCH = _method_not_allowed  # noqa: N815

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


