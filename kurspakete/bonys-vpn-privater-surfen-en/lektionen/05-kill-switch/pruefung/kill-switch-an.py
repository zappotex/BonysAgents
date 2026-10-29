#!/usr/bin/env python3
# Check (as root): kill switch on (rules loaded), a tunnel connects automatically and is connected.
# Only asks "bonys-vpn status --json" – it contains no keys (docs/cli.md of Bony's VPN).
# No output: exit 0 = done, 1 = not yet.
import json
import subprocess
import sys

try:
    aus = subprocess.run(["bonys-vpn", "status", "--json"], capture_output=True, text=True, timeout=20)
    status = json.loads(aus.stdout)
except (OSError, subprocess.SubprocessError, ValueError):
    sys.exit(1)
ks = status.get("killswitch") or {}
automatisch = [t for t in status.get("tunnels", []) if t.get("autostart")]
verbunden = status.get("active") is not None
sys.exit(0 if ks.get("enabled") and ks.get("active") and automatisch and verbunden else 1)
