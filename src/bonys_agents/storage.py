# SPDX-License-Identifier: GPL-3.0-or-later
"""Speicherorte: Wo liegen die Agent-PCs?

Ein *Speicherort* ist ein Ordner, in dem jeder Agent-PC einen eigenen Unterordner hat,
z. B. ``E:\\BonysAgents\\mein-agent\\`` oder ``/media/bony/SSD/BonysAgents/mein-agent/``.

- Der Standard-Speicherort liegt im Benutzerprofil des Hauptsystems.
- Auf jedem Laufwerk wird ein Ordner ``BonysAgents`` im Wurzelverzeichnis automatisch
  erkannt. So findet die App Agent-PCs auf einer SSD wieder – auch an einem anderen PC
  oder wenn Windows einen anderen Laufwerksbuchstaben vergibt.
- Weitere Ordner können über „Vorhandenen hinzufügen“ eingetragen werden.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import psutil

from bonys_agents import APP_ID

LIBRARY_DIRNAME = "BonysAgents"
GB = 1024 ** 3

# Dateisysteme ohne Dateien > 4 GB – dort passt keine VM-Festplatte hin.
FAT_TYPES = {"vfat", "msdos", "fat", "fat16", "fat32", "umsdos"}
_SKIP_FSTYPES = {"squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660", "udf", "proc", "sysfs", "nsfs", "autofs"}
_SKIP_PREFIXES = ("/snap", "/boot", "/var/lib/docker", "/var/snap", "/run/user", "/proc", "/sys", "/dev")


def data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_ID, appauthor=False))


def default_library() -> Path:
    return data_dir() / "vms"


def old_user_install() -> Path | None:
    """Ältere Installation aus ``install.sh``, die ein installiertes Paket überdecken kann.

    Sie liegt im Benutzerordner und hat im Startmenü und im PATH Vorrang vor dem
    ``.deb``-Paket. Läuft das Programm gerade selbst daraus, ist alles in Ordnung.
    """
    app = data_dir() / "app"
    if not (app / "bin" / "bonys-agents").exists():
        return None
    import sys

    if Path(sys.prefix).resolve() == app.resolve():
        return None
    return app


# ---------------------------------------------------------------- Einstellungen
def _settings_file() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    try:
        s = json.loads(_settings_file().read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("default_location", None)
    s.setdefault("locations", [])
    s.setdefault("known", {})  # Name -> letzter bekannter Pfad (für „nicht verfügbar“)
    return s


def save_settings(s: dict) -> None:
    f = _settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), "utf-8")
    os.replace(tmp, f)


def preferred_library() -> Path:
    """Ort, der beim Erstellen vorausgewählt ist."""
    loc = load_settings()["default_location"]
    return Path(loc) if loc else default_library()


def set_preferred_library(path: Path | None) -> None:
    s = load_settings()
    s["default_location"] = str(path) if path else None
    if path:
        add_location(path, s)
    save_settings(s)


def add_location(path: Path, s: dict | None = None) -> None:
    own = s is None
    s = s or load_settings()
    p = str(Path(path))
    if p not in s["locations"] and Path(p) != default_library():
        s["locations"].append(p)
    if own:
        save_settings(s)


def remember(name: str, vm_path: Path) -> None:
    s = load_settings()
    if s["known"].get(name) != str(vm_path):
        s["known"][name] = str(vm_path)
        save_settings(s)


def forget(name: str) -> None:
    s = load_settings()
    if s["known"].pop(name, None) is not None:
        save_settings(s)


# ---------------------------------------------------------------- Laufwerke
@dataclass(frozen=True)
class Drive:
    mount: Path
    label: str
    fstype: str
    total: int
    free: int
    removable: bool
    system: bool

    @property
    def library(self) -> Path:
        """Vorgeschlagener Ordner auf diesem Laufwerk."""
        return self.mount / LIBRARY_DIRNAME

    @property
    def is_fat(self) -> bool:
        return self.fstype.lower() in FAT_TYPES

    def describe(self) -> str:
        kind = "Hauptsystem" if self.system else ("Wechseldatenträger" if self.removable else "Laufwerk")
        name = self.label if self.label else str(self.mount)
        where = "" if self.label == str(self.mount) else f" ({self.mount})"
        return f"{name}{where} – {kind}, {self.fstype or '?'}, {self.free / GB:.0f} GB frei"


def _windows_volume_label(mount: str) -> str:
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(mount), buf, 261, None, None, None, None, 0
        )
        return buf.value if ok else ""
    except Exception:  # noqa: BLE001
        return ""


def _linux_removable(device: str, mount: str) -> bool:
    if mount.startswith(("/media/", "/run/media/")):
        return True
    try:
        node = (Path("/sys/class/block") / Path(device).name).resolve()
        for cand in (node, node.parent):  # Partition -> Gerät
            f = cand / "removable"
            if f.exists() and f.read_text().strip() == "1":
                return True
        return "/usb" in str(node)  # USB-SSDs melden sich oft nicht als „removable“
    except OSError:
        return False


def _partitions():
    try:
        return psutil.disk_partitions(all=False)
    except Exception:  # noqa: BLE001
        return []


def drives() -> list[Drive]:
    result: list[Drive] = []
    seen: set[str] = set()
    system_mount = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
    home = str(Path.home())
    home_mount = None
    try:
        # Laufwerk mit dem Benutzerordner über die Geräte-ID: unter macOS liegt /Users auf
        # /System/Volumes/Data, ohne dass der Pfad damit beginnt („/“ selbst ist schreibgeschützt).
        home_dev = os.stat(home).st_dev
    except OSError:
        home_dev = None
    for p in _partitions():
        mount, fstype = p.mountpoint, (p.fstype or "")
        if os.name == "nt":
            if "cdrom" in p.opts or not fstype:
                continue
        else:
            if fstype.lower() in _SKIP_FSTYPES or mount.startswith(_SKIP_PREFIXES):
                continue
            try:
                same_dev = home_dev is not None and os.stat(mount).st_dev == home_dev
            except OSError:
                same_dev = False
            if (same_dev or home.startswith(mount)) and (home_mount is None or len(mount) > len(home_mount)):
                home_mount = mount
        key = p.device if os.name != "nt" else mount
        if key in seen:
            continue
        if "ro" in p.opts.split(","):
            continue  # schreibgeschützt (z. B. CD, eingebundenes Image)
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue  # leeres Kartenlesegerät o. Ä.
        if usage.total < GB:
            continue
        seen.add(key)
        if os.name == "nt":
            removable = "removable" in p.opts
            label = _windows_volume_label(mount)
            label = f"{label} ({mount.rstrip(chr(92))})" if label else mount
        else:
            removable = _linux_removable(p.device, mount)
            label = Path(mount).name if mount != "/" else "/"
        result.append(Drive(Path(mount), label, fstype, usage.total, usage.free, removable, mount == system_mount))
    if home_mount and home_mount != "/":
        result = [d if str(d.mount) != home_mount else Drive(d.mount, d.label, d.fstype, d.total, d.free,
                                                               d.removable, True) for d in result]
    result.sort(key=lambda d: (not d.system, str(d.mount)))
    return result


def drive_for(path: Path) -> Drive | None:
    """Laufwerk, auf dem ``path`` liegt (längster passender Mountpoint)."""
    p = str(Path(path).resolve() if Path(path).exists() else Path(path).absolute())
    best = None
    for d in drives():
        m = str(d.mount)
        if os.name == "nt":
            match = p.lower().startswith(m.lower())
        else:
            match = p == m or p.startswith(m.rstrip("/") + "/")
        if match and (best is None or len(m) > len(str(best.mount))):
            best = d
    return best


# ---------------------------------------------------------------- Bibliotheken finden
_cache: tuple[float, list[Path]] = (0.0, [])


def discovered_libraries(max_age: float = 10.0) -> list[Path]:
    """``BonysAgents``-Ordner im Wurzelverzeichnis aller Laufwerke (kurz zwischengespeichert)."""
    global _cache
    now = time.monotonic()
    if now - _cache[0] < max_age:
        return list(_cache[1])
    found = []
    for p in _partitions():
        cand = Path(p.mountpoint) / LIBRARY_DIRNAME
        try:
            if cand.is_dir():
                found.append(cand)
        except OSError:
            continue
    _cache = (now, found)
    return list(found)


def invalidate_cache() -> None:
    global _cache
    _cache = (0.0, [])


def libraries() -> list[Path]:
    """Alle Speicherorte, in denen nach Agent-PCs gesucht wird – ohne Doppelte."""
    s = load_settings()
    cands = [default_library()]
    if s["default_location"]:
        cands.append(Path(s["default_location"]))
    cands += [Path(p) for p in s["locations"]]
    cands += discovered_libraries()
    out: list[Path] = []
    seen: set[str] = set()
    for c in cands:
        try:
            key = os.path.normcase(str(c.resolve()))
        except OSError:
            key = os.path.normcase(str(c))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


# ---------------------------------------------------------------- Prüfen
@dataclass
class LocationCheck:
    path: Path
    errors: list[str]
    warnings: list[str]
    drive: Drive | None

    @property
    def ok(self) -> bool:
        return not self.errors


MIN_FREE_GB = 4  # Image + erste Einrichtung


def check_location(path: Path, disk_gb: int, create: bool = False, min_free_gb: float = MIN_FREE_GB) -> LocationCheck:
    path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    drive = drive_for(path)

    if drive and drive.is_fat:
        errors.append(
            f"Das Laufwerk ist mit {drive.fstype.upper()} formatiert – das erlaubt keine Dateien über 4 GB. "
            "Bitte als exFAT, NTFS oder ext4 formatieren."
        )

    try:
        free = shutil.disk_usage(_existing_parent(path)).free
    except OSError:
        free = None
        errors.append("Ordner ist nicht erreichbar – ist das Laufwerk eingesteckt?")
    if free is not None:
        if free < min_free_gb * GB:
            errors.append(f"Zu wenig Platz: nur {free / GB:.1f} GB frei, mindestens {min_free_gb:g} GB nötig.")
        elif free < (disk_gb + 1) * GB:
            warnings.append(
                f"Nur {free / GB:.0f} GB frei. Die virtuelle Festplatte ({disk_gb} GB) wächst erst bei Bedarf, "
                "kann das Laufwerk aber irgendwann füllen."
            )

    if not errors and create:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / f".schreibtest-{uuid.uuid4().hex[:8]}"
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError as e:
            errors.append(f"Keine Schreibrechte für {path}: {e.strerror or e}")

    if drive and drive.removable and not errors:
        warnings.append("Wechseldatenträger: den Agent-PC vor dem Abziehen immer herunterfahren.")
    return LocationCheck(path, errors, warnings, drive)


def _existing_parent(path: Path) -> Path:
    p = Path(path).absolute()
    while not p.exists() and p.parent != p:
        p = p.parent
    return p
