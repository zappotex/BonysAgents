# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurse über das Bony-Netz (Aufgabe 04): anlegen und steuern (Kursleiter), beitreten und verlassen (Teilnehmer).

Fenster: ``gui/kurse_dialog.py`` (Teilnahme, beide Editionen) und ``trainer/gui/kurse_leiten.py`` (Kursleitung, nur
Kursleiter-Version). Die Schulung im eigenen Netz (Vorlage freigeben, „Schulung beitreten“, Vorführen, Hilfe-Schalter)
bleibt daneben unverändert – sie braucht weder Internet noch Bony-Netz.

Wie ``bonys_agents.netz``: Alle Aufrufe blockieren bis zu 15 Sekunden (nur im Hintergrund), und ohne eingeschaltetes
Bony-Netz mit angemeldeter Instanz gibt es keinen Kontakt zur Zentrale (RuntimeError). Fehlermeldungen der Zentrale
(Code abgelaufen, Kurs voll, kein Kursleiter …) kommen unverändert als ``ZentraleFehler.meldung`` an die Oberfläche –
anders als in ``netz._fragen`` wird ein 404 hier also nicht als „kein Bony-Netz-Server“ gedeutet.

Kurspakete (Entscheidung 11 in ``docs/dev/plan-kurspakete.md``): Der Kursleiter lädt das Kurspaket zum Kurs hoch, die
Teilnehmer holen es (Prüfsumme muss passen, danach volle Prüfung wie beim Import) und melden nur Lektion und
„geschafft / noch nicht“. Der Kursleiter sieht das in der Kursansicht, solange der Kurs läuft.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from bony_netz import Konto, Zentrale, ZentraleFehler
from bony_netz.zentrale import kurscode_formatieren

from bonys_agents import kurslauf, kurspaket, netz
from bonys_agents.i18n import n_, tr

T = TypeVar("T")

KURSLEITER_NAME = "kursleiter_name"   # Schlüssel in konto.extra
ANZEIGENAME = "anzeigename"

OFFEN, LAEUFT, PAUSIERT, BEENDET = "offen", "laeuft", "pausiert", "beendet"
STATUS_TEXT = {OFFEN: n_("offen"), LAEUFT: n_("läuft"), PAUSIERT: n_("pausiert"), BEENDET: n_("beendet")}
_REIHENFOLGE = {LAEUFT: 0, PAUSIERT: 1, OFFEN: 2, BEENDET: 3}

TAGE_MIN, TAGE_MAX, TAGE_STANDARD = 1, 60, 14
NAME_MAX = 80
KURSANSICHT_SEKUNDEN = 15     # Kursansicht und Kursliste, solange sichtbar
TEILNAHMEN_SEKUNDEN = 60      # „Der Kurs X hat begonnen“ – höchstens so oft fragen

MAX_PAKET_MB = 25            # wie MAX_KURSPAKET_MB der Zentrale (Standard)
MAX_PAKET = MAX_PAKET_MB * 1024 * 1024

NETZ_HINWEIS = (n_("Solange der Kurs läuft, kannst du die gewählten Agenten-PCs der Teilnehmer über das Bony-Netz "
                   "erreichen."))
BEENDEN_HINWEIS = n_("Alle Teilnehmer verlieren den Zugang.")


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


def _ganz(wert, standard: int = 0) -> int:
    return wert if isinstance(wert, int) and not isinstance(wert, bool) else standard


@dataclass
class PaketAngaben:
    """Kurspaket eines Kurses, wie die Zentrale es kennt (die Datei selbst holt ``kurspaket_fuer_kurs``)."""
    paket_id: str
    name: str
    version: str
    lektionen: int = 0
    sha256: str = ""
    groesse: int = 0

    @classmethod
    def aus(cls, d) -> PaketAngaben | None:
        if not isinstance(d, dict) or not isinstance(d.get("paket_id"), str):
            return None
        return cls(d["paket_id"], str(d.get("name") or d["paket_id"]), str(d.get("version") or ""),
                   _ganz(d.get("lektionen")), str(d.get("sha256") or "").lower(), _ganz(d.get("groesse")))

    @property
    def text(self) -> str:
        return f"{self.name} {self.version}" + (f" · {self.lektionen} Lektionen" if self.lektionen else "")


