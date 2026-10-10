# SPDX-License-Identifier: GPL-3.0-or-later
"""WireGuard auf dem eigenen Rechner (Host) – ohne Qt, damit es sich testen lässt.

- **Linux**: Bony's VPN. Das .deb bringt den Root-Helfer (``/usr/sbin/bonys-vpn-helper``), die
  polkit-Aktion (``auth_admin_keep``) und die systemd-Unit des Kill-Switch mit. Die Oberfläche ist
  der Bereich „VPN“ in Bony's Agents (``gui/host_vpn.py``). ``wireguard-tools`` und ``nftables``
  sind nur empfohlen und werden bei Bedarf nach Rückfrage per pkexec/apt nachinstalliert.
- **Windows**: die offizielle WireGuard-App per winget (``WireGuard.WireGuard``).
- **macOS**: die offizielle WireGuard-App gibt es nur im App Store. Einen offiziellen automatischen
  Weg gibt es nicht (Homebrew/MacPorts liefern nur die Kommandozeilen-Werkzeuge ohne App), also
  wird die App-Store-Seite geöffnet.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .procutil import clean_env
from .vpn import cli as vpncli
from .vpn import conf as wgconf

TOOLS = {"wg": "wireguard-tools", "wg-quick": "wireguard-tools", "nft": "nftables"}
PACKAGES = ("wireguard-tools", "nftables")
SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
# polkit-Regel von Bony's VPN: .deb, sonst install.py
RULES_FILES = (Path("/usr/share/polkit-1/rules.d/50-bonys-vpn.rules"), Path("/etc/polkit-1/rules.d/50-bonys-vpn.rules"))

WHOLE_COMPUTER = "Das VPN gilt dann für deinen ganzen Rechner, nicht nur für die Agent-PCs."
INTRO = (WHOLE_COMPUTER + "\n\nJedes Programm auf diesem Rechner – Browser, Mail, Updates und auch die "
         "Agent-PCs – geht dann durch den Tunnel. Agent-PCs mit eigenem Bony's VPN bauen ihren Tunnel "
         "zusätzlich durch diesen auf.\n\nFür Aktionen wie Verbinden und Trennen fragt dein Rechner nach "
         "dem Administrator-Passwort und merkt es sich einige Minuten.")
KILLSWITCH_WARNING = (
    "Kill-Switch für den ganzen Rechner einschalten?\n\n"
    "Solange kein Tunnel verbunden ist, kommt dann kein Programm auf diesem Rechner mehr ins Internet – "
    "auch nach einem Neustart nicht, bis du den Kill-Switch wieder abschaltest. Fällt der VPN-Server aus, "
    "bist du offline.\n\n"
    "Agent-PCs starten und laufen weiter: Steuerung, Fernzugriff (RDP/SPICE), Herunterfahren und "
    "Fortschritt gehen über diesen Rechner selbst und sind nicht betroffen. Ihr Internet geht dann aber "
    "ebenfalls nur über den Tunnel – ohne Tunnel können sie nichts herunterladen, und neue Agent-PCs "
    "lassen sich erst nach dem Verbinden erstellen.\n\n"
    "Geräte im Heimnetz (Drucker, NAS) erreichst du ohne Tunnel nur, wenn du ihr Netz als Ausnahme einträgst.")

# Windows
WINGET_ID = "WireGuard.WireGuard"
WINGET_INSTALL = ["winget", "install", "--id", WINGET_ID, "-e", "--silent",
                  "--accept-package-agreements", "--accept-source-agreements"]
WINDOWS_INTRO = (
    "Bony's Agents installiert jetzt die offizielle WireGuard-App über winget (Paket „WireGuard.WireGuard“, "
    "von wireguard.com).\n\n" + WHOLE_COMPUTER + "\n\nWindows fragt gleich nach Administratorrechten. "
    "Danach öffnest du die App, importierst dort deine .conf („Tunnel aus Datei importieren“) und klickst "
    "„Aktivieren“. Einen Kill-Switch bietet die App beim Bearbeiten eines Tunnels an "
    "(„Untunnelten Datenverkehr blockieren“).")

# macOS
MAC_APP_ID = "1451685025"
MAC_APP_STORE_URL = f"https://apps.apple.com/app/wireguard/id{MAC_APP_ID}"
MAC_APP_STORE_DEEPLINK = f"macappstore://apps.apple.com/app/id{MAC_APP_ID}"
MAC_APP = Path("/Applications/WireGuard.app")
MAC_INTRO = (
    "Die offizielle WireGuard-App für den Mac gibt es nur im App Store (kostenlos, von WireGuard "
    "Development Team). Einen offiziellen Weg, sie automatisch zu installieren, gibt es nicht – "
    "Homebrew bringt nur die Kommandozeilen-Werkzeuge ohne App.\n\n" + WHOLE_COMPUTER + "\n\n"
    "Gleich öffnet sich der App Store: dort „Laden“ klicken. Danach in der WireGuard-App „Tunnel aus "
    "Datei importieren“ wählen, deine .conf auswählen, macOS die VPN-Konfiguration erlauben und "
    "„Aktivieren“ klicken.")


class HostVpnError(RuntimeError):
    """Fehler mit deutscher Meldung für die Oberfläche (enthält nie Schlüssel)."""


# ---------------------------------------------------------------- Linux: Zustand
def supported() -> bool:
    return sys.platform.startswith("linux")


def helper() -> str | None:
    """Installierter Helfer (aus dem .deb oder per install.py) – sonst None."""
    path = vpncli.helper_path()
    return path if Path(path).exists() else None


def missing_tools(path: str = SYSTEM_PATH) -> list[str]:
    """Debian-Pakete, die für Bony's VPN noch fehlen (wireguard-tools, nftables)."""
    missing = []
    for tool, pkg in TOOLS.items():
        if not shutil.which(tool, path=path) and pkg not in missing:
            missing.append(pkg)
    return missing


