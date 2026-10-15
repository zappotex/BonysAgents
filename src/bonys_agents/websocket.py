# SPDX-License-Identifier: GPL-3.0-or-later
"""WebSocket (RFC 6455) – nur was die Schulungen brauchen, ohne zusätzliche Abhängigkeiten.

Server-Seite (Browser mit noVNC ↔ Bony's Agents) und Client-Seite (Bony's Agents des Teilnehmers ↔ Kursleiter
im Hilfe-Modus). Nachrichten werden auf ``MAX_PAYLOAD`` begrenzt, Fragmente zusammengesetzt, Ping beantwortet.
"""

from __future__ import annotations

import base64
import collections
import contextlib
import hashlib
import os
import select
import socket
import ssl
import struct
import threading
from collections.abc import Callable

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
MAX_PAYLOAD = 4 * 1024 * 1024


class WebSocketClosed(ConnectionError):
    def __init__(self, code: int = 1000, reason: str = ""):
        super().__init__(f"WebSocket geschlossen ({code} {reason})".strip())
        self.code = code
        self.reason = reason


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key.strip() + GUID).encode()).digest()).decode()


def new_key() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def _read_exact(rfile, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = rfile.read(n - len(data))
        if not chunk:
            raise WebSocketClosed(1006, "Verbindung abgebrochen")
        data += chunk
    return data


def encode_frame(opcode: int, payload: bytes = b"", mask: bool = False) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    bit = 0x80 if mask else 0
    if n < 126:
        head += bytes([bit | n])
    elif n < 65536:
        head += bytes([bit | 126]) + struct.pack("!H", n)
    else:
        head += bytes([bit | 127]) + struct.pack("!Q", n)
    if mask:
        key = os.urandom(4)
        return head + key + _xor(payload, key)
    return head + payload


def _xor(data: bytes, key: bytes) -> bytes:
    if not data:
        return b""
    n = len(data)
    k = (key * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "little") ^ int.from_bytes(k, "little")).to_bytes(n, "little")


class Connection:
    """Eine WebSocket-Verbindung über bereits geöffnete Datei-Objekte (nach dem HTTP-Upgrade).

    ``client=True``: eigene Rahmen maskieren (Pflicht für Clients), eingehende dürfen nicht maskiert sein –
    beim Server genau umgekehrt. Schreiben ist threadsicher (Lesen nur aus einem Thread).
    """

    def __init__(self, rfile, wfile, client: bool = False, max_payload: int = MAX_PAYLOAD):
        self.rfile = rfile
        self.wfile = wfile
        self.client = client
        self.max_payload = max_payload
        self.closed = False
        self._wlock = threading.Lock()

    def send(self, payload: bytes, opcode: int = OP_BINARY) -> None:
        if self.closed:
            raise WebSocketClosed(1006, "schon geschlossen")
        frame = encode_frame(opcode, payload, mask=self.client)
        with self._wlock:
            self.wfile.write(frame)
            self.wfile.flush()

    def send_text(self, text: str) -> None:
        self.send(text.encode("utf-8"), OP_TEXT)

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        try:
            self.send(struct.pack("!H", code) + reason.encode("utf-8")[:120], OP_CLOSE)
        except (OSError, ValueError, WebSocketClosed):
            pass
        self.closed = True

    def recv(self) -> tuple[int, bytes]:
        """Nächste vollständige Nachricht (Text oder Binär). Wirft ``WebSocketClosed`` am Ende."""
        parts: list[bytes] = []
        first_op = None
        total = 0
        while True:
            b0, b1 = _read_exact(self.rfile, 2)
            fin, op = b0 & 0x80, b0 & 0x0F
            if b0 & 0x70:
                raise WebSocketClosed(1002, "Erweiterungen nicht unterstützt")
            masked = bool(b1 & 0x80)
            if masked == self.client:
                raise WebSocketClosed(1002, "Maskierung falsch")
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack("!H", _read_exact(self.rfile, 2))[0]
            elif n == 127:
                n = struct.unpack("!Q", _read_exact(self.rfile, 8))[0]
            if op >= 0x8 and (n > 125 or not fin):
                raise WebSocketClosed(1002, "Steuerrahmen zu groß")
            if total + n > self.max_payload:
                raise WebSocketClosed(1009, "Nachricht zu groß")
            key = _read_exact(self.rfile, 4) if masked else b""
            data = _read_exact(self.rfile, n)
            if masked:
                data = _xor(data, key)
            if op == OP_PING:
                self.send(data, OP_PONG)
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                code = struct.unpack("!H", data[:2])[0] if len(data) >= 2 else 1005
                reason = data[2:].decode("utf-8", errors="replace")
                self.close(code if code not in (1005, 1006) else 1000)
                raise WebSocketClosed(code, reason)
            if op == OP_CONT:
                if first_op is None:
                    raise WebSocketClosed(1002, "Fortsetzung ohne Anfang")
            elif op in (OP_TEXT, OP_BINARY):
                if first_op is not None:
                    raise WebSocketClosed(1002, "neue Nachricht mitten in einer anderen")
                first_op = op
            else:
                raise WebSocketClosed(1002, "unbekannter Rahmen")
            parts.append(data)
            total += n
            if fin:
                return first_op, b"".join(parts)


