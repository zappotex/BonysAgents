# SPDX-License-Identifier: GPL-3.0-or-later
"""QEMU finden, Startbefehl bauen und über QMP steuern."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from bonys_agents import screen as screen_cfg
from bonys_agents import x509
from bonys_agents.procutil import clean_env, no_window_flags
from bonys_agents.i18n import tr

ARCH_BINARY = {"x86_64": "qemu-system-x86_64", "aarch64": "qemu-system-aarch64"}

_EXTRA_DIRS = {
    "windows": [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "qemu"],
    "macos": [Path("/opt/homebrew/bin"), Path("/usr/local/bin")],
    "linux": [Path("/usr/bin"), Path("/usr/local/bin")],
}

INSTALL_HINTS = {
    "linux": "Debian/Ubuntu: sudo apt install qemu-system qemu-utils\n"
             "Fedora: sudo dnf install qemu-kvm qemu-img\n"
             "Arch: sudo pacman -S qemu-full",
    "macos": "brew install qemu",
    "windows": "winget install SoftwareFreedomConservancy.QEMU\n"
               "und für volle Geschwindigkeit die Windows-Funktion "
               "'Windows-Hypervisorplattform' aktivieren.",
}


# Das QEMU-Fenster öffnet sich in dieser Größe (bevorzugte Auflösung der virtuellen Grafikkarte).
SCREEN = screen_cfg.START_SIZE
NETDEV = "net0"
GUEST_RDP_PORT = 3389


class QemuNotFound(RuntimeError):
    pass


def find_binary(name: str, host_os: str) -> Path:
    exe = name + (".exe" if host_os == "windows" else "")
    found = shutil.which(exe)
    if found:
        return Path(found)
    for d in _EXTRA_DIRS.get(host_os, []):
        p = d / exe
        if p.exists():
            return p
    raise QemuNotFound(tr("{exe} nicht gefunden.\nInstallation:\n{wert}", exe=exe, wert=INSTALL_HINTS.get(host_os, '')))


def find_aarch64_firmware(qemu_bin: Path) -> Path:
    """UEFI-Firmware für ARM64-Gäste (nötig auf Apple Silicon)."""
    candidates = [
        qemu_bin.parent.parent / "share" / "qemu" / "edk2-aarch64-code.fd",   # Homebrew (…/bin → …/share)
        qemu_bin.resolve().parent.parent / "share" / "qemu" / "edk2-aarch64-code.fd",  # Homebrew-Cellar
        Path("/opt/homebrew/share/qemu/edk2-aarch64-code.fd"),                 # Homebrew, Apple-Chip
        Path("/usr/local/share/qemu/edk2-aarch64-code.fd"),                    # Homebrew, Intel
        qemu_bin.parent / "share" / "edk2-aarch64-code.fd",                   # Windows-Build
        Path("/usr/share/qemu/edk2-aarch64-code.fd"),
        Path("/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"),
        Path("/usr/share/AAVMF/AAVMF_CODE.fd"),
        Path("/usr/share/edk2/aarch64/QEMU_EFI.fd"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise QemuNotFound(tr("UEFI-Firmware für ARM64 (edk2-aarch64-code.fd) nicht gefunden"))


@dataclass
class LaunchSpec:
    qemu_bin: Path
    arch: str
    accel: str
    name: str
    cpus: int
    ram_mb: int
    disk: Path
    qmp_port: int
    ssh_port: int
    serial_log: Path
    pidfile: Path
    seed_iso: Path | None = None
    firmware: Path | None = None
    headless: bool = False
    # Fenster-Anzeige (gtk, cocoa, sdl). Muss ausdrücklich stehen: Mit -spice öffnet QEMU sonst kein Fenster.
    display: str | None = None
    screen: tuple[int, int] = SCREEN       # bevorzugte Auflösung beim Start = Größe des QEMU-Fensters
    screen_setting: str = screen_cfg.AUTO  # an den Gast (fw_cfg): auto, scale:BxH oder fixed:BxH
    qga_port: int | None = None            # QEMU Guest Agent (Befehle im Gast ohne SSH)
    # Steuerkanäle als Unix-Socket (Linux/macOS) statt TCP: Aus dem Agent-PC ist 127.0.0.1 des Hosts über
    # 10.0.2.2 erreichbar (QEMU-Benutzernetz) – ein TCP-Port für QMP oder den Gast-Agent wäre ein Weg aus der
    # VM hinaus. Gesetzt, gelten qmp_port/qga_port nicht.
    qmp_socket: Path | None = None
    qga_socket: Path | None = None
    # Ohne Unix-Sockets (Windows): QMP und Gast-Agent über TCP mit TLS – QEMU lässt nur herein, wer ein
    # Client-Zertifikat aus diesem Ordner hat (x509.make_control_tls). Ein Agent-PC hat es nicht.
    control_tls_dir: Path | None = None
    # Fernzugriff
    rdp_addr: str | None = None            # RDP-Weiterleitung schon beim Start (None = aus)
    rdp_port: int | None = None            # Host-Port → Gast 3389 (xrdp)
    spice_addr: str = "127.0.0.1"          # 0.0.0.0 = SPICE aus dem Heimnetz erreichbar
    spice_port: int | None = None          # None = kein SPICE
    spice_password_file: Path | None = None  # nötig, sobald SPICE an einem TCP-Port lauscht
    spice_socket: Path | None = None       # SPICE nur an diesem Rechner: Unix-Socket statt Port (Linux/macOS)
    audio: str | None = None               # audiodev-Treiber (spice, pipewire, pa, dsound, coreaudio …)
    # Netz abschotten: kein Internet und kein Zugriff auf den Host – nur die SSH-Weiterleitung bleibt
    # (z. B. beim Verallgemeinern für eine Vorlage, damit keine Sitzung des Originals online geht).
    restrict_net: bool = False
    # Weitere Weiterleitungen schon beim Start (Regeln wie bei hostfwd, z. B. Mission Control nur an 127.0.0.1)
    extra_forwards: tuple[str, ...] = ()
    # Nullen auf der Festplatte als „Null-Cluster“ speichern statt als Daten (Arbeitskopie für Vorlagen:
    # das Überschreiben des freien Platzes kostet so keinen Platz)
    zero_unmap: bool = False
    # Bildschirm zusätzlich per VNC – NUR lokal: „unix:PFAD“ (Linux/macOS) bzw. „127.0.0.1:N“ (Windows).
    # Für Schulungen (Vorführen, Hilfe-Modus); den Weg ins Netz übernimmt der Proxy in Bony's Agents.
    vnc: str | None = None


def _esc(p: Path) -> str:
    """Kommas in QEMU-Optionswerten verdoppeln."""
    return str(p).replace(",", ",,")


def build_command(s: LaunchSpec) -> list[str]:
    cmd: list[str] = [str(s.qemu_bin), "-name", s.name]

    # Beschleuniger: der beste zuerst, TCG (Software) als Rückfallebene.
    if s.accel == "tcg":
        cmd += ["-accel", "tcg,thread=multi"]
    elif s.accel == "whpx":
        cmd += ["-accel", "whpx,kernel-irqchip=off", "-accel", "tcg,thread=multi"]
    else:
        cmd += ["-accel", s.accel, "-accel", "tcg,thread=multi"]

    # EDID an: QEMU meldet jede neue Fenstergröße als bevorzugte Auflösung an den Gast.
    res = f"edid=on,xres={s.screen[0]},yres={s.screen[1]}"
    if s.arch == "aarch64":
        if s.firmware is None:
            raise ValueError(tr("ARM64 braucht UEFI-Firmware"))
        cmd += ["-machine", "virt", "-cpu", "host" if s.accel == "hvf" else "max",
                "-bios", str(s.firmware), "-device", f"virtio-gpu-pci,{res}"]
    else:
        cmd += ["-machine", "q35", "-cpu", "max", "-device", f"virtio-vga,{res}"]

    # Start nur von der Systemplatte: sie ist ausdrücklich das erste (und wegen strict=on einzige)
    # Startgerät. Die Netzwerkkarte bekommt kein Boot-ROM (romfile=) – sonst lädt die Firmware
    # iPXE und versucht unter Umständen erst einen Netzwerk-Start (PXE), bevor sie die Platte nimmt.
    cmd += [
        "-smp", str(s.cpus),
        "-m", str(s.ram_mb),
        "-boot", "strict=on,menu=off",
        "-drive", f"if=none,id=disk0,file={_esc(s.disk)},format=qcow2,discard=unmap"
                  + (",detect-zeroes=unmap" if s.zero_unmap else ""),
        "-device", "virtio-blk-pci,drive=disk0,bootindex=0",
        "-netdev", _netdev(s),
        "-device", f"virtio-net-pci,netdev={NETDEV},romfile=",
        "-device", "virtio-rng-pci",
        "-device", "qemu-xhci",
        "-device", "usb-tablet",
        "-device", "usb-kbd",
        *_qmp_args(s),
        "-serial", f"file:{s.serial_log}",
        "-pidfile", str(s.pidfile),
        # Anzeige-Einstellung für das Skript im Gast (bonys-screen)
        "-fw_cfg", f"name={screen_cfg.FW_CFG_NAME},string={s.screen_setting}",
    ]
    if s.seed_iso is not None:
        # Seed-ISO ohne bootindex: wird nie gestartet, cloud-init findet es über die Kennung „cidata“
        cmd += ["-drive", f"if=none,id=seed0,file={_esc(s.seed_iso)},format=raw,readonly=on",
                "-device", "virtio-blk-pci,drive=seed0"]
    if s.qga_socket or s.qga_port or s.spice_socket or s.spice_port:
        cmd += ["-device", "virtio-serial-pci"]
    if s.qga_socket or s.qga_port:
        # Kanal für qemu-guest-agent im Gast (nur von diesem Rechner aus erreichbar)
        where = f"path={_esc(s.qga_socket)}" if s.qga_socket else f"host=127.0.0.1,port={s.qga_port}"
        if s.control_tls_dir and not s.qga_socket:
            where += f",tls-creds={CONTROL_TLS}"
        cmd += [
            "-chardev", f"socket,id=qga0,{where},server=on,wait=off",
            "-device", f"virtserialport,chardev=qga0,name={GUEST_AGENT_CHANNEL}",
        ]
    if s.spice_socket or s.spice_port:
        if s.spice_socket:
            # Nur dieser Benutzer kann den Socket öffnen (Ordner 0700) – ohne Passwort, kein Weg aus dem Gast
            spice = f"unix=on,addr={_esc(s.spice_socket)},disable-ticketing=on"
        elif s.spice_password_file:
            cmd += ["-object", f"secret,id=spicepw,file={_esc(s.spice_password_file)}"]
            spice = f"port={s.spice_port},addr={s.spice_addr},password-secret=spicepw"
        else:
            # Ein TCP-Port ohne Passwort wäre aus jedem Agent-PC über 10.0.2.2 erreichbar
            raise ValueError(tr("SPICE an einem TCP-Port nur mit Passwort"))
        cmd += [
            "-spice", spice,
            # Kanal für spice-vdagent im Gast: Zwischenablage und automatische Bildschirmgröße
            "-chardev", "spicevmc,id=vdagent,name=vdagent",
            "-device", "virtserialport,chardev=vdagent,name=com.redhat.spice.0",
        ]
    if s.vnc:
        cmd += ["-vnc", vnc_option(s.vnc)]
    if s.audio:
        cmd += ["-audiodev", f"{s.audio},id=snd0", "-device", "ich9-intel-hda", "-device", "hda-duplex,audiodev=snd0"]
    if s.headless:
        cmd += ["-display", "none"]
    elif s.display:
        cmd += ["-display", s.display]
    return cmd


CONTROL_TLS = "bonysctl"


def _qmp_args(s: LaunchSpec) -> list[str]:
    """QEMU-Steuerung: Unix-Socket, sonst TCP an 127.0.0.1 – mit TLS und Client-Zertifikat, wenn möglich."""
    if s.qmp_socket:
        return ["-qmp", f"unix:{_esc(s.qmp_socket)},server=on,wait=off"]
    if s.control_tls_dir:
        return ["-object", f"tls-creds-x509,id={CONTROL_TLS},dir={_esc(s.control_tls_dir)},endpoint=server,"
                           "verify-peer=on",
                "-chardev", f"socket,id=qmp0,host=127.0.0.1,port={s.qmp_port},server=on,wait=off,"
                            f"tls-creds={CONTROL_TLS}",
                "-mon", "chardev=qmp0,mode=readline"]  # Text-Monitor: QMP über TLS bricht in QEMU 8.2 ab
    return ["-qmp", f"tcp:127.0.0.1:{s.qmp_port},server=on,wait=off"]


def vnc_option(target: str) -> str:
    """Wert für „-vnc“. Nie eine Adresse im Netz: nur Unix-Socket oder 127.0.0.1.

    share=force-shared: mehrere Zuschauer gleichzeitig, keiner wirft den anderen hinaus. lossy=on: JPEG
    (Tight) für Zuschauer im WLAN. Zwischenablage schickt QEMU nur an Clients mit „Extended Clipboard“ –
    das filtert der Proxy heraus (``rfb``).
    """
    if target.startswith("unix:"):
        where = "unix:" + _esc(Path(target[5:]))
    elif re.fullmatch(r"127\.0\.0\.1:\d{1,2}", target):
        where = target
    else:
        raise ValueError(tr("VNC nur lokal (unix:… oder 127.0.0.1:N), nicht {target}", target=target))
    return f"{where},share=force-shared,lossy=on"


def free_vnc_display(first: int = 5900, last: int = 5999) -> int:
    """Freie VNC-Anzeigenummer an 127.0.0.1 (Port = 5900 + N) – für Windows ohne Unix-Socket."""
    for port in range(first, last + 1):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port - 5900
    raise RuntimeError(tr("Kein freier VNC-Port zwischen 5900 und 5999"))


def _netdev(s: LaunchSpec) -> str:
    """Netzwerk: SSH immer nur lokal, RDP nur bei eingeschaltetem Fernzugriff."""
    net = f"user,id={NETDEV},hostfwd=tcp:127.0.0.1:{s.ssh_port}-:22"
    if s.restrict_net:
        net += ",restrict=on"
    if s.rdp_port and s.rdp_addr:
        net += f",hostfwd={rdp_forward(s.rdp_addr, s.rdp_port)}"
    for rule in s.extra_forwards:
        net += f",hostfwd={rule}"
    return net


def rdp_forward(addr: str, port: int) -> str:
    """Regel für die RDP-Weiterleitung, wie sie hostfwd bzw. hostfwd_add erwartet."""
    return f"tcp:{addr}:{port}-:{GUEST_RDP_PORT}"


# ---------------------------------------------------------------- Fähigkeiten des QEMU-Builds
_caps_cache: dict[str, dict] = {}


def capabilities(qemu_bin: Path, cache_file: Path | None = None) -> dict:
    """Kann dieser QEMU-Build SPICE, und welche Audio-Treiber hat er?

    SPICE fehlt oft (Windows-Builds, Homebrew). Ein kurzer Probelauf mit angehaltener CPU
    und ohne Festplatte ist die verlässlichste Prüfung. Ergebnis wird je Binärdatei gemerkt.
    """
    try:
        key = f"{qemu_bin}:{qemu_bin.stat().st_mtime_ns}"
    except OSError:
        key = str(qemu_bin)
    if key in _caps_cache:
        return _caps_cache[key]
    if cache_file:
        try:
            stored = json.loads(cache_file.read_text("utf-8"))
            if stored.get("key") == key and "tls" in stored.get("caps", {}):
                _caps_cache[key] = stored["caps"]
                return stored["caps"]
        except (OSError, ValueError, KeyError):
            pass
    caps = {"spice": _probe_spice(qemu_bin), "audio": _audio_drivers(qemu_bin),
            "displays": _help_list(qemu_bin, "-display"),
            # TLS nur nötig, wo es keine Unix-Sockets gibt (Windows) – spart sonst den Probelauf
            "tls": not hasattr(socket, "AF_UNIX") and _probe_tls(qemu_bin)}
    _caps_cache[key] = caps
    if cache_file:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"key": key, "caps": caps}), "utf-8")
        except OSError:
            pass
    return caps


def _audio_drivers(qemu_bin: Path) -> list[str]:
    return _help_list(qemu_bin, "-audiodev")


def _help_list(qemu_bin: Path, option: str) -> list[str]:
    """Liste aus „qemu … <option> help“ (Audio-Treiber, Anzeigen …)."""
    try:
        out = subprocess.run([str(qemu_bin), option, "help"], capture_output=True, text=True,
                             timeout=10, creationflags=no_window_flags(), env=clean_env()).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines()[1:] if line.strip() and " " not in line.strip()]


def window_display(host_os: str, available: list[str], mode: str = screen_cfg.AUTO) -> str | None:
    """Anzeige für das QEMU-Fenster. None = QEMU entscheidet (nur wenn die Liste fehlt)."""
    prefer = ["cocoa", "sdl"] if host_os == "macos" else ["gtk", "sdl"]
    chosen = next((d for d in prefer if d in available), None)
    if chosen == "gtk":
        return "gtk," + screen_cfg.gtk_options(mode)
    if chosen == "cocoa" and mode == screen_cfg.SCALE:
        return "cocoa,zoom-to-fit=on"
    return chosen


def _probe_spice(qemu_bin: Path) -> bool:
    cmd = [
        str(qemu_bin), "-S", "-nodefaults", "-machine", "none", "-display", "none",
        "-spice", f"port={free_port()},addr=127.0.0.1,disable-ticketing=on",
        "-chardev", "spicevmc,id=vdagent,name=vdagent",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, creationflags=no_window_flags(), env=clean_env())
    except OSError:
        return False
    try:
        proc.wait(timeout=1.5)
        return False  # sofort beendet = Option unbekannt bzw. Modul fehlt
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return True  # läuft = SPICE funktioniert


def _probe_tls(qemu_bin: Path) -> bool:
    """Kann dieser QEMU-Build TLS (gnutls)? „tls-creds-*“ steht auch ohne gnutls in der Liste – darum ausprobieren."""
    cmd = [str(qemu_bin), "-S", "-nodefaults", "-machine", "none", "-display", "none", "-monitor", "none",
           "-object", "tls-creds-anon,id=t,endpoint=server"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, creationflags=no_window_flags(), env=clean_env())
    except OSError:
        return False
    try:
        proc.wait(timeout=1.5)
        return False  # sofort beendet = ohne gnutls gebaut
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return True


def host_audio_driver(host_os: str, available: list[str]) -> str | None:
    """Passender Audio-Treiber für das lokale QEMU-Fenster."""
    if host_os == "linux":
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        prefer = ["pipewire", "pa", "alsa"] if runtime and Path(runtime, "pipewire-0").exists() else ["pa", "alsa"]
    elif host_os == "windows":
        prefer = ["dsound"]
    elif host_os == "macos":
        prefer = ["coreaudio"]
    else:
        prefer = []
    return next((d for d in prefer if d in available), None)


def create_disk(qemu_img: Path, base_image: Path, disk: Path, size_gb: int) -> None:
    """Eigene qcow2-Platte als Kopie des Basis-Images, auf Zielgröße vergrößert.

    Dynamisch: belegt auf dem Host nur so viel, wie im Gast genutzt wird.
    """
    disk.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(qemu_img), "convert", "-O", "qcow2", str(base_image), str(disk)],
        check=True, capture_output=True, creationflags=no_window_flags(), env=clean_env(),
    )
    resize_disk(qemu_img, disk, size_gb)


def resize_disk(qemu_img: Path, disk: Path, size_gb: int) -> None:
    """Virtuelle Festplatte auf ``size_gb`` vergrößern."""
    subprocess.run(
        [str(qemu_img), "resize", str(disk), f"{size_gb}G"],
        check=True, capture_output=True, creationflags=no_window_flags(), env=clean_env(),
    )


def create_overlay(qemu_img: Path, backing: Path, disk: Path, size_gb: int | None = None,
                   relative: bool = False) -> None:
    """Überlagerung (qcow2 mit Backing-File): liest aus ``backing``, schreibt nur in ``disk``.

    ``relative``: Pfad zum Backing-File relativ zu ``disk`` speichern – übersteht einen anderen
    Laufwerksbuchstaben bzw. Einhängepunkt, solange beide auf demselben Laufwerk bleiben.
    """
    disk.parent.mkdir(parents=True, exist_ok=True)
    ref = os.path.relpath(backing, disk.parent) if relative else str(Path(backing).resolve())
    cmd = [str(qemu_img), "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", ref, str(disk)]
    if size_gb:
        cmd.append(f"{size_gb}G")
    _run_img(cmd)


def convert_disk(qemu_img: Path, src: Path, dst: Path, compress: bool = False,
                 progress=None) -> None:
    """``src`` (samt Backing-Kette) in eine eigenständige qcow2-Datei schreiben.

    Nullbereiche werden übersprungen. ``compress``: komprimiert (zstd, sonst zlib) – für Vorlagen.
    ``progress(frac)`` bekommt den Fortschritt 0..1.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    # -m/-W: mehrere Anfragen parallel, Schreiben in beliebiger Reihenfolge (Ziel ist eine neue Datei)
    base = [str(qemu_img), "convert", "-p", "-m", "8", "-W", "-O", "qcow2"]
    variants = [base + ["-c", "-o", "compression_type=zstd"], base + ["-c"]] if compress else [base]
    err = ""
    for cmd in variants:
        dst.unlink(missing_ok=True)
        rc, err = _run_with_progress(cmd + [str(src), str(dst)], progress)
        if rc == 0:
            return
    dst.unlink(missing_ok=True)
    raise RuntimeError(tr("qemu-img convert fehlgeschlagen: {wert}", wert=err.strip()[-400:]))


