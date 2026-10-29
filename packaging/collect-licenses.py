#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lizenztexte aller tatsächlich mitgelieferten Teile in den Programmordner legen (Ordner ``licenses``).

    python packaging/collect-licenses.py dist/bonys-agents
    python packaging/collect-licenses.py "dist/Bony's Agents.app"        (→ Contents/Resources/licenses)

Läuft nach PyInstaller im Bau-Python (dessen Pakete und Lizenzdateien eingebaut wurden):

- Python selbst: LICENSE.txt der Laufzeit (unter Windows/macOS inkl. OpenSSL, libffi, expat, … des Python-Builds),
- jedes Python-Paket, dessen Module im Programm stecken: seine Lizenzdateien (PySide6/Shiboken6: LGPL-3.0 + GPL-3.0),
- Qt: Lizenz- und Copyright-Angaben aller Drittteile (qt_attribution.json) der eingebauten Qt-Version
  (aus den Qt-Quellen, nur diese Dateien werden geladen) und ICU, falls Qt sie mitbringt,
- Qt WebEngine (Kursraum): Lizenz von Chromium in genau der eingebauten Fassung und wo die Liste seiner
  Drittkomponenten steht; livekit-client liegt mit Lizenz unter bonys_agents/resources/kursraum/vendor,
- Linux: die Debian/Ubuntu-``copyright``-Datei jedes Pakets, aus dem eine mitgelieferte Bibliothek stammt.

Fehlt für ein mitgeliefertes Python-Paket der Lizenztext, bricht das Skript ab – nichts soll ohne Lizenz hinein.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.request
from pathlib import Path

LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
# Pakete ohne Lizenzdatei im Wheel → SPDX-Texte aus den Qt-Quellen (LICENSES/)
QT_LICENSED = {"pyside6", "pyside6-essentials", "pyside6-addons", "pyside6-webengine", "shiboken6"}
# Teile der Qt-Quellen, die nie im Programm landen (Tests, Bauwerkzeuge, andere Plattformen)
QT_SKIP = ("/testlib/", "/testinternal/", "cmake/", "util/", "/android/", "/wasm/", "/gradle/")


def bundle_dirs(root: Path) -> tuple[Path, Path]:
    """(Inhalt, Zielordner) – bei einer macOS-.app liegt alles unter Contents/."""
    if root.suffix == ".app":
        return root / "Contents", root / "Contents" / "Resources" / "licenses"
    return root, root / "licenses"


def bundled_modules(content: Path) -> set[str]:
    """Oberste Modulnamen im Programm: lose Dateien/Ordner und Module in den PYZ-Archiven der Programmdateien."""
    names = set()
    for p in content.rglob("*"):
        if p.suffix in (".py", ".pyc", ".so", ".pyd") or (p.is_dir() and (p / "__init__.py").exists()):
            names.add(p.name.split(".")[0])
    for p in content.rglob("*"):
        names.add(p.name)
    try:
        from PyInstaller.archive.readers import PKG_ITEM_PYZ, CArchiveReader
    except ImportError:
        return names
    for exe in (p for p in content.rglob("*") if p.is_file() and p.stat().st_size > 100_000):
        try:
            pkg = CArchiveReader(str(exe))
        except Exception:  # noqa: BLE001 – keine PyInstaller-Datei
            continue
        for entry, info in pkg.toc.items():
            if info[-1] == PKG_ITEM_PYZ:
                names |= {m.split(".")[0] for m in pkg.open_embedded_archive(entry).toc}
    return names


def top_level(dist: md.Distribution) -> set[str]:
    text = dist.read_text("top_level.txt")
    if text:
        return {line.strip() for line in text.splitlines() if line.strip()}
    return {Path(str(f)).parts[0].split(".")[0] for f in dist.files or [] if not str(f).startswith(("..", "/"))
            and ".dist-info" not in str(f)}


