# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt die cloud-init-Konfiguration (NoCloud) und das cidata-ISO.

Das ISO wird rein in Python gebaut (pycdlib), damit unter Windows/macOS
keine zusätzlichen Werkzeuge wie genisoimage nötig sind.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import pycdlib

from bonys_agents import desktops, screen, vpnlink
from bonys_agents.apps import APT_WAIT, AppSpec

READY_MARKER = "BONYS-AGENTS-READY"
STEP_MARKER = "BONYS-STEP"
RESUME_MARKER = "BONYS-RESUME"
STATE_DIR = "/var/lib/bonys-agents"
PROVISION_SCRIPT = "/usr/local/sbin/bonys-provision.sh"
PROVISION_SERVICE = "bonys-provision.service"
# Serielle Konsole des Gasts, die die App als console.log liest. Bewusst /dev/console und nicht
# /dev/ttyS0: Das Cloud-Image setzt console=ttyS0 (ARM64: ttyAMA0), /dev/console IST also die
# serielle Schnittstelle. Startet aber serial-getty@ttyS0, macht agetty ein vhangup() – danach sind
# alle offenen Dateien auf /dev/ttyS0 tot (die Ausgabe bräche nach Schritt 1 ab), solche über
# /dev/console nimmt der Kernel davon aus.
GUEST_CONSOLE = "/dev/console"
WALLPAPER_PATH = screen.WALLPAPER_JPG
SCHEMA_OVERRIDE = screen.SCHEMA_OVERRIDE
GROWROOT_SCRIPT = "/usr/local/sbin/bonys-growroot"
SCREEN_SCRIPT = screen.SCREEN_SCRIPT
LOGIND_DROPIN = desktops.LOGIND_DROPIN
GREETER_DROPIN = desktops.GREETER_DROPIN
WALLPAPER_BORDER = desktops.WALLPAPER_BORDER


@dataclass
class GuestConfig:
    hostname: str
    username: str
    password: str
    apps: list[AppSpec]
    keyboard: str = "de"
    timezone: str = "Europe/Berlin"
    locale: str = "de_DE.UTF-8"
    ssh_authorized_keys: list[str] = field(default_factory=list)
    desktop: str = desktops.DEFAULT
    # Mitgebrachte WireGuard-Konfiguration: kommt als eigene Datei ins Seed-ISO, nie in user-data
    vpn: vpnlink.VpnSetup | None = None


def _q(s: str) -> str:
    """Bash-sicheres Quoting."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def desktop_folder(locale: str) -> str:
    """Name des Schreibtisch-Ordners, wie ihn xdg-user-dirs für die Sprache anlegt."""
    return "Schreibtisch" if locale.startswith("de") else "Desktop"


def wallpaper_b64() -> str:
    """Desktop-Hintergrund des Agent-PCs (dasselbe Bild wie in der App), base64-kodiert."""
    data = (resources.files("bonys_agents") / "resources" / "wallpaper.jpg").read_bytes()
    return base64.b64encode(data).decode("ascii")


def provision_script(cfg: GuestConfig) -> str:
    desk = desktops.get(cfg.desktop)
    steps: list[tuple[str, str]] = [
        ("Sprache, Tastatur und Zeitzone", f"""
apt-get update -y
# git und build-essential braucht Hermes Agent – deshalb gleich zu Beginn.
apt-get install -y locales keyboard-configuration console-setup curl ca-certificates gnupg \\
  git build-essential cloud-guest-utils