def has_apt() -> bool:
    return bool(shutil.which("apt-get"))


def install_tools_command(packages: list[str] | None = None) -> list[str]:
    """pkexec apt-get install … – die Oberfläche fragt vorher nach."""
    pkgs = [p for p in (packages or list(PACKAGES)) if p in PACKAGES]
    script = ("set -e\nexport DEBIAN_FRONTEND=noninteractive\napt-get update -q\n"
              f"apt-get install -y -q --no-install-recommends {' '.join(pkgs)}\n")
    return ["pkexec", "sh", "-c", script]


def install_tools(packages: list[str] | None = None) -> None:
    if not shutil.which("pkexec"):
        raise HostVpnError("pkexec fehlt – bitte im Terminal „sudo apt install wireguard-tools nftables“ ausführen.")
    rc = subprocess.run(install_tools_command(packages), env=clean_env()).returncode
    if rc in (126, 127):
        raise HostVpnError("Die Anmeldung wurde abgebrochen – nichts installiert.")
    if rc != 0:
        raise HostVpnError(f"Die Installation ist fehlgeschlagen (Code {rc}).")


def status_needs_password(rules: tuple[Path, ...] = RULES_FILES) -> bool:
    """Erlaubt die polkit-Regel „… status“ ohne Passwort? Sonst fragt jede Statusabfrage nach dem
    Passwort – die Oberfläche fragt den Helfer dann nicht regelmäßig."""
    for f in rules:
        try:
            if 'command_line") == "' in f.read_text("utf-8"):
                return False
        except OSError:
            continue
    return True


def nm_wireguard(run=subprocess.run) -> set[str]:
    """Aktive WireGuard-Verbindungen des NetworkManager. Die trennt nur der NetworkManager selbst
    (wg-quick kennt sie nicht), und sie benutzen dieselbe Routing-Tabelle wie wg-quick (51820)."""
    if not shutil.which("nmcli"):
        return set()
    try:
        proc = run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"], capture_output=True,
                   text=True, timeout=5, env=clean_env({"LC_ALL": "C"}))
    except (OSError, subprocess.SubprocessError):
        return set()
    out = set()
    for line in proc.stdout.splitlines():
        name, _, kind = line.replace("\\:", "\0").rpartition(":")
        if kind == "wireguard":
            out.add(name.replace("\0", ":"))
    return out


