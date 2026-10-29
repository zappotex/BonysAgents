# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: VNC-Betrachter für die Hilfe-Funktion über das Bony-Netz (Aufgabe 06, nur Kursleiter-Version).

Zwei Wege (Entscheidung vom 18.10.2026: „Beides“):

- **Eingebettet (Standard):** noVNC in einem eigenen Fenster (Qt WebEngine, ``trainer/gui/hilfe_fenster.py``).
  noVNC spricht WebSocket, x11vnc im Agent-PC nur RFB über TCP – dazwischen sitzt ``Bruecke``: ein Port nur auf
  127.0.0.1, ein geheimer Pfad je Sitzung, genau eine Verbindung, danach ist der Port zu. Das Passwort bekommt noVNC
  über QWebChannel im Speicher.
- **Rückfall TigerVNC** (wo Qt WebEngine fehlt, z. B. Linux auf ARM): ``vncviewer -PasswordFile`` mit einer Datei
  (Rechte 600, Format von ``vncpasswd``), die gelöscht wird, sobald der Betrachter verbunden ist bzw. sich beendet.

Ob Eingaben durchgehen, entscheidet x11vnc im Agent-PC (``-viewonly``) – nicht diese Seite.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from bonys_agents import vncauth, websocket
from bonys_agents.hilfe import ANSEHEN, Freigabe
from bonys_agents.i18n import tr

VERBINDEN_SEKUNDEN = 10
KOPF_MAX = 16 * 1024
HERKUNFT = "kursraum://app"   # Origin der Seite im eingebetteten Betrachter


class BetrachterFehler(Exception):
    """Für den Nutzer geschrieben."""


