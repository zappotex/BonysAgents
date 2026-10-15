#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""noVNC (MPL-2.0) für die Live-Vorführung ins Paket holen – beim Bauen, nicht im Repository.

Lädt das offizielle Release-Archiv von GitHub (feste Version, feste SHA-256), prüft die Prüfsumme und legt nur die
Bibliothek (core/, vendor/pako/) samt Lizenztexten nach src/bonys_agents/resources/novnc/. Wiederholbar: ist die
richtige Version schon da, passiert nichts.

    python packaging/fetch-novnc.py            # holen bzw. prüfen
    python packaging/fetch-novnc.py --force    # neu holen
"""

from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.7.0"
SHA256 = "b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6"
URL = f"https://github.com/novnc/noVNC/archive/refs/tags/v{VERSION}.tar.gz"

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "src" / "bonys_agents" / "resources" / "novnc"
CACHE = ROOT / "build" / f"novnc-v{VERSION}.tar.gz"
PREFIX = f"noVNC-{VERSION}/"
KEEP_FILES = {"LICENSE.txt", "AUTHORS", "docs/LICENSE.MPL-2.0", "vendor/pako/LICENSE"}


def wanted(rel: str) -> bool:
    if rel in KEEP_FILES:
        return True
    return (rel.startswith("core/") or rel.startswith("vendor/pako/lib/")) and rel.endswith(".js")


def download() -> bytes:
    if CACHE.is_file():
        data = CACHE.read_bytes()
        if hashlib.sha256(data).hexdigest() == SHA256:
            return data
    print(f"Lade noVNC {VERSION} von {URL} …")
    with urllib.request.urlopen(URL, timeout=120) as r:  # noqa: S310 – feste https-Adresse
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != SHA256:
        sys.exit(f"Prüfsumme von noVNC stimmt nicht (erwartet {SHA256}, bekommen {got}) – Abbruch.")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(data)
    return data


def main() -> None:
    stamp = DEST / "VERSION"
    if "--force" not in sys.argv and stamp.is_file() and stamp.read_text().strip() == f"{VERSION} {SHA256}" \
            and (DEST / "core" / "rfb.js").is_file():
        print(f"noVNC {VERSION} ist schon da ({DEST}).")
        return
    data = download()
    tmp = DEST.with_name("novnc.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile() or not m.name.startswith(PREFIX):
                continue
            rel = m.name[len(PREFIX):]
            if ".." in rel.split("/") or rel.startswith("/") or not wanted(rel):
                continue
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(m).read())
            count += 1
    if not (tmp / "core" / "rfb.js").is_file():
        sys.exit("Im noVNC-Archiv fehlt core/rfb.js – Abbruch.")
    (tmp / "VERSION").write_text(f"{VERSION} {SHA256}\n")
    shutil.rmtree(DEST, ignore_errors=True)
    tmp.rename(DEST)
    print(f"noVNC {VERSION}: {count} Dateien nach {DEST}")


if __name__ == "__main__":
    main()