# ---------------------------------------------------------------- Linux: Aktionen
def _call(args: list[str], data: bytes | None = None) -> str:
    if helper() is None:
        raise HostVpnError("Der Helfer von Bony's VPN ist nicht installiert – er kommt mit dem .deb von "
                           "Bony's Agents (/usr/sbin/bonys-vpn-helper).")
    try:
        return vpncli.call(args, data)
    except vpncli.CliError as e:
        raise HostVpnError(str(e)) from None


def _call_json(args: list[str], data: bytes | None = None):
    import json

    try:
        return json.loads(_call(args, data))
    except ValueError:
        raise HostVpnError("Unerwartete Antwort des Helfers.") from None


def status() -> dict:
    return _call_json(["status"])


def up(name: str) -> None:
    _call(["up", wgconf.check_name(name)])


def down(name: str | None = None) -> None:
    _call(["down"] + ([wgconf.check_name(name)] if name else []))


def import_conf(name: str, data: bytes, allow_hooks: bool = False, replace: bool = False) -> dict:
    extra = (["--allow-hooks"] if allow_hooks else []) + (["--replace"] if replace else [])
    return _call_json(["import", wgconf.check_name(name), *extra], data)


def delete(name: str) -> None:
    _call(["delete", wgconf.check_name(name)])


def rename(old: str, new: str) -> None:
    _call(["rename", wgconf.check_name(old), wgconf.check_name(new)])


def show(name: str) -> dict:
    return _call_json(["show", wgconf.check_name(name)])


def export(name: str) -> str:
    return _call(["export", wgconf.check_name(name)])


def set_autostart(name: str, on: bool) -> None:
    _call(["autostart", wgconf.check_name(name), "on" if on else "off"])


def set_killswitch(on: bool, exceptions: list[str] | None = None) -> dict:
    """Kill-Switch an/aus. ``exceptions`` (nur beim Einschalten): None = bisherige behalten, [] = keine."""
    extra: list[str] = []
    if on and exceptions is not None:
        extra = [x for net in exceptions for x in ("--exception", net)] or ["--no-exceptions"]
    return _call_json(["killswitch", "on" if on else "off", *extra])


def parse_exceptions(text: str) -> list[str]:
    """„192.168.178.0/24, 10.0.0.5“ → Liste. Ungültige Einträge → ValueError mit dem Eintrag."""
    import ipaddress

    out = []
    for item in text.replace(";", ",").replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            out.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError:
            raise ValueError(f"„{item}“ ist keine IP-Adresse und kein Netz (z. B. 192.168.178.0/24).") from None
    return out


# ---------------------------------------------------------------- Windows
def windows_app() -> Path | None:
    """wireguard.exe, falls die offizielle App installiert ist."""
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            exe = Path(base) / "WireGuard" / "wireguard.exe"
            if exe.is_file():
                return exe
    return None


def windows_install() -> None:
    """Offizielle WireGuard-App per winget installieren (Windows fragt nach Administratorrechten)."""
    if not shutil.which("winget"):
        raise HostVpnError("winget fehlt. Es kommt mit dem „App-Installer“ aus dem Microsoft Store. Alternativ "
                           "das Installationsprogramm von https://www.wireguard.com/install/ verwenden.")
    proc = subprocess.run(WINGET_INSTALL, capture_output=True, text=True, env=clean_env(),
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0 and windows_app() is None:
        detail = (proc.stdout or proc.stderr).strip().splitlines()[-1:] or [""]
        raise HostVpnError(f"WireGuard konnte nicht installiert werden (winget, Code {proc.returncode}). {detail[0]}")


def windows_open(exe: Path | None = None) -> None:
    exe = exe or windows_app()
    if exe is None:
        raise HostVpnError("Die WireGuard-App wurde nicht gefunden.")
    subprocess.Popen([str(exe)], env=clean_env(), close_fds=True)


# ---------------------------------------------------------------- macOS
def mac_app() -> Path | None:
    return MAC_APP if MAC_APP.exists() else None


def mac_open_app() -> None:
    subprocess.Popen(["open", "-a", str(MAC_APP)], env=clean_env())


def mac_open_store() -> None:
    """App-Store-Seite öffnen – erst die App Store-App direkt, sonst die Webseite."""
    if subprocess.run(["open", MAC_APP_STORE_DEEPLINK], env=clean_env()).returncode != 0:
        subprocess.run(["open", MAC_APP_STORE_URL], env=clean_env())
