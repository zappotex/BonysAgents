# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: Hilfe-Modus – der Kursleiter sieht (und steuert) den Agent-PC eines Teilnehmers, nur mit Zustimmung.

Ablauf:

1. Der Teilnehmer verbindet sich **von sich aus** mit dem Kurs-Server des Kursleiters (``present.Presentation`` –
   derselbe HTTPS-Server wie beim Vorführen: Code, Zertifikat mit Fingerabdruck, Sperre nach Fehlversuchen) und
   hält einen Steuer-Kanal offen (WebSocket ``/bonys/v1/help/ws``). „Hilfe anfordern“ schickt eine Anfrage.
   Ausgehende Verbindungen klappen auch hinter Firewall/NAT und über VPN – der Teilnehmer öffnet keine Ports.
2. Der Kursleiter klickt „Ansehen“ → Rückfrage beim Teilnehmer („Erlauben/Ablehnen“). Erst nach „Erlauben“ öffnet
   der Teilnehmer für jede Ansicht einen Tunnel (``/bonys/v1/help/tunnel``) zu seinem **lokalen VNC-Socket** –
   nur der Agent-PC ist sichtbar, nie der Desktop des Teilnehmer-Rechners.
3. „Steuerung übernehmen“ braucht eine **zweite**, getrennte Zustimmung. Ob Eingaben durchgehen, entscheidet der
   Teilnehmer selbst: Sein ``rfb.ClientFilter`` lässt Tastatur/Maus nur bei erteilter Steuerung durch, die
   Zwischenablage nie. „Nur ansehen“ und „Beenden“ wirken sofort.
4. Beim Teilnehmer wird festgehalten, wann wer zugesehen bzw. gesteuert hat (ohne Bildinhalte).

Der Kursleiter sieht den Agent-PC im Browser auf seinem eigenen Rechner (``https://127.0.0.1:PORT/help/``, nur von
diesem Rechner aus erreichbar, mit einem Schlüssel je Ansicht).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from bonys_agents import __version__, rfb, share, storage, websocket

API = "/bonys/v1/help"
COOKIE = "bonys_help"
VM_HEADER = "X-Bonys-VM"
TUNNEL_WAIT = 15.0
FORGET_AFTER = 30 * 60          # getrennte Teilnehmer verschwinden nach 30 min aus der Liste
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

# Zustände beim Kursleiter
CONNECTED, WAITING, ASKED, DENIED, VIEWING, CONTROL, ENDED, OFFLINE = (
    "verbunden", "wartet auf Hilfe", "Anfrage läuft", "abgelehnt", "sieht zu", "steuert", "beendet", "getrennt")