class FrameParser:
    """Rahmen aus einem Bytestrom zerlegen (für Schleifen mit ``select`` statt blockierendem Lesen).

    ``feed(data)`` gibt fertige Nachrichten als (Opcode, Nutzdaten) zurück – Text/Binär zusammengesetzt,
    Steuerrahmen (Close, Ping, Pong) einzeln. ``WebSocketClosed`` bei Protokollfehlern.
    """

    def __init__(self, expect_masked: bool = True, max_payload: int = MAX_PAYLOAD):
        self.expect_masked = expect_masked
        self.max_payload = max_payload
        self.buf = bytearray()
        self.parts: list[bytes] = []
        self.first_op: int | None = None
        self.total = 0

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self.buf += data
        out: list[tuple[int, bytes]] = []
        while True:
            frame = self._frame()
            if frame is None:
                return out
            fin, op, payload = frame
            if op >= 0x8:
                out.append((op, payload))
                continue
            if op == OP_CONT:
                if self.first_op is None:
                    raise WebSocketClosed(1002, "Fortsetzung ohne Anfang")
            elif op in (OP_TEXT, OP_BINARY):
                if self.first_op is not None:
                    raise WebSocketClosed(1002, "neue Nachricht mitten in einer anderen")
                self.first_op = op
            else:
                raise WebSocketClosed(1002, "unbekannter Rahmen")
            self.parts.append(payload)
            self.total += len(payload)
            if self.total > self.max_payload:
                raise WebSocketClosed(1009, "Nachricht zu groß")
            if fin:
                out.append((self.first_op, b"".join(self.parts)))
                self.parts, self.first_op, self.total = [], None, 0

    def _frame(self) -> tuple[bool, int, bytes] | None:
        buf = self.buf
        if len(buf) < 2:
            return None
        b0, b1 = buf[0], buf[1]
        if b0 & 0x70:
            raise WebSocketClosed(1002, "Erweiterungen nicht unterstützt")
        masked = bool(b1 & 0x80)
        if masked != self.expect_masked:
            raise WebSocketClosed(1002, "Maskierung falsch")
        n = b1 & 0x7F
        pos = 2
        if n == 126:
            if len(buf) < 4:
                return None
            n = struct.unpack("!H", buf[2:4])[0]
            pos = 4
        elif n == 127:
            if len(buf) < 10:
                return None
            n = struct.unpack("!Q", buf[2:10])[0]
            pos = 10
        op = b0 & 0x0F
        if op >= 0x8 and (n > 125 or not b0 & 0x80):
            raise WebSocketClosed(1002, "Steuerrahmen zu groß")
        if n > self.max_payload:
            raise WebSocketClosed(1009, "Nachricht zu groß")
        end = pos + (4 if masked else 0) + n
        if len(buf) < end:
            return None
        key = bytes(buf[pos:pos + 4]) if masked else b""
        payload = bytes(buf[end - n:end])
        del buf[:end]
        return bool(b0 & 0x80), op, (_xor(payload, key) if masked else payload)