# ---------------------------------------------------------------- Brücke WebSocket (noVNC) ↔ TCP (x11vnc)
class Bruecke:
    """Lokaler WebSocket-Endpunkt für noVNC, der genau eine Verbindung zu ``ziel`` (Adresse, Port) weiterleitet."""

    def __init__(self, ziel: tuple[str, int], herkunft: str = HERKUNFT,
                 verbinden: Callable[[tuple[str, int], float], socket.socket] = socket.create_connection):
        self.ziel = ziel
        self.herkunft = herkunft
        self._verbinden = verbinden
        self.pfad = "/hilfe/" + secrets.token_urlsafe(24)
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._stop = threading.Event()
        self.ende: tuple[int, str] | None = None     # warum die Verbindung endete
        self._faden = threading.Thread(target=self._laufen, name="hilfe-bruecke", daemon=True)
        self._faden.start()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}{self.pfad}"

    def schliessen(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._server.close()

    def _laufen(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    r, _, _ = select.select([self._server], [], [], 0.25)
                except (OSError, ValueError):
                    return
                if not r:
                    continue
                try:
                    conn, _addr = self._server.accept()
                except OSError:
                    return
                if self._annehmen(conn):
                    return
        finally:
            with contextlib.suppress(OSError):
                self._server.close()

    def _annehmen(self, conn: socket.socket) -> bool:
        """Handschlag prüfen; bei Erfolg weiterleiten (blockiert bis zum Ende). False = abgewiesen."""
        conn.settimeout(5)
        try:
            kopf = b""
            while b"\r\n\r\n" not in kopf:
                teil = conn.recv(4096)
                if not teil or len(kopf) > KOPF_MAX:
                    conn.close()
                    return False
                kopf += teil
            kopf, rest = kopf.split(b"\r\n\r\n", 1)
            zeilen = kopf.decode("latin-1").split("\r\n")
            teile = zeilen[0].split(" ")
            felder = {}
            for z in zeilen[1:]:
                name, _, wert = z.partition(":")
                felder[name.strip().lower()] = wert.strip()
            ok = (len(teile) == 3 and teile[0] == "GET" and secrets.compare_digest(teile[1], self.pfad)
                  and felder.get("upgrade", "").lower() == "websocket" and felder.get("sec-websocket-key")
                  and (not self.herkunft or felder.get("origin") == self.herkunft))
            if not ok:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                conn.close()
                return False
            try:
                ziel = self._verbinden(self.ziel, VERBINDEN_SEKUNDEN)
            except OSError:
                self.ende = (4010, "Agent-PC nicht erreichbar")
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                conn.close()
                return True
            antwort = ["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket", "Connection: Upgrade",
                       "Sec-WebSocket-Accept: " + websocket.accept_key(felder["sec-websocket-key"])]
            protokolle = [p.strip() for p in felder.get("sec-websocket-protocol", "").split(",") if p.strip()]
            if "binary" in protokolle:
                antwort.append("Sec-WebSocket-Protocol: binary")
            conn.sendall(("\r\n".join(antwort) + "\r\n\r\n").encode())
        except OSError:
            with contextlib.suppress(OSError):
                conn.close()
            return False
        with contextlib.suppress(OSError):
            self._server.close()   # genau eine Verbindung – danach ist der Port zu
        self.ende = self._pumpen(conn, ziel, rest)
        return True

    def _pumpen(self, ws: socket.socket, ziel: socket.socket, rest: bytes) -> tuple[int, str]:
        parser = websocket.FrameParser(expect_masked=True)
        ws.settimeout(30)
        ziel.settimeout(30)

        def senden(op: int, daten: bytes) -> None:
            ws.sendall(websocket.encode_frame(op, daten))

        try:
            puffer = rest
            while not self._stop.is_set():
                if puffer:
                    daten, puffer = puffer, b""
                else:
                    r, _, _ = select.select([ws, ziel], [], [], 0.25)
                    if ziel in r:
                        d = ziel.recv(65536)
                        if not d:
                            senden(websocket.OP_CLOSE, websocket.close_payload(4010, "Bildschirm getrennt"))
                            return 4010, "Bildschirm getrennt"
                        senden(websocket.OP_BINARY, d)
                    if ws not in r:
                        continue
                    daten = ws.recv(65536)
                    if not daten:
                        return 1006, "Betrachter weg"
                for op, nutz in parser.feed(daten):
                    if op == websocket.OP_CLOSE:
                        with contextlib.suppress(OSError):
                            senden(websocket.OP_CLOSE, websocket.close_payload(1000))
                        return websocket.parse_close(nutz)
                    if op == websocket.OP_PING:
                        senden(websocket.OP_PONG, nutz)
                    elif op == websocket.OP_BINARY:
                        ziel.sendall(nutz)
            with contextlib.suppress(OSError):
                senden(websocket.OP_CLOSE, websocket.close_payload(1000, "beendet"))
            return 1000, "beendet"
        except websocket.WebSocketClosed as e:
            return e.code, e.reason
        except (OSError, ValueError):
            return 1006, "Verbindung abgebrochen"
        finally:
            for s in (ws, ziel):
                with contextlib.suppress(OSError):
                    s.close()


# ---------------------------------------------------------------- Rückfall: TigerVNC
TIGERVNC_PFADE = {
    "win32": [r"C:\Program Files\TigerVNC\vncviewer.exe", r"C:\Program Files (x86)\TigerVNC\vncviewer.exe"],
    "darwin": ["/Applications/TigerVNC Viewer.app/Contents/MacOS/TigerVNC Viewer"],
}
TIGERVNC_FEHLT = {
    "linux": "Installiere dafür TigerVNC aus den Paketquellen (Paket „tigervnc-viewer“).",
    "win32": "Installiere dafür TigerVNC (https://tigervnc.org, z. B. „winget install TigerVNC.TigerVNC“).",
    "darwin": "Installiere dafür den „TigerVNC Viewer“ (https://tigervnc.org).",
}


def tigervnc() -> str | None:
    for name in ("vncviewer", "xtigervncviewer"):
        exe = shutil.which(name)
        if exe:
            return exe
    return next((p for p in TIGERVNC_PFADE.get(sys.platform, []) if os.path.isfile(p)), None)


def tigervnc_fehlt_text() -> str:
    schluessel = "linux" if sys.platform.startswith("linux") else sys.platform
    return (tr("Für die Hilfe-Funktion fehlt der eingebettete Betrachter (Qt WebEngine) und TigerVNC ist nicht "
               "installiert. {wert}", wert=TIGERVNC_FEHLT.get(schluessel, TIGERVNC_FEHLT["linux"])))


def passwortdatei(passwort: str, ordner: str | None = None) -> Path:
    """Temporäre Datei mit Rechten 600 im Format von ``vncpasswd`` – nur für den eigenen Benutzer lesbar."""
    ordner = ordner or os.environ.get("XDG_RUNTIME_DIR") or None
    fd, pfad = tempfile.mkstemp(prefix="bonys-hilfe-", suffix=".passwd", dir=ordner)
    try:
        with os.fdopen(fd, "wb") as f:
            os.chmod(pfad, 0o600)
            f.write(vncauth.passwortdatei(passwort))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(pfad)
        raise
    return Path(pfad)


def tigervnc_befehl(exe: str, freigabe: Freigabe, datei: Path) -> list[str]:
    """Befehlszeile – ohne Passwort (das steht nur in der Datei)."""
    return [exe, f"-PasswordFile={datei}", f"-ViewOnly={1 if freigabe.modus == ANSEHEN else 0}", "-Shared=0",
            "-SendClipboard=0", "-AcceptClipboard=0", f"{freigabe.ip}::{freigabe.port}"]


class TigerVNC:
    """Läuft ``vncviewer``; ``aufraeumen()`` löscht die Passwortdatei (nach kurzer Zeit oder wenn er endet)."""

    def __init__(self, freigabe: Freigabe, exe: str | None = None, popen=subprocess.Popen):
        exe = exe or tigervnc()
        if not exe:
            raise BetrachterFehler(tigervnc_fehlt_text())
        self.datei: Path | None = passwortdatei(freigabe.passwort)
        try:
            self.proc = popen(tigervnc_befehl(exe, freigabe, self.datei), stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.aufraeumen()
            raise BetrachterFehler(tr("TigerVNC ließ sich nicht starten: {e}", e=e)) from None

    def laeuft(self) -> bool:
        return self.proc.poll() is None

    def aufraeumen(self) -> None:
        if self.datei is not None:
            with contextlib.suppress(OSError):
                self.datei.unlink()
            self.datei = None

    def beenden(self) -> None:
        if self.laeuft():
            with contextlib.suppress(OSError):
                self.proc.terminate()
        self.aufraeumen()
