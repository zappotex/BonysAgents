# SPDX-License-Identifier: GPL-3.0-or-later
"""Hintergrundbild der Agent-PCs: Standardbild, frühere Standardbilder und das Umstellen bestehender Agent-PCs.

Das Standardbild liegt im Agent-PC immer unter ``/usr/share/backgrounds/bonys-agents/wallpaper.jpg`` (dazu eine
RGBA-PNG-Fassung, siehe ``screen``). Alle Desktops verweisen auf diesen Pfad – so genügt es, die Datei zu ersetzen,
und wer selbst ein anderes Bild gewählt hat, behält es (dessen Einstellung zeigt auf einen anderen Pfad).

Umstellen (``update``, Knopf „Hintergrundbild aktualisieren“, ``bonys-agents wallpaper NAME``):

- ``aktuell``: schon das neue Bild – nichts zu tun.
- ``alt``: noch eines unserer früheren Standardbilder (``OLD_SHA256``) und kein eigenes Bild gewählt → ersetzen.
- Eigenes Bild in einem Desktop gewählt (``custom``) oder die Datei ist keines unserer Bilder (``fremd``) → nur nach
  Rückfrage bzw. mit ``--force`` (setzt dann auch die Desktops wieder auf das Standardbild).

Ersetzt werden: Bild (JPEG + PNG), gsettings-Voreinstellung (Cinnamon, GNOME, MATE), Anmeldeskript (Xfce, KDE) mit
der neuen Randfarbe, LXQt-Einstellung; in einer laufenden Sitzung wird das Bild sofort neu geladen. Der
Anmeldebildschirm (LightDM) zeigt auf denselben Pfad. Agent-PCs aus alten Vorlagen bzw. ``.bonys``-Dateien
bekommen das neue Bild beim ersten Start automatisch – aber nur, wenn sie noch das alte hatten.
"""

from __future__ import annotations

import base64
import hashlib
import shlex
from dataclasses import dataclass, field
from importlib import resources

from bonys_agents import desktops, screen
from bonys_agents.i18n import tr

RESOURCE = "wallpaper.jpg"
DIR = "/usr/share/backgrounds/bonys-agents"
STAGED = "/var/lib/bonys-agents/wallpaper-standard.jpg"   # beim ersten Start eines Klons (cloud-init)
# Frühere Standardbilder (SHA-256 der JPEG-Datei im Agent-PC). Alle Versionen 0.3 bis 0.18 hatten dasselbe.
OLD_SHA256 = {
    "cd4e20c64df915a9e7a9b575f5ef4f6b3cb3e4a119147ae5f6fd9cf97242541d": "0.3 – 0.18",
}
MARK = "BONYS-WP"
CURRENT, OLD, FOREIGN, MISSING = "aktuell", "alt", "fremd", "fehlt"


def data() -> bytes:
    return (resources.files("bonys_agents") / "resources" / RESOURCE).read_bytes()


def sha256() -> str:
    return hashlib.sha256(data()).hexdigest()


@dataclass
class Status:
    state: str = ""                                   # aktuell | alt | fremd | fehlt
    custom: list[str] = field(default_factory=list)   # „Desktop: Pfad“ selbst gewählter Bilder
    done: str = ""                                    # aktuell | umgestellt | nachfragen

    @property
    def needs_consent(self) -> bool:
        """Würde Umstellen etwas Selbstgewähltes ersetzen?"""
        return bool(self.custom) or self.state == FOREIGN


def parse(output: str) -> Status:
    s = Status()
    for line in output.splitlines():
        if not line.startswith(MARK + " "):
            continue
        key, _, value = line[len(MARK) + 1:].partition("=")
        if key == "STATE":
            s.state = value.strip()
        elif key == "CUSTOM" and value.strip():
            s.custom.append(value.strip())
        elif key == "DONE":
            s.done = value.strip()
    return s


