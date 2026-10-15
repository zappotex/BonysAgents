# SPDX-License-Identifier: GPL-3.0-or-later
"""Brücke zwischen einer WebSocket-Gegenstelle und dem lokalen VNC-Socket eines Agent-PCs (beide Editionen).

Der Teilnehmer braucht sie im Hilfe-Modus (Tunnel zum Kursleiter), der Kursleiter beim Vorführen (Zuschauer im
Browser). Was durchgeht, entscheidet ``rfb.ClientFilter`` – Eingaben nur, wenn sie erlaubt sind.
"""

from __future__ import annotations

import contextlib
import select
import socket
import ssl
import time
from collections.abc import Callable

from bonys_agents import rfb, websocket

MIN_FPS = 1.0
CLOSE_ERROR = 4010   # WebSocket-Schließcode „Bildschirm getrennt“ (versteht auch die Seite im Browser)


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
