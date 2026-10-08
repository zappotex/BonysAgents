# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop-Umgebungen, aus denen beim Erstellen eines Agent-PCs gewählt werden kann.

Jeder Desktop ist ein ``DesktopSpec`` – wie die Apps in ``apps.py``. Neuen Desktop ergänzen =
einen weiteren Eintrag in ``DESKTOPS``.

Gemeinsam für alle (geprüft mit Debian 13):

- **Anmeldemanager: LightDM** mit automatischer Anmeldung. Er startet jede X11-Sitzung und führt
  beim Start jedes X-Servers unser Skript zur Bildschirmgröße aus. KDE empfiehlt SDDM – wird nicht
  installiert, LightDM startet Plasma (X11) zuverlässig.
  **Ausnahme GNOME: GDM.** ``gnome-core`` hängt ohnehin fest von GDM ab, und unter LightDM schaltet
  GNOME 48 die Bildschirmsperre ab („erfordert den GNOME Display-Manager“). GDM läuft mit
  ``WaylandEnable=false`` und automatischer Anmeldung in ``gnome-xorg``.
- **X11-Sitzungen**, auch bei KDE (``plasmax11``) und GNOME (``gnome-xorg``): xrdp, die
  Auflösungsanpassung per xrandr und spice-vdagent brauchen X11.
- **Ausschaltknopf:** systemd-logind fährt sofort herunter (``PowerKeyIgnoreInhibited``), auch wenn
  der Desktop die Taste für sich beansprucht. Wo es eine Desktop-Einstellung gibt, steht sie zusätzlich
  auf „Herunterfahren“ bzw. „nichts tun“, damit kein Dialog aufblitzt.
- **Terminal für Verknüpfungen:** ``/usr/local/bin/bonys-terminal TITEL BEFEHL …`` startet das
  Terminal des Desktops (gnome-terminal, xfce4-terminal, konsole, mate-terminal, qterminal).
- **Bei jeder Anmeldung** (``bonys-desktop-login``): Programm-Symbole auf dem Schreibtisch als
  vertrauenswürdig markieren, bei GNOME ins Dash aufnehmen; einmalig das Hintergrundbild bei Desktops,
  die es nur in der laufenden Sitzung setzen lassen (Xfce als Rückfallebene, KDE Plasma).