def guest_script(username: str, mode: str, image: str = STAGED) -> str:
    """Bash (als root im Agent-PC). ``mode``: „check“ (nur Status), „auto“ (ersetzen nur ohne Rückfrage-Grund),
    „force“ (immer ersetzen, auch Desktops mit eigenem Bild zurücksetzen). ``image``: Pfad des neuen Bildes
    (Shell-Ausdruck, z. B. ``"$T"``)."""
    if mode not in ("check", "auto", "force"):
        raise ValueError(mode)
    border = desktops.WALLPAPER_BORDER
    r, g, b = (f"{int(border[i:i + 2], 16) / 255:.4f}" for i in (1, 3, 5))
    return f"""
U={shlex.quote(username)}
MODE={mode}
NEWIMG={image}
R=${{BONYS_WP_ROOT:-}}   # nur für Tests: alles unter einem anderen Wurzelordner
DIR=$R{DIR}
JPG=$R{screen.WALLPAPER_JPG}
PNG=$R{screen.WALLPAPER_PNG}
SCHEMA=$R{screen.SCHEMA_OVERRIDE}
LOGIN=$R{desktops.LOGIN_SCRIPT}
NEW={sha256()}
OLD="{' '.join(OLD_SHA256)}"
say() {{ echo "{MARK} $*"; }}
H=$(getent passwd "$U" | cut -d: -f6)
ID=$(id -u "$U" 2>/dev/null || echo 0)
[ -n "$R" ] && H=$R/home/$U
cur=""
[ -f "$JPG" ] && cur=$(sha256sum "$JPG" | cut -c1-64)
if [ -z "$cur" ]; then state={MISSING}
elif [ "$cur" = "$NEW" ]; then state={CURRENT}
else case " $OLD " in *" $cur "*) state={OLD} ;; *) state={FOREIGN} ;; esac
fi
say "STATE=$state"
# Selbst gewählte Bilder finden (nur Pfade außerhalb von $DIR – unsere Bilder zählen nicht)
custom=0
note() {{
  v=$(printf '%s' "$2" | sed "s/^'//; s/'$//; s|^file://||")
  case "$v" in ""|"$DIR"/*|{DIR}/*) return ;; esac
  say "CUSTOM=$1: $v"
  custom=1
}}
asuser() {{
  if [ -n "$R" ]; then env HOME="$H" "$@"
  else runuser -u "$U" -- env HOME="$H" XDG_RUNTIME_DIR="/run/user/$ID" "$@"; fi
}}
GS="org.cinnamon.desktop.background:picture-uri org.gnome.desktop.background:picture-uri"
GS="$GS org.mate.background:picture-filename"
if [ -n "$H" ] && command -v gsettings >/dev/null 2>&1; then
  for k in $GS; do
    v=$(asuser gsettings get "${{k%%:*}}" "${{k#*:}}" 2>/dev/null) || continue
    n=${{k#org.}}; note "${{n%%.*}}" "$v"
  done
fi
XF="$H/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"
KD="$H/.config/plasma-org.kde.plasma.desktop-appletsrc"
LQ="$H/.config/pcmanfm-qt/lxqt/settings.conf"
if [ -f "$XF" ]; then
  while IFS= read -r v; do note xfce "$v"; done < <(grep -o 'name="last-image" type="string" value="[^"]*"' "$XF" \
    | sed 's/.*value="//; s/"$//' | sort -u)
fi
[ -f "$KD" ] && while IFS= read -r v; do note kde "$v"; done < <(sed -n 's/^Image=//p' "$KD" | sort -u)
[ -f "$LQ" ] && while IFS= read -r v; do note lxqt "$v"; done < <(sed -n 's/^Wallpaper=//p' "$LQ")
[ "$MODE" = check ] && exit 0
if [ "$MODE" = auto ]; then
  if [ "$state" = {CURRENT} ]; then say "DONE=aktuell"; exit 0; fi
  if [ "$custom" = 1 ] || [ "$state" = {FOREIGN} ]; then say "DONE=nachfragen"; exit 0; fi
fi
[ -s "$NEWIMG" ] || {{ echo "Neues Bild fehlt: $NEWIMG" >&2; exit 1; }}
# Bild ersetzen (JPEG + RGBA-PNG wie bei der Einrichtung)
install -d -m755 "$DIR"
install -m644 "$NEWIMG" "$JPG"
rm -f "$PNG"
python3 - "$JPG" "$PNG.tmp" <<'BONYS_WP' 2>/dev/null && mv -f "$PNG.tmp" "$PNG" && chmod 644 "$PNG" || rm -f "$PNG.tmp"
import sys
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
pix = GdkPixbuf.Pixbuf.new_from_file(sys.argv[1])
pix.add_alpha(False, 0, 0, 0).savev(sys.argv[2], "png", [], [])
BONYS_WP
IMG={screen.WALLPAPER_JPG}; [ -f "$PNG" ] && IMG={screen.WALLPAPER_PNG}
# Voreinstellungen mit der neuen Randfarbe (Cinnamon, GNOME, MATE)
if [ -d "$R/usr/share/glib-2.0/schemas" ]; then
  cat > "$SCHEMA" <<'BONYS_WP'
{desktops.schema_override()}BONYS_WP
  [ -f "$PNG" ] && sed -i "s|{screen.WALLPAPER_JPG}|{screen.WALLPAPER_PNG}|" "$SCHEMA"
  [ -z "$R" ] && {{ glib-compile-schemas /usr/share/glib-2.0/schemas 2>/dev/null || true; }}
fi
# Anmeldeskript (Xfce, KDE) mit der neuen Randfarbe
if [ -f "$LOGIN" ]; then
  cat > "$LOGIN" <<'BONYS_DESKTOP_LOGIN'
{desktops.login_script()}BONYS_DESKTOP_LOGIN
  chmod 755 "$LOGIN"
fi
reset_all=0
{{ [ "$custom" = 0 ] || [ "$MODE" = force ]; }} && reset_all=1
# LXQt
if [ -f "$LQ" ]; then
  sed -i 's/^BgColor=.*/BgColor={border}/' "$LQ"
  [ "$reset_all" = 1 ] && sed -i "s|^Wallpaper=.*|Wallpaper=$IMG|; s/^WallpaperMode=.*/WallpaperMode=fit/" "$LQ"
fi
# Xfce/KDE: das Anmeldeskript setzt das Bild beim nächsten Anmelden erneut
[ "$reset_all" = 1 ] && rm -f "$H/.config/bonys-agents/hintergrund-xfce" "$H/.config/bonys-agents/hintergrund-kde"
# Laufende Sitzung: sofort neu laden
BUS=/run/user/$ID/bus
if [ "$reset_all" = 1 ] && [ -z "$R" ] && [ -S "$BUS" ]; then
  S() {{ runuser -u "$U" -- env HOME="$H" DISPLAY=:0 XDG_RUNTIME_DIR="/run/user/$ID" \\
    DBUS_SESSION_BUS_ADDRESS="unix:path=$BUS" "$@"; }}
  for k in $GS; do
    s=${{k%%:*}}; key=${{k#*:}}
    S gsettings get "$s" "$key" >/dev/null 2>&1 || continue
    S gsettings set "$s" "$key" "''" 2>/dev/null
    S gsettings reset "$s" "$key" 2>/dev/null
    # Die laufende Sitzung kennt die neuen Voreinstellungen noch nicht (erst nach dem Neustart) – also ausdrücklich
    S gsettings set "$s" picture-options "'scaled'" 2>/dev/null
    S gsettings set "$s" primary-color "'{border}'" 2>/dev/null
    S gsettings set "$s" color-shading-type "'solid'" 2>/dev/null
  done
  if pgrep -u "$U" -x xfdesktop >/dev/null 2>&1; then
    for p in $(S xfconf-query -c xfce4-desktop -l 2>/dev/null | grep '/last-image$'); do
      b="${{p%/last-image}}"
      S xfconf-query -c xfce4-desktop -p "$p" -s ""
      S xfconf-query -c xfce4-desktop -p "$p" -s "$IMG"
      S xfconf-query -c xfce4-desktop -p "$b/image-style" -s 4 2>/dev/null \\
        || S xfconf-query -c xfce4-desktop -p "$b/image-style" -n -t int -s 4
      S xfconf-query -c xfce4-desktop -p "$b/color-style" -s 0 2>/dev/null \\
        || S xfconf-query -c xfce4-desktop -p "$b/color-style" -n -t int -s 0
      S xfconf-query -c xfce4-desktop -p "$b/rgba1" -r 2>/dev/null
      S xfconf-query -c xfce4-desktop -p "$b/rgba1" -n -a -t double -s {r} -t double -s {g} -t double -s {b} \\
        -t double -s 1
    done
    mkdir -p "$H/.config/bonys-agents" && touch "$H/.config/bonys-agents/hintergrund-xfce"
    chown -R "$U:" "$H/.config/bonys-agents"
  fi
  if pgrep -u "$U" -x plasmashell >/dev/null 2>&1; then
    JS="desktops().forEach(function(d){{d.wallpaperPlugin='org.kde.image';\\
d.currentConfigGroup=['Wallpaper','org.kde.image','General'];d.writeConfig('Image','');\\
d.writeConfig('Image','file://$IMG');d.writeConfig('FillMode',1);d.writeConfig('Color','{border}');}});"
    S dbus-send --session --print-reply --dest=org.kde.plasmashell /PlasmaShell \\
      org.kde.PlasmaShell.evaluateScript "string:$JS" >/dev/null 2>&1 \\
      && mkdir -p "$H/.config/bonys-agents" && touch "$H/.config/bonys-agents/hintergrund-kde" \\
      && chown -R "$U:" "$H/.config/bonys-agents"
  fi
  if pgrep -u "$U" -x pcmanfm-qt >/dev/null 2>&1; then
    S pcmanfm-qt --set-wallpaper "$IMG" --wallpaper-mode fit >/dev/null 2>&1 || true
  fi
fi
[ "$NEWIMG" = {STAGED} ] && rm -f "$NEWIMG"
true
say "DONE=umgestellt"
"""


