#!/usr/bin/env python3
# Check (as root): a published (active) workflow in n8n contains "RSS Feed Trigger" and a Telegram node.
# Only reads the node types of the workflows from n8n's database – never credentials (they're stored encrypted
# in another table). No output: exit 0 = done, 1 = not yet.
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
