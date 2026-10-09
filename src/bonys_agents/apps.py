# SPDX-License-Identifier: GPL-3.0-or-later
"""Apps, die in einen Agent-PC installiert werden können.

Jede App ist ein kleines Bash-Snippet, das im Gast als root läuft.
Verfügbare Variablen: $AGENT_USER, $AGENT_HOME, $DESKTOP_DIR.
KI-Werkzeuge installieren sich selbst als $AGENT_USER (nie als root) und
bringen keinerlei Zugangsdaten mit – angemeldet wird beim ersten Start im Agent-PC.

Neue App hinzufügen = einen weiteren ``AppSpec`` in ``APPS`` eintragen.
Die Reihenfolge in ``APPS`` ist auch die Reihenfolge der Einrichtungsschritte.
"""

from __future__ import annotations

import base64
import gzip
import io
import tarfile
from dataclasses import dataclass
from importlib import resources

from bonys_agents import screen

PROGRAM = "program"
AGENT = "agent"


@dataclass(frozen=True)
class AppSpec:
    id: str
    name: str
    description: str
    install: str
    default: bool = True
    category: str = PROGRAM   # PROGRAM oder AGENT (Bereich im Dialog)
    weight: float = 10.0      # ungefähre Dauer der Installation, für die Prozentanzeige
    check: str = "true"       # prüft (als $AGENT_USER) nach dem Nachinstallieren, ob die App da ist
    # Offizieller Update-Befehl (läuft als $AGENT_USER); leer = kommt über apt bzw. flatpak mit
    update: str = ""
    # Name der .desktop-Datei (für das GNOME-Dash); leer = kein Programm-Symbol
    launcher: str = ""


# Ordner im PATH des Agent-Benutzers ergänzen – in ~/.bashrc (Terminal) und ~/.profile (Anmeldung).
ENSURE_PATH = r"""
ensure_path() {  # $1 = Ordner relativ zu $HOME, z. B. .local/bin
  for f in "$AGENT_HOME/.bashrc" "$AGENT_HOME/.profile"; do
    touch "$f"
    grep -qF "\$HOME/$1" "$f" || printf '\n# ergänzt von Bonys Agents\nexport PATH="$HOME/%s:$PATH"\n' "$1" >> "$f"
    chown "$AGENT_USER:$AGENT_USER" "$f"
  done
}
"""


BRAVE = AppSpec(
    id="brave",
    name="Brave Browser",
    description="Datenschutzfreundlicher Browser (offizielles Brave-Repository)",
    check="command -v brave-browser",
    launcher="brave-browser.desktop",
    install=r"""
curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg \
  https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" \
  > /etc/apt/sources.list.d/brave-browser-release.list
apt-get update -y
apt-get install -y brave-browser
cp /usr/share/applications/brave-browser.desktop "$DESKTOP_DIR/" || true
""",
)

TELEGRAM = AppSpec(
    id="telegram",
    name="Telegram Desktop",
    description="Messenger über Flathub (x86_64 und ARM64)",
    check="flatpak info org.telegram.desktop",
    launcher="org.telegram.desktop.desktop",
    install=r"""
apt-get install -y flatpak
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --noninteractive --or-update flathub org.telegram.desktop
cp /var/lib/flatpak/exports/share/applications/org.telegram.desktop.desktop "$DESKTOP_DIR/" || true
""",
)

