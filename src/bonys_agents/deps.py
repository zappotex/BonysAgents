# SPDX-License-Identifier: GPL-3.0-or-later
"""Prüft und installiert alles, was Bony's Agents auf dem Host braucht.

- Linux:   QEMU über den Paketmanager (apt, dnf, pacman, zypper) und Zugriff auf /dev/kvm
- Windows: QEMU über winget und die Windows-Hypervisorplattform (WHPX)
- macOS:   QEMU über Homebrew (fehlt Homebrew, öffnet sich der offizielle Installer im Terminal)

Administratorrechte werden nur für genau diese Schritte angefragt
(pkexec/sudo unter Linux, UAC unter Windows).
"""

from __future__ import annotations

import getpass
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bonys_agents import host, qemu
from bonys_agents.procutil import clean_env, no_window_flags

LogFn = Callable[[str], None]


@dataclass(frozen=True)
class Issue:
    key: str        # qemu | firmware | homebrew | kvm-missing | kvm-access | whpx | hvf | rosetta
    text: str
    fixable: bool
    blocking: bool  # ohne Behebung kann gar keine VM starten


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def can_run(self) -> bool:
        return not any(i.blocking for i in self.issues)

    @property
    def fixable(self) -> list[Issue]:
        return [i for i in self.issues if i.fixable]


@dataclass
class InstallResult:
    success: bool
    reboot_required: bool = False
    message: str = ""


# ---------------------------------------------------------------- Prüfen
def check(info: host.HostInfo | None = None) -> Report:
    info = info or host.detect()
    r = Report()
    qemu_bin = None
    try:
        qemu_bin = qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os)
        qemu.find_binary("qemu-img", info.os)
    except qemu.QemuNotFound:
        r.issues.append(Issue("qemu", "QEMU (die Virtualisierungs-Software) ist nicht installiert.", True, True))

    if qemu_bin and info.arch == "aarch64":
        try:
            qemu.find_aarch64_firmware(qemu_bin)
        except qemu.QemuNotFound:
            r.issues.append(Issue("firmware", "UEFI-Firmware für ARM64 fehlt.", True, True))

    if info.os == "linux":
        if not os.path.exists("/dev/kvm"):
            r.issues.append(Issue(
                "kvm-missing",
                "Keine Hardware-Virtualisierung (/dev/kvm fehlt). Meist muss sie im BIOS/UEFI "
                "eingeschaltet werden (Intel VT-x bzw. AMD-V/SVM).", True, False,
            ))
        elif not os.access("/dev/kvm", os.R_OK | os.W_OK):
            r.issues.append(Issue("kvm-access", "Dein Benutzer darf KVM noch nicht verwenden.", True, False))
    elif info.os == "windows":
        if host.windows_hypervisor_state() == "disabled":
            r.issues.append(Issue(
                "whpx", "Die Windows-Hypervisorplattform ist ausgeschaltet – VMs liefen sehr langsam.", True, False,
            ))
    elif info.os == "macos":
        if qemu_bin is None and find_brew(info.arch) is None:
            r.issues.append(Issue(
                "homebrew", "Homebrew fehlt – damit wird QEMU installiert (kostenlos, von brew.sh).", True, True,
            ))
        if info.accel != "hvf":
            r.issues.append(Issue("hvf", "Dieser Mac unterstützt keine Hardware-Virtualisierung.", False, False))
        if host.macos_rosetta():
            r.issues.append(Issue(
                "rosetta", "Hier läuft die Intel-Version von Bony's Agents auf einem Mac mit Apple-Chip. "
                "Bitte die Version für Apple-Chip laden (…-macos-applesilicon.dmg).", False, False,
            ))
    return r


# ---------------------------------------------------------------- Linux
LINUX_PACKAGES = {
    "apt-get": {
        "x86_64": ["qemu-system-x86", "qemu-system-gui", "qemu-utils", "acl"],
        "aarch64": ["qemu-system-arm", "qemu-system-gui", "qemu-utils", "qemu-efi-aarch64", "acl"],
    },
    "dnf": {
        "x86_64": ["qemu-kvm", "qemu-img", "qemu-ui-gtk", "acl"],
        "aarch64": ["qemu-kvm", "qemu-img", "qemu-ui-gtk", "edk2-aarch64", "acl"],
    },
    "pacman": {
        "x86_64": ["qemu-desktop", "acl"],
        "aarch64": ["qemu-desktop", "edk2-aarch64", "acl"],
    },
    "zypper": {
        "x86_64": ["qemu-x86", "qemu-tools", "qemu-ui-gtk", "acl"],
        "aarch64": ["qemu-arm", "qemu-tools", "qemu-ui-gtk", "qemu-uefi-aarch64", "acl"],
    },
}

_INSTALL_CMD = {
    "apt-get": "(apt-get update || true) && DEBIAN_FRONTEND=noninteractive apt-get install -y {pkgs}",
    "dnf": "dnf install -y {pkgs}",
    "pacman": "pacman -S --needed --noconfirm {pkgs}",
    "zypper": "zypper --non-interactive install {pkgs}",
}


