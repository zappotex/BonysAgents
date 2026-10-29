# SPDX-License-Identifier: GPL-3.0-or-later
"""Musik und Radio beim Lernen – Sender, eigene Musik und Einstellungen (ohne Qt).

Die Leiste unten im Hauptfenster (``gui/musik_ui.py``) spielt bewusst gewählte Quellen ab:

- Radio: eine kleine feste Liste öffentlich-rechtlicher Sender (``SENDER``) und eigene Sender (nur ``https://``,
  von Hand eingetragen oder aus einer ``.m3u``/``.pls``-Datei übernommen);
- eigene Musik: Dateien aus einem Ordner und/oder einzeln gewählte Dateien dieses Rechners.

Nichts startet von selbst – auch nicht beim Programmstart mit einer zuletzt gewählten Quelle. Wiedergabelisten
und Einstellungen sind Daten: Es werden nur ``https``-Adressen übernommen, nichts wird ausgeführt.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from bonys_agents import storage

EINSTELLUNG = "musik"
MUSIK_ENDUNGEN = {".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".wav"}
LISTEN_ENDUNGEN = {".m3u", ".m3u8", ".pls"}
MAX_TITEL = 5000              # Dateien in der eigenen Liste
MAX_TIEFE = 6                 # Unterordner beim Durchsuchen eines Musikordners
MAX_EIGENE_SENDER = 50
MAX_LISTE = 256 * 1024        # Größe einer .m3u/.pls-Datei
MAX_URL = 500
MAX_NAME = 80
LAUTSTAERKE_STANDARD = 40     # Prozent – lieber leise anfangen

RADIO, MUSIK = "radio", "musik"


class MusikFehler(Exception):
    """Verständliche Meldung für die Oberfläche."""


@dataclass(frozen=True)
class Sender:
    name: str
    url: str
    eigen: bool = False


# Hirschmilch (https://hirschmilch.de) – offizielle Stream-Adressen aus deren .pls-Listen (geprüft am 29.10.2026).
# Die App verweist nur auf den Stream; gehört wird direkt beim Sender (dort: nur privat, nicht kommerziell).
SENDER: tuple[Sender, ...] = tuple(
    Sender(f"Hirschmilch {name}", f"https://hirschmilch.de:7000/{kanal}.mp3") for kanal, name in (
        ("chillout", "Chillout"), ("electronic", "Electronic"), ("hypnotic", "Hypnotic"),
        ("organic-house", "Organic House"), ("prog-house", "Prog House"), ("progressive", "Progressive"),
        ("psytrance", "Psytrance"), ("techno", "Techno"),
    )
)

_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")


def name_pruefen(name: str) -> str:
    name = _STEUERZEICHEN.sub("", str(name)).strip()
    if not name:
        raise MusikFehler("Bitte einen Namen für den Sender angeben.")
    return name[:MAX_NAME]


def url_pruefen(url: str) -> str:
    """Stream-Adresse prüfen: nur ``https://`` mit Rechnername, ohne Zugangsdaten, ohne Leer-/Steuerzeichen."""
    url = str(url).strip()
    if not url or len(url) > MAX_URL or _STEUERZEICHEN.search(url) or " " in url:
        raise MusikFehler("Die Adresse ist leer, zu lang oder enthält Leerzeichen.")
    try:
        teile = urllib.parse.urlsplit(url)
        teile.port  # noqa: B018 – wirft bei ungültigem Port
    except ValueError:
        raise MusikFehler(f"„{url}“ ist keine gültige Adresse.") from None
    if teile.scheme.lower() != "https" or not teile.hostname:
        raise MusikFehler("Nur sichere Adressen mit „https://“ sind erlaubt.")
    if teile.username or teile.password:
        raise MusikFehler("Adressen mit Benutzername oder Passwort werden nicht gespeichert.")
    return url


