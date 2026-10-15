# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: Live-Vorführung eines Agent-PCs im Browser der Teilnehmer (nur ansehen).

Der Kursleiter startet eine ``Presentation``: ein HTTPS-Server (wie bei der Freigabe: Zertifikat pro Vorführung,
Code mit Sperre nach Fehlversuchen, Zeitlimit) mit einer kleinen Startseite (Name + Code), einer Ansicht mit noVNC
und einem WebSocket-Proxy zum **lokalen** VNC-Socket des Agent-PCs (QEMU, nie direkt im Netz).

Zuschauen wird **im Proxy erzwungen**: Tastatur, Maus, Zwischenablage und alle sonstigen Nachrichten vom Browser an
den Agent-PC verwirft ``rfb.ClientFilter`` – nur was für das Bild nötig ist, geht durch. noVNC läuft zusätzlich im
view_only-Modus. „Pause“ trennt alle Zuschauer sofort vom Bildschirm (kein einziges Bild mehr, bis es weitergeht);
die Seite zeigt solange „Gleich geht's weiter“ und verbindet sich danach selbst wieder.

Jede Zuschauer-Verbindung läuft in einem Thread mit einer einzigen ``select``-Schleife – TLS-Sockets dürfen nicht
von zwei Threads gleichzeitig benutzt werden.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import select
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote, urlsplit

from bonys_agents import __version__, mdns, rfb, share, websocket

DEFAULT_PORT = 47120
DEFAULT_TIMEOUT_MIN = 90
DEFAULT_MAX_VIEWERS = 30
DEFAULT_QUALITY = "medium"
QUALITY_LABELS = {"low": "niedrig (langsames WLAN)", "medium": "mittel (WLAN)", "high": "hoch (Kabel/schnelles Netz)"}
COOKIE = "bonys_view"
API = "/bonys/v1/present"
REMOVED_BLOCK_SECONDS = 300
VIEWER_STALE = 60          # Sekunden ohne Verbindung und ohne Statusabfrage → zählt nicht mehr mit
FULL_FPS_VIEWERS = 8       # bis zu so vielen Zuschauern volle Bildrate, darüber anteilig weniger
MIN_FPS = 1.0
# WebSocket-Schließcodes, die die Seite versteht
CLOSE_ENDED, CLOSE_PAUSED, CLOSE_IDLE, CLOSE_REMOVED, CLOSE_ERROR = 4000, 4001, 4002, 4003, 4010

WARNING = ("Alle Teilnehmer sehen alles, was im Agent-PC angezeigt wird. Nutze Pause, bevor du Passwörter oder "
           "Tokens eingibst.")
SOUND_HINT = "Ton ist nicht dabei – im Raum sprechen oder z. B. Jitsi nutzen."
NAME_RE = re.compile(r"[^\w .'()-]")
HOST_RE = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(:\d{1,5})?$")


class PresentError(RuntimeError):
    pass


def resources_dir() -> Path:
    return Path(__file__).resolve().parent / "resources"


def novnc_dir() -> Path | None:
    """noVNC aus dem Paket (beim Bauen geholt: packaging/fetch-novnc.py) – None, wenn es fehlt."""
    d = resources_dir() / "novnc"
    return d if (d / "core" / "rfb.js").is_file() else None


def page_dir() -> Path:
    return resources_dir() / "present"


@dataclass
class Viewer:
    id: str                      # kurz, für die Anzeige beim Kursleiter (nicht geheim)
    token_hash: str              # SHA-256 des Cookies – der Cookie selbst wird nicht gespeichert
    name: str
    address: str
    joined: float = field(default_factory=time.time)
    last: float = field(default_factory=time.monotonic)
    connections: int = 0
    removed: bool = False
    dropped_input: int = 0       # verworfene Eingaben (Tippen/Klicken) – nur zur Anzeige

    @property
    def connected(self) -> bool:
        return self.connections > 0

    def active(self, now: float) -> bool:
        return not self.removed and (self.connections > 0 or now - self.last < VIEWER_STALE)


