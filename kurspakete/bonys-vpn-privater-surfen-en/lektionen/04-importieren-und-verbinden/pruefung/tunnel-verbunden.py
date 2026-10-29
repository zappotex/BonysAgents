#!/usr/bin/env python3
# Check (as root): a tunnel is connected in Bony's VPN and has a handshake with the server.
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
aktiv = status.get("active")
tunnel = next((t for t in status.get("tunnels", []) if t.get("name") == aktiv), None)
sys.exit(0 if tunnel and tunnel.get("handshake") else 1)
