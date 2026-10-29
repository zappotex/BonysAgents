# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitgelieferte Kurspakete (``kurspakete/``) für das Release: signierbar vorbereiten und als ``.bonyspaket`` packen.

Zwei Schritte, dazwischen signiert die Release-Aktion jede ``pruefsummen.txt`` mit minisign (Release-Schlüssel):

    python3 packaging/kurspakete.py vorbereiten BAU      # BAU/<id>/ … + pruefsummen.txt
    minisign -S -s KEY -m BAU/<id>/pruefsummen.txt …     # → pruefsummen.txt.minisig
    python3 packaging/kurspakete.py packen BAU AUSGABE   # AUSGABE/<id>-<version>.bonyspaket + kurspakete-index.json

``kurspakete-index.json`` ist die ``index.json`` für das öffentliche Repo zappotex/bonys-agents-kurspakete (Dateien
dort unter ``pakete/``) – siehe docs/RELEASE.md. Braucht nur platformdirs, psutil und pycdlib (kein Qt).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bonys_agents import kurslauf, kurspaket  # noqa: E402

QUELLE = ROOT / "kurspakete"
INDEX = "kurspakete-index.json"
UNTERORDNER = "pakete"     # im Repo bonys-agents-kurspakete


def vorbereiten(bau: Path, quelle: Path = QUELLE) -> list[Path]:
    """Jedes Kurspaket geprüft nach ``bau/<id>/`` kopieren (ohne Versteckte) und ``pruefsummen.txt`` schreiben."""
    ordner = []
    for basis in sorted(p for p in quelle.iterdir() if (p / kurspaket.PAKET_JSON).is_file()):
        paket = kurspaket.laden(basis)
        kurspaket.geheimnisse_pruefen(basis)
        ziel = bau / paket.id
        if ziel.exists():
            shutil.rmtree(ziel)
        for p, rel in kurspaket._dateien(basis):
            if rel.as_posix() in (kurslauf.PRUEFSUMMEN, kurslauf.SIGNATUR):
                continue
            (ziel / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, ziel / rel)
        (ziel / kurslauf.PRUEFSUMMEN).write_text(kurslauf.pruefsummen_text(ziel), encoding="utf-8")
        ordner.append(ziel)
    return ordner


def packen(bau: Path, ausgabe: Path, public_key: str | None = None) -> Path:
    """Signierte Ordner aus ``vorbereiten`` packen und ``kurspakete-index.json`` schreiben. Bricht ab, wenn eine
    Signatur fehlt oder nicht zum Release-Schlüssel passt."""
    ausgabe.mkdir(parents=True, exist_ok=True)
    eintraege = []
    for ordner in sorted(p for p in bau.iterdir() if (p / kurspaket.PAKET_JSON).is_file()):
        paket = kurspaket.laden(ordner)
        pruef = kurslauf.signatur_pruefen(paket, public_key) if public_key else kurslauf.signatur_pruefen(paket)
        if not pruef:
            raise SystemExit(f"{paket.id}: Signatur fehlt oder passt nicht (pruefsummen.txt.minisig).")
        datei = kurspaket.packen(ordner, ausgabe / kurspaket.dateiname(paket))
        eintraege.append({
            "id": paket.id, "name": paket.name, "version": paket.version, "stufe": paket.stufe,
            "dauer_minuten": paket.dauer_minuten, "beschreibung": paket.beschreibung, "sprache": paket.sprache,
            **({"entwurf": True} if paket.entwurf else {}),
            "datei": f"{UNTERORDNER}/{datei.name}",
            "sha256": hashlib.sha256(datei.read_bytes()).hexdigest(), "groesse": datei.stat().st_size,
        })
    index = ausgabe / INDEX
    index.write_text(json.dumps({"format": kurspaket.KATALOG_FORMAT, "pakete": eintraege}, ensure_ascii=False,
                                indent=2) + "\n", encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="befehl", required=True)
    v = sub.add_parser("vorbereiten")
    v.add_argument("bau", type=Path)
    p = sub.add_parser("packen")
    p.add_argument("bau", type=Path)
    p.add_argument("ausgabe", type=Path)
    a = ap.parse_args(argv)
    if a.befehl == "vorbereiten":
        for o in vorbereiten(a.bau):
            print(o / kurslauf.PRUEFSUMMEN)
    else:
        print(packen(a.bau, a.ausgabe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
