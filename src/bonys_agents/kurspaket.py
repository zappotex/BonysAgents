# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspakete ``.bonyspaket``: Format, Prüfung, sicheres Entpacken, Bibliothek und Fortschritt.

Begriffe: Ein **Kurspaket** ist der *Inhalt* (Lektionen, Ablaufplan, Handout, Prüfungen, Quiz). Ein **Kurs** ist die
*Durchführung* – über das Bony-Netz (``bonys_agents.kurse``) oder als Schulung im eigenen Netz. Ein Kurspaket lässt
sich auch ohne Kurs allein durcharbeiten (Selbstlern-Modus).

Ein Kurspaket ist ein Ordner (mit Git versionierbar) oder dasselbe als ZIP-Datei ``.bonyspaket``::

    paket.json                       Steuerdatei (Schema in docs/kurspaket-format.md)
    ablaufplan.md                    für die Kursleitung: Blöcke mit Zeiten, Notizen, Lösungen
    handout.md                       optional: für Teilnehmer (zum Ausdrucken)
    bilder/                          optional
    lektionen/NN-name/anleitung.md   optional: Schritte für Teilnehmer neben dem Agent-PC
    lektionen/NN-name/kursleitung.md optional: Notizen zur Lektion – nur für die Kursleitung
    lektionen/NN-name/quiz.json      optional
    lektionen/NN-name/pruefung/      optional: Prüfskripte – laufen NUR im Agent-PC
    lektionen/NN-name/start/         optional: Startskript für den Startzustand – NUR im Agent-PC
    lektionen/NN-name/bilder/        optional

Kurspakete von Dritten sind fremde Daten: ``paket.json`` und ``quiz.json`` werden vollständig geprüft (verständliche
deutsche Meldungen als ``PaketFehler``), ZIP-Dateien vor und während des Entpackens (keine absoluten Pfade, kein
``..``, keine Links, Größen- und Anzahl-Grenzen, nur erlaubte Dateiarten). Dieses Modul führt nie ein Skript aus
einem Kurspaket aus – Prüf- und Startskripte gehen nur in den Agent-PC (Gast-Agent, Sitzung 2).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from bonys_agents import __version__, apps, desktops, distros, storage, vm

SUFFIX = ".bonyspaket"
FORMAT_ID = "bonys-agents-kurspaket"
FORMAT_VERSION = 1
MIN_VERSION = "0.23.0"            # erste Version von Bony's Agents mit Kurspaketen
PAKET_JSON = "paket.json"
ABLAUFPLAN = "ablaufplan.md"
HANDOUT = "handout.md"
LEKTIONEN = "lektionen"
ANLEITUNG = "anleitung.md"
KURSLEITUNG = "kursleitung.md"
QUIZ = "quiz.json"
HERKUNFT = ".herkunft.json"       # nur in der Bibliothek: woher das Kurspaket kam (nie Teil eines Pakets)

# Grenzen für fremde Pakete
MAX_GESAMT = 200 * 1024 * 1024    # entpackt
MAX_DATEI = 25 * 1024 * 1024
MAX_DATEIEN = 2000
MAX_TIEFE = 8
MAX_JSON = 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024        # Markdown-Dateien, Skripte
MAX_LEKTIONEN = 100
ENDUNGEN = {".md", ".txt", ".json", ".sh", ".py", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".minisig", ""}
SKRIPT_ENDUNGEN = {".sh", ".py"}

STUFEN = {"anfaenger": "Anfänger", "fortgeschritten": "Fortgeschritten", "experte": "Experte"}
STUFEN_REIHENFOLGE = {s: i for i, s in enumerate(STUFEN)}
LIZENZ_STANDARD = "CC-BY-SA-4.0"
PRUEF_ZEIT_STANDARD, PRUEF_ZEIT_MAX = 30, 300
START_ZEIT_STANDARD, START_ZEIT_MAX = 120, 1800
ALS = ("benutzer", "root")
SKRIPT = "skript"
# Prüfungen, die Bony's Agents selbst ausführt – ohne Code aus dem Kurspaket
EINGEBAUTE_PRUEFUNGEN = {
    "agent-pc-laeuft": "Der Agent-PC läuft und ist fertig eingerichtet.",
    "vorlage-vorhanden": "Es gibt mindestens eine Vorlage.",
}

MITGELIEFERT, DATEI, INTERNET, EIGEN, KURS = "mitgeliefert", "datei", "internet", "eigen", "kurs"
COMMUNITY = "community"          # aus dem Community-Katalog – nie „geprüft“ oder mitgeliefert
HERKUNFT_TEXT = {MITGELIEFERT: "mitgeliefert", DATEI: "aus Datei", INTERNET: "aus dem Internet",
                 EIGEN: "selbst erstellt", KURS: "aus einem Kurs",
                 COMMUNITY: "Community, von der Moderation geprüft"}

# Kurspakete aus dem Internet: Liste aus dem öffentlichen GitHub-Repo (index.json, Dateien unter pakete/).
KATALOG_REPO = "zappotex/bonys-agents-kurspakete"
KATALOG_URL = f"https://raw.githubusercontent.com/{KATALOG_REPO}/main/index.json"
KATALOG_ENV = "BONYS_AGENTS_PAKET_KATALOG"   # andere Adresse (Tests, eigener Katalog)
KATALOG_FORMAT = "bonys-agents-kurspaket-katalog"
COMMUNITY_URL = "https://kurse.bony23.de/katalog/index.json"
COMMUNITY_ENV = "BONYS_AGENTS_COMMUNITY_KATALOG"
COMMUNITY_EINSTELLUNG = "community_katalog"   # Einstellung; Standard: an
TIMEOUT = 20
USER_AGENT = f"bonys-agents/{__version__}"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
ORDNER_RE = re.compile(r"^[0-9]{2}-[a-z0-9][a-z0-9-]{0,58}$")
VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+){0,3}$")
SPRACHE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

ProgressFn = Callable[[float, str], None]
Opener = Callable[..., object]   # wie urllib.request.urlopen (für Tests austauschbar)


class PaketFehler(ValueError):
    """Kurspaket ungültig oder nicht lesbar – ``str(e)`` ist eine verständliche Meldung für die Oberfläche."""


class PaketExistiert(PaketFehler):
    """Ein Kurspaket mit derselben ID ist schon in der Bibliothek – ``ersetzen=True`` aktualisiert es."""

    def __init__(self, alt: Kurspaket, neu: Kurspaket):
        self.alt, self.neu = alt, neu
        vergleich = version_vergleich(neu.version, alt.version)
        if vergleich > 0:
            text = f"Version {neu.version} ist neuer als die vorhandene {alt.version} – aktualisieren?"
        elif vergleich == 0:
            text = f"Version {neu.version} ist schon vorhanden – erneut einspielen?"
        else:
            text = f"Achtung: Version {neu.version} ist ÄLTER als die vorhandene {alt.version} – trotzdem ersetzen?"
        super().__init__(f"Das Kurspaket „{alt.name}“ ist schon in der Bibliothek. {text}")


# ---------------------------------------------------------------- Hilfen
def version_tupel(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)


