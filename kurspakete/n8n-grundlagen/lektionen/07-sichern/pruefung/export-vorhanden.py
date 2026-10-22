#!/usr/bin/env python3
# Prüfung: Im Download-Ordner liegt ein aus n8n exportierter Workflow (.json) mit „RSS Feed Trigger“.
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
        knoten = daten.get("nodes") if isinstance(daten, dict) else None
        if isinstance(knoten, list) and any(isinstance(k, dict) and k.get("type") == "n8n-nodes-base.rssFeedReadTrigger"
                                            for k in knoten):
            sys.exit(0)
sys.exit(1)
