# SPDX-License-Identifier: GPL-3.0-or-later
"""Grundsysteme eines Agent-PCs: Debian 13 (Standard) oder Kali Linux.

Beide kommen als offizielles Cloud-Abbild und werden mit derselben Einrichtung (cloud-init + Schritte) zum
Agent-PC. Kali braucht ein paar eigene Schritte (siehe ``cloudinit``): Das Cloud-Abbild hat einen Kernel ohne
Grafiktreiber und meldet root ab Werk automatisch an.
"""

from __future__ import annotations

from dataclasses import dataclass

from bonys_agents import desktops

DEBIAN = "debian"
KALI = "kali"
DEFAULT = DEBIAN


@dataclass(frozen=True)
class DistroSpec:
    id: str
    name: str
    description: str
    # Nur diese Architekturen des Hosts (leer = alle)
    archs: tuple[str, ...] = ()
    # Nur diese Desktops (leer = alle); der erste ist der Standard
    desktops: tuple[str, ...] = ()
    # Zusätzlich vorausgewählte Apps
    default_apps: tuple[str, ...] = ()

    def available(self, arch: str) -> bool:
        return not self.archs or arch in self.archs


DISTROS: dict[str, DistroSpec] = {d.id: d for d in (
    DistroSpec(
        id=DEBIAN,
        name="Debian 13",
        description="Debian 13 „Trixie“ – das stabile Standard-System für Agent-PCs",
    ),
    # Nur x86_64 und Xfce: so geprüft. Kali ist eine Rolling-Distribution (Paketstand „kali-last-snapshot“).
    DistroSpec(
        id=KALI,
        name="Kali Linux",
        description="Kali Linux mit den bekanntesten Werkzeugen für Sicherheitstests (nmap, Metasploit, Burp, "
                    "Wireshark …) – für Kurse und Übungen, nur an eigenen oder freigegebenen Systemen",
        archs=("x86_64",),
        desktops=("xfce",),
        default_apps=("kali-tools",),
    ),
)}


def get(distro_id: str) -> DistroSpec:
    try:
        return DISTROS[distro_id]
    except KeyError:
        raise ValueError(f"Unbekanntes Grundsystem „{distro_id}“. Verfügbar: {', '.join(DISTROS)}") from None


def name(distro_id: str) -> str:
    d = DISTROS.get(distro_id or DEFAULT)
    return d.name if d else distro_id


def check(distro_id: str, arch: str, desktop: str) -> None:
    """Fehler, wenn das Grundsystem auf diesem Rechner oder mit diesem Desktop nicht geht."""
    d = get(distro_id)
    if not d.available(arch):
        raise ValueError(f"{d.name} gibt es als Agent-PC nur auf {', '.join(d.archs)} (dieser Rechner: {arch}).")
    if d.desktops and desktop not in d.desktops:
        raise ValueError(f"{d.name} gibt es als Agent-PC nur mit {', '.join(desktops.name(i) for i in d.desktops)}.")
