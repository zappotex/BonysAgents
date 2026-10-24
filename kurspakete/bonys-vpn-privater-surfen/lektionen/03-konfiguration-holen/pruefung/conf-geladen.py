#!/usr/bin/env python3
# Prüfung: Im Download-Ordner liegt eine WireGuard-Konfiguration (.conf) oder ein ZIP-Archiv mit Konfigurationen.
# Sieht nur auf Dateinamen und -größen – öffnet keine Datei, liest also nie einen Schlüssel.
# Gibt nichts aus: Exit 0 = geschafft, 1 = noch nicht.
import pathlib
import subprocess
import sys

ordner = {pathlib.Path.home() / "Downloads"}
try:
    xdg = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    if xdg:
        ordner.add(pathlib.Path(xdg))
except (OSError, subprocess.SubprocessError):
    pass
for o in ordner:
    for datei in sorted(o.iterdir()) if o.is_dir() else []:
        try:
            if datei.suffix.lower() in (".conf", ".zip") and datei.is_file() and 0 < datei.stat().st_size < 1_000_000:
                sys.exit(0)
        except OSError:
            continue
sys.exit(1)
