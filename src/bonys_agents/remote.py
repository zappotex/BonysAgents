# SPDX-License-Identifier: GPL-3.0-or-later
"""Fernzugriff auf Agent-PCs: RDP (xrdp im Gast) und SPICE (direkt aus QEMU).

- Remmina-Profile (Linux) für jeden Agent-PC, Gruppe „Bony's Agents“ – ohne Passwörter
- .rdp-Dateien für die Windows-Remotedesktopverbindung
- Verbinden-Befehle je Host-System
- Firewall-Freigabe nur fürs lokale Netz (ufw bzw. Windows-Firewall) – immer erst nach Rückfrage
"""

from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

from bonys_agents import host
from bonys_agents.procutil import clean_env, no_window_flags, spawn_detached

GROUP = "Bony's Agents"
PROFILE_PREFIX = "bonys-agents-"
FIRST_RDP_PORT = 3390
FIRST_SPICE_PORT = 5901
REMMINA_FLATPAK = "org.remmina.Remmina"
REMMINA_PACKAGES = ["remmina", "remmina-plugin-rdp", "remmina-plugin-spice"]
LAN_WARNING = "Nur im Heimnetz verwenden. Diese Ports NICHT im Router freigeben."


# ---------------------------------------------------------------- Netzwerk
@dataclass(frozen=True)
class LanAddress:
    ip: str
    network: str  # z. B. 192.168.1.0/24


def lan_addresses() -> list[LanAddress]:
    """IPv4-Adressen dieses Rechners im lokalen Netz (ohne Loopback, Link-Local, Docker & Co.)."""
    result: list[LanAddress] = []
    try:
        interfaces = psutil.net_if_addrs()
    except Exception:  # noqa: BLE001
        return result
    for name, addrs in interfaces.items():
        if name.startswith(("docker", "br-", "virbr", "veth", "lo")):
            continue
        for a in addrs:
            if a.family != socket.AF_INET or not a.netmask:
                continue
            ip = ipaddress.ip_address(a.address)
            if ip.is_loopback or ip.is_link_local or not ip.is_private:
                continue
            net = ipaddress.ip_network(f"{a.address}/{a.netmask}", strict=False)
            if net.prefixlen >= 32:
                continue  # Punkt-zu-Punkt (z. B. VPN) – kein Heimnetz
            result.append(LanAddress(a.address, str(net)))
    return sorted(set(result), key=lambda x: x.ip)


def port_free(port: int) -> bool:
    for addr in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((addr, port))
            except OSError:
                return False
    return True


def next_free_port(start: int, used: set[int], check_host: bool = True) -> int:
    port = start
    while port in used or (check_host and not port_free(port)):
        port += 1
    return port


# ---------------------------------------------------------------- Remmina
def remmina_native() -> str | None:
    return shutil.which("remmina")


def remmina_flatpak() -> bool:
    if not shutil.which("flatpak"):
        return False
    try:
        return subprocess.run(["flatpak", "info", REMMINA_FLATPAK], capture_output=True, timeout=10,
                              env=clean_env()).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def remmina_command() -> list[str] | None:
    if remmina_native():
        return ["remmina"]
    if remmina_flatpak():
        return ["flatpak", "run", REMMINA_FLATPAK]
    return None


def remmina_dirs(native: bool | None = None, flatpak: bool | None = None) -> list[Path]:
    """Profil-Ordner der installierten Remmina-Varianten."""
    native = bool(remmina_native()) if native is None else native
    flatpak = remmina_flatpak() if flatpak is None else flatpak
    dirs = []
    if native:
        dirs.append(Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "remmina")
    if flatpak:
        dirs.append(Path.home() / ".var" / "app" / REMMINA_FLATPAK / "data" / "remmina")
    return dirs


def profile_name(vm_name: str, protocol: str) -> str:
    return f"{PROFILE_PREFIX}{vm_name}-{protocol.lower()}.remmina"


