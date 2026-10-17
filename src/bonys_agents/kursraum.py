# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursraum eines Bony-Netz-Kurses (Aufgabe 05): Bildschirm, Ton, Kamera und Chat über LiveKit.

Das Fenster (``gui/kursraum_fenster.py``) zeigt eine mitgelieferte Seite (``resources/kursraum/``) in einem
eingebetteten Browser (Qt WebEngine). Hier steht alles ohne Qt:

- ``eintreten(kurs_id)`` holt die Eintrittskarte bei der Zentrale (nur solange der Kurs läuft, sonst 409).
- ``stummschalten`` und ``entfernen`` (nur Kursleiter) rufen die Server-Schnittstelle von LiveKit auf
  (Twirp ``RoomService``) – mit der Kursleiter-Karte als Bearer-Token, sie enthält ``roomAdmin``.
- ``seiten_datei`` und ``erlaubt`` sind die Regeln für die Seite: nur Dateien aus ``resources/kursraum``, und
  Kamera, Mikrofon und Bildschirmaufnahme nur für diese lokale Seite.

Die Eintrittskarte ist ein Token wie das Instanz-Token: nie anzeigen, nie ins Log, nie in Fehlermeldungen, nie in
die Adresse der Seite (sie geht per QWebChannel an die Seite).
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from bony_netz import ZentraleFehler

from bonys_agents import kurse

SCHEMA = "kursraum"                  # eigene Adresse der Seite: kursraum://app/index.html
HOST = "app"
STARTSEITE = f"{SCHEMA}://{HOST}/index.html"
LIVEKIT_VERSION = "2.22.3"           # packaging/fetch-livekit.py holt genau diese Fassung
ZEITLIMIT = 15

KURSLEITER, TEILNEHMER = "kursleiter", "teilnehmer"

KURS_LAEUFT_NICHT = ("Der Kurs läuft gerade nicht. Den Kursraum gibt es nur, solange der Kursleiter den Kurs "
                     "gestartet hat.")
KARTE_ABGELAUFEN = "Deine Eintrittskarte ist abgelaufen (sie gilt 6 Stunden). Tritt bitte erneut ein."
KEIN_WEBENGINE = ("Für den Kursraum fehlt dieser Installation der eingebettete Browser (Qt WebEngine). "
                  "Mit den fertigen Paketen von Bony's Agents ist er dabei; aus dem Quelltext: "
                  "pip install PySide6-WebEngine (bzw. PySide6-Addons bis Version 6.11).")
KEINE_SEITE = ("Die Seite des Kursraums fehlt in dieser Installation (beim Bauen: python packaging/fetch-livekit.py).")
WAYLAND_HINWEIS = ("Bildschirm teilen geht unter Linux nur in einer X11-Sitzung: Der eingebaute Browser kann unter "
                   "Wayland keine Bildschirmaufnahme. Melde dich dafür mit „Cinnamon“/„GNOME on Xorg“ o. Ä. an. "
                   "Kamera, Ton und Chat gehen auch so.")

# Was die Seite bekommen darf (Namen von QWebEnginePermission.PermissionType bzw. QWebEnginePage.Feature)
ERLAUBT = frozenset({
    "MediaAudioCapture", "MediaVideoCapture", "MediaAudioVideoCapture",
    "DesktopVideoCapture", "DesktopAudioVideoCapture",
})

# Dateien der Seite (resources/kursraum) – andere Endungen liefert das Schema nicht aus
MIME = {
    ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
    ".png": "image/png", ".json": "application/json",
}


class KursraumFehler(Exception):
    """Für den Nutzer geschrieben – kann direkt angezeigt werden."""


@dataclass
class Karte:
    kurs_id: str
    kursraum_url: str
    raum: str
    rolle: str
    token: str = field(repr=False)
    ablauf: float | None = None      # „exp“ aus dem Token (Sekunden seit 1970)

    @property
    def kursleiter(self) -> bool:
        return self.rolle == KURSLEITER

    def abgelaufen(self, jetzt: float | None = None) -> bool:
        return self.ablauf is not None and (jetzt if jetzt is not None else time.time()) >= self.ablauf

    def fuer_seite(self, **extra) -> dict:
        """Was die Seite zum Verbinden braucht – nur über QWebChannel, nie über die Adresse."""
        return {"url": self.kursraum_url, "token": self.token, "rolle": self.rolle, "raum": self.raum,
                "ablauf": self.ablauf, **extra}


