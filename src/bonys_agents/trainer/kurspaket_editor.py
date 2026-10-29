# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspaket-Editor (nur Kursleiter-Edition): anlegen, bearbeiten, speichern, duplizieren, prüfen, PDFs.

Der Editor bearbeitet einen Paket-Ordner – in der Bibliothek (``Datenordner/kurspakete/<id>``) oder irgendwo sonst,
z. B. in einem Git-Repository. Gespeichert wird in zwei Schritten: Erst entsteht das ganze Kurspaket in einem
Bauordner und wird dort vollständig geprüft (Format, Geheimnis-Prüfung) – erst dann wird der Ziel-Ordner Datei für
Datei abgeglichen. Versteckte Dateien (``.git``, ``.herkunft.json``) bleiben dabei unangetastet; eine Signatur
(``pruefsummen.txt``) fällt weg, weil sie nach einer Änderung nicht mehr passt.

Skripte aus Kurspaketen laufen auch hier **nur im Agent-PC** (``kurslauf``) – „Kurspaket prüfen“ spielt die
Lektionen in einem Test-Agent-PC durch. Python-Skripte werden lokal nur übersetzt (``compile``), nie ausgeführt;
Bash-Skripte prüft ``bash -n`` im Agent-PC.
"""

from __future__ import annotations

import ast
import base64
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from bonys_agents import __version__, apps, desktops, kurslauf, kurspaket, qemu, storage, templates, vm
from bonys_agents.procutil import clean_env, no_window_flags
from bonys_agents.i18n import tr

ProgressFn = Callable[[float, str], None]
TEST_SCHNAPPSCHUSS = "bonys-paket-test"
BILD_DATEIEN = "Bilder (*.png *.jpg *.jpeg *.gif *.webp)"
MAX_STARTDATEN = 1400 * 1024        # Daten im Startskript (gepackt) – das Skript darf höchstens 2 MB groß sein
PANDOC_URL = "https://github.com/jgm/pandoc/releases"
TYPST_URL = "https://github.com/typst/typst/releases"
_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
_BILD_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)|<(https?://[^>\s]+)>")
_GAST_PFAD = re.compile(r"^~/[A-Za-z0-9._ /-]{1,200}$")
_DIENST = re.compile(r"^[A-Za-z0-9@._:-]{1,120}$")


def slug(text: str, max_len: int = 58) -> str:
    """„Übung 1: Dateien“ → „uebung-1-dateien“ (für IDs und Lektionsordner)."""
    s = re.sub(r"[^a-z0-9]+", "-", text.translate(_UMLAUTE).lower()).strip("-")
    return s[:max_len].rstrip("-")


def version_erhoehen(version: str, teil: str = "patch") -> str:
    """1.2.3 → 1.2.4 (patch), 1.3.0 (minor) oder 2.0.0 (major)."""
    t = list(kurspaket.version_tupel(version)) + [0, 0, 0]
    major, minor, patch = t[:3]
    if teil == "major":
        return f"{major + 1}.0.0"
    if teil == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def bearbeitbar(paket: kurspaket.Kurspaket) -> bool:
    """Mitgelieferte Kurspakete gehören zum Programm – dafür gibt es „Eigene Fassung“ bzw. „Duplizieren“."""
    return not paket.mitgeliefert and os.access(paket.pfad, os.W_OK)


def in_bibliothek(ordner: Path) -> bool:
    return kurspaket._innerhalb(kurspaket.bibliothek_dir(), Path(ordner)) and \
        Path(ordner).resolve() != kurspaket.bibliothek_dir().resolve()


def _herkunft_eigen(ordner: Path) -> None:
    storage.write_json(Path(ordner) / kurspaket.HERKUNFT, {"quelle": kurspaket.EIGEN, "geaendert": int(time.time())})


# ---------------------------------------------------------------- Neu, Duplizieren
ABLAUFPLAN_VORLAGE = """---
title: {name}
subtitle: Ablaufplan für die Kursleitung
---

## Überblick

| Zeit | Block | Inhalt |
|---|---|---|
| 0:00 | Ankommen | Begrüßung, Agent-PCs starten |

## Block 1 – Ankommen

::: tipp
Notizen und Lösungen für die Kursleitung stehen hier – Teilnehmer sehen den Ablaufplan nicht.
:::
"""
ANLEITUNG_VORLAGE = """# {titel}

1. Erster Schritt
2. Zweiter Schritt

