#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""livekit-client (Apache-2.0) für den Kursraum ins Paket holen – beim Bauen, nicht im Repository.

Lädt das offizielle npm-Paket (feste Version, feste SHA-256 des Archivs), prüft die Prüfsumme und legt nur
``dist/livekit-client.umd.js`` samt Lizenz nach src/bonys_agents/resources/kursraum/vendor/ (beide Editionen).
Die Version steht auch in ``bonys_agents.kursraum.LIVEKIT_VERSION`` und in THIRD-PARTY-LICENSES. Wiederholbar: ist
die richtige Version schon da, passiert nichts.

    python packaging/fetch-livekit.py            # holen bzw. prüfen
    python packaging/fetch-livekit.py --force    # neu holen
"""

from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "2.22.3"
SHA256 = "0f920230001fcbfdccb0bcd2efffd64da8594808908953ed466d4c39c1529fa3"
URL = f"https://registry.npmjs.org/livekit-client/-/livekit-client-{VERSION}.tgz"

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "src" / "bonys_agents" / "resources" / "kursraum" / "vendor"
CACHE = ROOT / "build" / f"livekit-client-{VERSION}.tgz"
FILES = {"package/dist/livekit-client.umd.js": "livekit-client.umd.js", "package/LICENSE": "LICENSE-livekit-client"}


def download() -> bytes:
    if CACHE.is_file():
        data = CACHE.read_bytes()
        if hashlib.sha256(data).hexdigest() == SHA256:
            return data
    print(f"Lade livekit-client {VERSION} von {URL} …")
    with urllib.request.urlopen(URL, timeout=120) as r:  # noqa: S310 – feste https-Adresse
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != SHA256:
        sys.exit(f"Prüfsumme von livekit-client stimmt nicht (erwartet {SHA256}, bekommen {got}) – Abbruch.")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(data)
    return data


def main() -> None:
    stamp = DEST / "VERSION"
    if "--force" not in sys.argv and stamp.is_file() and stamp.read_text().strip() == f"{VERSION} {SHA256}" \
            and all((DEST / name).is_file() for name in FILES.values()):
        print(f"livekit-client {VERSION} ist schon da ({DEST}).")
        return
    data = download()
    tmp = DEST.with_name("vendor.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name in FILES:
                (tmp / FILES[m.name]).write_bytes(tar.extractfile(m).read())
    missing = [name for name in FILES.values() if not (tmp / name).is_file()]
    if missing:
        sys.exit(f"Im Archiv von livekit-client fehlt {', '.join(missing)} – Abbruch.")
    (tmp / "VERSION").write_text(f"{VERSION} {SHA256}\n")
    shutil.rmtree(DEST, ignore_errors=True)
    tmp.rename(DEST)
    print(f"livekit-client {VERSION} nach {DEST}")


if __name__ == "__main__":
    main()
