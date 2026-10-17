# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurse über das Bony-Netz (Aufgabe 04): anlegen und steuern (Kursleiter), beitreten und verlassen (Teilnehmer).

Fenster: ``gui/kurse_dialog.py`` (Teilnahme, beide Editionen) und ``trainer/gui/kurse_leiten.py`` (Kursleitung, nur
Kursleiter-Version). Die Schulung im eigenen Netz (Vorlage freigeben, „Schulung beitreten“, Vorführen, Hilfe-Schalter)
bleibt daneben unverändert – sie braucht weder Internet noch Bony-Netz.

Wie ``bonys_agents.netz``: Alle Aufrufe blockieren bis zu 15 Sekunden (nur im Hintergrund), und ohne eingeschaltetes
Bony-Netz mit angemeldeter Instanz gibt es keinen Kontakt zur Zentrale (RuntimeError). Fehlermeldungen der Zentrale
(Code abgelaufen, Kurs voll, kein Kursleiter …) kommen unverändert als ``ZentraleFehler.meldung`` an die Oberfläche –
anders als in ``netz._fragen`` wird ein 404 hier also nicht als „kein Bony-Netz-Server“ gedeutet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

from bony_netz import Konto, Zentrale, ZentraleFehler
from bony_netz.zentrale import kurscode_formatieren

from bonys_agents import netz

T = TypeVar("T")

KURSLEITER_NAME = "kursleiter_name"   # Schlüssel in konto.extra
ANZEIGENAME = "anzeigename"

OFFEN, LAEUFT, PAUSIERT, BEENDET = "offen", "laeuft", "pausiert", "beendet"
STATUS_TEXT = {OFFEN: "offen", LAEUFT: "läuft", PAUSIERT: "pausiert", BEENDET: "beendet"}
_REIHENFOLGE = {LAEUFT: 0, PAUSIERT: 1, OFFEN: 2, BEENDET: 3}

TAGE_MIN, TAGE_MAX, TAGE_STANDARD = 1, 60, 14
NAME_MAX = 80
KURSANSICHT_SEKUNDEN = 15     # Kursansicht und Kursliste, solange sichtbar
TEILNAHMEN_SEKUNDEN = 60      # „Der Kurs X hat begonnen“ – höchstens so oft fragen

NETZ_HINWEIS = ("Solange der Kurs läuft, kannst du die gewählten Agenten-PCs der Teilnehmer über das Bony-Netz "
                "erreichen.")
BEENDEN_HINWEIS = "Alle Teilnehmer verlieren den Zugang."
KURSRAUM_SPAETER = "Der Kursraum mit Bildschirm, Ton, Kamera und Chat kommt mit einer der nächsten Versionen."


def _aufruf(fn: Callable[[Zentrale], T]) -> T:
    """Aufruf der Zentrale mit der angemeldeten Instanz. Ist sie auf dem Server gelöscht, wird abgemeldet.

    Wirft RuntimeError (Bony-Netz aus), NetzFehler, ZentraleFehler oder KeinBonyNetz (Antwort ist kein JSON).
    """
    konto, zentrale = netz._zentrale()
    try:
        return fn(zentrale)
    except ZentraleFehler as e:
        netz._anmeldung_pruefen(konto, e)
        raise
    except (ValueError, KeyError, TypeError):
        raise netz._kein_server(konto.server, "unerwartete Antwort") from None


def _zeit(wert) -> float | None:
    return float(wert) if isinstance(wert, (int, float)) and not isinstance(wert, bool) and wert > 0 else None


def datum(ts: float | None, uhrzeit: bool = True) -> str:
    if ts is None:
        return "–"
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M" if uhrzeit else "%d.%m.%Y")
    except (OverflowError, OSError, ValueError):
        return "–"


@dataclass
class Teilnehmer:
    instanz_id: str
    anzeigename: str
    geraet_name: str = ""
    geraet_ip: str = ""
    beigetreten: float | None = None

    @classmethod
    def aus(cls, d: dict) -> Teilnehmer:
        return cls(str(d["instanz_id"]), str(d.get("anzeigename") or "?"), str(d.get("geraet_name") or ""),
                   str(d.get("geraet_ip") or ""), _zeit(d.get("beigetreten")))


