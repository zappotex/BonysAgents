# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursportal-Annahme: nimmt ``.bonyspaket``-Dateien entgegen und prüft sie mit der lokalen Intake-Schicht.

Läuft im Container hinter Caddy. Pakete werden nur als Daten behandelt (nie entpackte Skripte ausführen).
Anmeldung per Einladungs-Token (nur der SHA-256 liegt auf dem Server), Rate-Limits je Einreicher und global,
Größen- und Speichergrenzen. Moderationsentscheidungen laufen per Kommandozeile im Container
(``liste``, ``zeige``, ``entscheiden``); veröffentlicht wird hier nichts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATEN = Path(os.environ.get("PORTAL_DATEN", "/data"))
MAX_BYTES = int(os.environ.get("PORTAL_MAX_BYTES", str(50 * 1024 * 1024)))
MAX_SPEICHER = int(os.environ.get("PORTAL_MAX_SPEICHER", str(2 * 1024 ** 3)))
LIMIT_STUNDE = int(os.environ.get("PORTAL_LIMIT_STUNDE", "5"))
LIMIT_TAG = int(os.environ.get("PORTAL_LIMIT_TAG", "20"))
LIMIT_GLOBAL_STUNDE = int(os.environ.get("PORTAL_LIMIT_GLOBAL_STUNDE", "60"))
LIMIT_FEHLVERSUCHE_MINUTE = int(os.environ.get("PORTAL_LIMIT_FEHLVERSUCHE", "20"))
KATALOG = Path(os.environ.get("PORTAL_KATALOG", "/katalog"))   # öffentliches Volume, von Caddy nur gelesen
RESERVIERT = Path(os.environ.get("PORTAL_RESERVIERT", "/app/reservierte_ids.json"))
LIMIT_MOD_MINUTE = int(os.environ.get("PORTAL_LIMIT_MOD_MINUTE", "60"))
LIMIT_MOD_FEHLVERSUCHE = int(os.environ.get("PORTAL_LIMIT_MOD_FEHLVERSUCHE", "10"))
MAX_LISTE = 500
LIMIT_ORIGINAL_MINUTE = int(os.environ.get("PORTAL_LIMIT_ORIGINAL_MINUTE", "10"))
MAX_ENTSCHEIDUNG = 16 * 1024          # Body von POST /moderation/entscheiden
ENTSCHEIDUNGEN = ("approved", "rejected", "published", "withdrawn")
_SPERRE = threading.Lock()          # Annahme/Prüfung nacheinander: begrenzt Speicher und CPU
_ZEITEN: dict[str, list[float]] = {}
_FEHLVERSUCHE: list[float] = []
_MOD_FEHLVERSUCHE: list[float] = []      # getrennt von der Annahme: Fehlversuche dort sperren nicht die Moderation


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tokens_datei() -> Path:
    return DATEN / "tokens.json"


def _moderatoren_datei() -> Path:
    return DATEN / "moderatoren.json"


def _tabelle(datei: Path) -> dict[str, str]:
    """Hash -> Name; es liegt nie ein Token im Klartext auf dem Server."""
    try:
        d = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}


def _tokens() -> dict[str, str]:
    return _tabelle(_tokens_datei())


