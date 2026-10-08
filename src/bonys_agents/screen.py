# SPDX-License-Identifier: GPL-3.0-or-later
"""Bildschirm des Agent-PCs: Auflösung folgt dem QEMU-Fenster, Zoom oder feste Größe.

QEMU meldet die Größe des Fensters über die virtuelle Grafikkarte (virtio-gpu mit EDID) als
neue bevorzugte Auflösung an den Gast – wie VirtualBox mit Gasterweiterungen. Im Gast löst das
ein DRM-Hotplug-Ereignis aus; eine udev-Regel startet dann einen kleinen Dienst, der in allen
laufenden X-Servern (Anmeldebildschirm und Cinnamon-Sitzung) „xrandr --auto“ ausführt.

Welche Einstellung gilt, gibt QEMU dem Gast beim Start über fw_cfg mit
(/sys/firmware/qemu_fw_cfg/by_name/opt/bonys-agents/screen/raw): „auto“, „scale:BxH“ oder „fixed:BxH“.
"""

from __future__ import annotations

import re

AUTO = "auto"      # Auflösung folgt dem Fenster (Standard)
SCALE = "scale"    # feste Auflösung im Gast, QEMU skaliert das Bild aufs Fenster (Zoom to Fit)
FIXED = "fixed"    # feste Auflösung, Fenster so groß wie der Gast
MODES = {
    AUTO: "Auflösung folgt dem Fenster",
    SCALE: "Bild skalieren (Zoom to Fit)",
    FIXED: "Feste Auflösung",
}
# Startgröße des Fensters bei „folgt dem Fenster“
START_SIZE = (800, 600)
SIZES = ["800x600", "1024x768", "1280x720", "1280x800", "1366x768", "1440x900", "1600x900",
         "1680x1050", "1920x1080", "1920x1200", "2560x1440"]
DEFAULT_SIZE = "1280x800"
_SIZE_RE = re.compile(r"^(\d{3,4})x(\d{3,4})$")

FW_CFG_NAME = "opt/bonys-agents/screen"

SCREEN_SCRIPT = "/usr/local/bin/bonys-screen"
SYNC_SCRIPT = "/usr/local/sbin/bonys-screen-sync"
EVENT_SCRIPT = "/usr/local/sbin/bonys-screen-event"
GUARD_SCRIPT = "/usr/local/sbin/bonys-cinnamon-guard"
GUARD_SERVICE = "bonys-cinnamon-guard.service"
GUARD_SECONDS = 90
UDEV_RULE = "/etc/udev/rules.d/70-bonys-screen.rules"
SERVICE = "bonys-screen.service"
LIGHTDM_DROPIN = "/etc/lightdm/lightdm.conf.d/60-bonys-screen.conf"
AUTOSTART = "/etc/xdg/autostart/bonys-screen.desktop"
# Hintergrundbild: Cinnamon (llvmpipe) stürzt nach Größenwechseln ab, wenn das Bild 24-Bit-RGB ist
# (JPG) – der Textur-Zugriff liest 4 Byte und damit beim letzten Pixel über das Pufferende hinaus.
# Deshalb wandelt der Gast das JPG in ein PNG mit Alphakanal (RGBA) um.
WALLPAPER_JPG = "/usr/share/backgrounds/bonys-agents/wallpaper.jpg"
WALLPAPER_PNG = "/usr/share/backgrounds/bonys-agents/wallpaper.png"
SCHEMA_OVERRIDE = "/usr/share/glib-2.0/schemas/90-bonys-agents.gschema.override"
# Version der Gast-Skripte – steht in den Dateien, damit man nachgerüstete Agent-PCs erkennt
GUEST_VERSION = 6


def parse_size(size: str) -> tuple[int, int]:
    """„1280x800“ → (1280, 800). ValueError bei ungültiger oder unsinniger Größe."""
    m = _SIZE_RE.match(size.strip().lower().replace("×", "x"))
    if not m:
        raise ValueError(f"Auflösung „{size}“ ungültig – Beispiel: 1280x800")
    w, h = int(m.group(1)), int(m.group(2))
    if not (640 <= w <= 7680 and 480 <= h <= 4320):
        raise ValueError(f"Auflösung „{size}“ außerhalb von 640x480 bis 7680x4320")
    return w, h


def check_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"Anzeige: {', '.join(MODES)} (angegeben: {mode})")


def start_size(mode: str, size: str) -> tuple[int, int]:
    """Bevorzugte Auflösung beim Start = Größe, mit der sich das QEMU-Fenster öffnet."""
    return START_SIZE if mode == AUTO else parse_size(size)


