# SPDX-License-Identifier: GPL-3.0-or-later
"""RFB (VNC) – Filter für alles, was ein Zuschauer bzw. Helfer an den Agent-PC schickt.

Der Filter sitzt im Proxy zwischen Browser (noVNC) und dem lokalen VNC-Socket von QEMU und liest den Datenstrom
**vom Client zum Server** Nachricht für Nachricht. Nur was für die Bilddarstellung nötig ist, geht weiter:

- Handshake (Protokollversion, Sicherheitstyp „None“, ClientInit – immer „geteilt“),
- SetPixelFormat, SetEncodings (nur bekannte Bild-Kodierungen – **ohne** „Extended Clipboard“, ohne QEMU-Ton und
  -Tastatur; Bildqualität und Kompression setzt der Proxy selbst), FramebufferUpdateRequest.

Tastatur (KeyEvent) und Maus (PointerEvent) gehen nur durch, wenn ``allow_input()`` es gerade erlaubt (Hilfe-Modus
mit Zustimmung zum Steuern). Zwischenablage (ClientCutText), XVP (Neustart/Ausschalten) und QEMU-Erweiterungen werden
immer verworfen. Alles Unbekannte beendet die Verbindung – die Länge wäre nicht bekannt.

QEMU schickt seine Zwischenablage nur an Clients, die „Extended Clipboard“ angemeldet haben (ui/vnc-clipboard.c) –
das ist herausgefiltert, also kommt auch in der Gegenrichtung keine Zwischenablage an.
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from bonys_agents.i18n import tr

# Client → Server
SET_PIXEL_FORMAT, SET_ENCODINGS, FB_UPDATE_REQUEST, KEY_EVENT, POINTER_EVENT, CLIENT_CUT_TEXT = 0, 2, 3, 4, 5, 6
XVP, QEMU_MSG = 250, 255

# Bild-Kodierungen und harmlose Pseudo-Kodierungen, die durchgehen
ALLOWED_ENCODINGS = frozenset({
    0,          # Raw
    1,          # CopyRect
    2,          # RRE
    5,          # Hextile
    6,          # Zlib
    7,          # Tight
    16,         # ZRLE
    17,         # ZYWRLE
    -260,       # Tight PNG
    -223,       # DesktopSize
    -308,       # ExtendedDesktopSize
    -239,       # Cursor
    -224,       # LastRect
    -257,       # QEMU Pointer Motion Change
    -261,       # QEMU LED-Status (Feststelltaste …)
    -307,       # DesktopName
    0x574D5669,  # WMVi
})
JPEG_QUALITY = range(-32, -22)       # Stufe 0 … 9
COMPRESS_LEVEL = range(-256, -246)   # Stufe 0 … 9
MAX_CUT_TEXT = 1 << 20
MAX_BUFFER = 1 << 21

# Qualitätsstufen für Zuschauer: (JPEG-Qualität 0–9, Kompression 0–9, Bilder pro Sekunde)
QUALITY = {
    "low": (2, 9, 5),
    "medium": (5, 6, 10),
    "high": (8, 2, 20),
}


class ProtocolError(ValueError):
    pass


def quality_encodings(quality: str) -> list[int]:
    jpeg, comp, _fps = QUALITY[quality]
    return [JPEG_QUALITY.start + jpeg, COMPRESS_LEVEL.start + comp]


def set_encodings(encodings: list[int]) -> bytes:
    return struct.pack("!BxH", SET_ENCODINGS, len(encodings)) + b"".join(struct.pack("!i", e) for e in encodings)


class ClientFilter:
    """Zerlegt den Datenstrom des Clients und entscheidet je Nachricht.

    ``feed(data)`` liefert eine Liste von (Art, Bytes): „pass“ = sofort an QEMU, „update“ = FramebufferUpdateRequest
    (der Proxy darf ihn verzögern – Bildrate, Pause). Verworfene Nachrichten tauchen nicht auf, werden aber in
    ``dropped`` gezählt. ``ProtocolError`` = Verbindung beenden.
    """

    def __init__(self, allow_input: Callable[[], bool] = lambda: False, quality: str | None = None):
        self.allow_input = allow_input
        self.quality = quality
        self.buf = b""
        self.state = "version"
        self.minor = 8
        self.dropped = 0
        self.dropped_input = 0

    def feed(self, data: bytes) -> list[tuple[str, bytes]]:
        self.buf += data
        if len(self.buf) > MAX_BUFFER:
            raise ProtocolError(tr("Zu viele Daten auf einmal"))
        out: list[tuple[str, bytes]] = []
        while True:
            item = self._next()
            if item is None:
                return out
            if item[0] != "drop":
                out.append(item)

    def _take(self, n: int) -> bytes | None:
        if len(self.buf) < n:
            return None
        chunk, self.buf = self.buf[:n], self.buf[n:]
        return chunk

    def _drop(self, n: int, is_input: bool) -> tuple[str, bytes] | None:
        if self._take(n) is None:
            return None
        self.dropped += 1
        if is_input:
            self.dropped_input += 1
        return ("drop", b"")

    def _next(self) -> tuple[str, bytes] | None:
        if self.state == "version":
            raw = self._take(12)
            if raw is None:
                return None
            if raw[:4] != b"RFB " or raw[11:] != b"\n" or not raw[4:11].replace(b".", b"").isdigit():
                raise ProtocolError(tr("Kein VNC-Client"))
            major, minor = int(raw[4:7]), int(raw[8:11])
            if major != 3:
                raise ProtocolError(tr("RFB-Version nicht unterstützt"))
            self.minor = 3 if minor < 7 else (7 if minor == 7 else 8)
            self.state = "security" if self.minor >= 7 else "init"
            return ("pass", b"RFB 003.%03d\n" % self.minor)
        if self.state == "security":
            raw = self._take(1)
            if raw is None:
                return None
            if raw != b"\x01":  # nur „None“ – der lokale Socket von QEMU hat kein Passwort
                raise ProtocolError(tr("Sicherheitstyp nicht erlaubt"))
            self.state = "init"
            return ("pass", raw)
        if self.state == "init":
            if self._take(1) is None:
                return None
            self.state = "msg"
            return ("pass", b"\x01")  # immer „geteilt“ – kein Zuschauer wirft andere hinaus
        if not self.buf:
            return None
        t = self.buf[0]
        if t == SET_PIXEL_FORMAT:
            raw = self._take(20)
            return None if raw is None else ("pass", raw)
        if t == SET_ENCODINGS:
            if len(self.buf) < 4:
                return None
            n = struct.unpack("!H", self.buf[2:4])[0]
            raw = self._take(4 + 4 * n)
            if raw is None:
                return None
            wanted = [e for (e,) in struct.iter_unpack("!i", raw[4:])]
            keep = [e for e in wanted if e in ALLOWED_ENCODINGS
                    or (self.quality is None and (e in JPEG_QUALITY or e in COMPRESS_LEVEL))]
            if self.quality:
                keep += quality_encodings(self.quality)
            return ("pass", set_encodings(keep))
        if t == FB_UPDATE_REQUEST:
            raw = self._take(10)
            return None if raw is None else ("update", raw)
        if t in (KEY_EVENT, POINTER_EVENT):
            n = 8 if t == KEY_EVENT else 6
            if len(self.buf) < n:
                return None
            if self.allow_input():
                return ("pass", self._take(n))
            return self._drop(n, True)
        if t == CLIENT_CUT_TEXT:
            if len(self.buf) < 8:
                return None
            length = abs(struct.unpack("!i", self.buf[4:8])[0])
            if length > MAX_CUT_TEXT:
                raise ProtocolError(tr("Zwischenablage zu groß"))
            return self._drop(8 + length, False)
        if t == XVP:
            return self._drop(4, False)
        if t == QEMU_MSG:
            if len(self.buf) < 2:
                return None
            sub = self.buf[1]
            if sub == 0:     # erweiterte Tastatur-Nachricht – nie angemeldet, also nie erwartet
                return self._drop(12, True)
            if sub == 1:     # Ton
                if len(self.buf) < 4:
                    return None
                op = struct.unpack("!H", self.buf[2:4])[0]
                return self._drop(10 if op == 2 else 4, False)
            raise ProtocolError(tr("Unbekannte QEMU-Nachricht"))
        raise ProtocolError(tr("Unbekannte Nachricht {t}", t=t))


# ---------------------------------------------------------------- Bausteine für Tests und den Proxy
def key_event(down: bool, keysym: int) -> bytes:
    return struct.pack("!BBxxI", KEY_EVENT, 1 if down else 0, keysym)


def pointer_event(mask: int, x: int, y: int) -> bytes:
    return struct.pack("!BBHH", POINTER_EVENT, mask, x, y)


def cut_text(text: bytes) -> bytes:
    return struct.pack("!BxxxI", CLIENT_CUT_TEXT, len(text)) + text


def update_request(incremental: bool, x: int, y: int, w: int, h: int) -> bytes:
    return struct.pack("!BBHHHH", FB_UPDATE_REQUEST, 1 if incremental else 0, x, y, w, h)