def staged_script(username: str, mode: str) -> str:
    """Wie ``guest_script``, das neue Bild steckt aber im Skript selbst (für laufende Agent-PCs, per stdin)."""
    b64 = base64.b64encode(data()).decode("ascii")
    lines = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    return (f"#!/bin/bash\nT=$(mktemp)\ntrap 'rm -f \"$T\"' EXIT\nbase64 -d > \"$T\" <<'BONYS_WP_IMG'\n{lines}\n"
            f"BONYS_WP_IMG\n" + guest_script(username, mode, image='"$T"'))


def check(machine, password: str | None = None, ssh_prompt: bool = False) -> Status:
    _ready(machine)
    out = machine.guest_run("#!/bin/bash\n" + guest_script(machine.config.username, "check"), password=password,
                            ssh_prompt=ssh_prompt, timeout=60, via_stdin=True)
    return parse(out)


def update(machine, force: bool = False, password: str | None = None, ssh_prompt: bool = False) -> Status:
    """Im laufenden Agent-PC umstellen. Ohne ``force`` nur, wenn kein eigenes Bild betroffen ist – sonst
    ``Status.done == "nachfragen"`` (nichts geändert)."""
    _ready(machine)
    out = machine.guest_run(staged_script(machine.config.username, "force" if force else "auto"), password=password,
                            ssh_prompt=ssh_prompt, timeout=180, via_stdin=True)
    return parse(out)


def _ready(machine) -> None:
    if not machine.is_running() or not machine.progress().ready or machine.config.first_boot_pending:
        raise RuntimeError(tr("„{name}“ muss laufen und fertig eingerichtet sein.", name=machine.name))


def describe(s: Status) -> str:
    """Verständlicher Text zum Ergebnis."""
    if s.done == "aktuell" or (not s.done and s.state == CURRENT):
        if s.custom:
            return (tr("Das neue Standard-Hintergrundbild ist schon da. Du hast ein eigenes Bild gewählt – das "
                       "bleibt ({wert}).", wert="; ".join(s.custom[:3])))
        return tr("Das neue Standard-Hintergrundbild ist schon aktiv.")
    if s.done == "umgestellt":
        return tr("Hintergrundbild aktualisiert – das neue Standardbild ist aktiv (auch auf dem Anmeldebildschirm).")
    reasons = []
    if s.custom:
        reasons.append("Du hast ein eigenes Hintergrundbild gewählt (" + "; ".join(s.custom[:3]) + ").")
    if s.state == FOREIGN:
        reasons.append("Die Bilddatei des Agent-PCs ist nicht mehr unser früheres Standardbild.")
    return " ".join(reasons) or "Nichts geändert."
