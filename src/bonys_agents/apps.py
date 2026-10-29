# SPDX-License-Identifier: GPL-3.0-or-later
"""Apps, die in einen Agent-PC installiert werden können.

Jede App ist ein kleines Bash-Snippet, das im Gast als root läuft.
Verfügbare Variablen: $AGENT_USER, $AGENT_HOME, $DESKTOP_DIR.
KI-Werkzeuge installieren sich selbst als $AGENT_USER (nie als root) und
bringen keinerlei Zugangsdaten mit – angemeldet wird beim ersten Start im Agent-PC.

Neue App hinzufügen = einen weiteren ``AppSpec`` in ``APPS`` eintragen.
Die Reihenfolge in ``APPS`` ist auch die Reihenfolge der Einrichtungsschritte – Abhängigkeiten
(``requires``) müssen deshalb vor den Apps stehen, die sie brauchen.
"""

from __future__ import annotations

from dataclasses import dataclass

from bonys_agents import desktops, screen

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
    # Andere Apps, die mitinstalliert werden (IDs, z. B. "docker")
    requires: tuple[str, ...] = ()
    # Nur Baustein für andere Apps: im Dialog keine eigene Auswahl, nur „wird mitinstalliert“
    hidden: bool = False
    # Darf in einer weitergegebenen Vorlage (.bonys) stecken? False = Lizenz erlaubt keine Weitergabe:
    # Vor dem Export wird die App mit ``uninstall`` (als root) aus der Kopie entfernt, der Empfänger
    # installiert sie aus der offiziellen Quelle neu.
    redistributable: bool = True
    uninstall: str = ""
    # Gibt die installierte Version aus (läuft als $AGENT_USER, erste Zeile zählt) – fürs Manifest
    version: str = ""
    # Nur für diese Architekturen des Agent-PCs ("x86_64", "aarch64"); leer = überall
    archs: tuple[str, ...] = ()
    # Nur für diese Grundsysteme des Agent-PCs ("debian", "kali"); leer = überall
    distros: tuple[str, ...] = ()

    def available(self, arch: str, distro: str = "debian") -> bool:
        return (not self.archs or arch in self.archs) and (not self.distros or distro in self.distros)


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


BRAVE_BASIC_MARKER = desktops.BRAVE_BASIC_MARKER

BRAVE = AppSpec(
    id="brave",
    name="Brave Browser",
    description="Datenschutzfreundlicher Browser (offizielles Brave-Repository)",
    check="command -v brave-browser",
    launcher="brave-browser.desktop",
    version="dpkg-query -W -f='${Version}' brave-browser",
    install=r"""
curl -fsSL --retry 3 --max-time 120 -o /usr/share/keyrings/brave-browser-archive-keyring.gpg \
  https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" \
  > /etc/apt/sources.list.d/brave-browser-release.list
apt-get update -y
apt-get install -y brave-browser
""" + r"""
# Ohne Schlüsselbund-Abfrage beim ersten Start (automatische Anmeldung hat keinen entsperrten Schlüsselbund):
# offizieller Chromium-Schalter --password-store=basic – wie bei Obsidian. Nur bei NEU installiertem Brave: Ein
# bestehendes Profil mit Passwörtern im Schlüsselbund könnte diese danach nicht mehr lesen. Die Markierung sagt
# anderen Startern (z. B. Mission Control), dass Brave hier so läuft. Der Eintrag in /usr/local/share hat
# Vorrang vor dem des Pakets und bleibt bei Brave-Updates erhalten.
mkdir -p /usr/local/share/applications """ + BRAVE_BASIC_MARKER.rsplit("/", 1)[0] + r"""
sed 's|^Exec=/usr/bin/brave-browser-stable|Exec=/usr/bin/brave-browser-stable --password-store=basic|' \
  /usr/share/applications/brave-browser.desktop > /usr/local/share/applications/brave-browser.desktop
grep -q -- '--password-store=basic' /usr/local/share/applications/brave-browser.desktop
touch """ + BRAVE_BASIC_MARKER + r"""
cp /usr/local/share/applications/brave-browser.desktop "$DESKTOP_DIR/"
""",
)

