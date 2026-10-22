# SPDX-License-Identifier: GPL-3.0-or-later
"""n8n im Agent-PC: Workflows per Klick, als Docker-Container aus dem offiziellen Image.

- Image ``docker.n8n.io/n8nio/n8n:stable`` (offizielle Registry von n8n), Docker aus der App „docker“ – derselbe
  Unterbau wie Mission Control, nichts doppelt.
- Nur an 127.0.0.1:5678 im Agent-PC – weder ins Heimnetz noch ins Bony-Netz.
- Daten im benannten Volume ``n8n_data`` (``/home/node/.n8n``), dadurch überstehen Workflows jedes Update.
- ``bonys-n8n.service`` legt den Container beim Start an, falls er fehlt (z. B. nach einer frischen Vorlage), und
  startet ihn; Zeitzone = die des Agent-PCs.

Lizenz: Sustainable Use License – Quellcode offen, aber keine OSI-Open-Source-Lizenz. Deshalb steckt n8n nicht in
weitergegebenen Vorlagen (``redistributable=False``): Der Empfänger lädt das Image selbst aus der offiziellen Quelle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bonys_agents import agenten_apps, desktops

if TYPE_CHECKING:
    from bonys_agents.apps import AppSpec

APP_ID = "n8n"
NAME = "n8n"
IMAGE = "docker.n8n.io/n8nio/n8n:stable"
CONTAINER = "n8n"
VOLUME = "n8n_data"
PORT = 5678
URL = f"http://localhost:{PORT}"
HOMEPAGE = "https://n8n.io"
SCRIPT = "/usr/local/bin/bonys-n8n"
OPENER = "/usr/local/bin/bonys-n8n-open"
UNIT = "bonys-n8n.service"
LAUNCHER = "bonys-n8n.desktop"
LICENSE_NOTE = ("Sustainable Use License: Quellcode offen und kostenlos für eigene Zwecke, aber keine "
                "OSI-Open-Source-Lizenz")
# Zusätzlicher Bedarf (laut n8n grob 0,5–1 GB RAM; Image samt Daten etwa 1–2 GB)
MIN_RAM_MB = 1024
MIN_FREE_DISK_GB = 2
FRESH_CLEANUP = ("n8n: Workflows, Zugangsdaten und Konto (Docker-Volume n8n_data) – jeder neue Agent-PC richtet "
                 "n8n beim ersten Öffnen neu ein; das Image bleibt")


def _sq(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def requirement_note() -> str:
    return f"braucht Docker, ca. {MIN_RAM_MB / 1024:.0f} GB mehr RAM und {MIN_FREE_DISK_GB} GB Festplatte"


def resource_warnings(app_ids: list[str], ram_mb: int, desktop_min_ram_mb: int,
                      other_ram_mb: int = 0) -> list[str]:
    """Warnung, wenn der RAM für n8n knapp ist (leer = alles gut).

    ``other_ram_mb``: Bedarf weiterer Docker-Apps, die gleichzeitig laufen (z. B. Mission Control).
    """
    from bonys_agents import apps

    if APP_ID not in apps.with_dependencies(app_ids):
        return []
    need = desktop_min_ram_mb + MIN_RAM_MB + other_ram_mb
    if ram_mb >= need:
        return []
    return [f"{NAME} braucht etwa {MIN_RAM_MB / 1024:.0f} GB RAM zusätzlich – empfohlen sind mindestens "
            f"{need / 1024:.1f} GB für den Agent-PC (eingestellt: {ram_mb / 1024:.1f} GB). "
            "Vorschlag: Arbeitsspeicher erhöhen."]


def container_script() -> str:
    """``bonys-n8n start|update``: Container anlegen bzw. mit neuem Image neu anlegen – das Volume bleibt."""
    return r"""#!/bin/sh
# Von Bony's Agents: n8n-Container (offizielles Image, nur 127.0.0.1:""" + str(PORT) + r""", Daten im Volume """ + VOLUME + r""")
#   start   beim Systemstart: anlegen, falls er fehlt, dann starten
#   update  neues Image laden und den Container damit neu anlegen
set -eu
IMAGE=""" + _sq(IMAGE) + r"""
ZONE="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
[ -n "$ZONE" ] || ZONE="$(cat /etc/timezone 2>/dev/null || true)"
[ -n "$ZONE" ] || ZONE=Europe/Berlin
create() {
  docker volume create """ + VOLUME + r""" >/dev/null
  docker run -d --name """ + CONTAINER + r""" --restart unless-stopped \
    -p 127.0.0.1:""" + f"{PORT}:{PORT}" + r""" \
    -e GENERIC_TIMEZONE="$ZONE" -e TZ="$ZONE" \
    -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
    -e N8N_DIAGNOSTICS_ENABLED=false \
    -v """ + VOLUME + r""":/home/node/.n8n \
    "$IMAGE" >/dev/null
}
case "${1:-start}" in
  start)
    if ! docker container inspect """ + CONTAINER + r""" >/dev/null 2>&1; then
      docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"
      create
    fi
    docker start """ + CONTAINER + r""" >/dev/null
    ;;
  update)
    docker pull "$IMAGE"
    docker rm -f """ + CONTAINER + r""" >/dev/null 2>&1 || true
    create
    ;;
  *) echo "Aufruf: $0 start|update" >&2; exit 2 ;;
esac
"""


def install_script() -> str:
    """App-Schritt (als root im Gast, $AGENT_USER und $DESKTOP_DIR gesetzt): n8n installieren und starten."""
    return r"""