def guest_setting(mode: str, size: str) -> str:
    """Text für fw_cfg, den das Skript im Gast liest."""
    return AUTO if mode == AUTO else f"{mode}:{'x'.join(map(str, parse_size(size)))}"


def label(mode: str, size: str) -> str:
    return MODES.get(mode, mode) + ("" if mode == AUTO else f" ({size})")


def gtk_options(mode: str) -> str:
    """Optionen für „-display gtk“.

    Jede Größenänderung des Fensters geht per EDID/Hotplug an den Gast. Bei „folgt dem Fenster“ muss
    zoom-to-fit trotzdem an sein: Mit zoom-to-fit=off ist das Fenster nie kleiner als der Gast-Bildschirm
    – es ließe sich vergrößern, aber nicht mehr verkleinern. Bis der Gast umgeschaltet hat, skaliert QEMU
    das Bild kurz. Nur bei „feste Auflösung“ ist das Fenster so groß wie der Gast (zoom-to-fit=off).
    """
    return f"zoom-to-fit={'off' if mode == FIXED else 'on'},show-menubar=on"


# Höhe der Menüleiste im QEMU-Fenster (GTK) – für die Startgröße des Fensters
GTK_MENUBAR = 25


# ---------------------------------------------------------------- Skripte im Gast
_APPLY = r"""#!/bin/sh
# Von Bony's Agents (Version @VERSION@): Bildschirmauflösung des QEMU-Fensters anwenden – für $DISPLAY.
# Einstellung kommt von QEMU (fw_cfg): auto = bevorzugte Auflösung (= Fenstergröße), sonst feste Größe.
[ -n "${XRDP_SESSION:-}" ] && exit 0          # RDP-Sitzungen passen sich selbst an
command -v xrandr >/dev/null 2>&1 || exit 0
CFG=/sys/firmware/qemu_fw_cfg/by_name/@FWCFG@/raw
CACHE=/run/bonys-screen.mode
MODE=""
if [ -r "$CFG" ]; then
  MODE="$(cat "$CFG" 2>/dev/null)"
  # fw_cfg darf nur root lesen – für die Cinnamon-Sitzung (Autostart) eine Kopie ablegen
  [ "$(id -u)" = 0 ] && printf '%s\n' "$MODE" > "$CACHE" 2>/dev/null
fi
[ -z "$MODE" ] && [ -r "$CACHE" ] && MODE="$(cat "$CACHE" 2>/dev/null)"
SIZE=""
case "$MODE" in
  fixed:*|scale:*) SIZE="${MODE#*:}" ;;
esac
for out in $(xrandr --query 2>/dev/null | awk '$2 == "connected" {print $1}'); do
  case "$out" in
    Virtual-*|VGA-*|default) ;;
    *) continue ;;
  esac
  if [ -z "$SIZE" ]; then
    xrandr --output "$out" --auto 2>/dev/null || true
  elif ! xrandr --output "$out" --mode "$SIZE" 2>/dev/null; then
    # Größe fehlt in der Liste der Grafikkarte – Modus selbst anlegen. Eigener Name: Ein Modus „BxH“
    # kann im X-Server noch von einer früheren Abfrage existieren, ohne am Ausgang zu hängen.
    NAME="bonys-$SIZE"
    LINE="$(cvt "${SIZE%x*}" "${SIZE#*x}" 2>/dev/null | sed -n 's/^Modeline "[^"]*" *//p')"
    [ -n "$LINE" ] && xrandr --newmode "$NAME" $LINE 2>/dev/null
    xrandr --addmode "$out" "$NAME" 2>/dev/null
    xrandr --output "$out" --mode "$NAME" 2>/dev/null || true
  fi
done
exit 0
"""

_SYNC = r"""#!/bin/sh
# Von Bony's Agents (Version @VERSION@): Das QEMU-Fenster hat eine neue Größe (DRM-Hotplug) –
# Auflösung in allen laufenden X-Servern anpassen: Anmeldebildschirm (LightDM) und Cinnamon.
STAMP=/run/bonys-screen.event
apply() {
  for pid in $(pgrep -x Xorg); do
    args="$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null)"
    disp="$(printf '%s\n' "$args" | grep -m1 '^:[0-9][0-9]*$')"
    auth="$(printf '%s\n' "$args" | grep -A1 -m1 '^-auth$' | tail -n1)"
    [ -n "$disp" ] || continue
    DISPLAY="$disp" XAUTHORITY="$auth" @APPLY@
  done
}
# Cinnamon stürzt nach Größenwechseln selten ab (Mesa/llvmpipe) – eine Weile darauf aufpassen
systemctl restart --no-block @GUARD@ 2>/dev/null
# Entprellen: Beim Ziehen am Fensterrand kommen mehrere Meldungen kurz hintereinander –
# erst umschalten, wenn 0,5 s lang keine neue kam, und danach prüfen, ob inzwischen eine neue da ist.
i=0
while [ $i -lt 40 ]; do
  i=$((i + 1))
  seen="$(cat "$STAMP" 2>/dev/null)"
  sleep 0.5
  [ "$(cat "$STAMP" 2>/dev/null)" = "$seen" ] || continue
  apply
  [ "$(cat "$STAMP" 2>/dev/null)" = "$seen" ] && break
done
exit 0
"""