XRDP = AppSpec(
    id="xrdp",
    name="Fernzugriff (RDP)",
    description="Fernsteuerung mit Ton – z. B. mit Remmina oder der Windows-Remotedesktopverbindung",
    weight=6.0,
    check="test -x /usr/sbin/xrdp",  # nur installiert – eingeschaltet wird bei Bedarf
    install=r"""
apt-get install -y xrdp pipewire-module-xrdp dbus-x11
adduser xrdp ssl-cert
# Desktop des Agent-PCs als RDP-Sitzung (steht in /etc/bonys-agents/desktop.env, sonst Cinnamon).
# Eigener D-Bus-Sitzungsbus (dbus-run-session): Ist derselbe Benutzer schon lokal angemeldet
# (Autologin), teilen sich sonst beide Sitzungen den Bus unter /run/user/<uid>/bus – die
# RDP-Sitzung bliebe schwarz oder bräche ab.
cat > /etc/xrdp/startwm.sh <<'EOF'
#!/bin/sh
# Von Bony's Agents: Desktop-Sitzung für xrdp
if [ -r /etc/default/locale ]; then
  . /etc/default/locale
  export LANG LANGUAGE
fi
XSESSION=cinnamon SESSION_CMD=cinnamon-session XDG_DESKTOP=X-Cinnamon
[ -r /etc/bonys-agents/desktop.env ] && . /etc/bonys-agents/desktop.env
unset DBUS_SESSION_BUS_ADDRESS
export XDG_CURRENT_DESKTOP="$XDG_DESKTOP" XDG_SESSION_DESKTOP="$XSESSION" DESKTOP_SESSION="$XSESSION" XDG_SESSION_TYPE=x11
[ "$XSESSION" = gnome-xorg ] && export GNOME_SHELL_SESSION_MODE=gnome
exec dbus-run-session -- $SESSION_CMD
EOF
chmod 755 /etc/xrdp/startwm.sh
# Keine Passwort-Abfragen von colord in RDP-Sitzungen („Farbprofil anlegen …“)
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/45-bonys-xrdp-colord.rules <<'EOF'
polkit.addRule(function(action, subject) {
  if (action.id.indexOf("org.freedesktop.color-manager.") == 0 && subject.isInGroup("users")) {
    return polkit.Result.YES;
  }
});
EOF
adduser "$AGENT_USER" users || true
# Installiert, aber aus: Bony's Agents schaltet xrdp nur bei Bedarf ein („Fernzugriff einschalten“).
systemctl disable --now xrdp xrdp-sesman || true
""",
)