def python_license(out: Path) -> None:
    for cand in (Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"):
        if cand.is_file():
            shutil.copyfile(cand, out / "Python-LICENSE.txt")
            return
    raise SystemExit("LICENSE.txt von Python nicht gefunden")


def packages(content: Path, out: Path, qt_licenses: Path) -> list[str]:
    mods = bundled_modules(content)
    done = []
    for dist in md.distributions():
        name = dist.metadata["Name"]
        bootloader = name.lower() == "pyinstaller"  # steckt in jeder Programmdatei, als Modul aber nicht
        if not bootloader and (name.lower() in ("pip", "setuptools", "wheel", "bonys-agents")
                               or not (top_level(dist) & mods)):
            continue
        target = out / "python" / f"{name}-{dist.version}"
        target.mkdir(parents=True, exist_ok=True)
        files = [f for f in dist.files or [] if LICENSE_FILE.search(Path(str(f)).name) and ".dist-info" in str(f)]
        for f in files:
            shutil.copyfile(Path(dist.locate_file(f)), target / Path(str(f)).name)
        if not files and re.sub(r"[-_.]+", "-", name.lower()) in QT_LICENSED:
            for spdx in ("LGPL-3.0-only", "GPL-3.0-only"):
                shutil.copyfile(qt_licenses / f"{spdx}.txt", target / f"{spdx}.txt")
        elif not files:
            raise SystemExit(f"Kein Lizenztext für das mitgelieferte Paket {name} {dist.version}")
        lic = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "?"
        done.append(f"{name} {dist.version} – {lic.splitlines()[0][:70]}")
    return sorted(done, key=str.lower)


def _git(*args: str) -> None:
    """git mit drei Versuchen – ein kurzer Netzaussetzer soll den Bau nicht abbrechen."""
    for attempt in range(3):
        if subprocess.run(["git", *args]).returncode == 0:
            return
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"git {' '.join(args[:4])} … ist dreimal fehlgeschlagen")


def fetch_qt(repo: str, version: str, dest: Path) -> Path:
    """Nur qt_attribution.json, die dort genannten Lizenzdateien und LICENSES/ aus den Qt-Quellen holen."""
    d = dest / repo
    if not d.exists():
        _git("clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1", "--branch", f"v{version}",
             f"https://github.com/qt/{repo}.git", str(d))
    base = ["**/qt_attribution.json", "/LICENSES/"]
    _git("-C", str(d), "sparse-checkout", "set", "--no-cone", *base)
    _git("-C", str(d), "checkout", "-q")
    wanted = []
    for f, e in qt_entries(d):
        for lf in _as_list(e.get("LicenseFile")):
            wanted.append("/" + (f.parent / lf).relative_to(d).as_posix())
    if wanted:  # noch einmal „set“ mit allem – ältere git (Windows/macOS) kennen „add --no-cone“ nicht
        _git("-C", str(d), "sparse-checkout", "set", "--no-cone", *base, *wanted)
        _git("-C", str(d), "checkout", "-q")
    return d


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v] if v else []


def qt_entries(src: Path) -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(src.rglob("qt_attribution.json")):
        rel = "/" + f.relative_to(src).as_posix()
        if any(s in rel or rel.startswith("/" + s) for s in QT_SKIP):
            continue
        data = json.loads(f.read_text("utf-8"), strict=False)
        out += [(f, e) for e in _as_list(data) if isinstance(e, dict)]
    return out


def qt_attributions(src: Path, title: str) -> str:
    parts = [f"{title}\n{'=' * len(title)}\n"]
    for f, e in qt_entries(src):
        head = f"{e.get('Name', e.get('Id', '?'))} {e.get('Version', '')}".strip()
        parts.append(f"\n{head}\n{'-' * len(head)}")
        if e.get("QtUsage"):
            parts.append(f"Verwendung: {e['QtUsage']}")
        parts.append(f"Lizenz: {e.get('License', '?')} ({e.get('LicenseId', '?')})")
        for c in _as_list(e.get("Copyright")):
            parts.append(c)
        texts = [(f.parent / lf) for lf in _as_list(e.get("LicenseFile"))]
        if not texts:  # nur SPDX-Kennung → Text aus LICENSES/
            ids = re.findall(r"[A-Za-z0-9.+-]+", e.get("LicenseId", ""))
            texts = [src / "LICENSES" / f"{i}.txt" for i in ids if i not in ("AND", "OR", "WITH")]
        for t in texts:
            if t.is_file():
                parts.append("\n" + t.read_text("utf-8", errors="replace").strip())
    return "\n".join(parts) + "\n"


