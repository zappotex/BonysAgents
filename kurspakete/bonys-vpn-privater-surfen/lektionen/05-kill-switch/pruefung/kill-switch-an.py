#!/usr/bin/env python3
# Prüfung (als root): Kill-Switch an (Regeln geladen), ein Tunnel verbindet sich automatisch und ist verbunden.
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
ks = status.get("killswitch") or {}
automatisch = [t for t in status.get("tunnels", []) if t.get("autostart")]
verbunden = status.get("active") is not None
sys.exit(0 if ks.get("enabled") and ks.get("active") and automatisch and verbunden else 1)