::: tipp
Hier steht ein Tipp für Teilnehmer.
:::
"""


def neu_anlegen(name: str, stufe: str = "anfaenger", paket_id: str = "", autor: str = "") -> kurspaket.Kurspaket:
    """Neues, gültiges Kurspaket in der Bibliothek anlegen (mit Ablaufplan und einer ersten Lektion)."""
    name = name.strip()
    paket_id = paket_id or slug(name, 60)
    if not kurspaket.ID_RE.match(paket_id):
        raise kurspaket.PaketFehler(tr("Die Kennung muss 3 bis 60 Zeichen lang sein – nur Kleinbuchstaben, Ziffern und "
                                       "Bindestrich (z. B. „einfuehrung-hermes-agent“)."))
    if any(p.id == paket_id for p in kurspaket.liste()):
        raise kurspaket.PaketFehler(tr("Es gibt schon ein Kurspaket mit der Kennung „{paket_id}“.", paket_id=paket_id))
    paket = kurspaket.Kurspaket(id=paket_id, name=name, beschreibung="Worum geht es in diesem Kurspaket?",
                                stufe=stufe, version="0.1.0", autor=autor.strip(), min_version=_min_version(),
                                entwurf=True)
    lek = kurspaket.Lektion(ordner="01-ankommen", titel="Ankommen", dauer_minuten=10, art="Mitmachen")
    paket.lektionen.append(lek)
    bib = kurspaket.bibliothek_dir()
    bib.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".neu-", dir=bib))
    try:
        d = tmp / "paket"
        (d / kurspaket.LEKTIONEN / lek.ordner).mkdir(parents=True)
        (d / kurspaket.PAKET_JSON).write_text(kurspaket.json_text(kurspaket.paket_json(paket)), encoding="utf-8")
        (d / kurspaket.ABLAUFPLAN).write_text(ABLAUFPLAN_VORLAGE.format(name=name), encoding="utf-8")
        (d / kurspaket.LEKTIONEN / lek.ordner / kurspaket.ANLEITUNG).write_text(
            ANLEITUNG_VORLAGE.format(titel=lek.titel), encoding="utf-8")
        kurspaket.laden(d)
        _herkunft_eigen(d)
        os.replace(d, bib / paket_id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return kurspaket.laden(bib / paket_id, kurspaket.EIGEN)


def _min_version() -> str:
    """Neue Pakete brauchen mindestens die Version mit Kurspaketen – oder die laufende, wenn die älter ist (Tests)."""
    return kurspaket.MIN_VERSION if kurspaket.version_vergleich(kurspaket.MIN_VERSION, __version__) <= 0 \
        else __version__


def duplizieren(paket: kurspaket.Kurspaket, neue_id: str, neuer_name: str = "") -> kurspaket.Kurspaket:
    """Kopie in der Bibliothek. Mit derselben ID entsteht eine „eigene Fassung“ eines mitgelieferten Pakets (sie
    verdeckt das mitgelieferte, der Fortschritt bleibt) – mit neuer ID ein neues Kurspaket (Version 0.1.0)."""
    if not kurspaket.ID_RE.match(neue_id):
        raise kurspaket.PaketFehler(tr("Die Kennung muss 3 bis 60 Zeichen lang sein – nur Kleinbuchstaben, Ziffern und "
                                       "Bindestrich."))
    bib = kurspaket.bibliothek_dir()
    if (bib / neue_id).exists():
        raise kurspaket.PaketFehler(tr("In der Bibliothek gibt es schon ein Kurspaket „{neue_id}“.", neue_id=neue_id))
    if neue_id != paket.id and any(p.id == neue_id for p in kurspaket.liste()):
        raise kurspaket.PaketFehler(tr("Es gibt schon ein Kurspaket mit der Kennung „{neue_id}“.", neue_id=neue_id))
    bib.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".kopie-", dir=bib))
    try:
        d = tmp / "paket"
        kurspaket._ordner_kopieren(paket.pfad, d)
        for name in (kurslauf.PRUEFSUMMEN, kurslauf.SIGNATUR):
            (d / name).unlink(missing_ok=True)
        if neue_id != paket.id:
            daten = kurspaket.paket_json(kurspaket.laden(d))
            daten.update(id=neue_id, name=(neuer_name or f"{paket.name} (Kopie)").strip(), version="0.1.0")
            (d / kurspaket.PAKET_JSON).write_text(kurspaket.json_text(daten), encoding="utf-8")
        kurspaket.laden(d)
        _herkunft_eigen(d)
        os.replace(d, bib / neue_id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return kurspaket.laden(bib / neue_id, kurspaket.EIGEN)


# ---------------------------------------------------------------- Speichern
@dataclass
class LektionEntwurf:
    """Eine Lektion, wie der Editor sie hält. ``quelle``: bisheriger Ordner (Bilder usw.), None = neue Lektion."""
    lektion: kurspaket.Lektion
    quelle: Path | None = None
    anleitung: str = ""
    kursleitung: str = ""
    quiz: list[kurspaket.Frage] = field(default_factory=list)
    pruef_skript: str = ""          # Inhalt, wenn lektion.pruefung.typ == "skript"
    loesung_skript: str = ""        # optional, nur für „Kurspaket prüfen“
    start_skript: str = ""          # Inhalt, wenn lektion.start gesetzt ist

    @classmethod
    def aus_lektion(cls, lek: kurspaket.Lektion) -> LektionEntwurf:
        def lesen(rel: str) -> str:
            return kurspaket._lesen(lek.pfad / rel) if rel and (lek.pfad / rel).is_file() else ""

        p = lek.pruefung
        return cls(lektion=replace(lek, pruefung=replace(p) if p else None, start=replace(lek.start) if lek.start
                                   else None),
                   quelle=lek.pfad, anleitung=lek.anleitung() if lek.anleitung_datei.is_file() else "",
                   kursleitung=lek.kursleitung(), quiz=lek.quiz(),
                   pruef_skript=lesen(p.skript) if p and p.typ == kurspaket.SKRIPT else "",
                   loesung_skript=lesen(p.loesung) if p and p.typ == kurspaket.SKRIPT else "",
                   start_skript=lesen(lek.start.skript) if lek.start else "")


@dataclass
class Entwurf:
    """Das ganze Kurspaket im Editor. ``paket`` trägt Steckbrief und Rezept; ``quelle`` ist der bisherige Ordner."""
    paket: kurspaket.Kurspaket
    quelle: Path
    ablaufplan: str = ""
    handout: str = ""
    lektionen: list[LektionEntwurf] = field(default_factory=list)

    @classmethod
    def laden(cls, ordner: Path) -> Entwurf:
        paket = kurspaket.laden(ordner)
        return cls(paket=paket, quelle=Path(ordner), ablaufplan=paket.ablaufplan(), handout=paket.handout(),
                   lektionen=[LektionEntwurf.aus_lektion(lek) for lek in paket.lektionen])


_VERWALTET = {kurspaket.ANLEITUNG, kurspaket.KURSLEITUNG, kurspaket.QUIZ}


def _ordnernamen(entwurf: Entwurf) -> list[str]:
    """Lektionsordner in der aktuellen Reihenfolge: Nummer = Position, der Name bleibt (neu: aus dem Titel)."""
    namen: list[str] = []
    for i, le in enumerate(entwurf.lektionen, 1):
        alt = le.quelle.name if le.quelle is not None else ""
        rest = alt[3:] if kurspaket.ORDNER_RE.match(alt) else (slug(le.lektion.titel, 50) or "lektion")
        name = f"{i:02d}-{rest}"
        n = 2
        while name in namen:
            name = f"{i:02d}-{rest[:50]}-{n}"
            n += 1
        namen.append(name)
    return namen


def _skriptpfad(rel: str, standard: str) -> str:
    return rel or standard


def bauen(entwurf: Entwurf, ziel: Path) -> kurspaket.Kurspaket:
    """Kurspaket vollständig in ``ziel`` (neu) erzeugen und prüfen – PaketFehler/GeheimnisGefunden mit Meldung."""
    quelle = entwurf.quelle
    ziel.mkdir(parents=True)
    oben = {kurspaket.PAKET_JSON, kurspaket.ABLAUFPLAN, kurspaket.HANDOUT, kurslauf.PRUEFSUMMEN, kurslauf.SIGNATUR}
    for p, rel in kurspaket._dateien(quelle):
        if rel.parts[0] == kurspaket.LEKTIONEN or (len(rel.parts) == 1 and rel.name in oben) or p.is_symlink():
            continue
        (ziel / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, ziel / rel)
    (ziel / kurspaket.ABLAUFPLAN).write_text(entwurf.ablaufplan, encoding="utf-8")
    if entwurf.handout.strip():
        (ziel / kurspaket.HANDOUT).write_text(entwurf.handout, encoding="utf-8")
    paket = replace(entwurf.paket, lektionen=[])
    for le, ordner in zip(entwurf.lektionen, _ordnernamen(entwurf), strict=True):
        d = ziel / kurspaket.LEKTIONEN / ordner
        d.mkdir(parents=True)
        if le.quelle is not None and le.quelle.is_dir():
            for p, rel in kurspaket._dateien(le.quelle):
                if p.is_symlink() or (len(rel.parts) == 1 and rel.name in _VERWALTET):
                    continue
                if rel.parts[0] in ("pruefung", "start") and rel.suffix.lower() in kurspaket.SKRIPT_ENDUNGEN:
                    continue        # Skripte schreibt der Editor selbst (unten) – alte fallen weg
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, d / rel)
        (d / kurspaket.ANLEITUNG).write_text(le.anleitung, encoding="utf-8")
        if le.kursleitung.strip():
            (d / kurspaket.KURSLEITUNG).write_text(le.kursleitung, encoding="utf-8")
        if le.quiz:
            (d / kurspaket.QUIZ).write_text(kurspaket.json_text(kurspaket.quiz_json(le.quiz)), encoding="utf-8")
        lek = replace(le.lektion, ordner=ordner, pfad=d)
        p = lek.pruefung
        if p is not None and p.typ == kurspaket.SKRIPT:
            p = replace(p, skript=_skriptpfad(p.skript, "pruefung/pruefen.sh"))
            _skript_schreiben(d / p.skript, le.pruef_skript)
            if le.loesung_skript.strip():
                p = replace(p, loesung=_skriptpfad(p.loesung, "pruefung/loesung.sh"))
                _skript_schreiben(d / p.loesung, le.loesung_skript)
            else:
                p = replace(p, loesung="")
            lek.pruefung = p
        elif p is not None:
            lek.pruefung = replace(p, skript="", loesung="")
        if lek.start is not None:
            lek.start = replace(lek.start, skript=_skriptpfad(lek.start.skript, "start/start.sh"))
            _skript_schreiben(d / lek.start.skript, le.start_skript)
        paket.lektionen.append(lek)
    (ziel / kurspaket.PAKET_JSON).write_text(kurspaket.json_text(kurspaket.paket_json(paket)), encoding="utf-8")
    fertig = kurspaket.laden(ziel)
    kurspaket.geheimnisse_pruefen(ziel)
    return fertig


def _skript_schreiben(pfad: Path, inhalt: str) -> None:
    if not inhalt.strip():
        raise kurspaket.PaketFehler(tr("Das Skript „{name}/{name2}“ ist leer.", name=pfad.parent.name, name2=pfad.name))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    # Immer Unix-Zeilenenden – im Agent-PC laufen bash und python3
    pfad.write_text(inhalt.replace("\r\n", "\n").rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    pfad.chmod(0o644)


def _abgleichen(bau: Path, ziel: Path) -> None:
    """``ziel`` an ``bau`` angleichen: geänderte Dateien schreiben, entfallene löschen – Versteckte bleiben."""
    neu = {rel.as_posix(): p for p, rel in kurspaket._dateien(bau)}
    for p, rel in list(kurspaket._dateien(ziel)):
        if rel.as_posix() not in neu:
            p.unlink()
    for rel, p in neu.items():
        out = ziel / rel
        if out.is_symlink():
            out.unlink()
        if out.is_file() and out.read_bytes() == p.read_bytes():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
        shutil.copyfile(p, tmp)
        os.replace(tmp, out)
    for d in sorted((x for x in ziel.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
        rel = d.relative_to(ziel)
        if not kurspaket._ueberspringen(rel.parts) and not any(d.iterdir()):
            d.rmdir()


def speichern(entwurf: Entwurf, ziel: Path | None = None) -> kurspaket.Kurspaket:
    """Entwurf prüfen und nach ``ziel`` (Standard: der bisherige Ordner) schreiben. Bei einem Fehler bleibt der
    Ordner unverändert. Liegt er in der Bibliothek, gilt das Kurspaket danach als „selbst erstellt“."""
    ziel = Path(ziel or entwurf.quelle)
    basis = kurspaket.bibliothek_dir() if in_bibliothek(ziel) else None
    if basis is not None:
        basis.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".speichern-", dir=basis) as tmp:
        bau = Path(tmp) / "paket"
        paket = bauen(entwurf, bau)
        if paket.id != entwurf.paket.id:
            raise kurspaket.PaketFehler(tr("Die Kennung eines Kurspakets lässt sich nicht ändern – dafür "
                                           "„Duplizieren“."))
        ziel.mkdir(parents=True, exist_ok=True)
        if (ziel / kurspaket.PAKET_JSON).is_file():
            alt = kurspaket.laden(ziel)
            if alt.id != paket.id:
                raise kurspaket.PaketFehler(tr("Im Ordner „{name}“ liegt ein anderes Kurspaket ({id}).",
                                               name=ziel.name, id=alt.id))
        _abgleichen(bau, ziel)
    if basis is not None:
        _herkunft_eigen(ziel)
    gespeichert = kurspaket.laden(ziel, kurspaket.EIGEN if basis is not None else kurspaket.DATEI)
    if gespeichert.skripte():
        kurslauf.zustimmen(gespeichert)     # eigene Skripte – nicht bei jedem Durcharbeiten nachfragen
    return gespeichert


# ---------------------------------------------------------------- Vorlagen für Prüfskripte
def vorlage_datei_existiert(pfad: str, enthaelt: str = "") -> str:
    """Prüfskript „Datei existiert (und enthält …)“. ``pfad`` im Agent-PC, z. B. „~/Kurs/einkaufsliste.txt“."""
    pfad = pfad.strip()
    if not _GAST_PFAD.match(pfad) or ".." in pfad.split("/"):
        raise ValueError(tr("Der Pfad muss mit „~/“ beginnen (im Persönlichen Ordner), z. B. ~/Kurs/einkaufsliste.txt"))
    if "\n" in enthaelt:
        raise ValueError(tr("Der gesuchte Text muss einzeilig sein."))
    zeilen = ["#!/bin/bash",
              f"# Prüfung: {pfad} existiert" + (f" und enthält „{enthaelt}“" if enthaelt else "")
              + " (Vorlage aus Bony's Agents)",
              f'datei="$HOME"/{shlex.quote(pfad[2:])}',
              'test -s "$datei" || exit 1']
    if enthaelt:
        zeilen.append(f'grep -qiF -- {shlex.quote(enthaelt)} "$datei"')
    return "\n".join(zeilen) + "\n"


def vorlage_dienst_laeuft(dienst: str, benutzer: bool = False) -> str:
    """Prüfskript „Dienst läuft“ (systemd). ``benutzer``: Benutzerdienst (``systemctl --user``)."""
    dienst = dienst.strip()
    if not _DIENST.match(dienst):
        raise ValueError(tr("Ungültiger Dienstname (z. B. „docker“ oder „hermes-gateway.service“)."))
    if benutzer:
        return ("#!/bin/bash\n"
                f"# Prüfung: Benutzerdienst {dienst} läuft (Vorlage aus Bony's Agents) – Prüfung als „benutzer“\n"
                'export XDG_RUNTIME_DIR="/run/user/$(id -u)"\n'
                'export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"\n'
                f"systemctl --user is-active --quiet -- {shlex.quote(dienst)}\n")
    return ("#!/bin/bash\n"
            f"# Prüfung: Dienst {dienst} läuft (Vorlage aus Bony's Agents)\n"
            f"systemctl is-active --quiet -- {shlex.quote(dienst)}\n")


VORLAGE_HERMES = '''#!/usr/bin/env python3
# Prüfung: Hermes ist eingerichtet (Vorlage aus Bony's Agents).
# Liest NUR die Einträge model.provider und model.default aus ~/.hermes/config.yaml – nie .env oder auth.json,
# dort stehen Zugangsdaten. Gibt nichts aus: Exit 0 = eingerichtet, 1 = noch nicht.
import pathlib
import re
import sys

datei = pathlib.Path.home() / ".hermes" / "config.yaml"
try:
    zeilen = datei.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeDecodeError):
    sys.exit(1)
werte, im_model, einzug = {}, False, None
for zeile in zeilen:
    if not zeile.strip() or zeile.lstrip().startswith("#"):
        continue
    tiefe = len(zeile) - len(zeile.lstrip())
    if tiefe == 0:
        im_model = zeile.split("#")[0].strip() == "model:"
        einzug = None
        continue
    if im_model:
        einzug = tiefe if einzug is None else einzug
        m = re.match(r"\\s+(provider|default)\\s*:\\s*(.*?)\\s*(#.*)?$", zeile)
        if tiefe == einzug and m:
            werte[m.group(1)] = m.group(2).strip("\\"'")
# „auto“ steht schon in der Standard-Einstellung eines frisch installierten Hermes – das ist noch keine Wahl
anbieter = werte.get("provider", "")
sys.exit(0 if anbieter and anbieter.lower() != "auto" and werte.get("default") else 1)
'''


def vorlage_hermes_eingerichtet() -> str:
    return VORLAGE_HERMES


# ---------------------------------------------------------------- Aus dem Agent-PC übernehmen
def rezept_aus_agent_pc(machine: vm.VM, alt: kurspaket.Rezept | None = None) -> kurspaket.Rezept:
    """Rezept nach einem eingerichteten Agent-PC: Desktop, Programme, RAM, CPUs, Festplatte, Benutzer, Tastatur,
    Zeitzone – und die Vorlage, aus der er entstanden ist (wenn es sie hier gibt)."""
    c = machine.config
    vorlage = ""
    if c.template:
        try:
            vorlage = templates.get(c.template).name
        except (KeyError, OSError, ValueError, RuntimeError):
            vorlage = ""
    return kurspaket.Rezept(
        name=(alt.name if alt else "") or "agent-kurs", desktop=c.desktop if c.desktop in desktops.DESKTOPS
        else desktops.DEFAULT, apps=[a for a in c.apps if a in apps.APPS and not apps.APPS[a].hidden],
        ram_mb=c.ram_mb, cpus=c.cpus, disk_gb=c.disk_gb, username=c.username, keyboard=c.keyboard,
        timezone=c.timezone, vorlage=vorlage, vorlage_sha256=(alt.vorlage_sha256 if alt and alt.vorlage == vorlage
                                                              else ""))


def startskript_aus_agent_pc(machine: vm.VM, ordner: str = "~/Kurs") -> str:
    """Startskript, das ``ordner`` (im Persönlichen Ordner des Agent-PCs) so wiederherstellt, wie er jetzt ist.

    Der Ordner wird über den Gast-Agent gepackt gelesen (nur Daten – hier wird nichts davon ausgeführt). Das Skript
    läuft später als Benutzer des Agent-PCs (``als: benutzer``) und packt die Daten dort wieder aus."""
    ordner = ordner.strip().rstrip("/")
    if not _GAST_PFAD.match(ordner) or ".." in ordner.split("/"):
        raise ValueError(tr("Der Ordner muss mit „~/“ beginnen, z. B. ~/Kurs"))
    if not kurslauf.bereit(machine):
        raise kurslauf.NichtBereit(tr("Der Agent-PC muss laufen und fertig eingerichtet sein."))
    user = machine.config.username
    if not vm.USERNAME_RE.match(user):
        raise ValueError(tr("ungültiger Benutzername"))
    rel = ordner[2:]
    befehl = ('cd "$HOME" && test -d "$1" || exit 3; n=$(du -sk -- "$1" | cut -f1); '
              f'[ "$n" -le {MAX_STARTDATEN // 1024 * 8} ] || exit 4; '
              'tar --numeric-owner --owner=0 --group=0 -czf - -- "$1" | base64 -w0')
    args = ["-k", "3", "60", "/usr/sbin/runuser", "-u", user, "--", "/usr/bin/env", "-i", f"HOME=/home/{user}",
            "PATH=/usr/bin:/bin", "/bin/sh", "-c", befehl, "sh", rel]
    try:
        with qemu.GuestAgent(machine.qga_endpoint(), timeout=5) as ga:
            rc, out, _err = ga.exec("/usr/bin/timeout", args, timeout=80)
    except qemu.GuestAgentError:
        raise kurslauf.NichtBereit(tr("Der Agent-PC antwortet noch nicht – bitte warten, bis der Desktop da ist.")) \
            from None
    if rc == 3:
        raise ValueError(tr("Im Agent-PC gibt es den Ordner {ordner} nicht.", ordner=ordner))
    if rc == 4:
        raise ValueError(tr("Der Ordner {ordner} ist zu groß für ein Startskript (höchstens etwa 1 MB gepackt).",
                            ordner=ordner))
    if rc != 0 or not out.strip():
        raise RuntimeError(tr("Der Ordner {ordner} ließ sich nicht lesen (Code {rc}).", ordner=ordner, rc=rc))
    daten = out.strip()
    if len(daten) > MAX_STARTDATEN * 4 // 3 + 4 or not re.fullmatch(r"[A-Za-z0-9+/=]+", daten):
        raise ValueError(tr("Der Ordner {ordner} ist zu groß für ein Startskript (höchstens etwa 1 MB gepackt).",
                            ordner=ordner))
    base64.b64decode(daten, validate=True)
    zeilen = [daten[i:i + 76] for i in range(0, len(daten), 76)]
    return ("#!/bin/bash\n"
            f"# Startzustand: legt {ordner} so an, wie er im Agent-PC der Kursleitung war (Bony's Agents).\n"
            "# Läuft als Benutzer des Agent-PCs; vorhandene Dateien mit gleichem Namen werden ersetzt.\n"
            "set -e\n"
            'cd "$HOME"\n'
            "base64 -d <<'BONYS_DATEN' | tar --no-same-owner -xzf -\n"
            + "\n".join(zeilen) + "\nBONYS_DATEN\n")


def bildschirmfoto(machine: vm.VM, ziel: Path) -> Path:
    """Bildschirmfoto des laufenden Agent-PCs als PNG (QEMU ``screendump``)."""
    if not machine.is_running():
        raise kurslauf.NichtBereit(tr("Der Agent-PC läuft nicht – bitte zuerst starten."))
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bonys-foto-") as tmp:
        datei = Path(tmp) / "bild.png"
        with qemu.QMP(machine.qmp_endpoint(), timeout=20) as q:
            if q.text:
                out = q.hmp(f"screendump {datei} -f png").strip()
                if out:
                    raise RuntimeError(tr("Bildschirmfoto nicht möglich: {wert}", wert=out[-300:]))
            else:
                q.execute("screendump", filename=str(datei), format="png")
        for _ in range(50):
            if datei.is_file() and datei.stat().st_size > 0:
                break
            time.sleep(0.1)
        if not datei.is_file() or datei.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(tr("Bildschirmfoto nicht möglich (QEMU hat kein Bild geliefert)."))
        shutil.copyfile(datei, ziel)
    ziel.chmod(0o644)
    return ziel


def bild_name(ordner: Path, basis: str, endung: str = ".png") -> Path:
    """Freier Dateiname in ``ordner/bilder``: „bildschirm.png“, „bildschirm-2.png“ …"""
    basis = slug(basis, 40) or "bild"
    for n in range(1, 1000):
        p = Path(ordner) / "bilder" / (f"{basis}{endung}" if n == 1 else f"{basis}-{n}{endung}")
        if not p.exists():
            return p
    raise RuntimeError(tr("zu viele Bilder"))


# ---------------------------------------------------------------- PDF (Ablaufplan, Handout)
class WerkzeugFehlt(RuntimeError):
    """pandoc oder typst fehlt – die Meldung sagt, woher."""


def _vorlage_dir() -> Path:
    hier = Path(__file__).resolve().parent
    for k in (hier / "resources" / "handbuch-vorlage", hier.parent.parent.parent / "docs" / "handbuch" / "vorlage"):
        if (k / "pandoc.typ").is_file() and (k / "stil.typ").is_file():
            return k
    raise WerkzeugFehlt(tr("Die Vorlage für die PDFs fehlt in dieser Installation."))


def _werkzeug(name: str, url: str) -> str:
    pfad = shutil.which(name) or next((str(p) for p in (Path.home() / ".local" / "bin" / name,) if p.is_file()), None)
    if not pfad:
        raise WerkzeugFehlt(tr("Für PDFs braucht Bony's Agents die Programme „pandoc“ und „typst“ – „{name}“ fehlt. "
                               "Lade es von {url} (eine einzelne Datei, z. B. nach ~/.local/bin) und versuche es "
                               "dann noch einmal.", name=name, url=url))
    return pfad


def pdf_werkzeuge() -> tuple[str, str]:
    return _werkzeug("pandoc", PANDOC_URL), _werkzeug("typst", TYPST_URL)


def pdf_bauen(paket: kurspaket.Kurspaket, welches: str, ziel: Path, timeout: float = 120) -> Path:
    """Ablaufplan (``welches="ablaufplan"``) oder Handout als PDF – mit der Vorlage der Handbücher.

    Gebaut wird in einem eigenen Ordner, der nur die Vorlage, Logo/Hintergrund und die Bilder des Kurspakets enthält
    (typst ``--root``: andere Dateien des Rechners sind für das Dokument nicht erreichbar)."""
    quelle = paket.ablaufplan_datei if welches == "ablaufplan" else paket.handout_datei
    if not quelle.is_file():
        raise kurspaket.PaketFehler(tr("Dieses "
                                       "Kurspaket "
                                       "hat "
                                       "kein "
                                       "Handout.") if welches != "ablaufplan" else tr("Dieses Kurspaket hat keinen "
                                                                                      "Ablaufplan."))
    pandoc, typst = pdf_werkzeuge()
    vorlage = _vorlage_dir()
    resources = Path(kurspaket.__file__).resolve().parent / "resources"
    with tempfile.TemporaryDirectory(prefix="bonys-pdf-") as tmp:
        root = Path(tmp)
        hb = root / "docs" / "handbuch"
        shutil.copytree(vorlage, hb / "vorlage")
        (root / "src" / "bonys_agents" / "resources").mkdir(parents=True)
        for name in ("logo.png", "background.jpg"):
            shutil.copyfile(resources / name, root / "src" / "bonys_agents" / "resources" / name)
        if (paket.pfad / "bilder").is_dir():
            for p, rel in kurspaket._dateien(paket.pfad / "bilder"):
                if not p.is_symlink() and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                    (hb / "bilder" / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, hb / "bilder" / rel)
        text = kurspaket._lesen(quelle)
        (hb / "quelle.md").write_text(text, encoding="utf-8")
        # Feste Texte in der Sprache des Kurspakets (nicht der App): die Vorlage nimmt „sprache“ (de/en)
        sprache = kurspaket.sprache_kurz(paket.sprache)
        ablauf = ("Ablaufplan", "Ablaufplan für die Kursleitung") if sprache == "de" else \
            ("Schedule", "Schedule for the trainer")
        titel = paket.name + " – " + (ablauf[0] if welches == "ablaufplan" else "Handout")
        meta = {"title": paket.name, "subtitle": ablauf[1] if welches == "ablaufplan" else "Handout",
                "paket-autor": paket.autor, "paket-lizenz": paket.lizenz, "paket-version": paket.version,
                "sprache": sprache}
        storage.write_json(hb / "meta.json", meta)
        datum = time.strftime("%d.%m.%Y" if sprache == "de" else "%Y-%m-%d")
        art = "kompakt" if welches == "ablaufplan" else "kurz"
        befehl = [pandoc, "quelle.md", "-f", "markdown-citations-raw_attribute-raw_html-raw_tex", "-t", "typst",
                  "--template", "vorlage/pandoc.typ", "--lua-filter", "vorlage/filter.lua",
                  "--metadata-file", "meta.json", "-V", f"version={_v(paket.version)}", "-V", f"datum={datum}",
                  "-V", f"dokument={_v(titel)}", "-V", f"{art}=true", "-V", "kurspaket=true", "-o", "dok.typ"]
        _lauf(befehl, hb, timeout)
        _lauf([typst, "compile", "--root", str(root), "--font-path", "vorlage/schriften", "dok.typ", "dok.pdf"], hb,
              timeout)
        ziel = Path(ziel)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hb / "dok.pdf", ziel)
    return ziel


def _v(text: str) -> str:
    """Wert für ``-V`` (landet ungeschützt im Typst-Text): nur harmlose Zeichen."""
    return re.sub(r"[^\w .,:;()+–-]", "", text, flags=re.UNICODE)[:200]


def _lauf(befehl: list[str], cwd: Path, timeout: float) -> None:
    try:
        proc = subprocess.run(befehl, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              creationflags=no_window_flags(), env=clean_env())
    except subprocess.TimeoutExpired:
        raise RuntimeError(tr("{name} hat zu lange gebraucht.", name=Path(befehl[0]).name)) from None
    except OSError as e:
        raise RuntimeError(tr("{name} ließ sich nicht starten: {e}", name=Path(befehl[0]).name, e=e)) from None
    if proc.returncode != 0:
        meldung = (proc.stderr or proc.stdout).strip()[-800:]
        raise RuntimeError(tr("{name} meldet einen Fehler:\n{meldung}", name=Path(befehl[0]).name, meldung=meldung))


# ---------------------------------------------------------------- „Kurspaket prüfen“
OK, HINWEIS, WARNUNG, FEHLER = "ok", "hinweis", "warnung", "fehler"
ZEICHEN = {OK: "✓", HINWEIS: "ℹ", WARNUNG: "⚠", FEHLER: "✗"}


@dataclass
class Meldung:
    stufe: str
    text: str
    wo: str = ""

    def __str__(self) -> str:
        return f"{ZEICHEN.get(self.stufe, '•')} {self.wo + ': ' if self.wo else ''}{self.text}"


def _markdown_dateien(paket: kurspaket.Kurspaket) -> list[tuple[str, Path, Path]]:
    """(Anzeigename, Datei, Ordner für relative Bilder) aller Markdown-Texte des Kurspakets."""
    out = [(kurspaket.ABLAUFPLAN, paket.ablaufplan_datei, paket.pfad)]
    if paket.handout_datei.is_file():
        out.append((kurspaket.HANDOUT, paket.handout_datei, paket.pfad))
    for lek in paket.lektionen:
        out.append((f"{lek.ordner}/{kurspaket.ANLEITUNG}", lek.anleitung_datei, lek.pfad))
        if lek.kursleitung_datei.is_file():
            out.append((f"{lek.ordner}/{kurspaket.KURSLEITUNG}", lek.kursleitung_datei, lek.pfad))
    return out


def links(paket: kurspaket.Kurspaket) -> list[tuple[str, str]]:
    """(Fundort, Adresse) aller Links (Quellen und Markdown)."""
    out = [(f"{kurspaket.PAKET_JSON}, Quellen", q["url"]) for q in paket.quellen]
    for name, datei, _o in _markdown_dateien(paket):
        for m in _LINK_RE.finditer(kurspaket._lesen(datei)):
            url = m.group(1) or m.group(2)
            if re.match(r"^[a-z]+:", url):
                out.append((name, url))
    return out


def pruefen_statisch(ordner: Path) -> list[Meldung]:
    """Prüfung ohne Agent-PC: Format, Geheimnisse, Bilder, Links, Rezept, Skripte (Python nur übersetzt)."""
    try:
        paket = kurspaket.laden(ordner)
    except kurspaket.PaketFehler as e:
        return [Meldung(FEHLER, str(e))]
    m = [Meldung(OK, f"Format in Ordnung ({len(paket.lektionen)} Lektionen, Version {paket.version}).")]
    funde = kurspaket.geheimnisse_suchen(ordner)
    m += [Meldung(FEHLER, f.art + " – vor dem Weitergeben entfernen", f"{f.datei}, Zeile {f.zeile}") for f in funde]
    if not funde:
        m.append(Meldung(OK, "Keine Zugangsdaten oder persönlichen Daten gefunden."))
    for name, datei, basis in _markdown_dateien(paket):
        text = kurspaket._lesen(datei)
        for b in _BILD_RE.finditer(text):
            src = urllib.parse.unquote(b.group(1))
            if re.match(r"^[a-z]+:", src):
                m.append(Meldung(WARNUNG, f"Bild aus dem Internet ({src}) – Bony's Agents zeigt nur Bilder aus dem "
                                          "Kurspaket an.", name))
            elif not (basis / src).is_file() or not kurspaket._innerhalb(paket.pfad, basis / src):
                m.append(Meldung(FEHLER, f"Bild „{src}“ fehlt.", name))
        if re.search(r"<(?!https?://)[a-zA-Z/!][^>]*>", re.sub(r"`[^`]*`|```.*?```", "", text, flags=re.S)):
            m.append(Meldung(HINWEIS, "Enthält HTML – das zeigt Bony's Agents nicht an.", name))
        if not text.strip():
            m.append(Meldung(WARNUNG, "Ist leer.", name))
    for wo, url in links(paket):
        if not url.startswith("https://") and not url.startswith("mailto:"):
            m.append(Meldung(WARNUNG, f"Link ohne https ({url}) – Bony's Agents öffnet nur https-Links.", wo))
    r = paket.rezept
    for a in r.unbekannte_apps():
        m.append(Meldung(FEHLER, f"Programm „{a}“ aus dem Rezept kennt diese Version von Bony's Agents nicht.",
                         "Rezept"))
    for a in r.apps:
        if a in apps.APPS and apps.APPS[a].hidden:
            m.append(Meldung(WARNUNG, f"Programm „{a}“ lässt sich nicht mehr auswählen (veraltet).", "Rezept"))
    if r.vorlage and kurspaket.passende_vorlage(paket) is None:
        m.append(Meldung(HINWEIS, f"Die Vorlage „{r.vorlage}“ gibt es auf diesem Rechner nicht – Teilnehmer "
                                  "bekommen einen neuen Agent-PC nach dem Rezept.", "Rezept"))
    if kurspaket.version_vergleich(paket.min_version, __version__) < 0 and \
            kurspaket.version_vergleich(paket.min_version, kurspaket.MIN_VERSION) < 0:
        m.append(Meldung(HINWEIS, f"Mindestversion {paket.min_version} ist älter als die erste Version mit "
                                  f"Kurspaketen ({kurspaket.MIN_VERSION}).", kurspaket.PAKET_JSON))
    summe = sum(lek.dauer_minuten for lek in paket.lektionen)
    if paket.lektionen and summe and paket.dauer_minuten and abs(paket.dauer_minuten - summe) > max(
            15, paket.pause_minuten + 5):
        m.append(Meldung(HINWEIS, f"Die Lektionen dauern zusammen {kurspaket.dauer_text(summe)}, angegeben sind "
                                  f"{paket.dauer_text}.", kurspaket.PAKET_JSON))
    if paket.entwurf:
        m.append(Meldung(HINWEIS, "Ist als Entwurf markiert.", kurspaket.PAKET_JSON))
    for lek in paket.lektionen:
        wo = f"Lektion „{lek.titel}“"
        for art, rel in _skripte(lek):
            p = lek.pfad / rel
            if p.suffix.lower() == ".py":
                try:
                    compile(p.read_text(encoding="utf-8"), rel, "exec", flags=ast.PyCF_ONLY_AST)
                except SyntaxError as e:
                    m.append(Meldung(FEHLER, f"{art} „{rel}“: Syntaxfehler in Zeile {e.lineno}.", wo))
        if lek.pruefung and lek.pruefung.typ == kurspaket.SKRIPT and not lek.pruefung.loesung:
            m.append(Meldung(HINWEIS, "Prüfaufgabe ohne Lösungsskript – „Kurspaket prüfen“ kann nur testen, dass "
                                      "sie anfangs nicht erfüllt ist.", wo))
    return m


def _skripte(lek: kurspaket.Lektion) -> list[tuple[str, str]]:
    out = []
    if lek.start:
        out.append(("Startskript", lek.start.skript))
    if lek.pruefung and lek.pruefung.typ == kurspaket.SKRIPT:
        out.append(("Prüfskript", lek.pruefung.skript))
        if lek.pruefung.loesung:
            out.append(("Lösungsskript", lek.pruefung.loesung))
    return out


def links_pruefen(paket: kurspaket.Kurspaket, opener=None, timeout: float = 10) -> list[Meldung]:
    """Erreichbarkeit der https-Links (Quellen und Markdown) – meldet tote Links als „veraltet“."""
    opener = opener or urllib.request.urlopen
    m: list[Meldung] = []
    gesehen: set[str] = set()
    for wo, url in links(paket):
        if not url.startswith("https://") or url in gesehen:
            continue
        gesehen.add(url)
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": kurspaket.USER_AGENT})
        try:
            with opener(req, timeout=timeout) as r:
                code = getattr(r, "status", 200)
        except urllib.error.HTTPError as e:
            code = e.code
        except (OSError, ValueError) as e:
            m.append(Meldung(WARNUNG, f"Link nicht erreichbar: {url} ({getattr(e, 'reason', e)})", wo))
            continue
        if code in (405, 403):      # manche Server mögen kein HEAD – dann gilt die Seite als vorhanden
            continue
        if code >= 400:
            m.append(Meldung(WARNUNG, f"Link veraltet? {url} antwortet mit {code}.", wo))
    if not m:
        m.append(Meldung(OK, f"Alle {len(gesehen)} Links erreichbar." if gesehen else "Keine Links im Kurspaket."))
    return m


class Abgebrochen(Exception):
    pass


def durchspielen(machine: vm.VM, paket: kurspaket.Kurspaket, progress: ProgressFn | None = None,
                 abbrechen: Callable[[], bool] | None = None, zuruecksetzen: bool = True) -> list[Meldung]:
    """Lektionen im (Test-)Agent-PC durchspielen: je Lektion Startskript, Syntax der Skripte, Prüfung vor der Übung
    (darf noch nicht erfüllt sein), Lösungsskript und Prüfung danach (muss erfüllt sein).

    Vorher entsteht ein Schnappschuss; mit ``zuruecksetzen`` wird der Agent-PC danach darauf zurückgesetzt
    (herunterfahren, zurückspielen, neu starten). Alle Skripte laufen nur im Agent-PC."""
    if not kurslauf.bereit(machine):
        raise kurslauf.NichtBereit(tr("Der Test-Agent-PC muss laufen und fertig eingerichtet sein."))
    progress = progress or (lambda _f, _t: None)
    m: list[Meldung] = []
    kurslauf.startzustand_speichern(machine, TEST_SCHNAPPSCHUSS)
    try:
        n = max(1, len(paket.lektionen))
        for i, lek in enumerate(paket.lektionen):
            if abbrechen and abbrechen():
                raise Abgebrochen
            progress(i / n, tr("Lektion {wert} von {n}: {titel}", wert=i + 1, n=n, titel=lek.titel))
            m += _lektion_durchspielen(machine, lek)
        progress(1.0, tr("Fertig"))
    except Abgebrochen:
        m.append(Meldung(HINWEIS, "Abgebrochen."))
    finally:
        if zuruecksetzen:
            progress(1.0, tr("Setze den Test-Agent-PC zurück …"))
            try:
                if machine.is_running():
                    machine.stop()
                kurslauf._img("snapshot", "-a", TEST_SCHNAPPSCHUSS, str(machine.disk))
                kurslauf.startzustand_loeschen(machine, TEST_SCHNAPPSCHUSS)
                machine.start()
                m.append(Meldung(OK, "Test-Agent-PC auf den Stand vor der Prüfung zurückgesetzt."))
            except (RuntimeError, OSError, qemu.QemuNotFound) as e:
                m.append(Meldung(WARNUNG, f"Test-Agent-PC ließ sich nicht zurücksetzen: {e}"))
        else:
            m.append(Meldung(HINWEIS, f"Der Stand vor der Prüfung liegt als Schnappschuss „{TEST_SCHNAPPSCHUSS}“ "
                                      "auf der Festplatte des Test-Agent-PCs."))
    return m


def _rc_text(rc: int) -> str:
    if rc == kurslauf.ZEITLIMIT_RC:
        return tr("Zeitlimit überschritten")
    if rc == 127:
        return tr("ein Befehl fehlt im Agent-PC (Code 127 – veraltet?)")
    if rc == 126:
        return tr("ein Befehl lässt sich nicht ausführen (Code 126)")
    return f"Code {rc}"


def _lektion_durchspielen(machine: vm.VM, lek: kurspaket.Lektion) -> list[Meldung]:
    wo = f"Lektion „{lek.titel}“"
    m: list[Meldung] = []
    for art, rel in _skripte(lek):
        if rel.lower().endswith(".sh"):
            rc = kurslauf.im_agent_pc_ausfuehren(machine, lek.pfad / rel, "benutzer", 20, nur_syntax=True)
            if rc != 0:
                m.append(Meldung(FEHLER, f"{art} „{rel}“ hat einen Syntaxfehler (bash -n).", wo))
    if lek.start:
        rc = kurslauf.im_agent_pc_ausfuehren(machine, lek.pfad / lek.start.skript, lek.start.als, lek.start.zeitlimit)
        m.append(Meldung(OK, "Startskript läuft.", wo) if rc == 0
                 else Meldung(FEHLER, f"Startskript fehlgeschlagen ({_rc_text(rc)}).", wo))
    p = lek.pruefung
    if p is None:
        return m
    if p.typ != kurspaket.SKRIPT:
        erg = kurslauf.pruefen(machine, kurspaket.Kurspaket(id="test", name="", beschreibung="", stufe="anfaenger",
                                                             version="1"), lek)
        m.append(Meldung(OK if erg.geschafft else HINWEIS,
                         f"Eingebaute Prüfung „{p.typ}“: {'erfüllt' if erg.geschafft else 'nicht erfüllt'}.", wo))
        return m
    vorher = kurslauf.im_agent_pc_ausfuehren(machine, lek.pfad / p.skript, p.als, p.zeitlimit)
    if vorher == 0:
        m.append(Meldung(WARNUNG, "Die Prüfung ist schon vor der Übung erfüllt – prüft sie das Richtige?", wo))
    elif vorher in (kurslauf.ZEITLIMIT_RC, 126, 127):
        m.append(Meldung(FEHLER, f"Prüfskript: {_rc_text(vorher)}.", wo))
    if p.loesung:
        rc = kurslauf.im_agent_pc_ausfuehren(machine, lek.pfad / p.loesung, p.als, max(p.zeitlimit, 60))
        if rc != 0:
            m.append(Meldung(FEHLER, f"Lösungsskript fehlgeschlagen ({_rc_text(rc)}).", wo))
            return m
        nachher = kurslauf.im_agent_pc_ausfuehren(machine, lek.pfad / p.skript, p.als, p.zeitlimit)
        if nachher == 0:
            m.append(Meldung(OK, "Prüfung erkennt die Lösung.", wo))
        else:
            m.append(Meldung(FEHLER, f"Prüfung erkennt die Lösung nicht ({_rc_text(nachher)}).", wo))
    elif vorher not in (0, kurslauf.ZEITLIMIT_RC, 126, 127):
        m.append(Meldung(OK, "Prüfskript läuft (anfangs nicht erfüllt).", wo))
    return m