def qt_version() -> str:
    """Version der eingebauten Qt-Bibliotheken (PySide6 6.8.0.2 bringt z. B. Qt 6.8.0 mit)."""
    try:
        from PySide6.QtCore import qVersion
        return qVersion()
    except ImportError:
        return ".".join(md.version("shiboken6").split(".")[:3])


def qt_and_icu(content: Path, out: Path, tmp: Path) -> tuple[str, Path]:
    version = qt_version()
    names = [p.name for p in content.rglob("*") if p.is_file()]
    def has(lib: str) -> bool:
        return any(f"Qt6{lib}" in n or f"Qt{lib}" in n for n in names)

    repos = ["qtbase"] + (["qtsvg"] if has("Svg") else []) + (["qtwayland"] if has("Wayland") else []) \
        + (["qtdeclarative"] if has("Qml") else []) + (["qtpositioning"] if has("Positioning") else []) \
        + (["qtwebchannel"] if has("WebChannel") else []) + (["qtmultimedia"] if has("Multimedia") else [])
    text = ""
    base = None
    for repo in repos:
        src = fetch_qt(repo, version, tmp)
        base = base or src
        text += qt_attributions(src, f"Qt {version} – Drittkomponenten ({repo})") + "\n"
    (out / "Qt-third-party.txt").write_text(text, "utf-8")
    icu = sorted({m.group(1) for n in names if (m := re.match(r"libicu\w*\.so\.(\d+)", n))})
    for major in icu:
        for minor in ("2", "1"):
            url = f"https://raw.githubusercontent.com/unicode-org/icu/release-{major}-{minor}/icu4c/LICENSE"
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    (out / f"ICU-{major}-LICENSE.txt").write_bytes(r.read())
                break
            except OSError:
                continue
        else:
            raise SystemExit(f"Lizenz von ICU {major} nicht geladen")
    return version, base / "LICENSES"


def openssl(content: Path, out: Path, qt_licenses: Path) -> bool:
    """Windows/macOS: OpenSSL 3 kommt mit Python mit – Apache-2.0 verlangt eine Kopie des Lizenztexts.
    (Unter Linux erledigt das die copyright-Datei von libssl3.)"""
    if sys.platform.startswith("linux"):
        return False
    if not any(re.match(r"(lib)?(ssl|crypto)[-.]", p.name) for p in content.rglob("*") if p.is_file()):
        return False
    text = (qt_licenses / "Apache-2.0.txt").read_text("utf-8")
    (out / "OpenSSL-LICENSE.txt").write_text("OpenSSL 3 (mit Python mitgeliefert) – Apache License 2.0\n"
                                             "Copyright (c) 1998-2025 The OpenSSL Project Authors\n\n" + text, "utf-8")
    return True


def webengine_versionen(libs: list[Path]) -> tuple[str, str]:
    """(Chromium, Qt WebEngine) – ohne QtWebEngine zu laden: Dem Bau-Rechner fehlen oft Grafikbibliotheken (libEGL).

    Chromium steht im User-Agent der Bibliothek („Chrome/140.0.7339.225“). Qt WebEngine hat ab PySide6 6.12 eine eigene
    Nummer: Wheel PySide6-WebEngine 6.12.0.140 → Qt WebEngine 6.140.0; davor gleich der Qt-Version.
    """
    chromium = ""
    for lib in sorted(libs, key=lambda p: -p.stat().st_size):
        if m := re.search(rb"Chrome/(\d+\.\d+\.\d+\.\d+)", lib.read_bytes()):
            chromium = m.group(1).decode()
            break
    if not chromium:
        raise SystemExit("Chromium-Version in Qt WebEngine nicht gefunden")
    try:
        teile = md.version("PySide6-WebEngine").split(".")
        version = f"{teile[0]}.{teile[3]}.0" if len(teile) == 4 else qt_version()
    except md.PackageNotFoundError:
        version = qt_version()
    return chromium, version