@dataclass
class Stand:
    """Fortschritt eines Teilnehmers im Kurspaket: nur Lektion (ab 1) und „geschafft / noch nicht“."""
    lektion: int
    geschafft: bool | None = None
    aktualisiert: float | None = None

    @classmethod
    def aus(cls, d) -> Stand | None:
        if not isinstance(d, dict) or _ganz(d.get("lektion")) < 1:
            return None
        g = d.get("geschafft")
        return cls(d["lektion"], g if isinstance(g, bool) else None, _zeit(d.get("aktualisiert")))

    def lektion_text(self, paket: kurspaket.Kurspaket | None = None, gesamt: int = 0) -> str:
        if paket is not None and 0 < self.lektion <= len(paket.lektionen):
            return f"{self.lektion}. {paket.lektionen[self.lektion - 1].titel}"
        return tr("{lektion} von {gesamt}", lektion=self.lektion, gesamt=gesamt) if gesamt else str(self.lektion)

    @property
    def pruefung_text(self) -> str:
        return {True: tr("✓ geschafft"), False: tr("✗ noch nicht")}.get(self.geschafft, "–")


@dataclass
class Teilnehmer:
    instanz_id: str
    anzeigename: str
    geraet_name: str = ""
    geraet_ip: str = ""
    beigetreten: float | None = None
    stand: Stand | None = None

    @classmethod
    def aus(cls, d: dict) -> Teilnehmer:
        return cls(str(d["instanz_id"]), str(d.get("anzeigename") or "?"), str(d.get("geraet_name") or ""),
                   str(d.get("geraet_ip") or ""), _zeit(d.get("beigetreten")), Stand.aus(d.get("fortschritt")))


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
    kurspaket: PaketAngaben | None = None

    @classmethod
    def aus(cls, d) -> Kurs:
        if not isinstance(d, dict):
            raise TypeError(tr("kein Kurs"))
        return cls(
            kurs_id=str(d["kurs_id"]), name=str(d.get("name") or "?"),
            kursleiter_name=str(d.get("kursleiter_name") or ""), status=str(d.get("status") or OFFEN),
            code=str(d.get("code") or ""), code_gueltig_bis=_zeit(d.get("code_gueltig_bis")),
            erstellt=_zeit(d.get("erstellt")),
            teilnehmer=[Teilnehmer.aus(t) for t in d.get("teilnehmer") or [] if isinstance(t, dict)],
            mein_geraet_id=str(d.get("mein_geraet_id") or ""),
            kurspaket=PaketAngaben.aus(d.get("kurspaket")),
        )

    @property
    def status_text(self) -> str:
        return tr(STATUS_TEXT.get(self.status, self.status))

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
        raise TypeError(tr("keine Liste"))
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
        raise ValueError(tr("Bitte {was} eingeben.", was=was))
    if len(wert) > NAME_MAX:
        raise ValueError(tr("{wert}{wert2} ist zu lang (höchstens {NAME_MAX} Zeichen).", wert=was[0].upper(),
                            wert2=was[1:], NAME_MAX=NAME_MAX))
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
        raise ValueError(tr("Bitte den Kursleiter-Code eingeben."))
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
        raise ValueError(tr("Der Code kann {TAGE_MIN} bis {TAGE_MAX} Tage gültig sein.", TAGE_MIN=TAGE_MIN,
                            TAGE_MAX=TAGE_MAX))
    _merken(KURSLEITER_NAME, kursleiter_name)
    return Kurs.aus(_aufruf(lambda z: z.kurs_anlegen(name, kursleiter_name, int(tage))))


