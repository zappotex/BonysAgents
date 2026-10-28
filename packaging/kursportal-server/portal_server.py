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
_SPERRE = threading.Lock()          # Annahme/Prüfung nacheinander: begrenzt Speicher und CPU
_ZEITEN: dict[str, list[float]] = {}
_FEHLVERSUCHE: list[float] = []


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tokens_datei() -> Path:
    return DATEN / "tokens.json"


def _tokens() -> dict[str, str]:
    try:
        return json.loads(_tokens_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def token_neu(autor: str) -> str:
    """Neues Einladungs-Token für eine Autorreferenz; gespeichert wird nur der Hash."""
    autor = autor.strip()
    if not autor or len(autor) > 80:
        raise ValueError("Autorreferenz fehlt oder ist zu lang.")
    token = secrets.token_urlsafe(32)
    tokens = _tokens()
    tokens[token_hash(token)] = autor
    DATEN.mkdir(parents=True, exist_ok=True)
    tmp = _tokens_datei().with_suffix(".tmp")
    tmp.write_text(json.dumps(tokens, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(_tokens_datei())
    return token


def autor_fuer(token: str) -> str | None:
    gefunden = None
    h = token_hash(token)
    for bekannt, autor in _tokens().items():       # konstante Zeit je Vergleich
        if hmac.compare_digest(bekannt, h):
            gefunden = autor
    return gefunden


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


def fehlversuch_gesperrt(jetzt: float | None = None, zaehlen: bool = False) -> bool:
    jetzt = time.time() if jetzt is None else jetzt
    _FEHLVERSUCHE[:] = [t for t in _FEHLVERSUCHE if jetzt - t < 60]
    if zaehlen:
        _FEHLVERSUCHE.append(jetzt)
    return len(_FEHLVERSUCHE) >= LIMIT_FEHLVERSUCHE_MINUTE


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

    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"fehler": "nicht_gefunden"})

    def do_POST(self):
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
    print("Aufruf: token-neu NAME | liste | zeige ID | entscheiden ID NACH AKTEUR BEGRUENDUNG | katalog | server",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