"""

from __future__ import annotations

from dataclasses import dataclass

from bonys_agents import screen

DEFAULT = "cinnamon"
CONF_DIR = "/etc/bonys-agents"
DESKTOP_ENV = f"{CONF_DIR}/desktop.env"
FAVORITES = f"{CONF_DIR}/favorites"
TERMINAL_SCRIPT = "/usr/local/bin/bonys-terminal"
LOGIN_SCRIPT = "/usr/local/bin/bonys-desktop-login"
LOGIN_AUTOSTART = "/etc/xdg/autostart/bonys-desktop-login.desktop"
AUTOLOGIN_CONF = "/etc/lightdm/lightdm.conf.d/50-bonys-autologin.conf"
GDM_CONF = "/etc/gdm3/daemon.conf"
GREETER_DROPIN = "/etc/lightdm/lightdm-gtk-greeter.conf.d/50-bonys-agents.conf"
LOGIND_DROPIN = "/etc/systemd/logind.conf.d/50-bonys-powerkey.conf"
WALLPAPER_BORDER = "#0b1117"  # Randfarbe, wo das skalierte Bild den Bildschirm nicht ganz füllt
# Pakete für jeden Desktop: Anmeldung, Schriften, Ton, Gast-Werkzeuge, Hintergrundbild-Umwandlung
COMMON_PACKAGES = ("xdg-user-dirs fonts-noto-core fonts-noto-color-emoji pipewire-pulse "
                   "spice-vdagent qemu-guest-agent x11-xserver-utils python3-gi gir1.2-gdkpixbuf-2.0 gvfs dbus-x11")


@dataclass(frozen=True)
class DesktopSpec:
    id: str
    name: str
    description: str
    packages: str            # zusätzlich zu COMMON_PACKAGES; „paket-“ = nicht installieren
    xsession: str            # Name der X11-Sitzung (/usr/share/xsessions/<xsession>.desktop)
    session_cmd: str         # für xrdp (startwm.sh)
    xdg_desktop: str         # XDG_CURRENT_DESKTOP
    terminal: str
    min_ram_mb: int          # empfohlener Arbeitsspeicher
    weight: float            # Dauer des Installationsschritts relativ zu den Apps (Download-Größe)
    extra: str = ""          # Bash: eigene Einstellungen (läuft als root, $IMG = Hintergrundbild)
    display_manager: str = "lightdm"   # „lightdm“ oder „gdm3“


# Pakete des Anmeldemanagers
DM_PACKAGES = {"lightdm": "lightdm lightdm-gtk-greeter", "gdm3": "gdm3"}


def _xfce_desktop_xml() -> str:
    """xfconf-Voreinstellung für den Benutzer: Hintergrund skaliert, Rand in der App-Farbe."""
    r, g, b = (int(WALLPAPER_BORDER[i:i + 2], 16) / 255 for i in (1, 3, 5))
    rgba = "".join(f'<value type="double" value="{v:.4f}"/>' for v in (r, g, b, 1.0))
    monitors = ""
    for mon in ("monitorVirtual-1", "monitorVirtual1", "monitor0", "monitorVGA-1"):
        ws = "".join(
            f'<property name="workspace{w}" type="empty">'
            '<property name="color-style" type="int" value="0"/>'
            '<property name="image-style" type="int" value="4"/>'
            '<property name="last-image" type="string" value="IMGPATH"/>'
            f'<property name="rgba1" type="array">{rgba}</property></property>'
            for w in range(4))
        monitors += f'<property name="{mon}" type="empty">{ws}</property>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<channel name="xfce4-desktop" version="1.0">'
            f'<property name="backdrop" type="empty"><property name="screen0" type="empty">{monitors}'
            "</property></property></channel>\n")


_XFCE_EXTRA = f"""
# Hintergrund: Voreinstellung für den Benutzer (die Anmeldung setzt es zusätzlich für jeden Bildschirm)
D="$AGENT_HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
mkdir -p "$D"
[ -f "$D/xfce4-desktop.xml" ] || cat > "$D/xfce4-desktop.xml" <<'BONYS_XFCE'
{_xfce_desktop_xml()}BONYS_XFCE
sed -i "s|IMGPATH|$IMG|g" "$D/xfce4-desktop.xml"
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_HOME/.config"
"""

_KDE_EXTRA = r"""
# Ausschaltknopf: Herunterfahren statt Abmelde-Dialog (8 = Herunterfahren)
cat > /etc/xdg/powerdevilrc <<'BONYS_KDE'
[AC][SuspendAndShutdown]
PowerButtonAction=8

[Battery][SuspendAndShutdown]
PowerButtonAction=8

[LowBattery][SuspendAndShutdown]
PowerButtonAction=8
BONYS_KDE
# Begrüßungs-Assistent nicht bei jedem neuen Agent-PC zeigen: er startet über ein kded-Modul –
# Modul nicht laden und systemweit als „schon gesehen“ markieren
cat > /etc/xdg/kded6rc <<'BONYS_KDE'
[Module-plasma-welcome]
autoload=false
BONYS_KDE
printf '[General]\nLastSeenVersion=99.0.0\n' > /etc/xdg/plasma-welcomerc
# Kein SDDM – LightDM übernimmt die Anmeldung
systemctl disable sddm >/dev/null 2>&1 || true
"""


_LXQT_EXTRA = r"""
# Hintergrund für pcmanfm-qt (zeichnet den LXQt-Schreibtisch) und Fenstermanager festlegen –
# sonst fragt LXQt beim ersten Start, welcher genutzt werden soll.
D="$AGENT_HOME/.config/pcmanfm-qt/lxqt"
mkdir -p "$D" "$AGENT_HOME/.config/lxqt"
if [ ! -f "$D/settings.conf" ]; then
  printf '[Desktop]\nWallpaper=%s\nWallpaperMode=fit\nBgColor=@BORDER@\n' "$IMG" > "$D/settings.conf"
fi
for wm in openbox xfwm4 kwin_x11; do
  if command -v "$wm" >/dev/null 2>&1; then
    grep -q '^window_manager=' "$AGENT_HOME/.config/lxqt/session.conf" 2>/dev/null \
      || printf '[General]\nwindow_manager=%s\n' "$wm" >> "$AGENT_HOME/.config/lxqt/session.conf"
    break
  fi