def status_setzen(kurs_id: str, status: str) -> Kurs:
    aufrufe = {LAEUFT: Zentrale.kurs_starten, PAUSIERT: Zentrale.kurs_pausieren, BEENDET: Zentrale.kurs_beenden}
    if status not in aufrufe:
        raise ValueError(tr("Unbekannter Status: {status}", status=status))
    antwort = _aufruf(lambda z: aufrufe[status](z, kurs_id))
    try:
        return Kurs.aus(antwort)
    except (KeyError, TypeError):   # Zentrale antwortet nur knapp – dann frisch holen
        return geleiteter_kurs(kurs_id) or Kurs(kurs_id, "?", status=status)


def teilnehmer_entfernen(kurs_id: str, instanz_id: str) -> None:
    _aufruf(lambda z: z.teilnehmer_entfernen(kurs_id, instanz_id))


def paket_packen(paket: kurspaket.Kurspaket) -> bytes:
    """Kurspaket für einen Kurs packen – mit Prüfung auf Zugangsdaten und der Größengrenze für Kurse."""
    with tempfile.TemporaryDirectory(prefix="bonys-kurspaket-") as tmp:
        datei = kurspaket.packen(paket.pfad, Path(tmp) / kurspaket.dateiname(paket))
        daten = datei.read_bytes()
    if len(daten) > MAX_PAKET:
        raise ValueError(tr("Das Kurspaket ist gepackt {wert:.1f} MB groß – für einen Kurs gehen höchstens "
                            "{MAX_PAKET_MB} MB. Große Bilder verkleinern oder weglassen.",
                            wert=len(daten) / 1024 ** 2, MAX_PAKET_MB=MAX_PAKET_MB))
    return daten


def kurspaket_hochladen(kurs_id: str, paket: kurspaket.Kurspaket) -> Kurs:
    """Kurspaket packen (mit Prüfung auf Zugangsdaten) und zum Kurs hochladen – ersetzt ein vorhandenes."""
    daten = paket_packen(paket)
    antwort = _aufruf(lambda z: z.kurspaket_hochladen(kurs_id, daten, paket.id, paket.name, paket.version,
                                                      len(paket.lektionen)))
    try:
        return Kurs.aus(antwort)
    except (KeyError, TypeError):
        return geleiteter_kurs(kurs_id) or Kurs(kurs_id, "?")


def kurspaket_entfernen(kurs_id: str) -> None:
    _aufruf(lambda z: z.kurspaket_entfernen(kurs_id))


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
        raise TypeError(tr("keine Liste"))
    selbst = _vpn_rechner()
    geraete = [g for g in liste if isinstance(g, dict) and g.get("geraet_id") is not None
               and not (selbst and g.get("name") == selbst)]
    return sorted(geraete, key=lambda g: (not g.get("online"), str(g.get("name", "")).lower()))


def kurs_beitreten(code: str, geraet_id: str, anzeigename: str) -> Kurs:
    code = kurscode_formatieren(code)
    if len(code) < 4:
        raise ValueError(tr("Bitte den Kurscode eingeben (z. B. K7QX-M3PA)."))
    if not geraet_id:
        raise ValueError(tr("Bitte einen Agent-PC wählen."))
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


_GLEICH: dict[str, str] = {}   # SHA-256 der Kurs-Datei → Ordner des inhaltsgleichen Pakets (z. B. mitgeliefert)


def kurspaket_vorhanden(angaben: PaketAngaben) -> kurspaket.Kurspaket | None:
    """Das Kurspaket des Kurses, wenn es schon in der Bibliothek liegt (aus diesem Kurs, gleiche Prüfsumme – oder
    in dieser Sitzung schon als inhaltsgleich erkannt)."""
    for p in kurspaket.liste():
        if p.id == angaben.paket_id and p.version == angaben.version and angaben.sha256 and (
                kurspaket.herkunft_sha256(p) == angaben.sha256 or _GLEICH.get(angaben.sha256) == str(p.pfad)):
            return p
    return None


