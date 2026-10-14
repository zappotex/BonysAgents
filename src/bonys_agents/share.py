# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: eine Vorlage im lokalen Netz bzw. im VPN freigeben – und als Teilnehmer beitreten.

Kursleiter: ``Share`` startet einen kleinen HTTPS-Server (nur solange freigegeben), der genau eine
``.bonys``-Datei ausliefert. Sicherheit:

- selbstsigniertes Zertifikat (Ed25519) **pro Freigabe**; sein SHA-256-Fingerabdruck steht auf dem Bildschirm
  des Kursleiters und im QR-Code. Teilnehmer prüfen ihn (und brechen ab, wenn er nicht passt).
- Zugriff nur mit Freigabe-Code (z. B. ``4711-BONY``), Vergleich in konstanter Zeit, Sperre nach mehreren
  Fehlversuchen je Adresse, die Freigabe endet nach zu vielen Fehlversuchen insgesamt.
- nur lesend: GET/HEAD auf ``/bonys/v1/info`` und ``/bonys/v1/download`` – keine anderen Dateien erreichbar.
- endet automatisch nach der eingestellten Zeit; höchstens N gleichzeitige Downloads, der Rest wartet in
  einer Schlange (Antwort 503 mit Platz in der Schlange).

Teilnehmer: ``fetch_info`` (Fingerabdruck und Manifest, vor dem Download) und ``download`` (mit Fortschritt,
Fortsetzen per HTTP-Range nach einem Abbruch, Prüfsumme der ganzen Datei), danach Import wie bei einer Datei.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
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
from urllib.parse import parse_qs, quote, urlsplit

from bonys_agents import __version__, bonysfile, mdns, signing, storage, templates

DEFAULT_PORT = 47110
DEFAULT_TIMEOUT_MIN = 120
DEFAULT_MAX_DOWNLOADS = 4
MAX_FAILS_PER_ADDR = 5
LOCK_SECONDS = 60
MAX_FAILS_TOTAL = 100
API = "/bonys/v1"
CODE_HEADER = "X-Bonys-Code"
CLIENT_HEADER = "X-Bonys-Client"
CODE_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"  # ohne I, O, Q – gut vorlesbar
CHUNK = 1024 * 1024
WAITING_STALE = 30  # Sekunden ohne Nachfrage → nicht mehr in der Schlange

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


class ShareError(RuntimeError):
    pass


class WrongCode(ShareError):
    pass


class FingerprintMismatch(ShareError):
    pass


# ---------------------------------------------------------------- Code, Adresse, Fingerabdruck
def new_code() -> str:
    """Zufälliger, kurzer, gut vorlesbarer Code: 4 Ziffern, Bindestrich, 4 Buchstaben (z. B. 4711-BONY)."""
    digits = "".join(secrets.choice("0123456789") for _ in range(4))
    letters = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
    return f"{digits}-{letters}"


def normalize_code(code: str) -> str:
    """Getippten Code vereinheitlichen: Groß-/Kleinschreibung, Leerzeichen und Bindestrich egal,
    „O“ im Zahlenteil ist eine Null, „0“ im Buchstabenteil ein O."""
    raw = re.sub(r"[^0-9A-Za-z]", "", code or "").upper()
    if len(raw) != 8:
        return raw
    return f"{raw[:4].replace('O', '0')}-{raw[4:].replace('0', 'O')}"


def format_fingerprint(fp: str) -> str:
    fp = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()
    return ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))


def short_fingerprint(fp: str) -> str:
    """Zum Vergleichen auf dem Bildschirm: die ersten 8 Bytes, in Vierergruppen."""
    fp = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()[:16]
    return " ".join(fp[i:i + 4] for i in range(0, len(fp), 4))