class Presentation(share.Guarded):
    """Kurs-Server des Kursleiters: Vorführung eines Bildschirms (``connect_vnc()`` liefert eine neue Verbindung
    zum lokalen VNC-Socket) und Hilfe-Schalter (``helpdesk``, siehe ``helpmode``). Ohne ``connect_vnc`` läuft nur
    der Hilfe-Schalter („gerade keine Vorführung“); ``set_screen``/``clear_screen`` starten bzw. beenden eine
    Vorführung, ohne dass sich Code oder Zertifikat ändern."""

    def __init__(self, title: str = "", connect_vnc: Callable[[], socket.socket] | None = None, *,
                 is_alive: Callable[[], bool] = lambda: True, port: int = DEFAULT_PORT,
                 timeout_min: int = DEFAULT_TIMEOUT_MIN, max_viewers: int = DEFAULT_MAX_VIEWERS,
                 quality: str = DEFAULT_QUALITY, code: str | None = None, bind: str = "",
                 advertise: bool = True, novnc: Path | None = None):
        super().__init__(code, timeout_min)
        if quality not in rfb.QUALITY:
            raise ValueError(f"Qualität: {', '.join(rfb.QUALITY)}")
        self.novnc = novnc if novnc is not None else novnc_dir()
        if self.novnc is None:
            raise PresentError("noVNC fehlt in dieser Installation (beim Bauen: python packaging/fetch-novnc.py).")
        self.title = title or f"Kurs auf {_hostname() or 'diesem Rechner'}"
        self.connect_vnc = connect_vnc
        self.is_alive = is_alive
        self.keep_running = False   # True: Hilfe-Schalter in Benutzung – Ende der Vorführung beendet den Server nicht
        self.port = port
        self.bind = bind
        self.max_viewers = max(1, int(max_viewers))
        self.quality = quality
        self.paused = False
        self.paused_since = 0.0
        self.viewers: dict[str, Viewer] = {}      # token_hash → Viewer
        self.blocked: dict[str, float] = {}       # Adresse → bis wann (nach „Zuschauer entfernen“)
        self.cpu_factor = 1.0
        self.cpu_percent = 0.0
        self.addresses_cache = self._addresses()
        self.cert, key = share.make_certificate("Bony's Agents Vorführung", kind="ec",
                                                addresses=self.addresses_cache + ["127.0.0.1"],
                                                names=[_hostname_local()] if _hostname_local() else [])
        self.fingerprint = hashlib.sha256(self.cert).hexdigest()
        self._ctx = share.server_context(self.cert, key)
        del key
        self.advertise = advertise
        self.advertiser: mdns.Advertiser | None = None
        self.httpd: share._Server | None = None
        self.started = 0.0
        from bonys_agents import helpmode  # hier: helpmode braucht dieses Modul

        self.helpdesk = helpmode.HelpDesk(self)

    @property
    def has_screen(self) -> bool:
        return self.connect_vnc is not None

    def set_screen(self, title: str, connect_vnc: Callable[[], socket.socket], *,
                   is_alive: Callable[[], bool] = lambda: True, quality: str | None = None,
                   max_viewers: int | None = None) -> None:
        """Vorführung (neu) beginnen – Zuschauer, die schon da sind, sehen das neue Bild ohne neuen Code."""
        if quality is not None:
            if quality not in rfb.QUALITY:
                raise ValueError(f"Qualität: {', '.join(rfb.QUALITY)}")
            self.quality = quality
        if max_viewers is not None:
            self.max_viewers = max(1, int(max_viewers))
        self.title = title
        self.is_alive = is_alive
        self.paused = False
        self.connect_vnc = connect_vnc
        self._event(f"Vorführung „{title}“ beginnt.")

    def clear_screen(self, reason: str = "Vorführung beendet.") -> None:
        """Vorführung beenden, Server (Hilfe-Schalter) läuft weiter. Zuschauer sehen „gerade keine Vorführung“."""
        if self.connect_vnc is None:
            return
        self.connect_vnc = None
        self.paused = False
        self.is_alive = lambda: True
        self._event(reason)

    # ---------- Anzeige ----------
    def _addresses(self) -> list[str]:
        return [self.bind] if self.bind and self.bind not in ("0.0.0.0", "::") else share.local_addresses()

    def addresses(self) -> list[str]:
        return list(self.addresses_cache)

    def url(self, host: str | None = None, with_code: bool = True, name: str = "") -> str:
        """Adresse für den Browser. Code (und Name) stehen hinter „#“ – der Browser schickt sie nicht mit."""
        h = host or (self.addresses_cache or ["127.0.0.1"])[0]
        h = f"[{h}]" if ":" in h else h
        frag = []
        if with_code:
            frag.append(f"code={quote(self.code)}")
            frag.append(f"fp={self.fingerprint[:16]}")
        if name:
            frag.append(f"name={quote(name)}")
        return f"https://{h}:{self.port}/" + ("#" + "&".join(frag) if frag else "")

    def fps(self) -> float:
        """Bildrate je Zuschauer: Grundwert der Qualitätsstufe, bei vielen Zuschauern bzw. hoher CPU-Last weniger."""
        base = float(rfb.QUALITY[self.quality][2])
        n = self.viewer_count()
        if n > FULL_FPS_VIEWERS:
            base *= FULL_FPS_VIEWERS / n
        return max(MIN_FPS, base * self.cpu_factor)

    def viewer_count(self) -> int:
        now = time.monotonic()
        with self.lock:
            return sum(1 for v in self.viewers.values() if v.active(now))

    def viewer_list(self) -> list[Viewer]:
        now = time.monotonic()
        with self.lock:
            return [v for v in self.viewers.values() if v.active(now)]

    # ---------- Lebenszyklus ----------
    def start(self) -> None:
        pres = self

        class Handler(_Handler):
            pass

        Handler.pres = pres
        try:
            httpd = share._Server((self.bind, self.port), Handler)
        except OSError as e:
            raise PresentError(f"Port {self.port} ist belegt oder nicht erlaubt ({e.strerror or e}). Einen anderen "
                               f"Port wählen (z. B. {DEFAULT_PORT + 1}).") from e
        httpd.socket = self._ctx.wrap_socket(httpd.socket, server_side=True, do_handshake_on_connect=False)
        self.port = httpd.server_address[1]
        self.httpd = httpd
        self.started = time.monotonic()
        self.deadline = self.started + self.timeout_min * 60
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5}, name="vorfuehrung",
                         daemon=True).start()
        threading.Thread(target=self._watch, name="vorfuehrung-ende", daemon=True).start()
        if self.advertise:
            self.advertiser = mdns.Advertiser(
                f"Vorführung {self.title}", self.port, self.addresses(),
                {"kind": "present", "name": self.title[:60], "creator": (_hostname() or "")[:60],
                 "fp": self.fingerprint, "v": "1"})
            if not self.advertiser.start():
                self._event(self.advertiser.error)
                self.advertiser = None
        what = "Vorführung" if self.has_screen else "Hilfe-Schalter"
        self._event(f"{what} gestartet auf Port {self.port} (endet nach {self.timeout_min} min).")

    def _watch(self) -> None:
        try:
            import psutil

            proc = psutil.Process()
            proc.cpu_percent(None)
        except Exception:  # noqa: BLE001 – ohne psutil keine Messung
            proc = None
        tick = 0
        while not self.stopped.wait(1):
            tick += 1
            if self.remaining() <= 0:
                self.stop("Zeit abgelaufen – Vorführung automatisch beendet.")
                return
            if tick % 2 == 0:
                try:
                    alive = self.is_alive()
                except Exception:  # noqa: BLE001
                    alive = False
                if not alive and self.has_screen:
                    if self.keep_running:
                        self.clear_screen("Der Agent-PC wurde ausgeschaltet – Vorführung beendet.")
                    else:
                        self.stop("Der Agent-PC wurde ausgeschaltet – Vorführung beendet.")
                        return
                if proc is not None:
                    with contextlib.suppress(Exception):
                        self._adjust_cpu(proc.cpu_percent(None))
            now = time.monotonic()
            with self.lock:
                for addr in [a for a, until in self.blocked.items() if until < now]:
                    del self.blocked[addr]

    def _adjust_cpu(self, percent: float) -> None:
        """CPU-Last dieses Prozesses (Proxy) in Prozent eines Kerns – bei hoher Last Bildrate senken."""
        self.cpu_percent = percent
        if percent > 80:
            self.cpu_factor = max(0.3, self.cpu_factor * 0.8)
        elif percent < 40 and self.cpu_factor < 1.0:
            self.cpu_factor = min(1.0, self.cpu_factor * 1.15)

    def stop(self, reason: str = "Vorführung beendet.") -> None:
        if self.stopped.is_set():
            return
        self.stop_reason = reason
        self.stopped.set()
        self.helpdesk.close_all()
        if self.advertiser:
            self.advertiser.stop()
            self.advertiser = None
        httpd = self.httpd
        if httpd:
            def shutdown() -> None:
                time.sleep(0.6)  # Zuschauer-Schleifen schicken noch „beendet“ an die Browser
                httpd.shutdown()
                with contextlib.suppress(OSError):
                    httpd.server_close()
            threading.Thread(target=shutdown, daemon=True).start()
        self._event(reason)

    def set_paused(self, paused: bool) -> None:
        if paused == self.paused:
            return
        self.paused = paused
        self.paused_since = time.monotonic() if paused else 0.0
        self._event("Pause – die Zuschauer sehen „Gleich geht's weiter“." if paused else "Weiter – Bild läuft wieder.")

    def remove_viewer(self, viewer_id: str) -> Viewer | None:
        with self.lock:
            v = next((x for x in self.viewers.values() if x.id == viewer_id), None)
            if v is None:
                return None
            v.removed = True
            self.blocked[v.address] = time.monotonic() + REMOVED_BLOCK_SECONDS
        self._event(f"{v.name} ({v.address}) entfernt – {REMOVED_BLOCK_SECONDS // 60} min gesperrt.")
        return v

    # ---------- Zuschauer ----------
    def join(self, addr: str, name: str, code: str) -> tuple[str | None, int, dict]:
        """Name + Code prüfen. Gibt (Cookie-Wert, HTTP-Status, Antwort) zurück."""
        if self.stopped.is_set():
            return None, 410, {"error": "Die Vorführung ist beendet.", "state": "ended"}
        with self.lock:
            until = self.blocked.get(addr, 0)
        if until > time.monotonic():
            return None, 403, {"error": "Du wurdest vom Kursleiter entfernt.", "state": "removed"}
        why = self.check_code(addr, code)
        if why == "gesperrt":
            return None, 429, {"error": "Zu viele falsche Codes – bitte eine Minute warten."}
        if why:
            return None, 403, {"error": "Falscher Code."}
        if self.viewer_count() >= self.max_viewers:
            return None, 503, {"error": f"Die Vorführung ist voll ({self.max_viewers} Zuschauer)."}
        name = NAME_RE.sub("", name or "").strip()[:40] or addr
        token = secrets.token_urlsafe(24)
        v = Viewer(id=secrets.token_hex(4), token_hash=_hash(token), name=name, address=addr)
        with self.lock:
            self.viewers[v.token_hash] = v
        self._event(f"{name} ({addr}) schaut zu.")
        return token, 200, {"ok": True, "name": name}

    def viewer(self, token: str | None) -> Viewer | None:
        if not token:
            return None
        h = _hash(token)
        with self.lock:
            v = self.viewers.get(h)
        if v is not None and hmac.compare_digest(v.token_hash, h):
            v.last = time.monotonic()
            return v
        return None

    def state_for(self, v: Viewer | None) -> str:
        if self.stopped.is_set():
            return "ended"
        if v is None:
            return "unknown"
        if v.removed:
            return "removed"
        if not self.has_screen:
            return "idle"
        return "paused" if self.paused else "live"

    def status(self, v: Viewer | None) -> dict:
        return {"state": self.state_for(v), "title": self.title, "viewers": self.viewer_count(),
                "ends_in": int(self.remaining()), "name": v.name if v else "", "version": __version__,
                "message": "Gleich geht's weiter …" if self.paused else
                           ("Gerade keine Vorführung – gleich geht's los." if not self.has_screen else "")}

    def close_reason(self, v: Viewer) -> tuple[int, str] | None:
        if self.stopped.is_set():
            return CLOSE_ENDED, "beendet"
        if v.removed:
            return CLOSE_REMOVED, "entfernt"
        if not self.has_screen:
            return CLOSE_IDLE, "keine Vorführung"
        if self.paused:
            return CLOSE_PAUSED, "pause"
        return None

    def serve_viewer(self, tls: ssl.SSLSocket, v: Viewer) -> None:
        """Proxy-Schleife: Browser (WebSocket, TLS) ↔ lokaler VNC-Socket. Kehrt zurück, wenn die Verbindung endet."""
        connect = self.connect_vnc
        try:
            if connect is None:
                raise OSError("keine Vorführung")
            up = connect()
        except OSError as e:
            self._event(f"{v.name}: Bildschirm nicht erreichbar ({e}).")
            _ws_close(tls, CLOSE_ERROR, "kein Bild")
            return
        with self.lock:
            v.connections += 1
        filt = rfb.ClientFilter(allow_input=lambda: False, quality=self.quality)
        try:
            pump_viewer(tls, up, filt, lambda: self.close_reason(v), self.fps)
        finally:
            with self.lock:
                v.connections -= 1
                v.dropped_input += filt.dropped_input
                v.last = time.monotonic()
            with contextlib.suppress(OSError):
                up.close()
        if filt.dropped_input:
            self._event(f"{v.name}: {filt.dropped_input} Eingaben verworfen (nur ansehen).")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hostname() -> str:
    with contextlib.suppress(OSError):
        return socket.gethostname()
    return ""