def kurspaket_fuer_kurs(kurs: Kurs) -> kurspaket.Kurspaket:
    """Teilnehmer: Kurspaket des Kurses holen und in die Bibliothek übernehmen (oder das vorhandene nehmen).

    Die Datei muss zur Prüfsumme der Zentrale passen und wird wie jeder Import vollständig geprüft. Ist der Inhalt
    gleich einem vorhandenen Kurspaket (z. B. dem mitgelieferten), bleibt das vorhandene – mitgelieferte bleiben so
    „geprüft“. Ein selbst erstelltes Kurspaket mit derselben Kennung wird nie überschrieben.
    """
    a = kurs.kurspaket
    if a is None:
        raise ValueError(tr("Der Kurs „{name}“ hat kein Kurspaket.", name=kurs.name))
    schon = kurspaket_vorhanden(a)
    if schon is not None:
        return schon
    daten = _aufruf(lambda z: z.kurspaket_holen(kurs.kurs_id, MAX_PAKET))
    return paket_uebernehmen(daten, a.paket_id, a.sha256)


def paket_uebernehmen(daten: bytes, paket_id: str, sha256: str) -> kurspaket.Kurspaket:
    """Kurspaket-Datei aus einem Kurs (Bony-Netz oder Schulung im eigenen Netz) in die Bibliothek übernehmen.

    ``daten`` muss genau ``sha256`` haben; ist der Inhalt gleich einem vorhandenen Paket, bleibt das vorhandene."""
    if not isinstance(daten, bytes) or hashlib.sha256(daten).hexdigest() != sha256:
        raise kurspaket.PaketFehler(tr("Das Kurspaket kam nicht vollständig an (Prüfsumme passt nicht) – bitte später "
                                       "noch einmal versuchen."))
    with tempfile.TemporaryDirectory(prefix="bonys-kurspaket-") as tmp:
        datei = Path(tmp) / "kurs.bonyspaket"
        datei.write_bytes(daten)
        inhalt = Path(tmp) / "inhalt"
        kurspaket.entpacken(datei, inhalt)
        neu = kurspaket.laden(inhalt)
        if neu.id != paket_id:
            raise kurspaket.PaketFehler(tr("Das Kurspaket des Kurses passt nicht zu seinen Angaben."))
        vorhanden = next((p for p in kurspaket.liste() if p.id == neu.id), None)
        if vorhanden is not None and vorhanden.version == neu.version \
                and kurslauf.pruefsummen_text(vorhanden.pfad) == kurslauf.pruefsummen_text(neu.pfad):
            _GLEICH[sha256] = str(vorhanden.pfad)
            return vorhanden
        if vorhanden is not None and vorhanden.herkunft == kurspaket.EIGEN:
            raise kurspaket.PaketFehler(
                tr("Du hast selbst ein Kurspaket mit derselben Kennung („{id}“) erstellt. Damit es nicht "
                   "überschrieben wird, übernimmt Bony's Agents das Kurspaket des Kurses nicht – bitte dein eigenes "
                   "unter „Kurspakete“ duplizieren oder löschen.", id=neu.id))
        return kurspaket.importieren(datei, ersetzen=True, herkunft=kurspaket.KURS, sha256=sha256)


def fortschritt_melden(kurs_id: str, lektion_index: int, geschafft: bool | None) -> None:
    """Teilnehmer: aktuelle Lektion (Index ab 0) und ob ihre Prüfaufgabe geschafft ist – sonst nichts."""
    _aufruf(lambda z: z.fortschritt_melden(kurs_id, lektion_index + 1, geschafft))


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
        return tr("Der Kurs „{name}“ hat begonnen – „Kurse“ → „Kursraum betreten“.", name=kurse[0].name)
    return "Diese Kurse haben begonnen: " + ", ".join(f"„{k.name}“" for k in kurse) + "."
