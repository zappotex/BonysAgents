# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's Agents – virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent."""

from pathlib import Path

__version__ = "0.14.0"
APP_NAME = "Bony's Agents"
APP_ID = "bonys-agents"
TAGLINE = "Mit KI lernen, arbeiten und kreativ sein – aber der Mensch bleibt am Steuer"

YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@BonysAgents"
# Vorstellungsvideo – sobald es online ist, nur diese Zeile ändern.
INTRO_VIDEO_URL = YOUTUBE_CHANNEL_URL

LICENSE_ID = "GPL-3.0-or-later"
COPYRIGHT = "Copyright © 2026 Bony"
REPO_URL = "https://github.com/zappotex/BonysAgents"

# ---------- Updates – nur hier ändern ----------
# GitHub-Repository („Besitzer/Name“), dessen Releases nach neuen Versionen durchsucht werden.
# Daraus ergibt sich auch die APT-Paketquelle: https://<besitzer>.github.io/<name>/apt/
UPDATE_REPO = "zappotex/BonysAgents"
# Öffentlicher minisign-Schlüssel (die Zeile „RW…“ aus der .pub-Datei), mit dem die Release-Pipeline
# die Datei SHA256SUMS signiert – siehe docs/RELEASE.md. Leer = Updates werden nicht installiert.
UPDATE_PUBLIC_KEY = "RWSbJYUNae7BsW6nDlNspFi16gc1nsM4hGbdmXq9noaPLpeVMtvDdIM6"


def license_location(name: str) -> str:
    """Lizenzdatei (LICENSE oder THIRD-PARTY-LICENSES) als Pfad – sonst die Adresse auf GitHub.

    Im installierten Programm liegen beide unter bonys_agents/licenses/, im Quellordner im Hauptverzeichnis.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "licenses" / name, here.parent.parent / name):
        if candidate.is_file():
            return str(candidate)
    return f"{REPO_URL}/blob/main/{name}"