_EVENT = r"""#!/bin/sh
# Von Bony's Agents (Version @VERSION@): von udev bei DRM-Hotplug aufgerufen – nur merken und den Dienst anstoßen.
date +%s%N > /run/bonys-screen.event
exec /bin/systemctl --no-block start @SERVICE@
"""


_GUARD = r"""#!/bin/sh
# Von Bony's Agents (Version @VERSION@): Cinnamon stürzt nach einem Wechsel der Bildschirmgröße selten ab
# (Fehler in Mesa/llvmpipe bzw. Muffin beim Neuzeichnen des Hintergrunds). cinnamon-launcher bliebe dann
# im Rückfallmodus hängen. Läuft eine Weile nach jedem Größenwechsel und startet Cinnamon neu – offene
# Fenster bleiben erhalten.
KEY="org.cinnamon.launcher memory-limit-enabled"
alive() {  # läuft unter dem Launcher $1 ein Cinnamon (kein Zombie)?
  ps -o stat=,comm= --ppid "$1" 2>/dev/null | awk '$1 !~ /^Z/ && $2 == "cinnamon" {f=1} END {exit !f}'
}
restart() {  # $1 = PID von cinnamon-launcher
  U="$(stat -c %U "/proc/$1")"
  BUS="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(stat -c %u "/proc/$1")/bus"
  OLD="$(runuser -u "$U" -- env "$BUS" gsettings get $KEY 2>/dev/null)"
  case "$OLD" in true) NEW=false ;; false) NEW=true ;; *) NEW="" ;; esac
  if [ -n "$NEW" ]; then
    # Ändert sich diese Einstellung, startet sich cinnamon-launcher selbst neu (gleicher Prozess, die
    # Sitzung merkt nichts). Sofort zurückstellen – der Launcher ist dann schon dabei.
    runuser -u "$U" -- env "$BUS" sh -c "gsettings set $KEY $NEW; gsettings set $KEY $OLD"
    sleep 6
  fi
  # Hat das nicht geklappt: Launcher beenden – cinnamon-session startet ihn neu
  alive "$1" || kill "$1" 2>/dev/null
}
END=$(( $(date +%s) + @SECONDS@ ))
while [ "$(date +%s)" -lt "$END" ]; do
  for L in $(pgrep -f '^cinnamon-launcher'); do
    MARK="/run/bonys-cinnamon-guard.$L"
    if alive "$L"; then
      rm -f "$MARK"
    elif [ -e "$MARK" ]; then
      # zweimal hintereinander ohne Cinnamon (kein kurzer Neustart) → abgestürzt
      logger -t bonys-screen "Cinnamon abgestürzt – wird neu gestartet"
      rm -f "$MARK"
      restart "$L"
    else
      touch "$MARK"
    fi
  done
  sleep 1
done
rm -f /run/bonys-cinnamon-guard.*
exit 0
"""


def _fill(text: str) -> str:
    return (text.replace("@VERSION@", str(GUEST_VERSION)).replace("@FWCFG@", FW_CFG_NAME)
            .replace("@APPLY@", SCREEN_SCRIPT).replace("@SERVICE@", SERVICE)
            .replace("@GUARD@", GUARD_SERVICE).replace("@SECONDS@", str(GUARD_SECONDS)))