OBSIDIAN = AppSpec(
    id="obsidian",
    name="Obsidian (Notizen)",
    description="Markdown-Notizen (offizielles GitHub-Release) – kostenlos, aber kein Open Source",
    default=False,
    weight=8.0,
    check="test -x /opt/Obsidian/obsidian",
    launcher="md.obsidian.Obsidian.desktop",
    # Neueste Version aus dem offiziellen GitHub-Release, SHA-256 aus der GitHub-API.
    # amd64: offizielle .deb. arm64: keine .deb vorhanden → offizielles tar.gz nach /opt/Obsidian
    # mit denselben Abhängigkeiten und demselben Sandbox-Vorgehen wie die .deb.
    # Programm-Updates holt Obsidian selbst; leerer Tresor ohne Anmeldung/Sync.
    install=r"""
apt-get install -y curl ca-certificates python3
ARCH="$(dpkg --print-architecture)"
TMP="$(mktemp -d)"
python3 - "$ARCH" > "$TMP/asset" <<'EOF'
import json, sys, urllib.request
arch = sys.argv[1]
req = urllib.request.Request(
    "https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "bonys-agents"})
rel = json.load(urllib.request.urlopen(req, timeout=60))
ver = rel["tag_name"].lstrip("v")
want = {"amd64": f"obsidian_{ver}_amd64.deb", "arm64": f"obsidian-{ver}-arm64.tar.gz"}.get(arch)
if not want:
    sys.exit(f"Obsidian gibt es nicht für {arch}.")
prefix = "https://github.com/obsidianmd/obsidian-releases/releases/download/"
for a in rel["assets"]:
    if a["name"] == want and a["browser_download_url"].startswith(prefix):
        digest = a.get("digest") or ""
        print(ver, a["name"], a["browser_download_url"], digest.removeprefix("sha256:") if digest.startswith("sha256:") else "-")
        break
else:
    sys.exit(f"{want} fehlt im Obsidian-Release {ver}.")
EOF
read -r VER FILE URL SHA < "$TMP/asset"
echo "Lade Obsidian $VER ($FILE) …"
curl -fSL --retry 3 -o "$TMP/$FILE" "$URL"
if [ "$SHA" != "-" ]; then
  echo "$SHA  $TMP/$FILE" | sha256sum -c -
else
  echo "WARNUNG: Für $FILE ist keine Prüfsumme angegeben."
fi
if [ "$ARCH" = amd64 ]; then
  apt-get install -y "$TMP/$FILE"
else
  apt-get install -y libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0
  rm -rf /opt/Obsidian
  mkdir -p /opt/Obsidian
  tar -xzf "$TMP/$FILE" -C /opt/Obsidian --strip-components=1 --no-same-owner
  if { [ -L /proc/self/ns/user ] && unshare --user true; }; then
    chmod 0755 /opt/Obsidian/chrome-sandbox
  else
    chmod 4755 /opt/Obsidian/chrome-sandbox
  fi
  ln -sf /opt/Obsidian/obsidian /usr/bin/obsidian
  # gleicher Eintrag wie in der offiziellen .deb, nur mit dem Symbol aus dem Archiv
  cat > /usr/share/applications/md.obsidian.Obsidian.desktop <<'EOF'
[Desktop Entry]
Name=Obsidian
Exec=/opt/Obsidian/obsidian %U
Terminal=false
Type=Application
Icon=/opt/Obsidian/resources/icon.png
StartupWMClass=md.obsidian.Obsidian
Comment=Obsidian
MimeType=application/pdf;text/markdown;application/x-obsidian-canvas;application/x-obsidian-base;x-scheme-handler/obsidian;
Categories=Office;
EOF
fi
rm -rf "$TMP"
# Ohne Schlüsselbund-Abfrage beim ersten Start (automatische Anmeldung hat keinen entsperrten
# Schlüsselbund): offizieller Electron-Schalter --password-store=basic. Der Eintrag in
# /usr/local/share hat Vorrang vor dem der .deb und bleibt bei deren Updates erhalten.
mkdir -p /usr/local/share/applications
sed 's|^Exec=/opt/Obsidian/obsidian |Exec=/opt/Obsidian/obsidian --password-store=basic |' \
  /usr/share/applications/md.obsidian.Obsidian.desktop > /usr/local/share/applications/md.obsidian.Obsidian.desktop
grep -q -- '--password-store=basic' /usr/local/share/applications/md.obsidian.Obsidian.desktop
cp /usr/local/share/applications/md.obsidian.Obsidian.desktop "$DESKTOP_DIR/"
# Leerer Tresor „Agent-Notizen“, beim ersten Start schon geöffnet (keine Anmeldung, kein Sync)
VAULT="$AGENT_HOME/Agent-Notizen"
mkdir -p "$VAULT/.obsidian" "$AGENT_HOME/.config/obsidian"
CONF="$AGENT_HOME/.config/obsidian/obsidian.json"
if [ ! -s "$CONF" ]; then
  printf '{"vaults":{"%s":{"path":"%s","ts":%s,"open":true}}}\n' \
    "$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')" "$VAULT" "$(date +%s%3N)" > "$CONF"
fi
chown "$AGENT_USER:$AGENT_USER" "$AGENT_HOME/.config"
chown -R "$AGENT_USER:$AGENT_USER" "$VAULT" "$AGENT_HOME/.config/obsidian"
""",
)

# Debian-Pakete für Bony's VPN: Werkzeuge + Oberfläche (GTK 3 über python3-gi, Tray über Ayatana-AppIndicator).
# Kein openresolv: Der Agent-PC nutzt systemd-resolved, das resolvconf schon mitbringt.
VPN_PACKAGES = ("wireguard-tools nftables pkexec polkitd python3-gi gir1.2-gtk-3.0 "
                "gir1.2-ayatanaappindicator3-0.1")


def vpn_payload() -> str:
    """Quelltext von Bony's VPN (src/bonys_agents/vpn, ohne __pycache__) als tar.gz in base64.

    Steht direkt im Installationsschritt – kommt so beim Erstellen über das Seed-ISO und beim
    Nachinstallieren über den SSH-Weg in den Agent-PC. Reproduzierbar (feste Zeiten und Rechte).
    """
    root = resources.files("bonys_agents") / "vpn"
    files: list[tuple[str, bytes]] = []

    def walk(node, prefix: str) -> None:
        for child in sorted(node.iterdir(), key=lambda c: c.name):
            if child.name == "__pycache__" or child.name.endswith(".pyc"):
                continue
            if child.is_dir():
                walk(child, f"{prefix}{child.name}/")
            else:
                files.append((f"{prefix}{child.name}", child.read_bytes()))

    walk(root, "bonys_vpn/")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(fileobj=gz, mode="w") as tar:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return base64.encodebytes(buf.getvalue()).decode("ascii")


