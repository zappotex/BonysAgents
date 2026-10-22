#!/usr/bin/env python3
# Prüfung (als root): In n8n ist ein Konto angelegt. Fragt in der Datenbank von n8n (Docker-Volume n8n_data) nur,
# ob ein Benutzer mit E-Mail-Adresse existiert – liest weder Adressen noch Passwörter noch Zugangsschlüssel.
# Gibt nichts aus: Exit 0 = Konto angelegt, 1 = noch nicht.
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    anzahl = con.execute("SELECT COUNT(*) FROM user WHERE email IS NOT NULL AND email != ''").fetchone()[0]
except sqlite3.Error:
    sys.exit(1)
sys.exit(0 if anzahl else 1)
