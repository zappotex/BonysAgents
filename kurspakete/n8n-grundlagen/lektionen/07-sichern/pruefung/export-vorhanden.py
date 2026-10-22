#!/usr/bin/env python3
# Prüfung: Im Download-Ordner liegt ein aus n8n exportierter Workflow (.json) mit „RSS Feed Trigger“ – einzeln
# („Export JSON“) oder als Liste (n8n export:workflow).
# Gibt nichts aus: Exit 0 = geschafft, 1 = noch nicht.
import json
import pathlib
import subprocess
import sys

ordner = {pathlib.Path.home() / "Downloads"}
try:
    xdg = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    if xdg:
        ordner.add(pathlib.Path(xdg))
except (OSError, subprocess.SubprocessError):
    pass
for o in ordner:
    for datei in sorted(o.glob("*.json")) if o.is_dir() else []:
        try:
            if datei.stat().st_size > 5_000_000:
                continue
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for wf in daten if isinstance(daten, list) else [daten]:
            knoten = wf.get("nodes") if isinstance(wf, dict) else None
            typen = {k.get("type") for k in knoten if isinstance(k, dict)} if isinstance(knoten, list) else set()
            if "n8n-nodes-base.rssFeedReadTrigger" in typen:
                sys.exit(0)
sys.exit(1)
