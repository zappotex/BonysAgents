#!/usr/bin/env python3
# Prüfung: PdfCraft ist installiert (~/.local/bin/pdfcraft-cli) und als MCP-Server „pdfcraft“ bei Hermes eingetragen.
# Liest NUR die Namen unter mcp_servers in ~/.hermes/config.yaml – nie .env oder auth.json, dort stehen
# Zugangsdaten. Gibt nichts aus: Exit 0 = eingerichtet, 1 = noch nicht.
import os
import pathlib
import re
import sys

home = pathlib.Path.home()
cli = home / ".local" / "bin" / "pdfcraft-cli"
if not (cli.is_file() and os.access(cli, os.X_OK)):
    sys.exit(1)
try:
    zeilen = (home / ".hermes" / "config.yaml").read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeDecodeError):
    sys.exit(1)
im_mcp, einzug, server = False, None, set()
for zeile in zeilen:
    if not zeile.strip() or zeile.lstrip().startswith("#"):
        continue
    tiefe = len(zeile) - len(zeile.lstrip())
    if tiefe == 0:
        im_mcp = zeile.split("#")[0].strip() == "mcp_servers:"
        einzug = None
        continue
    if im_mcp:
        einzug = tiefe if einzug is None else einzug
        m = re.match(r"\s+[\"']?([A-Za-z0-9_-]+)[\"']?\s*:\s*$", zeile)
        if tiefe == einzug and m:
            server.add(m.group(1))
sys.exit(0 if "pdfcraft" in server else 1)