def _vpn_install() -> str:
    return r"""
apt-get install -y """ + VPN_PACKAGES + r"""
VPN_TMP="$(mktemp -d)"
base64 -d > "$VPN_TMP/bonys-vpn.tar.gz" <<'BONYS_VPN_PAYLOAD'
""" + vpn_payload() + r"""BONYS_VPN_PAYLOAD
tar -xzf "$VPN_TMP/bonys-vpn.tar.gz" -C "$VPN_TMP" --no-same-owner
# Helfer, Kommandozeile, Oberfläche, polkit (Benutzer ohne Passwort), Kill-Switch-Unit, Autostart des Tray-Symbols
python3 -I "$VPN_TMP/bonys_vpn/install.py" --variant agent --user "$AGENT_USER" --autostart-tray
rm -rf "$VPN_TMP"
systemctl daemon-reload
cp /usr/local/share/applications/io.github.bonys_agents.vpn.desktop "$DESKTOP_DIR/"
"""


VPN = AppSpec(
    id="vpn",
    name="WireGuard VPN (Bony's VPN)",
    description="Eigene WireGuard-Tunnel mit Kill-Switch und Tray-Symbol – Konfiguration bringst du selbst mit",
    default=False,
    weight=3.0,
    check="test -x /usr/local/bin/bonys-vpn-gui && test -x /usr/local/sbin/bonys-vpn-helper",
    launcher="io.github.bonys_agents.vpn.desktop",
    install=_vpn_install(),
)

HERMES = AppSpec(
    id="hermes",
    name="Hermes Agent",
    description="Selbstlernender KI-Agent von Nous Research (offizieller Installer)",
    category=AGENT,
    weight=12.0,
    check='PATH="$HOME/.local/bin:$PATH" command -v hermes',
    update='export PATH="$HOME/.local/bin:$PATH"; hermes update',
    launcher="hermes-agent.desktop",
    install=r"""
su - "$AGENT_USER" -c 'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash' </dev/null \
  || echo "WARNUNG: Hermes-Installation fehlgeschlagen – im Terminal erneut ausführen."
cat > /usr/local/bin/bonys-hermes <<'EOF'
#!/bin/bash
# Hermes Agent starten (fehlt er, mit dem offiziellen Installer nachholen)
export PATH="$HOME/.local/bin:$PATH"
command -v hermes >/dev/null || curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes
exec bash
EOF
chmod 755 /usr/local/bin/bonys-hermes
cat > /usr/share/applications/hermes-agent.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Hermes Agent
Comment=Hermes Agent im Terminal starten
Exec=/usr/local/bin/bonys-terminal "Hermes Agent" /usr/local/bin/bonys-hermes
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOF
cp /usr/share/applications/hermes-agent.desktop "$DESKTOP_DIR/"
""",
)

OPENCLAW = AppSpec(
    id="openclaw",
    name="OpenClaw",
    description="Persönlicher KI-Assistent mit Chat-Anbindung (Telegram, WhatsApp u. a.)",
    category=AGENT,
    weight=12.0,
    default=False,
    check='test -x "$HOME/.openclaw/bin/openclaw"',
    launcher="openclaw.desktop",
    # Eigener Updater; geht der nicht, aktualisiert der offizielle Installer (ohne Ersteinrichtung)
    update='export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"; openclaw update '
           '|| curl -fsSL https://openclaw.ai/install-cli.sh | bash -s -- --no-onboard',
    # Offizieller rootless Installer: Node.js und OpenClaw unter ~/.openclaw, ohne Ersteinrichtung.
    # Den Gateway-Dienst richtet erst „openclaw onboard“ ein – unser Starter verhindert das (--no-install-daemon).
    install=ENSURE_PATH + r"""
apt-get install -y xz-utils
su - "$AGENT_USER" -c 'curl -fsSL https://openclaw.ai/install-cli.sh | OPENCLAW_NO_ONBOARD=1 bash -s -- --no-onboard' </dev/null \
  || echo "WARNUNG: OpenClaw-Installation fehlgeschlagen – im Terminal erneut ausführen."
ensure_path .openclaw/bin
cat > /usr/local/bin/bonys-openclaw <<'EOF'
#!/bin/bash
# Erster Start: Ersteinrichtung (ohne dauerhaften Gateway-Dienst), danach OpenClaw selbst.
export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"
MARKER="$HOME/.openclaw/.bonys-eingerichtet"
if ! command -v openclaw >/dev/null; then
  echo "OpenClaw fehlt – installiere …"
  curl -fsSL https://openclaw.ai/install-cli.sh | bash -s -- --no-onboard
fi
if [ ! -f "$MARKER" ]; then
  echo "Ersteinrichtung von OpenClaw – Modell wählen und anmelden."
  openclaw onboard --no-install-daemon && mkdir -p "$HOME/.openclaw" && touch "$MARKER"
else
  openclaw
fi
exec bash
EOF
chmod 755 /usr/local/bin/bonys-openclaw
cat > /usr/share/applications/openclaw.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=OpenClaw
Comment=Persönlicher KI-Assistent im Terminal
Exec=/usr/local/bin/bonys-terminal OpenClaw /usr/local/bin/bonys-openclaw
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOF
cp /usr/share/applications/openclaw.desktop "$DESKTOP_DIR/"
""",
)

