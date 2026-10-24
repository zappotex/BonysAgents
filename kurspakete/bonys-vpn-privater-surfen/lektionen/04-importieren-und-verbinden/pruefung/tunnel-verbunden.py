#!/usr/bin/env python3
# Prüfung (als root): In Bony's VPN ist ein Tunnel verbunden und hat einen Handshake mit dem Server.
# Fragt nur „bonys-vpn status --json“ – darin stehen keine Schlüssel (docs/cli.md von Bony's VPN).
# Gibt nichts aus: Exit 0 = geschafft, 1 = noch nicht.
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
