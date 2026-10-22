#!/usr/bin/env python3
# Prüfung: ~/Agent-Dateien/pdf/rechnungen-gesamt.pdf hat genau zwei Seiten und enthält beide Rechnungsnummern.
# Liest Seitenzahl und Text mit pdfinfo/pdftotext (im Agent-PC vorhanden). Gibt nichts aus: Exit 0 = geschafft.
import pathlib
import re
import subprocess
import sys

datei = pathlib.Path.home() / "Agent-Dateien" / "pdf" / "rechnungen-gesamt.pdf"
if not datei.is_file():
    sys.exit(1)


def ausgabe(*befehl: str) -> str:
    try:
        return subprocess.run(befehl, capture_output=True, text=True, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        sys.exit(1)


seiten = re.search(r"^Pages:\s+(\d+)", ausgabe("pdfinfo", str(datei)), re.MULTILINE)
text = ausgabe("pdftotext", "-q", str(datei), "-")
sys.exit(0 if seiten and seiten.group(1) == "2" and "2026-031" in text and "2026-042" in text else 1)
