#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sammelt alle Texte aus ``tr("…")`` und gleicht sie mit dem englischen Katalog ab.

    python packaging/i18n-sammeln.py              neue Texte als leere Einträge in den Katalog, Bericht
    python packaging/i18n-sammeln.py --pruefen    nur prüfen; Exit 1 bei offenen, verwaisten oder falschen Einträgen
    python packaging/i18n-sammeln.py --aufraeumen zusätzlich verwaiste Einträge entfernen

Gesucht wird in ``src/bonys_agents`` nach ``tr(…)``, ``i18n.tr(…)`` und dem Marker ``n_(…)`` mit einem festen Text
als erstem Argument (per ``ast``, Texte werden nicht ausgeführt). ``tr(variable)`` zählt der Bericht nur – der Text
dazu muss an seiner Quelle mit ``n_("…")`` markiert sein (``--stellen`` zeigt die Aufrufe).
"""

from __future__ import annotations

import argparse
import ast
import json
import string
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bonys_agents"
KATALOG = SRC / "resources" / "i18n" / "en.json"


@dataclass
class Bericht:
    texte: dict[str, list[str]] = field(default_factory=dict)   # Text → Fundstellen „datei:zeile“
    berechnet: list[str] = field(default_factory=list)          # tr() ohne festen Text
    offen: list[str] = field(default_factory=list)              # im Code, Übersetzung fehlt oder leer
    verwaist: list[str] = field(default_factory=list)           # im Katalog, nicht mehr im Code
    platzhalter: list[str] = field(default_factory=list)        # Platzhalter weichen ab

    @property
    def sauber(self) -> bool:
        return not (self.offen or self.verwaist or self.platzhalter)


def _ist_tr(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id in ("tr", "n_")
    return isinstance(func, ast.Attribute) and func.attr in ("tr", "n_") and \
        isinstance(func.value, ast.Name) and func.value.id == "i18n"


def sammeln(src: Path = SRC) -> tuple[dict[str, list[str]], list[str]]:
    texte: dict[str, list[str]] = {}
    berechnet: list[str] = []
    for datei in sorted(src.rglob("*.py")):
        rel = datei.relative_to(src.parent).as_posix()
        for node in ast.walk(ast.parse(datei.read_text("utf-8"), str(datei))):
            if not (isinstance(node, ast.Call) and _ist_tr(node.func) and node.args):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                texte.setdefault(arg.value, []).append(f"{rel}:{node.lineno}")
            else:
                berechnet.append(f"{rel}:{node.lineno}")
    # Seite des Kursraums (tr('…') in kursraum.js, data-tr in index.html) – Regeln in kursraum.seiten_texte()
    seite = src / "resources" / "kursraum"
    if (seite / "kursraum.js").is_file():
        sys.path.insert(0, str(src.parent))
        from bonys_agents import kursraum

        for text in kursraum.seiten_texte():
            texte.setdefault(text, []).append(f"{seite.relative_to(src.parent).as_posix()}")
    # Seiten der Kursleiter-Version im Browser (Vorführung, Hilfe)
    from bonys_agents import i18n

    vorfuehrung = src / "trainer" / "resources" / "present"
    if vorfuehrung.is_dir():
        for text in i18n.seiten_texte(vorfuehrung):
            texte.setdefault(text, []).append(vorfuehrung.relative_to(src.parent).as_posix())
    return texte, berechnet


def platzhalter(text: str) -> set[str]:
    try:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError:   # z. B. einzelne „{“ – zählt als eigener Fehler
        return {"<ungültig>"}


def katalog_laden(pfad: Path = KATALOG) -> dict[str, str]:
    return json.loads(pfad.read_text("utf-8")) if pfad.is_file() else {}


def katalog_schreiben(daten: dict[str, str], pfad: Path = KATALOG) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(dict(sorted(daten.items())), ensure_ascii=False, indent=1) + "\n", "utf-8")


def pruefen(texte: dict[str, list[str]], katalog: dict[str, str], berechnet: list[str] | None = None) -> Bericht:
    b = Bericht(texte=texte, berechnet=berechnet or [])
    for text in sorted(texte):
        uebersetzt = katalog.get(text)
        if not uebersetzt:
            b.offen.append(text)
        elif platzhalter(text) != platzhalter(uebersetzt):
            b.platzhalter.append(text)
    b.verwaist = sorted(k for k in katalog if k not in texte)
    return b


def _kurz(text: str) -> str:
    return json.dumps(text if len(text) <= 70 else text[:67] + "…", ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Texte aus tr() sammeln und mit dem englischen Katalog abgleichen.")
    ap.add_argument("--pruefen", action="store_true", help="nur prüfen, Katalog nicht ändern")
    ap.add_argument("--aufraeumen", action="store_true", help="verwaiste Einträge entfernen")
    ap.add_argument("--stellen", action="store_true", help="tr()-Aufrufe ohne festen Text einzeln zeigen")
    args = ap.parse_args(argv)

    texte, berechnet = sammeln()
    katalog = katalog_laden()
    if not args.pruefen:
        neu = {t: "" for t in texte if t not in katalog}
        katalog.update(neu)
        if args.aufraeumen:
            katalog = {k: v for k, v in katalog.items() if k in texte}
        if neu or args.aufraeumen:
            katalog_schreiben(katalog)
        print(f"{len(neu)} neue Texte in {KATALOG.relative_to(ROOT)}")
    b = pruefen(texte, katalog, berechnet)
    print(f"{len(texte)} Texte, {len(texte) - len(b.offen)} übersetzt, {len(b.offen)} offen")
    for titel, liste in (("Offen", b.offen), ("Platzhalter weichen ab", b.platzhalter),
                         ("Verwaist (nicht mehr im Code)", b.verwaist)):
        for text in liste:
            print(f"  {titel}: {_kurz(text)}  {' '.join(texte.get(text, []))}")
    if berechnet:
        print(f"{len(berechnet)} Aufrufe ohne festen Text (Quelle mit n_() markieren)")
    for stelle in berechnet if args.stellen else []:
        print(f"  Hinweis: ohne festen Text in {stelle}")
    return 0 if b.sauber else 1


if __name__ == "__main__":
    sys.exit(main())
