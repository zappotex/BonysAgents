# SPDX-License-Identifier: GPL-3.0-or-later
"""Client für die Online-Moderation des Kursportals (``/moderation/*`` auf dem Annahme-Server).

Bietet dieselben Lesefunktionen wie ``kurspaket_moderation.Moderation`` (``ids``, ``status``, ``bericht``, ``verlauf``,
``entscheiden``), damit der Moderationsdialog beide Quellen gleich behandelt. Der Akteur einer Entscheidung ergibt sich
auf dem Server aus dem Moderator-Token; der Client schickt keinen. Es werden nur Daten angezeigt – nichts aus einem
Paket wird ausgeführt oder geöffnet. Das Token liegt in einer eigenen Datei mit Rechten 600, nie in den Einstellungen.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request

from bonys_agents import kurspaket, kurspaket_moderation as mod, kurspaket_portal as portal, storage
from bonys_agents.i18n import tr

PORTAL_URL = "https://kurse.bony23.de"
PORTAL_ENV = "BONYS_AGENTS_PORTAL_URL"          # andere Adresse (Tests)
ZUGANG_DATEI = "kursportal-moderator.json"
TIMEOUT = 10
MAX_ANTWORT = 2 * 1024 * 1024
MAX_LISTE = 500
MAX_ORIGINAL = 50 * 1024 * 1024         # wie die Annahmegrenze des Servers
MAX_ANSICHT_DATEI = 200 * 1024          # je Datei zum Anzeigen
MAX_ANSICHT_GESAMT = 4 * 1024 * 1024
TEXT_ENDUNGEN = {".md", ".txt", ".json"}
BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_STEUER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")


class OnlineFehler(mod.ModerationsFehler):
    """Fehler der Online-Moderation mit einer Meldung, die der Dialog direkt zeigen darf (``code``: HTTP-Status)."""

    def __init__(self, meldung: str, code: int | None = None):
        super().__init__(meldung)
        self.code = code


@dataclass
class Zugang:
    url: str
    token: str


def portal_url() -> str:
    return (os.environ.get(PORTAL_ENV) or PORTAL_URL).rstrip("/")


def _zugang_datei():
    return storage.data_dir() / ZUGANG_DATEI


def zugang_laden() -> Zugang | None:
    try:
        d = json.loads(_zugang_datei().read_text(encoding="utf-8"))
        url, token = d["url"], d["token"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return Zugang(url, token) if isinstance(url, str) and isinstance(token, str) and token else None


def zugang_speichern(token: str, url: str | None = None) -> None:
    """Token mit Rechten 600 ablegen (die Datei wird vor dem Schreiben mit 600 angelegt)."""
    url = (url or portal_url()).rstrip("/")
    token = token.strip()
    if not token or any(c.isspace() for c in token) or len(token) > 200:
        raise OnlineFehler(tr("Das Token ist leer oder enthält Leerzeichen."))
    if not kurspaket._url_ok(url):
        raise OnlineFehler(tr("Die Adresse des Portals muss mit https:// beginnen."))
    datei = _zugang_datei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"url": url, "token": token}, f)
    os.replace(tmp, datei)


def zugang_loeschen() -> None:
    _zugang_datei().unlink(missing_ok=True)


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):        # das Token würde sonst mit zu einem anderen Ziel wandern
        return None


def _text(wert, maximum: int = 300) -> str:
    return portal._bereinigen(str(wert if wert is not None else ""), maximum)


def _texte(werte, maximum: int = 300) -> list[str]:
    return [_text(w, maximum) for w in (werte if isinstance(werte, list) else [])[:200]]


@dataclass
class Ereignis:
    """Eintrag des Verlaufs, wie ihn der Server liefert (ohne Hashkette)."""
    nr: int
    zeit: str
    von: str
    nach: str
    akteur: str
    begruendung: str


class OnlineAblage:
    """Einreichungen des Servers: ``aktualisieren()`` lädt die Liste, ``detail_laden()`` Bericht und Verlauf."""

    def __init__(self, zugang: Zugang, opener=None, timeout: float = TIMEOUT):
        if not kurspaket._url_ok(zugang.url):
            raise OnlineFehler(tr("Die Adresse des Portals muss mit https:// beginnen."))
        self.zugang = zugang
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener(_KeineWeiterleitung()).open
        self._liste: dict[str, dict] = {}
        self._reihenfolge: list[str] = []
        self._detail: dict[str, dict] = {}

    # --- HTTP ------------------------------------------------------------

    def _anfrage(self, methode: str, pfad: str, daten: dict | None = None) -> dict:
        body = json.dumps(daten).encode("utf-8") if daten is not None else None
        req = urllib.request.Request(
            self.zugang.url + pfad, data=body, method=methode,
            headers={"Authorization": f"Bearer {self.zugang.token}", "Accept": "application/json",
                     "User-Agent": kurspaket.USER_AGENT, **({"Content-Type": "application/json"} if body else {})})
        try:
            with self._opener(req, timeout=self.timeout) as r:
                antwort = json.loads(r.read(MAX_ANTWORT + 1)[:MAX_ANTWORT].decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise OnlineFehler(self._fehlertext(e), e.code) from None
        except (OSError, ValueError):
            raise OnlineFehler(tr("Das Portal ist nicht erreichbar oder antwortet unverständlich.")) from None
        if not isinstance(antwort, dict):
            raise OnlineFehler(tr("Das Portal antwortet unverständlich."))
        return antwort

    @staticmethod
    def _fehlertext(e: urllib.error.HTTPError) -> str:
        meldung = {401: "Das Moderator-Token gilt nicht (mehr).",
                   403: "Dieses Token gehört nicht zu einem Moderator.",
                   404: "Diese Einreichung gibt es nicht.",
                   413: "Die Anfrage ist zu groß.",
                   422: "Die Entscheidung ist ungültig (Begründung fehlt oder ist zu lang).",
                   429: "Zu viele Anfragen – bitte eine Minute warten."}.get(e.code)
        if e.code == 409:
            try:
                meldung = _text(json.loads(e.read(4096).decode("utf-8")).get("meldung"), 200)
            except (OSError, ValueError, AttributeError):
                meldung = ""
            meldung = meldung or "Diese Entscheidung ist nicht erlaubt."
        return meldung or f"Das Portal hat die Anfrage abgelehnt (Fehler {e.code})."

    # --- Lesen -----------------------------------------------------------

    def aktualisieren(self) -> None:
        daten = self._anfrage("GET", "/moderation/liste")
        zeilen = daten.get("einreichungen")
        if not isinstance(zeilen, list):
            raise OnlineFehler(tr("Das Portal antwortet unverständlich."))
        self._liste, self._reihenfolge, self._detail = {}, [], {}
        for z in zeilen[:MAX_LISTE]:
            if not isinstance(z, dict) or not isinstance(z.get("id"), str) or not mod._ID.fullmatch(z["id"]):
                continue
            self._liste[z["id"]] = {"status": _text(z.get("status"), 20), "zeit": _text(z.get("zeit"), 40),
                                    "paket_id": _text(z.get("paket_id"), 60), "name": _text(z.get("name"), 120),
                                    "version": _text(z.get("version"), 20)}
            self._reihenfolge.append(z["id"])

    def detail_laden(self, sid: str) -> None:
        if sid in self._detail:
            return
        if not mod._ID.fullmatch(sid):
            raise OnlineFehler(tr("Ungültige Einreichungs-ID."))
        d = self._anfrage("GET", f"/moderation/einreichung/{sid}")
        b, verlauf = d.get("bericht"), d.get("verlauf")
        if not isinstance(b, dict) or not isinstance(verlauf, list):
            raise OnlineFehler(tr("Das Portal antwortet unverständlich."))
        ereignisse = []
        for e in verlauf[:200]:
            if isinstance(e, dict):
                ereignisse.append(Ereignis(int(e.get("nr") or 0), _text(e.get("zeit"), 40), _text(e.get("von"), 20),
                                           _text(e.get("nach"), 20), _text(e.get("akteur"), 80),
                                           _text(e.get("begruendung"), 2000)))
        self._detail[sid] = {
            "status": _text(d.get("status"), 20), "kette_ok": d.get("kette_ok") is True, "verlauf": ereignisse,
            "bericht": {"paket_id": _text(b.get("paket_id"), 60), "name": _text(b.get("name"), 120),
                        "version": _text(b.get("version"), 20), "groesse": int(b.get("groesse") or 0),
                        "sha256": _text(b.get("sha256"), 64), "findings": _texte(b.get("findings")),
                        "skripte": _texte(b.get("skripte")), "externe_links": _texte(b.get("externe_links")),
                        "fundstellen": _texte(b.get("fundstellen"))}}

    def ids(self) -> list[str]:
        return list(self._reihenfolge)

    def status(self, sid: str) -> str:
        if sid in self._detail:
            return self._detail[sid]["status"]
        return self._liste.get(sid, {}).get("status", "")

    def bericht(self, sid: str) -> dict | None:
        if sid in self._detail:
            return self._detail[sid]["bericht"]
        z = self._liste.get(sid)
        return {k: z[k] for k in ("paket_id", "name", "version")} if z else None

    def verlauf(self, sid: str) -> list[Ereignis]:
        self.detail_laden(sid)
        return self._detail[sid]["verlauf"]

    def kette_ok(self, sid: str) -> bool:
        return self._detail.get(sid, {}).get("kette_ok", True)

    # --- Schreiben -------------------------------------------------------

    def entscheiden(self, sid: str, nach: str, _akteur: str, begruendung: str) -> None:
        """Entscheidung senden. ``akteur`` wird ignoriert – der Server nimmt den Moderator des Tokens."""
        if not mod._ID.fullmatch(sid):
            raise OnlineFehler(tr("Ungültige Einreichungs-ID."))
        self._anfrage("POST", f"/moderation/entscheiden/{sid}", {"nach": nach, "begruendung": begruendung})
        self._detail.pop(sid, None)
        self.aktualisieren()

    @contextmanager
    def original_bereit(self, sid: str):
        """Lädt die Paketdatei in ein temporäres Verzeichnis (Größe und SHA-256 gegen den Bericht geprüft) und
        löscht sie danach wieder."""
        if not mod._ID.fullmatch(sid):
            raise OnlineFehler(tr("Ungültige Einreichungs-ID."))
        self.detail_laden(sid)
        soll = self._detail[sid]["bericht"]["sha256"]
        req = urllib.request.Request(self.zugang.url + f"/moderation/original/{sid}", method="GET",
                                     headers={"Authorization": f"Bearer {self.zugang.token}",
                                              "User-Agent": kurspaket.USER_AGENT})
        with tempfile.TemporaryDirectory(prefix=".ansicht-") as t:
            ziel = Path(t) / "original.bonyspaket"
            h, menge = hashlib.sha256(), 0
            try:
                with self._opener(req, timeout=self.timeout) as r, ziel.open("wb") as f:
                    while block := r.read(256 * 1024):
                        menge += len(block)
                        if menge > MAX_ORIGINAL:
                            raise OnlineFehler(tr("Die Paketdatei ist größer als erlaubt."))
                        h.update(block)
                        f.write(block)
            except urllib.error.HTTPError as e:
                raise OnlineFehler(self._fehlertext(e), e.code) from None
            except OSError:
                raise OnlineFehler(tr("Das Portal ist nicht erreichbar oder die Übertragung brach ab.")) from None
            if h.hexdigest() != soll:
                raise OnlineFehler(tr("Die Paketdatei passt nicht zur Prüfsumme im Bericht – verworfen."))
            yield ziel


@dataclass
class InhaltsDatei:
    pfad: str
    art: str            # "text", "skript", "bild" oder "sonstig"
    groesse: int
    text: str           # nur bei "text" und "skript"; Bilder und Sonstiges werden nie dargestellt


def _sauber(daten: bytes) -> str:
    return _STEUER.sub(" ", daten.decode("utf-8", errors="replace"))


def inhalt_lesen(datei: Path) -> list[InhaltsDatei]:
    """Paketdatei prüfend entpacken (``kurspaket.entpacken``, alle Schutzgrenzen) und die Texte als Klartext einlesen.
    Skripte werden nur als Text gelesen, nie ausgeführt; Bilder werden nicht geöffnet. Das Verzeichnis wird gelöscht."""
    ergebnis, gesamt = [], 0
    with tempfile.TemporaryDirectory(prefix=".ansicht-") as t:
        ziel = Path(t) / "p"
        try:
            kurspaket.entpacken(Path(datei), ziel)
        except kurspaket.PaketFehler as exc:
            raise OnlineFehler(tr("Das Paket lässt sich nicht sicher öffnen: {wert}", wert=_text(exc, 200))) from None
        for p in sorted(ziel.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            ende, groesse = p.suffix.lower(), p.stat().st_size
            art = ("skript" if ende in kurspaket.SKRIPT_ENDUNGEN else "text" if ende in TEXT_ENDUNGEN
                   else "bild" if ende in BILD_ENDUNGEN else "sonstig")
            text = ""
            if art in ("text", "skript") and gesamt < MAX_ANSICHT_GESAMT:
                with p.open("rb") as f:
                    daten = f.read(MAX_ANSICHT_DATEI + 1)
                text = _sauber(daten[:MAX_ANSICHT_DATEI]) + ("\n[… gekürzt]" if len(daten) > MAX_ANSICHT_DATEI else "")
                gesamt += len(text)
            ergebnis.append(InhaltsDatei(p.relative_to(ziel).as_posix(), art, groesse, text))
    return ergebnis
