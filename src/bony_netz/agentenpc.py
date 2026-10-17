"""Alles, was im Agenten-PC selbst passiert, damit er dem Bony-Netz beitritt."""

from __future__ import annotations

import re
import shlex

SKRIPT_VORLAGE = r"""#!/bin/bash
# Bony-Netz: Agenten-PC beim ersten Start mit dem Netz verbinden.
# Erzeugt von Bony's Agents. Läuft einmal; danach verbindet sich Tailscale von selbst.
set -euo pipefail
LOG=/var/log/bony-netz-beitritt.log
exec >>"$LOG" 2>&1
echo "== $(date -Is) Bony-Netz-Beitritt =="

LOGIN_SERVER=__LOGIN_SERVER__
SCHLUESSEL=__SCHLUESSEL__
NAME=__NAME__

# Warten, bis das Internet erreichbar ist (bis zu 5 Minuten)
for _ in $(seq 1 60); do
  if getent hosts pkgs.tailscale.com >/dev/null; then break; fi
  sleep 5
done

# Tailscale aus der offiziellen Paketquelle installieren
if ! command -v tailscale >/dev/null; then
  command -v curl >/dev/null || { apt-get update -q; DEBIAN_FRONTEND=noninteractive apt-get install -y -q curl ca-certificates; }
  . /etc/os-release
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL "https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}.noarmor.gpg" \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl -fsSL "https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}.tailscale-keyring.list" \
    -o /etc/apt/sources.list.d/tailscale.list
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q tailscale
fi
systemctl enable --now tailscaled

# Schon verbunden? Dann nichts tun (z. B. nach erneutem Ausführen).
if tailscale status --json 2>/dev/null | grep -q '"BackendState": "Running"'; then
  echo "Schon mit dem Netz verbunden."
else
  tailscale up --login-server "$LOGIN_SERVER" --authkey "$SCHLUESSEL" --hostname "$NAME" --accept-dns=true
fi
tailscale status || true

# Der Schlüssel ist jetzt verbraucht. Skript und Schlüssel entfernen.
rm -f -- "$0"
echo "== fertig =="
"""


def geraetename(name: str) -> str:
    """Macht aus einem Anzeigenamen einen gültigen Gerätenamen im Netz.

    'Agent PC 1 (Büro)' -> 'agent-pc-1-buero'
    """
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    name = name.strip().lower()
    for alt, neu in ersatz.items():
        name = name.replace(alt, neu)
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    name = re.sub(r"-{2,}", "-", name)
    return (name[:63].rstrip("-")) or "agent-pc"


def erstbeitritt_skript(login_server: str, schluessel: str, name: str) -> str:
    """Shell-Skript, das im Agenten-PC beim ersten Start als root laufen soll.

    login_server und schluessel kommen aus Zentrale.geraeteschluessel().
    Der Schlüssel ist nur einmal und nur kurz gültig (Standard: 60 Minuten).
    Das Skript also erst kurz vor dem ersten Start erzeugen.
    """
    if not login_server.startswith("https://"):
        raise ValueError("login_server muss mit https:// beginnen")
    return (SKRIPT_VORLAGE
            .replace("__LOGIN_SERVER__", shlex.quote(login_server))
            .replace("__SCHLUESSEL__", shlex.quote(schluessel))
            .replace("__NAME__", shlex.quote(geraetename(name))))
