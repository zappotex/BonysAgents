# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller-Bauplan für Bony's Agents
#
# Erzeugt EINEN Ordner dist/bonys-agents/ mit zwei Programmen, die sich alle
# Bibliotheken teilen:
#   BonysAgents(.exe)    – Desktop-App, ohne Konsolenfenster
#   bonys-agents(.exe)   – Kommandozeile (wird auch vom Windows-Installer genutzt)
#
# Bauen:  pyinstaller --noconfirm packaging/bonys-agents.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # noqa: F821 – SPECPATH stellt PyInstaller bereit
ICON = str(ROOT / "src" / "bonys_agents" / "resources" / "icon.ico")
VERSION = next(
    line.split('"')[1]
    for line in (ROOT / "src" / "bonys_agents" / "__init__.py").read_text().splitlines()
    if line.startswith("__version__")
)
datas = collect_data_files("bonys_agents")
# Bony's VPN wird als Quelltext in den Agent-PC übertragen (apps.vpn_payload) – also auch die .py-Dateien.
datas += collect_data_files("bonys_agents.vpn", include_py_files=True)

# Nicht benötigte Qt-Teile weglassen – spart ~100 MB.
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtPrintSupport", "PySide6.QtDBus",
    "PySide6.QtHelp", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtWebEngineCore",
    "tkinter", "unittest", "pydoc",
]


def analysis(script):
    return Analysis(  # noqa: F821
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT / "src")],
        datas=datas,
        hiddenimports=["bonys_agents.gui.app", "bonys_agents.gui.main_window"],
        excludes=EXCLUDES,
        noarchive=False,
    )


gui_a = analysis("gui_entry.py")
cli_a = analysis("cli_entry.py")

gui_exe = EXE(  # noqa: F821
    PYZ(gui_a.pure),  # noqa: F821
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name="BonysAgents",
    console=False,
    icon=ICON,
    upx=False,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli_a.pure),  # noqa: F821
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name="bonys-agents",
    console=True,
    icon=ICON,
    upx=False,
)

# Linux: GTK/GLib und alles, was sie selbst laden, kommen vom System (das .deb hängt davon ab).
# Mitgeliefert würden sie mit den System-Bibliotheken kollidieren: Lädt z. B. das GTK-Theme-Plugin
# von Qt das libgio des Systems, bekäme es sonst ein älteres mitgeliefertes libmount
# („version `MOUNT_2_40' not found“). Nur der Build-Rechner ist alt genug, um das zu übersehen.
SYSTEM_LIBS = (
    # GTK, GLib, Pango, Cairo
    "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libgio-2.0", "libglib-2.0", "libgobject-2.0",
    "libgmodule-2.0", "libgthread-2.0", "libpango", "libcairo", "libatk", "libatspi", "libepoxy",
    "libharfbuzz", "libfribidi", "libthai", "libdatrie", "libgraphite2", "libpixman", "libpng16",
    "libfontconfig", "libfreetype", "libexpat", "libbrotli",
    # util-linux, SELinux, systemd/udev, D-Bus und deren Abhängigkeiten
    "libmount", "libblkid", "libuuid", "libselinux", "libpcre2", "libudev", "libsystemd", "libdbus",
    "libcap.so", "libgcrypt", "libgpg-error", "liblz4", "liblzma", "libzstd", "libbz2",
    # Grundbibliotheken (libz.so – nicht libzstd mit „libz“ verwechseln)
    "libz.so", "libstdc++", "libgcc_s", "libffi",
    # X11/xcb (lädt auch GTK)
    "libX11", "libXau", "libXdmcp", "libbsd", "libmd.so", "libxcb", "libXcomposite", "libXcursor",
    "libXdamage", "libXext", "libXfixes", "libXinerama", "libXi.so", "libXrandr", "libXrender", "libxkbcommon",
)


def keep_binary(entry) -> bool:
    name = Path(entry[0]).name
    return not (sys.platform.startswith("linux") and name.startswith(SYSTEM_LIBS))


def keep_data(entry) -> bool:
    # Von den Qt-Übersetzungen nur Deutsch und Englisch behalten.
    dest = entry[0].replace("\\", "/")
    if "/translations/" in dest and dest.endswith(".qm"):
        return dest.endswith(("_de.qm", "_en.qm"))
    return True


def slim(a):
    a.binaries = [b for b in a.binaries if keep_binary(b)]
    a.datas = [d for d in a.datas if keep_data(d)]


slim(gui_a)
slim(cli_a)

coll = COLLECT(  # noqa: F821
    gui_exe, gui_a.binaries, gui_a.datas,
    cli_exe, cli_a.binaries, cli_a.datas,
    name="bonys-agents",
    upx=False,
)

if sys.platform == "darwin":
    # Ältestes unterstütztes macOS: PySide6 ab 6.12 läuft erst ab macOS 14 (Sonoma), Homebrew (für QEMU)
    # unterstützt 14 ebenfalls noch. Der Release-Workflow prüft, dass keine mitgelieferte Bibliothek
    # ein neueres macOS verlangt (sonst startet die App auf älteren Macs nicht).
    MACOS_MIN = "14.0"
    app = BUNDLE(  # noqa: F821
        coll,
        name="Bony's Agents.app",
        icon=str(ROOT / "packaging" / "macos" / "icon.icns"),
        bundle_identifier="io.github.bonys-agents",
        version=VERSION,
        info_plist={
            "CFBundleName": "Bony's Agents",
            "CFBundleDisplayName": "Bony's Agents",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleDevelopmentRegion": "de",
            "LSMinimumSystemVersion": MACOS_MIN,
            "LSApplicationCategoryType": "public.app-category.utilities",
            "NSHumanReadableCopyright": "Copyright © 2026 Bony – GPL-3.0-or-later",
            "NSHighResolutionCapable": True,
            # Wichtig: COLLECT übernimmt console=True vom zuletzt genannten Programm (der Kommandozeile),
            # BUNDLE macht daraus LSBackgroundOnly=True. Dann wäre die App ein unsichtbarer
            # Hintergrunddienst – kein Dock-Symbol, keine Menüleiste, Fenster kommen nicht nach vorn.
            "LSBackgroundOnly": False,
        },
    )
