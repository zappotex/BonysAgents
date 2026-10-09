# SPDX-License-Identifier: GPL-3.0-or-later
"""Kill-Switch: nftables-Regelwerk in eigener Tabelle ``inet bonys_vpn``.

Nur ausgehender Verkehr wird gefiltert (Hook ``output``). Erlaubt sind:

- Loopback und die WireGuard-Geräte der Tunnel
- Antworten auf Verbindungen, die von außen hereinkommen (``ct direction reply``), etwa SSH zum Agent-PC
- DHCP (v4/v6) und IPv6-Nachbarsuche, damit die Netzwerkkarte ihre Adresse behält
- die Endpunkte (IP + UDP-Port) der Tunnel, damit der Tunnel überhaupt aufgebaut werden kann
- DNS nur für root (bzw. systemd-resolved), damit der Endpunkt-Name (z. B. ``*.myfritz.net``) auflösbar bleibt
- eine Ausnahmeliste von Netzen (im Agent-PC das QEMU-Netz 10.0.2.0/24 für die Steuerung)

Alles andere wird mit „administratively prohibited“ abgewiesen, damit Programme sofort einen Fehler
bekommen statt zu hängen. Das Regelwerk ersetzt die Tabelle in einem Schritt (``nft -f`` ist atomar).
"""

from __future__ import annotations

import ipaddress

TABLE = "bonys_vpn"


def check_exception(net: str) -> str:
    """Eintrag der Ausnahmeliste: IP-Adresse oder Netz (CIDR) → normalisiert, sonst ValueError."""
    return str(ipaddress.ip_network(net.strip(), strict=False))


def ruleset(interfaces: list[str], endpoints: list[tuple[str, int]], exceptions: list[str],
            dns_uids: list[int] | tuple[int, ...] = (0,)) -> str:
    """Regelwerk als Text für ``nft -f``.

    ``interfaces`` – geprüfte Tunnelnamen, ``endpoints`` – (IP, Port) mit bereits aufgelöster IP,
    ``exceptions`` – Netze in CIDR-Schreibweise, ``dns_uids`` – Benutzer, die DNS (Port 53) dürfen.
    """
    rules = [
        'oifname "lo" accept',
    ]
    if interfaces:
        rules.append("oifname { " + ", ".join(f'"{i}"' for i in sorted(set(interfaces))) + " } accept")
    rules += [
        "ct direction reply accept",
        "udp sport 68 udp dport 67 accept",
        "udp sport 546 udp dport 547 accept",
        "icmpv6 type { nd-router-solicit, nd-neighbor-solicit, nd-neighbor-advert } accept",
    ]
    for ip, port in sorted(set(endpoints)):
        addr = ipaddress.ip_address(ip)
        fam = "ip" if addr.version == 4 else "ip6"
        rules.append(f"{fam} daddr {addr} udp dport {int(port)} accept")
    for uid in sorted(set(dns_uids)):
        rules.append(f"meta skuid {int(uid)} udp dport 53 accept")
        rules.append(f"meta skuid {int(uid)} tcp dport 53 accept")
    for net in sorted({check_exception(n) for n in exceptions}):
        fam = "ip" if ipaddress.ip_network(net).version == 4 else "ip6"
        rules.append(f"{fam} daddr {net} accept")
    rules.append("reject with icmpx admin-prohibited")
    body = "\n".join(f"\t\t{r}" for r in rules)
    return (
        "# Bony's VPN – Kill-Switch (wird vom Helfer erzeugt, nicht von Hand ändern)\n"
        f"table inet {TABLE}\n"
        f"delete table inet {TABLE}\n"
        f"table inet {TABLE} {{\n"
        "\tchain output {\n"
        "\t\ttype filter hook output priority filter; policy drop;\n"
        f"{body}\n"
        "\t}\n"
        "}\n"
    )
