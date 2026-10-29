#!/usr/bin/env python3
# Check: the Downloads folder contains a WireGuard configuration (.conf) or a ZIP archive with configurations.
# Only looks at file names and sizes – opens no file, so it never reads a key.
# No output: exit 0 = done, 1 = not yet.
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
