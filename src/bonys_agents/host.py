# SPDX-License-Identifier: GPL-3.0-or-later
"""Erkennt das Host-System: Betriebssystem, CPU-Architektur, Kerne, RAM, Beschleuniger."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass

import psutil

from bonys_agents.procutil import clean_env, no_window_flags

MB = 1024 * 1024
# Mindestreserve für den Host, damit er nicht einfriert.
MIN_HOST_RESERVE_MB = 3072
HOST_RESERVE_FRACTION = 0.25
MIN_VM_RAM_MB = 2048


@dataclass(frozen=True)
class HostInfo:
    os: str            # "linux" | "macos" | "windows"
    arch: str          # "x86_64" | "aarch64"
    cpus: int
    ram_mb: int
    accel: str         # "kvm" | "hvf" | "whpx" | "tcg"

    @property
    def default_vm_cpus(self) -> int:
        return self.cpus

    @property
    def max_vm_ram_mb(self) -> int:
        reserve = max(int(self.ram_mb * HOST_RESERVE_FRACTION), MIN_HOST_RESERVE_MB)
        return max(self.ram_mb - reserve, MIN_VM_RAM_MB)

    @property
    def default_vm_ram_mb(self) -> int:
        return self.max_vm_ram_mb

    @property
    def accel_is_fast(self) -> bool:
        return self.accel != "tcg"


def detect_os() -> str:
    s = platform.system().lower()
    if s.startswith("darwin"):
        return "macos"
    if s.startswith("win"):
        return "windows"
    return "linux"


def _sysctl(name: str) -> str:
    """Wert eines macOS-sysctl als Text ('' wenn unbekannt)."""
    try:
        return subprocess.run(
            ["/usr/sbin/sysctl", "-n", name], capture_output=True, text=True, timeout=5, env=clean_env(),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def macos_rosetta() -> bool:
    """Läuft die Intel-Version der App per Rosetta auf einem Mac mit Apple-Chip?"""
    return detect_os() == "macos" and _sysctl("sysctl.proc_translated") == "1"


def detect_arch() -> str:
    """Architektur der Hardware.

    Auf dem Mac zählt der Chip, nicht die App: Läuft die Intel-Version per Rosetta auf einem Apple-Chip,
    sollen trotzdem das native QEMU, das ARM64-Image und HVF verwendet werden.
    """
    m = platform.machine().lower()
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        return "aarch64"
    if m == "x86_64" and detect_os() == "macos" and _sysctl("hw.optional.arm64") == "1":
        return "aarch64"
    return "x86_64"


def macos_chip_name(arch: str) -> str:
    return "Apple-Chip (arm64)" if arch == "aarch64" else "Intel (x86_64)"


def detect_accel(os_name: str) -> str:
    """Wählt den schnellsten verfügbaren Hardware-Beschleuniger."""
    if os_name == "linux":
        return "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"
    if os_name == "macos":
        # Hypervisor.framework (HVF). In virtualisierten Macs (z. B. GitHub-Runnern) meist 0.
        return "hvf" if _sysctl("kern.hv_support") == "1" else "tcg"
    if os_name == "windows":
        return "whpx" if _windows_hypervisor_platform_enabled() else "tcg"
    return "tcg"


def windows_hypervisor_state() -> str:
    """'enabled', 'disabled' oder 'unknown' – funktioniert ohne Admin-Rechte."""
    try:
        out = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_OptionalFeature -Filter \"Name='HypervisorPlatform'\").InstallState",
            ],
            capture_output=True, text=True, timeout=30, creationflags=no_window_flags(), env=clean_env(),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return {"1": "enabled", "2": "disabled"}.get(out, "unknown")


def _windows_hypervisor_platform_enabled() -> bool:
    # Bei 'unknown' optimistisch WHPX versuchen – QEMU fällt sonst auf TCG zurück (siehe qemu.py).
    return windows_hypervisor_state() != "disabled"


def detect() -> HostInfo:
    os_name = detect_os()
    return HostInfo(
        os=os_name,
        arch=detect_arch(),
        cpus=psutil.cpu_count(logical=True) or os.cpu_count() or 2,
        ram_mb=int(psutil.virtual_memory().total / MB),
        accel=detect_accel(os_name),
    )
