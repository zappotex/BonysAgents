# SPDX-License-Identifier: GPL-3.0-or-later
"""Kleines mDNS/DNS-SD (Zeroconf) – nur was die Schulungs-Freigabe braucht, ohne zusätzliche Abhängigkeiten.

- ``Advertiser`` (nur Kursleiter, ``bonys_agents.trainer.announce``): beantwortet Anfragen nach
  ``_bonys-agents._tcp.local`` (PTR, SRV, TXT, A) im lokalen Netz, kündigt die Freigabe beim Start an und meldet
  sie am Ende ab (TTL 0). Hier stehen die gemeinsamen Bausteine (Namen, Einträge, Zerlegen).
- ``browse()``: fragt einmal im Netz nach (Antwort direkt an uns, „QU“) und sammelt die Freigaben.

Im TXT-Eintrag stehen nur öffentliche Angaben (Name, Version, Ersteller, Zertifikats-Fingerabdruck) – der
Freigabe-Code nie. In VPN-Netzen (WireGuard) geht Multicast nicht: dort Adresse und Code eintippen.
"""

from __future__ import annotations

import contextlib
import ipaddress
import select
import socket
import struct
import time
from dataclasses import dataclass, field

from bonys_agents.i18n import tr

GROUP = "224.0.0.251"
PORT = 5353
SERVICE = "_bonys-agents._tcp.local"
TTL = 120

T_A, T_PTR, T_TXT, T_SRV, T_ANY = 1, 12, 16, 33, 255
C_IN = 1
FLUSH = 0x8000
QU = 0x8000


def _name(name: str) -> bytes:
    out = b""
    for part in name.rstrip(".").split("."):
        raw = part.encode("utf-8")[:63]
        out += bytes([len(raw)]) + raw
    return out + b"\0"


def _read_name(data: bytes, pos: int, depth: int = 0) -> tuple[str, int]:
    labels = []
    end = None
    while True:
        if pos >= len(data) or depth > 20:
            raise ValueError(tr("kaputter Name"))
        n = data[pos]
        if n == 0:
            pos += 1
            break
        if n & 0xC0 == 0xC0:  # Zeiger
            ptr = ((n & 0x3F) << 8) | data[pos + 1]
            if end is None:
                end = pos + 2
            pos = ptr
            depth += 1
            continue
        labels.append(data[pos + 1:pos + 1 + n].decode("utf-8", errors="replace"))
        pos += 1 + n
    return ".".join(labels), (end if end is not None else pos)


def _rr(name: str, rtype: int, rdata: bytes, ttl: int = TTL, flush: bool = False) -> bytes:
    return _name(name) + struct.pack("!HHIH", rtype, C_IN | (FLUSH if flush else 0), ttl, len(rdata)) + rdata


def _txt(values: dict[str, str]) -> bytes:
    out = b""
    for k, v in values.items():
        raw = f"{k}={v}".encode()[:255]
        out += bytes([len(raw)]) + raw
    return out or b"\0"


def query(service: str = SERVICE, unicast: bool = True) -> bytes:
    head = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    return head + _name(service) + struct.pack("!HH", T_PTR, C_IN | (QU if unicast else 0))


@dataclass
class Record:
    name: str
    rtype: int
    ttl: int
    data: object


def parse(packet: bytes) -> tuple[int, list[tuple[str, int, int]], list[Record]]:
    """→ (flags, Fragen [(Name, Typ, Klasse)], Einträge aus Antwort/Zusatz)."""
    if len(packet) < 12:
        raise ValueError(tr("zu kurz"))
    _id, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", packet[:12])
    pos = 12
    questions = []
    for _ in range(qd):
        name, pos = _read_name(packet, pos)
        qtype, qclass = struct.unpack("!HH", packet[pos:pos + 4])
        pos += 4
        questions.append((name.lower(), qtype, qclass))
    records = []
    for _ in range(an + ns + ar):
        name, pos = _read_name(packet, pos)
        rtype, _rclass, ttl, rdlen = struct.unpack("!HHIH", packet[pos:pos + 10])
        pos += 10
        rd = packet[pos:pos + rdlen]
        data: object = rd
        if rtype == T_PTR:
            data = _read_name(packet, pos)[0]
        elif rtype == T_SRV:
            prio, weight, port = struct.unpack("!HHH", rd[:6])
            data = (port, _read_name(packet, pos + 6)[0])
        elif rtype == T_A and rdlen == 4:
            data = socket.inet_ntoa(rd)
        elif rtype == T_TXT:
            txt, i = {}, 0
            while i < len(rd):
                n = rd[i]
                item = rd[i + 1:i + 1 + n].decode("utf-8", errors="replace")
                if "=" in item:
                    k, v = item.split("=", 1)
                    txt[k] = v
                i += 1 + n
            data = txt
        records.append(Record(name, rtype, ttl, data))
        pos += rdlen
    return flags, questions, records


def _safe_label(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_ " else "-" for c in text)[:50] or "Freigabe"


@dataclass
class Found:
    instance: str
    host: str
    port: int
    addresses: list[str] = field(default_factory=list)
    txt: dict[str, str] = field(default_factory=dict)

    @property
    def address(self) -> str:
        return f"{self.addresses[0]}:{self.port}" if self.addresses else f"{self.host}:{self.port}"


def order(addresses: list[str], near: str | None) -> list[str]:
    """Adressen nach Nähe zu ``near`` sortieren (längstes gemeinsames Präfix zuerst)."""
    if not near or not _is_ipv4(near):
        return list(addresses)
    ref = int(ipaddress.IPv4Address(near))

    def common(a: str) -> int:
        return 32 - (int(ipaddress.IPv4Address(a)) ^ ref).bit_length()

    return sorted(addresses, key=common, reverse=True)


def _is_ipv4(addr: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv4Address)
    except ValueError:
        return False


def browse(timeout: float = 2.5, interfaces: list[str] | None = None) -> list[Found]:
    """Freigaben im lokalen Netz suchen (über alle IPv4-Schnittstellen)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.bind(("", 0))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        for addr in interfaces or [None]:
            with contextlib.suppress(OSError):
                if addr:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(addr))
                s.sendto(query(), (GROUP, PORT))
        records: list[Record] = []
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([s], [], [], left)
            if not ready:
                break
            try:
                packet, _src = s.recvfrom(9000)
                flags, _q, recs = parse(packet)
            except (OSError, ValueError, struct.error, IndexError):
                continue
            if flags & 0x8000:
                records += recs
    finally:
        s.close()
    return collect(records)


def collect(records: list[Record]) -> list[Found]:
    """Einträge zu Freigaben zusammensetzen (PTR → SRV/TXT → A)."""
    by = {}
    for r in records:
        by.setdefault((r.name.lower(), r.rtype), []).append(r)
    found = []
    for ptr in by.get((SERVICE.lower(), T_PTR), []):
        inst = str(ptr.data)
        if ptr.ttl == 0 or any(f.instance == inst for f in found):
            continue
        srv = by.get((inst.lower(), T_SRV))
        if not srv:
            continue
        port, host = srv[0].data
        txt = by.get((inst.lower(), T_TXT))
        addrs = [str(a.data) for a in by.get((host.lower(), T_A), [])]
        found.append(Found(instance=inst, host=host, port=port, addresses=list(dict.fromkeys(addrs)),
                           txt=txt[0].data if txt else {}))
    return found
