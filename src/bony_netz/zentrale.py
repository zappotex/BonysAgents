# SPDX-License-Identifier: GPL-3.0-or-later
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
                 anmeldung: bool = True, parameter: dict | None = None, *,
                 roh_senden: bytes | None = None, roh_lesen: int = 0, zeitlimit: float | None = None):
        """JSON hin und zurück. ``roh_senden``: Bytes statt JSON schicken; ``roh_lesen`` > 0: Antwort als Bytes
        (höchstens so viele) statt JSON."""
        url = self.server + pfad
        if parameter:
            url += "?" + urllib.parse.urlencode(parameter)
        koepfe = {"Accept": "application/octet-stream" if roh_lesen else "application/json",
                  "User-Agent": "bony-netz/0.2"}
        rumpf = None
        if daten is not None:
            rumpf = json.dumps(daten).encode()
            koepfe["Content-Type"] = "application/json"
        elif roh_senden is not None:
            rumpf = roh_senden
            koepfe["Content-Type"] = "application/octet-stream"
        if anmeldung:
            if not self.token:
                raise ZentraleFehler(401, "Diese Instanz ist noch nicht angemeldet.")
            koepfe["Authorization"] = f"Bearer {self.token}"

        anfrage = urllib.request.Request(url, data=rumpf, headers=koepfe, method=methode)
        kontext = self._ssl if url.startswith("https://") else None
        try:
            with urllib.request.urlopen(anfrage, timeout=zeitlimit or self.zeitlimit, context=kontext) as antwort:
                if roh_lesen:
                    inhalt = antwort.read(roh_lesen + 1)
                    if len(inhalt) > roh_lesen:
                        raise NetzFehler(f"Die Antwort von {self.server} ist zu groß.")
                    return inhalt
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

    def kurspaket_hochladen(self, kurs_id: str, datei: bytes, paket_id: str, name: str, version: str,
                            lektionen: int = 0) -> dict:
        """Kurspaket (.bonyspaket) zum Kurs hochladen – ersetzt ein vorhandenes. Liefert den Kurs (mit „kurspaket“:
        paket_id, name, version, lektionen, sha256, groesse, hochgeladen)."""
        return self._anfrage("PUT", f"/api/v1/kurse/{kurs_id}/kurspaket", roh_senden=datei,
                             parameter={"paket_id": paket_id, "name": name, "version": version,
                                        "lektionen": int(lektionen)},
                             zeitlimit=max(self.zeitlimit, 120))

    def kurspaket_entfernen(self, kurs_id: str) -> None:
        self._anfrage("DELETE", f"/api/v1/kurse/{kurs_id}/kurspaket")

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

    def kurspaket_holen(self, kurs_id: str, max_bytes: int = 25 * 1024 * 1024) -> bytes:
        """Die .bonyspaket-Datei des Kurses (Teilnehmer und Kursleiter). Prüfsumme selbst vergleichen!"""
        return self._anfrage("GET", f"/api/v1/kurse/{kurs_id}/kurspaket", roh_lesen=max_bytes,
                             zeitlimit=max(self.zeitlimit, 120))

    def fortschritt_melden(self, kurs_id: str, lektion: int, geschafft: bool | None = None) -> None:
        """Nur Lektion (ab 1) und „geschafft / noch nicht“ (None: keine Prüfaufgabe bzw. nicht geprüft)."""
        self._anfrage("POST", f"/api/v1/kurse/{kurs_id}/fortschritt",
                      {"lektion": int(lektion), "geschafft": geschafft})

    # -----------------------------------------------------------------------
    # Kursraum
    # -----------------------------------------------------------------------

    def eintrittskarte(self, kurs_id: str) -> dict:
        """{kursraum_url, raum, eintrittskarte, rolle} – nur wenn der Kurs läuft."""
        return self._anfrage("POST", f"/api/v1/kurse/{kurs_id}/eintritt")