def linux_package_manager() -> str | None:
    for pm in ("apt-get", "dnf", "pacman", "zypper"):
        if shutil.which(pm):
            return pm
    return None


def linux_root_script(info: host.HostInfo, report: Report, user: str, pm: str | None) -> str:
    """Ein einziges Root-Skript, damit nur einmal nach dem Passwort gefragt wird."""
    keys = {i.key for i in report.fixable}
    lines = ["set -e"]
    if keys & {"qemu", "firmware"}:
        if pm is None:
            raise RuntimeError("Kein unterstützter Paketmanager gefunden (apt, dnf, pacman, zypper).")
        pkgs = " ".join(LINUX_PACKAGES[pm][info.arch])
        lines.append(_INSTALL_CMD[pm].format(pkgs=pkgs))
    if "kvm-missing" in keys:
        lines.append("modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true")
    # Zugriff auf KVM: dauerhaft über die Gruppe, sofort über eine ACL (kein Neu-Anmelden nötig).
    lines += [
        "if [ -e /dev/kvm ]; then",
        "  getent group kvm >/dev/null || groupadd -r kvm",
        f"  usermod -aG kvm '{user}' || true",
        f"  setfacl -m u:'{user}':rw /dev/kvm 2>/dev/null || true",
        "fi",
    ]
    return "\n".join(lines) + "\n"


def _elevate_linux(script: str, gui: bool) -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ["sh", "-c", script]
    if gui and shutil.which("pkexec"):
        return ["pkexec", "sh", "-c", script]
    if shutil.which("sudo"):
        return ["sudo", "sh", "-c", script]
    if shutil.which("pkexec"):
        return ["pkexec", "sh", "-c", script]
    raise RuntimeError("Weder sudo noch pkexec gefunden – bitte als Administrator ausführen.")


# ---------------------------------------------------------------- Windows
WINGET_QEMU = [
    "winget", "install", "--id", "SoftwareFreedomConservancy.QEMU", "-e", "--silent",
    "--accept-package-agreements", "--accept-source-agreements",
]
ENABLE_WHPX = [
    "powershell", "-NoProfile", "-Command",
    "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
    "'-NoProfile -Command Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All -NoRestart'",
]


# ---------------------------------------------------------------- macOS
# Homebrew liegt auf Macs mit Apple-Chip unter /opt/homebrew, auf Intel-Macs unter /usr/local.
# Aus dem Finder gestartete Apps haben beide Ordner NICHT im PATH – deshalb hier selbst suchen.
HOMEBREW_PREFIX = {"aarch64": Path("/opt/homebrew"), "x86_64": Path("/usr/local")}
HOMEBREW_INSTALL_URL = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"


def homebrew_explanation(in_terminal: bool = False) -> str:
    """Was Homebrew ist und was gleich passiert – ``in_terminal``: Kommandozeile statt App."""
    where = ("Gleich startet hier der offizielle Installationsbefehl von brew.sh. Dann:" if in_terminal else
             "Es öffnet sich jetzt das Terminal mit dem offiziellen Installationsbefehl von brew.sh. Dort:")
    return (
        "Für die Agent-PCs braucht dein Mac QEMU. Das installiert Bony's Agents über Homebrew – "
        "den bekanntesten (kostenlosen) Paketmanager für macOS (https://brew.sh).\n\n"
        f"Homebrew ist noch nicht installiert. {where}\n"
        "  1. mit der Eingabetaste bestätigen,\n"
        "  2. dein Mac-Passwort eingeben (man sieht beim Tippen nichts – das ist normal),\n"
        "  3. warten, bis „Fertig“ erscheint. Danach wird QEMU automatisch installiert.\n\n"
        "Das dauert meist 5–15 Minuten." + ("" if in_terminal else " Danach hier „Erneut prüfen“ wählen.")
    )


INTEL_QEMU_NOTE = (
    "Hinweis für Intel-Macs: Homebrew bietet QEMU für Intel oft nur noch als Quellcode an – "
    "dann baut dein Mac es selbst. Das kann 30–60 Minuten dauern, bitte das Fenster offen lassen."
)


def find_brew(arch: str) -> Path | None:
    """Homebrew finden – zuerst das zur Hardware passende (Apple-Chip: /opt/homebrew)."""
    prefixes = [HOMEBREW_PREFIX[arch]] + [p for a, p in HOMEBREW_PREFIX.items() if a != arch]
    for prefix in prefixes:
        brew = prefix / "bin" / "brew"
        if brew.exists():
            return brew
    found = shutil.which("brew")
    return Path(found) if found else None


def homebrew_install_script(arch: str) -> str:
    """Shell-Skript: offizieller Homebrew-Installer, danach QEMU. Läuft sichtbar im Terminal."""
    brew = f"{HOMEBREW_PREFIX[arch].as_posix()}/bin/brew"  # Mac-Pfad – auch wenn der Test unter Windows läuft
    lines = [
        "echo \"Bony's Agents: Homebrew und QEMU werden installiert.\"",
        f"/bin/bash -c \"$(curl -fsSL {HOMEBREW_INSTALL_URL})\" || exit 1",
        f"eval \"$({brew} shellenv)\"",
    ]
    if arch == "x86_64":
        lines.append(f"echo {shlex.quote(INTEL_QEMU_NOTE)}")
    lines += [
        "brew install qemu || exit 1",
        "echo",
        "echo \"Fertig! Dieses Fenster kann geschlossen werden – in Bony's Agents jetzt „Erneut prüfen“ wählen.\"",
    ]
    return "\n".join(lines) + "\n"