class HelpError(RuntimeError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _clean(text: str, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).strip()[:n]


# ================================================================ Kursleiter: Hilfe-Schalter im Kurs-Server
@dataclass
class _Tunnel:
    id: str
    to_viewer: websocket.Mailbox = field(default_factory=websocket.Mailbox)
    to_tunnel: websocket.Mailbox = field(default_factory=websocket.Mailbox)
    ready: threading.Event = field(default_factory=threading.Event)
    closed: tuple[int, str] | None = None

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed is None:
            self.closed = (code, reason)
        self.to_viewer.close_with(*self.closed)
        self.to_tunnel.close_with(*self.closed)


@dataclass
class HelpSession:
    id: str
    name: str
    vm: str
    address: str
    state: str = CONNECTED
    message: str = ""
    requested_at: float = 0.0       # time.time() der letzten Anfrage (0 = keine)
    view_allowed: bool = False
    control: bool = False
    control_requested: bool = False
    connected: bool = True
    last_change: float = field(default_factory=time.monotonic)
    view_token_hash: str = ""
    mailbox: websocket.Mailbox = field(default_factory=websocket.Mailbox)
    tunnels: dict[str, _Tunnel] = field(default_factory=dict)

    def send(self, data: dict) -> None:
        if self.connected:
            self.mailbox.send_text(json.dumps(data))


class HelpDesk:
    """Hilfe-Anfragen im Kurs-Server (``server`` = ``present.Presentation``)."""

    def __init__(self, server):
        self.server = server
        self.sessions: dict[str, HelpSession] = {}
        self.requests_total = 0          # zählt jede neue Anfrage – die Oberfläche benachrichtigt bei Änderung

    @property
    def lock(self) -> threading.Lock:
        return self.server.lock

    def _event(self, text: str) -> None:
        self.server._event(text)

    def session_list(self) -> list[HelpSession]:
        now = time.monotonic()
        with self.lock:
            for sid in [k for k, v in self.sessions.items()
                        if not v.connected and now - v.last_change > FORGET_AFTER]:
                del self.sessions[sid]
            return sorted(self.sessions.values(), key=lambda v: (-(v.requested_at or 0), v.name))

    def get(self, sid: str) -> HelpSession | None:
        with self.lock:
            return self.sessions.get(sid)

    def _set(self, s: HelpSession, state: str) -> None:
        s.state = state
        s.last_change = time.monotonic()

    # ---------- Aktionen des Kursleiters ----------
    def view_url(self, sid: str) -> str:
        """„Ansehen“: fragt beim Teilnehmer nach (falls noch nicht erlaubt) und gibt die Adresse der Ansicht im
        Browser des Kursleiters zurück (Schlüssel hinter „#“, gilt nur für diese Ansicht)."""
        s = self.get(sid)
        if s is None or not s.connected:
            raise HelpError("Der Teilnehmer ist nicht mehr verbunden.")
        token = secrets.token_urlsafe(24)
        with self.lock:
            s.view_token_hash = _hash(token)
            ask = not s.view_allowed
            if ask:
                self._set(s, ASKED)
        if ask:
            s.send({"type": "view_request"})
            self._event(f"Ansehen bei {s.name} angefragt – wartet auf Zustimmung.")
        return f"https://127.0.0.1:{self.server.port}/help/#s={sid}&t={quote(token)}"

    def request_control(self, sid: str) -> None:
        s = self.get(sid)
        if s is None or not s.view_allowed:
            raise HelpError("Erst ansehen – Steuerung geht nur, während du zusiehst.")
        if s.control:
            return
        s.control_requested = True
        s.send({"type": "control_request"})
        self._event(f"Steuerung bei {s.name} angefragt – wartet auf Zustimmung.")

    def release_control(self, sid: str) -> None:
        s = self.get(sid)
        if s is None:
            return
        with self.lock:
            s.control = False
            s.control_requested = False
            if s.view_allowed:
                self._set(s, VIEWING)
        s.send({"type": "release_control"})
        self._event(f"Steuerung bei {s.name} abgegeben – nur ansehen.")

    def end_view(self, sid: str, by_teacher: bool = True) -> None:
        s = self.get(sid)
        if s is None:
            return
        with self.lock:
            was = s.view_allowed or s.state == ASKED
            s.view_allowed = s.control = s.control_requested = False   # Schlüssel bleibt nur für „beendet“
            s.requested_at = 0.0
            tunnels = list(s.tunnels.values())
            s.tunnels.clear()
            self._set(s, ENDED if s.connected else OFFLINE)
        for t in tunnels:
            t.close(4000, "beendet")
        if by_teacher:
            s.send({"type": "ended"})
        if was:
            self._event(f"Hilfe für {s.name} beendet" + (" (Kursleiter)." if by_teacher else " (Teilnehmer)."))

    def forget(self, sid: str) -> None:
        s = self.get(sid)
        if s is None:
            return
        self.end_view(sid)
        s.mailbox.close_with(4000, "Kursleiter hat die Verbindung entfernt")
        with self.lock:
            self.sessions.pop(sid, None)

    def close_all(self) -> None:
        for s in self.session_list():
            for t in list(s.tunnels.values()):
                t.close(4000, "beendet")
            s.mailbox.close_with(4000, "Kurs beendet")

    # ---------- Nachrichten vom Teilnehmer ----------
    def _on_message(self, s: HelpSession, op: int, payload: bytes) -> None:
        if op != websocket.OP_TEXT:
            return
        try:
            msg = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "request":
            with self.lock:
                s.message = _clean(msg.get("message", ""), 300)
                s.requested_at = time.time()
                if not s.view_allowed and s.state != ASKED:
                    self._set(s, WAITING)
                self.requests_total += 1
            self._event(f"Hilfe-Anfrage von {s.name} ({s.vm})" + (f": {s.message}" if s.message else "."))
        elif kind == "cancel":
            with self.lock:
                s.requested_at = 0.0
                if s.state in (WAITING, DENIED, ENDED):
                    self._set(s, CONNECTED)
            self._event(f"{s.name} hat die Hilfe-Anfrage zurückgezogen.")
        elif kind == "consent":
            granted = msg.get("granted") is True
            if msg.get("what") == "view":
                with self.lock:   # Schlüssel bleibt – die Seite des Kursleiters soll „abgelehnt“ anzeigen können
                    s.view_allowed = granted
                    self._set(s, VIEWING if granted else DENIED)
                self._event(f"{s.name} hat das Ansehen {'erlaubt' if granted else 'abgelehnt'}.")
            elif msg.get("what") == "control":
                with self.lock:
                    s.control_requested = False
                    s.control = granted and s.view_allowed
                    if s.control:
                        self._set(s, CONTROL)
                self._event(f"{s.name} hat die Steuerung {'erlaubt' if granted else 'abgelehnt'}.")
        elif kind == "state":
            view = msg.get("view") is True
            control = msg.get("control") is True
            if not view:
                self.end_view(s.id, by_teacher=False)
                return
            with self.lock:
                downgraded = s.control and not control
                s.control = control and s.view_allowed
                s.control_requested = s.control_requested and not s.control
                if s.view_allowed:
                    self._set(s, CONTROL if s.control else VIEWING)
            if downgraded:
                self._event(f"{s.name} hat auf „nur ansehen“ zurückgestellt.")
        elif kind == "end":
            self.end_view(s.id, by_teacher=False)

    # ---------- HTTP ----------
    def handle(self, h, method: str, path: str) -> bool:
        """Anfragen unter /help/ und /bonys/v1/help/ beantworten. False = nicht zuständig."""
        if path in ("/help", "/help/"):
            if method != "GET":
                return False
            if not self._local(h):
                return True
            h._file(_page_dir() / "help.html")
            return True
        if not path.startswith(API + "/"):
            return False
        name = path[len(API) + 1:]
        if method == "GET" and name == "ws":
            self._participant(h)
        elif method == "GET" and name == "tunnel":
            self._tunnel(h)
        elif method == "POST" and name in ("auth", "control", "release", "stop"):
            self._teacher_post(h, name)
        elif method == "GET" and name == "status":
            self._teacher_status(h)
        elif method == "GET" and name == "view":
            self._teacher_view(h)
        else:
            h._json(404, {"error": "Nicht gefunden."})
        return True

    def _local(self, h) -> bool:
        if h.client_address[0] in LOOPBACK:
            return True
        h._json(403, {"error": "Nur auf dem Rechner des Kursleiters."})
        return False

    def _code_ok(self, h) -> bool:
        if self.server.stopped.is_set():
            h._json(410, {"error": "Der Kurs ist beendet."})
            return False
        why = self.server.check_code(h.client_address[0], h.headers.get(share.CODE_HEADER, ""))
        if why == "gesperrt":
            h._json(429, {"error": "Zu viele falsche Codes – bitte eine Minute warten."},
                    {"Retry-After": str(share.LOCK_SECONDS)})
            return False
        if why:
            h._json(403, {"error": "Falscher Code."})
            return False
        return True

    def _participant(self, h) -> None:
        """Steuer-Kanal eines Teilnehmers (Bony's Agents des Teilnehmers, nicht der Browser)."""
        if not h.is_websocket():
            h._json(400, {"error": "WebSocket erwartet."})
            return
        if not self._code_ok(h):
            return
        name = re.sub(r"[^\w .'()-]", "", h.headers.get(share.CLIENT_HEADER, ""))[:40] or h.client_address[0]
        vm = re.sub(r"[^\w.-]", "", h.headers.get(VM_HEADER, ""))[:40] or "?"
        s = HelpSession(id=secrets.token_hex(4), name=name, vm=vm, address=h.client_address[0])
        with self.lock:
            self.sessions[s.id] = s
        self._event(f"{name} ({vm}, {s.address}) ist für Hilfe verbunden.")
        h.accept_websocket()
        s.send({"type": "hello", "session": s.id, "title": self.server.title, "version": __version__})
        try:
            websocket.serve(h.connection, s.mailbox, lambda op, data: self._on_message(s, op, data),
                            lambda: (4000, "Kurs beendet") if self.server.stopped.is_set() else None)
        finally:
            with self.lock:
                s.connected = False
                tunnels = list(s.tunnels.values())
                s.tunnels.clear()
                s.view_allowed = s.control = False
                self._set(s, OFFLINE)
            for t in tunnels:
                t.close(4000, "Teilnehmer getrennt")
            s.mailbox.dispose()
            self._event(f"{s.name} ist nicht mehr verbunden.")

    def _tunnel(self, h) -> None:
        """Tunnel vom Teilnehmer: Bild seines Agent-PCs für genau eine Ansicht des Kursleiters."""
        if not h.is_websocket():
            h._json(400, {"error": "WebSocket erwartet."})
            return
        if not self._code_ok(h):
            return
        q = parse_qs(urlsplit(h.path).query)
        sid, tid = (q.get("s") or [""])[0], (q.get("t") or [""])[0]
        s = self.get(sid)
        t = s.tunnels.get(tid) if s else None
        if s is None or t is None or not s.view_allowed or t.ready.is_set() \
                or s.address != h.client_address[0]:
            h._json(403, {"error": "Kein Tunnel angefordert."})
            return
        h.accept_websocket()
        t.ready.set()
        try:
            websocket.serve(h.connection, t.to_tunnel,
                            lambda op, data: op == websocket.OP_BINARY and t.to_viewer.put((op, data)),
                            lambda: t.closed or ((4000, "beendet") if not s.view_allowed else None),
                            client_side=False)
        finally:
            t.close(1000, "Tunnel beendet")
            with self.lock:
                s.tunnels.pop(tid, None)

    def _token_session(self, h, sid: str) -> HelpSession | None:
        s = self.get(sid)
        token = h._token_named(COOKIE)
        if s is None or not token or not s.view_token_hash \
                or not hmac.compare_digest(_hash(token), s.view_token_hash):
            return None
        return s

    def viewer_cookie_ok(self, h) -> bool:
        """Darf diese Anfrage noVNC laden? Nur der Browser des Kursleiters mit dem Schlüssel einer Ansicht."""
        token = h._token_named(COOKIE)
        if not token or h.client_address[0] not in LOOPBACK:
            return False
        th = _hash(token)
        with self.lock:
            return any(s.view_token_hash and hmac.compare_digest(th, s.view_token_hash) for s in self.sessions.values())

    def _teacher_post(self, h, name: str) -> None:
        if not self._local(h):
            return
        if not h._same_origin():
            h._json(403, {"error": "Anfrage von einer fremden Seite."})
            return
        try:
            data = json.loads(h._read_body() or b"{}")
            sid = str(data.get("s", ""))
        except (ValueError, AttributeError):
            h._json(400, {"error": "Anfrage nicht verstanden."})
            return
        if name == "auth":
            s = self.get(sid)
            token = str(data.get("t", ""))
            if s is None or not s.view_token_hash or not hmac.compare_digest(_hash(token), s.view_token_hash):
                h._json(403, {"error": "Diese Ansicht ist abgelaufen – in Bony's Agents erneut „Ansehen“."})
                return
            h._json(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}={token}; Path=/; Secure; HttpOnly; SameSite=Strict"})
            return
        s = self._token_session(h, sid)
        if s is None:
            h._json(403, {"error": "Keine gültige Ansicht."})
            return
        try:
            if name == "control":
                self.request_control(sid)
            elif name == "release":
                self.release_control(sid)
            elif name == "stop":
                self.end_view(sid)
        except HelpError as e:
            h._json(409, {"error": str(e)})
            return
        h._json(200, self.status(s))

    def status(self, s: HelpSession) -> dict:
        return {"state": s.state, "name": s.name, "vm": s.vm, "view": s.view_allowed, "control": s.control,
                "control_requested": s.control_requested, "connected": s.connected, "message": s.message}

    def _teacher_status(self, h) -> None:
        if not self._local(h):
            return
        sid = (parse_qs(urlsplit(h.path).query).get("s") or [""])[0]
        s = self._token_session(h, sid)
        if s is None:
            h._json(403, {"state": "unbekannt", "error": "Keine gültige Ansicht."})
            return
        h._json(200, self.status(s))

    def _teacher_view(self, h) -> None:
        """noVNC im Browser des Kursleiters ↔ Tunnel des Teilnehmers."""
        if not self._local(h):
            return
        if not h.is_websocket() or not h._same_origin():
            h._json(403, {"error": "Anfrage von einer fremden Seite."})
            return
        sid = (parse_qs(urlsplit(h.path).query).get("s") or [""])[0]
        s = self._token_session(h, sid)
        if s is None:
            h._json(403, {"error": "Keine gültige Ansicht."})
            return
        if not s.view_allowed or not s.connected:
            h._json(409, {"error": "Noch keine Zustimmung des Teilnehmers.", "state": s.state})
            return
        t = _Tunnel(id=secrets.token_urlsafe(12))
        with self.lock:
            for old in s.tunnels.values():   # nur eine Ansicht je Teilnehmer (z. B. Seite neu geladen)
                old.close(4000, "neue Ansicht")
            s.tunnels[t.id] = t
        s.send({"type": "open_tunnel", "t": t.id})
        if not t.ready.wait(TUNNEL_WAIT) or t.closed:
            with self.lock:
                s.tunnels.pop(t.id, None)
            h._json(504, {"error": "Der Teilnehmer-Rechner antwortet nicht."})
            return
        h.accept_websocket()
        self._event(f"Kursleiter sieht den Agent-PC von {s.name}.")
        try:
            websocket.serve(h.connection, t.to_viewer,
                            lambda op, data: op == websocket.OP_BINARY and t.to_tunnel.put((op, data)),
                            lambda: t.closed)
        finally:
            t.close(1000, "Ansicht geschlossen")


def _page_dir() -> Path:
    return Path(__file__).resolve().parent / "resources" / "present"


# ================================================================ Teilnehmer
def log_file() -> Path:
    d = storage.data_dir() / "schulung"
    d.mkdir(parents=True, exist_ok=True)
    return d / "hilfe-protokoll.log"


def log_event(course: str, vm: str, text: str) -> None:
    """Protokoll beim Teilnehmer: wann wer zugesehen/gesteuert hat – nie Bildinhalte."""
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{course}\t{vm}\t{text}\n"
    with contextlib.suppress(OSError), log_file().open("a", encoding="utf-8") as f:
        f.write(line)


def _open_ws(target: share.Target, path: str, headers: dict, timeout: float = 15) -> tuple[ssl.SSLSocket, str]:
    """TLS-Verbindung zum Kurs-Server (Fingerabdruck prüfen), dann WebSocket-Upgrade. Gibt (Socket, FP) zurück."""
    try:
        raw = socket.create_connection((target.host, target.port), timeout=timeout)
    except OSError as e:
        raise HelpError(f"Keine Verbindung zu {target.netloc}: {e}. Läuft der Kurs noch? Gleiches Netz bzw. VPN?") \
            from e
    try:
        tls = share.client_context().wrap_socket(raw)
    except (OSError, ssl.SSLError) as e:
        raw.close()
        raise HelpError(f"Verschlüsselte Verbindung zu {target.netloc} nicht möglich: {e}") from e
    fp = hashlib.sha256(tls.getpeercert(binary_form=True) or b"").hexdigest()
    if target.fingerprint and not hmac.compare_digest(fp, target.fingerprint):
        tls.close()
        raise share.FingerprintMismatch("Der Fingerabdruck passt nicht zum Kurs – Verbindung abgebrochen. Falsche "
                                        "Adresse, oder jemand im Netz gibt sich als Kursleiter aus.")
    key = websocket.new_key()
    head = {"Host": target.netloc, "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13", share.CODE_HEADER: target.code,
            "User-Agent": f"BonysAgents/{__version__}", **headers}
    tls.sendall(f"GET {path} HTTP/1.1\r\n".encode() + "".join(f"{k}: {v}\r\n" for k, v in head.items()).encode()
                + b"\r\n")
    data = b""
    while b"\r\n\r\n" not in data:      # byteweise – danach gehört alles der WebSocket-Schleife
        ch = tls.recv(1)
        if not ch or len(data) > 16384:
            tls.close()
            raise HelpError("Der Kurs-Server hat die Verbindung geschlossen.")
        data += ch
    lines = data.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 0
    if status != 101:
        tls.close()
        if status == 403:
            raise share.WrongCode("Falscher Code (oder diese Verbindung ist nicht mehr gültig).")
        if status == 429:
            raise HelpError("Zu viele falsche Codes – bitte eine Minute warten.")
        raise HelpError(f"Der Kurs-Server lehnt ab (Antwort {status}).")
    accept = next((ln.split(":", 1)[1].strip() for ln in lines[1:] if ln.lower().startswith("sec-websocket-accept:")),
                  "")
    if accept != websocket.accept_key(key):
        tls.close()
        raise HelpError("Unerwartete Antwort des Kurs-Servers.")
    tls.settimeout(None)
    return tls, fp


class HelpClient:
    """Teilnehmer: Verbindung zum Hilfe-Schalter des Kursleiters für einen Agent-PC.

    ``machine`` braucht ``name`` und ``vnc_connect()`` (``vm.VM``). Rückrufe (aus einem Hintergrund-Thread):
    ``on_view_request()``, ``on_control_request()``, ``on_change()`` (Zustand geändert), ``on_closed(Grund)``.
    Die Zustimmungen (``view_allowed``, ``control_allowed``) liegen **nur hier** – der Kurs-Server kann sie nicht
    setzen. Eingaben vom Kursleiter gehen nur bei ``control_allowed`` an den Agent-PC.
    """

    def __init__(self, target: share.Target, machine, name: str = "", *,
                 on_view_request: Callable[[], None] = lambda: None,
                 on_control_request: Callable[[], None] = lambda: None,
                 on_change: Callable[[], None] = lambda: None,
                 on_closed: Callable[[str], None] = lambda reason: None):
        self.target = target
        self.machine = machine
        self.name = _clean(name or share._client_name(), 40)
        self.on_view_request = on_view_request
        self.on_control_request = on_control_request
        self.on_change = on_change
        self.on_closed = on_closed
        self.view_allowed = False
        self.control_allowed = False
        self.requested = False
        self.watching = 0               # offene Tunnel (Kursleiter sieht gerade zu)
        self.fingerprint = ""
        self.title = ""
        self.session_id = ""
        self.closed = threading.Event()
        self.close_reason = ""
        self._mailbox = websocket.Mailbox()
        self._tunnels: dict[str, socket.socket] = {}   # Tunnel-ID → lokaler VNC-Socket
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def course(self) -> str:
        return f"{self.title or 'Kurs'} ({self.target.netloc})"

    def _log(self, text: str) -> None:
        log_event(self.course, self.machine.name, text)

    # ---------- Verbindung ----------
    def connect(self) -> None:
        """Steuer-Kanal öffnen (prüft Fingerabdruck und Code) – kehrt zurück, sobald die Verbindung steht."""
        tls, fp = _open_ws(self.target, f"{API}/ws", {share.CLIENT_HEADER: self.name, VM_HEADER: self.machine.name})
        self.fingerprint = fp
        if not self.target.fingerprint:
            self.target.fingerprint = fp   # Tunnel müssen zum selben Zertifikat gehen
        self._thread = threading.Thread(target=self._run, args=(tls,), name="hilfe-kanal", daemon=True)
        self._thread.start()

    def _run(self, tls) -> None:
        why = websocket.serve(tls, self._mailbox, self._on_message,
                              lambda: (1000, "getrennt") if self.closed.is_set() else None, client_side=True)
        with contextlib.suppress(OSError):
            tls.close()
        reason = self.close_reason or (why[1] if why and why[1] else "Verbindung zum Kurs getrennt.")
        was_viewed = self.view_allowed
        self._revoke()
        if was_viewed:
            self._log("Verbindung getrennt – Ansehen beendet")
        self.closed.set()
        self.close_reason = reason
        self._mailbox.dispose()
        self.on_closed(reason)

    def close(self, reason: str = "Verbindung beendet.") -> None:
        self.close_reason = reason
        self._revoke()
        self._mailbox.close_with(1000, "Teilnehmer trennt")
        self.closed.set()

    def _send(self, data: dict) -> None:
        if not self.closed.is_set():
            self._mailbox.send_text(json.dumps(data))

    # ---------- Aktionen des Teilnehmers ----------
    def request(self, message: str = "") -> None:
        self.requested = True
        self._send({"type": "request", "message": _clean(message, 300)})
        self._log("Hilfe angefordert" + (f": {_clean(message, 120)}" if message else ""))
        self.on_change()

    def cancel(self) -> None:
        self.requested = False
        self._send({"type": "cancel"})
        self._log("Hilfe-Anfrage zurückgezogen")
        self.on_change()

    def allow_view(self, granted: bool) -> None:
        self.view_allowed = granted
        if not granted:
            self.control_allowed = False
        self._send({"type": "consent", "what": "view", "granted": granted})
        self._log("Ansehen erlaubt" if granted else "Ansehen abgelehnt")
        self.on_change()

    def allow_control(self, granted: bool) -> None:
        self.control_allowed = granted and self.view_allowed
        self._send({"type": "consent", "what": "control", "granted": self.control_allowed})
        self._log("Steuerung erlaubt" if self.control_allowed else "Steuerung abgelehnt")
        self.on_change()

    def view_only(self) -> None:
        """Zurück auf „nur ansehen“ – sofort, Eingaben gehen ab jetzt nicht mehr durch."""
        if not self.control_allowed:
            return
        self.control_allowed = False
        self._send({"type": "state", "view": self.view_allowed, "control": False})
        self._log("Auf „nur ansehen“ zurückgestellt")
        self.on_change()

    def end(self) -> None:
        """Ansehen/Steuern sofort beenden (trennt alle Tunnel)."""
        if not self.view_allowed and not self._tunnels:
            return
        self._revoke()
        self.requested = False
        self._send({"type": "end"})
        self._log("Beendet (Teilnehmer)")
        self.on_change()

    def _revoke(self) -> None:
        self.view_allowed = False
        self.control_allowed = False
        with self._lock:
            socks = list(self._tunnels.values())
        for sock in socks:  # Agent-PC-Seite schließen – die Tunnel-Schleife endet dadurch sofort
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    # ---------- Nachrichten vom Kursleiter ----------
    def _on_message(self, op: int, payload: bytes) -> None:
        if op != websocket.OP_TEXT:
            return
        try:
            msg = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        kind = msg.get("type") if isinstance(msg, dict) else None
        if kind == "hello":
            self.title = _clean(msg.get("title", ""), 60)
            self.session_id = re.sub(r"[^0-9a-f]", "", str(msg.get("session", "")))[:16]
        elif kind == "view_request":
            if self.view_allowed:
                self._send({"type": "consent", "what": "view", "granted": True})
            else:
                self.on_view_request()
        elif kind == "control_request":
            if self.view_allowed and not self.control_allowed:
                self.on_control_request()
        elif kind == "release_control":
            if self.control_allowed:
                self.control_allowed = False
                self._log("Kursleiter hat die Steuerung abgegeben")
                self.on_change()
        elif kind == "ended":
            if self.view_allowed or self._tunnels:
                self._revoke()
                self.requested = False
                self._log("Beendet (Kursleiter)")
                self.on_change()
        elif kind == "open_tunnel":
            tid = str(msg.get("t", ""))
            if self.view_allowed and re.fullmatch(r"[A-Za-z0-9_-]{8,40}", tid):
                threading.Thread(target=self._tunnel, args=(tid,), name="hilfe-tunnel", daemon=True).start()

    def _tunnel(self, tid: str) -> None:
        try:
            vnc = self.machine.vnc_connect()
        except (OSError, RuntimeError) as e:
            self._log(f"Bildschirm nicht erreichbar: {e}")
            return
        with self._lock:
            self._tunnels[tid] = vnc
        try:
            if not self.view_allowed:
                return
            sid = self.session_id
            tls, _fp = _open_ws(self.target, f"{API}/tunnel?s={sid}&t={tid}", {})
        except (HelpError, OSError):
            with self._lock:
                self._tunnels.pop(tid, None)
            with contextlib.suppress(OSError):
                vnc.close()
            return
        self.watching += 1
        if self.watching == 1:
            self._log("Kursleiter sieht zu")
        self.on_change()
        filt = rfb.ClientFilter(allow_input=lambda: self.view_allowed and self.control_allowed)
        try:
            from bonys_agents import present

            present.pump_viewer(tls, vnc, filt,
                                lambda: None if self.view_allowed and not self.closed.is_set()
                                else (4000, "beendet"), None, client_side=True)
        finally:
            with self._lock:
                self._tunnels.pop(tid, None)
            for sock in (tls, vnc):
                with contextlib.suppress(OSError):
                    sock.close()
            self.watching = max(0, self.watching - 1)
            if self.watching == 0:
                self._log("Kursleiter sieht nicht mehr zu")
            self.on_change()

    @property
    def state(self) -> str:
        if self.closed.is_set():
            return "getrennt"
        if self.control_allowed and self.watching:
            return "steuert"
        if self.view_allowed and self.watching:
            return "sieht zu"
        if self.view_allowed:
            return "erlaubt"
        return "wartet" if self.requested else "verbunden"