# ---------------------------------------------------------------- Wiedergabelisten (.m3u/.pls) als Daten
def wiedergabeliste_lesen(datei: Path) -> list[Sender]:
    """Sender aus einer ``.m3u``/``.m3u8``/``.pls``-Datei – nur ``https``-Adressen, alles andere wird übergangen."""
    datei = Path(datei)
    if datei.suffix.lower() not in LISTEN_ENDUNGEN:
        raise MusikFehler("Bitte eine Wiedergabeliste (.m3u, .m3u8 oder .pls) wählen.")
    try:
        if datei.stat().st_size > MAX_LISTE:
            raise MusikFehler("Die Wiedergabeliste ist zu groß.")
        text = datei.read_bytes().decode("utf-8", errors="replace")
    except OSError as e:
        raise MusikFehler(f"„{datei.name}“ lässt sich nicht lesen: {e.strerror or e}") from None
    paare = _pls(text) if datei.suffix.lower() == ".pls" else _m3u(text)
    out: list[Sender] = []
    for name, url in paare:
        try:
            url = url_pruefen(url)
        except MusikFehler:
            continue
        try:
            name = name_pruefen(name)
        except MusikFehler:
            name = urllib.parse.urlsplit(url).hostname or url
        if all(s.url != url for s in out):
            out.append(Sender(name, url, eigen=True))
        if len(out) >= MAX_EIGENE_SENDER:
            break
    if not out:
        raise MusikFehler("In der Wiedergabeliste steht keine sichere Sender-Adresse (https://).")
    return out


def _m3u(text: str) -> list[tuple[str, str]]:
    paare, name = [], ""
    for zeile in text.splitlines():
        zeile = zeile.strip().lstrip("﻿")
        if zeile.upper().startswith("#EXTINF:"):
            name = zeile.split(",", 1)[1] if "," in zeile else ""
        elif zeile and not zeile.startswith("#"):
            paare.append((name, zeile))
            name = ""
    return paare


def _pls(text: str) -> list[tuple[str, str]]:
    dateien: dict[str, str] = {}
    titel: dict[str, str] = {}
    for zeile in text.splitlines():
        if m := re.match(r"\s*(File|Title)(\d+)\s*=\s*(.*)$", zeile, re.IGNORECASE):
            (dateien if m.group(1).lower() == "file" else titel)[m.group(2)] = m.group(3).strip()
    return [(titel.get(n, ""), dateien[n]) for n in sorted(dateien, key=int)]


# ---------------------------------------------------------------- eigene Musik
def ist_musikdatei(p: Path) -> bool:
    return p.suffix.lower() in MUSIK_ENDUNGEN and not p.name.startswith(".")


def titel_im_ordner(ordner: Path) -> list[Path]:
    """Musikdateien eines Ordners (mit Unterordnern bis ``MAX_TIEFE``), sortiert. Versteckte Dateien/Ordner und
    verlinkte Ordner werden übergangen, höchstens ``MAX_TITEL`` Dateien."""
    ordner = Path(ordner)
    if not ordner.is_dir():
        raise MusikFehler(f"Der Ordner „{ordner}“ ist nicht vorhanden.")
    out: list[Path] = []
    for wurzel, unterordner, dateien in os.walk(ordner, followlinks=False):
        tiefe = len(Path(wurzel).relative_to(ordner).parts)
        unterordner[:] = sorted(d for d in unterordner if not d.startswith(".")) if tiefe < MAX_TIEFE else []
        for name in sorted(dateien):
            p = Path(wurzel) / name
            if ist_musikdatei(p) and p.is_file():
                out.append(p)
                if len(out) >= MAX_TITEL:
                    return out
    return out