def remmina_profile(vm_name: str, protocol: str, server: str, port: int, username: str) -> str:
    """Inhalt einer .remmina-Datei – bewusst ohne Passwort (Remmina fragt danach)."""
    lines = [
        "[remmina]",
        f"name={vm_name} ({protocol})",
        f"group={GROUP}",
        f"protocol={protocol}",
        f"server={server}:{port}",
    ]
    if protocol == "RDP":
        lines += [f"username={username}", "sound=local", "resolution_mode=2", "colordepth=32",
                  "cert_ignore=1" if server == "127.0.0.1" else "cert_ignore=0"]
    else:  # SPICE
        # scale=2 (dynamische Auflösung): Remmina meldet jede neue Fenstergröße an den Gast – ohne bleibt
        # das Bild trotz resizeguest=1 in der Startgröße mittig im Fenster stehen
        lines += ["enableaudio=1", "resizeguest=1", "scale=2", "sharefolder="]
    return "\n".join(lines) + "\n"


def write_if_changed(path: Path, text: str) -> bool:
    try:
        if path.read_text("utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return True


def sync_profiles(vm_name: str, username: str, rdp_port: int, spice_port: int | None,
                  dirs: list[Path] | None = None) -> list[Path]:
    """Remmina-Profile eines Agent-PCs anlegen bzw. aktualisieren (nur wenn Remmina da ist)."""
    written = []
    for d in remmina_dirs() if dirs is None else dirs:
        items = [("RDP", rdp_port)] + ([("SPICE", spice_port)] if spice_port else [])
        for proto, port in items:
            path = d / profile_name(vm_name, proto)
            write_if_changed(path, remmina_profile(vm_name, proto, "127.0.0.1", port, username))
            written.append(path)
        if not spice_port:
            (d / profile_name(vm_name, "SPICE")).unlink(missing_ok=True)
    return written


def remove_profiles(vm_name: str, dirs: list[Path] | None = None) -> None:
    """Beim Löschen eines Agent-PCs: seine Remmina-Profile entfernen."""
    candidates = dirs if dirs is not None else remmina_dirs(native=True, flatpak=True)
    for d in candidates:
        for proto in ("RDP", "SPICE"):
            (d / profile_name(vm_name, proto)).unlink(missing_ok=True)


def rdp_file(server: str, port: int, username: str) -> str:
    """.rdp-Datei für die Windows-Remotedesktopverbindung (mstsc), mit Ton am Client."""
    return "\r\n".join([
        f"full address:s:{server}:{port}",
        f"username:s:{username}",
        "audiomode:i:0",
        "prompt for credentials:i:1",
        "screen mode id:i:2",
        "dynamic resolution:i:1",
        "authentication level:i:2",
    ]) + "\r\n"


def export_profiles(folder: Path, vm_name: str, username: str, rdp_port: int, spice_port: int | None,
                    server: str) -> list[Path]:
    """Profile für einen anderen PC: Remmina (.remmina) und Windows (.rdp), mit LAN-Adresse."""
    folder.mkdir(parents=True, exist_ok=True)
    out = [folder / f"{vm_name} (RDP).remmina", folder / f"{vm_name}.rdp"]
    out[0].write_text(remmina_profile(vm_name, "RDP", server, rdp_port, username), "utf-8")
    out[1].write_text(rdp_file(server, rdp_port, username), "utf-8")
    if spice_port:
        p = folder / f"{vm_name} (SPICE).remmina"
        p.write_text(remmina_profile(vm_name, "SPICE", server, spice_port, username), "utf-8")
        out.append(p)
    return out


# ---------------------------------------------------------------- Verbinden
def remote_viewer() -> str | None:
    found = shutil.which("remote-viewer")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
            for exe in Path(base).glob("VirtViewer*/bin/remote-viewer.exe"):
                return str(exe)
    return None


def spice_viewer_available() -> bool:
    return bool(remote_viewer() or (sys.platform.startswith("linux") and remmina_command()))


def connect_command(protocol: str, vm_name: str, username: str, port: int, work_dir: Path,
                    host_os: str | None = None) -> list[str]:
    """Befehl, der eine Verbindung öffnet – oder RuntimeError mit Hinweis, was fehlt."""
    host_os = host_os or host.detect().os
    protocol = protocol.upper()
    if protocol == "RDP":
        if host_os == "linux":
            cmd = remmina_command()
            if not cmd:
                raise RuntimeError("Für RDP bitte Remmina installieren (Knopf „Remmina installieren“).")
            profiles = [d / profile_name(vm_name, "RDP") for d in remmina_dirs()]
            target = next((str(p) for p in profiles if p.exists()), f"rdp://{username}@127.0.0.1:{port}")
            return cmd + ["-c", target]
        f = work_dir / f"{vm_name}.rdp"
        f.write_text(rdp_file("127.0.0.1", port, username), "utf-8")
        if host_os == "windows":
            return ["mstsc", str(f)]
        return ["open", str(f)]  # macOS: Microsoft Remote Desktop / Windows App
    # SPICE
    if host_os == "linux":
        cmd = remmina_command()
        profiles = [d / profile_name(vm_name, "SPICE") for d in remmina_dirs()] if cmd else []
        existing = next((str(p) for p in profiles if p.exists()), None)
        if cmd and existing:
            return cmd + ["-c", existing]
    viewer = remote_viewer()
    if viewer:
        return [viewer, f"--title={vm_name}", f"spice://127.0.0.1:{port}"]
    if host_os == "linux" and remmina_command():
        return remmina_command() + ["-c", f"spice://127.0.0.1:{port}"]
    raise RuntimeError("Für SPICE wird remote-viewer (Paket virt-viewer) oder Remmina benötigt.")


def connect(protocol: str, vm_name: str, username: str, port: int, work_dir: Path) -> None:
    spawn_detached(connect_command(protocol, vm_name, username, port, work_dir))


# ---------------------------------------------------------------- Remmina installieren (Linux)
def remmina_install_script() -> str:
    return "set -e\napt-get update\napt-get install -y " + " ".join(REMMINA_PACKAGES) + "\n"


# ---------------------------------------------------------------- Firewall (immer erst fragen!)
def ufw_active() -> bool:
    """Ist die ufw-Firewall eingeschaltet? (ohne Root lesbar)"""
    try:
        text = Path("/etc/ufw/ufw.conf").read_text()
    except OSError:
        return False
    return shutil.which("ufw") is not None and "ENABLED=yes" in text.replace(" ", "")


def ufw_script(ports: list[int], networks: list[str]) -> str:
    lines = ["set -e"]
    for net in networks:
        for port in ports:
            lines.append(f"ufw allow from {net} to any port {port} proto tcp comment \"Bony's Agents\"")
    return "\n".join(lines) + "\n"


def windows_firewall_command(rule_name: str, ports: list[int]) -> list[str]:
    """Firewall-Regel (nur lokales Subnetz) per UAC anlegen."""
    netsh = (f'advfirewall firewall add rule name=\\"{rule_name}\\" dir=in action=allow protocol=TCP '
             f'localport={",".join(map(str, ports))} remoteip=localsubnet')
    return ["powershell", "-NoProfile", "-Command",
            f"Start-Process netsh -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList \"{netsh}\""]


def firewall_needed(host_os: str | None = None) -> bool:
    """Lohnt sich eine Freigabe? Linux nur bei aktiver ufw, Windows immer."""
    host_os = host_os or host.detect().os
    return ufw_active() if host_os == "linux" else host_os == "windows"


def allow_firewall(vm_name: str, ports: list[int], gui: bool = False) -> tuple[bool, str]:
    """Ports nur fürs lokale Netz freigeben (fragt per pkexec/sudo bzw. UAC nach Rechten).

    Aufrufer müssen VORHER den Nutzer gefragt haben.
    """
    from bonys_agents import deps

    host_os = host.detect().os
    if host_os == "linux":
        networks = sorted({a.network for a in lan_addresses()})
        if not networks:
            return False, "Kein Heimnetz gefunden."
        cmd = deps._elevate_linux(ufw_script(ports, networks), gui)
    elif host_os == "windows":
        cmd = windows_firewall_command(f"Bony's Agents – {vm_name}", ports)
    else:
        return False, "Unter macOS fragt das System beim ersten Zugriff selbst nach."
    rc = subprocess.run(cmd, creationflags=no_window_flags(), env=clean_env()).returncode
    ports_txt = ", ".join(map(str, ports))
    return (rc == 0, f"Ports {ports_txt} fürs Heimnetz freigegeben." if rc == 0
            else f"Freigabe nicht erfolgt (Code {rc}).")