@dataclass
class Target:
    host: str
    port: int = DEFAULT_PORT
    code: str = ""
    fingerprint: str = ""   # Hex ohne Trennzeichen, kleingeschrieben

    @property
    def netloc(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"


def parse_target(text: str, code: str = "", fingerprint: str = "") -> Target:
    """„192.168.1.5“, „pc.local:47110“, „[fd00::1]:47110“ oder ein Link bonys://ADRESSE:PORT?code=…&fp=…"""
    text = (text or "").strip()
    if not text:
        raise ValueError("Bitte die Adresse des Kursleiter-Rechners angeben.")
    if "://" not in text:
        text = "bonys://" + text
    u = urlsplit(text)
    if u.scheme not in ("bonys", "https") or not u.hostname:
        raise ValueError("Adresse nicht verstanden – z. B. 192.168.1.5:47110 oder bonys://…")
    q = parse_qs(u.query)
    try:
        port = u.port or DEFAULT_PORT
    except ValueError as e:
        raise ValueError("Ungültiger Port.") from e
    fp = re.sub(r"[^0-9A-Fa-f]", "", fingerprint or (q.get("fp") or [""])[0]).lower()
    if fp and len(fp) != 64:
        raise ValueError("Der Fingerabdruck muss 64 Hex-Zeichen haben (SHA-256).")
    return Target(host=u.hostname, port=port, code=normalize_code(code or (q.get("code") or [""])[0]),
                  fingerprint=fp)


def share_link(host: str, port: int, code: str, fingerprint: str) -> str:
    h = f"[{host}]" if ":" in host else host
    return f"bonys://{h}:{port}?code={quote(code)}&fp={fingerprint}"


def local_addresses() -> list[str]:
    """IPv4-Adressen dieses Rechners (ohne Loopback), VPN-Adressen (z. B. WireGuard) eingeschlossen."""
    out: list[str] = []
    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127.") \
                        and not a.address.startswith("169.254."):
                    out.append(a.address)
    except Exception:  # noqa: BLE001 – dann wenigstens die Standard-Route
        pass
    if not out:
        with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # Testnetz – es wird nichts gesendet
            out.append(s.getsockname()[0])
    return list(dict.fromkeys(out))


def address_kind(addr: str) -> str:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return ""
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return "VPN"
    return "LAN" if ip.is_private else "öffentlich"


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


def make_certificate(common_name: str = "Bony's Agents Freigabe", days: int = 2) -> tuple[bytes, bytes]:
    """Selbstsigniertes X.509-Zertifikat → (Zertifikat DER, privater Schlüssel PKCS#8 DER)."""
    seed = secrets.token_bytes(32)
    pub = signing.ed25519_public_key(seed)
    alg = _seq(_ED25519)
    name = _seq(_der(0x31, _seq(_der(0x06, bytes.fromhex("550403")), _der(0x0C, common_name.encode()))))
    now = datetime.now(timezone.utc)
    serial = int.from_bytes(secrets.token_bytes(16), "big") >> 1 or 1
    tbs = _seq(
        _der(0xA0, _der(0x02, b"\x02")),                                  # Version 3
        _der(0x02, serial.to_bytes((serial.bit_length() + 8) // 8, "big")),
        alg, name,
        _seq(_time(now - timedelta(hours=1)), _time(now + timedelta(days=days))),
        name,
        _seq(alg, _der(0x03, b"\0" + pub)),
    )
    cert = _seq(tbs, alg, _der(0x03, b"\0" + signing.ed25519_sign(seed, tbs)))
    key = _seq(_der(0x02, b"\0"), alg, _der(0x04, _der(0x04, seed)))
    return cert, key


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


def client_context() -> ssl.SSLContext:
    """Kein CA-Check (selbstsigniert) – stattdessen wird der Fingerabdruck verglichen (``_connect``)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
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


class Share:
    """Freigabe einer .bonys-Datei. ``start()`` … ``stop()``; Status über ``participants`` und ``events``."""

    def __init__(self, file: Path, *, port: int = DEFAULT_PORT, timeout_min: int = DEFAULT_TIMEOUT_MIN,
                 max_downloads: int = DEFAULT_MAX_DOWNLOADS, code: str | None = None, sha256: str | None = None,
                 bind: str = "", advertise: bool = True):
        self.file = Path(file)
        self.manifest = bonysfile.read_manifest(self.file)
        self.size = self.file.stat().st_size
        self.sha256 = sha256 or file_sha256(self.file)
        self.port = port
        self.bind = bind
        self.timeout_min = max(1, int(timeout_min))
        self.max_downloads = max(1, int(max_downloads))
        self.code = normalize_code(code) if code else new_code()
        self.cert, key = make_certificate()
        self.fingerprint = hashlib.sha256(self.cert).hexdigest()
        self._ctx = server_context(self.cert, key)
        del key
        self.participants: dict[str, Participant] = {}
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.active = 0
        self.waiting: list[str] = []
        self.fails: dict[str, list[float]] = {}
        self.fails_total = 0
        self.deadline = 0.0
        self.stopped = threading.Event()
        self.stop_reason = ""
        self.advertise = advertise
        self.advertiser: mdns.Advertiser | None = None
        self.httpd: ThreadingHTTPServer | None = None
        self._threads: list[threading.Thread] = []

    # ---------- Anzeige ----------
    def addresses(self) -> list[str]:
        return [self.bind] if self.bind and self.bind not in ("0.0.0.0", "::") else local_addresses()

    def link(self, host: str | None = None) -> str:
        return share_link(host or (self.addresses() or ["127.0.0.1"])[0], self.port, self.code, self.fingerprint)

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic()) if self.deadline else 0.0

    def _event(self, text: str) -> None:
        with self.lock:
            self.events.append(f"{datetime.now().strftime('%H:%M:%S')} {text}")
            del self.events[:-200]

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
            self.advertiser = mdns.Advertiser(
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
            self.stop("Zu viele falsche Codes – Freigabe zur Sicherheit beendet.")
        return "falsch"

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
        return {"app": "bonys-agents", "api": 1, "version": __version__, "manifest": self.manifest,
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


# ---------------------------------------------------------------- Teilnehmer: Client
@dataclass
class RemoteInfo:
    target: Target
    fingerprint: str
    manifest: dict
    file_name: str
    size: int
    sha256: str
    ends_in: int = 0


def _client_name() -> str:
    with contextlib.suppress(OSError):
        return socket.gethostname()[:40]
    return ""


def _connect(target: Target, timeout: float = 15) -> tuple[http.client.HTTPSConnection, str]:
    conn = http.client.HTTPSConnection(target.host, target.port, timeout=timeout, context=client_context())
    try:
        conn.connect()
    except (OSError, ssl.SSLError) as e:
        conn.close()
        raise ShareError(f"Keine Verbindung zu {target.netloc}: {e}. Läuft die Freigabe noch? Gleiches Netz bzw. "
                         "VPN verbunden? Lässt die Firewall des Kursleiter-Rechners den Port zu?") from e
    der = conn.sock.getpeercert(binary_form=True) or b""
    fp = hashlib.sha256(der).hexdigest()
    if target.fingerprint and not hmac.compare_digest(fp, target.fingerprint):
        conn.close()
        raise FingerprintMismatch("Der Fingerabdruck des Zertifikats passt nicht zur Freigabe – Verbindung "
                                  "abgebrochen. Falsche Adresse, oder jemand im Netz gibt sich als Kursleiter aus.")
    return conn, fp


def _headers(target: Target, extra: dict | None = None) -> dict:
    h = {CODE_HEADER: target.code, CLIENT_HEADER: _client_name(), "User-Agent": f"BonysAgents/{__version__}"}
    h.update(extra or {})
    return h


def _error(resp: http.client.HTTPResponse) -> ShareError:
    try:
        msg = json.loads(resp.read().decode("utf-8")).get("error", "")
    except (ValueError, OSError):
        msg = ""
    if resp.status == 403:
        return WrongCode(msg or "Falscher Freigabe-Code.")
    return ShareError(msg or f"Antwort {resp.status} vom Kursleiter-Rechner.")


def fetch_info(target: Target) -> RemoteInfo:
    """Fingerabdruck prüfen (bzw. ermitteln) und Inhalt der Freigabe holen – vor dem Download anzeigen."""
    if not target.code:
        raise WrongCode("Bitte den Freigabe-Code eingeben (z. B. 4711-BONY).")
    conn, fp = _connect(target)
    try:
        conn.request("GET", f"{API}/info", headers=_headers(target))
        resp = conn.getresponse()
        if resp.status != 200:
            raise _error(resp)
        data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise ShareError(f"Antwort des Kursleiter-Rechners nicht verstanden: {e}") from e
    finally:
        conn.close()
    m = bonysfile.validate_manifest(data.get("manifest"))
    f = data.get("file") or {}
    if not isinstance(f.get("size"), int) or not re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))):
        raise ShareError("Antwort des Kursleiter-Rechners unvollständig.")
    name = bonysfile.default_filename(m["name"], m.get("version") or "1")
    return RemoteInfo(target=target, fingerprint=fp, manifest=m, file_name=name, size=f["size"],
                      sha256=f["sha256"], ends_in=int(data.get("ends_in") or 0))


def download(info: RemoteInfo, dest_dir: Path, progress: Callable[[str, float, str], None] | None = None,
             cancel: threading.Event | None = None, retry_wait: float = 5.0) -> Path:
    """Datei laden – setzt nach einem Abbruch fort (HTTP-Range), wartet in der Schlange, prüft die Prüfsumme.

    ``progress(phase, 0..1, Text)``, phase: „queue“ | „download“ | „verify“. Gibt die fertige .bonys-Datei zurück.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / info.file_name
    part = final.with_name(final.name + ".teil")
    meta = final.with_name(final.name + ".teil.json")
    target = Target(info.target.host, info.target.port, info.target.code, info.fingerprint)
    want = {"sha256": info.sha256, "size": info.size}
    try:
        if json.loads(meta.read_text("utf-8")) != want:
            part.unlink(missing_ok=True)
    except (OSError, ValueError):
        part.unlink(missing_ok=True)
    meta.write_text(json.dumps(want), "utf-8")
    if shutil.disk_usage(dest_dir).free < info.size - (part.stat().st_size if part.exists() else 0) + 256 * 2**20:
        raise ShareError(f"Zu wenig Platz in {dest_dir} ({info.size / storage.GB:.1f} GB nötig).")

    def report(phase: str, frac: float, msg: str) -> None:
        if cancel is not None and cancel.is_set():
            raise bonysfile.Cancelled("Download abgebrochen – „Beitreten“ setzt später fort.")
        if progress:
            progress(phase, frac, msg)

    errors = 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        if have >= info.size:
            break
        report("download", have / info.size, "Verbinde …")
        try:
            conn, _fp = _connect(target)
        except FingerprintMismatch:
            raise
        except ShareError:
            errors += 1
            if errors > 5:
                raise
            _sleep(retry_wait, report, "download", have / info.size, "Verbindung unterbrochen – neuer Versuch …")
            continue
        try:
            conn.request("GET", f"{API}/download", headers=_headers(target, {"Range": f"bytes={have}-"} if have
                                                                       else None))
            resp = conn.getresponse()
            if resp.status == 503:
                pos = json.loads(resp.read().decode("utf-8") or "{}").get("queue", "?")
                wait = float(resp.getheader("Retry-After") or retry_wait)
                _sleep(min(wait, 30), report, "queue", have / info.size,
                       f"Warteschlange: Platz {pos} – es laden gerade andere Teilnehmer …")
                continue
            if resp.status not in (200, 206):
                raise _error(resp)
            if resp.status == 200 and have:
                have = 0  # Server kann nicht fortsetzen → von vorn
            if (resp.getheader("X-Bonys-Sha256") or info.sha256) != info.sha256:
                raise ShareError("Die Freigabe hat sich geändert – bitte neu beitreten.")
            t0, d0 = time.monotonic(), have
            with part.open("r+b" if have else "wb") as out:
                out.seek(have)
                out.truncate()
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
                    have += len(chunk)
                    elapsed = time.monotonic() - t0
                    rate = (have - d0) / elapsed if elapsed > 0.5 else 0
                    eta = f" · noch {_fmt_eta((info.size - have) / rate)}" if rate > 0 else ""
                    report("download", have / info.size,
                           f"Lade … {have / storage.GB:.2f} / {info.size / storage.GB:.2f} GB"
                           + (f" · {rate / 2**20:.1f} MB/s" if rate else "") + eta)
            errors = 0
        except (OSError, http.client.HTTPException, ssl.SSLError) as e:
            errors += 1
            if errors > 5:
                raise ShareError(f"Download immer wieder unterbrochen: {e}") from e
            _sleep(retry_wait, report, "download", have / info.size, "Verbindung unterbrochen – setze fort …")
        finally:
            conn.close()
    report("verify", 0, "Prüfe die Prüfsumme (SHA-256) …")
    sha = bonysfile._hash_file(part, lambda f: report("verify", f, f"Prüfe die Prüfsumme … {f * 100:.0f} %"))
    if sha != info.sha256:
        part.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        raise ShareError("Prüfsumme stimmt nicht – die Datei wurde beschädigt. Bitte erneut beitreten.")
    final.unlink(missing_ok=True)
    os.replace(part, final)
    meta.unlink(missing_ok=True)
    report("verify", 1, f"Geladen und geprüft: {final.name}")
    return final


def _sleep(seconds: float, report, phase: str, frac: float, msg: str) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        report(phase, frac, msg)
        time.sleep(min(0.5, max(0.0, end - time.monotonic())))


def _fmt_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def discover(timeout: float = 2.5) -> list[mdns.Found]:
    """Freigaben im gleichen Netz finden (mDNS). In VPN-Netzen leer – dann Adresse eintippen."""
    try:
        return mdns.browse(timeout, local_addresses())
    except OSError:
        return []


def downloads_dir() -> Path:
    d = storage.data_dir() / "schulung"
    d.mkdir(parents=True, exist_ok=True)
    return d