_PROGRESS_RE = re.compile(rb"\((\d+(?:\.\d+)?)/100%\)")


def _run_with_progress(cmd: list[str], progress) -> tuple[int, str]:
    """qemu-img mit ``-p`` ausführen und dessen Fortschritt „(12.34/100%)“ weiterreichen."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=no_window_flags(), env=clean_env())
    buf = b""
    try:
        while True:
            chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(64)
            if not chunk:
                break
            buf = (buf + chunk)[-200:]
            found = _PROGRESS_RE.findall(buf)
            if found and progress:
                progress(min(float(found[-1]) / 100, 1.0))
    except BaseException:
        # Abbruch (z. B. aus ``progress``): qemu-img nicht weiterlaufen lassen
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read().decode("utf-8", errors="replace")
    return proc.wait(), err


def check_disk(qemu_img: Path, disk: Path) -> None:
    """Konsistenz prüfen (qemu-img check) – RuntimeError bei Fehlern."""
    proc = subprocess.run([str(qemu_img), "check", "-q", str(disk)], capture_output=True, text=True,
                          creationflags=no_window_flags(), env=clean_env())
    # Code 3 = nur „verwaiste Cluster“ (verschwendeter Platz, keine Datenfehler)
    if proc.returncode not in (0, 3):
        raise RuntimeError(tr("Festplattenabbild {name} ist beschädigt (qemu-img check, Code {returncode}): {wert}",
                              name=disk.name, returncode=proc.returncode,
                              wert=(proc.stdout + proc.stderr).strip()[-400:]))


def rebase(qemu_img: Path, disk: Path, backing: Path | None, unsafe: bool = False, progress=None) -> None:
    """Backing-File ändern. ``backing=None``: alle Daten übernehmen → eigenständige Festplatte.

    ``unsafe``: nur den Verweis umschreiben (wenn die Datei nur woanders liegt, aber gleich ist);
    der Pfad wird dann relativ zu ``disk`` gespeichert.
    """
    cmd = [str(qemu_img), "rebase", "-p", "-f", "qcow2"]
    if unsafe:
        cmd.append("-u")
    if backing is None:
        cmd += ["-b", ""]
    else:
        cmd += ["-F", "qcow2", "-b", os.path.relpath(backing, disk.parent) if unsafe else str(backing)]
    rc, err = _run_with_progress(cmd + [str(disk)], progress)
    if rc != 0:
        raise RuntimeError(tr("qemu-img rebase fehlgeschlagen: {wert}", wert=err.strip()[-400:]))


def virtual_size(qemu_img: Path, disk: Path) -> int:
    """Virtuelle Größe in Bytes (qemu-img info)."""
    out = _run_img([str(qemu_img), "info", "--output=json", str(disk)])
    return int(json.loads(out)["virtual-size"])


def _run_img(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=no_window_flags(), env=clean_env())
    if proc.returncode != 0:
        raise RuntimeError(tr("{name} {wert} fehlgeschlagen: {wert2}", name=Path(cmd[0]).name, wert=cmd[1],
                              wert2=proc.stderr.strip()[-400:]))
    return proc.stdout


def backing_file(disk: Path) -> Path | None:
    """Backing-File laut qcow2-Kopf (ohne qemu-img – schnell genug für jede Statusabfrage).

    Relative Angaben gelten relativ zum Ordner von ``disk``. None = eigenständige Festplatte.
    """
    try:
        with open(disk, "rb") as f:
            head = f.read(20)
            if len(head) < 20 or head[:4] != b"QFI\xfb":
                return None
            offset = int.from_bytes(head[8:16], "big")
            size = int.from_bytes(head[16:20], "big")
            if not offset or not size or size > 4096:
                return None
            f.seek(offset)
            name = f.read(size).decode("utf-8", errors="replace")
    except OSError:
        return None
    p = Path(name)
    return p if p.is_absolute() else disk.parent / p


_QCOW2_DATA_FILE_BIT = 1 << 2      # incompatible_features: Daten liegen in einer externen Datei
_EXT_DATA_FILE = 0x44415441        # Kopf-Erweiterung „Name der externen Datei“
_EXT_BACKING_FORMAT = 0xE2792ACA   # Kopf-Erweiterung „Format der Backing-Datei“
_PROTOCOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+:")  # json:, nbd:, http: … (nicht „C:“)


def _qcow2_header(disk: Path) -> dict:
    """Die sicherheitsrelevanten Teile des qcow2-Kopfs – ValueError, wenn es kein qcow2 ist."""
    with open(disk, "rb") as f:
        head = f.read(104)
        if len(head) < 72 or head[:4] != b"QFI\xfb":
            raise ValueError(tr("{name} ist kein qcow2-Festplattenabbild.", name=disk.name))
        version = int.from_bytes(head[4:8], "big")
        if version not in (2, 3):
            raise ValueError(tr("{name}: unbekannte qcow2-Version {version}.", name=disk.name, version=version))
        offset, size = int.from_bytes(head[8:16], "big"), int.from_bytes(head[16:20], "big")
        backing = None
        if offset and size:
            if size > 1023:
                raise ValueError(tr("{name}: ungültiger Verweis auf eine Backing-Datei.", name=disk.name))
            f.seek(offset)
            backing = f.read(size).decode("utf-8", errors="replace")
        incompatible, ext_start = 0, 72
        if version == 3:
            if len(head) < 104:
                raise ValueError(tr("{name}: qcow2-Kopf ist zu kurz.", name=disk.name))
            incompatible = int.from_bytes(head[72:80], "big")
            ext_start = int.from_bytes(head[100:104], "big")
        extensions: dict[int, bytes] = {}
        f.seek(ext_start)
        for _ in range(64):
            raw = f.read(8)
            if len(raw) < 8:
                break
            typ, length = int.from_bytes(raw[:4], "big"), int.from_bytes(raw[4:], "big")
            if typ == 0:
                break
            if length > 65536:
                raise ValueError(tr("{name}: ungültige qcow2-Kopferweiterung.", name=disk.name))
            extensions[typ] = f.read(length)
            f.seek((8 - length % 8) % 8, os.SEEK_CUR)
    return {"backing": backing, "incompatible": incompatible, "extensions": extensions}


def check_disk_safe(disk: Path, allow_backing: bool = False, require_qcow2: bool = True) -> None:
    """Festplatte darf nur aus sich selbst (und ggf. einer Vorlage) lesen – ValueError sonst.

    Abgelehnt werden eine externe Datendatei (``data_file``, könnte auf beliebige Dateien des Rechners zeigen),
    Backing-Verweise mit Protokoll (``json:``, ``nbd:`` …), Backing-Formate außer qcow2 und – ohne
    ``allow_backing`` – jede Backing-Datei. Bei erlaubter Backing-Datei wird die ganze Kette geprüft;
    jede Datei darin muss ein qcow2-Abbild sein. Läuft ohne qemu-img, also bevor QEMU die Datei öffnet.
    ``require_qcow2=False``: ist ``disk`` selbst kein qcow2, nichts prüfen (QEMU öffnet sie nur als qcow2).
    """
    seen: set[Path] = set()
    current = Path(disk)
    if not require_qcow2:
        with open(disk, "rb") as f:
            if f.read(4) != b"QFI\xfb":
                return
    for _ in range(16):
        h = _qcow2_header(current)
        if h["incompatible"] & _QCOW2_DATA_FILE_BIT or _EXT_DATA_FILE in h["extensions"]:
            raise ValueError(tr("{name} verweist auf eine externe Datendatei – so eine Festplatte könnte Dateien "
                                "deines Rechners lesen und wird nicht verwendet.", name=current.name))
        name = h["backing"]
        if name is None:
            return
        if not allow_backing:
            raise ValueError(tr("{name} ist nicht eigenständig (verweist auf {name2}).", name=current.name, name2=name))
        fmt = h["extensions"].get(_EXT_BACKING_FORMAT)
        if "\0" in name or _PROTOCOL_RE.match(name) or (fmt is not None and fmt.rstrip(b"\0") != b"qcow2"):
            raise ValueError(tr("{name} hat einen unzulässigen Verweis auf eine Backing-Datei: {name2}",
                                name=current.name, name2=name))
        p = Path(name)
        nxt = (p if p.is_absolute() else current.parent / p).resolve()
        if nxt in seen:
            raise ValueError(tr("{name}: Backing-Dateien verweisen im Kreis.", name=current.name))
        seen.add(nxt)
        if not nxt.exists():
            return  # fehlende Vorlage meldet der Aufrufer verständlicher
        current = nxt
    raise ValueError(tr("{name}: zu viele verschachtelte Backing-Dateien.", name=disk.name))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def endpoint(socket_path: Path | None, port: int | None, tls_dir: Path | None = None) -> str:
    """Adresse eines Steuerkanals für runtime.json: „unix:PFAD“, „tls:PORT:ORDNER“ oder „tcp:127.0.0.1:PORT“."""
    if socket_path:
        return f"unix:{socket_path}"
    if tls_dir:
        return f"tls:{port or 0}:{tls_dir}"
    return f"tcp:127.0.0.1:{port or 0}"


def runtime_target(rt: dict, kind: str) -> str | int | None:
    """Adresse des Steuerkanals ``kind`` („qmp“ oder „qga“) aus runtime.json – bis 0.19 nur eine Portnummer."""
    return rt.get(kind) or rt.get(f"{kind}_port")


def connect_local(target: int | str | None, timeout: float = 5.0) -> socket.socket:
    """Verbindung zu einem lokalen Steuerkanal: „unix:PFAD“, „tcp:127.0.0.1:PORT“ oder (bis 0.19) eine Portnummer.

    Nie zu einer anderen Adresse als 127.0.0.1 – runtime.json könnte von einem fremden Laufwerk stammen.
    """
    if isinstance(target, str) and target.startswith("unix:"):
        if not hasattr(socket, "AF_UNIX"):
            raise ConnectionRefusedError(tr("Unix-Sockets gibt es auf diesem System nicht"))
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(target[5:])
        except OSError:
            sock.close()
            raise
        return sock
    tls_dir = None
    if isinstance(target, str) and target.startswith("tls:"):
        port_text, _, folder = target[4:].partition(":")
        port, tls_dir = (int(port_text) if port_text.isdigit() else 0), Path(folder)
    elif isinstance(target, str):
        m = re.fullmatch(r"tcp:127\.0\.0\.1:(\d{1,5})", target)
        port = int(m.group(1)) if m else 0
    else:
        port = target if isinstance(target, int) and not isinstance(target, bool) else 0
    if not 0 < port < 65536:
        raise ConnectionRefusedError(tr("Kein Steuerkanal bekannt (läuft der Agent-PC?)"))
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    if tls_dir is None:
        return sock
    try:
        return x509.control_client_context(tls_dir).wrap_socket(sock, server_hostname="127.0.0.1")
    except (OSError, ValueError):
        sock.close()
        raise


# Befehle, die Bony's Agents im Betrieb braucht – über den Text-Monitor (HMP) beim TLS-Kanal
_HMP_COMMANDS = {
    "system_powerdown": lambda a: "system_powerdown",
    "quit": lambda a: "quit",
    "expire_password": lambda a: f"expire_password {a['protocol']} {a['time']}",
}
_HMP_PROMPT = b"(qemu) "
_ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


class QMP:
    """Minimaler Client für das QEMU Machine Protocol.

    Beim TLS-Kanal (Windows, „tls:…“) spricht QEMU stattdessen den Text-Monitor (HMP): QMP über eine
    TLS-Verbindung bricht in QEMU 8.2 nach dem ersten Befehl ab, HMP nicht. Nach außen gleich – ``execute`` kennt
    dann die Befehle aus ``_HMP_COMMANDS`` und „human-monitor-command“.
    """

    def __init__(self, target: int | str | None, timeout: float = 5.0):
        self.sock = connect_local(target, timeout)
        try:
            self.file = self.sock.makefile("rwb")
            self.text = isinstance(target, str) and target.startswith("tls:")
            if self.text:
                self._until_prompt()  # Begrüßung
                return
            self._read()  # Begrüßung
            self.execute("qmp_capabilities")
        except BaseException:
            _schliessen(self)
            raise

    def _until_prompt(self) -> str:
        buf = b""
        while not _ANSI.sub(b"", buf).endswith(_HMP_PROMPT):
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError(tr("Monitor-Verbindung geschlossen"))
            buf += chunk
            if len(buf) > 1_000_000:
                raise ConnectionError(tr("Monitor antwortet unerwartet"))
        text = _ANSI.sub(b"", buf)[: -len(_HMP_PROMPT)].replace(b"\r", b"")
        return text.decode("utf-8", errors="replace")

    def _text_command(self, line: str) -> str:
        if "\n" in line or "\r" in line:
            raise ValueError(tr("Monitor-Befehl mit Zeilenumbruch"))
        self.sock.sendall(line.encode() + b"\n")
        out = self._until_prompt()
        # Der Monitor wiederholt die Eingabe – nur die Ausgabe danach zurückgeben
        first, _, rest = out.partition("\n")
        return rest if line in first else out

    def _read(self) -> dict:
        while True:
            line = self.file.readline()
            if not line:
                raise ConnectionError(tr("QMP-Verbindung geschlossen"))
            msg = json.loads(line)
            if "event" not in msg:
                return msg

    def execute(self, command: str, **arguments) -> dict:
        if self.text:
            if command == "human-monitor-command":
                return self._text_command(arguments["command-line"])
            if command not in _HMP_COMMANDS:
                raise RuntimeError(tr("{command} geht über den TLS-Kanal nicht", command=command))
            try:
                out = self._text_command(_HMP_COMMANDS[command](arguments)).strip()
            except ConnectionError:
                if command == "quit":
                    return {}  # QEMU beendet sich, bevor die Eingabeaufforderung kommt
                raise
            if out:
                raise RuntimeError(out)
            return {}
        payload = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        self.file.write(json.dumps(payload).encode() + b"\n")
        self.file.flush()
        reply = self._read()
        if "error" in reply:
            raise RuntimeError(reply["error"].get("desc", str(reply["error"])))
        return reply.get("return", {})

    def hmp(self, command_line: str) -> str:
        """Befehl des menschenlesbaren Monitors (z. B. hostfwd_add) – gibt dessen Ausgabe zurück."""
        return self.execute("human-monitor-command", **{"command-line": command_line}) or ""

    def hostfwd_add(self, rule: str) -> None:
        """Port-Weiterleitung zur Laufzeit einrichten (kein Neustart nötig)."""
        out = self.hmp(f"hostfwd_add {NETDEV} {rule}").strip()
        if out:  # Erfolg = keine Ausgabe
            raise RuntimeError(tr("Weiterleitung {rule} nicht möglich: {out}", rule=rule, out=out))

    def hostfwd_remove(self, rule: str) -> None:
        """Port-Weiterleitung entfernen; „nicht gefunden“ ist auch in Ordnung."""
        host_part = rule.rsplit("-", 1)[0]  # tcp:0.0.0.0:3390
        self.hmp(f"hostfwd_remove {NETDEV} {host_part}")

    def close(self) -> None:
        try:
            self.file.close()
        finally:
            self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _schliessen(client) -> None:
    """Verbindung eines halb aufgebauten Clients schließen – erst die Datei aus makefile(), sonst bleibt der
    Socket offen."""
    file = getattr(client, "file", None)
    try:
        if file is not None:
            file.close()
    except OSError:
        pass
    finally:
        client.sock.close()


# ---------------------------------------------------------------- QEMU Guest Agent
GUEST_AGENT_CHANNEL = "org.qemu.guest_agent.0"


class GuestAgentError(RuntimeError):
    """Gast-Agent nicht erreichbar (z. B. Gast bootet noch oder älterer Start ohne Kanal)."""


class GuestAgent:
    """Minimaler Client für qemu-guest-agent – führt Befehle als root im Gast aus."""

    def __init__(self, target: int | str | None, timeout: float = 5.0):
        try:
            self.sock = connect_local(target, timeout)
        except (OSError, ValueError) as e:
            raise GuestAgentError(tr("Gast-Agent nicht erreichbar ({e})", e=e)) from None
        try:
            self.file = self.sock.makefile("rwb")
            self._sync()
        except BaseException as e:
            # Sofort schließen: QEMU nimmt immer nur eine Verbindung an. Bleibt diese offen (z. B. nach einem Timeout,
            # weil gerade ein anderer Client verbunden war), nimmt QEMU sie später an – und blockiert alle anderen.
            _schliessen(self)
            if isinstance(e, (OSError, ValueError)):
                raise GuestAgentError(tr("Gast-Agent nicht erreichbar ({e})", e=e)) from None
            raise

    def _send(self, command: str, **arguments) -> None:
        payload = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        self.file.write(json.dumps(payload).encode() + b"\n")
        self.file.flush()

    def _read(self) -> dict:
        line = self.file.readline()
        if not line:
            raise GuestAgentError(tr("Verbindung zum Gast-Agent geschlossen"))
        return json.loads(line.lstrip(b"\xff"))

    def _sync(self) -> None:
        # Antworten früherer, abgebrochener Verbindungen verwerfen (Protokoll von qemu-ga).
        token = secrets.randbelow(2**31)
        self.file.write(b"\xff")
        self._send("guest-sync-delimited", id=token)
        while True:
            line = self.file.readline()
            if not line:
                raise GuestAgentError(tr("Verbindung zum Gast-Agent geschlossen"))
            try:
                msg = json.loads(line.lstrip(b"\xff"))
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("return") == token:
                return

    def execute(self, command: str, **arguments):
        try:
            self._send(command, **arguments)
            reply = self._read()
        except (OSError, ValueError) as e:
            raise GuestAgentError(tr("Gast-Agent antwortet nicht ({e})", e=e)) from None
        if "error" in reply:
            raise RuntimeError(reply["error"].get("desc", str(reply["error"])))
        return reply.get("return")

    def shutdown(self) -> None:
        """Gast herunterfahren (systemctl poweroff). qemu-ga antwortet darauf nicht – nicht warten."""
        try:
            self._send("guest-shutdown", mode="powerdown")
        except (OSError, ValueError) as e:
            raise GuestAgentError(tr("Gast-Agent antwortet nicht ({e})", e=e)) from None

    def run(self, script: str, timeout: float = 120, shell: str = "/bin/sh", poll=None) -> tuple[int, str]:
        """Shell-Skript im Gast ausführen. Gibt (Exit-Code, Ausgabe) zurück."""
        rc, out, err = self.exec(shell, ["-c", script], timeout=timeout, poll=poll)
        return rc, out + err

    def exec(self, path: str, args: list[str], stdin: bytes | None = None,
             timeout: float = 120, poll=None) -> tuple[int, str, str]:
        """Programm im Gast ausführen, ``stdin`` geht über die Standardeingabe (landet in keiner Datei).

        ``poll()`` wird beim Warten regelmäßig aufgerufen – eine Ausnahme daraus bricht das Warten ab
        (z. B. „Abbrechen“ in der Oberfläche). Gibt (Exit-Code, stdout, stderr) zurück.
        """
        extra = {"capture-output": True}
        if stdin is not None:
            extra["input-data"] = base64.b64encode(stdin).decode("ascii")
        pid = self.execute("guest-exec", path=path, arg=args, **extra)["pid"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.execute("guest-exec-status", pid=pid)
            if st.get("exited"):
                out, err = (base64.b64decode(st.get(k, "")).decode("utf-8", errors="replace")
                            for k in ("out-data", "err-data"))
                return int(st.get("exitcode", 0)), out, err
            if poll:
                poll()
            time.sleep(0.2)
        raise GuestAgentError(tr("Befehl im Gast nicht innerhalb von {timeout:.0f} s fertig", timeout=timeout))

    def close(self) -> None:
        try:
            self.file.close()
        finally:
            self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