done
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_HOME/.config"
""".replace("@BORDER@", WALLPAPER_BORDER)

CINNAMON = DesktopSpec(
    id="cinnamon", name="Cinnamon",
    description="Klassisch wie Windows, aufgeräumt und vertraut – der Standard",
    packages="cinnamon-core gnome-terminal nemo",
    xsession="cinnamon", session_cmd="cinnamon-session", xdg_desktop="X-Cinnamon",
    terminal="gnome-terminal", min_ram_mb=3072, weight=38.0,
)
XFCE = DesktopSpec(
    id="xfce", name="Xfce",
    description="Leicht und schnell, klassische Bedienung – gut für wenig Arbeitsspeicher",
    packages="xfce4 xfce4-terminal xfce4-notifyd mousepad ristretto xfce4-screenshooter xfce4-taskmanager",
    xsession="xfce", session_cmd="startxfce4", xdg_desktop="XFCE",
    terminal="xfce4-terminal", min_ram_mb=2048, weight=19.0, extra=_XFCE_EXTRA,
)
KDE = DesktopSpec(
    id="kde", name="KDE Plasma",
    description="Modern und sehr einstellbar, viele Programme – braucht mehr Speicher und Platz",
    packages="kde-plasma-desktop kwin-x11 konsole sddm-",
    xsession="plasmax11", session_cmd="startplasma-x11", xdg_desktop="KDE",
    terminal="konsole", min_ram_mb=4096, weight=78.0, extra=_KDE_EXTRA,
)
GNOME = DesktopSpec(
    id="gnome", name="GNOME",
    description="Schlicht und modern mit Übersicht statt Taskleiste; Programme im Dash links",
    packages="gnome-core gnome-session-xsession gnome-terminal",
    xsession="gnome-xorg", session_cmd="gnome-session", xdg_desktop="GNOME",
    terminal="gnome-terminal", min_ram_mb=4096, weight=52.0, display_manager="gdm3",
)
MATE = DesktopSpec(
    id="mate", name="MATE",
    description="Klassischer Desktop (Nachfolger von GNOME 2), sparsam und stabil",
    packages="mate-desktop-environment-core mate-terminal",
    xsession="mate", session_cmd="mate-session", xdg_desktop="MATE",
    terminal="mate-terminal", min_ram_mb=2048, weight=31.0,
)
LXQT = DesktopSpec(
    id="lxqt", name="LXQt",
    description="Sehr leicht, schlicht und schnell – für schwache Rechner",
    # ohne lxqt-powermanagement: meldet in der VM „Keine Batterie!“; den Ausschaltknopf übernimmt logind
    packages="lxqt-core qterminal lxqt-powermanagement-",
    xsession="lxqt", session_cmd="startlxqt", xdg_desktop="LXQt",
    terminal="qterminal", min_ram_mb=1536, weight=32.0, extra=_LXQT_EXTRA,
)

DESKTOPS: dict[str, DesktopSpec] = {d.id: d for d in (CINNAMON, XFCE, KDE, GNOME, MATE, LXQT)}


def get(desktop_id: str) -> DesktopSpec:
    try:
        return DESKTOPS[desktop_id]
    except KeyError:
        raise ValueError(f"Unbekannter Desktop '{desktop_id}'. Verfügbar: {', '.join(DESKTOPS)}") from None


def name(desktop_id: str) -> str:
    return DESKTOPS[desktop_id].name if desktop_id in DESKTOPS else desktop_id


def format_ram(mb: int) -> str:
    gb = mb / 1024
    return f"{gb:.0f} GB" if gb == int(gb) else f"{gb:.1f} GB".replace(".", ",")


def ram_warning(desktop_id: str, ram_mb: int) -> str:
    """Hinweis, wenn weniger Arbeitsspeicher eingestellt ist als für den Desktop empfohlen – sonst ""."""
    d = get(desktop_id)
    if ram_mb >= d.min_ram_mb:
        return ""
    return (f"{d.name} braucht mindestens etwa {format_ram(d.min_ram_mb)} Arbeitsspeicher – eingestellt sind "
            f"{format_ram(ram_mb)}. Der Agent-PC wird langsam oder Programme werden beendet.")


# ---------------------------------------------------------------- Gast-Skripte
def schema_override() -> str:
    """gsettings-Voreinstellungen für alle GTK-Desktops (unbekannte Schemas überspringt der Gast)."""
    img = screen.WALLPAPER_JPG
    bg = (f"picture-options='scaled'\nprimary-color='{WALLPAPER_BORDER}'\ncolor-shading-type='solid'\n")
    return (
        f"[org.cinnamon.desktop.background]\npicture-uri='file://{img}'\n{bg}\n"
        "[org.cinnamon.settings-daemon.plugins.power]\nbutton-power='shutdown'\n\n"
        f"[org.gnome.desktop.background]\npicture-uri='file://{img}'\npicture-uri-dark='file://{img}'\n{bg}\n"
        f"[org.gnome.desktop.screensaver]\npicture-uri='file://{img}'\n{bg}\n"
        # GNOME: keine Einstellung zum Ausschaltknopf – in VMs fährt gsd-media-keys bei allem außer
        # „nothing“ sofort herunter (und hält die Taste per handle-power-key-Sperre, logind greift nicht).
        "[org.gnome.shell]\nfavorite-apps=['org.gnome.Nautilus.desktop', 'org.gnome.Terminal.desktop']\n"
        "welcome-dialog-last-shown-version='999'\n\n"
        f"[org.mate.background]\npicture-filename='{img}'\n{bg}\n"
        "[org.mate.power-manager]\nbutton-power='shutdown'\n"
    )


# Terminal des Desktops starten: bonys-terminal "Titel" befehl argumente …
_TERMINAL = r"""#!/bin/bash
# Von Bony's Agents: Befehl im Terminal des Desktops starten – bonys-terminal "Titel" befehl argumente …
T="${1:-Terminal}"; shift
[ -r @ENV@ ] && . @ENV@
# Befehl in ein kurzes Skript schreiben – so muss kein Terminal unsere Anführungszeichen verstehen
F="$(mktemp /tmp/bonys-terminal.XXXXXX)"
{ echo '#!/bin/bash'; echo 'rm -f "$0"'; printf '%q ' "$@"; echo; } > "$F"
chmod 700 "$F"
for t in ${TERMINAL:-} gnome-terminal konsole xfce4-terminal mate-terminal qterminal; do
  command -v "$t" >/dev/null 2>&1 || continue
  case "$t" in
    gnome-terminal) exec gnome-terminal --title="$T" -- "$F" ;;
    konsole) exec konsole -p tabtitle="$T" -e "$F" ;;
    xfce4-terminal) exec xfce4-terminal --title="$T" -x "$F" ;;
    mate-terminal) exec mate-terminal --title="$T" -x "$F" ;;
    qterminal) exec qterminal -e "$F" ;;
  esac