# ---------------------------------------------------------------- Eintrittskarte
def token_ablauf(token: str) -> float | None:
    """``exp`` aus einem JWT lesen (ohne Prüfung der Signatur – nur für die Anzeige „abgelaufen“)."""
    try:
        teil = token.split(".")[1]
        daten = json.loads(base64.urlsafe_b64decode(teil + "=" * (-len(teil) % 4)))
        exp = daten.get("exp")
        return float(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else None
    except (IndexError, ValueError, TypeError, AttributeError):
        return None


def eintreten(kurs_id: str) -> Karte:
    """Eintrittskarte holen. Läuft der Kurs nicht (409), kommt ``KursraumFehler(KURS_LAEUFT_NICHT)``."""
    try:
        d = kurse._aufruf(lambda z: z.eintrittskarte(kurs_id))
    except ZentraleFehler as e:
        if e.status == 409:
            raise KursraumFehler(KURS_LAEUFT_NICHT) from None
        raise
    if not isinstance(d, dict):
        raise KursraumFehler("Die Zentrale hat keine Eintrittskarte geschickt.")
    url, token = d.get("kursraum_url"), d.get("eintrittskarte")
    if not isinstance(url, str) or not isinstance(token, str) or not token:
        raise KursraumFehler("Die Zentrale hat keine gültige Eintrittskarte geschickt.")
    server_adresse(url)   # prüft das Schema
    rolle = KURSLEITER if d.get("rolle") == KURSLEITER else TEILNEHMER
    return Karte(kurs_id, url, str(d.get("raum") or ""), rolle, token, token_ablauf(token))


# ---------------------------------------------------------------- LiveKit-Server (nur Kursleiter)
def server_adresse(kursraum_url: str) -> str:
    """``wss://k.example.de`` → ``https://k.example.de`` (Server-Schnittstelle von LiveKit)."""
    teile = urllib.parse.urlsplit(kursraum_url.strip())
    schema = {"wss": "https", "ws": "http", "https": "https", "http": "http"}.get(teile.scheme.lower())
    if schema is None or not teile.netloc:
        raise KursraumFehler(f"Unbekannte Adresse des Kursraums: {kursraum_url}")
    pfad = teile.path.rstrip("/")
    return urllib.parse.urlunsplit((schema, teile.netloc, pfad, "", ""))


def _twirp(karte: Karte, methode: str, daten: dict) -> dict:
    if not karte.kursleiter:
        raise KursraumFehler("Das darf nur der Kursleiter.")
    if karte.abgelaufen():
        raise KursraumFehler(KARTE_ABGELAUFEN)
    url = f"{server_adresse(karte.kursraum_url)}/twirp/livekit.RoomService/{methode}"
    anfrage = urllib.request.Request(url, data=json.dumps(daten).encode(), method="POST", headers={
        "Authorization": f"Bearer {karte.token}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "bonys-agents-kursraum"})
    kontext = ssl.create_default_context() if url.startswith("https://") else None
    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITLIMIT, context=kontext) as antwort:  # noqa: S310
            inhalt = antwort.read()
            return json.loads(inhalt) if inhalt else {}
    except urllib.error.HTTPError as e:
        raise KursraumFehler(_twirp_fehler(e)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        grund = getattr(e, "reason", e)
        raise KursraumFehler(f"Der Kursraum-Server ist nicht erreichbar ({grund}).") from None
    except ValueError:
        return {}


def _twirp_fehler(e: urllib.error.HTTPError) -> str:
    try:
        d = json.loads(e.read())
        code, msg = str(d.get("code") or ""), str(d.get("msg") or "")
    except Exception:  # noqa: BLE001
        code, msg = "", ""
    if e.code == 401 or code == "unauthenticated":
        return "Der Kursraum-Server hat die Karte nicht angenommen – tritt bitte erneut ein."
    if e.code == 403 or code == "permission_denied":
        return "Der Kursraum-Server erlaubt das dieser Karte nicht."
    if e.code == 404 or code == "not_found":
        return "Der Teilnehmer ist nicht mehr im Kursraum."
    return f"Der Kursraum-Server hat mit Fehler {e.code} geantwortet" + (f": {msg}" if msg else ".")


def stummschalten(karte: Karte, identitaet: str, track_sid: str) -> None:
    """Mikrofon eines Teilnehmers stumm schalten. Er kann es danach selbst wieder einschalten."""
    if not identitaet or not track_sid:
        raise KursraumFehler("Der Teilnehmer hat kein Mikrofon an.")
    _twirp(karte, "MutePublishedTrack",
           {"room": karte.raum, "identity": identitaet, "track_sid": track_sid, "muted": True})


def entfernen(karte: Karte, identitaet: str) -> None:
    """Teilnehmer aus dem Kursraum werfen (nicht aus dem Kurs – dafür „Entfernen …“ in der Kursansicht)."""
    if not identitaet:
        raise KursraumFehler("Kein Teilnehmer gewählt.")
    _twirp(karte, "RemoveParticipant", {"room": karte.raum, "identity": identitaet})


# ---------------------------------------------------------------- Regeln für die Seite
def seiten_ordner() -> Path:
    return Path(str(resources.files("bonys_agents") / "resources" / "kursraum"))


def livekit_da(ordner: Path | None = None) -> bool:
    return ((ordner or seiten_ordner()) / "vendor" / "livekit-client.umd.js").is_file()


def seiten_datei(pfad: str, ordner: Path | None = None) -> tuple[Path, str] | None:
    """URL-Pfad der Seite → (Datei, MIME-Typ). Nur Dateien in ``resources/kursraum`` mit bekannter Endung."""
    ordner = (ordner or seiten_ordner()).resolve()
    pfad = urllib.parse.unquote(pfad or "/").lstrip("/") or "index.html"
    teile = pfad.split("/")
    if any(t in ("", ".", "..") or "\\" in t or ":" in t for t in teile):
        return None
    datei = ordner.joinpath(*teile).resolve()
    if ordner not in datei.parents or not datei.is_file():
        return None
    mime = MIME.get(datei.suffix.lower())
    return (datei, mime) if mime else None


def erlaubt(schema: str, host: str, art: str) -> bool:
    """Kamera, Mikrofon, Bildschirm – nur für die lokale Seite des Kursraums, alles andere nie."""
    return schema == SCHEMA and host == HOST and art in ERLAUBT


def wayland() -> bool:
    """Linux-Sitzung mit Wayland (dort kann Qt WebEngine den Bildschirm nicht aufnehmen)."""
    if not sys.platform.startswith("linux"):
        return False
    sitzung = os.environ.get("XDG_SESSION_TYPE", "").lower()
    return sitzung == "wayland" if sitzung else bool(os.environ.get("WAYLAND_DISPLAY"))


USERNS_SPERRE = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
APPARMOR_LABEL = (Path("/proc/self/attr/apparmor/current"), Path("/proc/self/attr/current"))
APPARMOR_PROFIL = "bonys-agents"   # packaging/linux/apparmor-bonys-agents


def sandbox_abschalten(sperre: Path = USERNS_SPERRE, label: tuple[Path, ...] = APPARMOR_LABEL) -> bool:
    """Ubuntu ab 24.04 ohne unser AppArmor-Profil: Chromium darf keine Namensräume anlegen, der Kursraum stürzte ab.

    Das .deb bringt das Profil mit (dann bleibt die Sandbox an). Fehlt es – Quelltext-Installation, eigener Pfad –,
    läuft Qt WebEngine ohne Sandbox. Die Seite lädt nur Dateien aus der App und spricht nur mit dem Kursraum-Server.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        if sperre.read_text().strip() != "1":
            return False
    except OSError:
        return False
    for datei in label:
        try:
            if datei.read_text().strip().startswith(APPARMOR_PROFIL + " "):
                return False
        except OSError:
            continue
    return True


def bildschirm_teilen() -> tuple[bool, str]:
    """(möglich, Hinweis) für den Knopf „Bildschirm teilen“ beim Kursleiter."""
    return (False, WAYLAND_HINWEIS) if wayland() else (True, "")