def open_homebrew_installer(arch: str) -> Path:
    """Terminal-Fenster mit dem Homebrew-Installer öffnen – der Benutzer bestätigt dort selbst.

    Das Skript liegt in einer Datei: so muss nichts davon durch AppleScript hindurch maskiert werden.
    """
    import tempfile

    from bonys_agents.procutil import spawn_detached, terminal_command

    fd, name = tempfile.mkstemp(prefix="bonys-agents-homebrew-", suffix=".sh")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(homebrew_install_script(arch))
    spawn_detached(terminal_command(["/bin/bash", name], "macos"))
    return Path(name)


def run_homebrew_installer_here(arch: str) -> int:
    """Kommandozeile: Homebrew-Installer direkt in diesem Terminal ausführen (Ein- und Ausgabe sichtbar)."""
    return subprocess.call(["/bin/bash", "-c", homebrew_install_script(arch)], env=clean_env())


def _brew_env() -> dict[str, str]:
    return clean_env({"HOMEBREW_NO_ENV_HINTS": "1", "HOMEBREW_NO_INSTALL_CLEANUP": "1"})


# ---------------------------------------------------------------- Ausführen
def _run(cmd: list[str], log: LogFn, env: dict[str, str] | None = None) -> int:
    log("$ " + " ".join(c if len(c) < 120 else c[:117] + "…" for c in cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        text=True, errors="replace", creationflags=no_window_flags(), env=env or clean_env(),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log(line)
    return proc.wait()


def install(
    info: host.HostInfo | None = None,
    report: Report | None = None,
    log: LogFn = print,
    gui: bool = False,
) -> InstallResult:
    info = info or host.detect()
    report = report or check(info)
    keys = {i.key for i in report.fixable}
    if not keys:
        return InstallResult(True, message="Alles ist bereits installiert.")

    reboot = False
    try:
        if info.os == "linux":
            user = os.environ.get("SUDO_USER") or getpass.getuser()
            script = linux_root_script(info, report, user, linux_package_manager())
            log("Installiere mit Administratorrechten (Passwortabfrage) …")
            if _run(_elevate_linux(script, gui), log) != 0:
                return InstallResult(False, message="Installation abgebrochen oder fehlgeschlagen.")

        elif info.os == "windows":
            if "qemu" in keys:
                if not shutil.which("winget"):
                    return InstallResult(False, message=(
                        "winget fehlt. Bitte den „App-Installer“ aus dem Microsoft Store installieren "
                        "oder QEMU manuell von https://qemu.weilnetz.de/w64/ installieren."
                    ))
                log("Installiere QEMU über winget (Windows fragt nach Zustimmung) …")
                code = _run(WINGET_QEMU, log)
                if code != 0 and not _qemu_present(info):
                    return InstallResult(False, message=f"QEMU-Installation fehlgeschlagen (Code {code}).")
            if "whpx" in keys:
                log("Schalte die Windows-Hypervisorplattform ein (Windows fragt nach Zustimmung) …")
                if _run(ENABLE_WHPX, log) != 0:
                    return InstallResult(False, message="Hypervisorplattform konnte nicht eingeschaltet werden.")
                reboot = True

        elif info.os == "macos":
            if keys & {"qemu", "firmware", "homebrew"}:
                brew = find_brew(info.arch)
                if not brew:
                    # Den Installer starten die Aufrufer (App: Terminal-Fenster, Kommandozeile: direkt),
                    # nachdem sie erklärt und gefragt haben – siehe HOMEBREW_EXPLANATION.
                    return InstallResult(False, message="Homebrew fehlt – bitte zuerst installieren (https://brew.sh).")
                if info.arch == "x86_64":
                    log(INTEL_QEMU_NOTE)
                log("Installiere QEMU über Homebrew …")
                if _run([str(brew), "install", "qemu"], log, env=_brew_env()) != 0:
                    return InstallResult(False, message="QEMU-Installation über Homebrew fehlgeschlagen.")
    except (OSError, RuntimeError) as e:
        return InstallResult(False, message=str(e))

    after = check(info)
    if reboot:
        return InstallResult(True, True, "Fertig. Bitte Windows einmal neu starten, damit die Beschleunigung wirkt.")
    if after.ok:
        return InstallResult(True, message="Alles installiert und bereit.")
    rest = " ".join(i.text for i in after.issues)
    return InstallResult(after.can_run, message=("Installiert, aber: " + rest) if after.can_run else rest)


def _qemu_present(info: host.HostInfo) -> bool:
    try:
        qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os)
        return True
    except qemu.QemuNotFound:
        return False
