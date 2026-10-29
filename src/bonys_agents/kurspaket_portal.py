# SPDX-License-Identifier: GPL-3.0-or-later
"""Lokale Intake-Prüfung für künftige Kursportal-Einreichungen.

Die Schicht behandelt fremde ``.bonyspaket``-Dateien nur als Daten. Sie führt
keine Paket-Skripte aus und liefert einen sanitisierten technischen Vorbericht.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import secrets
import tempfile

from bonys_agents import kurspaket


STATUS_APPROVED = "approved"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_REJECTED = "rejected"

MAX_EINREICHUNG = 50 * 1024 * 1024   # Originaldatei; das Format erlaubt entpackt mehr, das Portal nimmt weniger an
GROSS_DATEIEN = 300                  # darüber: ungewöhnlich komplex -> menschliche Prüfung
GROSS_LEKTIONEN = 30
GROSS_ENTPACKT = 50 * 1024 * 1024
MAX_FUNDSTELLEN = 20
MAX_BESCHREIBUNG = 2000
MAX_MELDUNG = 300                    # Meldungen können Absender-Text enthalten (Dateinamen, Feldwerte)

_EXTERNAL_LINK = re.compile(r"https://[^\s)\]>\"']+")
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".sh", ".py", ""}


@dataclass(frozen=True)
class Pruefbericht:
    """Sanitizierter Vorbericht ohne Geheimniswerte oder lokale Arbeitswege."""

    status: str
    dateiname: str
    groesse: int
    sha256: str
    paket_id: str = ""
    version: str = ""
    name: str = ""
    stufe: str = ""
    beschreibung: str = ""
    dauer_minuten: int = 0
    sprache: str = "de"
    skripte: list[str] = field(default_factory=list)
    externe_links: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    fundstellen: list[str] = field(default_factory=list)   # Datei, Zeile, Art – nie der Fundwert

    def as_dict(self) -> dict:
        return asdict(self)


def _bereinigen(text: str, maximum: int = MAX_MELDUNG) -> str:
    """Steuerzeichen entfernen und Länge begrenzen, bevor fremder Text in den Bericht kommt."""
    sauber = "".join(c if c.isprintable() else " " for c in str(text)).strip()
    return sauber if len(sauber) <= maximum else sauber[:maximum - 1] + "…"


def _sha256(datei: Path) -> str:
    digest = hashlib.sha256()
    with datei.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _links(ordner: Path) -> list[str]:
    gefunden: set[str] = set()
    for datei in ordner.rglob("*"):
        if not datei.is_file() or datei.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            text = datei.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        gefunden.update(_EXTERNAL_LINK.findall(text))
    return sorted(gefunden)


def _basis(datei: Path, status: str, findings: list[str]) -> Pruefbericht:
    try:
        groesse = datei.stat().st_size
        sha = _sha256(datei)
    except OSError:
        groesse = 0
        sha = ""
    return Pruefbericht(status=status, dateiname=datei.name, groesse=groesse, sha256=sha,
                        findings=list(findings))


def _skript_dateien(ordner: Path) -> list[str]:
    return sorted(p.relative_to(ordner).as_posix() for p in ordner.rglob("*")
                  if p.is_file() and p.suffix.lower() in kurspaket.SKRIPT_ENDUNGEN)


def _umfang(ordner: Path) -> tuple[int, int]:
    dateien = [p for p in ordner.rglob("*") if p.is_file()]
    return len(dateien), sum(p.stat().st_size for p in dateien)


def pruefen(datei: Path, bekannt: Mapping[str, set[str]] | None = None,
            reserviert: Collection[str] = ()) -> Pruefbericht:
    """Prüft ein fremdes Kurspaket ohne Skriptausführung.

    ``approved`` bedeutet hier ausschließlich technisch unauffällig. Pakete mit
    Skripten, externen Links, ungewöhnlichem Umfang oder möglichem Duplikat werden
    mindestens ``needs_review`` und sind damit nicht automatisch freigegeben.

    ``bekannt`` ordnet Paket-IDs den SHA-256-Summen bereits eingereichter Dateien zu.
    ``reserviert`` sind IDs der mitgelieferten Pakete; wer eine davon einreicht, wird abgelehnt.
    """
    datei = Path(datei)
    if not datei.is_file():
        return _basis(datei, STATUS_REJECTED, ["Die Kurspaket-Datei fehlt."])
    try:
        groesse = datei.stat().st_size
        if groesse > MAX_EINREICHUNG:
            return _basis(datei, STATUS_REJECTED,
                          [f"Die Datei ist größer als {MAX_EINREICHUNG // (1024 * 1024)} MiB."])
        sha = _sha256(datei)
        with tempfile.TemporaryDirectory(prefix="bonys-kursportal-") as tmp:
            ordner = Path(tmp) / "paket"
            kurspaket.entpacken(datei, ordner)
            paket = kurspaket.laden(ordner)
            kopf = dict(dateiname=datei.name, groesse=groesse, sha256=sha,
                        paket_id=_bereinigen(paket.id), version=_bereinigen(paket.version),
                        name=_bereinigen(paket.name), stufe=_bereinigen(paket.stufe),
                        beschreibung=_bereinigen(paket.beschreibung, MAX_BESCHREIBUNG),
                        dauer_minuten=int(paket.dauer_minuten), sprache=_bereinigen(paket.sprache))
            if paket.id in set(reserviert):
                return Pruefbericht(status=STATUS_REJECTED, **kopf, findings=[
                    "Diese Paket-ID gehört zu einem mitgelieferten Kurspaket. Bitte eine andere ID wählen."])
            funde = kurspaket.geheimnisse_suchen(ordner)
            if funde:
                return Pruefbericht(
                    status=STATUS_REJECTED, **kopf,
                    findings=["Geheimnis- oder personenbezogene Daten gefunden."],
                    fundstellen=[_bereinigen(f) for f in funde[:MAX_FUNDSTELLEN]])
            skripte = sorted(set(s[2] for s in paket.skripte()) | set(_skript_dateien(ordner)))
            links = _links(ordner)
            dateien, entpackt = _umfang(ordner)
            findings = []
            if skripte:
                findings.append("Das Paket enthält Skripte (Prüf- oder Startskripte) und braucht menschliche Prüfung.")
            if links:
                findings.append("Das Paket enthält externe HTTPS-Links und braucht Inhaltsprüfung.")
            if dateien > GROSS_DATEIEN or len(paket.lektionen) > GROSS_LEKTIONEN or entpackt > GROSS_ENTPACKT:
                findings.append("Das Paket ist ungewöhnlich groß oder komplex und braucht menschliche Prüfung.")
            frueher = (bekannt or {}).get(paket.id, set())
            if sha in frueher:
                findings.append("Diese Datei wurde bereits eingereicht (Duplikat).")
            elif frueher:
                findings.append("Die Paket-ID wurde bereits mit anderem Inhalt eingereicht und braucht Prüfung.")
            return Pruefbericht(
                status=STATUS_NEEDS_REVIEW if findings else STATUS_APPROVED, **kopf,
                skripte=skripte, externe_links=links, findings=findings)
    except kurspaket.PaketFehler as exc:
        return _basis(datei, STATUS_REJECTED, [_bereinigen(exc)])
    except OSError as exc:
        grund = f"Datei konnte nicht geprüft werden: {exc.strerror or exc}."
        return _basis(datei, STATUS_REJECTED, [_bereinigen(grund)])


@dataclass(frozen=True)
class Einreichung:
    """Eine eingereichte Fassung: opake ID und Zeitpunkt zusätzlich zum (reproduzierbaren) Prüfbericht."""

    submission_id: str
    eingereicht_am: str
    bericht: Pruefbericht

    def as_dict(self) -> dict:
        return asdict(self)


def einreichen(datei: Path, bekannt: Mapping[str, set[str]] | None = None,
               reserviert: Collection[str] = ()) -> Einreichung:
    """Lokale Einreichung: prüft die Datei und vergibt eine neue Submission-ID. Speichert und veröffentlicht nichts."""
    return Einreichung(
        submission_id=secrets.token_hex(16),
        eingereicht_am=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        bericht=pruefen(datei, bekannt, reserviert))
