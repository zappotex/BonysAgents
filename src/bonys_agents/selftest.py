# SPDX-License-Identifier: GPL-3.0-or-later
"""Selbsttest: startet QEMU auf genau demselben Weg wie die App und meldet klar OK oder Fehler.

Gedacht für Fehler, die nur auf manchen Systemen auftreten – z. B. wenn QEMU wegen
mitgelieferter Bibliotheken nicht startet. Läuft ohne Agent-PC und ohne Hardware-Beschleunigung
(auch in einem Container).
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bonys_agents import cloudinit, host, procutil, qemu
from bonys_agents.procutil import clean_env, no_window_flags


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def check_environment() -> Check:
    """Bekommen externe Programme die Umgebung ohne die Bibliothekspfade des Programmordners?"""
    if not procutil.is_frozen():
        return Check("Umgebung für externe Programme", True, "Quellcode-Installation – nichts zu bereinigen")
    env = clean_env()
    dirs = [d for d in procutil.bundle_dirs() if d]
    leaked = [k for k in (*procutil.LIBRARY_PATH_VARS, "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")
              if any(d in env.get(k, "") for d in dirs)]
    if leaked:
        return Check("Umgebung für externe Programme", False, "zeigt noch auf den Programmordner: " + ", ".join(leaked))
    return Check("Umgebung für externe Programme", True, "Bibliothekspfade des Programmordners werden zurückgesetzt")


def check_version(binary: Path) -> Check:
    name = f"{binary.name} --version"
    try:
        r = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=30,
                           creationflags=no_window_flags(), env=clean_env())
    except (OSError, subprocess.SubprocessError) as e:
        return Check(name, False, str(e))
    if r.returncode != 0:
        return Check(name, False, _tail(r.stderr or r.stdout) or f"Code {r.returncode}")
    return Check(name, True, _first_line(r.stdout))


def check_seed_iso(qemu_bin: Path, qemu_img: Path | None, workdir: Path) -> list[Check]:
    """Test-Seed-ISO schreiben, mit qemu-img prüfen und von QEMU öffnen lassen (CPU angehalten)."""
    checks: list[Check] = []
    iso = workdir / "selbsttest-seed.iso"
    try:
        cfg = cloudinit.GuestConfig(hostname="selbsttest", username="agent", password="selbsttest", apps=[])
        cloudinit.write_seed_iso(iso, cfg, instance_id="bonys-selbsttest")
    except Exception as e:  # noqa: BLE001 – jeder Fehler ist hier ein Testergebnis
        return [Check("Test-Seed-ISO schreiben", False, str(e))]
    checks.append(Check("Test-Seed-ISO schreiben", True, f"{iso.stat().st_size // 1024} KB"))
    if qemu_img:
        try:
            r = subprocess.run([str(qemu_img), "info", str(iso)], capture_output=True, text=True, timeout=30,
                               creationflags=no_window_flags(), env=clean_env())
            ok = r.returncode == 0 and "raw" in r.stdout
            checks.append(Check("qemu-img liest das Seed-ISO", ok,
                                "Format raw" if ok else _tail(r.stderr or r.stdout)))
        except (OSError, subprocess.SubprocessError) as e:
            checks.append(Check("qemu-img liest das Seed-ISO", False, str(e)))

    port = qemu.free_port()
    cmd = [str(qemu_bin), "-machine", "none", "-nodefaults", "-S", "-display", "none",
           "-drive", f"if=none,id=seed,file={qemu._esc(iso)},format=raw,readonly=on",
           "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off"]
    log = workdir / "qemu.log"
    name = f"{qemu_bin.name} öffnet das Seed-ISO"
    with log.open("w") as out:
        try:
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    creationflags=no_window_flags(), env=clean_env())
        except OSError as e:
            checks.append(Check(name, False, str(e)))
            return checks
        try:
            attached = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    with qemu.QMP(port, timeout=2) as q:
                        attached = q.execute("query-block")
                    break
                except (OSError, ConnectionError, ValueError):
                    time.sleep(0.2)
            if proc.poll() is not None:
                checks.append(Check(name, False, "QEMU ist sofort beendet:\n" + _tail(log.read_text(errors="replace"))))
            elif not attached:
                checks.append(Check(name, False, "QEMU antwortet nicht (QMP)"))
            else:
                files = [b.get("inserted", {}).get("file", "") for b in attached]
                ok = any(Path(f).name == iso.name for f in files)
                checks.append(Check(name, ok, "eingebunden" if ok else f"nicht eingebunden: {files}"))
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
    return checks


def check_boot(info: host.HostInfo, qemu_bin: Path, qemu_img: Path, workdir: Path, seconds: float = 5) -> Check:
    """Agent-PC-Start bis QEMU läuft: derselbe Startbefehl wie in der App (Firmware, Maschine, Beschleuniger).

    Mit einer leeren Platte – es bootet also kein System, aber QEMU muss Firmware und alle Geräte annehmen
    und ``seconds`` lang laufen. Gedacht für die Release-Tests (z. B. macOS mit Homebrew-QEMU).
    """
    name = f"Agent-PC starten ({info.arch}, {info.accel})"
    disk = workdir / "boot-test.qcow2"
    try:
        subprocess.run([str(qemu_img), "create", "-q", "-f", "qcow2", str(disk), "1G"], check=True,
                       capture_output=True, timeout=30, creationflags=no_window_flags(), env=clean_env())
        firmware = qemu.find_aarch64_firmware(qemu_bin) if info.arch == "aarch64" else None
    except (OSError, subprocess.SubprocessError, qemu.QemuNotFound) as e:
        return Check(name, False, str(e))
    port = qemu.free_port()
    spec = qemu.LaunchSpec(
        qemu_bin=qemu_bin, arch=info.arch, accel=info.accel, name="selbsttest", cpus=min(info.cpus, 2), ram_mb=1024,
        disk=disk, qmp_port=port, ssh_port=qemu.free_port(), serial_log=workdir / "console.log",
        pidfile=workdir / "qemu.pid", firmware=firmware, headless=True,
    )
    cmd = qemu.build_command(spec)
    log = workdir / "boot.log"
    with log.open("w") as out:
        try:
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    creationflags=no_window_flags(), env=clean_env())
        except OSError as e:
            return Check(name, False, str(e))
        try:
            status = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and proc.poll() is None and status is None:
                try:
                    with qemu.QMP(port, timeout=2) as q:
                        status = q.execute("query-status").get("status")
                except (OSError, ConnectionError, ValueError):
                    time.sleep(0.2)
            end = time.monotonic() + seconds
            while proc.poll() is None and time.monotonic() < end:
                time.sleep(0.2)
            if proc.poll() is not None:
                return Check(name, False, "QEMU ist beendet:\n" + _tail(log.read_text(errors="replace"))
                             + "\nBefehl: " + " ".join(cmd))
            detail = f"läuft ({status}) – {'Firmware ' + str(firmware) if firmware else 'BIOS von QEMU'}"
            return Check(name, status == "running", detail)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)


def check_qt() -> Check:
    """Lassen sich die Bibliotheken der Desktop-App laden (Qt mit den System-Bibliotheken)?"""
    try:
        from PySide6 import QtGui, QtWidgets  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return Check("Bibliotheken der Desktop-App (Qt)", False, str(e))
    from PySide6 import __version__ as pyside_version

    return Check("Bibliotheken der Desktop-App (Qt)", True, f"PySide6 {pyside_version}")


def run(log: Callable[[Check], None] | None = None, include_qt: bool = True, boot: bool = False) -> list[Check]:
    """Alle Prüfungen; ``log`` bekommt jedes Ergebnis sofort (für die Anzeige)."""
    results: list[Check] = []

    def add(c: Check) -> None:
        results.append(c)
        if log:
            log(c)

    info = host.detect()
    add(check_environment())
    binaries: dict[str, Path | None] = {}
    for name in (qemu.ARCH_BINARY[info.arch], "qemu-img"):
        try:
            binaries[name] = qemu.find_binary(name, info.os)
        except qemu.QemuNotFound as e:
            binaries[name] = None
            add(Check(f"{name} finden", False, str(e).splitlines()[0]))
            continue
        add(check_version(binaries[name]))
    qemu_bin = binaries.get(qemu.ARCH_BINARY[info.arch])
    if qemu_bin:
        with tempfile.TemporaryDirectory(prefix="bonys-selbsttest-") as tmp:
            for c in check_seed_iso(qemu_bin, binaries.get("qemu-img"), Path(tmp)):
                add(c)
            if boot and binaries.get("qemu-img"):
                add(check_boot(info, qemu_bin, binaries["qemu-img"], Path(tmp)))
    if include_qt:
        add(check_qt())
    return results


def passed(results: list[Check]) -> bool:
    return all(c.ok for c in results)