def _tabelle_schreiben(datei: Path, tabelle: dict[str, str]) -> None:
    DATEN.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps(tabelle, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(datei)


def _neu(datei: Path, name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Name fehlt oder ist zu lang.")
    token = secrets.token_urlsafe(32)
    tabelle = _tabelle(datei)
    tabelle[token_hash(token)] = name
    _tabelle_schreiben(datei, tabelle)
    return token


def _entfernen(datei: Path, name: str) -> int:
    tabelle = _tabelle(datei)
    rest = {h: n for h, n in tabelle.items() if n != name}
    if len(rest) != len(tabelle):
        _tabelle_schreiben(datei, rest)
    return len(tabelle) - len(rest)


def token_neu(autor: str) -> str:
    """Neues Einladungs-Token für eine Autorreferenz; gespeichert wird nur der Hash."""
    return _neu(_tokens_datei(), autor)


def moderator_neu(name: str) -> str:
    """Neues Moderator-Token; gilt nur für ``/moderation/*`` und nie für die Annahme."""
    return _neu(_moderatoren_datei(), name)


def _name_fuer(tabelle: dict[str, str], token: str) -> str | None:
    gefunden = None
    h = token_hash(token)
    for bekannt, name in tabelle.items():           # konstante Zeit je Vergleich
        if hmac.compare_digest(bekannt, h):
            gefunden = name
    return gefunden


def autor_fuer(token: str) -> str | None:
    return _name_fuer(_tokens(), token)


def moderator_fuer(token: str) -> str | None:
    return _name_fuer(_tabelle(_moderatoren_datei()), token)


def _frei(schluessel: str, fenster: float, limit: int, jetzt: float) -> bool:
    zeiten = [t for t in _ZEITEN.get(schluessel, []) if jetzt - t < fenster]
    _ZEITEN[schluessel] = zeiten
    return len(zeiten) < limit


def limit_pruefen(autor: str, jetzt: float | None = None) -> str | None:
    """Gibt einen Grund zurück, wenn der Einreicher gerade nicht darf, sonst ``None`` und zählt die Einreichung."""
    jetzt = time.time() if jetzt is None else jetzt
    if not _frei("*", 3600, LIMIT_GLOBAL_STUNDE, jetzt):
        return "Das Portal ist gerade ausgelastet."
    if not _frei("a:" + autor, 3600, LIMIT_STUNDE, jetzt):
        return f"Höchstens {LIMIT_STUNDE} Einreichungen pro Stunde."
    if not _frei("a:" + autor, 86400, LIMIT_TAG, jetzt):
        return f"Höchstens {LIMIT_TAG} Einreichungen pro Tag."
    for schluessel in ("*", "a:" + autor):
        _ZEITEN.setdefault(schluessel, []).append(jetzt)
    return None


def _fehlversuch(liste: list[float], limit: int, jetzt: float | None, zaehlen: bool) -> bool:
    jetzt = time.time() if jetzt is None else jetzt
    liste[:] = [t for t in liste if jetzt - t < 60]
    if zaehlen:
        liste.append(jetzt)
    return len(liste) >= limit


def fehlversuch_gesperrt(jetzt: float | None = None, zaehlen: bool = False) -> bool:
    return _fehlversuch(_FEHLVERSUCHE, LIMIT_FEHLVERSUCHE_MINUTE, jetzt, zaehlen)


def mod_fehlversuch_gesperrt(jetzt: float | None = None, zaehlen: bool = False) -> bool:
    return _fehlversuch(_MOD_FEHLVERSUCHE, LIMIT_MOD_FEHLVERSUCHE, jetzt, zaehlen)


def mod_limit_pruefen(name: str, jetzt: float | None = None) -> bool:
    """True, wenn der Moderator noch darf (und zählt die Anfrage)."""
    jetzt = time.time() if jetzt is None else jetzt
    if not _frei("m:" + name, 60, LIMIT_MOD_MINUTE, jetzt):
        return False
    _ZEITEN.setdefault("m:" + name, []).append(jetzt)
    return True


def _speicher_belegt() -> int:
    ablage = DATEN / "ablage"
    return sum(p.stat().st_size for p in ablage.rglob("*") if p.is_file()) if ablage.is_dir() else 0


def _reservierte_ids() -> list[str]:
    """IDs der mitgelieferten Kurspakete (beim Bundle-Bau erzeugt); sie dürfen nicht eingereicht werden."""
    try:
        return [str(x) for x in json.loads(RESERVIERT.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        return []


def _moderation():
    from bonys_agents import kurspaket_moderation as mod

    return mod, mod.Moderation(DATEN / "ablage", _reservierte_ids())


def _text(wert, maximum: int = 300) -> str:
    from bonys_agents import kurspaket_portal as p

    return p._bereinigen(str(wert if wert is not None else ""), maximum)


def _texte(werte, maximum: int = 300, anzahl: int = 200) -> list[str]:
    return [_text(w, maximum) for w in (werte if isinstance(werte, list) else [])[:anzahl]]


def sicht_liste(ablage, mod) -> list[dict]:
    """Einreichungen für die Moderation: nur feste Felder, neueste Änderung zuerst."""
    zeilen = []
    for sid in ablage.ids():
        try:
            b = ablage.bericht(sid) or {}
            ereignisse = ablage.verlauf(sid)
            zeilen.append({"id": sid, "status": ereignisse[-1].nach, "zeit": ereignisse[-1].zeit,
                           "paket_id": _text(b.get("paket_id"), 60), "name": _text(b.get("name"), 120),
                           "version": _text(b.get("version"), 20)})
        except mod.ModerationsFehler:
            zeilen.append({"id": sid, "status": "defekt", "zeit": "", "paket_id": "", "name": "", "version": ""})
    zeilen.sort(key=lambda z: (z["zeit"], z["id"]), reverse=True)
    return zeilen[:MAX_LISTE]


def sicht_einreichung(ablage, mod, sid: str) -> dict:
    """Bericht und Verlauf einer Einreichung – ohne Dateiname, Hashketten und Fundwerte."""
    try:
        ablage.verlauf_pruefen(sid)
        kette_ok = True
    except mod.ModerationsFehler as exc:
        if str(exc) == "Unbekannte Einreichung.":
            raise
        kette_ok = False
    b = ablage.bericht(sid) or {}
    return {
        "id": sid, "status": ablage.status(sid), "kette_ok": kette_ok,
        "bericht": {
            "paket_id": _text(b.get("paket_id"), 60), "name": _text(b.get("name"), 120),
            "version": _text(b.get("version"), 20), "stufe": _text(b.get("stufe"), 20),
            "beschreibung": _text(b.get("beschreibung"), 2000),
            "dauer_minuten": int(b.get("dauer_minuten") or 0), "groesse": int(b.get("groesse") or 0),
            "sha256": _text(b.get("sha256"), 64), "findings": _texte(b.get("findings")),
            "skripte": _texte(b.get("skripte")), "externe_links": _texte(b.get("externe_links")),
            "fundstellen": _texte(b.get("fundstellen")),
        },
        "verlauf": [{"nr": e.nr, "zeit": e.zeit, "von": e.von, "nach": e.nach,
                     "akteur": _text(e.akteur, 80), "begruendung": _text(e.begruendung, 2000)}
                    for e in ablage.verlauf(sid)],
    }


class Handler(BaseHTTPRequestHandler):
    timeout = 30                              # langsame Verbindungen kappen
    server_version = "Kursportal"
    sys_version = ""

    def log_message(self, format, *args):      # keine IP-Adressen oder Anfragedaten in Container-Logs
        return

    def _json(self, status: int, daten: dict, extra: dict | None = None) -> None:
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _moderator(self) -> str | None:
        """Prüft das Moderator-Token; antwortet selbst, wenn der Zugang nicht gilt. Eigene Zähler und Grenzen."""
        if mod_fehlversuch_gesperrt():
            self._json(429, {"fehler": "zu_viele_fehlversuche"}, {"Retry-After": "60"})
            return None
        kopf = self.headers.get("Authorization", "")
        token = kopf[7:].strip() if kopf.startswith("Bearer ") else ""
        name = moderator_fuer(token) if token else None
        if not name:
            mod_fehlversuch_gesperrt(zaehlen=True)
            if token and autor_fuer(token):          # Einreicher-Token öffnet nie die Moderation
                self._json(403, {"fehler": "kein_moderator"})
            else:
                self._json(401, {"fehler": "nicht_angemeldet"})
            return None
        if not mod_limit_pruefen(name):
            self._json(429, {"fehler": "zu_viele_anfragen"}, {"Retry-After": "60"})
            return None
        return name

    def _moderation_original(self, ablage, mod, name: str, sid: str) -> None:
        """Die Paketdatei zum Ansehen: nur wenn sie noch zur Prüfsumme im Bericht passt. Wird nie ausgeführt."""
        from bonys_agents import kurspaket_portal as portal

        jetzt = time.time()
        if not _frei("d:" + name, 60, LIMIT_ORIGINAL_MINUTE, jetzt):
            return self._json(429, {"fehler": "zu_viele_downloads"}, {"Retry-After": "60"})
        _ZEITEN.setdefault("d:" + name, []).append(jetzt)
        try:
            ablage.status(sid)
        except mod.ModerationsFehler:
            return self._json(404, {"fehler": "nicht_gefunden"})
        datei = DATEN / "ablage" / sid / "original.bonyspaket"
        if not datei.is_file():
            return self._json(404, {"fehler": "nicht_gefunden"})
        if portal._sha256(datei) != (ablage.bericht(sid) or {}).get("sha256"):
            return self._json(409, {"fehler": "original_veraendert"})
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{sid}.bonyspaket"')
        self.send_header("Content-Length", str(datei.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with datei.open("rb") as f:
            while block := f.read(1024 * 1024):
                self.wfile.write(block)

    def _moderation_get(self) -> None:
        name = self._moderator()
        if name is None:
            return
        mod, ablage = _moderation()
        if self.path == "/moderation/liste":
            return self._json(200, {"einreichungen": sicht_liste(ablage, mod)})
        teile = self.path.split("/")
        if len(teile) == 4 and teile[2] == "original" and mod._ID.fullmatch(teile[3]):
            return self._moderation_original(ablage, mod, name, teile[3])
        if len(teile) == 4 and teile[2] == "einreichung":
            try:
                return self._json(200, sicht_einreichung(ablage, mod, teile[3]))
            except mod.ModerationsFehler:
                pass
        self._json(404, {"fehler": "nicht_gefunden"})

    def _moderation_entscheiden(self) -> None:
        """``POST /moderation/entscheiden/<id>``: Akteur ist der Moderator des Tokens, nie ein Feld aus dem Body."""
        self.close_connection = True              # Body wird bei Abweisung nicht gelesen
        name = self._moderator()
        if name is None:
            return
        teile = self.path.split("/")
        mod, ablage = _moderation()
        if len(teile) != 4 or not teile[3]:
            return self._json(404, {"fehler": "nicht_gefunden"})
        try:
            laenge = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"fehler": "laenge_fehlt"})
        if laenge <= 0 or laenge > MAX_ENTSCHEIDUNG:
            return self._json(413, {"fehler": "anfrage_zu_gross", "hoechstens_bytes": MAX_ENTSCHEIDUNG})
        try:
            daten = json.loads(self.rfile.read(laenge).decode("utf-8"))
            nach, begruendung = daten["nach"], daten["begruendung"]
            if not (isinstance(nach, str) and isinstance(begruendung, str)):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"fehler": "ungueltige_anfrage"})
        begruendung = begruendung.strip()
        if nach not in ENTSCHEIDUNGEN or not begruendung or len(begruendung) > mod.MAX_TEXT:
            return self._json(422, {"fehler": "ungueltige_entscheidung", "erlaubt": list(ENTSCHEIDUNGEN)})
        try:
            ablage.status(teile[3])
        except mod.ModerationsFehler:
            return self._json(404, {"fehler": "nicht_gefunden"})
        try:
            ereignis = ablage.entscheiden(teile[3], nach, name, begruendung)
        except mod.ModerationsFehler as exc:
            return self._json(409, {"fehler": "nicht_erlaubt", "meldung": _text(exc, 200)})
        katalog_ok = _katalog_abgleichen(ablage) == 0     # Entscheidung steht; bei Fehler später `katalog` wiederholen
        self._json(200, {"id": teile[3], "status": ereignis.nach, "nr": ereignis.nr, "akteur": name,
                         "katalog_ok": katalog_ok})

    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"ok": True})
        elif self.path.startswith("/moderation/"):
            self._moderation_get()
        else:
            self._json(404, {"fehler": "nicht_gefunden"})

    def do_POST(self):
        if self.path.startswith("/moderation/entscheiden/"):
            return self._moderation_entscheiden()
        if self.path != "/einreichen":
            return self._json(404, {"fehler": "nicht_gefunden"})
        if fehlversuch_gesperrt():
            return self._json(429, {"fehler": "zu_viele_fehlversuche"}, {"Retry-After": "60"})
        kopf = self.headers.get("Authorization", "")
        autor = autor_fuer(kopf[7:].strip()) if kopf.startswith("Bearer ") else None
        if not autor:
            fehlversuch_gesperrt(zaehlen=True)
            return self._json(401, {"fehler": "nicht_angemeldet"})
        try:
            laenge = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"fehler": "laenge_fehlt"})
        if laenge <= 0 or laenge > MAX_BYTES:
            self.close_connection = True
            return self._json(413, {"fehler": "datei_zu_gross", "hoechstens_bytes": MAX_BYTES})
        if _speicher_belegt() + laenge > MAX_SPEICHER:
            self.close_connection = True
            return self._json(507, {"fehler": "portal_voll"})
        grund = limit_pruefen(autor)
        if grund:
            self.close_connection = True
            return self._json(429, {"fehler": "zu_viele_einreichungen", "grund": grund}, {"Retry-After": "3600"})
        with _SPERRE, tempfile.TemporaryDirectory(prefix="annahme-") as tmp:
            datei = Path(tmp) / "eingang.bonyspaket"
            rest = laenge
            with datei.open("wb") as f:
                while rest > 0:
                    block = self.rfile.read(min(1024 * 1024, rest))
                    if not block:
                        return self._json(400, {"fehler": "unvollstaendig"})
                    f.write(block)
                    rest -= len(block)
            mod, ablage = _moderation()
            sid = ablage.einreichen(datei, autor)
            bericht = ablage.bericht(sid) or {}
            self._json(200, {"submission_id": sid, "status": ablage.status(sid),
                             "befunde": bericht.get("findings", [])})