sed -i 's/^# *{cfg.locale}/{cfg.locale}/' /etc/locale.gen
grep -q '^{cfg.locale}' /etc/locale.gen || echo '{cfg.locale} UTF-8' >> /etc/locale.gen
locale-gen
update-locale LANG={cfg.locale}
timedatectl set-timezone {_q(cfg.timezone)} || ln -sf /usr/share/zoneinfo/{cfg.timezone} /etc/localtime
sed -i 's/^XKBLAYOUT=.*/XKBLAYOUT="{cfg.keyboard}"/' /etc/default/keyboard
localectl set-x11-keymap {cfg.keyboard} || true
# Belegung sofort auch auf der Textkonsole anwenden (sonst gilt dort bis zum Neustart US: Y/Z vertauscht)
setupcon --force --keyboard-only </dev/null || true
# Harmlose, aber verunsichernde Startmeldungen ausblenden
# (z. B. „systemd-ssh-generator: Failed to query local AF_VSOCK CID“).
mkdir -p /etc/systemd/system-generators
ln -sf /dev/null /etc/systemd/system-generators/systemd-ssh-generator
echo 'kernel.printk = 3 4 1 3' > /etc/sysctl.d/20-bonys-quiet-console.conf
sysctl -q -p /etc/sysctl.d/20-bonys-quiet-console.conf || true
# Vergrößerte Festplatte bei jedem Start nutzen. cloud-init übernimmt das nicht mehr,
# weil nach der Einrichtung das Seed-ISO (mit dem Passwort) entfernt wird.
cat > {GROWROOT_SCRIPT} <<'EOF'
#!/bin/sh
ROOT="$(findmnt -n -o SOURCE /)"
PART="$(basename "$ROOT")"
DISK="/dev/$(lsblk -no PKNAME "$ROOT")"
NUM="$(cat "/sys/class/block/$PART/partition")"
growpart "$DISK" "$NUM" || true   # „NOCHANGE“, wenn schon alles genutzt wird
case "$(findmnt -n -o FSTYPE /)" in
  ext*) resize2fs "$ROOT" ;;
  xfs) xfs_growfs / ;;
  btrfs) btrfs filesystem resize max / ;;
esac
EOF
chmod 755 {GROWROOT_SCRIPT}
cat > /etc/systemd/system/bonys-growroot.service <<EOF
[Unit]
Description=Bony's Agents: Systempartition auf die ganze Festplatte erweitern
After=local-fs.target

[Service]
Type=oneshot
ExecStart={GROWROOT_SCRIPT}

