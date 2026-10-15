#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prüft ein fertig gebündeltes Programm (PyInstaller-Ordner, .app oder entpacktes Paket) auf seine Edition.

    python packaging/check-edition.py dist/bonys-agents anwender
    python packaging/check-edition.py dist/bonys-agents-kursleiter kursleiter

Anwender: weder Dateien noch Python-Module aus ``bonys_agents.trainer``, kein noVNC – nicht nur ausgeblendet.
Kursleiter: trainer-Module, Seiten der Vorführung und noVNC sind da. In beiden Fällen steht die Edition fest im
Programm (``bonys_agents._edition``), und pycdlib (LGPL) liegt als lose, austauschbare .py-Dateien daneben.
Durchsucht werden alle Dateien und die Modul-Archive (PYZ) in den Programmen.
Ohne PyInstaller (z. B. für ein entpacktes .deb ohne Bau-Umgebung) werden nur die Dateien geprüft.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editions  # noqa: E402

EXECUTABLES = ("BonysAgents", "bonys-agents", "BonysAgents.exe", "bonys-agents.exe")


def files(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def modules(root: Path) -> tuple[set[str], dict[str, object]]:
    """Alle Python-Module aus den PYZ-Archiven der Programme und den Code von ``bonys_agents._edition``."""
    try:
        from PyInstaller.archive.readers import PKG_ITEM_PYZ, CArchiveReader
    except ImportError:
        return set(), {}
    names: set[str] = set()
    edition_code: dict[str, object] = {}
    for exe in (p for p in root.rglob("*") if p.is_file() and p.name in EXECUTABLES):
        try:
            pkg = CArchiveReader(str(exe))
        except Exception:  # noqa: BLE001 – keine PyInstaller-Datei
            continue
        for entry, info in pkg.toc.items():
            if info[-1] != PKG_ITEM_PYZ:
                continue
            pyz = pkg.open_embedded_archive(entry)
            names |= set(pyz.toc)
            if "bonys_agents._edition" in pyz.toc:
                edition_code[exe.name] = pyz.extract("bonys_agents._edition")
    return names, edition_code


def check(root: Path, edition: str) -> list[str]:
    problems = []
    all_files = files(root)
    trainer_files = [f for f in all_files if "/bonys_agents/trainer/" in f"/{f}" or "novnc" in f.lower()]
    mods, edition_code = modules(root)
    trainer_mods = sorted(m for m in mods if editions.is_trainer_path(m))
    if edition == "anwender":
        problems += [f"Datei aus der Kursleiter-Version: {f}" for f in trainer_files[:20]]
        problems += [f"Modul aus der Kursleiter-Version: {m}" for m in trainer_mods[:20]]
    else:
        for want in ("trainer/resources/novnc/core/rfb.js", "trainer/resources/present/view.html"):
            if not any(f.endswith(want) for f in all_files):
                problems.append(f"fehlt: …/{want}")
        if mods and not {"bonys_agents.trainer.present", "bonys_agents.trainer.share_server",
                         "bonys_agents.trainer.helpdesk", "bonys_agents.trainer.gui.present_dialog"} <= set(mods):
            problems.append("Kursleiter-Module fehlen im Programm")
    if not any(f.endswith("licenses/INDEX.txt") for f in all_files):
        problems.append("Lizenztexte fehlen (licenses/INDEX.txt) – packaging/collect-licenses.py ausführen")
    # LGPL-2.1 §6: pycdlib muss austauschbar als lose Dateien daliegen, nicht im Archiv der Programmdatei
    if not any(f.endswith("pycdlib/pycdlib.py") for f in all_files):
        problems.append("pycdlib fehlt als lose Datei (…/pycdlib/pycdlib.py) – module_collection_mode in der .spec?")
    if any(m == "pycdlib" or m.startswith("pycdlib.") for m in mods):
        problems.append("pycdlib steckt im Archiv der Programmdatei (PYZ) – muss austauschbar daneben liegen")
    if mods:
        if not edition_code:
            problems.append("bonys_agents._edition fehlt im Programm")
        for exe, code in edition_code.items():
            consts = getattr(code, "co_consts", ())
            if edition not in consts:
                problems.append(f"{exe}: Edition im Programm ist nicht „{edition}“ ({consts})")
    return problems


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in editions.EDITIONS:
        print(__doc__)
        return 2
    root, edition = Path(sys.argv[1]), sys.argv[2]
    if not root.is_dir():
        print(f"Ordner fehlt: {root}", file=sys.stderr)
        return 2
    problems = check(root, edition)
    if problems:
        print(f"Edition „{edition}“ in {root}: NICHT in Ordnung", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    mods, _ = modules(root)
    print(f"Edition „{edition}“ in {root}: in Ordnung ({len(files(root))} Dateien, {len(mods)} Module geprüft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
