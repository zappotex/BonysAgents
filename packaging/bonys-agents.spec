# SPDX-License-Identifier: GPL-3.0-or-later
# PyInstaller-Bauplan für Bony's Agents
#
# Erzeugt EINEN Ordner mit zwei Programmen, die sich alle Bibliotheken teilen:
#   BonysAgents(.exe)    – Desktop-App, ohne Konsolenfenster
#   bonys-agents(.exe)   – Kommandozeile (wird auch vom Windows-Installer genutzt)
#
# Zwei Editionen aus einem Quellcode (siehe docs/editionen.md, packaging/editions.py):
#   pyinstaller --noconfirm packaging/bonys-agents.spec                          → dist/bonys-agents/ (Anwender)
#   pyinstaller --noconfirm packaging/bonys-agents.spec -- --edition kursleiter  → dist/bonys-agents-kursleiter/
# (oder BONYS_EDITION=kursleiter). Die Anwender-Version enthält bonys_agents.trainer gar nicht – kein Server-Code,
# kein noVNC. Die Edition steht danach fest im Programm (bonys_agents/_edition.py, nur während des Bauens).

import atexit
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 – SPECPATH stellt PyInstaller bereit
sys.path.insert(0, str(ROOT / "packaging"))
import editions  # noqa: E402

EDITION = editions.parse(sys.argv)
TRAINER = EDITION == "kursleiter"
DIST_NAME = editions.DIST_NAMES[EDITION]
DISPLAY_NAME = editions.DISPLAY_NAMES[EDITION]
print(f"==> Edition: {EDITION} ({DISPLAY_NAME}) -> dist/{DIST_NAME}")
if TRAINER and not (ROOT / "src" / "bonys_agents" / "trainer" / "resources" / "novnc" / "core" / "rfb.js").is_file():
    raise SystemExit("noVNC fehlt – erst python packaging/fetch-novnc.py ausführen.")

# Edition fest ins Programm schreiben – nur für diesen Bau, danach wieder weg (sonst gälte sie auch im Quellordner)
EDITION_FILE = ROOT / "src" / "bonys_agents" / "_edition.py"
EDITION_FILE.write_text(f'# Beim Bauen erzeugt (packaging/bonys-agents.spec)\nEDITION = "{EDITION}"\n')
atexit.register(lambda: EDITION_FILE.unlink(missing_ok=True))
ICON = str(ROOT / "src" / "bonys_agents" / "resources" / "icon.ico")
VERSION = next(
    line.split('"')[1]
    for line in (ROOT / "src" / "bonys_agents" / "__init__.py").read_text().splitlines()
    if line.startswith("__version__")
)
# Anwender: nichts aus trainer/ (Seiten der Vorführung, noVNC) – Kursleiter: alles
datas = [d for d in collect_data_files("bonys_agents") if editions.keep(EDITION, d[1])]

# Nicht benötigte Qt-Teile weglassen – spart ~100 MB.
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtPrintSupport", "PySide6.QtDBus",
    "PySide6.QtHelp", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtWebEngineCore",
    "tkinter", "unittest", "pydoc",
] + ([] if TRAINER else [editions.TRAINER_PACKAGE])
HIDDEN = ["bonys_agents.gui.app", "bonys_agents.gui.main_window", "bonys_agents.gui.share_dialogs",
          "bonys_agents._edition", "qrcode"]
if TRAINER:   # werden erst bei Bedarf importiert – PyInstaller fände sie sonst nicht
    HIDDEN += collect_submodules(editions.TRAINER_PACKAGE)


def analysis(script):
    a = Analysis(  # noqa: F821
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT / "src")],
        datas=datas,
        hiddenimports=HIDDEN,
        excludes=EXCLUDES,
        noarchive=False,
    )
    if not TRAINER:   # Sicherheitsnetz: kein Modul aus trainer/ in der Anwender-Version
        a.pure = [m for m in a.pure if not editions.is_trainer_path(m[0])]
    return a


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
    a.datas = [d for d in a.datas if keep_data(d) and editions.keep(EDITION, d[0])]


slim(gui_a)
slim(cli_a)

coll = COLLECT(  # noqa: F821
    gui_exe, gui_a.binaries, gui_a.datas,
    cli_exe, cli_a.binaries, cli_a.datas,
    name=DIST_NAME,
    upx=False,
)

if sys.platform == "darwin":
    # Ältestes unterstütztes macOS: PySide6 ab 6.12 läuft erst ab macOS 14 (Sonoma), Homebrew (für QEMU)
    # unterstützt 14 ebenfalls noch. Der Release-Workflow prüft, dass keine mitgelieferte Bibliothek
    # ein neueres macOS verlangt (sonst startet die App auf älteren Macs nicht).
    MACOS_MIN = "14.0"
    # Beide Editionen heißen im Ordner „Programme“ gleich und haben dieselbe Bundle-ID: Die eine ersetzt beim
    # Hineinziehen die andere (Finder fragt „Ersetzen?“), Berechtigungen und Einstellungen bleiben. Angezeigt wird
    # die Edition über CFBundleDisplayName (Dock, „Über“), der Name der .dmg nennt sie ebenfalls.
    app = BUNDLE(  # noqa: F821
        coll,
        name="Bony's Agents.app",
        icon=str(ROOT / "packaging" / "macos" / "icon.icns"),
        bundle_identifier="io.github.bonys-agents",
        version=VERSION,
        info_plist={
            "CFBundleName": "Bony's Agents",
            "CFBundleDisplayName": DISPLAY_NAME,
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