@dataclass
class Kurs:
    kurs_id: str
    name: str
    kursleiter_name: str = ""
    status: str = OFFEN
    code: str = ""                  # nur für den Kursleiter
    code_gueltig_bis: float | None = None
    erstellt: float | None = None
    teilnehmer: list[Teilnehmer] = field(default_factory=list)
    mein_geraet_id: str = ""        # nur bei eigenen Teilnahmen

    @classmethod
    def aus(cls, d) -> Kurs:
        if not isinstance(d, dict):
            raise TypeError("kein Kurs")
        return cls(
            kurs_id=str(d["kurs_id"]), name=str(d.get("name") or "?"),
            kursleiter_name=str(d.get("kursleiter_name") or ""), status=str(d.get("status") or OFFEN),
            code=str(d.get("code") or ""), code_gueltig_bis=_zeit(d.get("code_gueltig_bis")),
            erstellt=_zeit(d.get("erstellt")),
            teilnehmer=[Teilnehmer.aus(t) for t in d.get("teilnehmer") or [] if isinstance(t, dict)],
            mein_geraet_id=str(d.get("mein_geraet_id") or ""),
        )

    @property
    def status_text(self) -> str:
        return STATUS_TEXT.get(self.status, self.status)

    @property
    def laeuft(self) -> bool:
        return self.status == LAEUFT

    @property
    def beendet(self) -> bool:
        return self.status == BEENDET


def _sortiert(kurse: list[Kurs]) -> list[Kurs]:
    return sorted(kurse, key=lambda k: (_REIHENFOLGE.get(k.status, 9), -(k.erstellt or 0), k.name.lower()))


def _liste(antwort) -> list[Kurs]:
    if not isinstance(antwort, list):
        raise TypeError("keine Liste")
    return _sortiert([Kurs.aus(d) for d in antwort])


def gemerkt(schluessel: str) -> str:
    """Gemerkter Name aus konto.extra (``KURSLEITER_NAME`` oder ``ANZEIGENAME``) – ohne den Server zu fragen."""
    wert = Konto.laden().extra.get(schluessel)
    return wert if isinstance(wert, str) else ""


def _merken(schluessel: str, wert: str) -> None:
    try:
        netz.aendern(lambda k: k.extra.__setitem__(schluessel, wert))
    except OSError:
        pass   # nur eine Bequemlichkeit


def _text(wert: str, was: str) -> str:
    wert = " ".join(wert.split())
    if not wert:
        raise ValueError(f"Bitte {was} eingeben.")
    if len(wert) > NAME_MAX:
        raise ValueError(f"{was[0].upper()}{was[1:]} ist zu lang (höchstens {NAME_MAX} Zeichen).")
    return wert


# ---------------------------------------------------------------- Kursleiter
def ist_kursleiter() -> bool:
    """Fragt die Zentrale (``instanz()["ist_kursleiter"]``) und merkt das Ergebnis in der gemeinsamen konto.json."""
    instanz = _aufruf(lambda z: z.instanz())
    an = bool(instanz["ist_kursleiter"])
    _kursleiter_merken(an)
    return an


def _kursleiter_merken(an: bool) -> None:
    alt = Konto.laden().instanz_id

    def merken(k) -> None:
        if k.instanz_id == alt:
            k.ist_kursleiter = an

    try:
        netz.aendern(merken)
    except OSError:
        pass


def kursleiter_freischalten(code: str) -> None:
    code = code.strip()
    if not code:
        raise ValueError("Bitte den Kursleiter-Code eingeben.")
    _aufruf(lambda z: z.kursleiter_freischalten(code))
    _kursleiter_merken(True)


def geleitete_kurse(auch_beendete: bool = False) -> list[Kurs]:
    return _liste(_aufruf(lambda z: z.geleitete_kurse(auch_beendete)))


def geleiteter_kurs(kurs_id: str) -> Kurs | None:
    """Einen eigenen Kurs frisch holen (auch beendet). None, wenn es ihn nicht mehr gibt."""
    return next((k for k in geleitete_kurse(True) if k.kurs_id == kurs_id), None)


def kurs_anlegen(name: str, kursleiter_name: str, tage: int = TAGE_STANDARD) -> Kurs:
    name = _text(name, "einen Kursnamen")
    kursleiter_name = _text(kursleiter_name, "deinen Anzeigenamen")
    if not TAGE_MIN <= int(tage) <= TAGE_MAX:
        raise ValueError(f"Der Code kann {TAGE_MIN} bis {TAGE_MAX} Tage gültig sein.")
    _merken(KURSLEITER_NAME, kursleiter_name)
    return Kurs.aus(_aufruf(lambda z: z.kurs_anlegen(name, kursleiter_name, int(tage))))