CLAUDE_CODE = AppSpec(
    id="claude-code",
    name="Claude Code",
    description="KI-Programmierhilfe von Anthropic im Terminal – Anmeldung mit eigenem Claude-Konto; "
                "kein Open Source, Nutzung braucht ein kostenpflichtiges Claude-Abo oder API-Guthaben",
    category=AGENT,
    weight=8.0,
    default=False,
    check='test -x "$HOME/.local/bin/claude"',
    launcher="claude-code.desktop",
    update='export PATH="$HOME/.local/bin:$PATH"; claude update',
    # Offizieller Installer, unverändert: legt ~/.local/bin/claude an. Keine Zugangsdaten –
    # angemeldet wird beim ersten Start über den offiziellen Weg im Browser des Agent-PCs.
    install=ENSURE_PATH + r"""
su - "$AGENT_USER" -c 'curl -fsSL https://claude.ai/install.sh | bash' </dev/null \
  || echo "WARNUNG: Claude-Code-Installation fehlgeschlagen – im Terminal erneut ausführen."
ensure_path .local/bin
install -d -o "$AGENT_USER" -g "$AGENT_USER" "$AGENT_HOME/Projekte"
cat > /usr/local/bin/bonys-claude-code <<'EOF'
#!/bin/bash
# Claude Code im Ordner ~/Projekte starten. Beim ersten Start meldest du dich selbst an.
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/Projekte" && cd "$HOME/Projekte" || exit 1
if ! command -v claude >/dev/null; then
  echo "Claude Code fehlt – installiere mit dem offiziellen Installer …"
  curl -fsSL https://claude.ai/install.sh | bash
fi
claude
exec bash
EOF
chmod 755 /usr/local/bin/bonys-claude-code
cat > /usr/share/applications/claude-code.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Claude Code
Comment=KI-Programmierhilfe im Terminal (Anmeldung mit eigenem Claude-Konto)
Exec=/usr/local/bin/bonys-terminal "Claude Code" /usr/local/bin/bonys-claude-code
Icon=utilities-terminal
Terminal=false
Categories=Development;
EOF
cp /usr/share/applications/claude-code.desktop "$DESKTOP_DIR/"
""",
)

APPS: dict[str, AppSpec] = {a.id: a for a in (BRAVE, TELEGRAM, XRDP, OBSIDIAN, VPN, HERMES, OPENCLAW,
                                               CLAUDE_CODE)}


def default_app_ids() -> list[str]:
    return [a.id for a in APPS.values() if a.default]


def ids_in_category(category: str) -> list[str]:
    return [a.id for a in APPS.values() if a.category == category]


def resolve(app_ids: list[str]) -> list[AppSpec]:
    """Apps zu den IDs – ohne Doppelte und immer in der festen Reihenfolge von ``APPS``."""
    app_ids = [i.strip() for i in app_ids if i.strip()]
    unknown = [i for i in app_ids if i not in APPS]
    if unknown:
        raise ValueError(f"Unbekannte App(s): {', '.join(unknown)}. Verfügbar: {', '.join(APPS)}")
    return [a for a in APPS.values() if a.id in app_ids]


def names(app_ids: list[str]) -> list[str]:
    """Anzeigenamen; unbekannte IDs (z. B. aus neueren Versionen) bleiben, wie sie sind."""
    return [APPS[i].name if i in APPS else i for i in app_ids]