[Install]
WantedBy=multi-user.target
EOF
systemctl enable bonys-growroot.service
"""),
        (f"{desk.name}-Desktop mit automatischer Anmeldung", desktops.install_script(desk, locale=cfg.locale)),
    ]
    for app in cfg.apps:
        steps.append((f"{app.name} installieren", app.install + favorite_snippet(app)))
    # Ganz am Ende, nach allen Downloads: Ein eingeschalteter Kill-Switch sperrt ohne Tunnel das Internet.
    finish = vpnlink.guest_import_script(cfg.vpn) if cfg.vpn else ""
    return render_provision(steps, cfg.username, cfg.locale, finish=finish)


def favorite_snippet(app: AppSpec) -> str:
    """Programm für das GNOME-Dash vormerken (Liste, die bonys-desktop-login bei der Anmeldung abgleicht)."""
    if not app.launcher:
        return ""
    name, fav = _q(app.launcher), desktops.FAVORITES
    return f"\nmkdir -p {desktops.CONF_DIR}\ngrep -qx {name} {fav} 2>/dev/null || echo {name} >> {fav}\n"


def render_provision(steps: list[tuple[str, str]], username: str, locale: str = "de_DE.UTF-8", *,
                     state_dir: str = STATE_DIR, log_file: str = "/var/log/bonys-agents.log",
                     home_base: str = "/home", apt_lock_conf: str = "/etc/apt/apt.conf.d/90-bonys-agents-lock",
                     console: str = GUEST_CONSOLE, finish: str = "") -> str:
    """Einrichtungsskript aus (Titel, Bash-Code)-Schritten. Pfade nur für Tests änderbar.

    ``finish``: Bash-Code nach allen Schritten, vor „fertig“ (muss selbst wiederholbar sein).
    """
    total = len(steps)
    parts = [
        "#!/usr/bin/env bash",
        f"# Von Bony's Agents erzeugt – läuft als {PROVISION_SERVICE} bei jedem Start als root,",
        "# bis der Agent-PC fertig eingerichtet ist. Erledigte Schritte werden übersprungen.",
        "set -uo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        f"STATE={_q(state_dir)}",
        'mkdir -p "$STATE"',
        "# Ausgabe ins Protokoll und auf die serielle Konsole – dort liest Bony's Agents den Fortschritt.",
        f"OUT={_q(console)}",
        f'exec > >(tee -a {_q(log_file)} "$OUT") 2>&1',
        f"AGENT_USER={_q(username)}",
        f'AGENT_HOME={_q(home_base)}"/$AGENT_USER"',
        f'DESKTOP_DIR="$AGENT_HOME/{desktop_folder(locale)}"',
        'mkdir -p "$DESKTOP_DIR"',
        "export AGENT_USER AGENT_HOME DESKTOP_DIR",
        f"APT_LOCK_CONF={_q(apt_lock_conf)}",
        APT_HELPERS,
    ]
    done_checks = " ".join(f"{i}" for i in range(1, total + 1))
    parts += [
        "# Fortsetzung nach einem Abbruch (QEMU beendet, Neustart, Speichermangel …)?",
        'FIRST=""; ANY_DONE=""',
        f"for n in {done_checks}; do",
        '  if [ -f "$STATE/step-$n.done" ]; then ANY_DONE=1; elif [ -z "$FIRST" ]; then FIRST=$n; fi',
        "done",
        f'[ -n "$ANY_DONE" ] && [ -n "$FIRST" ] && echo "{RESUME_MARKER} Schritt $FIRST"',
    ]
    for i, (title, body) in enumerate(steps, start=1):
        delim = f"BONYS_STEP_{i}"
        step_file = f"$STATE/step-{i}.sh"
        parts += [
            f'if [ -f "$STATE/step-{i}.done" ]; then',
            f'  echo "Schritt {i}/{total} bereits erledigt: {title}"',
            "else",
            f'  echo "{STEP_MARKER} {i}/{total} {title}"',
            f"  cat > \"{step_file}\" <<'{delim}'{body}{delim}",
            "  bonys_apt_ready",
            # Eigene Bash mit -e: bricht der Schritt ab, läuft die Einrichtung mit dem nächsten weiter.
            # sync VOR der Markierung: Sonst kann nach einem harten Abbruch „erledigt“ auf der Platte
            # stehen, während die im Schritt geschriebenen Dateien noch leer sind (ext4 schreibt verzögert).
            f'  if bash -e "{step_file}" </dev/null; then sync; touch "$STATE/step-{i}.done"; sync; '
            f"else echo \"WARNUNG: Schritt '{title}' fehlgeschlagen\"; fi",
            "fi",
        ]
    if finish:
        parts.append(finish)
    parts += [
        'chmod +x "$DESKTOP_DIR"/*.desktop 2>/dev/null || true',
        'chown -R "$AGENT_USER:$AGENT_USER" "$DESKTOP_DIR"',
        "bonys_apt_resume",
        "sync",
        'touch "$STATE/ready"',
        f"systemctl disable {PROVISION_SERVICE} >/dev/null 2>&1 || true",
        f'echo "{READY_MARKER}"',
        "sync",
        "# Nur während der Ersteinrichtung (Seed-ISO eingelegt) ausschalten – die App startet dann mit Fenster.",
        "if [ -e /dev/disk/by-label/cidata ] || [ -e /dev/disk/by-label/CIDATA ] \\",
        "   || blkid -t LABEL=cidata >/dev/null 2>&1; then",
        '  echo "Bony\'s Agents: Einrichtung fertig, Agent-PC schaltet sich aus"',
        "  systemctl --no-block poweroff",
        "fi",
    ]
    return "\n".join(parts) + "\n"


# Schritte müssen gefahrlos wiederholbar sein: vor jedem Schritt auf fremde apt-/dpkg-Läufe warten
# und eine unterbrochene Paketinstallation zu Ende bringen.
APT_HELPERS = APT_WAIT + r"""
bonys_apt_ready() {
  bonys_apt_wait
  dpkg --configure -a || true
}
bonys_apt_resume() {
  rm -f "$APT_LOCK_CONF"
  systemctl start apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
}
# Automatische Updates im Gast während der Einrichtung anhalten, apt wartet auf Sperren
systemctl stop apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service \
  unattended-upgrades.service >/dev/null 2>&1 || true
echo 'DPkg::Lock::Timeout "900";' > "$APT_LOCK_CONF"
"""


def provision_service() -> str:
    """systemd-Dienst im Gast: läuft bei jedem Start, solange die Einrichtung nicht fertig ist.

    cloud-init führt runcmd nur einmal pro instance-id aus – nach einem Abbruch ginge es sonst
    nicht weiter. Das Skript deaktiviert den Dienst am Ende selbst.
    """
    # DefaultDependencies=no ist wichtig: Sonst ordnet sich multi-user.target (WantedBy) automatisch
    # HINTER diesen Dienst ein. cloud-init.target kommt aber selbst erst nach multi-user.target – das
    # ergäbe einen Zyklus, und systemd verwirft den Dienst beim nächsten Start stillschweigend
    # („Job bonys-provision.service/start deleted to break ordering cycle“). Die übrigen
    # Standard-Abhängigkeiten stehen deshalb ausdrücklich da.
    return f"""[Unit]