def status_setzen(kurs_id: str, status: str) -> Kurs:
    aufrufe = {LAEUFT: Zentrale.kurs_starten, PAUSIERT: Zentrale.kurs_pausieren, BEENDET: Zentrale.kurs_beenden}
    if status not in aufrufe:
        raise ValueError(f"Unbekannter Status: {status}")
    antwort = _aufruf(lambda z: aufrufe[status](z, kurs_id))
    try:
        return Kurs.aus(antwort)
    except (KeyError, TypeError):   # Zentrale antwortet nur knapp – dann frisch holen
        return geleiteter_kurs(kurs_id) or Kurs(kurs_id, "?", status=status)


def teilnehmer_entfernen(kurs_id: str, instanz_id: str) -> None:
    _aufruf(lambda z: z.teilnehmer_entfernen(kurs_id, instanz_id))


# ---------------------------------------------------------------- Teilnehmer
VPN_RECHNER = "vpn_rechner"   # merkt Bony's VPN in konto.extra: {instanz_id, name} des Rechners selbst


def _vpn_rechner() -> str:
    """Netzname dieses Rechners, wenn Bony's VPN ihn mit der Instanz verbunden hat – sonst ""."""
    konto = Konto.laden()
    rekord = konto.extra.get(VPN_RECHNER)
    if isinstance(rekord, dict) and rekord.get("instanz_id") == konto.instanz_id:
        return str(rekord.get("name") or "")
    return ""


def eigene_geraete() -> list[dict]:
    """Agenten-PCs dieser Instanz im Bony-Netz, online zuerst, dann nach Name.

    Ohne den Rechner selbst (über Bony's VPN im Netz): Der Kursleiter erreicht das gewählte Gerät, solange der Kurs
    läuft – das soll nie der eigene Rechner sein, nur ein Agent-PC.
    """
    liste = _aufruf(lambda z: z.geraete())
    if not isinstance(liste, list):
        raise TypeError("keine Liste")
    selbst = _vpn_rechner()
    geraete = [g for g in liste if isinstance(g, dict) and g.get("geraet_id") is not None
               and not (selbst and g.get("name") == selbst)]
    return sorted(geraete, key=lambda g: (not g.get("online"), str(g.get("name", "")).lower()))


def kurs_beitreten(code: str, geraet_id: str, anzeigename: str) -> Kurs:
    code = kurscode_formatieren(code)
    if len(code) < 4:
        raise ValueError("Bitte den Kurscode eingeben (z. B. K7QX-M3PA).")
    if not geraet_id:
        raise ValueError("Bitte einen Agent-PC wählen.")
    anzeigename = _text(anzeigename, "deinen Anzeigenamen")
    _merken(ANZEIGENAME, anzeigename)
    antwort = _aufruf(lambda z: z.kurs_beitreten(code, str(geraet_id), anzeigename))
    try:
        return Kurs.aus(antwort)
    except (KeyError, TypeError):
        return Kurs("", code)


def teilnahmen() -> list[Kurs]:
    return _liste(_aufruf(lambda z: z.teilnahmen()))


def kurs_verlassen(kurs_id: str) -> None:
    _aufruf(lambda z: z.kurs_verlassen(kurs_id))


class Beobachter:
    """Merkt, welche Teilnahmen schon als „läuft“ gemeldet wurden – für „Der Kurs X hat begonnen“."""

    def __init__(self) -> None:
        self.gemeldet: set[str] = set()

    def neu_begonnen(self, kurse: list[Kurs]) -> list[Kurs]:
        laufend = {k.kurs_id: k for k in kurse if k.laeuft}
        neu = [k for i, k in laufend.items() if i not in self.gemeldet]
        self.gemeldet = set(laufend)   # pausiert und wieder gestartet: erneut melden
        return neu


def begonnen_text(kurse: list[Kurs]) -> str:
    if len(kurse) == 1:
        return f"Der Kurs „{kurse[0].name}“ hat begonnen – „Kurse“ → „Kursraum betreten“."
    return "Diese Kurse haben begonnen: " + ", ".join(f"„{k.name}“" for k in kurse) + "."