# Sind dpkg/apt gerade beschäftigt (z. B. automatische Updates im Gast)? Geprüft werden dieselben
# fcntl-Sperren, die dpkg und apt selbst setzen – Prozessnamen wären unzuverlässig: der dauerhaft
# laufende Dienst „unattended-upgrade-shutdown“ heißt für pgrep genauso wie ein echtes Update.
APT_WAIT = r"""
bonys_apt_busy() {
  python3 - <<'PY' 2>/dev/null
import fcntl, sys
for path in ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock", "/var/lib/apt/lists/lock"):
    try:
        with open(path, "a") as f:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        sys.exit(0)
    except OSError:
        pass
sys.exit(1)
PY
}
bonys_apt_wait() {  # höchstens 20 Minuten
  for i in $(seq 0 239); do
    bonys_apt_busy || return 0
    [ $((i % 12)) -eq 0 ] && echo "Warte, bis eine andere Paketinstallation im Agent-PC fertig ist …"
    sleep 5
  done
}
"""

UPGRADE_DONE = "BONYS-UPGRADE-DONE"
REBOOT_MARKER = "BONYS-REBOOT-REQUIRED"


def _sq(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def upgrade_script(app_ids: list[str], username: str) -> str:
    """Skript (als root im Gast): System, Flatpaks und die installierten KI-Werkzeuge aktualisieren.

    Update-Befehle laufen nur für Werkzeuge, die laut Konfiguration installiert sind UND im Gast
    gefunden werden (``check``). Die Ausgabe geht zusätzlich auf die serielle Konsole – so zeigt
    die App den Fortschritt live. Am Ende: Hinweis, ob ein Neustart nötig ist.
    """
    lines = [
        "#!/usr/bin/env bash",
        "# Von Bony's Agents erzeugt – aktualisiert den Agent-PC.",
        "set -uo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        f"AGENT_USER={_sq(username)}",
        # serielle Konsole – dort zeigt die App die Ausgabe live (/dev/console: siehe cloudinit.GUEST_CONSOLE)
        'exec > >(tee -a /var/log/bonys-agents-upgrade.log /dev/console) 2>&1',
        "RC=0",
        'echo "== Bony\'s Agents: Agent-PC wird aktualisiert ($(date)) =="',
        APT_WAIT,
        "bonys_apt_wait",
        "dpkg --configure -a || true",
        'echo "== Systempakete (apt) =="',
        "apt-get -o DPkg::Lock::Timeout=600 update || RC=1",
        "apt-get -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "
        "-y full-upgrade || RC=1",
        "if command -v flatpak >/dev/null 2>&1; then",
        '  echo "== Flatpak-Programme =="',
        "  flatpak update -y --noninteractive || RC=1",
        "fi",
    ]
    for app in resolve([a for a in app_ids if a in APPS]):
        if not app.update:
            continue
        lines += [
            f"if su - \"$AGENT_USER\" -c {_sq(app.check)} </dev/null >/dev/null 2>&1; then",
            f'  echo "== {app.name} =="',
            f"  su - \"$AGENT_USER\" -c {_sq(app.update)} </dev/null || RC=1",
            "else",
            f'  echo "{app.name} ist nicht installiert – übersprungen."',
            "fi",
        ]
    lines += [
        'echo "== Anzeige-Treiber (Auflösung folgt dem Fenster) =="',
        "( set -e",
        screen.guest_setup_script(),
        ") || RC=1",
        "# Neustart nötig? Debian/Ubuntu-Markierung oder ein neuerer Kernel als der laufende",
        "NEWEST=$(ls -1 /boot/vmlinuz-* 2>/dev/null | sed 's|/boot/vmlinuz-||' | sort -V | tail -n1)",
        'if [ -f /var/run/reboot-required ] || { [ -n "$NEWEST" ] && [ "$NEWEST" != "$(uname -r)" ]; }; then',
        f'  echo "{REBOOT_MARKER}"',
        '  echo "Ein Neustart des Agent-PCs ist nötig, damit alle Updates wirken."',
        "fi",
        f'echo "{UPGRADE_DONE} $RC"',
        "exit $RC",
    ]
    return "\n".join(lines) + "\n"
