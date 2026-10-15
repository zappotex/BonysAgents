# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: Freigabe bzw. Kurs im lokalen Netz per mDNS ankündigen (nur in „Bony's Agents Kursleiter“).

Teilnehmer suchen mit ``bonys_agents.mdns.browse()``. Im TXT-Eintrag stehen nur öffentliche Angaben – der Code nie.
"""

from __future__ import annotations

import contextlib
import random
import select
import socket
import struct
import threading

from bonys_agents.mdns import (
    GROUP, PORT, QU, SERVICE, T_A, T_ANY, T_PTR, T_SRV, T_TXT, TTL, _is_ipv4, _name, _rr, _safe_label, _txt, order,
    parse,
)


class Advertiser:
    """Beantwortet mDNS-Anfragen nach der Freigabe, solange ``start()`` … ``stop()`` läuft."""

    def __init__(self, instance: str, port: int, addresses: list[str], txt: dict[str, str]):
        self.instance = f"{_safe_label(instance)}.{SERVICE}"
        self.host = f"bonys-{random.getrandbits(32):08x}.local"
        self.port = port
        self.addresses = [a for a in addresses if _is_ipv4(a)]
        self.txt = txt
        self.sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error = ""

    def records(self, ttl: int = TTL, near: str | None = None) -> list[bytes]:
        out = [
            _rr(SERVICE, T_PTR, _name(self.instance), ttl),
            _rr(self.instance, T_SRV, struct.pack("!HHH", 0, 0, self.port) + _name(self.host), ttl, flush=True),
            _rr(self.instance, T_TXT, _txt(self.txt), ttl, flush=True),
        ]
        out += [_rr(self.host, T_A, socket.inet_aton(a), ttl, flush=True) for a in order(self.addresses, near)]
        return out

    def response(self, ttl: int = TTL, near: str | None = None) -> bytes:
        """``near``: Adresse des Fragenden – die Adresse aus seinem Netz kommt zuerst (nicht z. B. Docker)."""
        recs = self.records(ttl, near)
        return struct.pack("!HHHHHH", 0, 0x8400, 0, len(recs), 0, 0) + b"".join(recs)

    def answers(self, questions: list[tuple[str, int, int]]) -> bool:
        names = {SERVICE.lower(), self.instance.lower(), self.host.lower()}
        return any(n in names and t in (T_PTR, T_SRV, T_TXT, T_A, T_ANY) for n, t, _c in questions)

    def start(self) -> bool:
        """False (mit ``error``), wenn Port 5353 nicht nutzbar ist – die Freigabe geht trotzdem (Adresse eintippen)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                with contextlib.suppress(OSError):
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(("", PORT))
            for addr in self.addresses or ["0.0.0.0"]:
                with contextlib.suppress(OSError):
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                 socket.inet_aton(GROUP) + socket.inet_aton(addr))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        except OSError as e:
            self.error = f"mDNS nicht verfügbar ({e}) – Teilnehmer geben Adresse und Code ein."
            return False
        self.sock = s
        self._thread = threading.Thread(target=self._loop, name="mdns", daemon=True)
        self._thread.start()
        self._announce(TTL)
        return True

    def _announce(self, ttl: int) -> None:
        if self.sock is None:
            return
        for addr in self.addresses or [None]:
            with contextlib.suppress(OSError):
                if addr:
                    self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(addr))
                self.sock.sendto(self.response(ttl), (GROUP, PORT))

    def _loop(self) -> None:
        assert self.sock is not None
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self.sock], [], [], 0.5)
                if not ready:
                    continue
                packet, src = self.sock.recvfrom(9000)
                flags, questions, _ = parse(packet)
            except (OSError, ValueError, struct.error, IndexError):
                continue
            if flags & 0x8000 or not self.answers(questions):
                continue  # Antworten anderer oder fremde Fragen
            unicast = src[1] != PORT or any(c & QU for _n, _t, c in questions)
            with contextlib.suppress(OSError):
                self.sock.sendto(self.response(near=src[0]), src if unicast else (GROUP, PORT))

    def stop(self) -> None:
        self._stop.set()
        self._announce(0)  # abmelden
        if self._thread:
            self._thread.join(timeout=2)
        if self.sock:
            self.sock.close()
            self.sock = None