TELEGRAM = AppSpec(
    id="telegram",
    name="Telegram Desktop",
    description="Messenger über Flathub (x86_64 und ARM64)",
    check="flatpak info org.telegram.desktop",
    launcher="org.telegram.desktop.desktop",
    version="flatpak info org.telegram.desktop | sed -n 's/^ *Version: *//p'",
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
    version="dpkg-query -W -f='${Version}' xrdp",
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
    version="dpkg-query -W -f='${Version}' obsidian 2>/dev/null || readlink -f /opt/Obsidian/obsidian",
    # Kostenlos, aber kein Open Source: Weitergabe nur über die offizielle Quelle
    redistributable=False,
    uninstall=r"""
if dpkg-query -W -f='${Status}' obsidian 2>/dev/null | grep -q 'install ok installed'; then
  apt-get purge -y obsidian
fi
rm -rf /opt/Obsidian /usr/bin/obsidian /usr/share/applications/md.obsidian.Obsidian.desktop \
  /usr/local/share/applications/md.obsidian.Obsidian.desktop "$DESKTOP_DIR/md.obsidian.Obsidian.desktop" \
  "$AGENT_HOME/.config/obsidian"
""",
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
curl -fSL --retry 3 --max-time 1800 -o "$TMP/$FILE" "$URL"
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

# Bony's VPN ist ein eigenes Projekt (https://github.com/zappotex/bonys-vpn). Installiert werden die Pakete
# bonys-vpn und bonys-vpn-agentpc aus dem offiziellen Release: SHA256SUMS mit minisign-Signatur (derselbe
# Schlüssel wie bei Bony's Agents, die Signatur muss genau diese Version nennen), dann die SHA-256 jeder
# Datei, dann apt (zieht wireguard-tools, nftables, GTK usw. aus Debian). Danach kommen Updates über die
# APT-Paketquelle, die das Paket selbst einträgt („Agent-PC aktualisieren“). Die alte, eingebaute Fassung
# unter /usr/local (bis 0.14) räumt das Paket beim Installieren auf – /etc/wireguard bleibt, wie es ist.
VPN_RELEASE = "https://github.com/zappotex/bonys-vpn/releases/latest/download"
VPN_PACKAGES = ("bonys-vpn", "bonys-vpn-agentpc")
VPN_BLOCKED_HINT = ("HINWEIS: Der Kill-Switch von Bony's VPN ist an, aber kein Tunnel verbunden – ohne VPN hat der "
                    "Agent-PC kein Internet. Erst den Tunnel verbinden, dann aktualisieren.")


def _vpn_install() -> str:
    from bonys_agents import UPDATE_PUBLIC_KEY, vpnlink

    return r"""
VPN_BASE='""" + VPN_RELEASE + r"""'
VPN_KEY='""" + UPDATE_PUBLIC_KEY + r"""'
VPN_MIN='""" + vpnlink.MIN_VERSION + r"""'
# Kill-Switch an, aber kein Tunnel → kein Internet: gleich mit Hinweis abbrechen
if nft list table inet bonys_vpn >/dev/null 2>&1 && [ -z "$(wg show interfaces 2>/dev/null)" ]; then
  echo '""" + VPN_BLOCKED_HINT.replace("'", "'\"'\"'") + r"""'
  exit 1
fi
apt-get install -y minisign curl ca-certificates
VPN_TMP="$(mktemp -d)"
trap 'rm -rf "$VPN_TMP"' EXIT
vpn_get() { curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --max-time 300 -o "$VPN_TMP/$1" "$VPN_BASE/$1"; }
echo "Bony's VPN: lade die Prüfsummen aus dem offiziellen Release (github.com/zappotex/bonys-vpn) …"
vpn_get SHA256SUMS
vpn_get SHA256SUMS.minisig
# Signatur prüfen – -Q gibt nur den signierten Kommentar aus („Bony's VPN v1.0.1“)
VPN_COMMENT="$(minisign -V -Q -P "$VPN_KEY" -m "$VPN_TMP/SHA256SUMS" -x "$VPN_TMP/SHA256SUMS.minisig")" || {
  echo "FEHLER: Die Signatur der Prüfsummen von Bony's VPN ist ungültig – nichts installiert." >&2; exit 1; }
VPN_ARCH="$(dpkg --print-architecture)"
VPN_VER="$(sed -n 's/^[0-9a-f]\{64\}  bonys-vpn_\([0-9][0-9A-Za-z.+~-]*\)_\(all\|'"$VPN_ARCH"'\)\.deb$/\1/p' \
  "$VPN_TMP/SHA256SUMS" | head -n1)"
[ -n "$VPN_VER" ] || { echo "FEHLER: Kein Paket von Bony's VPN für $VPN_ARCH im Release." >&2; exit 1; }
case " $VPN_COMMENT " in
  *" v$VPN_VER "*) ;;
  *) echo "FEHLER: Die Signatur gehört zu einer anderen Version – nichts installiert." >&2; exit 1 ;;
esac
dpkg --compare-versions "$VPN_VER" ge "$VPN_MIN" || {
  echo "FEHLER: Bony's VPN $VPN_VER ist älter als $VPN_MIN." >&2; exit 1; }
VPN_DEBS=""
for p in """ + " ".join(VPN_PACKAGES) + r"""; do
  f="$(grep -oE "  ${p}_${VPN_VER}_(all|$VPN_ARCH)\.deb$" "$VPN_TMP/SHA256SUMS" | head -n1 | sed 's/^  //')"
  [ -n "$f" ] || { echo "FEHLER: $p fehlt im Release $VPN_VER." >&2; exit 1; }
  echo "Bony's VPN: lade $f …"
  vpn_get "$f"
  ( cd "$VPN_TMP" && grep -E "^[0-9a-f]{64}  ${f}$" SHA256SUMS | sha256sum -c --strict - ) || {
    echo "FEHLER: Prüfsumme von $f stimmt nicht – nichts installiert." >&2; exit 1; }
  VPN_DEBS="$VPN_DEBS $VPN_TMP/$f"
done
echo "Bony's VPN $VPN_VER: Signatur und Prüfsummen in Ordnung, installiere …"
# Tray-Symbol der alten Fassung (/usr/local) merken – seine Dateien verschwinden gleich. [b]/[l]: damit das
# Muster nicht dieses Skript selbst trifft (es steht in dessen Befehlszeile).
VPN_TRAYS="$(pgrep -f '/usr/local/[b]in/bonys-vpn-gui|/usr/local/[l]ib/bonys-vpn/' 2>/dev/null | grep -vx "$$" || true)"
chmod 755 "$VPN_TMP"; chmod 644 "$VPN_TMP"/*.deb   # apt liest lokale Pakete als Benutzer _apt
# shellcheck disable=SC2086
apt-get install -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold $VPN_DEBS
# Bony's VPN ohne Passwort (polkit über die Gruppe bonys-vpn)
usermod -a -G bonys-vpn "$AGENT_USER"
# Verknüpfung auf dem Schreibtisch – die der alten Fassung zeigte auf /usr/local
rm -f "$DESKTOP_DIR/io.github.bonys_agents.vpn.desktop"
cp /usr/share/applications/bonys-vpn.desktop "$DESKTOP_DIR/"
# Altes Tray-Symbol durch das neue ersetzen – in derselben Sitzung (Umgebung des alten Prozesses)
for pid in $VPN_TRAYS; do
  [ -r "/proc/$pid/environ" ] || continue
  u="$(stat -c %U "/proc/$pid")"
  envs="$(tr '\0' '\n' < "/proc/$pid/environ" | grep -E \
    '^(DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|XDG_CURRENT_DESKTOP|LANG|HOME)=' || true)"
  kill "$pid" 2>/dev/null || true
  # shellcheck disable=SC2086
  runuser -u "$u" -- env -i PATH=/usr/bin:/bin $envs setsid -f /usr/bin/bonys-vpn-gui --tray \
    </dev/null >/dev/null 2>&1 || true
done
"""


VPN = AppSpec(
    id="vpn",
    name="WireGuard VPN (Bony's VPN)",
    description="Eigene WireGuard-Tunnel mit Kill-Switch und Tray-Symbol – Konfiguration bringst du selbst mit",
    default=False,
    weight=3.0,
    check="test -x /usr/bin/bonys-vpn-gui && test -x /usr/sbin/bonys-vpn-helper && id -nG | grep -qw bonys-vpn",
    launcher="bonys-vpn.desktop",
    version="dpkg-query -W -f='${Version}' bonys-vpn",
    install=_vpn_install(),
)

# Docker aus der offiziellen Paketquelle von Docker (nicht docker.io aus Debian). Der Schlüssel wird gegen
# den veröffentlichten Fingerabdruck geprüft, bevor apt ihm vertraut. Alte Pakete aus Debian (docker.io,
# docker-compose …) stören die offiziellen und werden vorher entfernt – /var/lib/docker bleibt dabei.
DOCKER_KEY_URL = "https://download.docker.com/linux/debian/gpg"
DOCKER_KEY_FINGERPRINT = "9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
DOCKER_PACKAGES = ("docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin")

DOCKER = AppSpec(
    id="docker",
    name="Docker",
    description="Container-Laufzeit aus der offiziellen Docker-Paketquelle (für Mission Control)",
    default=False,
    hidden=True,
    weight=8.0,
    # als Agent-Benutzer: Gruppe docker wirkt (su - meldet neu an), Dienst und Compose-Plugin da
    check="docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1",
    version="dpkg-query -W -f='${Version}' docker-ce",
    install=r"""
apt-get install -y ca-certificates curl gnupg
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in amd64|arm64) ;; *) echo "Docker gibt es hier nur für amd64 und arm64 (gefunden: $ARCH)." >&2; exit 1 ;; esac
CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
# Kali (rolling) hat bei Docker keinen eigenen Zweig – wie in der Kali-Anleitung den von Debian stable nehmen
[ "$(. /etc/os-release && echo "$ID")" = kali ] && CODENAME=trixie
TMP="$(mktemp -d)"
curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --max-time 120 -o "$TMP/docker.asc" '""" + DOCKER_KEY_URL + r"""'
FPR="$(gpg --batch --show-keys --with-colons "$TMP/docker.asc" | awk -F: '$1 == "fpr" { print $10; exit }')"
if [ "$FPR" != '""" + DOCKER_KEY_FINGERPRINT + r"""' ]; then
  echo "FEHLER: Der Schlüssel der Docker-Paketquelle hat einen unerwarteten Fingerabdruck – nichts installiert." >&2
  exit 1
fi
echo "Docker-Paketquelle: Schlüssel geprüft (Fingerabdruck $FPR)."
install -d -m 0755 /etc/apt/keyrings
install -m 0644 "$TMP/docker.asc" /etc/apt/keyrings/docker.asc
rm -rf "$TMP"
echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
OLD=""
for p in docker.io docker-doc docker-compose docker-cli podman-docker containerd runc; do
  dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' && OLD="$OLD $p"
done
if [ -n "$OLD" ]; then
  echo "Entferne Docker-Pakete aus Debian:$OLD (Daten in /var/lib/docker bleiben)"
  # shellcheck disable=SC2086
  apt-get remove -y $OLD
fi
apt-get update -y
apt-get install -y """ + " ".join(DOCKER_PACKAGES) + r"""
systemctl enable --now containerd.service docker.service
# Im Agent-PC vertretbar: Er ist vom Host abgeschottet, der Agent-Benutzer hat ohnehin sudo.
usermod -a -G docker "$AGENT_USER"
docker --version
docker compose version
""",
)


def _mission_control():
    from bonys_agents import mission_control

    return mission_control.app_spec()


def _n8n():
    from bonys_agents import n8n

    return n8n.app_spec()


def _agenten_apps():
    from bonys_agents import agenten_apps

    return agenten_apps.app_spec()


# GNOME Software mit Flathub: Programme wie GIMP per Klick (Flatpak, ohne Passwort für die Gruppe sudo).
# Offline-Fix: NetworkManager (kommt mit dem Desktop) verwaltet die Netzwerkkarte nicht – das macht
# systemd-networkd aus cloud-init/netplan. GIO fragt aber NetworkManager, hält den Agent-PC deshalb für offline,
# und GNOME Software zeigt keine Programme. Die offizielle GIO-Variable GIO_USE_NETWORK_MONITOR=netlink fragt
# stattdessen den Kernel (wirkt ab der nächsten Anmeldung). Automatische Updates von GNOME Software aus: Die macht
# Bony's Agents („Agent-PC aktualisieren“), zwei gleichzeitige apt-Läufe würden sich sperren.
SOFTWARE_CENTER = AppSpec(
    id="software-center",
    name="Software-Center",
    description="Programme wie GIMP oder Inkscape per Klick installieren (GNOME Software mit Flathub)",
    weight=4.0,
    check="command -v gnome-software && flatpak remotes --columns=name | grep -qx flathub",
    launcher="org.gnome.Software.desktop",
    version="dpkg-query -W -f='${Version}' gnome-software",
    install=r"""
apt-get install -y gnome-software gnome-software-plugin-flatpak flatpak
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
touch /etc/environment
grep -q '^GIO_USE_NETWORK_MONITOR=' /etc/environment \
  || printf '# Bony'"'"'s Agents: Netzwerk-Status vom Kernel statt von NetworkManager (Software-Center)\nGIO_USE_NETWORK_MONITOR=netlink\n' \
     >> /etc/environment
cat > /usr/share/glib-2.0/schemas/90_bonys-agents-software.gschema.override <<'EOF'
# Von Bony's Agents: Updates macht „Agent-PC aktualisieren“ – GNOME Software lädt nichts selbst
[org.gnome.software]
download-updates=false
download-updates-notify=false
EOF
glib-compile-schemas /usr/share/glib-2.0/schemas
cp /usr/share/applications/org.gnome.Software.desktop "$DESKTOP_DIR/"
""",
)


# Firefox-Sandbox des Tor Browsers: Das AppArmor-Profil von torbrowser-launcher 0.3.7 (Debian 13) verbietet
# Benutzer-Namensräume – der Tor Browser warnt dann „Einige Sicherheitsfunktionen … weniger Schutz“. Ab 0.3.9 steht
# „userns,“ im Profil selbst. Sonst kommt die Zeile in die lokale Ergänzung (überlebt Paket-Updates) – nur mit
# AppArmor ab 4 (ältere kennen die Regel nicht); lässt sich das Profil damit nicht laden, wird sie wieder entfernt.
# Bony entschied am 28.10.2026 für diese Korrektur (betrifft nur den Tor Browser und nur den Agent-PC).
TOR_APPARMOR = r"""
P=/etc/apparmor.d/torbrowser.Browser.firefox
L=/etc/apparmor.d/local/torbrowser.Browser.firefox
if [ -f "$P" ] && ! grep -qE '^[[:space:]]*userns,' "$P" && command -v apparmor_parser >/dev/null 2>&1; then
  AA="$(apparmor_parser --version 2>/dev/null | sed -n 's/.*version \([0-9][0-9]*\)\..*/\1/p' | head -n1)"
  if [ "${AA:-0}" -ge 4 ] && ! grep -qxF 'userns,' "$L" 2>/dev/null; then
    mkdir -p /etc/apparmor.d/local
    printf '%s\n' '# Bonys Agents: Firefox-Sandbox des Tor Browsers braucht Benutzer-Namensraeume' 'userns,' >> "$L"
    if apparmor_parser -r "$P" >/dev/null 2>&1; then
      echo "Tor Browser: volle Firefox-Sandbox eingeschaltet (AppArmor userns)."
    else
      sed -i '/^# Bonys Agents: Firefox-Sandbox des Tor Browsers/d; /^userns,$/d' "$L"
      apparmor_parser -r "$P" >/dev/null 2>&1 || true
      echo "Hinweis: Die AppArmor-Korrektur für den Tor Browser ließ sich nicht laden – unverändert." >&2
    fi
  fi
fi
"""


# Tor Browser: Debian-Paket torbrowser-launcher (Komponente „contrib“, wird dafür eingeschaltet). Es lädt beim ersten
# Start den offiziellen Tor Browser von torproject.org und prüft dessen Signatur; Updates macht der Tor Browser selbst.
# Das Tor Project baut für Linux nur x86_64 (kein ARM64) – daher nicht auf Macs mit Apple-Chip.
TOR_BROWSER = AppSpec(
    id="tor-browser",
    name="Tor Browser",
    description="Anonymer surfen über das Tor-Netz (offizieller Tor Browser, Signatur geprüft) – nur x86_64",
    default=False,
    weight=3.0,
    archs=("x86_64",),
    check="command -v torbrowser-launcher",
    launcher="torbrowser.desktop",
    version="dpkg-query -W -f='${Version}' torbrowser-launcher",
    install=r"""
if [ "$(dpkg --print-architecture)" != amd64 ]; then
  echo "Den Tor Browser gibt es für Linux nur auf x86_64 (amd64)." >&2; exit 1
fi
for f in /etc/apt/sources.list.d/debian.sources; do
  [ -f "$f" ] && sed -i -E '/^Components:/{/contrib/!s/$/ contrib/}' "$f"
done
if [ -f /etc/apt/sources.list ]; then
  sed -i -E '/^deb .*debian/{/contrib/!s/ main( |$)/ main contrib\1/}' /etc/apt/sources.list
fi
apt-get update
apt-get install -y torbrowser-launcher
# Debian 13: torbrowser.desktop, neuere Fassungen (z. B. unter Kali): org.torproject.torbrowser-launcher.desktop
for d in torbrowser.desktop org.torproject.torbrowser-launcher.desktop; do
  if [ -f "/usr/share/applications/$d" ]; then cp "/usr/share/applications/$d" "$DESKTOP_DIR/"; break; fi
done
""" + TOR_APPARMOR,
)


# Kali-Werkzeuge: die zehn bekanntesten (nmap, Metasploit, Burp Suite, Wireshark, John, Hydra, sqlmap, aircrack-ng,
# NetExec, Responder) aus den Kali-Paketquellen, dazu das Kali-Menü (sonst stehen sie nicht im Startmenü).
# Wireshark darf der Agent-Benutzer ohne root mitschneiden (wirkt ab der nächsten Anmeldung).
KALI_TOOLS = AppSpec(
    id="kali-tools",
    name="Kali-Werkzeuge",
    description="Die zehn bekanntesten Kali-Werkzeuge (nmap, Metasploit, Burp Suite, Wireshark …) mit Kali-Menü – "
                "nur unter Kali Linux",
    default=False,
    weight=25.0,
    distros=("kali",),
    check="command -v nmap && command -v msfconsole",
    version="dpkg-query -W -f='${Version}' kali-tools-top10",
    install=r"""
echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections
apt-get install -y kali-tools-top10 kali-menu
usermod -a -G wireshark "$AGENT_USER"
""",
)


HERMES = AppSpec(
    id="hermes",
    name="Hermes Agent",
    description="Selbstlernender KI-Agent von Nous Research (offizieller Installer)",
    category=AGENT,
    weight=12.0,
    check='PATH="$HOME/.local/bin:$PATH" command -v hermes',
    update='export PATH="$HOME/.local/bin:$PATH"; hermes update',
    version='PATH="$HOME/.local/bin:$PATH" hermes --version',
    launcher="hermes-agent.desktop",
    install=r"""
su - "$AGENT_USER" -c 'curl -fsSL --retry 3 --max-time 120 https://hermes-agent.nousresearch.com/install.sh | bash' </dev/null \
  || echo "WARNUNG: Hermes-Installation fehlgeschlagen – im Terminal erneut ausführen."
cat > /usr/local/bin/bonys-hermes <<'EOF'
#!/bin/bash
# Hermes Agent starten (fehlt er, mit dem offiziellen Installer nachholen)
export PATH="$HOME/.local/bin:$PATH"
command -v hermes >/dev/null || curl -fsSL --retry 3 --max-time 120 https://hermes-agent.nousresearch.com/install.sh | bash
hermes
exec bash
EOF
chmod 755 /usr/local/bin/bonys-hermes
# Sprache: Sprachpakete, Erkennung auf Deutsch – Hermes stellt sonst Englisch ein und übersetzt. Modell „base“ ist
# schnell genug. Stimme lokal mit Piper (Thorsten), als Alternative Edge (Katja, über das Internet). Beides wird vorab
# geladen. Die Verknüpfung „Hermes Agent (Sprache)“ schaltet Sprachmodus und Vorlesen gleich ein (sonst im Chat
# „/voice on“); gesprochen wird mit Strg+B.
cat > /usr/local/bin/bonys-hermes-sprachmodell <<'EOF'
#!/bin/bash
# Sprachmodell und Stimme von Hermes vorab laden (sonst dauert das erste Sprechen bzw. Vorlesen rund 30 s)
H="$HOME/.hermes/hermes-agent/.hermes/bin/hermes"
[ -x "$H" ] || exit 0
python3 - "$H" <<'PY'
import json, subprocess, sys
cmd = json.loads(subprocess.run([sys.argv[1], "--print-runtime-command"], capture_output=True, text=True,
                                check=True).stdout)
start = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
if len(cmd) < 4 or start not in cmd[3]:
    sys.exit("Startbefehl von Hermes unbekannt – Sprachmodell und Stimme laden beim ersten Gebrauch.")
laden = ("from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); "
         "sys.argv = ['piper', 'de_DE-thorsten-medium', '--download-dir', "
         "os.path.expanduser('~/.hermes/cache/piper-voices')]; runpy.run_module('piper.download_voices', "
         "run_name='__main__')")
subprocess.run(cmd[:3] + [cmd[3].replace(start, laden)], check=True)
PY
EOF
chmod 755 /usr/local/bin/bonys-hermes-sprachmodell
cat > /usr/local/bin/bonys-hermes-sprache <<'EOF'
#!/bin/bash
# Hermes Agent mit Sprache starten: Sprachmodus und Vorlesen sind gleich an – Strg+B drücken, sprechen, Strg+B.
# Optional ein Profil: bonys-hermes-sprache atlas
export PATH="$HOME/.local/bin:$PATH"
command -v hermes >/dev/null || exec /usr/local/bin/bonys-hermes
S="hermes-sprache-$$"
P=(); [ -n "${1:-}" ] && P=(-p "$1")
hermes "${P[@]}" config set voice.auto_tts true >/dev/null 2>&1
# tmux nur als Hülle, um „/voice on“ einzugeben: kein Präfix (Strg+B gehört Hermes), keine Statuszeile
tmux -f /dev/null new-session -d -s "$S" -x "$(tput cols 2>/dev/null || echo 120)" -y "$(tput lines 2>/dev/null || echo 36)" \
  "hermes ${P[*]}; exec bash" \; set -g prefix None \; set -g status off \; set -g mouse off \; unbind C-b
for _ in $(seq 90); do
  tmux capture-pane -p -t "$S" 2>/dev/null | grep -q "Welcome to Hermes Agent" && break
  sleep 1
done
sleep 1
# Text und Enter getrennt schicken – kommen sie zusammen, hält Hermes sie für eingefügten Text (Enter = neue Zeile)
tmux send-keys -t "$S" -l "/voice on"
sleep 1
tmux send-keys -t "$S" Enter
exec tmux attach -t "$S"
EOF
chmod 755 /usr/local/bin/bonys-hermes-sprache
apt-get install -y libportaudio2 ffmpeg tmux
su - "$AGENT_USER" -c 'export PATH="$HOME/.local/bin:$PATH"; hermes pm install --extra voice --extra piper --extra edge-tts && hermes config set stt.language de && hermes config set stt.local.language de && hermes config set stt.local.model base && hermes config set tts.provider piper && hermes config set tts.piper.voice de_DE-thorsten-medium && hermes config set tts.edge.voice de-DE-KatjaNeural && hermes config set voice.auto_tts true && /usr/local/bin/bonys-hermes-sprachmodell' </dev/null \
  || echo "WARNUNG: Spracheingabe für Hermes nicht vollständig eingerichtet – im Terminal „hermes pm install --extra voice“."
# Mission Control schon da (wird vor Hermes installiert): Sprachdienst für „Sprechen“ und Vorlesen einschalten
if [ -x /opt/bonys-mission-control/scripts/hermes-team.sh ]; then
  /opt/bonys-mission-control/scripts/hermes-team.sh voice on --user "$AGENT_USER" \
    || echo "WARNUNG: Sprachdienst für Mission Control nicht eingeschaltet – später mit „hermes-team.sh voice on“."
fi
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
cat > /usr/share/applications/hermes-agent-sprache.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Hermes Agent (Sprache)
Comment=Hermes Agent mit Spracheingabe und gesprochenen Antworten (Strg+B zum Sprechen)
Exec=/usr/local/bin/bonys-terminal "Hermes Agent (Sprache)" /usr/local/bin/bonys-hermes-sprache
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
EOF
cp /usr/share/applications/hermes-agent.desktop /usr/share/applications/hermes-agent-sprache.desktop "$DESKTOP_DIR/"
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
    version='"$HOME/.openclaw/bin/openclaw" --version',
    launcher="openclaw.desktop",
    # Eigener Updater; geht der nicht, aktualisiert der offizielle Installer (ohne Ersteinrichtung)
    update='export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"; openclaw update '
           '|| curl -fsSL --retry 3 --max-time 120 https://openclaw.ai/install-cli.sh | bash -s -- --no-onboard',
    # Offizieller rootless Installer: Node.js und OpenClaw unter ~/.openclaw, ohne Ersteinrichtung.
    # Den Gateway-Dienst richtet erst „openclaw onboard“ ein – unser Starter verhindert das (--no-install-daemon).
    install=ENSURE_PATH + r"""
apt-get install -y xz-utils
su - "$AGENT_USER" -c 'curl -fsSL --retry 3 --max-time 120 https://openclaw.ai/install-cli.sh | OPENCLAW_NO_ONBOARD=1 bash -s -- --no-onboard' </dev/null \
  || echo "WARNUNG: OpenClaw-Installation fehlgeschlagen – im Terminal erneut ausführen."
ensure_path .openclaw/bin
cat > /usr/local/bin/bonys-openclaw <<'EOF'
#!/bin/bash
# Erster Start: Ersteinrichtung (ohne dauerhaften Gateway-Dienst), danach OpenClaw selbst.
export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"
MARKER="$HOME/.openclaw/.bonys-eingerichtet"
if ! command -v openclaw >/dev/null; then
  echo "OpenClaw fehlt – installiere …"
  curl -fsSL --retry 3 --max-time 120 https://openclaw.ai/install-cli.sh | bash -s -- --no-onboard
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
    version='"$HOME/.local/bin/claude" --version',
    # Kein Open Source, Lizenz von Anthropic: nur über den offiziellen Installer
    redistributable=False,
    uninstall=r"""
rm -rf "$AGENT_HOME/.local/bin/claude" "$AGENT_HOME/.local/share/claude" "$AGENT_HOME/.local/state/claude" \
  "$AGENT_HOME/.cache/claude" "$AGENT_HOME/.claude" "$AGENT_HOME/.claude.json" "$AGENT_HOME/.claude.json.backup" \
  /usr/local/bin/bonys-claude-code /usr/share/applications/claude-code.desktop "$DESKTOP_DIR/claude-code.desktop"
""",
    # Offizieller Installer, unverändert: legt ~/.local/bin/claude an. Keine Zugangsdaten –
    # angemeldet wird beim ersten Start über den offiziellen Weg im Browser des Agent-PCs.
    install=ENSURE_PATH + r"""
su - "$AGENT_USER" -c 'curl -fsSL --retry 3 --max-time 120 https://claude.ai/install.sh | bash' </dev/null \
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
  curl -fsSL --retry 3 --max-time 120 https://claude.ai/install.sh | bash
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

MISSION_CONTROL = _mission_control()
N8N = _n8n()
# Nach n8n: Die Seite zeigt unter „Schon dabei“ nur, was wirklich installiert ist
AGENTEN_APPS = _agenten_apps()

APPS: dict[str, AppSpec] = {a.id: a for a in (BRAVE, TELEGRAM, XRDP, OBSIDIAN, SOFTWARE_CENTER, TOR_BROWSER, KALI_TOOLS, VPN, DOCKER,
                                               MISSION_CONTROL, N8N, HERMES, OPENCLAW, CLAUDE_CODE,
                                               AGENTEN_APPS)}


def not_redistributable(app_ids: list[str] | tuple[str, ...]) -> list[str]:
    """Die Apps aus ``app_ids``, die nicht in einer weitergegebenen Vorlage stecken dürfen."""
    return [i for i in app_ids if i in APPS and not APPS[i].redistributable]


def default_app_ids(distro: str = "debian") -> list[str]:
    """Vorausgewählte Apps – unter Kali kommen dessen eigene dazu (z. B. die Kali-Werkzeuge)."""
    from bonys_agents import distros

    extra = distros.get(distro).default_apps
    return [a.id for a in APPS.values() if (a.default or a.id in extra) and (not a.distros or distro in a.distros)]


def ids_in_category(category: str) -> list[str]:
    return [a.id for a in APPS.values() if a.category == category]


def visible_ids() -> list[str]:
    """Apps, die man selbst auswählen kann (ohne reine Bausteine wie Docker)."""
    return [a.id for a in APPS.values() if not a.hidden]


def dependencies(app_ids: list[str] | tuple[str, ...]) -> list[str]:
    """Alle Apps, die für ``app_ids`` mitinstalliert werden (auch indirekt), ohne die gewählten selbst."""
    wanted = [i for i in app_ids if i in APPS]
    seen: set[str] = set(wanted)
    todo = list(wanted)
    while todo:
        for dep in APPS[todo.pop()].requires:
            if dep not in seen:
                seen.add(dep)
                todo.append(dep)
    return [i for i in APPS if i in seen and i not in wanted]


def with_dependencies(app_ids: list[str] | tuple[str, ...]) -> list[str]:
    """IDs samt Abhängigkeiten, in der festen Reihenfolge von ``APPS`` (unbekannte IDs bleiben hinten)."""
    known = set(app_ids) | set(dependencies(app_ids))
    return [i for i in APPS if i in known] + [i for i in app_ids if i not in APPS]


def required_by(app_id: str, app_ids: list[str] | tuple[str, ...]) -> list[str]:
    """Welche der ``app_ids`` brauchen ``app_id`` (direkt oder indirekt)?"""
    return [i for i in app_ids if i != app_id and i in APPS and app_id in dependencies([i])]


def check_arch(app_ids: list[str] | tuple[str, ...], arch: str, distro: str = "debian") -> None:
    """Fehler, wenn eine der Apps (samt Abhängigkeiten) auf dieser Architektur bzw. diesem Grundsystem nicht geht."""
    from bonys_agents import distros

    deps = [APPS[i] for i in with_dependencies(list(app_ids)) if i in APPS]
    bad_arch = [a.name for a in deps if not a.available(arch, distro) and a.archs and arch not in a.archs]
    if bad_arch:
        raise ValueError(f"Nicht verfügbar auf {arch}: {', '.join(bad_arch)}.")
    bad_distro = [a.name for a in deps if not a.available(arch, distro)]
    if bad_distro:
        raise ValueError(f"Nicht verfügbar unter {distros.name(distro)}: {', '.join(bad_distro)}.")


def resolve(app_ids: list[str]) -> list[AppSpec]:
    """Apps zu den IDs samt Abhängigkeiten – ohne Doppelte und immer in der festen Reihenfolge von ``APPS``."""
    app_ids = [i.strip() for i in app_ids if i.strip()]
    unknown = [i for i in app_ids if i not in APPS]
    if unknown:
        raise ValueError(f"Unbekannte App(s): {', '.join(unknown)}. Verfügbar: {', '.join(visible_ids())}")
    return [APPS[i] for i in with_dependencies(app_ids)]


def names(app_ids: list[str]) -> list[str]:
    """Anzeigenamen; unbekannte IDs (z. B. aus neueren Versionen) bleiben, wie sie sind."""
    return [APPS[i].name if i in APPS else i for i in app_ids]


def labels(app_ids: list[str], app_info: dict | None = None) -> list[str]:
    """Anzeigenamen, mit Version, wenn eine bekannt ist (z. B. „Mission Control 0.1.0“)."""
    out = []
    for app_id, name in zip(app_ids, names(app_ids), strict=True):
        version = ((app_info or {}).get(app_id) or {}).get("version")
        out.append(f"{name} {version}" if version else name)
    return out


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
        # Bony's VPN: Kill-Switch an, aber kein Tunnel → kein Internet, apt scheitert gleich
        "if nft list table inet bonys_vpn >/dev/null 2>&1 && [ -z \"$(wg show interfaces 2>/dev/null)\" ]; then",
        f'  echo "{VPN_BLOCKED_HINT}"',
        "  RC=1",
        "fi",
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
    if "tor-browser" in app_ids:   # auch schon vorhandene Agent-PCs bekommen die volle Firefox-Sandbox
        lines += ["if command -v torbrowser-launcher >/dev/null 2>&1; then", TOR_APPARMOR, "fi"]
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
