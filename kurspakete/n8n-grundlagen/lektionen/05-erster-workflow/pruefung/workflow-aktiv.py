#!/usr/bin/env python3
# Prüfung (als root): Ein veröffentlichter (aktiver) Workflow in n8n enthält „RSS Feed Trigger“ und einen
# Telegram-Knoten. Liest aus der Datenbank von n8n nur die Knoten-Typen der Workflows – nie Zugangsdaten
# (die liegen verschlüsselt in einer anderen Tabelle). Gibt nichts aus: Exit 0 = geschafft, 1 = noch nicht.
import json
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    zeilen = con.execute("SELECT nodes FROM workflow_entity WHERE active = 1 AND NOT isArchived").fetchall()
except sqlite3.Error:
    sys.exit(1)
for (nodes,) in zeilen:
    try:
        typen = {k.get("type") for k in json.loads(nodes or "[]") if isinstance(k, dict)}
    except (ValueError, TypeError):
        continue
    if "n8n-nodes-base.rssFeedReadTrigger" in typen and "n8n-nodes-base.telegram" in typen:
        sys.exit(0)
sys.exit(1)