def _hostname_local() -> str:
    h = _hostname().split(".")[0]
    return f"{h}.local" if re.fullmatch(r"[A-Za-z0-9-]{1,63}", h or "") else ""


def _ws_close(tls: ssl.SSLSocket, code: int, reason: str) -> None:
    with contextlib.suppress(OSError, ValueError):
        tls.settimeout(2)
        tls.sendall(websocket.encode_frame(websocket.OP_CLOSE, websocket.close_payload(code, reason)))


def pump_viewer(tls, up: socket.socket, filt: rfb.ClientFilter, should_close: Callable[[], tuple[int, str] | None],
                fps: Callable[[], float] | None, client_side: bool = False) -> tuple[int, str] | None:
    """Eine Schleife für beide Richtungen (ein Thread, kein gleichzeitiger Zugriff auf den TLS-Socket).

    Gegenstelle → Agent-PC: WebSocket-Rahmen zerlegen, durch ``filt`` (verwirft Eingaben), FramebufferUpdateRequests
    höchstens ``fps()`` mal pro Sekunde weitergeben (``fps=None``: ungebremst). Agent-PC → Gegenstelle: unverändert
    als Binär-Rahmen. ``client_side``: wir sind der WebSocket-Client (Tunnel des Teilnehmers im Hilfe-Modus).
    """
    parser = websocket.FrameParser(expect_masked=not client_side)
    pending: bytes | None = None
    last_update = 0.0
    up.settimeout(10)

    def send(op: int, payload: bytes) -> None:
        tls.settimeout(30)
        tls.sendall(websocket.encode_frame(op, payload, mask=client_side))

    try:
        while True:
            why = should_close()
            if why:
                send(websocket.OP_CLOSE, websocket.close_payload(*why))
                return why
            now = time.monotonic()
            wait = 0.25
            if pending is not None:
                due = last_update + 1.0 / max(MIN_FPS, fps()) if fps else now
                if now >= due:
                    up.sendall(pending)
                    pending, last_update = None, now
                else:
                    wait = min(wait, due - now)
            readable = [tls] if tls.pending() else select.select([tls, up], [], [], wait)[0]
            if tls in readable:
                tls.settimeout(0.05)
                try:
                    data = tls.recv(65536)
                except (TimeoutError, ssl.SSLWantReadError):
                    data = None
                if data == b"":
                    return None
                if data:
                    for op, payload in parser.feed(data):
                        if op == websocket.OP_CLOSE:
                            send(websocket.OP_CLOSE, websocket.close_payload(1000))
                            return websocket.parse_close(payload)
                        if op == websocket.OP_PING:
                            send(websocket.OP_PONG, payload)
                        elif op == websocket.OP_BINARY:
                            for kind, raw in filt.feed(payload):
                                if kind == "update":
                                    # nur die neueste Anfrage zählt – eine vollständige (nicht inkrementelle)
                                    # bleibt aber vollständig
                                    if pending is not None and pending[1] == 0:
                                        raw = raw[:1] + b"\0" + raw[2:]
                                    pending = raw
                                else:
                                    up.sendall(raw)
            if up in readable:
                data = up.recv(65536)
                if not data:
                    send(websocket.OP_CLOSE, websocket.close_payload(CLOSE_ERROR, "Bildschirm getrennt"))
                    return CLOSE_ERROR, "Bildschirm getrennt"
                send(websocket.OP_BINARY, data)
    except rfb.ProtocolError as e:
        with contextlib.suppress(OSError, ValueError):
            send(websocket.OP_CLOSE, websocket.close_payload(1008, str(e)))
        return 1008, str(e)
    except websocket.WebSocketClosed as e:
        with contextlib.suppress(OSError, ValueError):
            send(websocket.OP_CLOSE, websocket.close_payload(e.code if e.code < 4000 else 1002))
        return e.code, e.reason
    except (OSError, ValueError, ssl.SSLError):
        return None


