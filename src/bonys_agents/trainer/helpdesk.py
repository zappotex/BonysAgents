# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: Hilfe-Schalter im Kurs-Server (nur in „Bony's Agents Kursleiter“).

Teilnehmer verbinden sich von sich aus (``bonys_agents.helpmode.HelpClient``), der Kursleiter sieht ihre Anfragen
und – nur nach Zustimmung beim Teilnehmer – deren Agent-PC im Browser auf seinem eigenen Rechner
(``https://127.0.0.1:PORT/help/…``, nur von diesem Rechner aus erreichbar, mit einem Schlüssel je Ansicht). Ob
Eingaben durchgehen, entscheidet der Teilnehmer (sein ``rfb.ClientFilter``), nicht dieser Server.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from bonys_agents import __version__, share, websocket
from bonys_agents.trainer import share_server
from bonys_agents.helpmode import API, VM_HEADER, HelpError, _clean
from bonys_agents.i18n import n_, tr

COOKIE = "bonys_help"
TUNNEL_WAIT = 15.0
FORGET_AFTER = 30 * 60          # getrennte Teilnehmer verschwinden nach 30 min aus der Liste
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

# Zustände beim Kursleiter
CONNECTED, WAITING, ASKED, DENIED, VIEWING, CONTROL, ENDED, OFFLINE = (
    "verbunden", "wartet auf Hilfe", "Anfrage läuft", "abgelehnt", "sieht zu", "steuert", "beendet", "getrennt")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
            raise HelpError(tr("Der Teilnehmer ist nicht mehr verbunden."))
        token = secrets.token_urlsafe(24)
        with self.lock:
            s.view_token_hash = _hash(token)
            ask = not s.view_allowed
            if ask:
                self._set(s, ASKED)
        if ask:
            s.send({"type": "view_request"})
            self._event(f"Ansehen bei {s.name} angefragt – wartet auf Zustimmung.")
        # Sitzung im Pfad: jede Ansicht ist eine eigene Seite (ein offener Tab lädt bei nur anderem „#…“ nicht neu)
        return f"https://127.0.0.1:{self.server.port}/help/{sid}#t={quote(token)}"

    def request_control(self, sid: str) -> None:
        s = self.get(sid)
        if s is None or not s.view_allowed:
            raise HelpError(tr("Erst ansehen – Steuerung geht nur, während du zusiehst."))
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
        if path in ("/help", "/help/") or re.fullmatch(r"/help/[0-9a-f]{8}", path):
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
            h._json(404, {"error": n_("Nicht gefunden.")})
        return True

    def _local(self, h) -> bool:
        if h.client_address[0] in LOOPBACK:
            return True
        h._json(403, {"error": n_("Nur auf dem Rechner des Kursleiters.")})
        return False

    def _code_ok(self, h) -> bool:
        if self.server.stopped.is_set():
            h._json(410, {"error": n_("Der Kurs ist beendet.")})
            return False
        why = self.server.check_code(h.client_address[0], h.headers.get(share.CODE_HEADER, ""))
        if why == "gesperrt":
            h._json(429, {"error": n_("Zu viele falsche Codes – bitte eine Minute warten.")},
                    {"Retry-After": str(share.LOCK_SECONDS)})
            return False
        if why:
            h._json(403, {"error": n_("Falscher Code.")})
            return False
        return True

    def _participant(self, h) -> None:
        """Steuer-Kanal eines Teilnehmers (Bony's Agents des Teilnehmers, nicht der Browser)."""
        if not h.is_websocket():
            h._json(400, {"error": n_("WebSocket erwartet.")})
            return
        if not self._code_ok(h):
            return
        refusal = self.server.protocol_refusal(h.headers)
        if refusal:
            h._json(426, refusal, {share.PROTOCOL_HEADER: str(refusal["protocol"]),
                                   share.VERSION_HEADER: refusal["version"]})
            return
        name = re.sub(r"[^\w .'()-]", "", h.headers.get(share.CLIENT_HEADER, ""))[:40] or h.client_address[0]
        vm = re.sub(r"[^\w.-]", "", h.headers.get(VM_HEADER, ""))[:40] or "?"
        s = HelpSession(id=secrets.token_hex(4), name=name, vm=vm, address=h.client_address[0])
        with self.lock:
            self.sessions[s.id] = s
        self._event(f"{name} ({vm}, {s.address}) ist für Hilfe verbunden.")
        h.accept_websocket()
        s.send({"type": "hello", "session": s.id, "title": self.server.title, "version": __version__,
                "protocol": share_server.PROTOCOL})
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
            h._json(400, {"error": n_("WebSocket erwartet.")})
            return
        if not self._code_ok(h):
            return
        q = parse_qs(urlsplit(h.path).query)
        sid, tid = (q.get("s") or [""])[0], (q.get("t") or [""])[0]
        s = self.get(sid)
        t = s.tunnels.get(tid) if s else None
        if s is None or t is None or not s.view_allowed or t.ready.is_set() \
                or s.address != h.client_address[0]:
            h._json(403, {"error": n_("Kein Tunnel angefordert.")})
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
            h._json(403, {"error": n_("Anfrage von einer fremden Seite.")})
            return
        try:
            data = json.loads(h._read_body() or b"{}")
            sid = str(data.get("s", ""))
        except (ValueError, AttributeError):
            h._json(400, {"error": n_("Anfrage nicht verstanden.")})
            return
        if name == "auth":
            s = self.get(sid)
            token = str(data.get("t", ""))
            if s is None or not s.view_token_hash or not hmac.compare_digest(_hash(token), s.view_token_hash):
                h._json(403, {"error": n_("Diese Ansicht ist abgelaufen – in Bony's Agents erneut „Ansehen“.")})
                return
            h._json(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}={token}; Path=/; Secure; HttpOnly; SameSite=Strict"})
            return
        s = self._token_session(h, sid)
        if s is None:
            h._json(403, {"error": n_("Keine gültige Ansicht.")})
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
            h._json(403, {"state": "unbekannt", "error": n_("Keine gültige Ansicht.")})
            return
        h._json(200, self.status(s))

    def _teacher_view(self, h) -> None:
        """noVNC im Browser des Kursleiters ↔ Tunnel des Teilnehmers."""
        if not self._local(h):
            return
        if not h.is_websocket() or not h._same_origin():
            h._json(403, {"error": n_("Anfrage von einer fremden Seite.")})
            return
        sid = (parse_qs(urlsplit(h.path).query).get("s") or [""])[0]
        s = self._token_session(h, sid)
        if s is None:
            h._json(403, {"error": n_("Keine gültige Ansicht.")})
            return
        if not s.view_allowed or not s.connected:
            h._json(409, {"error": n_("Noch keine Zustimmung des Teilnehmers."), "state": s.state})
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
            h._json(504, {"error": n_("Der Teilnehmer-Rechner antwortet nicht.")})
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
