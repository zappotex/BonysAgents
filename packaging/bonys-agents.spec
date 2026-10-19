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
import importlib.util
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
if TRAINER:   # Vorlage der Handbücher – der Kurspaket-Editor baut damit Ablaufplan und Handout als PDF
    datas.append((str(ROOT / "docs" / "handbuch" / "vorlage"), "bonys_agents/trainer/resources/handbuch-vorlage"))

# Nicht benötigte Qt-Teile weglassen. Qt WebEngine (Kursraum) bleibt drin – es bringt QtNetwork, QtWebChannel und
# die Qt-Bibliotheken von Qml/Quick selbst mit (als Abhängigkeit von libQt6WebEngineCore, nicht als Python-Modul).
EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtDBus",   # QtPrintSupport braucht QtWebEngineCore
    "PySide6.QtHelp", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "tkinter", "unittest", "pydoc",
] + ([] if TRAINER else [editions.TRAINER_PACKAGE])
HIDDEN = ["bonys_agents.gui.app", "bonys_agents.gui.main_window", "bonys_agents.gui.share_dialogs",
          "bonys_agents._edition", "qrcode", "bony_netz",   # bony_netz: gemeinsamer Baustein mit Bony's VPN
          "bonys_agents.gui.kursraum_fenster"]
# Kursraum (Qt WebEngine) – nicht in Linux arm64 (dort ist PySide6-WebEngine nicht installiert, siehe Lock-Datei)
if importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None:
    HIDDEN += ["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore", "PySide6.QtWebChannel"]
if not (ROOT / "src" / "bonys_agents" / "resources" / "kursraum" / "vendor" / "livekit-client.umd.js").is_file():
    raise SystemExit("livekit-client fehlt – erst python packaging/fetch-livekit.py ausführen.")
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
        # pycdlib (LGPL-2.1) als lose .py-Dateien in _internal/pycdlib – austauschbar (LGPL-2.1 §6), nicht im
        # Archiv der Programmdatei. packaging/check-edition.py prüft das.
        module_collection_mode={"pycdlib": "py"},
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
    # Qt WebEngine (Kursraum): NSS lädt zur Laufzeit eigene Module des Systems (libsoftokn3, libfreebl3) –
    # mitgelieferte, ältere libnss3 passten nicht dazu. Ton (ALSA), Grafik (GBM/DRM) und Tastatur ebenso vom System.
    "libnss3", "libnssutil3", "libsmime3", "libnspr4", "libplc4", "libplds4", "libasound", "libgbm", "libdrm",
    "libxkbfile", "libXtst",
    # … und die NSS-Module, die PyInstaller für WebEngine einsammelt (alles von NSS kommt vom System)
    "libsoftokn3", "libfreebl3", "libfreeblpriv3", "libnssckbi", "libnssdbm3", "libsqlite3",
    # Druck-Plugin (CUPS) gibt es nicht (siehe keep_binary) – und damit auch nicht seine Bibliotheken
    "libcups", "libavahi", "libgnutls", "libgmp", "libnettle", "libhogweed", "libidn2", "libtasn1",
    "libunistring", "libp11-kit",
)
# Qt-Plugins, die die App nicht braucht: Drucken (zöge CUPS, Avahi und GnuTLS herein)
SKIP_PLUGINS = ("/plugins/printsupport/",)


def keep_binary(entry) -> bool:
    name = Path(entry[0]).name
    if any(skip in "/" + entry[0].replace("\\", "/") for skip in SKIP_PLUGINS):
        return False
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
            # Kursraum: Ohne diese Texte beendet macOS die App beim ersten Zugriff auf Kamera/Mikrofon.
            # Bildschirmaufnahme braucht keinen Text – macOS fragt selbst (Systemeinstellungen → Datenschutz).
            "NSCameraUsageDescription": "Im Kursraum können dich die anderen Teilnehmer sehen, wenn du deine "
                                        "Kamera einschaltest.",
            "NSMicrophoneUsageDescription": "Im Kursraum können dich die anderen Teilnehmer hören, wenn du dein "
                                            "Mikrofon einschaltest.",
            # Wichtig: COLLECT übernimmt console=True vom zuletzt genannten Programm (der Kommandozeile),
            # BUNDLE macht daraus LSBackgroundOnly=True. Dann wäre die App ein unsichtbarer
            # Hintergrunddienst – kein Dock-Symbol, keine Menüleiste, Fenster kommen nicht nach vorn.
            "LSBackgroundOnly": False,
        },
    )