# ---------------------------------------------------------------- HTTP
_STATIC = {"present.css", "join.js", "view.js", "help.js", "logo.png"}
_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
          ".png": "image/png", ".html": "text/html; charset=utf-8", ".json": "application/json"}


class _Handler(BaseHTTPRequestHandler):
    pres: Presentation
    server_version = "BonysAgents"
    sys_version = ""
    timeout = 60
    protocol_version = "HTTP/1.1"
    rbufsize = 0  # ungepuffert: nach dem WebSocket-Upgrade liest die Proxy-Schleife direkt vom Socket

    def log_message(self, fmt, *args) -> None:
        pass

    def setup(self) -> None:
        super().setup()
        with contextlib.suppress(OSError, ssl.SSLError):
            self.connection.do_handshake()

    # ---------- Hilfen ----------
    def _host(self) -> str:
        h = self.headers.get("Host", "")
        return h if HOST_RE.match(h) else ""

    def _headers_common(self, ctype: str, length: int) -> None:
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        host = self._host()
        ws = f" wss://{host}" if host else ""
        self.send_header("Content-Security-Policy",
                         f"default-src 'self'; connect-src 'self'{ws}; img-src 'self' data: blob:; "
                         "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self._headers_common(ctype, len(body))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: dict, extra: dict | None = None) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   extra)

    def _file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._json(404, {"error": "Nicht gefunden."})
            return
        ctype = _TYPES.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, body, ctype)

    def _token(self) -> str | None:
        return self._token_named(COOKIE)

    def _token_named(self, name: str) -> str | None:
        raw = self.headers.get("Cookie", "")
        try:
            c = SimpleCookie(raw)
        except CookieError:
            return None
        m = c.get(name)
        return m.value if m else None

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        host = self._host()
        return bool(host) and origin == f"https://{host}"

    def _read_body(self, limit: int = 4096) -> bytes:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > limit:
            raise ValueError("zu groß")
        data = b""
        while len(data) < n:
            chunk = self.rfile.read(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    # ---------- Anfragen ----------
    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        p = self.pres
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._file(page_dir() / "index.html")
            return
        if path.startswith("/assets/") and path[8:] in _STATIC:
            name = path[8:]
            self._file((resources_dir() / name) if name == "logo.png" else page_dir() / name)
            return
        if p.helpdesk.handle(self, "GET", path):
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path == "/bonys/v1/info":   # für „Kurs beitreten“ in Bony's Agents – nur mit Code, wie bei der Freigabe
            why = p.check_code(self.client_address[0], self.headers.get(share.CODE_HEADER, ""))
            if why:
                self._json(429 if why == "gesperrt" else 403, {"error": "Falscher Code." if why == "falsch" else
                                                               "Zu viele falsche Codes – bitte eine Minute warten."})
                return
            self._json(200, {"app": "bonys-agents", "api": 1, "kind": "present", "title": p.title,
                             "version": __version__, "ends_in": int(p.remaining())})
            return
        if path == f"{API}/status":
            v = p.viewer(self._token())
            self._json(200 if v else 403, p.status(v))
            return
        v = p.viewer(self._token())
        if path == "/view":
            if v is None or v.removed:
                self._send(303, b"", "text/plain", {"Location": "/"})
                return
            self._file(page_dir() / "view.html")
            return
        if path.startswith("/novnc/"):
            if (v is None or v.removed) and not p.helpdesk.viewer_cookie_ok(self):
                self._json(403, {"error": "Bitte zuerst beitreten."})
                return
            f = _safe_file(p.novnc, path[7:])
            if f is None:
                self._json(404, {"error": "Nicht gefunden."})
                return
            self._file(f)
            return
        if path == f"{API}/ws":
            self._websocket(v)
            return
        self._json(404, {"error": "Nicht gefunden."})

    def do_POST(self) -> None:  # noqa: N802
        p = self.pres
        path = urlsplit(self.path).path
        if p.helpdesk.handle(self, "POST", path):
            return
        if path not in (f"{API}/join", f"{API}/leave"):
            self._json(404, {"error": "Nicht gefunden."})
            return
        if not self._same_origin():
            self._json(403, {"error": "Anfrage von einer fremden Seite."})
            return
        try:
            data = json.loads(self._read_body() or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._json(400, {"error": "Anfrage nicht verstanden."})
            return
        if path == f"{API}/leave":
            v = p.viewer(self._token())
            if v is not None:
                with p.lock:
                    p.viewers.pop(v.token_hash, None)
                p._event(f"{v.name} hat die Vorführung verlassen.")
            self._json(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; Secure; HttpOnly; "
                                                         "SameSite=Strict"})
            return
        token, status, answer = p.join(self.client_address[0], str(data.get("name", "")), str(data.get("code", "")))
        extra = {"Retry-After": str(share.LOCK_SECONDS)} if status == 429 else {}
        if token:
            extra["Set-Cookie"] = (f"{COOKIE}={token}; Path=/; Max-Age={p.timeout_min * 60 + 600}; Secure; "
                                   "HttpOnly; SameSite=Strict")
        self._json(status, answer, extra)

    def _method_not_allowed(self) -> None:
        self._json(405, {"error": "Nicht erlaubt."}, {"Allow": "GET, HEAD, POST"})

    do_PUT = do_DELETE = do_PATCH = _method_not_allowed  # noqa: N815

    def is_websocket(self) -> bool:
        return self.headers.get("Upgrade", "").lower() == "websocket" and bool(self.headers.get("Sec-WebSocket-Key"))

    def accept_websocket(self) -> None:
        """Antwort 101 – danach gehört der Socket der WebSocket-Schleife."""
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket.accept_key(self.headers.get("Sec-WebSocket-Key", "")))
        protocols = [x.strip() for x in self.headers.get("Sec-WebSocket-Protocol", "").split(",") if x.strip()]
        if "binary" in protocols:
            self.send_header("Sec-WebSocket-Protocol", "binary")
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True

    def _websocket(self, v: Viewer | None) -> None:
        p = self.pres
        if not self.is_websocket():
            self._json(400, {"error": "WebSocket erwartet."})
            return
        if not self._same_origin():
            self._json(403, {"error": "Anfrage von einer fremden Seite."})
            return
        if v is None:
            self._json(403, {"error": "Bitte zuerst beitreten."})
            return
        why = p.close_reason(v)
        if why:  # Pause/entfernt/beendet/keine Vorführung: gar nicht erst verbinden
            self._json(409, {"error": why[1], "state": p.state_for(v)})
            return
        self.accept_websocket()
        p.serve_viewer(self.connection, v)


