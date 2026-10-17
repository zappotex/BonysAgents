# SPDX-License-Identifier: GPL-3.0-or-later
"""Editionen aus einem Quellcode: „Bony's Agents“ (Anwender) und „Bony's Agents Kursleiter“.

- **Anwender**: alles für eigene Agent-PCs und alles, was Teilnehmer einer Schulung brauchen (Kurs beitreten,
  Vorführung im Browser öffnen, Hilfe anfordern). Das Unterpaket ``bonys_agents.trainer`` ist beim Bauen gar nicht
  erst enthalten – kein Server-Code, kein noVNC.
- **Kursleiter**: zusätzlich ``bonys_agents.trainer`` (Vorlage im Netz freigeben, Vorführen, Hilfe-Anfragen
  annehmen, künftig das Kursleiter-Dashboard).

``EDITION`` steht im gebauten Programm fest (``_edition.py``, schreibt ``packaging/bonys-agents.spec``). Ohne diese
Datei (Quellcode, Tests) gilt ``BONYS_AGENTS_EDITION`` – sonst entscheidet, ob ``trainer/`` vorhanden ist. Kursleiter
ist nur möglich, wenn ``trainer/`` wirklich da ist.

Beide Editionen teilen Datenordner, Einstellungen, Agent-PCs und Vorlagen – ein Wechsel ändert daran nichts.
"""

from __future__ import annotations

import importlib.util
import os

ANWENDER = "anwender"
KURSLEITER = "kursleiter"
NAMES = {ANWENDER: "Bony's Agents", KURSLEITER: "Bony's Agents Kursleiter"}
LABELS = {ANWENDER: "Anwender", KURSLEITER: "Kursleiter"}
# Paketnamen bzw. Dateinamen im Release je Edition
PACKAGES = {ANWENDER: "bonys-agents", KURSLEITER: "bonys-agents-kursleiter"}
FILE_PREFIX = {ANWENDER: "BonysAgents", KURSLEITER: "BonysAgents-Kursleiter"}
ENV = "BONYS_AGENTS_EDITION"


def trainer_available() -> bool:
    """Ist das Kursleiter-Unterpaket in dieser Installation vorhanden?"""
    try:
        return importlib.util.find_spec("bonys_agents.trainer") is not None
    except (ImportError, ValueError):
        return False


def _built() -> str:
    try:
        from bonys_agents._edition import EDITION as built  # type: ignore[import-not-found]
    except ImportError:
        return ""
    return str(built)


def detect() -> str:
    wanted = (_built() or os.environ.get(ENV, "")).strip().lower()
    have = trainer_available()
    if wanted == ANWENDER or (wanted == KURSLEITER and not have):
        return ANWENDER
    if wanted == KURSLEITER:
        return KURSLEITER
    return KURSLEITER if have else ANWENDER


EDITION = detect()
IS_TRAINER = EDITION == KURSLEITER
NAME = NAMES[EDITION]
LABEL = LABELS[EDITION]
PACKAGE = PACKAGES[EDITION]


def version_text(version: str) -> str:
    """„0.19.0 (Kursleiter)“ – für --version, doctor und den Info-Dialog."""
    return f"{version} ({LABEL})"


def require_trainer(what: str) -> str | None:
    """None, wenn es hier Kursleiter-Funktionen gibt – sonst eine verständliche Meldung."""
    if IS_TRAINER:
        return None
    return (f"{what} gibt es nur in „{NAMES[KURSLEITER]}“. Teilnehmer brauchen sie nicht – sie treten mit "
            f"„bonys-agents join“ bzw. „Kurse“ → „Schulung im Netzwerk beitreten“ bei. Die Kursleiter-Version gibt "
            f"es hier: {download_url()}")


def download_url() -> str:
    from bonys_agents import REPO_URL

    return f"{REPO_URL}/releases/latest"