Description=Bony's Agents: Agent-PC einrichten
DefaultDependencies=no
Requires=sysinit.target
Wants=network-online.target
After=sysinit.target basic.target network-online.target cloud-init.target
Before=shutdown.target
Conflicts=shutdown.target
ConditionPathExists=!{STATE_DIR}/ready

[Service]
Type=oneshot
ExecStart={PROVISION_SCRIPT}
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
"""


def desktop_install_script(d: desktops.DesktopSpec, username: str, make_default: bool,
                           locale: str = "de_DE.UTF-8") -> str:
    """Skript, das einen weiteren Desktop in einem fertigen Agent-PC installiert (läuft per sudo)."""
    return "\n".join([
        "#!/usr/bin/env bash",
        "# Von Bony's Agents erzeugt – installiert einen weiteren Desktop.",
        "set -euo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        f"AGENT_USER={_q(username)}",
        'AGENT_HOME="/home/$AGENT_USER"',
        "export AGENT_USER AGENT_HOME",
        APT_WAIT,
        "bonys_apt_wait",
        "apt-get update -y || true",
        desktops.install_script(d, set_default=make_default, locale=locale),
        f'echo "{d.name} ist installiert."' + (" Ab dem nächsten Start meldet sich der Agent-PC dort an."
                                               if make_default else ""),
    ]) + "\n"


def app_install_script(app: AppSpec, username: str, locale: str = "de_DE.UTF-8") -> str:
    """Skript, das eine App nachträglich in einem fertigen Agent-PC installiert (läuft per sudo)."""
    return "\n".join([
        "#!/usr/bin/env bash",
        "# Von Bony's Agents erzeugt – installiert eine App nachträglich.",
        "set -uo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        f"AGENT_USER={_q(username)}",
        'AGENT_HOME="/home/$AGENT_USER"',
        f'DESKTOP_DIR="$AGENT_HOME/{desktop_folder(locale)}"',
        'mkdir -p "$DESKTOP_DIR"',
        "export AGENT_USER AGENT_HOME DESKTOP_DIR",
        "apt-get update -y || true",
        'STEP="$(mktemp)"',
        desktops.TERMINAL_HELPER,
        f"cat > \"$STEP\" <<'BONYS_APP'{app.install}BONYS_APP",
        favorite_snippet(app),
        'bash -e "$STEP" </dev/null || echo "WARNUNG: Installationsschritt mit Fehler beendet"',
        'rm -f "$STEP"',
        'chmod +x "$DESKTOP_DIR"/*.desktop 2>/dev/null || true',
        'chown -R "$AGENT_USER:$AGENT_USER" "$DESKTOP_DIR"',
        f'if su - "$AGENT_USER" -c {_q(app.check)} </dev/null >/dev/null 2>&1; then',
        f'  echo "{app.name} ist installiert."',
        "else",
        f'  echo "FEHLER: {app.name} wurde nicht gefunden – siehe Ausgabe oben." >&2',
        "  exit 3",
        "fi",
    ]) + "\n"


def user_data(cfg: GuestConfig) -> str:
    # JSON ist gültiges YAML – so vermeiden wir eine YAML-Abhängigkeit.
    doc = {
        "hostname": cfg.hostname,
        "preserve_hostname": False,
        "ssh_pwauth": True,
        "users": [
            {
                "name": cfg.username,
                "gecos": "Agent",
                "groups": "sudo,adm",
                "shell": "/bin/bash",
                "sudo": "ALL=(ALL) NOPASSWD:ALL",
                "lock_passwd": False,
                "plain_text_passwd": cfg.password,
            }
        ],
        "growpart": {"mode": "auto", "devices": ["/"]},
        "resize_rootfs": True,
        "write_files": [
            {
                "path": PROVISION_SCRIPT,
                "permissions": "0755",
                "content": provision_script(cfg),
            },
            {
                "path": f"/etc/systemd/system/{PROVISION_SERVICE}",
                "permissions": "0644",
                "content": provision_service(),
            },
            {
                "path": WALLPAPER_PATH,
                "permissions": "0644",
                "encoding": "b64",
                "content": wallpaper_b64(),
            },
        ],
        # Nur einschalten und anstoßen – die Einrichtung selbst läuft als Dienst, auch nach einem Abbruch
        # bei jedem weiteren Start. Am Ende schaltet sich der Gast selbst aus; die App startet ihn mit Fenster.
        "runcmd": [
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", PROVISION_SERVICE],
            ["systemctl", "start", "--no-block", PROVISION_SERVICE],
        ],
    }
    if cfg.ssh_authorized_keys:
        doc["users"][0]["ssh_authorized_keys"] = cfg.ssh_authorized_keys
    return "#cloud-config\n" + json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def meta_data(cfg: GuestConfig, instance_id: str) -> str:
    return f"instance-id: {instance_id}\nlocal-hostname: {cfg.hostname}\n"


def write_seed_iso(path: Path, cfg: GuestConfig, instance_id: str) -> None:
    files = {
        "user-data": user_data(cfg).encode("utf-8"),
        "meta-data": meta_data(cfg, instance_id).encode("utf-8"),
        # Kein network-config: Debian nutzt dann automatisch DHCP auf der ersten Netzwerkkarte.
    }
    if cfg.vpn:
        files[vpnlink.SEED_FILE] = cfg.vpn.data
    _write_iso(path, files)


def _write_iso(path: Path, files: dict[str, bytes]) -> None:
    """ISO nur für den eigenen Benutzer lesbar: Es enthält das Passwort und ggf. einen WireGuard-Schlüssel."""
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident="cidata")
    for name, data in files.items():
        iso_name = "/" + name.replace("-", "").upper()[:8] + ".;1"
        iso.add_fp(
            io.BytesIO(data), len(data), iso_name,
            rr_name=name, joliet_path="/" + name,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        iso.write_fp(f)
    iso.close()


# ---------------------------------------------------------------- Vorlagen
CLONE_SCRIPT = "/usr/local/sbin/bonys-clone-firstboot"
HOSTKEY_SERVICE = "bonys-ssh-hostkeys.service"


@dataclass(frozen=True)
class PersonalItem:
    """Persönliche Daten im Home des Agent-Benutzers, die vor dem Speichern als Vorlage gelöscht werden.

    ``paths`` relativ zum Home. ``keep``: nur bei einem Ordner – diese Einträge darin bleiben
    (das Programm selbst), alles andere darin wird gelöscht. ``contents``: nur den Inhalt der
    Ordner löschen, die Ordner selbst bleiben.
    """

    title: str
    paths: tuple[str, ...]
    keep: tuple[str, ...] = ()
    contents: bool = False

    def note(self) -> str:
        if self.keep:
            return f"  (außer {', '.join(self.keep)})"
        return "  (nur der Inhalt)" if self.contents else ""


PERSONAL_DATA: tuple[PersonalItem, ...] = (
    PersonalItem("Telegram: Anmeldung, Sitzungen und zwischengespeicherte Chats",
                 (".var/app/org.telegram.desktop",)),
    PersonalItem("Brave: ganzes Profil – gespeicherte Logins und Passwörter, Cookies, Verlauf, Lesezeichen, "
                 "Erweiterungen", (".config/BraveSoftware", ".cache/BraveSoftware")),
    PersonalItem("Schlüsselbund und KDE-Brieftasche (verschlüsseln u. a. die in Brave gespeicherten Passwörter)",
                 (".local/share/keyrings", ".local/share/kwalletd")),
    # tools (Node, Python, Chromium …) und installs legt der Installer an; skills sind die mitgelieferten
    # Fähigkeiten. Alles andere entsteht erst beim ersten Start und wird dann neu angelegt.
    PersonalItem("Hermes Agent: Konfiguration (config.yaml), API-Schlüssel (.env), Gedächtnis, Sitzungen, Protokolle, "
                 "Kopplungen, Caches – das Programm (hermes-agent, tools, installs) und die Skills bleiben",
                 (".hermes",), keep=("hermes-agent", "tools", "installs", "skills")),
    PersonalItem("OpenClaw: Konfiguration, Zugangsdaten, Agenten, Sitzungen, Arbeitsordner – "
                 "das Programm (bin, tools, lib) bleibt", (".openclaw",), keep=("bin", "tools", "lib")),
    PersonalItem("Claude Code: Anmeldung, Einstellungen, Verlauf", (".claude", ".claude.json", ".claude.json.backup")),
    PersonalItem("Obsidian: Anmeldung, Einstellungen und Zwischenspeicher – die Liste der Tresore bleibt",
                 (".config/obsidian",), keep=("obsidian.json",)),
    PersonalItem("Notizen im Tresor „Agent-Notizen“ (Obsidian)", ("Agent-Notizen",), contents=True),
    PersonalItem("SSH-Schlüssel und bekannte Rechner", (".ssh",)),
    PersonalItem("Git: Zugangsdaten, Name und E-Mail, GitHub-CLI-Anmeldung",
                 (".git-credentials", ".config/git/credentials", ".gitconfig", ".config/gh")),
    PersonalItem("Online-Konten und E-Mail-Daten des Desktops (GNOME Online Accounts, Evolution)",
                 (".config/goa-1.0", ".config/evolution", ".local/share/evolution")),
    PersonalItem("Eigene Dateien in Downloads, Dokumente, Bilder, Musik, Videos, Öffentlich, Projekte – "
                 "die Ordner bleiben, der Schreibtisch mit den Programm-Symbolen auch",
                 ("Downloads", "Dokumente", "Documents", "Bilder", "Pictures", "Musik", "Music", "Videos",
                  "Öffentlich", "Public", "Projekte"), contents=True),
    PersonalItem("Zuletzt geöffnete Dateien und Datei-Metadaten",
                 (".local/share/recently-used.xbel", ".local/share/gvfs-metadata")),
)

# Immer (auch mit --keep-personal-data): Verläufe, Caches, Protokolle, Identität des Rechners
SYSTEM_CLEANUP: tuple[str, ...] = (
    "cloud-init zurücksetzen (cloud-init clean --logs --seed --machine-id) – Klone starten als neue Instanz",
    "/etc/machine-id leeren – jeder Klon bekommt beim ersten Start eine eigene",
    "SSH-Host-Schlüssel löschen (/etc/ssh/ssh_host_*) – werden beim ersten Start neu erzeugt",
    "Befehlsverläufe von root und Benutzer (.bash_history, .python_history, .lesshst, .viminfo …)",
    "Paket-Cache (apt-get clean), Zwischenspeicher (~/.cache, ~/.npm-Cache) und ~/.xsession-errors",
    "Protokolle (/var/log, systemd-Journal), DHCP-Leases, Zufalls-Startwert",
    "Temporäre Dateien (/tmp, /var/tmp)",
    "Freien Platz mit Nullen überschreiben – entfernt auch Reste gelöschter Dateien (z. B. Schlüssel) und macht "
    "die Vorlage klein",
)


# Vorlage „frisch“ (persönliche Daten entfernen): Bony's VPN bzw. WireGuard ganz zurücksetzen.
# Nur Pfade werden ausgegeben, nie Inhalte. Bei einem Klon bleibt alles (mit Warnhinweis).
VPN_CLEANUP = r"""echo "== Bony's VPN / WireGuard =="
for f in /etc/wireguard/*.conf; do
  [ -e "$f" ] || continue
  n="$(basename "$f" .conf)"
  if [ "$DRY" = 1 ]; then
    systemctl is-enabled --quiet "wg-quick@$n" 2>/dev/null && echo "WÜRDE AUSSCHALTEN: automatisches Verbinden von $n"
  else
    systemctl disable --now "wg-quick@$n" >/dev/null 2>&1 || true
  fi
done
for f in /etc/wireguard/* /etc/wireguard/.[!.]*; do
  [ -e "$f" ] || [ -L "$f" ] || continue
  wipe "$f"
done
if [ -e /etc/bonys-vpn/killswitch.nft ] || systemctl is-enabled --quiet bonys-vpn-killswitch.service 2>/dev/null; then
  if [ "$DRY" = 1 ]; then
    echo "WÜRDE AUSSCHALTEN: Kill-Switch von Bony's VPN"
  else
    systemctl disable bonys-vpn-killswitch.service >/dev/null 2>&1 || true
    nft delete table inet bonys_vpn >/dev/null 2>&1 || true
    rm -f /etc/bonys-vpn/killswitch.nft
    echo "Kill-Switch von Bony's VPN ausgeschaltet"
  fi
fi
# Einstellungen behalten (Ausnahmen), aber aus und ohne die aufgelösten Adressen der Server
if [ "$DRY" = 0 ] && [ -f /etc/bonys-vpn/killswitch.json ]; then
  python3 - <<'PY' || true
import json
p = "/etc/bonys-vpn/killswitch.json"
try:
    d = json.load(open(p, encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit
d["enabled"], d["resolved"] = False, {}
with open(p, "w", encoding="utf-8") as f:
    f.write(json.dumps(d, indent=2) + "\n")
PY
fi"""


def personal_data_paths(username: str = "agent") -> list[str]:
    """Absolute Pfade (bzw. Ordner mit Ausnahmen) – für die Anzeige „Was wird gelöscht?“."""
    home = f"/home/{username}"
    out = []
    for item in PERSONAL_DATA:
        for p in item.paths:
            out.append(f"{home}/{p}{item.note()}")
    return out


def generalize_script(username: str, remove_personal: bool = True, dry_run: bool = False) -> str:
    """Skript (als root im Gast): Agent-PC für eine Vorlage verallgemeinern.

    Läuft nur in einer Überlagerung der Festplatte – das Original bleibt unberührt.
    ``dry_run``: nichts löschen, nur ausgeben, was gelöscht würde („WÜRDE LÖSCHEN: …“).
    Ausgabe enthält „BONYS-DEBIAN <Version>“ für template.json.
    """
    home = f"/home/{username}"
    lines = [
        "#!/bin/bash",
        "# Von Bony's Agents erzeugt – verallgemeinert einen Agent-PC für eine Vorlage.",
        "set -u",
        f"DRY={1 if dry_run else 0}",
        f"U={_q(username)}",
        f"H={_q(home)}",
        r"""wipe() {
  for p in "$@"; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    if [ "$DRY" = 1 ]; then
      echo "WÜRDE LÖSCHEN: $p ($(du -sh "$p" 2>/dev/null | cut -f1))"
    else
      rm -rf --one-file-system "$p" && echo "gelöscht: $p"
    fi
  done
}
wipe_except() {  # $1 = Ordner, danach: Einträge, die bleiben (das Programm)
  d="$1"; shift
  [ -d "$d" ] || return 0
  for e in "$d"/* "$d"/.[!.]* "$d"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    b="$(basename "$e")"; k=0
    for x in "$@"; do [ "$b" = "$x" ] && k=1; done
    if [ "$k" = 1 ]; then
      [ "$DRY" = 1 ] && echo "BLEIBT: $e"
      continue
    fi
    wipe "$e"
  done
}
run() {  # Systembefehl – im Probelauf nur anzeigen
  if [ "$DRY" = 1 ]; then echo "WÜRDE AUSFÜHREN: $*"; else "$@"; fi
}
echo "BONYS-DEBIAN $(cat /etc/debian_version 2>/dev/null)"
if [ "$DRY" = 0 ]; then
  # Desktop-Sitzung beenden, damit kein Programm (Telegram, Brave …) gelöschte Daten neu schreibt
  systemctl stop display-manager lightdm gdm3 >/dev/null 2>&1 || true
  loginctl terminate-user "$U" >/dev/null 2>&1 || true
  pkill -KILL -u "$U" >/dev/null 2>&1 || true
  sleep 1
fi""",
    ]
    if remove_personal:
        lines.append(VPN_CLEANUP)
        lines.append('echo "== Persönliche Daten =="')
        for item in PERSONAL_DATA:
            lines.append(f"# {item.title}")
            for p in item.paths:
                if item.keep or item.contents:
                    lines.append(f'wipe_except "$H/{p}" ' + " ".join(_q(k) for k in item.keep))
                else:
                    lines.append(f'wipe "$H/{p}"')
    lines.append(r"""echo "== System =="
wipe /root/.bash_history /root/.python_history /root/.lesshst /root/.viminfo /root/.wget-hsts
wipe "$H/.bash_history" "$H/.python_history" "$H/.lesshst" "$H/.viminfo" "$H/.wget-hsts" "$H/.node_repl_history"
wipe /var/lib/bonys-agents/vpn-config.done
wipe "$H/.cache" /root/.cache "$H/.npm/_cacache" "$H/.npm/_logs" "$H/.xsession-errors" "$H/.xsession-errors.old"
if [ "$DRY" = 1 ]; then
  echo "WÜRDE AUSFÜHREN: cloud-init clean --logs --seed --machine-id"
  echo "WÜRDE LEEREN: /etc/machine-id"
  for f in /etc/ssh/ssh_host_*; do [ -e "$f" ] && echo "WÜRDE LÖSCHEN: $f"; done
  echo "WÜRDE AUSFÜHREN: apt-get clean ($(du -sh /var/cache/apt/archives 2>/dev/null | cut -f1))"
  echo "WÜRDE LEEREN: Protokolle in /var/log ($(du -sh /var/log 2>/dev/null | cut -f1)), /tmp, /var/tmp"
  echo "WÜRDE AUSFÜHREN: freien Platz mit Nullen überschreiben (dd, danach fstrim)"
  exit 0
fi
cloud-init clean --logs --seed --machine-id \
  || { rm -rf /var/lib/cloud/instances /var/lib/cloud/instance /var/lib/cloud/data /var/lib/cloud/sem \
         /var/lib/cloud/seed /var/log/cloud-init*.log; }
truncate -s 0 /etc/machine-id
[ -L /var/lib/dbus/machine-id ] || rm -f /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*
# SSH-Host-Schlüssel beim ersten Start neu erzeugen (cloud-init tut das auch – doppelt hält besser)
cat > /etc/systemd/system/""" + HOSTKEY_SERVICE + r""" <<'EOF'
[Unit]
Description=Bony's Agents: SSH-Host-Schlüssel erzeugen (Agent-PC aus Vorlage)
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
EOF
systemctl enable """ + HOSTKEY_SERVICE + r""" >/dev/null 2>&1 || true
apt-get clean
rm -f /var/lib/systemd/random-seed /var/lib/dhcp/*.leases
rm -rf /var/lib/NetworkManager/*.lease /tmp/* /tmp/.[!.]* /var/tmp/* 2>/dev/null
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-time=1s >/dev/null 2>&1 || true
rm -rf /var/log/journal/*
find /var/log -type f \( -name '*.gz' -o -name '*.[0-9]' -o -name '*.old' \) -delete
find /var/log -type f -exec truncate -s 0 {} +
echo "== Freien Platz nullen =="
# fstrim allein reicht nicht: Es gibt nur ganze Cluster der Festplattendatei (64 KiB) frei. Ein freier
# Block in einem sonst belegten Cluster behielte seinen alten Inhalt – etwa eine gelöschte Datei mit
# einem Schlüssel. Deshalb jeden freien Block mit Nullen überschreiben. Die Arbeitskopie läuft mit
# detect-zeroes=unmap: Nullen kosten dort keinen Platz und fehlen in der komprimierten Vorlage.
sync
dd if=/dev/zero of=/var/tmp/bonys-zero bs=4M status=none 2>/dev/null || true
sync
rm -f /var/tmp/bonys-zero
sync
fstrim -av || true
sync
echo "BONYS-GENERALIZED"
""")
    return "\n".join(lines) + "\n"


def clone_firstboot_script(vpn: vpnlink.VpnSetup | None = None) -> str:
    """Läuft beim ersten Start eines Agent-PCs aus einer Vorlage (runcmd, einmal je Instanz)."""
    vpn_part = vpnlink.guest_import_script(vpn) if vpn else ""
    return f"""#!/bin/sh
# Von Bony's Agents erzeugt – erster Start eines Agent-PCs aus einer Vorlage.
ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1 || ssh-keygen -A
systemctl restart ssh.service >/dev/null 2>&1 || true
[ -s /var/lib/dbus/machine-id ] || dbus-uuidgen --ensure 2>/dev/null || true
command -v make-ssl-cert >/dev/null && make-ssl-cert generate-default-snakeoil --force-overwrite || true
[ -x /usr/sbin/xrdp-keygen ] && xrdp-keygen xrdp auto >/dev/null 2>&1 || true
[ -x {GROWROOT_SCRIPT} ] && {GROWROOT_SCRIPT} >/dev/null 2>&1 || true
{vpn_part}sync
echo "{READY_MARKER}" > {GUEST_CONSOLE}
"""


def clone_user_data(hostname: str, username: str, password: str, vpn: vpnlink.VpnSetup | None = None) -> str:
    """cloud-config für den ersten Start eines Klons: nur Rechnername, Passwort, Schlüssel, Platz."""
    doc = {
        "hostname": hostname,
        "preserve_hostname": False,
        "manage_etc_hosts": True,
        "ssh_pwauth": True,
        "users": [],  # Benutzer gibt es schon – keinen Standardbenutzer anlegen
        "chpasswd": {"expire": False, "users": [{"name": username, "password": password, "type": "text"}]},
        "growpart": {"mode": "auto", "devices": ["/"]},
        "resize_rootfs": True,
        "write_files": [{"path": CLONE_SCRIPT, "permissions": "0755", "content": clone_firstboot_script(vpn)}],
        "runcmd": [[CLONE_SCRIPT]],
    }
    return "#cloud-config\n" + json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_clone_seed_iso(path: Path, hostname: str, username: str, password: str, instance_id: str,
                         vpn: vpnlink.VpnSetup | None = None) -> None:
    files = {
        "user-data": clone_user_data(hostname, username, password, vpn).encode("utf-8"),
        "meta-data": f"instance-id: {instance_id}\nlocal-hostname: {hostname}\n".encode(),
    }
    if vpn:
        files[vpnlink.SEED_FILE] = vpn.data
    _write_iso(path, files)
