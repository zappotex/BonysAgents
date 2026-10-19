# SPDX-License-Identifier: GPL-3.0-or-later
"""Erfundene Zentrale für die Bildschirmfotos – nur im Speicher, ohne Server und ohne Netz.

``einsetzen()`` ersetzt ``bony_netz.Zentrale._anfrage``: Jeder Aufruf der App an die Zentrale landet hier und
bekommt Antworten wie von einem echten Bony-Netz-Server (API.md), nur mit Beispieldaten. Alle Adressen im Bony-Netz
stammen aus 100.64.0.0/10 (wie bei Headscale), Namen und Codes sind erfunden.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.parse
from pathlib import Path

from bony_netz import Zentrale, ZentraleFehler

SERVER = "https://zentrale.example"
KURSRAUM_URL = "wss://kursraum.example"
TOKEN = "vorfuehrung"                  # Anmeldung der Beispiel-Instanz (steht nie in einem Bild)
KURS_ID = "kurs-hermes"
KURSCODE = "K7QX-M3PA"
KURSLEITER_CODE = "BEISPIEL-CODE"
KURSLEITUNG = "Eva"                    # erfundene Kursleiterin

JETZT = int(time.time())
TAG = 86400
PAKET = Path(__file__).resolve().parents[3] / "kurspakete" / "einfuehrung-hermes-agent"


def _kurspaket() -> tuple[bytes, dict]:
    """Das mitgelieferte Kurspaket „Einführung in Hermes Agent“, gepackt wie für einen Kurs."""
    from bonys_agents import kurse, kurspaket

    paket = kurspaket.laden(PAKET)
    daten = kurse.paket_packen(paket)
    return daten, {"paket_id": paket.id, "name": paket.name, "version": paket.version,
                   "lektionen": len(paket.lektionen), "sha256": hashlib.sha256(daten).hexdigest(),
                   "groesse": len(daten), "hochgeladen": JETZT - 2 * TAG}


def _jwt(daten: dict) -> str:
    """Unsigniertes Beispiel-Token – die App liest daraus nur „exp“."""
    teil = base64.urlsafe_b64encode(json.dumps(daten).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{teil}.vorfuehrung"


class Beispiel:
    """Zustand der erfundenen Zentrale – je nach Bild als Teilnehmerin (Anna) oder Kursleiterin (Eva)."""

    def __init__(self, rolle: str = "teilnehmer") -> None:
        self.rolle = rolle
        self.kursleiter = rolle == "kursleiter"
        self.instanz_id = "inst-eva-0001" if self.kursleiter else "inst-anna-0001"
        if self.kursleiter:
            self.geraete = [
                {"geraet_id": "g1", "name": "agent-kursleitung", "ip": "100.64.0.10", "online": True,
                 "zuletzt_gesehen": JETZT},
            ]
        else:
            self.geraete = [
                {"geraet_id": "g11", "name": "agent-kurs", "ip": "100.64.0.21", "online": True,
                 "zuletzt_gesehen": JETZT},
                {"geraet_id": "g12", "name": "agent-buero", "ip": "100.64.0.22", "online": False,
                 "zuletzt_gesehen": JETZT - 3 * 3600},
            ]
        teilnehmer = [
            ("inst-anna-0001", "Anna", "agent-kurs", "100.64.0.21", 2 * TAG, (4, True)),
            ("inst-ben-0002", "Ben", "ben-laptop-pc", "100.64.0.31", TAG + 3600, (3, False)),
            ("inst-clara-0003", "Clara", "agent-pc-clara", "100.64.0.41", 5 * 3600, (5, None)),
        ]
        self.paket_daten, paket = _kurspaket()
        self.kurse = {
            KURS_ID: {
                "kurs_id": KURS_ID, "name": "Einführung in Hermes Agent", "kursleiter_name": KURSLEITUNG,
                "status": "laeuft", "raum": KURS_ID, "code": KURSCODE,
                "code_gueltig_bis": JETZT + 12 * TAG, "erstellt": JETZT - 2 * TAG, "kurspaket": paket,
                "teilnehmer": [{"instanz_id": i, "anzeigename": n, "geraet_name": g, "geraet_ip": ip,
                                "beigetreten": JETZT - vor,
                                "fortschritt": {"lektion": f[0], "geschafft": f[1], "aktualisiert": JETZT - 60}}
                               for i, n, g, ip, vor, f in teilnehmer],
            },
            "kurs-probe": {
                "kurs_id": "kurs-probe", "name": "Probelauf Technik", "kursleiter_name": KURSLEITUNG,
                "status": "beendet", "raum": "kurs-probe", "code": "P4RT-9QZE",
                "code_gueltig_bis": JETZT - TAG, "erstellt": JETZT - 9 * TAG, "kurspaket": None,
                "teilnehmer": [],
            },
        }
        self.neuer_kurs_status = "offen"

    # ---------------------------------------------------------------- Antworten wie die Zentrale
    def antwort(self, methode: str, pfad: str, daten: dict | None, parameter: dict | None):
        daten = daten or {}
        teile = urllib.parse.urlsplit(pfad).path.split("/")
        if (methode, pfad) == ("GET", "/api/v1/info"):
            return {"server_name": "Beispiel-Zentrale", "version": "1.0.0", "login_server": "https://netz.example",
                    "kursraum_url": KURSRAUM_URL}
        if (methode, pfad) == ("POST", "/api/v1/instanzen"):
            return {"instanz_id": self.instanz_id, "token": TOKEN, "login_server": "https://netz.example"}
        if (methode, pfad) == ("GET", "/api/v1/instanz"):
            return {"instanz_id": self.instanz_id, "ist_kursleiter": self.kursleiter, "erstellt": JETZT - 30 * TAG}
        if (methode, pfad) == ("DELETE", "/api/v1/instanz"):
            return None
        if (methode, pfad) == ("POST", "/api/v1/instanz/kursleiter"):
            if daten.get("code") != KURSLEITER_CODE:
                raise ZentraleFehler(400, "Der Kursleiter-Code ist ungültig.")
            self.kursleiter = True
            return None
        if (methode, pfad) == ("GET", "/api/v1/geraete"):
            return self.geraete
        if (methode, pfad) == ("POST", "/api/v1/geraete/schluessel"):
            return {"schluessel": "beispiel-schluessel", "login_server": "https://netz.example", "gueltig_minuten": 60}
        if methode == "DELETE" and pfad.startswith("/api/v1/geraete/"):
            return None
        if (methode, pfad) == ("POST", "/api/v1/kurse/beitreten"):
            code = "".join(z for z in str(daten.get("code", "")).upper() if z.isalnum())
            k = self.kurse[KURS_ID]
            if code != k["code"].replace("-", ""):
                raise ZentraleFehler(404, "Der Kurscode ist ungültig oder abgelaufen.")
            return self._oeffentlich(k, mit_code=False)
        if (methode, pfad) == ("GET", "/api/v1/kurse/teilnahmen"):
            if self.kursleiter:
                return []
            k = self.kurse[KURS_ID]
            return [{**self._oeffentlich(k, mit_code=False), "teilnehmer": [], "mein_geraet_id": "g11"}]
        if methode == "DELETE" and len(teile) == 6 and teile[5] == "teilnahme":
            return None
        if len(teile) == 6 and teile[5] in ("kurspaket", "fortschritt") and methode in ("GET", "POST"):
            k = self.kurse.get(teile[4])
            if k is None or k.get("kurspaket") is None:
                raise ZentraleFehler(404, "Dieser Kurs hat kein Kurspaket.")
            return self.paket_daten if methode == "GET" else None
        if methode == "POST" and len(teile) == 6 and teile[5] == "eintritt":
            k = self.kurse.get(teile[4])
            if k is None or k["status"] != "laeuft":
                raise ZentraleFehler(409, "Der Kurs läuft nicht.")
            rolle = "kursleiter" if self.kursleiter else "teilnehmer"
            name = KURSLEITUNG if self.kursleiter else "Anna"
            karte = _jwt({"exp": JETZT + 6 * 3600, "name": name, "sub": self.instanz_id})
            return {"kursraum_url": f"{KURSRAUM_URL}/?vorfuehrung={rolle}", "raum": k["raum"],
                    "eintrittskarte": karte, "rolle": rolle}
        if (methode, pfad) == ("POST", "/api/v1/kurse"):
            n = len(self.kurse) + 1
            kurs_id = f"kurs-neu-{n}"
            self.kurse[kurs_id] = {
                "kurs_id": kurs_id, "name": daten["name"], "kursleiter_name": daten["kursleiter_name"],
                "status": self.neuer_kurs_status, "raum": kurs_id, "code": "R2DW-8KTN",
                "code_gueltig_bis": JETZT + TAG * int(daten.get("code_gueltig_tage", 14)), "erstellt": JETZT,
                "kurspaket": None, "teilnehmer": []}
            return self._oeffentlich(self.kurse[kurs_id])
        if (methode, pfad) == ("GET", "/api/v1/kurse/geleitet"):
            alle = (parameter or {}).get("alle") == "true"
            return [self._oeffentlich(k) for k in self.kurse.values() if alle or k["status"] != "beendet"]
        k = self.kurse.get(teile[4]) if len(teile) > 4 else None
        if k is not None and methode == "POST" and teile[5:] == ["status"]:
            k["status"] = daten["status"]
            return self._oeffentlich(k)
        if k is not None and teile[5:] == ["kurspaket"] and methode == "PUT":
            k["kurspaket"] = {**(parameter or {}), "lektionen": int((parameter or {}).get("lektionen", 0)),
                              "sha256": "0" * 64, "groesse": 1, "hochgeladen": JETZT}
            return self._oeffentlich(k)
        if k is not None and teile[5:] == ["kurspaket"] and methode == "DELETE":
            k["kurspaket"] = None
            return None
        if k is not None and methode == "DELETE" and len(teile) == 7 and teile[5] == "teilnehmer":
            k["teilnehmer"] = [t for t in k["teilnehmer"] if t["instanz_id"] != teile[6]]
            return None
        raise ZentraleFehler(404, "Nicht gefunden")

    @staticmethod
    def _oeffentlich(k: dict, mit_code: bool = True) -> dict:
        d = json.loads(json.dumps(k))
        if not mit_code:
            d.pop("code", None)
        return d


_aktiv: Beispiel | None = None


def einsetzen(beispiel: Beispiel) -> None:
    """Alle Aufrufe der App an eine Zentrale gehen ab jetzt an ``beispiel``."""
    global _aktiv
    _aktiv = beispiel

    def anfrage(self, methode, pfad, daten=None, anmeldung=True, parameter=None, **_roh):
        if self.server != SERVER:
            from bony_netz import NetzFehler

            raise NetzFehler(f"Der Server {self.server} ist nicht erreichbar (Vorführmodus).")
        return _aktiv.antwort(methode, pfad, daten, parameter)

    Zentrale._anfrage = anfrage