def version_vergleich(a: str, b: str) -> int:
    ta, tb = version_tupel(a), version_tupel(b)
    n = max(len(ta), len(tb))
    ta, tb = ta + (0,) * (n - len(ta)), tb + (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def dauer_text(minuten: int) -> str:
    if minuten <= 0:
        return "–"
    if minuten < 60:
        return f"{minuten} min"
    h, m = divmod(minuten, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"


def _feld(d: dict, key: str, wo: str, *, pflicht: bool = False, max_len: int = 200, mehrzeilig: bool = False,
          standard: str = "") -> str:
    if key not in d or d[key] is None:
        if pflicht:
            raise PaketFehler(f"{wo}: Angabe „{key}“ fehlt.")
        return standard
    wert = d[key]
    if not isinstance(wert, str):
        raise PaketFehler(f"{wo}: „{key}“ muss ein Text sein.")
    if pflicht and not wert.strip():
        raise PaketFehler(f"{wo}: „{key}“ darf nicht leer sein.")
    if len(wert) > max_len:
        raise PaketFehler(f"{wo}: „{key}“ ist zu lang (höchstens {max_len} Zeichen).")
    if not mehrzeilig and ("\n" in wert or "\t" in wert):
        raise PaketFehler(f"{wo}: „{key}“ muss einzeilig sein.")
    if _STEUERZEICHEN.search(wert.replace("\n", " ").replace("\t", " ")):
        raise PaketFehler(f"{wo}: „{key}“ enthält unerlaubte Steuerzeichen.")
    return wert.strip()


def _zahl(d: dict, key: str, wo: str, *, minimum: int, maximum: int, standard: int | None = None) -> int:
    if key not in d or d[key] is None:
        if standard is None:
            raise PaketFehler(f"{wo}: Angabe „{key}“ fehlt.")
        return standard
    wert = d[key]
    if not isinstance(wert, int) or isinstance(wert, bool):
        raise PaketFehler(f"{wo}: „{key}“ muss eine ganze Zahl sein.")
    if not minimum <= wert <= maximum:
        raise PaketFehler(f"{wo}: „{key}“ muss zwischen {minimum} und {maximum} liegen (gefunden: {wert}).")
    return wert


def _textliste(d: dict, key: str, wo: str, max_eintraege: int = 30, max_len: int = 300) -> list[str]:
    wert = d.get(key, [])
    if wert is None:
        return []
    if not isinstance(wert, list) or len(wert) > max_eintraege:
        raise PaketFehler(f"{wo}: „{key}“ muss eine Liste mit höchstens {max_eintraege} Texten sein.")
    return [_feld({key: x}, key, wo, pflicht=True, max_len=max_len) for x in wert]


def _relpfad(wert: str, wo: str, key: str, endungen: set[str]) -> str:
    """Relativer Pfad innerhalb des Lektionsordners (POSIX), ohne Ausbruch und ohne versteckte Teile."""
    p = PurePosixPath(wert)
    if not wert or "\\" in wert or p.is_absolute() or ".." in p.parts or any(t.startswith(".") for t in p.parts):
        raise PaketFehler(f"{wo}: „{key}“ muss ein Pfad innerhalb der Lektion sein (gefunden: „{wert}“).")
    if p.suffix.lower() not in endungen:
        raise PaketFehler(f"{wo}: „{key}“ muss auf {' oder '.join(sorted(endungen))} enden (gefunden: „{wert}“).")
    return str(p)


def _lesen(path: Path, limit: int = MAX_TEXT) -> str:
    try:
        if path.stat().st_size > limit:
            raise PaketFehler(f"{path.name} ist zu groß (höchstens {max(1, limit // 1024 // 1024)} MB).")
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise PaketFehler(f"{path.name} ist kein UTF-8-Text.") from None
    except FileNotFoundError:
        raise PaketFehler(f"{path.name} fehlt.") from None
    except OSError as e:
        raise PaketFehler(f"{path.name} lässt sich nicht lesen: {e.strerror or e}") from None


def _json_lesen(path: Path, wo: str):
    text = _lesen(path, MAX_JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise PaketFehler(f"{wo}: kein gültiges JSON (Zeile {e.lineno}, Spalte {e.colno}: {e.msg}).") from None


def _innerhalb(basis: Path, ziel: Path) -> bool:
    try:
        ziel.resolve().relative_to(basis.resolve())
        return True
    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------- Datenmodell
@dataclass
class Pruefung:
    """Prüfaufgabe. ``typ`` „skript“: ein Skript, das im Agent-PC läuft (Exit-Code 0 = geschafft, sonst noch nicht).
    Die anderen Typen (``EINGEBAUTE_PRUEFUNGEN``) prüft Bony's Agents selbst – ohne Code aus dem Kurspaket."""
    typ: str = SKRIPT
    skript: str = ""               # relativ zum Lektionsordner, z. B. "pruefung/einkaufsliste.sh"
    aufgabe: str = ""              # was geprüft wird – für Teilnehmer
    geschafft: str = "Geschafft!"
    noch_nicht: str = "Noch nicht geschafft."
    zeitlimit: int = PRUEF_ZEIT_STANDARD
    als: str = "benutzer"          # „benutzer“ (Benutzer des Agent-PCs) oder „root“
    loesung: str = ""              # optional: Skript, das die Aufgabe löst – nur für „Kurspaket prüfen“ im Editor


@dataclass
class Start:
    """Startskript für den Startzustand einer Lektion (läuft im Agent-PC, Sitzung 2)."""
    skript: str
    zeitlimit: int = START_ZEIT_STANDARD
    als: str = "root"


@dataclass
class Frage:
    frage: str
    antworten: list[str]
    richtig: int
    erklaerung: str = ""


@dataclass
class Lektion:
    ordner: str
    titel: str
    dauer_minuten: int = 0
    art: str = ""
    ziel: str = ""
    pruefung: Pruefung | None = None
    start: Start | None = None
    pfad: Path = field(default=Path("."), repr=False)

    @property
    def anleitung_datei(self) -> Path:
        return self.pfad / ANLEITUNG

    @property
    def kursleitung_datei(self) -> Path:
        return self.pfad / KURSLEITUNG

    @property
    def quiz_datei(self) -> Path:
        return self.pfad / QUIZ

    @property
    def hat_quiz(self) -> bool:
        return self.quiz_datei.is_file()

    def anleitung(self) -> str:
        return _lesen(self.anleitung_datei)

    def kursleitung(self) -> str:
        """Notizen für die Kursleitung – die Oberfläche zeigt sie nur in der Kursleiter-Edition."""
        return _lesen(self.kursleitung_datei) if self.kursleitung_datei.is_file() else ""

    def quiz(self) -> list[Frage]:
        if not self.hat_quiz:
            return []
        wo = f"Lektion „{self.titel}“, {QUIZ}"
        return quiz_pruefen(_json_lesen(self.quiz_datei, wo), wo)


@dataclass
class Rezept:
    """Wie der Agent-PC für das Kurspaket aussieht – statt eines Festplatten-Abbilds."""
    name: str = ""                 # Vorschlag für den Namen des Agent-PCs, z. B. „agent-kurs“
    desktop: str = desktops.DEFAULT
    apps: list[str] = field(default_factory=list)
    distro: str = distros.DEFAULT  # Grundsystem: „debian“ oder „kali“
    ram_mb: int | None = None
    cpus: int | None = None
    disk_gb: int | None = None
    username: str = "agent"
    keyboard: str = "de"
    timezone: str = "Europe/Berlin"
    vorlage: str = ""              # optional: Name einer Vorlage, die genutzt wird, wenn sie hier vorhanden ist
    vorlage_sha256: str = ""       # optional: SHA-256 der passenden .bonys-Datei

    def fuer_erstellen(self) -> dict:
        """Argumente wie ``bonysfile.recipe`` – für ``CreateDialog(recipe=…)`` bzw. ``vm.create``."""
        return {
            "app_ids": [a for a in self.apps if a in apps.APPS and not apps.APPS[a].hidden],
            "desktop": self.desktop,
            "distro": self.distro,
            "username": self.username,
            "keyboard": self.keyboard,
            "timezone_name": self.timezone,
            "ram_mb": self.ram_mb,
            "cpus": self.cpus,
            "disk_gb": self.disk_gb,
        }

    def unbekannte_apps(self) -> list[str]:
        """Apps aus dem Rezept, die diese Version von Bony's Agents nicht kennt (sie fehlen dann im Agent-PC)."""
        return [a for a in self.apps if a not in apps.APPS]


@dataclass
class Kurspaket:
    id: str
    name: str
    beschreibung: str
    stufe: str
    version: str
    sprache: str = "de"
    autor: str = ""
    lizenz: str = LIZENZ_STANDARD
    min_version: str = MIN_VERSION
    dauer_minuten: int = 0
    pause_minuten: int = 0
    teilnehmer_min: int = 0
    teilnehmer_max: int = 0
    zielgruppe: str = ""
    voraussetzungen: list[str] = field(default_factory=list)
    kosten: str = ""
    lernziele: list[str] = field(default_factory=list)
    quellen: list[dict] = field(default_factory=list)
    entwurf: bool = False
    rezept: Rezept = field(default_factory=Rezept)
    lektionen: list[Lektion] = field(default_factory=list)
    pfad: Path = field(default=Path("."), repr=False)
    herkunft: str = DATEI

    @property
    def stufe_text(self) -> str:
        return STUFEN.get(self.stufe, self.stufe)

    @property
    def dauer_text(self) -> str:
        return dauer_text(self.dauer_minuten)

    @property
    def teilnehmer_text(self) -> str:
        lo, hi = self.teilnehmer_min, self.teilnehmer_max
        if lo and hi:
            return f"{lo}–{hi} Personen" if lo != hi else f"{lo} Personen"
        if hi:
            return f"bis {hi} Personen"
        if lo:
            return f"ab {lo} Personen"
        return "–"

    @property
    def mitgeliefert(self) -> bool:
        return self.herkunft == MITGELIEFERT

    @property
    def ablaufplan_datei(self) -> Path:
        return self.pfad / ABLAUFPLAN

    @property
    def handout_datei(self) -> Path:
        return self.pfad / HANDOUT

    def ablaufplan(self) -> str:
        """Für die Kursleitung – die Oberfläche zeigt ihn nur in der Kursleiter-Edition."""
        return _lesen(self.ablaufplan_datei)

    def handout(self) -> str:
        return _lesen(self.handout_datei) if self.handout_datei.is_file() else ""

    def skripte(self) -> list[tuple[Lektion, str, str]]:
        """Alle Skripte, die das Kurspaket im Agent-PC ausführen würde: (Lektion, Art, Pfad im Kurspaket)."""
        out = []
        for lek in self.lektionen:
            if lek.start:
                out.append((lek, "Startzustand", f"{LEKTIONEN}/{lek.ordner}/{lek.start.skript}"))
            if lek.pruefung and lek.pruefung.typ == SKRIPT:
                out.append((lek, "Prüfung", f"{LEKTIONEN}/{lek.ordner}/{lek.pruefung.skript}"))
                if lek.pruefung.loesung:
                    out.append((lek, "Lösung (nur „Kurspaket prüfen“)",
                                f"{LEKTIONEN}/{lek.ordner}/{lek.pruefung.loesung}"))
        return out

    def lektion(self, index: int) -> Lektion:
        return self.lektionen[max(0, min(index, len(self.lektionen) - 1))]


# ---------------------------------------------------------------- paket.json und quiz.json prüfen
def quiz_pruefen(d: object, wo: str = QUIZ) -> list[Frage]:
    if not isinstance(d, dict) or not isinstance(d.get("fragen"), list):
        raise PaketFehler(f"{wo}: erwartet wird {{\"fragen\": [ … ]}}.")
    if not 1 <= len(d["fragen"]) <= 30:
        raise PaketFehler(f"{wo}: 1 bis 30 Fragen erlaubt.")
    fragen = []
    for i, f in enumerate(d["fragen"], 1):
        w = f"{wo}, Frage {i}"
        if not isinstance(f, dict):
            raise PaketFehler(f"{w}: muss ein Objekt sein.")
        antworten = f.get("antworten")
        if not isinstance(antworten, list) or not 2 <= len(antworten) <= 6:
            raise PaketFehler(f"{w}: „antworten“ muss 2 bis 6 Texte enthalten.")
        antworten = [_feld({"antworten": a}, "antworten", w, pflicht=True, max_len=300) for a in antworten]
        richtig = _zahl(f, "richtig", w, minimum=0, maximum=len(antworten) - 1)
        fragen.append(Frage(_feld(f, "frage", w, pflicht=True, max_len=500), antworten, richtig,
                            _feld(f, "erklaerung", w, max_len=1000, mehrzeilig=True)))
    return fragen


def _als(d: dict, w: str, standard: str) -> str:
    als = _feld(d, "als", w, standard=standard)
    if als not in ALS:
        raise PaketFehler(f"{w}: „als“ muss „benutzer“ oder „root“ sein.")
    return als


def _pruefung(d: object, wo: str) -> Pruefung | None:
    if d is None:
        return None
    w = f"{wo}, Prüfung"
    if not isinstance(d, dict):
        raise PaketFehler(f"{w}: muss ein Objekt sein.")
    typ = _feld(d, "typ", w, standard=SKRIPT)
    if typ != SKRIPT and typ not in EINGEBAUTE_PRUEFUNGEN:
        raise PaketFehler(f"{w}: unbekannter „typ“ „{typ}“ (bekannt: {SKRIPT}, {', '.join(EINGEBAUTE_PRUEFUNGEN)}) "
                          "– vielleicht braucht das Kurspaket eine neuere Version von Bony's Agents.")
    skript = _relpfad(_feld(d, "skript", w, pflicht=True), w, "skript", SKRIPT_ENDUNGEN) if typ == SKRIPT else ""
    loesung = _feld(d, "loesung", w) if typ == SKRIPT else ""
    if loesung:
        loesung = _relpfad(loesung, w, "loesung", SKRIPT_ENDUNGEN)
        if loesung == skript:
            raise PaketFehler(f"{w}: „loesung“ muss ein anderes Skript sein als „skript“.")
    return Pruefung(
        typ=typ, skript=skript, loesung=loesung,
        aufgabe=_feld(d, "aufgabe", w, max_len=300),
        geschafft=_feld(d, "geschafft", w, max_len=300) or "Geschafft!",
        noch_nicht=_feld(d, "noch_nicht", w, max_len=500) or "Noch nicht geschafft.",
        zeitlimit=_zahl(d, "zeitlimit", w, minimum=1, maximum=PRUEF_ZEIT_MAX, standard=PRUEF_ZEIT_STANDARD),
        als=_als(d, w, "benutzer"),
    )


def _start(d: object, wo: str) -> Start | None:
    if d is None:
        return None
    w = f"{wo}, Startzustand"
    if not isinstance(d, dict):
        raise PaketFehler(f"{w}: muss ein Objekt sein.")
    return Start(skript=_relpfad(_feld(d, "skript", w, pflicht=True), w, "skript", SKRIPT_ENDUNGEN),
                 zeitlimit=_zahl(d, "zeitlimit", w, minimum=1, maximum=START_ZEIT_MAX, standard=START_ZEIT_STANDARD),
                 als=_als(d, w, "root"))


def _rezept(d: object) -> Rezept:
    wo = f"{PAKET_JSON}, Rezept"
    if d is None:
        d = {}
    if not isinstance(d, dict):
        raise PaketFehler(f"{wo}: „rezept“ muss ein Objekt sein.")
    distro = _feld(d, "distro", wo, standard=distros.DEFAULT)
    if distro not in distros.DISTROS:
        raise PaketFehler(f"{wo}: unbekanntes Grundsystem „{distro}“ (bekannt: {', '.join(distros.DISTROS)}) – "
                          "vielleicht braucht das Kurspaket eine neuere Version von Bony's Agents.")
    # Ohne Angabe: der Standard-Desktop des Grundsystems (Kali: Xfce)
    desktop = _feld(d, "desktop", wo, standard=(distros.get(distro).desktops or (desktops.DEFAULT,))[0])
    if desktop not in desktops.DESKTOPS:
        raise PaketFehler(f"{wo}: unbekannter Desktop „{desktop}“ (bekannt: {', '.join(desktops.DESKTOPS)}) – "
                          "vielleicht braucht das Kurspaket eine neuere Version von Bony's Agents.")
    app_liste = d.get("apps", [])
    if not isinstance(app_liste, list) or len(app_liste) > 40 or not all(
            isinstance(a, str) and vm.APP_ID_RE.match(a) for a in app_liste):
        raise PaketFehler(f"{wo}: „apps“ muss eine Liste von App-Kennungen sein (z. B. \"brave\", \"hermes\").")
    name = _feld(d, "name", wo, max_len=40)
    if name and not vm.NAME_RE.match(name):
        raise PaketFehler(f"{wo}: ungültiger Name für den Agent-PC „{name}“ (Buchstaben, Ziffern, - und _).")
    username = _feld(d, "username", wo, standard="agent")
    if not vm.USERNAME_RE.match(username):
        raise PaketFehler(f"{wo}: ungültiger Benutzername „{username}“ (klein, beginnt mit einem Buchstaben).")
    keyboard = _feld(d, "keyboard", wo, standard="de")
    if not vm.KEYBOARD_RE.match(keyboard):
        raise PaketFehler(f"{wo}: ungültige Tastatur „{keyboard}“.")
    timezone = _feld(d, "timezone", wo, standard="Europe/Berlin")
    if not vm.TIMEZONE_RE.match(timezone):
        raise PaketFehler(f"{wo}: ungültige Zeitzone „{timezone}“.")
    vorlage = _feld(d, "vorlage", wo, max_len=60)
    if vorlage and not vm.NAME_RE.match(vorlage):
        raise PaketFehler(f"{wo}: ungültiger Vorlagenname „{vorlage}“.")
    sha = _feld(d, "vorlage_sha256", wo, max_len=64).lower()
    if sha and not _HEX64.match(sha):
        raise PaketFehler(f"{wo}: „vorlage_sha256“ muss eine SHA-256-Prüfsumme (64 Hex-Zeichen) sein.")
    return Rezept(
        name=name, desktop=desktop, apps=list(dict.fromkeys(app_liste)), distro=distro,
        ram_mb=_zahl(d, "ram_mb", wo, minimum=1024, maximum=262144, standard=0) or None,
        cpus=_zahl(d, "cpus", wo, minimum=1, maximum=64, standard=0) or None,
        disk_gb=_zahl(d, "disk_gb", wo, minimum=vm.MIN_DISK_GB, maximum=vm.MAX_DISK_GB, standard=0) or None,
        username=username, keyboard=keyboard, timezone=timezone, vorlage=vorlage, vorlage_sha256=sha,
    )


def _quellen(d: dict) -> list[dict]:
    wert = d.get("quellen", [])
    wo = f"{PAKET_JSON}, Quelle"
    if not isinstance(wert, list) or len(wert) > 30:
        raise PaketFehler(f"{PAKET_JSON}: „quellen“ muss eine Liste sein (höchstens 30 Einträge).")
    out = []
    for q in wert:
        if not isinstance(q, dict):
            raise PaketFehler(f"{wo}: braucht „titel“ und „url“.")
        url = _feld(q, "url", wo, pflicht=True, max_len=500)
        if urllib.parse.urlparse(url).scheme != "https":
            raise PaketFehler(f"{wo}: nur https-Adressen erlaubt (gefunden: „{url}“).")
        out.append({"titel": _feld(q, "titel", wo, pflicht=True), "url": url})
    return out


def _teilnehmer(d: dict) -> tuple[int, int]:
    t = d.get("teilnehmer")
    if t is None:
        return 0, 0
    wo = f"{PAKET_JSON}, Teilnehmer"
    if not isinstance(t, dict):
        raise PaketFehler(f"{wo}: erwartet wird z. B. {{\"min\": 5, \"max\": 10}}.")
    lo = _zahl(t, "min", wo, minimum=1, maximum=1000, standard=0)
    hi = _zahl(t, "max", wo, minimum=1, maximum=1000, standard=0)
    if lo and hi and lo > hi:
        raise PaketFehler(f"{wo}: „min“ ist größer als „max“.")
    return lo, hi


def paket_pruefen(d: object, pfad: Path = Path(".")) -> Kurspaket:
    """``paket.json`` (fremde Daten!) prüfen und in ein ``Kurspaket`` wandeln – PaketFehler mit Meldung."""
    if not isinstance(d, dict) or d.get("format") != FORMAT_ID:
        raise PaketFehler(f"Kein Kurspaket von Bony's Agents (in {PAKET_JSON} fehlt "
                          f"\"format\": \"{FORMAT_ID}\").")
    fv = d.get("format_version")
    if not isinstance(fv, int) or isinstance(fv, bool) or fv < 1:
        raise PaketFehler(f"{PAKET_JSON}: ungültige „format_version“.")
    wo = PAKET_JSON
    min_v = _feld(d, "min_version", wo, standard=MIN_VERSION, max_len=20) or MIN_VERSION
    if not VERSION_RE.match(min_v):
        raise PaketFehler(f"{wo}: ungültige „min_version“ „{min_v}“ (z. B. „0.23.0“).")
    if fv > FORMAT_VERSION or version_vergleich(min_v, __version__) > 0:
        raise PaketFehler(f"Dieses Kurspaket braucht Bony's Agents {min_v} oder neuer (installiert: {__version__}). "
                          "Bitte zuerst Bony's Agents aktualisieren.")
    paket_id = _feld(d, "id", wo, pflicht=True, max_len=60)
    if not ID_RE.match(paket_id):
        raise PaketFehler(f"{wo}: „id“ „{paket_id}“ ist ungültig – 3 bis 60 Zeichen, nur Kleinbuchstaben, Ziffern "
                          "und Bindestrich (z. B. „einfuehrung-hermes-agent“).")
    stufe = _feld(d, "stufe", wo, pflicht=True)
    if stufe not in STUFEN:
        raise PaketFehler(f"{wo}: „stufe“ muss „anfaenger“, „fortgeschritten“ oder „experte“ sein "
                          f"(gefunden: „{stufe}“).")
    version = _feld(d, "version", wo, pflicht=True, max_len=20)
    if not VERSION_RE.match(version):
        raise PaketFehler(f"{wo}: „version“ „{version}“ ist ungültig (z. B. „1.0.0“).")
    sprache = _feld(d, "sprache", wo, standard="de", max_len=5)
    if not SPRACHE_RE.match(sprache):
        raise PaketFehler(f"{wo}: „sprache“ „{sprache}“ ist ungültig (z. B. „de“).")
    entwurf = d.get("entwurf", False)
    if not isinstance(entwurf, bool):
        raise PaketFehler(f"{wo}: „entwurf“ muss true oder false sein.")
    lo, hi = _teilnehmer(d)
    paket = Kurspaket(
        id=paket_id,
        name=_feld(d, "name", wo, pflicht=True, max_len=120),
        beschreibung=_feld(d, "beschreibung", wo, pflicht=True, max_len=2000, mehrzeilig=True),
        stufe=stufe, version=version, sprache=sprache,
        autor=_feld(d, "autor", wo, max_len=120),
        lizenz=_feld(d, "lizenz", wo, max_len=60) or LIZENZ_STANDARD,
        min_version=min_v,
        dauer_minuten=_zahl(d, "dauer_minuten", wo, minimum=0, maximum=100 * 60, standard=0),
        pause_minuten=_zahl(d, "pause_minuten", wo, minimum=0, maximum=24 * 60, standard=0),
        teilnehmer_min=lo, teilnehmer_max=hi,
        zielgruppe=_feld(d, "zielgruppe", wo, max_len=500, mehrzeilig=True),
        voraussetzungen=_textliste(d, "voraussetzungen", wo),
        kosten=_feld(d, "kosten", wo, max_len=300),
        lernziele=_textliste(d, "lernziele", wo),
        quellen=_quellen(d),
        entwurf=entwurf,
        rezept=_rezept(d.get("rezept")),
        pfad=pfad,
    )
    lektionen = d.get("lektionen", [])
    if not isinstance(lektionen, list):
        raise PaketFehler(f"{wo}: „lektionen“ muss eine Liste sein.")
    if len(lektionen) > MAX_LEKTIONEN:
        raise PaketFehler(f"{wo}: höchstens {MAX_LEKTIONEN} Lektionen erlaubt.")
    gesehen: set[str] = set()
    for i, lek in enumerate(lektionen, 1):
        w = f"{wo}, Lektion {i}"
        if not isinstance(lek, dict):
            raise PaketFehler(f"{w}: muss ein Objekt sein.")
        ordner = _feld(lek, "ordner", w, pflicht=True, max_len=61)
        if not ORDNER_RE.match(ordner):
            raise PaketFehler(f"{w}: „ordner“ „{ordner}“ ist ungültig – Form „NN-name“, z. B. „01-ankommen“.")
        if ordner in gesehen:
            raise PaketFehler(f"{w}: Ordner „{ordner}“ kommt doppelt vor.")
        gesehen.add(ordner)
        titel = _feld(lek, "titel", w, pflicht=True, max_len=120)
        w = f"Lektion {i} „{titel}“"
        paket.lektionen.append(Lektion(
            ordner=ordner, titel=titel,
            dauer_minuten=_zahl(lek, "dauer_minuten", w, minimum=0, maximum=24 * 60, standard=0),
            art=_feld(lek, "art", w, max_len=60),
            ziel=_feld(lek, "ziel", w, max_len=500, mehrzeilig=True),
            pruefung=_pruefung(lek.get("pruefung"), w),
            start=_start(lek.get("start"), w),
            pfad=pfad / LEKTIONEN / ordner,
        ))
    if not paket.dauer_minuten:
        paket.dauer_minuten = sum(lek.dauer_minuten for lek in paket.lektionen)
    return paket


def laden(ordner: Path, herkunft: str = DATEI) -> Kurspaket:
    """Kurspaket aus einem Ordner laden und vollständig prüfen (auch Ablaufplan, Lektionen, Skripte, Quiz)."""
    ordner = Path(ordner)
    datei = ordner / PAKET_JSON
    if not datei.is_file():
        raise PaketFehler(f"Im Ordner „{ordner.name}“ fehlt die Steuerdatei {PAKET_JSON}.")
    paket = paket_pruefen(_json_lesen(datei, PAKET_JSON), ordner)
    paket.herkunft = herkunft
    if not paket.ablaufplan_datei.is_file():
        raise PaketFehler(f"Im Kurspaket fehlt der Ablaufplan ({ABLAUFPLAN}).")
    for name in (ABLAUFPLAN, HANDOUT):
        if (ordner / name).is_file():
            _lesen(ordner / name)
    for i, lek in enumerate(paket.lektionen, 1):
        w = f"Lektion {i} „{lek.titel}“"
        if not lek.pfad.is_dir() or not _innerhalb(ordner, lek.pfad):
            raise PaketFehler(f"{w}: Ordner {LEKTIONEN}/{lek.ordner} fehlt.")
        if not lek.anleitung_datei.is_file():
            raise PaketFehler(f"{w}: {ANLEITUNG} fehlt.")
        lek.anleitung()
        for was, skript in (("Prüfskript", lek.pruefung.skript if lek.pruefung else ""),
                            ("Lösungsskript", lek.pruefung.loesung if lek.pruefung else ""),
                            ("Startskript", lek.start.skript if lek.start else "")):
            if skript:
                p = lek.pfad / skript
                if p.is_symlink() or not p.is_file() or not _innerhalb(lek.pfad, p):
                    raise PaketFehler(f"{w}: {was} „{skript}“ fehlt.")
                _lesen(p)
        if lek.hat_quiz:
            lek.quiz()
    return paket


# ---------------------------------------------------------------- paket.json schreiben (Editor)
def paket_json(paket: Kurspaket) -> dict:
    """Gegenstück zu ``paket_pruefen``: ``paket.json`` als Dict – Standardwerte bleiben weg, damit die Datei kurz
    und gut lesbar bleibt (und sich mit Git gut vergleichen lässt)."""
    d: dict = {"format": FORMAT_ID, "format_version": FORMAT_VERSION, "min_version": paket.min_version,
               "id": paket.id, "name": paket.name, "beschreibung": paket.beschreibung, "stufe": paket.stufe,
               "sprache": paket.sprache}
    if paket.autor:
        d["autor"] = paket.autor
    d["lizenz"] = paket.lizenz or LIZENZ_STANDARD
    d["version"] = paket.version
    if paket.entwurf:
        d["entwurf"] = True
    summe = sum(lek.dauer_minuten for lek in paket.lektionen)
    if paket.dauer_minuten and paket.dauer_minuten != summe:
        d["dauer_minuten"] = paket.dauer_minuten
    if paket.pause_minuten:
        d["pause_minuten"] = paket.pause_minuten
    if paket.teilnehmer_min or paket.teilnehmer_max:
        d["teilnehmer"] = {k: v for k, v in (("min", paket.teilnehmer_min), ("max", paket.teilnehmer_max)) if v}
    for key in ("zielgruppe", "kosten"):
        if getattr(paket, key):
            d[key] = getattr(paket, key)
    for key in ("voraussetzungen", "lernziele", "quellen"):
        if getattr(paket, key):
            d[key] = list(getattr(paket, key))
    r, standard = paket.rezept, Rezept()
    rezept: dict = {}
    if r.name:
        rezept["name"] = r.name
    rezept["desktop"] = r.desktop
    if r.distro != standard.distro:
        rezept["distro"] = r.distro
    if r.apps:
        rezept["apps"] = list(r.apps)
    for key in ("ram_mb", "cpus", "disk_gb"):
        if getattr(r, key):
            rezept[key] = getattr(r, key)
    for key in ("username", "keyboard", "timezone"):
        if getattr(r, key) != getattr(standard, key):
            rezept[key] = getattr(r, key)
    if r.vorlage:
        rezept["vorlage"] = r.vorlage
    if r.vorlage_sha256:
        rezept["vorlage_sha256"] = r.vorlage_sha256
    d["rezept"] = rezept
    lektionen = []
    for lek in paket.lektionen:
        ld: dict = {"ordner": lek.ordner, "titel": lek.titel}
        if lek.dauer_minuten:
            ld["dauer_minuten"] = lek.dauer_minuten
        if lek.art:
            ld["art"] = lek.art
        if lek.ziel:
            ld["ziel"] = lek.ziel
        if lek.pruefung:
            p, pd = lek.pruefung, {}
            if p.typ == SKRIPT:
                pd["skript"] = p.skript
                if p.loesung:
                    pd["loesung"] = p.loesung
            else:
                pd["typ"] = p.typ
            if p.aufgabe:
                pd["aufgabe"] = p.aufgabe
            pd["geschafft"] = p.geschafft or "Geschafft!"
            pd["noch_nicht"] = p.noch_nicht or "Noch nicht geschafft."
            if p.typ == SKRIPT:
                if p.zeitlimit != PRUEF_ZEIT_STANDARD:
                    pd["zeitlimit"] = p.zeitlimit
                if p.als != "benutzer":
                    pd["als"] = p.als
            ld["pruefung"] = pd
        if lek.start:
            sd: dict = {"skript": lek.start.skript}
            if lek.start.zeitlimit != START_ZEIT_STANDARD:
                sd["zeitlimit"] = lek.start.zeitlimit
            if lek.start.als != "root":
                sd["als"] = lek.start.als
            ld["start"] = sd
        lektionen.append(ld)
    d["lektionen"] = lektionen
    return d


def quiz_json(fragen: list[Frage]) -> dict:
    out = []
    for f in fragen:
        fd = {"frage": f.frage, "antworten": list(f.antworten), "richtig": f.richtig}
        if f.erklaerung:
            fd["erklaerung"] = f.erklaerung
        out.append(fd)
    return {"fragen": out}


def json_text(d: object) -> str:
    """JSON so, wie Bony's Agents es in Kurspaketen schreibt: UTF-8 lesbar, eingerückt, Zeilenende am Schluss."""
    return json.dumps(d, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- Geheimnis-Prüfung
@dataclass
class Fund:
    """Fundstelle der Geheimnis-Prüfung – ohne den Wert selbst (der soll nirgends angezeigt werden)."""
    datei: str
    zeile: int
    art: str

    def __str__(self) -> str:
        return f"{self.datei}, Zeile {self.zeile}: {self.art}"


class GeheimnisGefunden(PaketFehler):
    """Im Kurspaket stehen Zugangsdaten oder persönliche Daten – Speichern/Export ist blockiert, bis bereinigt."""

    def __init__(self, funde: list[Fund]):
        self.funde = funde
        liste = "\n".join(f"• {f}" for f in funde[:20]) + (f"\n• … und {len(funde) - 20} weitere"
                                                             if len(funde) > 20 else "")
        super().__init__("Im Kurspaket stehen Zugangsdaten oder persönliche Daten – das Kurspaket wird so nicht "
                         f"gespeichert bzw. exportiert, bis sie entfernt sind:\n{liste}\n\nSchreibe stattdessen "
                         "einen Platzhalter wie „<dein-schlüssel>“ – Teilnehmer nutzen ihr eigenes Konto.")


# Die erste passende Regel je Zeile zählt – die genaueren stehen daher vorn.
_GEHEIMNIS_MUSTER: list[tuple[str, re.Pattern]] = [
    ("privater Schlüssel", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY")),
    ("API-Schlüssel (Anthropic)", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}")),
    ("API-Schlüssel (OpenRouter)", re.compile(r"\bsk-or-[A-Za-z0-9_-]{16,}")),
    ("API-Schlüssel (sk-…)", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,}")),
    ("API-Schlüssel (Stripe)", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}")),
    ("GitHub-Token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("GitLab-Token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("AWS-Zugangsschlüssel", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google-API-Schlüssel", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("Slack-Token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Telegram-Bot-Token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}")),
    ("Hugging-Face-Token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("Token (JWT)", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Zugangsdaten in einer Adresse", re.compile(r"\b[a-z][a-z0-9+.-]{1,15}://[^\s/:@\"'<>]+:[^\s/@\"'<>]+@")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[0-9]{4}){4}(?: ?[0-9]{1,4})?\b")),
]
# Zuweisung wie API_KEY=… / "password": "…" – zählt nur, wenn der Wert nach einem echten Geheimnis aussieht
_ZUWEISUNG = re.compile(
    r"(?i)\b[\w-]*(?:api[_-]?key|token|secret|passwor[dt]|passwd|kennwort|client[_-]?secret)[\w-]*[\"']?\s*[:=]\s*"
    r"[\"']?([^\s\"'`,;]+)")
_PLATZHALTER = re.compile(r"(?i)^[<\[{($%]|^\.\.\.|…|dein|deine|your|xxx|beispiel|example|platzhalter|placeholder|"
                          r"changeme|^none$|^null$|^true$|^false$|getpass|environ|input\(")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
_EMAIL_ERLAUBT = re.compile(r"(?i)(^|\.)(example\.(com|org|net)|beispiel\.(de|org)|example|invalid|test|localhost|"
                            r"users\.noreply\.github\.com|github\.com)$")
_TELEFON = re.compile(r"(?<![\w+])(?:\+|00)(?:49|43|41)[ /-]?\(?0?\)?\d{2,5}[ /-]?\d{3,}(?:[ -]?\d{2,})?|"
                      r"(?<![\w/])01[5-7]\d[ /-]?\d{6,8}\b")
TEXT_ENDUNGEN = {".md", ".txt", ".json", ".sh", ".py", ""}


def _sieht_geheim_aus(wert: str) -> bool:
    if len(wert) < 8 or _PLATZHALTER.search(wert):
        return False
    hat_ziffer, hat_buchstabe = any(c.isdigit() for c in wert), any(c.isalpha() for c in wert)
    return (hat_ziffer and hat_buchstabe) or len(wert) >= 20


def geheimnisse_suchen_text(text: str, datei: str = "") -> list[Fund]:
    funde = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        art = next((a for a, muster in _GEHEIMNIS_MUSTER if muster.search(zeile)), "")
        if not art:
            m = _ZUWEISUNG.search(zeile)
            if m and _sieht_geheim_aus(m.group(1)):
                art = "Passwort oder Schlüssel"
        if not art:
            if any(not _EMAIL_ERLAUBT.search(m.group(1)) for m in _EMAIL.finditer(zeile)):
                art = "E-Mail-Adresse (persönliche Daten)"
            elif _TELEFON.search(zeile):
                art = "Telefonnummer (persönliche Daten)"
        if art:
            funde.append(Fund(datei, nr, art))
    return funde


def geheimnisse_suchen(ordner: Path) -> list[Fund]:
    """Alle Textdateien eines Paket-Ordners nach Zugangsdaten und persönlichen Daten durchsuchen."""
    funde: list[Fund] = []
    for p, rel in _dateien(Path(ordner)):
        if rel.suffix.lower() not in TEXT_ENDUNGEN or p.is_symlink() or rel.name == HERKUNFT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace") if p.stat().st_size <= MAX_TEXT else ""
        except OSError:
            continue
        funde += geheimnisse_suchen_text(text, rel.as_posix())
    return funde


def geheimnisse_pruefen(ordner: Path) -> None:
    funde = geheimnisse_suchen(ordner)
    if funde:
        raise GeheimnisGefunden(funde)


# ---------------------------------------------------------------- ZIP: prüfen, entpacken, packen
def _ueberspringen(teile: tuple[str, ...]) -> bool:
    """Beiwerk von macOS, Git und Editoren – wird still weggelassen."""
    return any(t.startswith(".") or t in ("__MACOSX", "__pycache__") for t in teile)


def _zip_eintraege(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    """Alle Einträge prüfen, bevor etwas entpackt wird. Gibt [(Eintrag, Zielpfad relativ zum Paket)] zurück.

    Erlaubt ist ``paket.json`` ganz oben oder genau ein Ordner ganz oben, der ``paket.json`` enthält (so entsteht
    eine ZIP-Datei, wenn man einen Ordner packt).
    """
    infos = zf.infolist()
    if len(infos) > MAX_DATEIEN:
        raise PaketFehler(f"Die Datei enthält zu viele Einträge (höchstens {MAX_DATEIEN}).")
    namen = []
    for info in infos:
        name = info.filename
        if "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name) or "\x00" in name:
            raise PaketFehler(f"Unerlaubter Pfad in der Datei: „{name}“.")
        p = PurePosixPath(name)
        if ".." in p.parts:
            raise PaketFehler(f"Unerlaubter Pfad in der Datei (führt aus dem Kurspaket heraus): „{name}“.")
        modus = info.external_attr >> 16
        if stat.S_ISLNK(modus) or (stat.S_IFMT(modus) and not (stat.S_ISREG(modus) or stat.S_ISDIR(modus))):
            raise PaketFehler(f"Die Datei enthält einen Verweis oder eine Sonderdatei: „{name}“ – nicht erlaubt.")
        if info.flag_bits & 0x1:
            raise PaketFehler("Verschlüsselte ZIP-Dateien werden nicht unterstützt.")
        namen.append((info, p))
    oben = {p.parts[0] for _i, p in namen if p.parts and not _ueberspringen(p.parts[:1])}
    praefix = ""
    if not any(p == PurePosixPath(PAKET_JSON) for _i, p in namen):
        if len(oben) == 1 and any(p == PurePosixPath(next(iter(oben)), PAKET_JSON) for _i, p in namen):
            praefix = next(iter(oben))
        else:
            raise PaketFehler(f"Keine Kurspaket-Datei von Bony's Agents: {PAKET_JSON} fehlt.")
    eintraege = []
    gesamt = 0
    gesehen: set[str] = set()
    for info, p in namen:
        if praefix and (not p.parts or p.parts[0] != praefix):
            continue
        rel = PurePosixPath(*p.parts[1:]) if praefix else p
        if not rel.parts or _ueberspringen(rel.parts) or info.is_dir():
            continue
        if len(rel.parts) > MAX_TIEFE:
            raise PaketFehler(f"Zu tief verschachtelt: „{info.filename}“.")
        if rel.suffix.lower() not in ENDUNGEN:
            raise PaketFehler(f"Unerlaubte Dateiart „{rel.suffix}“ in „{info.filename}“ – erlaubt sind Texte "
                              "(.md, .txt, .json), Skripte (.sh, .py) und Bilder (.png, .jpg, .gif, .webp).")
        key = rel.as_posix().lower()
        if key in gesehen:
            raise PaketFehler(f"Doppelter Pfad in der Datei: „{info.filename}“.")
        gesehen.add(key)
        if info.file_size > MAX_DATEI:
            raise PaketFehler(f"„{info.filename}“ ist zu groß (höchstens {MAX_DATEI // 1024 // 1024} MB je Datei).")
        gesamt += info.file_size
        if gesamt > MAX_GESAMT:
            raise PaketFehler(f"Das Kurspaket ist entpackt zu groß (höchstens {MAX_GESAMT // 1024 // 1024} MB).")
        eintraege.append((info, rel))
    return eintraege


def entpacken(datei: Path, ziel: Path) -> None:
    """``.bonyspaket`` sicher nach ``ziel`` (darf noch nicht existieren) entpacken.

    Zählt dabei die echten Bytes mit – die Größen im ZIP-Verzeichnis könnten gelogen sein (ZIP-Bombe).
    """
    try:
        zf = zipfile.ZipFile(datei)
    except zipfile.BadZipFile:
        raise PaketFehler(f"„{Path(datei).name}“ ist keine gültige Kurspaket-Datei (kein ZIP-Archiv).") from None
    except OSError as e:
        raise PaketFehler(f"„{Path(datei).name}“ lässt sich nicht öffnen: {e.strerror or e}") from None
    with zf:
        eintraege = _zip_eintraege(zf)
        ziel.mkdir(parents=True)
        gesamt = 0
        for info, rel in eintraege:
            out = ziel.joinpath(*rel.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            geschrieben = 0
            try:
                with zf.open(info) as src, out.open("xb") as dst:
                    while chunk := src.read(1024 * 1024):
                        geschrieben += len(chunk)
                        gesamt += len(chunk)
                        if geschrieben > MAX_DATEI or gesamt > MAX_GESAMT:
                            raise PaketFehler("Das Kurspaket ist entpackt zu groß – Entpacken abgebrochen.")
                        dst.write(chunk)
            except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError) as e:
                raise PaketFehler(f"„{info.filename}“ ist beschädigt: {e}") from None
            except FileExistsError:
                raise PaketFehler(f"Doppelter Pfad in der Datei: „{info.filename}“.") from None
            # Lesbar, aber auf diesem Rechner nie ausführbar – Skripte laufen nur im Agent-PC
            out.chmod(0o644)


def _dateien(ordner: Path):
    """Dateien eines Paket-Ordners, die in ein Paket gehören (ohne Versteckte, Beiwerk, Links)."""
    for p in sorted(Path(ordner).rglob("*")):
        rel = p.relative_to(ordner)
        if _ueberspringen(rel.parts) or p.is_dir():
            continue
        yield p, rel


def packen(ordner: Path, datei: Path) -> Path:
    """Paket-Ordner prüfen und als ``.bonyspaket`` speichern (``.herkunft.json`` und Versteckte bleiben weg).

    Enthält das Paket Zugangsdaten oder persönliche Daten, wird nichts gespeichert (``GeheimnisGefunden``)."""
    laden(ordner)
    geheimnisse_pruefen(ordner)
    datei = Path(datei)
    tmp = datei.with_name(f".{datei.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for p, rel in _dateien(ordner):
                if p.is_symlink():
                    raise PaketFehler(f"Der Paket-Ordner enthält einen Verweis (Link): „{rel.as_posix()}“.")
                if rel.suffix.lower() in ENDUNGEN:
                    zf.write(p, rel.as_posix())
        os.replace(tmp, datei)
    finally:
        tmp.unlink(missing_ok=True)
    return datei


def dateiname(paket: Kurspaket) -> str:
    return f"{paket.id}-{paket.version}{SUFFIX}"


# ---------------------------------------------------------------- Bibliothek
def bibliothek_dir() -> Path:
    return storage.data_dir() / "kurspakete"


def mitgeliefert_dirs() -> list[Path]:
    """Ordner mit mitgelieferten Kurspaketen: im Programm (``resources/kurspakete``), im Quellcode ``kurspakete/``."""
    hier = Path(__file__).resolve().parent
    kandidaten = [hier / "resources" / "kurspakete", hier.parent.parent / "kurspakete"]
    return [k for k in kandidaten if k.is_dir()]


def herkunft_sha256(paket: Kurspaket) -> str:
    """SHA-256 der Datei, aus der das Kurspaket importiert wurde (Download, Kurs) – sonst ""."""
    wert = _herkunft_lesen(paket.pfad).get("sha256") if not paket.mitgeliefert else ""
    return wert if isinstance(wert, str) else ""


def _herkunft_lesen(ordner: Path) -> dict:
    try:
        d = storage.read_json(ordner / HERKUNFT)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


@dataclass
class Bestand:
    pakete: list[Kurspaket]
    fehler: list[tuple[str, str]]     # (Ordner, Meldung) – kaputte Kurspakete in der Bibliothek


def bestand() -> Bestand:
    """Alle Kurspakete: eigene Bibliothek (importiert, heruntergeladen) und mitgelieferte. Eine importierte Fassung
    verdeckt die mitgelieferte mit derselben ID."""
    gefunden: dict[str, Kurspaket] = {}
    fehler: list[tuple[str, str]] = []
    bib = bibliothek_dir()
    if bib.is_dir():
        for ordner in sorted(bib.iterdir()):
            if not ordner.is_dir() or ordner.name.startswith("."):
                continue
            herkunft = _herkunft_lesen(ordner).get("quelle")
            try:
                paket = laden(ordner, herkunft if herkunft in (DATEI, INTERNET, EIGEN, KURS, COMMUNITY) else DATEI)
            except PaketFehler as e:
                fehler.append((ordner.name, str(e)))
                continue
            gefunden[paket.id] = paket
    for basis in mitgeliefert_dirs():
        for ordner in sorted(basis.iterdir()):
            if not (ordner / PAKET_JSON).is_file():
                continue
            try:
                paket = laden(ordner, MITGELIEFERT)
            except PaketFehler as e:
                fehler.append((ordner.name, str(e)))
                continue
            gefunden.setdefault(paket.id, paket)
    pakete = sorted(gefunden.values(),
                    key=lambda k: (k.entwurf, STUFEN_REIHENFOLGE.get(k.stufe, 9), k.name.lower()))
    return Bestand(pakete, fehler)


def liste() -> list[Kurspaket]:
    return bestand().pakete


def holen(paket_id: str) -> Kurspaket:
    for k in liste():
        if k.id == paket_id:
            return k
    raise PaketFehler(f"Das Kurspaket „{paket_id}“ gibt es nicht (mehr) in der Bibliothek.")


def importieren(quelle: Path, ersetzen: bool = False, herkunft: str = DATEI, sha256: str = "") -> Kurspaket:
    """Kurspaket aus ``.bonyspaket`` oder einem Ordner in die Bibliothek übernehmen.

    Gibt es die ID schon, wirft das ``PaketExistiert`` (mit beiden Versionen) – mit ``ersetzen=True`` wird es
    aktualisiert; der Fortschritt bleibt dabei erhalten.
    """
    quelle = Path(quelle)
    bib = bibliothek_dir()
    bib.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".import-", dir=bib))
    try:
        neu_dir = tmp / "paket"
        if quelle.is_dir():
            _ordner_kopieren(quelle, neu_dir)
        elif quelle.is_file():
            entpacken(quelle, neu_dir)
        else:
            raise PaketFehler(f"„{quelle.name}“ gibt es nicht.")
        neu = laden(neu_dir, herkunft)
        alt = next((k for k in liste() if k.id == neu.id), None)
        if alt is not None and not ersetzen:
            raise PaketExistiert(alt, neu)
        storage.write_json(neu_dir / HERKUNFT, {"quelle": herkunft, "datei": quelle.name, "sha256": sha256,
                                                "importiert": int(time.time())})
        ziel = bib / neu.id
        if ziel.exists():
            os.replace(ziel, tmp / "alt")
        os.replace(neu_dir, ziel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return laden(ziel, herkunft)


def _ordner_kopieren(quelle: Path, ziel: Path) -> None:
    """Paket-Ordner kopieren – mit denselben Regeln wie beim Entpacken (Größe, Dateiarten, keine Links)."""
    gesamt = anzahl = 0
    ziel.mkdir(parents=True)
    for p, rel in _dateien(quelle):
        if p.is_symlink():
            raise PaketFehler(f"Der Paket-Ordner enthält einen Verweis (Link): „{rel.as_posix()}“ – nicht erlaubt.")
        if rel.suffix.lower() not in ENDUNGEN:
            raise PaketFehler(f"Unerlaubte Dateiart „{rel.suffix}“ in „{rel.as_posix()}“.")
        if len(rel.parts) > MAX_TIEFE:
            raise PaketFehler(f"Zu tief verschachtelt: „{rel.as_posix()}“.")
        groesse = p.stat().st_size
        anzahl += 1
        gesamt += groesse
        if groesse > MAX_DATEI or gesamt > MAX_GESAMT or anzahl > MAX_DATEIEN:
            raise PaketFehler("Der Paket-Ordner ist zu groß.")
        out = ziel / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, out)
        out.chmod(0o644)


def loeschen(paket_id: str, fortschritt_auch: bool = True) -> None:
    """Importiertes Kurspaket löschen. Mitgelieferte gehören zum Programm (nur eine importierte Fassung geht weg)."""
    ziel = bibliothek_dir() / paket_id
    if not ID_RE.match(paket_id) or not ziel.is_dir():
        if any(k.id == paket_id and k.mitgeliefert for k in liste()):
            raise PaketFehler("Mitgelieferte Kurspakete gehören zum Programm und lassen sich nicht löschen.")
        raise PaketFehler(f"Das Kurspaket „{paket_id}“ gibt es nicht in der Bibliothek.")
    papierkorb = bibliothek_dir() / f".loeschen-{paket_id}-{os.getpid()}"
    os.replace(ziel, papierkorb)
    shutil.rmtree(papierkorb, ignore_errors=True)
    if fortschritt_auch:
        Fortschritt.vergessen(paket_id)


# ---------------------------------------------------------------- Kurspakete aus dem Internet
@dataclass
class KatalogEintrag:
    id: str
    name: str
    version: str
    stufe: str
    beschreibung: str
    dauer_minuten: int
    url: str
    sha256: str
    groesse: int
    entwurf: bool = False
    community: bool = False

    @property
    def stufe_text(self) -> str:
        return STUFEN.get(self.stufe, self.stufe)


def katalog_url() -> str:
    return os.environ.get(KATALOG_ENV) or KATALOG_URL


def community_url() -> str:
    return os.environ.get(COMMUNITY_ENV) or COMMUNITY_URL


def community_an() -> bool:
    """Community-Katalog anzeigen? Standard: ja."""
    return storage.load_settings().get(COMMUNITY_EINSTELLUNG) is not False


def community_setzen(an: bool) -> None:
    s = storage.load_settings()
    s[COMMUNITY_EINSTELLUNG] = bool(an)
    storage.save_settings(s)


def _url_ok(url: str) -> bool:
    teile = urllib.parse.urlparse(url)
    return teile.scheme == "https" or (teile.scheme == "http" and teile.hostname in ("127.0.0.1", "localhost"))


def katalog_laden(url: str | None = None, opener: Opener | None = None, timeout: float = TIMEOUT,
                  community: bool = False) -> list[KatalogEintrag]:
    """Liste der Kurspakete aus dem öffentlichen Repo (``index.json``). Nur HTTPS; jeder Eintrag wird geprüft,
    kaputte werden übersprungen. ``community=True`` kennzeichnet alle Einträge als Community-Pakete (die Herkunft
    bestimmt die App, nie die Datei)."""
    url = url or (community_url() if community else katalog_url())
    if not _url_ok(url):
        raise PaketFehler("Die Liste der Kurspakete muss über https:// geladen werden.")
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with opener(req, timeout=timeout) as r:
            daten = json.loads(r.read(MAX_JSON + 1)[:MAX_JSON].decode("utf-8"))
    except (OSError, ValueError) as e:
        raise PaketFehler(f"Die Liste der Kurspakete ließ sich nicht laden ({e}).") from None
    if not isinstance(daten, dict) or daten.get("format") != KATALOG_FORMAT or not isinstance(daten.get("pakete"),
                                                                                           list):
        raise PaketFehler("Die Liste der Kurspakete aus dem Internet hat ein unbekanntes Format.")
    eintraege = []
    for d in daten["pakete"][:500]:
        if not isinstance(d, dict):
            continue
        w = "Liste der Kurspakete"
        try:
            kid = _feld(d, "id", w, pflicht=True, max_len=60)
            stufe = _feld(d, "stufe", w, pflicht=True)
            version = _feld(d, "version", w, pflicht=True, max_len=20)
            sha = _feld(d, "sha256", w, pflicht=True, max_len=64).lower()
            ziel = urllib.parse.urljoin(url, _feld(d, "datei", w, pflicht=True, max_len=500))
            groesse = _zahl(d, "groesse", w, minimum=1, maximum=MAX_GESAMT)
            if not (ID_RE.match(kid) and stufe in STUFEN and VERSION_RE.match(version) and _HEX64.match(sha)
                    and _url_ok(ziel)):
                continue
            eintraege.append(KatalogEintrag(
                id=kid, name=_feld(d, "name", w, pflicht=True, max_len=120), version=version, stufe=stufe,
                beschreibung=_feld(d, "beschreibung", w, max_len=2000, mehrzeilig=True),
                dauer_minuten=_zahl(d, "dauer_minuten", w, minimum=0, maximum=6000, standard=0),
                url=ziel, sha256=sha, groesse=groesse, entwurf=d.get("entwurf") is True,
                community=community))
        except PaketFehler:
            continue
    return eintraege


def katalog_alle(opener: Opener | None = None, timeout: float = TIMEOUT) -> tuple[list[KatalogEintrag], str]:
    """Offizielle Liste plus (falls eingeschaltet) Community-Liste. Ein Fehler der Community-Quelle blockiert die
    offizielle Liste nicht – er kommt als Hinweistext zurück. Gleiche ID wie offiziell: offizieller Eintrag gewinnt."""
    eintraege = katalog_laden(opener=opener, timeout=timeout)
    hinweis = ""
    if community_an():
        try:
            offiziell = {e.id for e in eintraege}
            eintraege += [e for e in katalog_laden(opener=opener, timeout=timeout, community=True)
                          if e.id not in offiziell]
        except PaketFehler as e:
            hinweis = f"Community-Kurspakete nicht erreichbar: {e}"
    return eintraege, hinweis


def herunterladen(eintrag: KatalogEintrag, ersetzen: bool = False, opener: Opener | None = None,
                  progress: ProgressFn | None = None, timeout: float = TIMEOUT) -> Kurspaket:
    """Kurspaket aus dem Katalog laden, Größe und Prüfsumme vergleichen, dann importieren."""
    if not _url_ok(eintrag.url):
        raise PaketFehler("Kurspakete werden nur über https:// geladen.")
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(eintrag.url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    bibliothek_dir().mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".download-", suffix=SUFFIX, dir=bibliothek_dir())
    tmp = Path(name)
    try:
        geladen = 0
        with os.fdopen(fd, "wb") as out:
            try:
                with opener(req, timeout=timeout) as r:
                    while chunk := r.read(256 * 1024):
                        geladen += len(chunk)
                        if geladen > eintrag.groesse:
                            raise PaketFehler("Der Download ist größer als angekündigt – abgebrochen.")
                        h.update(chunk)
                        out.write(chunk)
                        if progress:
                            progress(geladen / eintrag.groesse, f"Lade „{eintrag.name}“ …")
            except OSError as e:
                raise PaketFehler(f"Download fehlgeschlagen ({e}).") from None
        if h.hexdigest() != eintrag.sha256:
            raise PaketFehler("Die Prüfsumme des heruntergeladenen Kurspakets stimmt nicht – Datei verworfen.")
        with tempfile.TemporaryDirectory(prefix=".pruefen-", dir=bibliothek_dir()) as pruef:
            entpacken(tmp, Path(pruef) / "p")
            if laden(Path(pruef) / "p").id != eintrag.id:
                raise PaketFehler("Das heruntergeladene Kurspaket passt nicht zum Eintrag in der Liste – verworfen.")
        return importieren(tmp, ersetzen=ersetzen, herkunft=COMMUNITY if eintrag.community else INTERNET,
                           sha256=eintrag.sha256)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- Fortschritt (nur lokal)
def _fortschritt_datei() -> Path:
    return bibliothek_dir() / "fortschritt.json"


@dataclass
class Fortschritt:
    """Fortschritt im Selbstlern-Modus – bleibt auf diesem Rechner."""
    paket_id: str
    agent_pc: str = ""
    lektion: int = 0                                     # aktuelle Lektion (Index)
    erledigt: list[str] = field(default_factory=list)    # Lektionsordner
    pruefungen: dict[str, bool] = field(default_factory=dict)
    quiz: dict[str, list[int]] = field(default_factory=dict)   # Ordner → [richtig, gesamt]
    skripte_erlaubt: str = ""                            # Kennung der Skripte, denen zugestimmt wurde
    gestartet: float = 0.0
    zuletzt: float = 0.0

    @staticmethod
    def _alle() -> dict:
        try:
            d = storage.read_json(_fortschritt_datei())
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    @classmethod
    def laden(cls, paket_id: str) -> Fortschritt:
        d = cls._alle().get(paket_id)
        f = cls(paket_id)
        if not isinstance(d, dict):
            return f
        if isinstance(d.get("agent_pc"), str):
            f.agent_pc = d["agent_pc"]
        if isinstance(d.get("lektion"), int) and not isinstance(d["lektion"], bool) and d["lektion"] >= 0:
            f.lektion = d["lektion"]
        if isinstance(d.get("erledigt"), list):
            f.erledigt = [x for x in d["erledigt"] if isinstance(x, str)]
        if isinstance(d.get("pruefungen"), dict):
            f.pruefungen = {k: v for k, v in d["pruefungen"].items() if isinstance(v, bool)}
        if isinstance(d.get("quiz"), dict):
            f.quiz = {k: v for k, v in d["quiz"].items()
                      if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v)}
        if isinstance(d.get("skripte_erlaubt"), str):
            f.skripte_erlaubt = d["skripte_erlaubt"]
        for key in ("gestartet", "zuletzt"):
            if isinstance(d.get(key), (int, float)) and not isinstance(d[key], bool):
                setattr(f, key, float(d[key]))
        return f

    def speichern(self) -> None:
        self.zuletzt = time.time()
        if not self.gestartet:
            self.gestartet = self.zuletzt
        alle = self._alle()
        alle[self.paket_id] = {"agent_pc": self.agent_pc, "lektion": self.lektion, "erledigt": self.erledigt,
                               "pruefungen": self.pruefungen, "quiz": self.quiz,
                               "skripte_erlaubt": self.skripte_erlaubt, "gestartet": self.gestartet,
                               "zuletzt": self.zuletzt}
        bibliothek_dir().mkdir(parents=True, exist_ok=True)
        storage.write_json(_fortschritt_datei(), alle)

    @classmethod
    def vergessen(cls, paket_id: str) -> None:
        alle = cls._alle()
        if alle.pop(paket_id, None) is not None:
            storage.write_json(_fortschritt_datei(), alle)

    @property
    def begonnen(self) -> bool:
        return bool(self.gestartet)

    def fertig(self, paket: Kurspaket) -> int:
        return len({lek.ordner for lek in paket.lektionen} & set(self.erledigt))

    def anteil(self, paket: Kurspaket) -> float:
        return self.fertig(paket) / max(1, len(paket.lektionen))

    def text(self, paket: Kurspaket) -> str:
        if not self.begonnen:
            return "nicht begonnen"
        if paket.lektionen and self.fertig(paket) == len(paket.lektionen):
            return "abgeschlossen"
        return f"{self.fertig(paket)} von {len(paket.lektionen)} Lektionen"

    def gehe_zu(self, paket: Kurspaket, index: int) -> None:
        self.lektion = max(0, min(index, len(paket.lektionen) - 1))
        self.speichern()

    def erledigen(self, lek: Lektion) -> None:
        if lek.ordner not in self.erledigt:
            self.erledigt.append(lek.ordner)


# ---------------------------------------------------------------- Selbstlern-Modus: Agent-PC
def agent_pc_vorschlag(paket: Kurspaket) -> str:
    """Freier Name für den Agent-PC: ``rezept.name`` (z. B. „agent-kurs“), sonst „kurs-<id>“ (höchstens 40)."""
    basis = (paket.rezept.name or f"kurs-{paket.id}")[:37].rstrip("-_")
    vorhanden = {m.name for m in vm.list_all()}
    if basis not in vorhanden:
        return basis
    for n in range(2, 100):
        if f"{basis}-{n}" not in vorhanden:
            return f"{basis}-{n}"
    return basis


def passende_vorlage(paket: Kurspaket) -> str | None:
    """Vorlage aus dem Rezept, wenn sie hier vorhanden und für diese Architektur ist – sonst None (neu einrichten)."""
    if not paket.rezept.vorlage:
        return None
    from bonys_agents import host, templates

    try:
        t = templates.get(paket.rezept.vorlage)
    except (KeyError, OSError, ValueError, RuntimeError):
        return None
    return t.name if t.arch == host.detect().arch else None


def agent_pc(paket: Kurspaket) -> vm.VM | None:
    """Der Agent-PC, der für dieses Kurspaket gemerkt ist – None, wenn es ihn nicht (mehr) gibt."""
    name = Fortschritt.laden(paket.id).agent_pc
    if not name:
        return None
    try:
        return vm.get(name)
    except (KeyError, OSError, ValueError, RuntimeError):
        return None


def agent_pc_merken(paket: Kurspaket, name: str) -> Fortschritt:
    f = Fortschritt.laden(paket.id)
    f.agent_pc = name
    f.speichern()
    return f


# ---------------------------------------------------------------- Anzeige
_KASTEN = {"hinweis": "ℹ️ Hinweis", "tipp": "💡 Tipp", "warnung": "⚠️ Achtung", "datenschutz": "🔒 Datenschutz"}
_DIV_AUF = re.compile(r"^:::+\s*(\{[^}]*\}|[\w-]+)?\s*$")
_FELD_TEXT = re.compile(r'text="([^"]*)"')


def markdown_fuer_anzeige(text: str) -> str:
    """Markdown der Handbücher (Pandoc) für die Anzeige in Bony's Agents aufbereiten.

    Titelblock (``---`` … ``---``) wird zur Überschrift, HTML-Kommentare fallen weg, Kästen (``::: tipp`` …
    ``:::``) werden zu Zitaten mit Beschriftung, Felder zum Ausfüllen (``::: {.feld text="…"}``) zu einer Zeile.
    Rohes HTML zeigt die Oberfläche ohnehin nicht an (``MarkdownNoHTML``).
    """
    zeilen = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    if zeilen and zeilen[0].strip() == "---":
        try:
            ende = zeilen.index("---", 1)
        except ValueError:
            ende = -1
        if ende > 0:
            kopf = {}
            for z in zeilen[1:ende]:
                k, _, v = z.partition(":")
                kopf[k.strip()] = v.strip().strip("\"'")
            if kopf.get("title"):
                out.append(f"# {kopf['title']}")
            if kopf.get("subtitle"):
                out.append(f"*{kopf['subtitle']}*")
            zeilen = zeilen[ende + 1:]
    text = re.sub(r"<!--.*?-->", "", "\n".join(zeilen), flags=re.S)
    stapel: list[str] = []
    for z in text.split("\n"):
        m = _DIV_AUF.match(z.strip())
        if m and z.strip().startswith(":::"):
            art = (m.group(1) or "").strip()
            if not art:                       # schließt den innersten Kasten
                if stapel:
                    stapel.pop()
                    out.append("")
                continue
            if art.startswith("{") and ".feld" in art:
                t = _FELD_TEXT.search(art)
                out.append(f"\n**{t.group(1)}:** ________________________\n" if t and t.group(1)
                           else "\n________________________\n")
                stapel.append("feld")
                continue
            stapel.append("kasten")
            out.append("")
            out.append(f"> **{_KASTEN.get(art.strip('{}. '), art.strip('{}. ').capitalize())}:**")
            continue
        if stapel and stapel[-1] == "kasten":
            out.append(f"> {z}" if z.strip() else ">")
        else:
            out.append(z)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
