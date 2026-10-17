# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony-Netz in Bony's Agents: Server, Instanz und Zustand (Fenster: ``gui/netz_dialog.py``).

Mit der Zentrale spricht der gemeinsame Baustein ``bony_netz`` (derselbe wie in Bony's VPN, unverändert übernommen).
Die Anmeldung liegt in seiner Datei ``konto.json``, die sich beide Apps teilen – deshalb wird sie vor jeder Änderung
frisch geladen, damit eine Änderung aus Bony's VPN nicht überschrieben wird.

Alle Funktionen, die die Zentrale fragen, blockieren bis zu 15 Sekunden: nur im Hintergrund aufrufen.
Ist der Schalter „Bony-Netz verwenden“ aus (Standard), nimmt die App keinen Kontakt zur Zentrale auf.
Das Instanz-Token erscheint nirgends – weder in Texten noch in Fehlermeldungen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from bony_netz import Konto, NetzFehler, Zentrale, ZentraleFehler
from bony_netz.konto import server_normalisieren

AKTIV = "aktiv"   # Schlüssel in konto.extra

KEINE_VERBINDUNG = "Keine Verbindung zum Server"
ANMELDUNG_UNGUELTIG = "Anmeldung ungültig, bitte Instanz neu anlegen"


class KeinBonyNetz(Exception):
    """Unter der Adresse antwortet etwas, aber kein Bony-Netz-Server (z. B. eine normale Webseite)."""


@dataclass
class Zustand:
    text: str                       # Zustandszeile
    konto: Konto                    # frisch geladen (evtl. mit aktualisiertem Kursleiter-Status oder abgemeldet)
    info: dict = field(default_factory=dict)   # Antwort von /info, leer ohne Verbindung
    verbunden: bool = False
    detail: str = ""                # genauere Fehlermeldung, falls nicht verbunden


def kurz_id(instanz_id: str) -> str:
    return instanz_id[:8]


def aktiv(konto: Konto) -> bool:
    return bool(konto.extra.get(AKTIV))


def aendern(fn: Callable[[Konto], object]) -> Konto:
    """Konto frisch laden, ändern, speichern (OSError, wenn das nicht geht)."""
    konto = Konto.laden()
    fn(konto)
    konto.speichern()
    return konto


def aktiv_setzen(an: bool) -> Konto:
    return aendern(lambda k: k.extra.__setitem__(AKTIV, bool(an)))


def fehlertext(e: BaseException) -> str:
    if isinstance(e, ZentraleFehler):
        return e.meldung
    if isinstance(e, OSError):
        return f"Die Anmeldung ließ sich nicht speichern ({e.strerror or e})."
    return str(e)


def _kein_server(server: str, grund: str = "") -> KeinBonyNetz:
    return KeinBonyNetz(f"Unter {server} antwortet kein Bony-Netz-Server{f' ({grund})' if grund else ''}. "
                        "Bitte die Adresse prüfen.")


def _fragen(server: str, fn: Callable[[], object]):
    """Aufruf der Zentrale. Antwortet dort etwas anderes (Webseite statt JSON, 404), gibt es KeinBonyNetz –
    der Baustein meldet eine Antwort, die kein JSON ist, nicht selbst als Fehler."""
    try:
        return fn()
    except ZentraleFehler as e:
        if e.status in (404, 405):
            raise _kein_server(server, f"Fehler {e.status}") from None
        raise
    except (ValueError, KeyError, TypeError):
        raise _kein_server(server, "unerwartete Antwort") from None


def server_info(server: str) -> dict:
    """``/info`` des Servers – mit Prüfung, dass es wirklich eine Zentrale ist."""
    server = server_normalisieren(server)
    info = _fragen(server, lambda: Zentrale(server).info())
    if not isinstance(info, dict) or not isinstance(info.get("server_name"), str):
        raise _kein_server(server, "unerwartete Antwort")
    return info


def zustand() -> Zustand:
    """Server fragen und – falls angemeldet – die Instanz. Wirft nicht: Fehler stehen im Ergebnis.

    Ist die Anmeldung ungültig (Instanz auf dem Server gelöscht), wird sie hier verworfen.
    """
    konto = Konto.laden()
    try:
        info = server_info(konto.server)
        if konto.angemeldet:
            instanz = _fragen(konto.server, lambda: Zentrale(konto.server, konto.token).instanz())
            if not isinstance(instanz, dict):
                raise _kein_server(konto.server, "unerwartete Antwort")
            kursleiter = bool(instanz.get("ist_kursleiter"))
            if kursleiter != konto.ist_kursleiter:
                alt = konto.instanz_id

                def merken(k: Konto) -> None:
                    if k.instanz_id == alt:
                        k.ist_kursleiter = kursleiter

                try:
                    konto = aendern(merken)
                except OSError:
                    konto.ist_kursleiter = kursleiter
        return Zustand(f"Verbunden mit {info['server_name']}", konto, info, verbunden=True)
    except NetzFehler as e:
        return Zustand(KEINE_VERBINDUNG, konto, detail=str(e))
    except ZentraleFehler as e:
        if not e.anmeldung_ungueltig:
            return Zustand(e.meldung, konto, detail=e.meldung)
        alt = konto.instanz_id
        try:   # nur diese Instanz verwerfen – Bony's VPN könnte inzwischen eine neue angelegt haben
            konto = aendern(lambda k: k.abmelden() if k.instanz_id == alt else None)
        except OSError:
            pass
        return Zustand(ANMELDUNG_UNGUELTIG, konto, detail=e.meldung)
    except KeinBonyNetz as e:
        return Zustand(str(e), konto, detail=str(e))


def server_wechseln(adresse: str) -> Zustand:
    """Neuen Server prüfen und erst dann übernehmen (eine Anmeldung beim alten wird dabei verworfen).

    Wirft NetzFehler, ZentraleFehler oder KeinBonyNetz, wenn der neue Server nicht taugt – der alte bleibt dann.
    """
    adresse = server_normalisieren(adresse)
    server_info(adresse)
    aendern(lambda k: k.server_wechseln(adresse))
    return zustand()


def instanz_anlegen(server: str) -> Konto:
    """Neue Instanz beim Server anlegen und sofort speichern.

    Hat Bony's VPN inzwischen schon eine angelegt, wird keine zweite angelegt.
    """
    konto = Konto.laden()
    if konto.server != server_normalisieren(server):
        raise RuntimeError("Der Server wurde inzwischen geändert – bitte das Fenster neu öffnen.")
    if konto.angemeldet:
        return konto
    registrierung = _fragen(konto.server, lambda: Zentrale(konto.server).instanz_registrieren())
    konto.uebernehmen(registrierung)
    konto.speichern()
    return konto


def instanz_loeschen() -> Konto:
    """Instanz auf dem Server löschen (mit allen Agenten-PCs im Netz, Kursen und Teilnahmen), dann abmelden.

    Gibt es sie auf dem Server schon nicht mehr, wird nur abgemeldet.
    """
    konto = Konto.laden()
    if konto.angemeldet:
        try:
            _fragen(konto.server, lambda: Zentrale(konto.server, konto.token).instanz_loeschen())
        except ZentraleFehler as e:
            if not e.anmeldung_ungueltig:
                raise
    alt = konto.instanz_id
    return aendern(lambda k: k.abmelden() if k.instanz_id == alt else None)
