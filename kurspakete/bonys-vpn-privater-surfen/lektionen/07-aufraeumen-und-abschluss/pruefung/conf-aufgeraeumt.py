#!/usr/bin/env python3
# Prüfung (als root): In Bony's VPN ist mindestens ein Tunnel importiert, und in keinem Download-Ordner der Benutzer
# (/home/*/Downloads) liegt noch eine .conf. Sieht nur auf Dateinamen – öffnet keine Datei, liest nie einen Schlüssel.
# Gibt nichts aus: Exit 0 = geschafft, 1 = noch nicht.
import json
import pathlib
import pwd
import subprocess
import sys

try:
    aus = subprocess.run(["bonys-vpn", "status", "--json"], capture_output=True, text=True, timeout=20)
    if not json.loads(aus.stdout).get("tunnels"):
        sys.exit(1)
except (OSError, subprocess.SubprocessError, ValueError):
    sys.exit(1)
for benutzer in pwd.getpwall():
    if benutzer.pw_uid < 1000 or not benutzer.pw_dir.startswith("/home/"):
        continue
    downloads = pathlib.Path(benutzer.pw_dir) / "Downloads"
    try:
        if any(d.suffix.lower() == ".conf" for d in downloads.iterdir()):
            sys.exit(1)
    except OSError:
        continue
sys.exit(0)