def webengine(content: Path, out: Path) -> str:
    """Qt WebEngine: Lizenz von Chromium (Zweig „<Version>-based“ von qtwebengine-chromium) – "" ohne WebEngine.

    Chromium bringt Hunderte Drittkomponenten mit; deren vollständige Liste veröffentlicht Qt für jede Version
    (Link in der Datei). Qt WebEngine selbst steht unter LGPL-3.0 wie Qt (Texte bei PySide6).
    """
    libs = [p for p in content.rglob("*") if p.is_file() and "WebEngineCore" in p.name]
    if not libs:
        return ""
    chromium, version = webengine_versionen(libs)
    zweig = f"{chromium.split('.')[0]}-based"
    url = f"https://raw.githubusercontent.com/qt/qtwebengine-chromium/{zweig}/chromium/LICENSE"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 – feste https-Adresse
                lizenz = r.read().decode("utf-8")
            break
        except OSError:
            time.sleep(10 * (attempt + 1))
    else:
        raise SystemExit(f"Lizenz von Chromium nicht geladen ({url})")
    major_minor = ".".join(version.split(".")[:2])
    (out / "QtWebEngine-Chromium.txt").write_text(
        f"Qt WebEngine {version} mit Chromium {chromium} (Kursraum)\n\n"
        "Qt WebEngine steht unter der LGPL-3.0 (Texte im Ordner python/ bei PySide6). Es enthält Chromium, das\n"
        "unter der folgenden BSD-Lizenz steht, und dessen Drittkomponenten mit eigenen Lizenzen (u. a. BSD, MIT,\n"
        "Apache-2.0, LGPL, MPL). Die vollständige Liste dieser Komponenten samt Lizenztexten:\n"
        f"  https://doc.qt.io/qt-{version.split('.')[0]}/qtwebengine-licensing.html (Qt WebEngine {major_minor})\n"
        "Quelltexte: https://code.qt.io/cgit/qt/qtwebengine.git (Tag v" + version + ") und\n"
        f"  https://code.qt.io/cgit/qt/qtwebengine-chromium.git (Zweig {zweig})\n\n"
        "Chromium – BSD-3-Clause\n=======================\n\n" + lizenz, "utf-8")
    return f"Qt WebEngine {version} / Chromium {chromium}: QtWebEngine-Chromium.txt"


SYSTEM_LIB_DIRS = ("/lib", "/usr/lib", "/lib64", "/usr/lib64")


FFMPEG_LIBS = ("libavcodec", "libavformat", "libavutil", "libswresample", "libswscale", "libQt6FFmpegStub",
               "avcodec-", "avformat-", "avutil-", "swresample-", "swscale-")


def ffmpeg(content: Path, out: Path) -> str:
    """Qt Multimedia (Musik & Radio) bringt FFmpeg mit – LGPL-2.1-or-later, Text und Quelle beilegen."""
    libs = sorted({p.name for p in content.rglob("*") if p.is_file() and p.name.startswith(FFMPEG_LIBS)})
    if not any(n.startswith(("libavcodec", "avcodec-")) for n in libs):
        return ""
    url = "https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/COPYING.LGPLv2.1"
    with urllib.request.urlopen(url, timeout=60) as r:
        text = r.read().decode("utf-8")
    (out / "FFmpeg-LICENSE.txt").write_text(
        "FFmpeg (mit Qt Multimedia aus PySide6-Addons mitgeliefert, für Musik & Radio)\n"
        "Lizenz: GNU Lesser General Public License 2.1 oder neuer (LGPL-2.1-or-later)\n"
        "Bibliotheken: " + ", ".join(libs) + "\n"
        "Quelltexte: https://ffmpeg.org/download.html – Bauweise in Qt: "
        "https://doc.qt.io/qt-6/qtmultimedia-attribution-ffmpeg.html\n\n" + text, "utf-8")
    return "FFmpeg (Musik & Radio): FFmpeg-LICENSE.txt"


