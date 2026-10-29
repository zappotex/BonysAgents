#!/usr/bin/env python3
# Check (as root): at least one tunnel is imported in Bony's VPN, and no user's Downloads folder (/home/*/Downloads)
# still contains a .conf. Only looks at file names – opens no file, never reads a key.
# No output: exit 0 = done, 1 = not yet.
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
