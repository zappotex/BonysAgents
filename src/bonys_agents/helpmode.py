# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: Hilfe-Modus – der Kursleiter sieht (und steuert) den Agent-PC eines Teilnehmers, nur mit Zustimmung.

Ablauf:

1. Der Teilnehmer verbindet sich **von sich aus** mit dem Kurs-Server des Kursleiters (``Presentation`` –
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

Hier steht nur die Teilnehmer-Seite (``HelpClient``, in beiden Editionen). Den Hilfe-Schalter im Kurs-Server gibt es
nur in „Bony's Agents Kursleiter“ (``bonys_agents.trainer.helpdesk``).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import socket
import ssl
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from bonys_agents import __version__, rfb, share, storage, vncbridge, websocket
from bonys_agents.i18n import tr

API = "/bonys/v1/help"
VM_HEADER = "X-Bonys-VM"


class HelpError(RuntimeError):
    pass


def _clean(text: str, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).strip()[:n]


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
        raise HelpError(tr("Keine Verbindung zu {netloc}: {e}. Läuft der Kurs noch? Gleiches Netz bzw. VPN?",
                           netloc=target.netloc, e=e)) \
            from e
    try:
        tls = share.client_context().wrap_socket(raw)
    except (OSError, ssl.SSLError) as e:
        raw.close()
        raise HelpError(tr("Verschlüsselte Verbindung zu {netloc} nicht möglich: {e}", netloc=target.netloc,
                           e=e)) from e
    fp = hashlib.sha256(tls.getpeercert(binary_form=True) or b"").hexdigest()
    if target.fingerprint and not hmac.compare_digest(fp, target.fingerprint):
        tls.close()
        raise share.FingerprintMismatch(tr("Der Fingerabdruck passt nicht zum Kurs – Verbindung abgebrochen. Falsche "
                                           "Adresse, oder jemand im Netz gibt sich als Kursleiter aus."))
    key = websocket.new_key()
    head = {"Host": target.netloc, "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13", share.CODE_HEADER: target.code,
            "User-Agent": f"BonysAgents/{__version__}", **share.protocol_headers(), **headers}
    tls.sendall(f"GET {path} HTTP/1.1\r\n".encode() + "".join(f"{k}: {v}\r\n" for k, v in head.items()).encode()
                + b"\r\n")
    data = b""
    while b"\r\n\r\n" not in data:      # byteweise – danach gehört alles der WebSocket-Schleife
        ch = tls.recv(1)
        if not ch or len(data) > 16384:
            tls.close()
            raise HelpError(tr("Der Kurs-Server hat die Verbindung geschlossen."))
        data += ch
    lines = data.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 0
    if status != 101:
        tls.close()
        if status == 426:
            got = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
            share.check_protocol(got.get(share.PROTOCOL_HEADER.lower(), "0"),
                                 got.get(share.VERSION_HEADER.lower(), "")[:20])
            raise HelpError(tr("Kurs-Protokoll passt nicht – bitte beide Bony's Agents aktualisieren."))
        if status == 403:
            raise share.WrongCode(tr("Falscher Code (oder diese Verbindung ist nicht mehr gültig)."))
        if status == 429:
            raise HelpError(tr("Zu viele falsche Codes – bitte eine Minute warten."))
        raise HelpError(tr("Der Kurs-Server lehnt ab (Antwort {status}).", status=status))
    accept = next((ln.split(":", 1)[1].strip() for ln in lines[1:] if ln.lower().startswith("sec-websocket-accept:")),
                  "")
    if accept != websocket.accept_key(key):
        tls.close()
        raise HelpError(tr("Unerwartete Antwort des Kurs-Servers."))
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
            vncbridge.pump_viewer(tls, vnc, filt,
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