def debian_packages(content: Path, out: Path) -> tuple[list[str], list[str]]:
    """Linux: Paket jeder mitgelieferten System-Bibliothek (dpkg -S mit ihrem Pfad im System) und dessen copyright.

    System-Bibliotheken legt PyInstaller direkt in _internal ab; Erweiterungsmodule von Python-Paketen liegen in
    Unterordnern (psutil/, PySide6/, lib-dynload/) und sind oben schon erfasst.
    """
    if not sys.platform.startswith("linux") or not shutil.which("dpkg"):
        return [], []
    internal = content / "_internal" if (content / "_internal").is_dir() else content
    pkgs, unknown = set(), []
    for lib in sorted(p for p in internal.iterdir() if p.is_file() and ".so" in p.name):
        if lib.name.startswith(("libpython", "libQt6", "libicu", "libpyside6", "libshiboken6") + FFMPEG_LIBS):
            continue  # Python, Qt/PySide6, ICU und FFmpeg aus dem Qt-Wheel – oben erfasst
        r = subprocess.run(["dpkg", "-S", f"*/{lib.name}"], capture_output=True, text=True)
        found = {line.split(":")[0] for line in r.stdout.splitlines()
                 if ":" in line and line.split(": ", 1)[-1].startswith(SYSTEM_LIB_DIRS)}
        if not found:
            unknown.append(lib.name)
        pkgs |= found
    target = out / "debian"
    target.mkdir(exist_ok=True)
    for pkg in sorted(pkgs):
        cp = Path("/usr/share/doc") / pkg / "copyright"
        if not cp.exists():
            raise SystemExit(f"copyright-Datei von {pkg} fehlt ({cp})")
        shutil.copyfile(cp.resolve(), target / f"{pkg}.copyright")
    return sorted(pkgs), unknown


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    content, out = bundle_dirs(Path(sys.argv[1]))
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    python_license(out)
    with tempfile.TemporaryDirectory() as tmp:
        qt_version, qt_licenses = qt_and_icu(content, out, Path(tmp))
        pkgs = packages(content, out, qt_licenses)
        ssl = openssl(content, out, qt_licenses)
    web = webengine(content, out)
    av = ffmpeg(content, out)
    deb, unknown = debian_packages(content, out)
    index = [
        "Lizenztexte der mitgelieferten Komponenten (beim Bauen aus dem Programmordner erzeugt)",
        "",
        f"Python {sys.version.split()[0]}: Python-LICENSE.txt (mit den Drittteilen des Python-Builds)",
        *(["OpenSSL 3: OpenSSL-LICENSE.txt"] if ssl else []),
        f"Qt {qt_version} und dessen Drittkomponenten: Qt-third-party.txt"
        + (" (ICU: ICU-*-LICENSE.txt)" if list(out.glob("ICU-*")) else ""),
        *([web] if web else []),
        *([av] if av else []),
        "Python-Pakete (Ordner python/):",
        *[f"  {p}" for p in pkgs],
    ]
    novnc = [p for p in content.rglob("novnc/LICENSE.txt")]
    if novnc:
        index.append(f"noVNC (Kursleiter-Version): {novnc[0].relative_to(content).as_posix()} und docs/, vendor/pako/")
    livekit = [p for p in content.rglob("kursraum/vendor/LICENSE-livekit-client")]
    if livekit:
        index.append(f"livekit-client (Kursraum): {livekit[0].relative_to(content).as_posix()} – darin gebündelte "
                     "Bibliotheken: siehe THIRD-PARTY-LICENSES")
    if deb:
        index += ["Bibliotheken aus Debian/Ubuntu-Paketen (Ordner debian/, Quelltexte: sources.debian.org bzw. "
                  "packages.ubuntu.com):", *[f"  {p}" for p in deb]]
    if unknown:  # nichts ohne Lizenztext ausliefern
        raise SystemExit("Bibliotheken ohne Paket und ohne Lizenztext: " + ", ".join(unknown))
    (out / "INDEX.txt").write_text("\n".join(index) + "\n", "utf-8")
    print("\n".join(index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