cat > """ + SCRIPT + r""" <<'BONYS_N8N'
""" + container_script() + r"""BONYS_N8N
chmod 755 """ + SCRIPT + r"""
cat > /etc/systemd/system/""" + UNIT + r""" <<'EOF'
[Unit]
Description=Bony's Agents: n8n (Docker, nur 127.0.0.1:""" + str(PORT) + r""")
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=""" + SCRIPT + r""" start
TimeoutStartSec=1200

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
echo "n8n: lade das offizielle Image """ + IMAGE + r""" …"
docker pull """ + _sq(IMAGE) + r"""
systemctl enable """ + UNIT + r"""
systemctl restart """ + UNIT + r"""
""" + launcher_script() + agenten_apps.REFRESH


def launcher_script() -> str:
    """Starter „n8n“: öffnet die Oberfläche in Brave (fehlt Brave, im Standard-Browser)."""
    return r"""
cat > """ + OPENER + r""" <<'EOF'
#!/bin/sh
# Von Bony's Agents: n8n im Browser öffnen (Brave, sonst Standard-Browser)
URL=""" + _sq(URL) + r"""
if command -v brave-browser >/dev/null 2>&1; then
  STORE=""
  [ -e """ + desktops.BRAVE_BASIC_MARKER + r""" ] && STORE="--password-store=basic"
  exec brave-browser $STORE --no-first-run --no-default-browser-check "$URL"
fi
exec xdg-open "$URL"
EOF
chmod 755 """ + OPENER + r"""
cat > /usr/share/applications/""" + LAUNCHER + r""" <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=n8n
Comment=Workflows bauen – n8n im Browser öffnen (nur im Agent-PC erreichbar)
Exec=""" + OPENER + r"""
Icon=applications-internet
Terminal=false
Categories=Network;Utility;
StartupNotify=false
EOF
chmod 644 /usr/share/applications/""" + LAUNCHER + r"""
cp /usr/share/applications/""" + LAUNCHER + r""" "$DESKTOP_DIR/"
chown "$AGENT_USER:$AGENT_USER" "$DESKTOP_DIR/""" + LAUNCHER + r""""
chmod 755 "$DESKTOP_DIR/""" + LAUNCHER + r""""
"""


UNINSTALL = r"""
systemctl disable --now """ + UNIT + r""" >/dev/null 2>&1 || true
if command -v docker >/dev/null 2>&1; then
  docker rm -f """ + CONTAINER + r""" >/dev/null 2>&1 || true
  docker volume rm """ + VOLUME + r""" >/dev/null 2>&1 || true
  docker image rm """ + _sq(IMAGE) + r""" >/dev/null 2>&1 || true
fi
rm -f /etc/systemd/system/""" + UNIT + " " + SCRIPT + " " + OPENER + " /usr/share/applications/" + LAUNCHER + \
    r""" "$DESKTOP_DIR/""" + LAUNCHER + r""""
systemctl daemon-reload
""" + agenten_apps.REFRESH

# Prüfung (als Agent-Benutzer): die Oberfläche selbst antwortet – /healthz meldet schon „ok“, während der Editor
# noch „Cannot GET /“ zeigt (beim Start etwa 1–2 Minuten). Bis zu 4 Minuten warten.
CHECK = (f"for i in $(seq 120); do curl -fsS --max-time 5 -H 'Accept: text/html' {URL}/ >/dev/null 2>&1 && exit 0; "
         "sleep 2; done; exit 1")


def fresh_template_script() -> str:
    """Teil von ``generalize_script`` (frische Vorlage): Daten von n8n entfernen – ``$DRY`` = 1 nur anzeigen.

    Der Container wird mitgelöscht; ``bonys-n8n.service`` legt ihn beim nächsten Start mit leerem Volume neu an.
    """
    return r"""echo "== n8n =="
if command -v docker >/dev/null 2>&1 && { systemctl start docker.service >/dev/null 2>&1 || true; } \
   && docker volume inspect """ + VOLUME + r""" >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then
    echo "WÜRDE AUSFÜHREN: Container """ + CONTAINER + r""" und Volume """ + VOLUME + r""" löschen (Workflows und Zugangsdaten von n8n)"
  else
    docker rm -f """ + CONTAINER + r""" >/dev/null 2>&1 || true
    docker volume rm """ + VOLUME + r""" >/dev/null || { echo "FEHLER: Die Daten von n8n (Docker-Volume) ließen sich nicht löschen."; exit 1; }
    echo "n8n: Workflows, Zugangsdaten und Konto entfernt – beim nächsten Start legt n8n alles neu an."
  fi
fi"""


def app_spec() -> AppSpec:
    from bonys_agents.apps import AppSpec

    return AppSpec(
        id=APP_ID,
        name=NAME,
        description="Workflows per Klick bauen (Mails, RSS, Telegram, Dateien, APIs) – läuft als Docker-Container "
                    "nur im Agent-PC, Hermes kann Workflows anstoßen",
        default=True,
        weight=12.0,   # Image laden und erster Start
        requires=("brave", "docker"),
        check=CHECK,
        launcher=LAUNCHER,
        # als Agent-Benutzer (Gruppe docker): neues Image, Container neu anlegen – Daten bleiben im Volume
        update=f"{SCRIPT} update",
        version=f"docker exec {CONTAINER} n8n --version",
        redistributable=False,
        uninstall=UNINSTALL,
        install=install_script(),
    )