def _katalog_abgleichen(ablage) -> int:
    """Öffentlichen Katalog nach einer Entscheidung neu schreiben (nur freigegebene Pakete, neueste Version)."""
    from bonys_agents import kurspaket_katalog

    try:
        index = kurspaket_katalog.katalog_schreiben(ablage, KATALOG)
    except OSError as exc:
        print(f"Warnung: Katalog konnte nicht geschrieben werden: {exc.strerror or exc}", file=sys.stderr)
        return 1
    print(f"Katalog: {len(index['pakete'])} Paket(e) öffentlich.")
    return 0


def _cli(argv: list[str]) -> int:
    befehl = argv[0] if argv else ""
    if befehl == "token-neu" and len(argv) == 2:
        print(token_neu(argv[1]))
        return 0
    if befehl == "moderator-neu" and len(argv) == 2:
        print(moderator_neu(argv[1]))
        return 0
    if befehl in ("moderator-liste", "token-liste") and len(argv) == 1:
        datei = _moderatoren_datei() if befehl == "moderator-liste" else _tokens_datei()
        for name in sorted(set(_tabelle(datei).values())):
            print(name)
        return 0
    if befehl in ("moderator-entfernen", "token-entfernen") and len(argv) == 2:
        datei = _moderatoren_datei() if befehl == "moderator-entfernen" else _tokens_datei()
        anzahl = _entfernen(datei, argv[1])
        print(f"{anzahl} Zugang/Zugänge entfernt." if anzahl else "Keinen Zugang mit diesem Namen gefunden.")
        return 0 if anzahl else 1
    if befehl == "liste" and len(argv) == 1:
        mod, ablage = _moderation()
        for sid in ablage.ids():
            b = ablage.bericht(sid) or {}
            print(f"{sid}  {ablage.status(sid):13}  {b.get('paket_id', '-')}  {b.get('version', '-')}")
        return 0
    if befehl == "zeige" and len(argv) == 2:
        mod, ablage = _moderation()
        print(json.dumps(ablage.bericht(argv[1]), ensure_ascii=False, indent=1))
        for e in ablage.verlauf(argv[1]):
            print(f"{e.nr}. {e.zeit} {e.nach} {e.akteur}: {e.begruendung}")
        return 0
    if befehl == "entscheiden" and len(argv) == 5:
        mod, ablage = _moderation()
        try:
            ablage.entscheiden(argv[1], argv[2], argv[3], argv[4])
        except mod.ModerationsFehler as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 1
        print(f"{argv[1]} -> {argv[2]}")
        _katalog_abgleichen(ablage)       # Entscheidung steht fest; bei Fehler Warnung, später `katalog` wiederholen
        return 0
    if befehl == "katalog" and len(argv) == 1:
        return _katalog_abgleichen(_moderation()[1])
    if befehl == "" or befehl == "server":
        DATEN.mkdir(parents=True, exist_ok=True)
        ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
        return 0
    print("Aufruf: token-neu NAME | token-liste | token-entfernen NAME | moderator-neu NAME | moderator-liste | "
          "moderator-entfernen NAME | liste | zeige ID | entscheiden ID NACH AKTEUR BEGRUENDUNG | katalog | server",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
