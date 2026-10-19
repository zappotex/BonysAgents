#!/usr/bin/env python3
# Prüfung: Hermes ist eingerichtet (Vorlage aus Bony's Agents).
# Liest NUR die Einträge model.provider und model.default aus ~/.hermes/config.yaml – nie .env oder auth.json,
# dort stehen Zugangsdaten. Gibt nichts aus: Exit 0 = eingerichtet, 1 = noch nicht.
import pathlib
import re
import sys

datei = pathlib.Path.home() / ".hermes" / "config.yaml"
try:
    zeilen = datei.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeDecodeError):
    sys.exit(1)
werte, im_model, einzug = {}, False, None
for zeile in zeilen:
    if not zeile.strip() or zeile.lstrip().startswith("#"):
        continue
    tiefe = len(zeile) - len(zeile.lstrip())
    if tiefe == 0:
        im_model = zeile.split("#")[0].strip() == "model:"
        einzug = None
        continue
    if im_model:
        einzug = tiefe if einzug is None else einzug
        m = re.match(r"\s+(provider|default)\s*:\s*(.*?)\s*(#.*)?$", zeile)
        if tiefe == einzug and m:
            werte[m.group(1)] = m.group(2).strip("\"'")
sys.exit(0 if werte.get("provider") and werte.get("default") else 1)
