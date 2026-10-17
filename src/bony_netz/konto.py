# SPDX-License-Identifier: GPL-3.0-or-later
"""Speichert Serveradresse und Instanz-Anmeldung im Benutzerordner.

Speicherort:
    Linux:   ~/.config/bonys-netz/konto.json   (oder $XDG_CONFIG_HOME)
    Windows: %APPDATA%\\BonysNetz\\konto.json
    macOS:   ~/Library/Application Support/BonysNetz/konto.json

Bony's Agents und Bony's VPN teilen sich diese Datei, damit beide dieselbe
Instanz benutzen. Unter Linux und macOS ist sie nur für den Benutzer lesbar.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

STANDARD_SERVER = "https://zentrale.bony23.de"


def speicherordner() -> Path:
    eigener = os.environ.get("BONY_NETZ_ORDNER")
    if eigener:
        return Path(eigener)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "BonysNetz"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BonysNetz"
    basis = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(basis) / "bonys-netz"


def server_normalisieren(adresse: str) -> str:
    """'zentrale.example.de' -> 'https://zentrale.example.de' (ohne Schrägstrich am Ende)."""
    adresse = adresse.strip().rstrip("/")
    if not adresse:
        return STANDARD_SERVER
    if "://" not in adresse:
        adresse = "https://" + adresse
    return adresse


@dataclass
class Konto:
    server: str = STANDARD_SERVER
    instanz_id: str = ""
    token: str = ""
    login_server: str = ""          # Adresse von Headscale, kommt von der Zentrale
    ist_kursleiter: bool = False
    extra: dict = field(default_factory=dict)   # Platz für App-eigene Einstellungen

    @property
    def angemeldet(self) -> bool:
        return bool(self.instanz_id and self.token)

    # -- Laden und Speichern -------------------------------------------------

    @staticmethod
    def pfad() -> Path:
        return speicherordner() / "konto.json"

    @classmethod
    def laden(cls) -> "Konto":
        pfad = cls.pfad()
        if not pfad.exists():
            return cls()
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        bekannt = {k: daten[k] for k in cls.__dataclass_fields__ if k in daten}
        return cls(**bekannt)

    def speichern(self) -> None:
        pfad = self.pfad()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(pfad.parent, 0o700)
        # Erst in eine Nachbardatei schreiben, dann ersetzen: so ist die Datei nie halb geschrieben.
        fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=".konto-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
            if os.name == "posix":
                os.chmod(tmp, 0o600)
            os.replace(tmp, pfad)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # -- Änderungen ----------------------------------------------------------

    def server_wechseln(self, adresse: str) -> None:
        """Anderen Server einstellen. Die Anmeldung beim alten Server wird verworfen."""
        neu = server_normalisieren(adresse)
        if neu != self.server:
            self.server = neu
            self.abmelden()

    def uebernehmen(self, registrierung: dict) -> None:
        """Antwort von Zentrale.instanz_registrieren() übernehmen."""
        self.instanz_id = registrierung["instanz_id"]
        self.token = registrierung["token"]
        self.login_server = registrierung.get("login_server", "")
        self.ist_kursleiter = False

    def abmelden(self) -> None:
        self.instanz_id = ""
        self.token = ""
        self.login_server = ""
        self.ist_kursleiter = False