# ---------------------------------------------------------------- Einstellungen
@dataclass
class Einstellungen:
    lautstaerke: int = LAUTSTAERKE_STANDARD
    eigene_sender: list[Sender] = field(default_factory=list)
    ordner: str = ""                                   # zuletzt gewählter Musikordner
    dateien: list[str] = field(default_factory=list)   # eigene Liste (Ordner-Inhalt + einzelne Dateien)
    zufall: bool = False
    quelle: str = ""                                   # RADIO oder MUSIK – zuletzt gewählt, startet nicht von selbst
    sender_url: str = ""
    titel: int = 0

    def alle_sender(self) -> list[Sender]:
        return list(SENDER) + self.eigene_sender

    def sender(self, url: str) -> Sender | None:
        return next((s for s in self.alle_sender() if s.url == url), None)

    def sender_hinzufuegen(self, sender: Sender) -> Sender:
        neu = Sender(name_pruefen(sender.name), url_pruefen(sender.url), eigen=True)
        if vorhanden := self.sender(neu.url):
            raise MusikFehler(f"Den Sender „{vorhanden.name}“ gibt es schon.")
        if len(self.eigene_sender) >= MAX_EIGENE_SENDER:
            raise MusikFehler(f"Höchstens {MAX_EIGENE_SENDER} eigene Sender.")
        self.eigene_sender.append(neu)
        return neu

    def sender_entfernen(self, url: str) -> None:
        if any(s.url == url for s in SENDER):
            raise MusikFehler("Mitgelieferte Sender lassen sich nicht entfernen.")
        self.eigene_sender = [s for s in self.eigene_sender if s.url != url]
        if self.sender_url == url:
            self.sender_url = ""

    def dateien_hinzufuegen(self, pfade: list[Path]) -> int:
        """Musikdateien an die eigene Liste anhängen (ohne Doppelte) – gibt die Zahl der neuen zurück."""
        vorhanden = set(self.dateien)
        neu = 0
        for p in pfade:
            s = str(Path(p))
            if s in vorhanden or not ist_musikdatei(Path(p)) or len(self.dateien) >= MAX_TITEL:
                continue
            self.dateien.append(s)
            vorhanden.add(s)
            neu += 1
        return neu


def _als_sender(d: object) -> Sender | None:
    if not isinstance(d, dict):
        return None
    try:
        return Sender(name_pruefen(d.get("name", "")), url_pruefen(d.get("url", "")), eigen=True)
    except MusikFehler:
        return None


def laden() -> Einstellungen:
    """Einstellungen lesen – Unpassendes (von Hand verändert, alte Fassung) wird still übergangen."""
    d = storage.load_settings().get(EINSTELLUNG)
    e = Einstellungen()
    if not isinstance(d, dict):
        return e
    v = d.get("lautstaerke")
    if isinstance(v, int) and not isinstance(v, bool):
        e.lautstaerke = max(0, min(100, v))
    for s in d.get("eigene_sender", []) if isinstance(d.get("eigene_sender"), list) else []:
        if (sender := _als_sender(s)) and not e.sender(sender.url) and len(e.eigene_sender) < MAX_EIGENE_SENDER:
            e.eigene_sender.append(sender)
    if isinstance(d.get("ordner"), str):
        e.ordner = d["ordner"]
    if isinstance(d.get("dateien"), list):
        e.dateien = [p for p in d["dateien"] if isinstance(p, str) and ist_musikdatei(Path(p))][:MAX_TITEL]
    e.zufall = d.get("zufall") is True
    if d.get("quelle") in (RADIO, MUSIK):
        e.quelle = d["quelle"]
    if isinstance(d.get("sender_url"), str) and e.sender(d["sender_url"]):
        e.sender_url = d["sender_url"]
    t = d.get("titel")
    if isinstance(t, int) and not isinstance(t, bool) and 0 <= t < len(e.dateien):
        e.titel = t
    return e


def speichern(e: Einstellungen) -> None:
    s = storage.load_settings()
    s[EINSTELLUNG] = {
        "lautstaerke": e.lautstaerke,
        "eigene_sender": [{"name": x.name, "url": x.url} for x in e.eigene_sender],
        "ordner": e.ordner,
        "dateien": e.dateien,
        "zufall": e.zufall,
        "quelle": e.quelle,
        "sender_url": e.sender_url,
        "titel": e.titel,
    }
    storage.save_settings(s)
