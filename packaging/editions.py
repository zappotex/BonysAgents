# SPDX-License-Identifier: GPL-3.0-or-later
"""Was in welche Edition gehört – genutzt vom PyInstaller-Bauplan, den Paket-Skripten und den Tests.

    Anwender   („Bony's Agents“)             ohne bonys_agents/trainer/ (kein Server-Code, kein noVNC)
    Kursleiter („Bony's Agents Kursleiter“)  mit trainer/ und noVNC

Edition wählen: ``pyinstaller packaging/bonys-agents.spec -- --edition kursleiter`` oder Umgebungsvariable
``BONYS_EDITION=kursleiter`` (Standard: anwender).
"""

from __future__ import annotations

import os

EDITIONS = ("anwender", "kursleiter")
DIST_NAMES = {"anwender": "bonys-agents", "kursleiter": "bonys-agents-kursleiter"}
DISPLAY_NAMES = {"anwender": "Bony's Agents", "kursleiter": "Bony's Agents Kursleiter"}
TRAINER_PACKAGE = "bonys_agents.trainer"


def parse(argv: list[str], env: dict | None = None) -> str:
    """Edition aus ``--edition X`` (hinter ``--``) bzw. ``BONYS_EDITION`` – sonst „anwender“."""
    env = os.environ if env is None else env
    value = env.get("BONYS_EDITION", "")
    for i, arg in enumerate(argv):
        if arg == "--edition" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--edition="):
            value = arg.split("=", 1)[1]
    value = (value or "anwender").strip().lower()
    if value not in EDITIONS:
        raise SystemExit(f"Unbekannte Edition „{value}“ – erlaubt: {', '.join(EDITIONS)}")
    return value


def is_trainer_path(dest: str) -> bool:
    """Gehört eine Datei/ein Modul (Zielpfad im Paket bzw. Modulname) zum Kursleiter-Teil?"""
    d = dest.replace("\\", "/").replace(".", "/")
    return d == "bonys_agents/trainer" or d.startswith("bonys_agents/trainer/") or "/novnc" in d.lower() \
        or d.lower().startswith("novnc")


def keep(edition: str, dest: str) -> bool:
    return edition == "kursleiter" or not is_trainer_path(dest)
