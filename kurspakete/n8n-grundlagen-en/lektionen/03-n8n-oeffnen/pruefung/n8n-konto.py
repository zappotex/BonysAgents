#!/usr/bin/env python3
# Check (as root): an account is created in n8n. Only asks n8n's database (Docker volume n8n_data) whether a user
# with an e-mail address exists – reads neither addresses nor passwords nor access keys.
# No output: exit 0 = account created, 1 = not yet.
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    anzahl = con.execute("SELECT COUNT(*) FROM user WHERE email IS NOT NULL AND email != ''").fetchone()[0]
except sqlite3.Error:
    sys.exit(1)
sys.exit(0 if anzahl else 1)
