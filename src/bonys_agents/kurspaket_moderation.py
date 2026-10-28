# SPDX-License-Identifier: GPL-3.0-or-later
"""Lokales Moderationsmodell mit unveränderlicher Verlaufshistorie für Kursportal-Einreichungen.

Jede Einreichung hat eine eigene append-only Verlaufsdatei. Die Einträge sind
per SHA-256 verkettet, eine nachträgliche Änderung fällt in ``verlauf_pruefen``
auf. Veröffentlichung und Rücknahme brauchen immer eine menschliche Entscheidung
mit Akteur und Begründung. Es gibt weder Webserver noch Katalog – nur lokale Dateien.
"""

from __future__ import annotations

from collections.abc import Collection
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading

from bonys_agents import kurspaket_portal as portal

try:
    import fcntl
except ImportError:            # Windows: nur der Sperre im eigenen Prozess vertrauen (dort gibt es keinen Server)
    fcntl = None

_SCHREIBEN = threading.Lock()      # Schreiben im selben Prozess nacheinander


UPLOADED = "uploaded"
SCANNING = "scanning"
NEEDS_REVIEW = "needs_review"
APPROVED = "approved"
PUBLISHED = "published"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"

# Übergänge, die ein Mensch auslösen muss (Akteur + Begründung Pflicht).
ERLAUBT_MENSCH = {
    NEEDS_REVIEW: {REJECTED, APPROVED},
    APPROVED: {PUBLISHED, REJECTED},
    PUBLISHED: {WITHDRAWN},
}
# Übergänge der automatischen Vorprüfung.
ERLAUBT_AUTO = {
    UPLOADED: {SCANNING},
    SCANNING: {NEEDS_REVIEW, APPROVED, REJECTED},
}

AKTEUR_SYSTEM = "system"
_ID = re.compile(r"[0-9a-f]{32}")
_GENESIS = "0" * 64
MAX_TEXT = 2000


class ModerationsFehler(Exception):
    """Ungültiger Übergang, fehlende Begründung oder beschädigter Verlauf."""


@dataclass(frozen=True)
class Ereignis:
    nr: int
    zeit: str
    von: str
    nach: str
    akteur: str
    begruendung: str
    bericht: dict | None
    vorher: str
    pruefsumme: str


def _hash(daten: dict) -> str:
    text = json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ereignis(zeile: str) -> Ereignis:
    return Ereignis(**json.loads(zeile))