def close_payload(code: int, reason: str = "") -> bytes:
    return struct.pack("!H", code) + reason.encode("utf-8")[:120]


def parse_close(payload: bytes) -> tuple[int, str]:
    if len(payload) < 2:
        return 1005, ""
    return struct.unpack("!H", payload[:2])[0], payload[2:].decode("utf-8", errors="replace")


class Mailbox:
    """Postfach für eine ``select``-Schleife: andere Threads legen Nachrichten ab und wecken die Schleife über ein
    Socket-Paar. Einträge: (Opcode, Nutzdaten) zum Senden oder („close“, Code, Grund)."""

    def __init__(self):
        self._items: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._r, self._w = socket.socketpair()
        self._r.setblocking(False)
        self._w.setblocking(False)

    def fileno(self) -> int:
        return self._r.fileno()

    def put(self, item: tuple) -> None:
        with self._lock:
            self._items.append(item)
        with contextlib.suppress(OSError):
            self._w.send(b"\0")

    def send_text(self, text: str) -> None:
        self.put((OP_TEXT, text.encode("utf-8")))

    def close_with(self, code: int, reason: str = "") -> None:
        self.put(("close", code, reason))

    def take(self) -> list[tuple]:
        with contextlib.suppress(OSError):
            while self._r.recv(4096):
                pass
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items

    def dispose(self) -> None:
        for s in (self._r, self._w):
            with contextlib.suppress(OSError):
                s.close()


def serve(tls, mailbox: Mailbox, on_message: Callable[[int, bytes], None],
          should_close: Callable[[], tuple[int, str] | None] = lambda: None, client_side: bool = False,
          poll: float = 0.25) -> tuple[int, str] | None:
    """WebSocket-Schleife in einem Thread: liest vom TLS-Socket (→ ``on_message``) und schickt, was im Postfach
    liegt. Nur dieser Thread benutzt den Socket. Gibt (Code, Grund) des Endes zurück (None = Abbruch)."""
    parser = FrameParser(expect_masked=not client_side)

    def send(op: int, payload: bytes) -> None:
        tls.settimeout(30)
        tls.sendall(encode_frame(op, payload, mask=client_side))

    try:
        while True:
            why = should_close()
            if why:
                send(OP_CLOSE, close_payload(*why))
                return why
            for item in mailbox.take():
                if item[0] == "close":
                    send(OP_CLOSE, close_payload(item[1], item[2]))
                    return item[1], item[2]
                send(item[0], item[1])
            readable = [tls] if tls.pending() else select.select([tls, mailbox], [], [], poll)[0]
            if tls not in readable:
                continue
            tls.settimeout(0.05)
            try:
                data = tls.recv(65536)
            except (TimeoutError, ssl.SSLWantReadError):
                continue
            if not data:
                return None
            for op, payload in parser.feed(data):
                if op == OP_CLOSE:
                    with contextlib.suppress(OSError, ValueError):
                        send(OP_CLOSE, close_payload(1000))
                    return parse_close(payload)
                if op == OP_PING:
                    send(OP_PONG, payload)
                elif op in (OP_TEXT, OP_BINARY):
                    on_message(op, payload)
    except WebSocketClosed as e:
        with contextlib.suppress(OSError, ValueError):
            send(OP_CLOSE, close_payload(e.code if e.code < 4000 else 1002))
        return e.code, e.reason
    except (OSError, ValueError, ssl.SSLError):
        return None
