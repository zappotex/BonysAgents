"""Client für die Zentrale eines Bony-Netz-Servers (siehe API.md im Server-Projekt).

Alle Methoden blockieren und dauern bei langsamer Verbindung einige Sekunden.
In einer Qt-Oberfläche deshalb nicht im Hauptthread aufrufen, sondern z. B. in
einem QThreadPool/QRunnable.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .fehler import NetzFehler, ZentraleFehler
from .konto import server_normalisieren


def kurscode_formatieren(code: str) -> str:
    """'k7qxm3pa' oder 'K7QX M3PA' -> 'K7QX-M3PA'."""
    rein = "".join(z for z in code.upper() if z.isalnum())
    return f"{rein[:4]}-{rein[4:]}" if len(rein) == 8 else rein


class Zentrale:
    def __init__(self, server: str, token: str = "", zeitlimit: float = 15) -> None:
        self.server = server_normalisieren(server)
        self.token = token
        self.zeitlimit = zeitlimit
        self._ssl = ssl.create_default_context()

    # -----------------------------------------------------------------------
    # Grundlage
    # -----------------------------------------------------------------------

    def _anfrage(self, methode: str, pfad: str, daten: dict | None = None,
                 anmeldung: bool = True, parameter: dict | None = None):
        url = self.server + pfad
        if parameter:
            url += "?" + urllib.parse.urlencode(parameter)
        koepfe = {"Accept": "application/json", "User-Agent": "bony-netz/0.1"}
        rumpf = None
        if daten is not None:
            rumpf = json.dumps(daten).encode()
            koepfe["Content-Type"] = "application/json"
        if anmeldung:
            if not self.token:
                raise ZentraleFehler(401, "Diese Instanz ist noch nicht angemeldet.")
            koepfe["Authorization"] = f"Bearer {self.token}"

        anfrage = urllib.request.Request(url, data=rumpf, headers=koepfe, method=methode)
        kontext = self._ssl if url.startswith("https://") else None
        try:
            with urllib.request.urlopen(anfrage, timeout=self.zeitlimit, context=kontext) as antwort:
                inhalt = antwort.read()
                return json.loads(inhalt) if inhalt else None
        except urllib.error.HTTPError as e:
            raise ZentraleFehler(e.code, self._fehlertext(e)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            grund = getattr(e, "reason", e)
            raise NetzFehler(f"Der Server {self.server} ist nicht erreichbar ({grund}).") from None

    @staticmethod
    def _fehlertext(e: urllib.error.HTTPError) -> str:
        try:
            detail = json.loads(e.read()).get("detail")
        except Exception:
            detail = None
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):        # Eingabe ungültig (Prüfung der Felder)
            return "Die Eingabe ist ungültig: " + "; ".join(
                str(d.get("msg", d)) for d in detail if isinstance(d, dict))
        return f"Der Server hat mit Fehler {e.code} geantwortet."

    # -----------------------------------------------------------------------
    # Allgemein und Instanz
    # -----------------------------------------------------------------------

    def info(self) -> dict:
        """Prüft den Server. Liefert server_name, version, login_server, kursraum_url, grenzen."""
        return self._anfrage("GET", "/api/v1/info", anmeldung=False)

    def instanz_registrieren(self) -> dict:
        """Legt eine neue Instanz an. Antwort an Konto.uebernehmen() geben und speichern!"""
        antwort = self._anfrage("POST", "/api/v1/instanzen", anmeldung=False)
        self.token = antwort["token"]
        return antwort

    def instanz(self) -> dict:
        return self._anfrage("GET", "/api/v1/instanz")

    def instanz_loeschen(self) -> None:
        self._anfrage("DELETE", "/api/v1/instanz")

    def kursleiter_freischalten(self, code: str) -> None:
        self._anfrage("POST", "/api/v1/instanz/kursleiter", {"code": code})

    # -----------------------------------------------------------------------
    # Geräte
    # -----------------------------------------------------------------------

    def geraete(self) -> list[dict]:
        """[{geraet_id, name, ip, online, zuletzt_gesehen}]"""
        return self._anfrage("GET", "/api/v1/geraete")

    def geraeteschluessel(self) -> dict:
        """{schluessel, login_server, gueltig_minuten} – einmal nutzbar."""
        return self._anfrage("POST", "/api/v1/geraete/schluessel")

    def geraet_entfernen(self, geraet_id: str) -> None:
        self._anfrage("DELETE", f"/api/v1/geraete/{geraet_id}")

    # -----------------------------------------------------------------------
    # Kurse – Kursleiter
    # -----------------------------------------------------------------------

    def kurs_anlegen(self, name: str, kursleiter_name: str, code_gueltig_tage: int = 14) -> dict:
        return self._anfrage("POST", "/api/v1/kurse", {
            "name": name, "kursleiter_name": kursleiter_name, "code_gueltig_tage": code_gueltig_tage,
        })

    def geleitete_kurse(self, auch_beendete: bool = False) -> list[dict]:
        return self._anfrage("GET", "/api/v1/kurse/geleitet",
                             parameter={"alle": "true" if auch_beendete else "false"})

    def kurs_starten(self, kurs_id: str) -> dict:
        return self._status(kurs_id, "laeuft")

    def kurs_pausieren(self, kurs_id: str) -> dict:
        return self._status(kurs_id, "pausiert")

    def kurs_beenden(self, kurs_id: str) -> dict:
        return self._status(kurs_id, "beendet")

    def _status(self, kurs_id: str, status: str) -> dict:
        return self._anfrage("POST", f"/api/v1/kurse/{kurs_id}/status", {"status": status})

    def teilnehmer_entfernen(self, kurs_id: str, instanz_id: str) -> None:
        self._anfrage("DELETE", f"/api/v1/kurse/{kurs_id}/teilnehmer/{instanz_id}")

    # -----------------------------------------------------------------------
    # Kurse – Teilnehmer
    # -----------------------------------------------------------------------

    def kurs_beitreten(self, code: str, geraet_id: str, anzeigename: str) -> dict:
        return self._anfrage("POST", "/api/v1/kurse/beitreten", {
            "code": code, "geraet_id": str(geraet_id), "anzeigename": anzeigename,
        })

    def teilnahmen(self) -> list[dict]:
        return self._anfrage("GET", "/api/v1/kurse/teilnahmen")

    def kurs_verlassen(self, kurs_id: str) -> None:
        self._anfrage("DELETE", f"/api/v1/kurse/{kurs_id}/teilnahme")

    # -----------------------------------------------------------------------
    # Kursraum
    # -----------------------------------------------------------------------

    def eintrittskarte(self, kurs_id: str) -> dict:
        """{kursraum_url, raum, eintrittskarte, rolle} – nur wenn der Kurs läuft."""
        return self._anfrage("POST", f"/api/v1/kurse/{kurs_id}/eintritt")