def guest_setup_script() -> str:
    """Bash-Schritt (als root im Gast): Anzeige-Treiber für die automatische Auflösung einrichten.

    Wiederholbar – dient bei der Einrichtung, bei „Agent-PC aktualisieren“ und beim Nachrüsten.
    """
    return f"""
# ---- Bony's Agents: Bildschirmauflösung folgt dem QEMU-Fenster (Anzeige-Treiber, Version {GUEST_VERSION}) ----
command -v xrandr >/dev/null 2>&1 || apt-get install -y x11-xserver-utils || true
# fw_cfg: darüber gibt QEMU die gewählte Anzeige-Einstellung mit
echo qemu_fw_cfg > /etc/modules-load.d/bonys-agents-screen.conf
modprobe qemu_fw_cfg 2>/dev/null || true
mkdir -p /usr/local/sbin /usr/local/bin /etc/lightdm/lightdm.conf.d /etc/xdg/autostart
cat > {SCREEN_SCRIPT} <<'BONYS_SCREEN_EOF'
{_fill(_APPLY)}BONYS_SCREEN_EOF
cat > {SYNC_SCRIPT} <<'BONYS_SCREEN_EOF'
{_fill(_SYNC)}BONYS_SCREEN_EOF
cat > {EVENT_SCRIPT} <<'BONYS_SCREEN_EOF'
{_fill(_EVENT)}BONYS_SCREEN_EOF
cat > {GUARD_SCRIPT} <<'BONYS_SCREEN_EOF'
{_fill(_GUARD)}BONYS_SCREEN_EOF
chmod 755 {SCREEN_SCRIPT} {SYNC_SCRIPT} {EVENT_SCRIPT} {GUARD_SCRIPT}
cat > /etc/systemd/system/{GUARD_SERVICE} <<'BONYS_SCREEN_EOF'
[Unit]
Description=Bony's Agents: Cinnamon nach einem Absturz beim Größenwechsel neu starten

[Service]
Type=simple
ExecStart={GUARD_SCRIPT}
BONYS_SCREEN_EOF
cat > /etc/systemd/system/{SERVICE} <<'BONYS_SCREEN_EOF'
[Unit]
Description=Bony's Agents: Bildschirmauflösung an das QEMU-Fenster anpassen

[Service]
Type=oneshot
ExecStart={SYNC_SCRIPT}
BONYS_SCREEN_EOF
cat > {UDEV_RULE} <<'BONYS_SCREEN_EOF'
# Von Bony's Agents: QEMU meldet eine neue Fenstergröße (virtio-gpu, EDID) → Auflösung anpassen
ACTION=="change", SUBSYSTEM=="drm", KERNEL=="card[0-9]*", RUN+="{EVENT_SCRIPT}"
BONYS_SCREEN_EOF
# Anmeldebildschirm: beim Start jedes X-Servers die Auflösung setzen
cat > {LIGHTDM_DROPIN} <<'BONYS_SCREEN_EOF'
[Seat:*]
display-setup-script={SCREEN_SCRIPT}
BONYS_SCREEN_EOF
# Cinnamon-Sitzung: nach der Anmeldung einmal anwenden (Cinnamon setzt sonst evtl. eine gespeicherte Größe)
cat > {AUTOSTART} <<'BONYS_SCREEN_EOF'
[Desktop Entry]
Type=Application
Name=Bony's Agents: Bildschirmgröße
Exec={SCREEN_SCRIPT}
NoDisplay=true
X-GNOME-Autostart-Phase=Initialization
BONYS_SCREEN_EOF
# Hintergrundbild als RGBA-PNG (siehe oben) – Cinnamon nimmt es, solange niemand ein anderes gewählt hat
if [ -f {WALLPAPER_JPG} ] && python3 - <<'BONYS_SCREEN_EOF'
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
pix = GdkPixbuf.Pixbuf.new_from_file("{WALLPAPER_JPG}")
pix.add_alpha(False, 0, 0, 0).savev("{WALLPAPER_PNG}.tmp", "png", [], [])
BONYS_SCREEN_EOF
then
  mv -f {WALLPAPER_PNG}.tmp {WALLPAPER_PNG}
  chmod 644 {WALLPAPER_PNG}
  if [ -f {SCHEMA_OVERRIDE} ]; then
    sed -i 's|{WALLPAPER_JPG}|{WALLPAPER_PNG}|' {SCHEMA_OVERRIDE}
    glib-compile-schemas /usr/share/glib-2.0/schemas || true
  fi
else
  rm -f {WALLPAPER_PNG}.tmp
  echo "Hinweis: Hintergrundbild konnte nicht umgewandelt werden."
fi
systemctl daemon-reload || true
udevadm control --reload-rules 2>/dev/null || true
# Gleich anwenden (bei laufender Sitzung) – ohne zu warten
date +%s%N > /run/bonys-screen.event
systemctl --no-block start {SERVICE} 2>/dev/null || true
echo "Anzeige-Treiber (Version {GUEST_VERSION}) eingerichtet."
"""


def guest_check_script() -> str:
    """Gibt die Version der installierten Gast-Skripte aus (0 = keine)."""
    return (f"grep -o 'Version [0-9]*' {SYNC_SCRIPT} 2>/dev/null | head -n1 | grep -o '[0-9]*' || echo 0")