def _safe_file(base: Path, rel: str) -> Path | None:
    """Nur Dateien aus dem noVNC-Ordner (core/, vendor/), keine Pfad-Tricks."""
    if not re.fullmatch(r"(core|vendor)/[A-Za-z0-9_./-]+\.js", rel) or ".." in rel.split("/"):
        return None
    f = (base / rel).resolve()
    try:
        f.relative_to(base.resolve())
    except ValueError:
        return None
    return f if f.is_file() else None


def describe(p: Presentation) -> str:
    """Text für die Kommandozeile."""
    rows = [f"Vorführung „{p.title}“ läuft – Code: {p.code}"]
    for a in p.addresses():
        kind = share.address_kind(a)
        rows.append(f"  Im Browser öffnen: https://{a}:{p.port}/" + (f"  ({kind})" if kind else ""))
    rows.append(f"  Fingerabdruck: {share.short_fingerprint(p.fingerprint)}  "
                f"({share.format_fingerprint(p.fingerprint)})")
    rows.append(f"  Qualität: {QUALITY_LABELS[p.quality]}, höchstens {p.max_viewers} Zuschauer, endet nach "
                f"{p.timeout_min} min")
    rows.append(f"  {WARNING}")
    rows.append(f"  {SOUND_HINT}")
    return "\n".join(rows)



class NeedsRestart(PresentError):
    """Agent-PC läuft noch ohne lokales VNC (vor Version 0.18 gestartet) – einmal neu starten."""


def for_vm(machine, **options) -> Presentation:
    """Vorführung für einen laufenden Agent-PC (``vm.VM``) vorbereiten – ``start()`` macht sie sichtbar."""
    if not machine.is_running():
        raise PresentError(f"„{machine.name}“ läuft nicht – bitte zuerst starten.")
    if not machine.vnc_available():
        raise NeedsRestart(f"„{machine.name}“ wurde mit einer älteren Version gestartet und zeigt seinen Bildschirm "
                           "noch nicht für Schulungen. Einmal neu starten – danach geht „Vorführen“ immer.")
    return Presentation(machine.name, machine.vnc_connect, is_alive=machine.is_running, **options)