done
exec x-terminal-emulator -e "$F"
""".replace("@ENV@", DESKTOP_ENV)

TERMINAL_HELPER = f"""
# Terminal-Starter für Verknüpfungen (passend zum Desktop) – auch für ältere Agent-PCs nachrüsten
mkdir -p /usr/local/bin
cat > {TERMINAL_SCRIPT} <<'BONYS_TERMINAL'
{_TERMINAL}BONYS_TERMINAL
chmod 755 {TERMINAL_SCRIPT}
"""

# Bei jeder Anmeldung (Autostart, läuft als Benutzer in der grafischen Sitzung)
_LOGIN = r"""#!/bin/bash
# Von Bony's Agents: bei jeder Anmeldung – Symbole vertrauenswürdig, GNOME-Dash, Hintergrund (einmalig)
IMG=@PNG@; [ -f "$IMG" ] || IMG=@JPG@
DONE="$HOME/.config/bonys-agents"; mkdir -p "$DONE"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null)"; [ -d "$DESK" ] || DESK="$HOME/Schreibtisch"
trust() {
  for f in "$DESK"/*.desktop; do
    [ -f "$f" ] || continue
    chmod +x "$f"
    gio set "$f" metadata::trusted true 2>/dev/null
    gio set "$f" metadata::trust true 2>/dev/null
    gio set "$f" metadata::xfce-exe-checksum "$(sha256sum "$f" | cut -d' ' -f1)" 2>/dev/null
  done
}
trust
case "${XDG_CURRENT_DESKTOP:-}" in
  *GNOME*)
    # Programme ins Dash (GNOME zeigt keine Schreibtisch-Symbole)
    python3 - "@FAV@" <<'PY'
import ast, os, subprocess, sys
try:
    wanted = [l.strip() for l in open(sys.argv[1]) if l.strip()]
except OSError:
    wanted = []
dirs = ["/usr/share/applications", "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/applications")]
cur = ast.literal_eval(subprocess.run(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                      capture_output=True, text=True).stdout.strip().removeprefix("@as ") or "[]")
new = cur + [a for a in wanted if a not in cur and any(os.path.exists(os.path.join(d, a)) for d in dirs)]
if new != cur:
    subprocess.run(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(new)])
PY
    ;;
  *XFCE*)
    if [ ! -f "$DONE/hintergrund-xfce" ]; then
      for i in $(seq 30); do pgrep -u "$(id -u)" -x xfdesktop >/dev/null && break; sleep 1; done
      sleep 3
      for p in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep '/last-image$'); do
        b="${p%/last-image}"
        xfconf-query -c xfce4-desktop -p "$p" -s "$IMG"
        xfconf-query -c xfce4-desktop -p "$b/image-style" -s 4 2>/dev/null \
          || xfconf-query -c xfce4-desktop -p "$b/image-style" -n -t int -s 4
        xfconf-query -c xfce4-desktop -p "$b/color-style" -s 0 2>/dev/null \
          || xfconf-query -c xfce4-desktop -p "$b/color-style" -n -t int -s 0
        xfconf-query -c xfce4-desktop -p "$b/rgba1" -r 2>/dev/null
        xfconf-query -c xfce4-desktop -p "$b/rgba1" -n -a -t double -s @R@ -t double -s @G@ -t double -s @B@ \
          -t double -s 1
      done
      touch "$DONE/hintergrund-xfce"
    fi
    ;;
  *KDE*)
    if [ ! -f "$DONE/hintergrund-kde" ]; then
      for i in $(seq 60); do
        dbus-send --session --print-reply --dest=org.freedesktop.DBus / org.freedesktop.DBus.NameHasOwner \
          string:org.kde.plasmashell 2>/dev/null | grep -q true && break
        sleep 1
      done
      sleep 2
      JS="desktops().forEach(function(d){d.wallpaperPlugin='org.kde.image';\
d.currentConfigGroup=['Wallpaper','org.kde.image','General'];d.writeConfig('Image','file://$IMG');\
d.writeConfig('FillMode',1);d.writeConfig('Color','@BORDER@');});"
      dbus-send --session --print-reply --dest=org.kde.plasmashell /PlasmaShell \
        org.kde.PlasmaShell.evaluateScript "string:$JS" >/dev/null && touch "$DONE/hintergrund-kde"
    fi
    ;;
esac
# Symbole, die erst nach dem Start des Desktops angelegt wurden, noch einmal
sleep 5; trust
exit 0
"""


def login_script() -> str:
    r, g, b = (f"{int(WALLPAPER_BORDER[i:i + 2], 16) / 255:.4f}" for i in (1, 3, 5))
    return (_LOGIN.replace("@PNG@", screen.WALLPAPER_PNG).replace("@JPG@", screen.WALLPAPER_JPG)
            .replace("@FAV@", FAVORITES).replace("@BORDER@", WALLPAPER_BORDER)
            .replace("@R@", r).replace("@G@", g).replace("@B@", b))


def env_file(d: DesktopSpec) -> str:
    return (f"DESKTOP={d.id}\nXSESSION={d.xsession}\nSESSION_CMD={d.session_cmd}\n"
            f"XDG_DESKTOP={d.xdg_desktop}\nTERMINAL={d.terminal}\n")


def _display_manager(d: DesktopSpec) -> str:
    """Bash: Anmeldemanager des Desktops einschalten, automatische Anmeldung in dessen X11-Sitzung."""
    if d.display_manager == "gdm3":
        return f"""# GNOME: GDM (unter LightDM schaltet GNOME die Bildschirmsperre ab) – nur X11, automatische Anmeldung
mkdir -p /etc/gdm3 /var/lib/AccountsService/users
cat > {GDM_CONF} <<BONYS_DESKTOP
# Von Bony's Agents: X11 statt Wayland (xrdp, Auflösung per xrandr), automatische Anmeldung
[daemon]
WaylandEnable=false
AutomaticLoginEnable=true
AutomaticLogin=$AGENT_USER
DefaultSession={d.xsession}.desktop

[security]

[xdmcp]

[chooser]

[debug]
BONYS_DESKTOP
cat > /var/lib/AccountsService/users/$AGENT_USER <<BONYS_DESKTOP
[User]
Session={d.xsession}
XSession={d.xsession}
SystemAccount=false
BONYS_DESKTOP
echo /usr/sbin/gdm3 > /etc/X11/default-display-manager
for dm in lightdm sddm; do systemctl disable "$dm" >/dev/null 2>&1 || true; done
for u in gdm gdm3; do
  if [ -f /lib/systemd/system/$u.service ] && [ ! -L /lib/systemd/system/$u.service ]; then
    ln -sf /lib/systemd/system/$u.service /etc/systemd/system/display-manager.service
    break
  fi
done"""
    return f"""# LightDM – auch wenn ein Desktop GDM oder SDDM mitbringt
groupadd -rf autologin
gpasswd -a "$AGENT_USER" autologin
cat > {AUTOLOGIN_CONF} <<BONYS_DESKTOP
[Seat:*]
autologin-user=$AGENT_USER
autologin-session={d.xsession}
user-session={d.xsession}
BONYS_DESKTOP
echo /usr/sbin/lightdm > /etc/X11/default-display-manager
for dm in gdm3 gdm sddm; do systemctl disable "$dm" >/dev/null 2>&1 || true; done
ln -sf /lib/systemd/system/lightdm.service /etc/systemd/system/display-manager.service"""


def install_script(d: DesktopSpec, set_default: bool = True, locale: str = "de_DE.UTF-8") -> str:
    """Bash-Schritt (als root): Desktop installieren; ``set_default`` = automatische Anmeldung dorthin.

    Erwartet $AGENT_USER und $AGENT_HOME. Wiederholbar.
    """
    lines = [f"""
apt-get install -y {COMMON_PACKAGES} {DM_PACKAGES[d.display_manager]} {d.packages}
test -f /usr/share/xsessions/{d.xsession}.desktop || {{ echo "FEHLER: Sitzung {d.xsession} fehlt"; exit 1; }}
mkdir -p {CONF_DIR} /etc/lightdm/lightdm.conf.d /etc/lightdm/lightdm-gtk-greeter.conf.d /etc/systemd/logind.conf.d
touch {FAVORITES}
"""]
    if set_default:
        lines.append(f"""
cat > {DESKTOP_ENV} <<'BONYS_DESKTOP'
{env_file(d)}BONYS_DESKTOP
{_display_manager(d)}
systemctl set-default graphical.target
""")
    lines.append(f"""
# Ausschaltknopf (ACPI – „Herunterfahren“ in der App) fährt sofort herunter, ohne Rückfrage im Gast.
cat > {LOGIND_DROPIN} <<'BONYS_DESKTOP'
[Login]
HandlePowerKey=poweroff
PowerKeyIgnoreInhibited=yes
BONYS_DESKTOP
# Hintergrundbild (Cinnamon, GNOME, MATE) und Energie-Einstellungen als gsettings-Voreinstellung
cat > {screen.SCHEMA_OVERRIDE} <<'BONYS_DESKTOP'
{schema_override()}BONYS_DESKTOP
glib-compile-schemas /usr/share/glib-2.0/schemas
# Anmeldebildschirm: lightdm-gtk-greeter kennt kein „scaled“; „#zoomed:“ füllt den Bildschirm mit
# erhaltenem Seitenverhältnis (Ränder werden beschnitten, aber nichts verzerrt).
cat > {GREETER_DROPIN} <<'BONYS_DESKTOP'
[greeter]
background=#zoomed:{screen.WALLPAPER_JPG}
user-background=false
BONYS_DESKTOP
{TERMINAL_HELPER}
cat > {LOGIN_SCRIPT} <<'BONYS_DESKTOP_LOGIN'
{login_script()}BONYS_DESKTOP_LOGIN
chmod 755 {LOGIN_SCRIPT}
cat > {LOGIN_AUTOSTART} <<'BONYS_DESKTOP'
[Desktop Entry]
Type=Application
Name=Bony's Agents: Anmeldung
Exec={LOGIN_SCRIPT}
NoDisplay=true
BONYS_DESKTOP
# Auflösung folgt dem QEMU-Fenster (wandelt auch das Hintergrundbild in RGBA-PNG um)
{screen.guest_setup_script()}
IMG={screen.WALLPAPER_PNG}; [ -f "$IMG" ] || IMG={screen.WALLPAPER_JPG}
""")
    if d.extra:
        lines.append(d.extra)
    lines.append(f"""
# Ordner wie Schreibtisch/Downloads gleich in der richtigen Sprache anlegen
su - "$AGENT_USER" -c 'LANG={locale} xdg-user-dirs-update --force' || true
""")
    return "".join(lines)