class Moderation:
    """Ablage unter ``wurzel``: ``<id>/original.bonyspaket`` und ``<id>/verlauf.jsonl``."""

    def __init__(self, wurzel: Path, reserviert: Collection[str] = ()):
        self.wurzel = Path(wurzel)
        self.reserviert = frozenset(reserviert)     # IDs mitgelieferter Pakete: werden abgelehnt

    def _ordner(self, submission_id: str) -> Path:
        if not _ID.fullmatch(submission_id):
            raise ModerationsFehler("Ungültige Submission-ID.")
        return self.wurzel / submission_id

    def _lesen(self, submission_id: str) -> list[Ereignis]:
        verlauf = self._ordner(submission_id) / "verlauf.jsonl"
        if not verlauf.is_file():
            raise ModerationsFehler("Unbekannte Einreichung.")
        return [_ereignis(z) for z in verlauf.read_text(encoding="utf-8").splitlines() if z.strip()]

    @contextmanager
    def _sperre(self, submission_id: str):
        """Schreibsperre je Einreichung (Threads und Prozesse): Prüfen und Anhängen bilden eine Einheit, damit
        zwei gleichzeitige Entscheidungen die Hashkette nicht brechen."""
        ordner = self._ordner(submission_id)
        with _SCHREIBEN:
            if fcntl is None or not ordner.is_dir():
                yield
                return
            with (ordner / ".sperre").open("a") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def _anhaengen(self, submission_id: str, nach: str, akteur: str, begruendung: str,
                   bericht: dict | None = None) -> Ereignis:
        with self._sperre(submission_id):
            return self._anhaengen_roh(submission_id, nach, akteur, begruendung, bericht)

    def _anhaengen_roh(self, submission_id: str, nach: str, akteur: str, begruendung: str,
                       bericht: dict | None = None) -> Ereignis:
        verlauf = self._ordner(submission_id) / "verlauf.jsonl"
        bisher = self._lesen(submission_id) if verlauf.is_file() else []
        kern = dict(nr=len(bisher) + 1,
                    zeit=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    von=bisher[-1].nach if bisher else "",
                    nach=nach, akteur=akteur, begruendung=begruendung, bericht=bericht,
                    vorher=bisher[-1].pruefsumme if bisher else _GENESIS)
        ereignis = _ereignis(json.dumps({**kern, "pruefsumme": _hash(kern)}))
        with verlauf.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ereignis.__dict__, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return ereignis

    # --- Lesen -----------------------------------------------------------

    @contextmanager
    def original_bereit(self, submission_id: str):
        """Pfad der eingereichten Paketdatei zum Ansehen (nur lesen, nie ausführen)."""
        datei = self._ordner(submission_id) / "original.bonyspaket"
        if not datei.is_file():
            raise ModerationsFehler("Die Paketdatei dieser Einreichung fehlt.")
        yield datei

    def ids(self) -> list[str]:
        if not self.wurzel.is_dir():
            return []
        return sorted(p.name for p in self.wurzel.iterdir() if p.is_dir() and _ID.fullmatch(p.name))

    def status(self, submission_id: str) -> str:
        return self._lesen(submission_id)[-1].nach

    def verlauf(self, submission_id: str) -> list[Ereignis]:
        return self._lesen(submission_id)

    def bericht(self, submission_id: str) -> dict | None:
        """Letzter Prüfbericht der Vorprüfung."""
        for e in reversed(self._lesen(submission_id)):
            if e.bericht is not None:
                return e.bericht
        return None

    def verlauf_pruefen(self, submission_id: str) -> None:
        """Wirft ``ModerationsFehler``, wenn der Verlauf verändert oder unplausibel ist."""
        vorher, status = _GENESIS, ""
        for i, e in enumerate(self._lesen(submission_id), 1):
            kern = {k: v for k, v in e.__dict__.items() if k != "pruefsumme"}
            if e.nr != i or e.vorher != vorher or e.von != status or _hash(kern) != e.pruefsumme:
                raise ModerationsFehler(f"Verlauf ist an Eintrag {i} verändert worden.")
            vorher, status = e.pruefsumme, e.nach

    def _bekannt(self) -> dict[str, set[str]]:
        bekannt: dict[str, set[str]] = {}
        for sid in self.ids():
            if self.status(sid) == REJECTED:      # abgelehnte Fassungen zählen nicht als Duplikat
                continue
            b = self.bericht(sid)
            if b and b.get("paket_id"):
                bekannt.setdefault(b["paket_id"], set()).add(b["sha256"])
        return bekannt

    # --- Schreiben -------------------------------------------------------

    def einreichen(self, datei: Path, autor: str) -> str:
        """Legt eine neue Einreichung an und führt die automatische Vorprüfung aus.

        Der Autor wird nur intern im Verlauf geführt. Veröffentlicht wird nichts.
        """
        autor = (autor or "").strip()
        if not autor:
            raise ModerationsFehler("Eine Autorreferenz ist nötig.")
        pruefung = portal.einreichen(Path(datei), self._bekannt(), self.reserviert)
        sid = pruefung.submission_id
        ordner = self._ordner(sid)
        ordner.mkdir(parents=True)
        try:
            if Path(datei).is_file():
                shutil.copyfile(datei, ordner / "original.bonyspaket")
            self._anhaengen(sid, UPLOADED, autor, "Eingereicht.")
            self._anhaengen(sid, SCANNING, AKTEUR_SYSTEM, "Technische Vorprüfung gestartet.")
            bericht = pruefung.bericht
            self._anhaengen(sid, bericht.status, AKTEUR_SYSTEM,
                            " ".join(bericht.findings) or "Technisch unauffällig.", bericht.as_dict())
        except Exception:
            shutil.rmtree(ordner, ignore_errors=True)
            raise
        return sid

    def entscheiden(self, submission_id: str, nach: str, akteur: str, begruendung: str) -> Ereignis:
        """Menschliche Moderationsentscheidung; prüft Übergang, Akteur und Begründung."""
        akteur, begruendung = (akteur or "").strip(), (begruendung or "").strip()
        if not akteur or akteur == AKTEUR_SYSTEM:
            raise ModerationsFehler("Eine Entscheidung braucht einen menschlichen Akteur.")
        if not begruendung:
            raise ModerationsFehler("Eine Entscheidung braucht eine Begründung.")
        if len(begruendung) > MAX_TEXT:
            raise ModerationsFehler(f"Die Begründung ist länger als {MAX_TEXT} Zeichen.")
        with self._sperre(submission_id):
            self.verlauf_pruefen(submission_id)
            aktuell = self.status(submission_id)
            if nach not in ERLAUBT_MENSCH.get(aktuell, set()):
                raise ModerationsFehler(f"Übergang {aktuell} -> {nach} ist nicht erlaubt.")
            if nach == PUBLISHED and (self.bericht(submission_id) or {}).get("paket_id") in self.reserviert:
                raise ModerationsFehler("Die Paket-ID gehört zu einem mitgelieferten Kurspaket und wird nicht "
                                        "veröffentlicht.")
            return self._anhaengen_roh(submission_id, nach, akteur, begruendung)
