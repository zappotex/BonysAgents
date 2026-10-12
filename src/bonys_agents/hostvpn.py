# SPDX-License-Identifier: GPL-3.0-or-later
"""WireGuard auf dem eigenen Rechner (Host) – ohne Qt, damit es sich testen lässt.

- **Linux**: Bony's VPN, ein eigenes Projekt (https://github.com/zappotex/bonys-vpn) mit eigener
  Oberfläche. Bony's Agents öffnet es nur bzw. installiert das Paket ``bonys-vpn`` nach Rückfrage
  aus der offiziellen Quelle: aus der APT-Paketquelle, wenn sie eingerichtet ist, sonst das .deb aus
  dem GitHub-Release (minisign-Signatur und SHA-256 geprüft), jeweils über pkexec.
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
from collections.abc import Callable
from pathlib import Path

from . import updates
from .procutil import clean_env
from .vpnlink import VPN_REPO, VPN_REPO_URL

PACKAGE = "bonys-vpn"
GUI = "bonys-vpn-gui"
GUI_PATH = Path("/usr/bin/bonys-vpn-gui")
VPN_SOURCES = Path("/etc/apt/sources.list.d/bonys-vpn.sources")
# Altes .deb von Bony's Agents (bis 0.14) brachte Bony's VPN mit – Reste davon erkennen
OLD_STATE = Path("/etc/bonys-vpn/killswitch.json")

WHOLE_COMPUTER = "Das VPN gilt dann für deinen ganzen Rechner, nicht nur für die Agent-PCs."
LINUX_INTRO = (
    "Bony's VPN ist ein eigenes Programm von mir für WireGuard-Tunnel – mit Kill-Switch, Tray-Symbol und "
    f"Import per Drag&Drop ({VPN_REPO_URL}).\n\n" + WHOLE_COMPUTER + "\n\n"
    "Bony's Agents installiert jetzt das Paket „bonys-vpn“ aus der offiziellen Quelle: aus der Paketquelle "
    "von Bony's Agents, sonst aus dem GitHub-Release (Signatur und Prüfsumme werden geprüft). Dein Rechner "
    "fragt dafür nach dem Administrator-Passwort. Updates kommen danach über die Aktualisierungsverwaltung.")
OLD_INSTALL_HINT = ("Bony's VPN steckt nicht mehr in Bony's Agents. Deine Tunnel in /etc/wireguard sind noch da – "
                    "zum Verwalten Bony's VPN installieren.")

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


# ---------------------------------------------------------------- Linux: Bony's VPN
def supported() -> bool:
    return sys.platform.startswith("linux")


def gui_command() -> str | None:
    """Oberfläche von Bony's VPN, wenn das Paket installiert ist."""
    found = shutil.which(GUI, path=os.pathsep.join(["/usr/bin", "/usr/local/bin", os.environ.get("PATH", "")]))
    return found or (str(GUI_PATH) if GUI_PATH.exists() else None)


def installed_version() -> str | None:
    """Installierte Version des Pakets bonys-vpn – None, wenn es fehlt (oder kein dpkg da ist)."""
    if not shutil.which("dpkg-query"):
        return None
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${db:Status-Status} ${Version}", PACKAGE],
                           capture_output=True, text=True, timeout=15, env=clean_env())
    except (OSError, subprocess.SubprocessError):
        return None
    state, _, version = r.stdout.strip().partition(" ")
    return version if r.returncode == 0 and state == "installed" and version else None


def old_leftovers() -> bool:
    """Gibt es Einstellungen der alten, eingebauten Fassung, aber kein Bony's VPN mehr?"""
    return OLD_STATE.exists() and gui_command() is None


def can_install() -> bool:
    return bool(shutil.which("apt-get") and shutil.which("dpkg"))


def open_app() -> None:
    cmd = gui_command()
    if cmd is None:
        raise HostVpnError("Bony's VPN ist nicht installiert.")
    subprocess.Popen([cmd], env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def deb_arch() -> str:
    try:
        out = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=10,
                             env=clean_env()).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return out or {"x86_64": "amd64", "aarch64": "arm64"}.get(os.uname().machine, os.uname().machine)


def asset_name(info: updates.UpdateInfo, arch: str) -> str:
    """Paket im Release: „all“ (reines Python), sonst passend zur Architektur."""
    for candidate in (f"{PACKAGE}_{info.version}_all.deb", f"{PACKAGE}_{info.version}_{arch}.deb"):
        if candidate in info.assets:
            return candidate
    raise HostVpnError(f"Im Release {info.tag} von Bony's VPN gibt es kein Paket für {arch}.")


def apt_configured() -> bool:
    return updates.apt_source_configured() or updates.apt_source_configured(VPN_SOURCES)


def apt_script() -> str:
    return ("set -e\nexport DEBIAN_FRONTEND=noninteractive\n"
            'apt-get update || echo "Warnung: Nicht alle Paketquellen ließen sich aktualisieren."\n'
            f"apt-get install -y {PACKAGE}\n")


def install(log: Callable[[str], None], opener=None, runner=None) -> str:
    """Bony's VPN installieren (die Oberfläche fragt vorher). Gibt die installierte Version zurück.

    Erst die Paketquelle (enthält bonys-vpn in beiden Suiten), sonst bzw. wenn das nicht klappt das
    geprüfte .deb aus dem offiziellen Release. Root nur über pkexec.
    """
    from . import deps

    run = runner or (lambda script: deps._run(deps._elevate_linux(script, gui=True), log))
    if apt_configured():
        log("Installiere bonys-vpn aus der Paketquelle (fragt nach deinem Passwort) …")
        rc = run(apt_script())
        if rc in (126, 127):
            raise HostVpnError("Die Anmeldung wurde abgebrochen – nichts installiert.")
        if rc == 0 and installed_version():
            return installed_version() or ""
        log("Über die Paketquelle ging es nicht – lade das Paket direkt aus dem Release.")
    log("Suche die neueste Version von Bony's VPN auf GitHub …")
    try:
        info = updates.fetch_latest(VPN_REPO, opener=opener)
    except Exception as e:  # noqa: BLE001
        raise HostVpnError(f"GitHub ist nicht erreichbar: {e}") from None
    if info is None:
        raise HostVpnError("Auf GitHub gibt es noch kein Release von Bony's VPN.")
    name = asset_name(info, deb_arch())
    log(f"Lade {name} und prüfe Signatur und Prüfsumme …")
    try:
        deb = updates.download_verified(info, name, updates.download_dir(), repo=VPN_REPO, opener=opener)
    except updates.UpdateError as e:
        raise HostVpnError(str(e)) from None
    log("Signatur und Prüfsumme in Ordnung. Installiere (fragt nach deinem Passwort) …")
    rc = run(updates.deb_install_script(deb))
    shutil.rmtree(deb.parent, ignore_errors=True)
    if rc in (126, 127):
        raise HostVpnError("Die Anmeldung wurde abgebrochen – nichts installiert.")
    if rc != 0:
        raise HostVpnError(f"Die Installation ist fehlgeschlagen (Code {rc}).")
    return installed_version() or info.version


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
