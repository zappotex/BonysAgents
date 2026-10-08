# SPDX-License-Identifier: GPL-3.0-or-later
"""Externe Programme mit der ursprünglichen Umgebung starten.

Das fertige Programm (PyInstaller) setzt beim Start u. a. ``LD_LIBRARY_PATH`` auf seinen
``_internal``-Ordner. Jedes Programm, das Bony's Agents startet (QEMU, qemu-img, apt/pkexec,
xdg-open, ssh, Remmina …), würde das erben und die mitgelieferten statt der System-Bibliotheken
laden – auf neueren Systemen startet QEMU dann gar nicht:

    qemu-system-x86_64: …/_internal/libmount.so.1: version `MOUNT_2_40' not found

Deshalb läuft jeder Aufruf mit ``env=clean_env()`` (ein Test prüft das im ganzen Quelltext).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping

# Suchpfade für Bibliotheken: PyInstaller merkt sich den ursprünglichen Wert in <NAME>_ORIG.
LIBRARY_PATH_VARS = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "LIBPATH")
# Variablen, die PyInstaller bzw. seine Laufzeit-Hooks auf den Programmordner setzen können.
# Sie werden nur entfernt, wenn sie wirklich in den Programmordner zeigen.
BUNDLE_VARS = (
    "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH",
    "QTWEBENGINEPROCESS_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "GIO_MODULE_DIR", "GI_TYPELIB_PATH", "GSETTINGS_SCHEMA_DIR", "FONTCONFIG_FILE", "FONTCONFIG_PATH",
    "TCL_LIBRARY", "TK_LIBRARY", "PYTHONHOME", "PYTHONPATH",
)
BUNDLE_PREFIXES = ("GTK_", "GDK_", "GST_", "PANGO_")
PATH_LIST_VARS = ("PATH", "XDG_DATA_DIRS")
# Interne Variablen des PyInstaller-Starters – ein neu gestartetes Bony's Agents (Neustart nach
# einem Update) soll sich nicht für einen Unterprozess des alten halten.
PYINSTALLER_INTERNAL = ("_PYI_", "_MEIPASS")


def is_frozen() -> bool:
    """Läuft das fertige Programm (PyInstaller) statt des Quellcodes?"""
    return bool(getattr(sys, "frozen", False))


def bundle_dirs() -> list[str]:
    """Programmordner des fertigen Programms (``_internal`` und der Ordner mit den Programmen)."""
    dirs = [getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.executable))]
    return [d for d in dirs if d]


def restore_environment(env: Mapping[str, str], dirs: list[str]) -> dict[str, str]:
    """Umgebung ohne die Änderungen von PyInstaller (reine Funktion – gut testbar)."""
    out = dict(env)
    norm = [os.path.normcase(os.path.normpath(d)) for d in dirs if d]

    def inside(value: str) -> bool:
        v = os.path.normcase(value)
        return any(d in v for d in norm)

    for var in LIBRARY_PATH_VARS:
        orig = out.pop(var + "_ORIG", None)
        if orig:
            out[var] = orig
        else:
            out.pop(var, None)
    for key in list(out):
        if key.startswith(PYINSTALLER_INTERNAL):
            out.pop(key)
        elif (key in BUNDLE_VARS or key.startswith(BUNDLE_PREFIXES)) and inside(out[key]):
            out.pop(key)
    for key in PATH_LIST_VARS:
        if key in out:
            parts = [p for p in out[key].split(os.pathsep) if p and not inside(p)]
            if parts:
                out[key] = os.pathsep.join(parts)
            else:
                out.pop(key)
    return out


# Homebrew: Apple-Chip, Intel. Aus dem Finder gestartete Apps bekommen nur /usr/bin:/bin:/usr/sbin:/sbin.
HOMEBREW_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def add_homebrew_to_path(env: dict | None = None, platform: str = sys.platform) -> None:
    """macOS: Homebrew-Ordner an den PATH hängen (für shutil.which und alle gestarteten Programme)."""
    if platform != "darwin":
        return
    env = os.environ if env is None else env
    parts = [p for p in env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(":") if p]  # macOS: immer „:“
    env["PATH"] = ":".join(parts + [d for d in HOMEBREW_BIN_DIRS if d not in parts])


def clean_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Umgebung für externe Programme: im fertigen Programm wie vor dem Start von Bony's Agents."""
    env = restore_environment(os.environ, bundle_dirs()) if is_frozen() else dict(os.environ)
    if extra:
        env.update(extra)
    return env


def no_window_flags() -> int:
    """Unter Windows kein schwarzes Konsolenfenster für Hilfsprozesse aufblitzen lassen."""
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def spawn_detached(cmd: list[str]) -> None:
    """Programm unabhängig von Bony's Agents starten (läuft weiter, wenn die App endet)."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, env=clean_env(), **kwargs)


def open_external(target: str) -> None:
    """Adresse oder Datei/Ordner mit dem Standardprogramm des Systems öffnen."""
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606 – ShellExecute, kein Bibliothekspfad
    elif sys.platform == "darwin":
        spawn_detached(["open", target])
    else:
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if not opener:
            raise RuntimeError("Kein Programm zum Öffnen gefunden (xdg-open fehlt).")
        spawn_detached([opener, target] if opener.endswith("xdg-open") else [opener, "open", target])


# Terminal-Programme unter Linux mit der Option, nach der der auszuführende Befehl folgt.
LINUX_TERMINALS = [
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("mate-terminal", ["-x"]),
    ("tilix", ["-e"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("x-terminal-emulator", ["-e"]),
    ("xterm", ["-e"]),
]


def terminal_command(argv: list[str], host_os: str | None = None, which=shutil.which) -> list[str]:
    """Befehl, der ein Terminalfenster öffnet und darin ``argv`` ausführt."""
    host_os = host_os or ("windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux")
    if host_os == "windows":
        return ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", subprocess.list2cmdline(argv)]
    if host_os == "macos":
        import shlex

        script = shlex.join(argv).replace("\\", "\\\\").replace('"', '\\"')
        return ["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                "-e", 'tell application "Terminal" to activate']
    for name, opts in LINUX_TERMINALS:
        if which(name):
            if name == "x-terminal-emulator":
                # Debian-Alternative: manche Terminals erwarten hier nur EINEN Befehl als Text
                import shlex

                return [name, "-e", shlex.join(argv)]
            return [name, *opts, *argv]
    raise RuntimeError("Kein Terminal-Programm gefunden (z. B. gnome-terminal oder xterm installieren).")
