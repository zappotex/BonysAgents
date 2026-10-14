# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen weitergeben: das Paketformat ``.bonys`` (z. B. für Schulungen).

Eine ``.bonys``-Datei ist ein unkomprimiertes tar (die Festplatte ist schon komprimiert)::

    manifest.json   immer das erste Element – Inhalt, Ersteller, Architektur, Apps, Prüfsummen
    preview.png     optional (oder preview.jpg): Vorschaubild
    disk.qcow2      komprimiert (qemu-img convert -c), eigenständig (kein Backing-File)

Export nur von frischen Vorlagen – und das wird im Image geprüft, nicht nur angenommen: Eine Überlagerung
der Vorlage startet ohne Netz (die Vorlage selbst bleibt unverändert). Dort sucht die **Frisch-Prüfung**
nach Resten (Tokens, Schlüssel, Browser-Profile, Sitzungen, Verläufe …). Funde nennen nur Art und Pfad,
nie Inhalte, und blockieren den Export, bis bereinigt wird (``clean=True``: persönliche Daten nur in der
Export-Kopie entfernen). Danach: nicht weitergebbare Apps entfernen (``AppSpec.redistributable``),
Passwort-Hashes sperren, verallgemeinern wie beim Erstellen einer Vorlage – und eine zweite, strenge
Prüfung, die auch Hostschlüssel, Maschinen-ID und Geheimnisse von Mission Control umfasst.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from bonys_agents import __version__, apps, cloudinit, desktops, host, mission_control, qemu, storage, templates, vm

SUFFIX = ".bonys"
FORMAT_ID = "bonys-agents-template"
FORMAT_VERSION = 1
MIN_VERSION = "0.17.0"          # erste Version von Bony's Agents, die .bonys lesen kann
MANIFEST = "manifest.json"
DISK = "disk.qcow2"
PREVIEWS = ("preview.png", "preview.jpg")
MAX_PREVIEW = 5 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
ARCH_NAMES = {"x86_64": "amd64", "aarch64": "arm64"}
ARCH_FROM_NAME = {v: k for k, v in ARCH_NAMES.items()}
REINSTALL_NOTE = "nicht frei weitergebbar – beim Empfänger aus der offiziellen Quelle neu installieren"
SLOW_ARCH_WARNING = ("Die Vorlage ist für {tpl}, dieser Rechner hat {host}. Ein Agent-PC daraus liefe nur emuliert – "
                     "sehr, sehr langsam (Minuten statt Sekunden für jeden Schritt). Besser: das Rezept nutzen – "
                     "derselbe Desktop mit denselben Apps wird hier neu eingerichtet, mit dem passenden Debian-Image.")

FUND_MARKER = "BONYS-FUND"
VERSION_MARKER = "BONYS-APPVERSION"
CHECK_DONE = "BONYS-CHECK-DONE"
PREP_DONE = "BONYS-PREP-DONE"

ProgressFn = Callable[[str, float, str], None]

# Anteile am Gesamtfortschritt beim Export
_PHASES = {"overlay": (0.0, 0.01), "boot": (0.01, 0.08), "check": (0.08, 0.1), "prepare": (0.1, 0.14),
           "generalize": (0.14, 0.36), "recheck": (0.36, 0.37), "shutdown": (0.37, 0.4),
           "convert": (0.4, 0.86), "hash": (0.86, 0.9), "pack": (0.9, 1.0)}


class Cancelled(Exception):
    """Vom Benutzer abgebrochen."""


class NotFreshError(RuntimeError):
    """Frisch-Prüfung hat Reste gefunden – Export blockiert, bis bereinigt ist."""

    def __init__(self, findings: list[Finding], strict: bool = False, not_fresh_template: bool = False):
        self.findings = findings
        self.strict = strict
        self.not_fresh_template = not_fresh_template
        if not_fresh_template:
            msg = ("Diese Vorlage wurde MIT persönlichen Daten erstellt (Klon) – sie lässt sich nur „frisch gemacht“ "
                   "exportieren: Die persönlichen Daten werden dann in der Export-Kopie entfernt, die Vorlage selbst "
                   "bleibt unverändert.")
        elif strict:
            msg = ("Nach dem Bereinigen sind noch Reste da – Export abgebrochen:\n" + format_findings(findings))
        else:
            msg = ("In der Vorlage sind noch persönliche Daten oder Geheimnisse – Export blockiert, bis bereinigt "
                   "ist:\n" + format_findings(findings))
        super().__init__(msg)


# ---------------------------------------------------------------- Frisch-Prüfung
@dataclass(frozen=True)
class Finding:
    category: str
    path: str

    @property
    def title(self) -> str:
        return category_title(self.category)


# Eigene Kategorien (zusätzlich zu den persönlichen Daten aus cloudinit.PERSONAL_DATA = „p0“, „p1“ …)
CATEGORIES: dict[str, str] = {
    "tokens": "Token- und Zugangsdaten-Dateien (z. B. npm, netrc, Docker, Cloud-Zugänge)",
    "wireguard": "WireGuard-/VPN-Konfiguration (Bony's VPN, /etc/wireguard)",
    "netconn": "Gespeicherte Netzwerk-/VPN-Verbindungen (NetworkManager)",
    "rootssh": "SSH-Schlüssel und bekannte Rechner von root",
    "browser": "Weitere Browser-Profile (Verlauf, Cookies, Logins)",
    "telegram": "Telegram-Sitzung (ohne Flatpak)",
    "history": "Befehlsverläufe (Shell-Historie)",
    "mc-secrets": "Mission Control: Geheimnisse in .env nicht zurückgesetzt",
    "mc-data": "Mission Control: Benutzerdaten (Docker-Volume)",
    "hostkeys": "SSH-Hostschlüssel des Rechners",
    "machine-id": "Maschinen-ID (/etc/machine-id)",
    "cloud-init": "cloud-init-Daten der letzten Instanz (enthalten u. a. das Start-Passwort)",
    "password": "Passwort-Hash eines Benutzers (/etc/shadow)",
    "app": "Nicht frei weitergebbares Programm ist noch installiert",
}


def category_title(category: str) -> str:
    if category.startswith("p") and category[1:].isdigit() and int(category[1:]) < len(cloudinit.PERSONAL_DATA):
        return cloudinit.PERSONAL_DATA[int(category[1:])].title
    return CATEGORIES.get(category, category)


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def check_script(username: str, strict: bool = False, removed_apps: list[str] | tuple[str, ...] = ()) -> str:
    """Frisch-Prüfung (Bash, als root im Gast). Gibt je Fund ``BONYS-FUND<TAB>Kategorie<TAB>Pfad`` aus – nie Inhalte.

    ``strict=False`` (vor dem Bereinigen): Was erst beim Start der Prüfkopie entstanden ist (z. B. ein leerer
    Schlüsselbund nach der automatischen Anmeldung, neue Geheimnisse von Mission Control), zählt nicht –
    gemeldet werden nur Pfade mit Dateien von vor dem Start. ``strict=True`` (nach dem Verallgemeinern): Jeder
    Pfad zählt, dazu Hostschlüssel, Maschinen-ID, cloud-init-Daten, Passwort-Hashes und ``removed_apps``.
    """
    home = f"/home/{username}"
    lines = [
        "#!/bin/bash",
        "# Von Bony's Agents erzeugt – Frisch-Prüfung vor dem Export einer Vorlage (gibt nur Pfade aus).",
        "set -u",
        f"STRICT={1 if strict else 0}",
        f"U={_q(username)}",
        # R: Wurzel des Dateisystems (in Tests ein Spiel-Ordner), BONYS_BOOT: Startzeit (nur Tests)
        'R="${BONYS_ROOT:-}"',
        f'H="$R"{_q(home)}',
        r"""REF="$(mktemp)"
touch -d "@${BONYS_BOOT:-$(( $(date +%s) - $(cut -d. -f1 /proc/uptime) ))}" "$REF"
fund() { printf '""" + FUND_MARKER + r"""\t%s\t%s\n' "$1" "$2"; }
# Zählt der Pfad? Streng: wenn es ihn gibt. Sonst nur mit einer Datei, die älter ist als der Start.
counts() {
  [ -e "$1" ] || [ -L "$1" ] || return 1
  [ "$STRICT" = 1 ] && return 0
  [ -n "$(find "$1" -xdev ! -type d ! -newer "$REF" -print -quit 2>/dev/null)" ]
}
paths() {  # $1 = Kategorie, danach Pfade
  k="$1"; shift
  for p in "$@"; do counts "$p" && fund "$k" "$p"; done
  return 0
}
except() {  # $1 = Kategorie, $2 = Ordner, danach Einträge, die dazugehören dürfen (das Programm)
  k="$1"; d="$2"; shift 2
  [ -d "$d" ] || return 0
  for e in "$d"/* "$d"/.[!.]* "$d"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    b="$(basename "$e")"; keep=0
    for x in "$@"; do [ "$b" = "$x" ] && keep=1; done
    [ "$keep" = 1 ] || { counts "$e" && fund "$k" "$e"; }
  done
  return 0
}
contains() {  # $1 = Kategorie, $2 = Muster (grep -E), danach Dateien – nur melden, wenn das Muster vorkommt
  k="$1"; pat="$2"; shift 2
  for p in "$@"; do [ -f "$p" ] && grep -qE "$pat" "$p" 2>/dev/null && counts "$p" && fund "$k" "$p"; done
  return 0
}""",
    ]
    for i, item in enumerate(cloudinit.PERSONAL_DATA):
        for p in item.paths:
            if item.keep or item.contents:
                lines.append(f'except p{i} "$H/{p}" ' + " ".join(_q(k) for k in item.keep))
            else:
                lines.append(f'paths p{i} "$H/{p}"')
    lines.append(r"""paths tokens "$H/.netrc" $R/root/.netrc "$H/.aws/credentials" $R/root/.aws/credentials \
  "$H/.config/rclone/rclone.conf" "$H/.pypirc" "$H/.config/hub"
contains tokens '_auth|_authToken|//.*:_password' "$H/.npmrc" $R/root/.npmrc
contains tokens '"auths?"[[:space:]]*:[[:space:]]*\{[[:space:]]*"' "$H/.docker/config.json" $R/root/.docker/config.json
for f in $R/etc/wireguard/* $R/etc/wireguard/.[!.]*; do paths wireguard "$f"; done
for f in $R/etc/NetworkManager/system-connections/*; do paths netconn "$f"; done
for f in $R/root/.ssh/*; do paths rootssh "$f"; done
paths browser "$H/.mozilla" "$H/.config/chromium" "$H/.config/google-chrome" "$H/.cache/chromium" \
  "$H/.var/app/com.brave.Browser" "$H/.var/app/org.mozilla.firefox" "$H/.var/app/org.chromium.Chromium" \
  $R/root/.config/BraveSoftware $R/root/.mozilla $R/root/.config/chromium
paths telegram "$H/.local/share/TelegramDesktop"
paths history "$H/.bash_history" "$H/.zsh_history" "$H/.python_history" "$H/.node_repl_history" \
  "$H/.local/share/fish/fish_history" "$H/.mysql_history" "$H/.psql_history" "$H/.sqlite_history" \
  $R/root/.bash_history $R/root/.zsh_history $R/root/.python_history $R/root/.node_repl_history
MC="$R""" + mission_control.INSTALL_DIR + r""""
if [ -f "$MC/.env" ] && [ -f "$MC/.env.example" ]; then
  for k in $(sed -n 's/^\([A-Z0-9_]*\)=""" + mission_control.SECRET_PLACEHOLDER + r"""$/\1/p' "$MC/.env.example"); do
    if ! grep -qx "$k=""" + mission_control.SECRET_PLACEHOLDER + r"""" "$MC/.env"; then
      if [ "$STRICT" = 1 ] || [ ! "$MC/.env" -nt "$REF" ]; then fund mc-secrets "$MC/.env ($k)"; fi
    fi
  done
fi
paths mc-data $R/var/lib/docker/volumes/""" + mission_control.VOLUME + r"""/_data
if [ "$STRICT" = 1 ]; then
  for f in $R/etc/ssh/ssh_host_*; do [ -e "$f" ] && fund hostkeys "$f"; done
  [ -s $R/etc/machine-id ] && fund machine-id $R/etc/machine-id
  [ -n "$(ls -A $R/var/lib/cloud/instances 2>/dev/null)" ] && fund cloud-init $R/var/lib/cloud/instances
  for s in $R/etc/shadow $R/etc/shadow-; do
    [ -f "$s" ] || continue
    awk -F: '$2 !~ /^[!*]/ { print $1 }' "$s" | while read -r u; do fund password "$s ($u)"; done
  done""")
    for app_id in removed_apps:
        spec = apps.APPS.get(app_id)
        if spec and spec.check != "true":
            lines.append(f'  su - "$U" -c {_q(spec.check)} </dev/null >/dev/null 2>&1 && fund app {_q(spec.name)}')
    lines.append("fi")
    lines.append('rm -f "$REF"')
    lines.append(f'echo "{CHECK_DONE}"')
    return "\n".join(lines) + "\n"


def parse_findings(out: str) -> list[Finding]:
    found: list[Finding] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] == FUND_MARKER:
            f = Finding(parts[1], parts[2])
            if f not in found:
                found.append(f)
    return found


def format_findings(findings: list[Finding], per_category: int = 8) -> str:
    """Verständliche Liste: je Art die Pfade (höchstens ``per_category``), nie Inhalte."""
    groups: dict[str, list[str]] = {}
    for f in findings:
        groups.setdefault(f.category, []).append(f.path)
    out = []
    for cat, paths in groups.items():
        out.append(f"• {category_title(cat)}")
        out += [f"      {p}" for p in paths[:per_category]]
        if len(paths) > per_category:
            out.append(f"      … und {len(paths) - per_category} weitere")
    return "\n".join(out)


def prepare_script(username: str, app_ids: list[str], remove: list[str]) -> str:
    """Vor dem Verallgemeinern (als root): Versionen abfragen, nicht weitergebbare Apps entfernen, Passwörter
    sperren."""
    lines = [
        "#!/bin/bash",
        "# Von Bony's Agents erzeugt – Export-Kopie einer Vorlage vorbereiten.",
        "set -u",
        "export DEBIAN_FRONTEND=noninteractive",
        f"U={_q(username)}",
        "AGENT_USER=\"$U\"",
        'AGENT_HOME="$(getent passwd "$U" | cut -d: -f6)"',
        '[ -n "$AGENT_HOME" ] || AGENT_HOME="/home/$U"',
        'DESKTOP_DIR="$AGENT_HOME/Schreibtisch"',
        '[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$AGENT_HOME/Desktop"',
        "export AGENT_USER AGENT_HOME DESKTOP_DIR",
        'echo "== Versionen =="',
    ]
    for app_id in app_ids:
        spec = apps.APPS.get(app_id)
        if not spec or not spec.version:
            continue
        cmd = "timeout 20 sh -c " + _q(spec.version)
        lines.append(f'V="$(su - "$U" -c {_q(cmd)} </dev/null 2>/dev/null | head -n1 | tr -d "\\r\\t" | cut -c1-60)"')
        lines.append(f'printf "{VERSION_MARKER}\\t%s\\t%s\\n" {_q(app_id)} "$V"')
    for app_id in remove:
        spec = apps.APPS[app_id]
        lines += [
            f'echo "== {spec.name} entfernen (nicht frei weitergebbar) =="',
            "( set -e",
            spec.uninstall.strip(),
            f') || {{ echo "FEHLER: {spec.name} ließ sich nicht entfernen."; exit 1; }}',
            f'echo "entfernt: {spec.name}"',
        ]
    lines += [
        'echo "== Passwörter sperren (der Empfänger setzt beim ersten Start ein eigenes) =="',
        "for u in root $(awk -F: '$3 >= 1000 && $3 < 65534 { print $1 }' /etc/passwd); do",
        "  usermod -p '!' \"$u\" && echo \"gesperrt: $u\"",
        "done",
        "cp -p /etc/shadow /etc/shadow- 2>/dev/null || true",
        f'echo "{PREP_DONE}"',
    ]
    return "\n".join(lines) + "\n"


_VERSION_RE = re.compile(r"\d+(?:\.\d+)+")


def parse_versions(out: str) -> dict[str, str]:
    """``BONYS-APPVERSION``-Zeilen → {App: Version}. Nur die Versionsnummer (ohne Epoche, Paket-Revision, Text)."""
    versions = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] == VERSION_MARKER and parts[2].strip():
            m = _VERSION_RE.search(parts[2].split(":", 1)[-1] if re.match(r"^\d+:", parts[2]) else parts[2])
            versions[parts[1]] = m.group(0) if m else parts[2].strip()
    return versions


# Seed der Export-Kopie: cloud-init sieht eine neue Instanz – kein Benutzer, kein Passwort, Rechnername bleibt
EXPORT_USER_DATA = "#cloud-config\npreserve_hostname: true\nusers: []\n"


# ---------------------------------------------------------------- Manifest
def arch_name(arch: str) -> str:
    return ARCH_NAMES.get(arch, arch)


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def recommended(t: templates.Template, app_ids: list[str]) -> dict:
    """Empfohlene Ausstattung: Arbeitsspeicher nach Desktop (+ Mission Control), 2 CPUs, Festplatte wie die Vorlage."""
    ram = max([desktops.get(d).min_ram_mb for d in [t.desktop, *t.extra_desktops] if d in desktops.DESKTOPS]
              or [4096])
    if mission_control.APP_ID in app_ids:
        ram += mission_control.DEFAULT_REQUIREMENTS.min_ram_mb
    return {"ram_mb": max(ram, 2048), "cpus": 2, "disk_gb": t.disk_gb}


def build_manifest(t: templates.Template, *, creator: str, version: str, disk_size: int, disk_sha256: str,
                   virtual_size: int, debian: str, versions: dict[str, str], removed: list[str],
                   preview: tuple[str, int, str] | None = None, checked: str = "") -> dict:
    kept = [a for a in t.apps if a not in removed]
    app_entries = []
    for a in kept:
        v = versions.get(a) or ((t.app_info.get(a) or {}).get("version") if isinstance(t.app_info, dict) else "")
        app_entries.append({"id": a, "name": apps.names([a])[0], "version": v or ""})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    files = {DISK: {"size": disk_size, "sha256": disk_sha256}}
    m = {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "min_version": MIN_VERSION,
        "created_with": __version__,
        "name": t.name,
        "version": version,
        "description": t.description,
        "creator": creator,
        "exported": now,
        "template_created": t.created,
        "arch": arch_name(t.arch),
        "desktop": t.desktop,
        "extra_desktops": list(t.extra_desktops),
        "debian": debian or t.debian,
        "username": t.username,
        "keyboard": t.keyboard,
        "timezone": t.timezone,
        "apps": app_entries,
        "reinstall": [{"id": a, "name": apps.names([a])[0], "note": REINSTALL_NOTE} for a in removed],
        "recommended": recommended(t, kept),
        "disk": {"file": DISK, "size": disk_size, "virtual_size": virtual_size, "sha256": disk_sha256},
        "files": files,
        "fresh_check": {"passed": True, "checked": checked or now},
    }
    if mission_control.APP_ID in kept and isinstance(t.app_info, dict):
        mc = t.app_info.get(mission_control.APP_ID) or {}
        if mc.get("version"):
            m["app_info"] = {mission_control.APP_ID: {"version": str(mc["version"])}}
    if preview:
        name, size, sha = preview
        m["preview"] = name
        files[name] = {"size": size, "sha256": sha}
    return m


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_./+:@ -]{0,64}$")


def validate_manifest(m: object) -> dict:
    """Manifest prüfen (aus einer fremden Datei!) – ValueError mit verständlicher Meldung."""
    if not isinstance(m, dict) or m.get("format") != FORMAT_ID:
        raise ValueError("Keine Vorlagen-Datei von Bony's Agents (manifest.json fehlt oder ist fremd).")
    fv = m.get("format_version")
    if not isinstance(fv, int) or fv < 1:
        raise ValueError("Manifest: ungültige Formatversion.")
    min_v = str(m.get("min_version") or "0")
    if fv > FORMAT_VERSION or _version_tuple(min_v) > _version_tuple(__version__):
        raise ValueError(f"Diese Datei braucht Bony's Agents {min_v} oder neuer (installiert: {__version__}). "
                         "Bitte zuerst aktualisieren.")
    for key in ("name", "version", "description", "creator", "exported", "template_created", "debian", "desktop",
                "username", "keyboard", "timezone"):
        if not isinstance(m.get(key, ""), str):
            raise ValueError(f"Manifest: „{key}“ ist kein Text.")
    templates.check_name(m.get("name", ""))
    if m.get("arch") not in ARCH_FROM_NAME:
        raise ValueError(f"Manifest: unbekannte Architektur „{m.get('arch')}“.")
    if m.get("desktop", desktops.DEFAULT) not in desktops.DESKTOPS:
        raise ValueError(f"Manifest: unbekannter Desktop „{m.get('desktop')}“ – vielleicht braucht die Datei eine "
                         "neuere Version von Bony's Agents.")
    if not re.match(r"^[a-z_][a-z0-9_-]{0,31}$", m.get("username", "")):
        raise ValueError("Manifest: ungültiger Benutzername.")
    for key in ("keyboard", "timezone", "debian", "version"):
        if not _SAFE_TEXT.match(m.get(key, "")):
            raise ValueError(f"Manifest: ungültige Angabe bei „{key}“.")
    for key in ("apps", "reinstall"):
        items = m.get(key, [])
        if not isinstance(items, list) or not all(isinstance(a, dict) and isinstance(a.get("id"), str)
                                                  and re.match(r"^[a-z0-9-]{1,40}$", a["id"]) for a in items):
            raise ValueError(f"Manifest: ungültige App-Liste „{key}“.")
    extra = m.get("extra_desktops", [])
    if not isinstance(extra, list) or not all(isinstance(d, str) and d in desktops.DESKTOPS for d in extra):
        raise ValueError("Manifest: ungültige zusätzliche Desktops.")
    files = m.get("files")
    if not isinstance(files, dict) or DISK not in files:
        raise ValueError("Manifest: Dateiliste fehlt.")
    for fname, meta in files.items():
        if fname not in (DISK, *PREVIEWS) or not isinstance(meta, dict) or not isinstance(meta.get("size"), int) \
                or meta["size"] < 0 or not _HEX64.match(str(meta.get("sha256", ""))):
            raise ValueError(f"Manifest: ungültiger Eintrag für „{fname}“.")
    if m.get("preview") not in (None, *PREVIEWS) or (m.get("preview") and m["preview"] not in files):
        raise ValueError("Manifest: ungültiges Vorschaubild.")
    rec = m.get("recommended", {})
    if not isinstance(rec, dict) or not all(isinstance(rec.get(k, 1), int) and rec.get(k, 1) > 0
                                            for k in ("ram_mb", "cpus", "disk_gb")):
        raise ValueError("Manifest: ungültige Empfehlung für die Ausstattung.")
    return m


def app_ids(m: dict) -> list[str]:
    return [a["id"] for a in m.get("apps", [])]


def reinstall_ids(m: dict) -> list[str]:
    return [a["id"] for a in m.get("reinstall", [])]


def arch_matches(m: dict) -> bool:
    return ARCH_FROM_NAME.get(m.get("arch", "")) == host.detect().arch


def describe_manifest(m: dict, size: int | None = None) -> str:
    """Mehrzeilige Beschreibung für Dialog und Kommandozeile."""
    rec = m.get("recommended", {})
    lines = [f"{m['name']}" + (f" (Version {m['version']})" if m.get("version") else "")]
    if m.get("description"):
        lines.append(m["description"])
    lines.append(f"Ersteller: {m.get('creator') or 'unbekannt'} · exportiert {_local(m.get('exported', ''))}")
    lines.append(f"Architektur: {m['arch']} · {desktops.name(m.get('desktop', desktops.DEFAULT))}"
                 + (f" · Debian {m['debian']}" if m.get("debian") else ""))
    apps_txt = ", ".join(f"{a.get('name') or a['id']}" + (f" {a['version']}" if a.get("version") else "")
                         for a in m.get("apps", []))
    lines.append(f"Programme: {apps_txt or '–'}")
    if m.get("reinstall"):
        lines.append("Beim Empfänger neu installieren (offizielle Quelle): "
                     + ", ".join(a.get("name") or a["id"] for a in m["reinstall"]))
    lines.append(f"Empfohlen: {rec.get('ram_mb', '?')} MB RAM, {rec.get('cpus', '?')} CPUs, "
                 f"Festplatte {rec.get('disk_gb', '?')} GB")
    disk = m.get("files", {}).get(DISK, {})
    total = size if size is not None else disk.get("size", 0)
    lines.append(f"Größe: {total / storage.GB:.2f} GB (Festplatte komprimiert)")
    return "\n".join(lines)


def _local(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso


def default_filename(name: str, version: str) -> str:
    v = re.sub(r"[^A-Za-z0-9_.-]+", "-", version).strip("-") or "1"
    return f"{name}-{v}{SUFFIX}"


# ---------------------------------------------------------------- Lesen
def is_bonys(file: Path) -> bool:
    """Neues Format (manifest.json zuerst)? Falsch auch bei kaputten oder fremden Dateien."""
    try:
        with tarfile.open(file, "r:") as tar:
            first = tar.next()
            return first is not None and first.name == MANIFEST
    except (OSError, tarfile.TarError):
        return False


def read_manifest(file: Path) -> dict:
    """Manifest lesen und prüfen – ohne die Festplatte anzufassen (liest nur den Anfang der Datei)."""
    try:
        with tarfile.open(file, "r:") as tar:
            first = tar.next()
            if first is None or first.name != MANIFEST or not first.isfile() or first.size > MAX_MANIFEST:
                raise ValueError("Keine .bonys-Datei: manifest.json muss am Anfang stehen.")
            data = tar.extractfile(first).read()
    except tarfile.TarError as e:
        raise ValueError(f"Datei ist beschädigt oder keine .bonys-Datei ({e}).") from e
    try:
        return validate_manifest(json.loads(data.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("manifest.json ist kein gültiges JSON.") from e


def _members(tar: tarfile.TarFile, m: dict) -> dict[str, tarfile.TarInfo]:
    """Nur reguläre Dateien mit genau den erwarteten Namen – keine Pfade, Links oder Geräte."""
    members = {}
    for info in tar.getmembers():
        if info.name in members or not info.isfile() or info.name not in (MANIFEST, DISK, *PREVIEWS):
            raise ValueError(f"Unerwarteter Eintrag in der Datei: {info.name!r}")
        members[info.name] = info
    expected = set(m["files"]) | {MANIFEST}
    if set(members) != expected:
        raise ValueError("Die Datei ist unvollständig oder enthält mehr als angegeben.")
    for name, meta in m["files"].items():
        if members[name].size != meta["size"]:
            raise ValueError(f"{name}: Größe stimmt nicht mit dem Manifest überein (Datei unvollständig?).")
    return members


# ---------------------------------------------------------------- Export
class _ExportVM(templates._WorkVM):
    """Überlagerung einer Vorlage – das Seed-ISO (ohne Passwort) bleibt bis zum Ende."""

    def _remove_seed(self) -> None:
        pass


def _start_export_copy(t: templates.Template, work: Path, qemu_img: Path) -> _ExportVM:
    """Überlagerung der Vorlage samt Seed (ohne Passwort) anlegen und unsichtbar, ohne Netz starten."""
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    qemu.create_overlay(qemu_img, t.disk, work / "disk.qcow2")
    info = host.detect()
    cfg = vm.VMConfig(name=f"export-{t.name}"[:40], arch=t.arch, cpus=max(1, min(2, info.cpus)),
                      ram_mb=max(2048, min(4096, info.default_vm_ram_mb)), disk_gb=t.disk_gb,
                      username=t.username, apps=list(t.apps), desktop=t.desktop,
                      extra_desktops=list(t.extra_desktops), provisioned=True, first_boot_pending=False,
                      display="qemu")
    (work / "vm.json").write_text(json.dumps(asdict(cfg), indent=2), "utf-8")
    cloudinit._write_iso(work / "seed.iso", {
        "user-data": EXPORT_USER_DATA.encode(),
        "meta-data": f"instance-id: bonys-export-{uuid.uuid4()}\n".encode(),
    })
    copy = _ExportVM(work)
    copy.start(headless=True)
    return copy


def _hash_file(path: Path, progress: Callable[[float], None] | None = None, cancel: Callable[[], None] | None = None
               ) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size or 1
    done = 0
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
            done += len(chunk)
            if cancel:
                cancel()
            if progress:
                progress(done / total)
    return h.hexdigest()


class _Reader:
    """Liest eine Datei für tar und meldet Fortschritt (und Abbruch)."""

    def __init__(self, f, cb: Callable[[int], None]):
        self.f, self.cb = f, cb

    def read(self, n: int = -1) -> bytes:
        data = self.f.read(n)
        self.cb(len(data))
        return data


def _tarinfo(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = size, int(time.time()), 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def write_bundle(file: Path, manifest: dict, disk: Path, preview: Path | None = None,
                 progress: Callable[[float], None] | None = None, cancel: Callable[[], None] | None = None) -> Path:
    """tar schreiben: manifest.json, (Vorschaubild), disk.qcow2. Erst unter .teil, dann umbenennen."""
    file = Path(file)
    tmp = file.with_name(file.name + ".teil")
    total = disk.stat().st_size or 1
    done = 0

    def tick(n: int) -> None:
        nonlocal done
        done += n
        if cancel:
            cancel()
        if progress:
            progress(done / total)

    try:
        with tarfile.open(tmp, "w", format=tarfile.PAX_FORMAT) as tar:
            data = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
            tar.addfile(_tarinfo(MANIFEST, len(data)), io.BytesIO(data))
            if preview is not None:
                name = manifest["preview"]
                with preview.open("rb") as f:
                    tar.addfile(_tarinfo(name, preview.stat().st_size), f)
            with disk.open("rb") as f:
                tar.addfile(_tarinfo(DISK, disk.stat().st_size), _Reader(f, tick))
        os.replace(tmp, file)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return file


def _check_preview(preview: Path) -> str:
    preview = Path(preview)
    head = preview.read_bytes()[:8]
    if head.startswith(b"\x89PNG"):
        name = "preview.png"
    elif head.startswith(b"\xff\xd8"):
        name = "preview.jpg"
    else:
        raise ValueError("Vorschaubild: nur PNG oder JPEG.")
    if preview.stat().st_size > MAX_PREVIEW:
        raise ValueError(f"Vorschaubild: höchstens {MAX_PREVIEW // (1024 * 1024)} MB.")
    return name


def export(name: str, file: Path | None = None, *, creator: str = "", version: str = "", clean: bool = False,
           preview: Path | None = None, password: str | None = None, progress: ProgressFn | None = None,
           cancel: threading.Event | None = None, log: Callable[[str], None] | None = None) -> Path:
    """Vorlage ``name`` als ``.bonys``-Datei exportieren.

    ``file``: Zieldatei oder Ordner (dann ``NAME-VERSION.bonys``), Standard: Persönlicher Ordner.
    ``clean``: Funde der Frisch-Prüfung in der Export-Kopie bereinigen (sonst NotFreshError).
    ``cancel``: gesetzt = abbrechen (räumt auf, wirft Cancelled).
    """
    t = templates.get(name)
    version = (version or t.version or "1").strip()
    if not _SAFE_TEXT.match(version) or not version:
        raise ValueError("Version: nur Buchstaben, Ziffern und . _ - (z. B. 1.0)")
    creator = creator.strip()[:80]
    if not t.personal_data_removed and not clean:
        raise NotFreshError([], not_fresh_template=True)
    preview_name = _check_preview(preview) if preview else None
    target = Path(file) if file else Path.home()
    if target.is_dir():
        target = target / default_filename(t.name, version)
    if target.suffix != SUFFIX:
        target = target.with_name(target.name + SUFFIX)
    if target.exists():
        raise FileExistsError(f"{target} gibt es schon.")
    target.parent.mkdir(parents=True, exist_ok=True)
    base = templates.templates_dir(t.library)
    if shutil.disk_usage(base).free < t.size + 2 * storage.GB:
        raise RuntimeError(f"Zu wenig Platz in {t.library}: gebraucht werden etwa {t.size / storage.GB + 2:.0f} GB "
                           "für die Export-Kopie.")
    if shutil.disk_usage(target.parent).free < t.size * 1.2 + 256 * 1024 * 1024:
        raise RuntimeError(f"Zu wenig Platz in {target.parent} für die Datei (etwa {t.size / storage.GB:.1f} GB).")

    emit = log or (lambda line: None)

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled("Export abgebrochen.")

    def report(phase: str, frac: float, msg: str) -> None:
        check_cancel()
        if progress:
            lo, hi = _PHASES.get(phase, (0.0, 1.0))
            progress(phase, lo + (hi - lo) * min(max(frac, 0.0), 1.0), msg)

    qemu_img = qemu.find_binary("qemu-img", host.detect().os)
    work = base / f".{t.name}.export"
    removed = apps.not_redistributable(t.apps)
    copy = None
    try:
        report("overlay", 0, "Lege Export-Kopie an (die Vorlage bleibt unverändert) …")
        copy = _start_export_copy(t, work, qemu_img)
        lo, hi = templates._PHASES["boot"]
        has_agent = templates._wait_guest_agent(copy, lambda _p, f, msg: report("boot", (f - lo) / (hi - lo), msg))

        def run(script: str, what: str, timeout: float) -> str:
            out = templates._run_in_copy(copy, script, password, has_agent, timeout=timeout, what=what,
                                         poll=check_cancel)
            check_cancel()
            return out

        report("check", 0, "Frisch-Prüfung: suche nach Anmeldungen, Schlüsseln, Verläufen …")
        findings = parse_findings(run(check_script(t.username), "Frisch-Prüfung", 300))
        if findings and not clean:
            raise NotFreshError(findings)
        if findings:
            emit(f"Frisch-Prüfung: {len(findings)} Fund(e) – werden in der Export-Kopie bereinigt.")
        report("prepare", 0, ("Entferne nicht frei weitergebbare Programme: " + ", ".join(apps.names(removed)) + " …")
               if removed else "Lese Versionen der Programme, sperre Passwörter …")
        out = run(prepare_script(t.username, list(t.apps), removed), "Vorbereiten", 900)
        for line in out.splitlines():
            if not line.startswith(VERSION_MARKER):
                emit(line)
        if PREP_DONE not in out:
            raise RuntimeError("Vorbereiten nicht vollständig – siehe Ausgabe.")
        versions = parse_versions(out)
        report("generalize", 0, "Verallgemeinere: persönliche Daten, Schlüssel, Protokolle, freien Platz nullen …")
        out = run(cloudinit.generalize_script(t.username, remove_personal=True), "Verallgemeinern",
                  templates.GENERALIZE_TIMEOUT)
        for line in out.splitlines():
            emit(line)
        if "BONYS-GENERALIZED" not in out:
            raise RuntimeError("Verallgemeinern nicht vollständig – siehe Ausgabe.")
        debian = next((ln.split(" ", 1)[1].strip() for ln in out.splitlines() if ln.startswith("BONYS-DEBIAN ")), "")
        report("recheck", 0, "Zweite Frisch-Prüfung (streng) …")
        rest = parse_findings(run(check_script(t.username, strict=True, removed_apps=removed), "Frisch-Prüfung", 300))
        if rest:
            raise NotFreshError(rest, strict=True)
        checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
        report("shutdown", 0, "Fahre Export-Kopie herunter …")
        copy.stop(timeout=120)
        copy = None

        part = work / "export.qcow2"
        report("convert", 0, "Komprimiere Festplatte …")
        qemu.convert_disk(qemu_img, work / "disk.qcow2", part, compress=True,
                          progress=lambda f: report("convert", f, f"Komprimiere Festplatte … {f * 100:.0f} %"))
        qemu.check_disk(qemu_img, part)
        if qemu.backing_file(part) is not None:
            raise RuntimeError("Die exportierte Festplatte ist nicht eigenständig.")
        (work / "disk.qcow2").unlink()
        report("hash", 0, "Berechne Prüfsumme (SHA-256) …")
        sha = _hash_file(part, lambda f: report("hash", f, f"Berechne Prüfsumme … {f * 100:.0f} %"), check_cancel)
        pv = None
        if preview:
            pv = (preview_name, Path(preview).stat().st_size, _hash_file(Path(preview)))
        manifest = build_manifest(t, creator=creator, version=version, disk_size=part.stat().st_size,
                                  disk_sha256=sha, virtual_size=qemu.virtual_size(qemu_img, part), debian=debian,
                                  versions=versions, removed=removed, preview=pv, checked=checked)
        validate_manifest(manifest)
        report("pack", 0, "Schreibe .bonys-Datei …")
        write_bundle(target, manifest, part, Path(preview) if preview else None,
                     progress=lambda f: report("pack", f, f"Schreibe {target.name} … {f * 100:.0f} %"),
                     cancel=check_cancel)
    finally:
        if copy is not None:
            copy.power_off()
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress("pack", 1.0, f"Exportiert: {target} ({target.stat().st_size / storage.GB:.2f} GB)")
    return target


# ---------------------------------------------------------------- Import
def import_bundle(file: Path, location: Path | None = None, name: str | None = None,
                  progress: ProgressFn | None = None, cancel: threading.Event | None = None) -> templates.Template:
    """``.bonys``-Datei als Vorlage übernehmen: Manifest prüfen, beim Entpacken SHA-256 prüfen, qemu-img check."""
    file = Path(file)
    m = read_manifest(file)
    name = name or m["name"]
    templates.check_name(name)
    if templates._exists(name):
        raise FileExistsError(f"Vorlage '{name}' gibt es schon – beim Importieren einen anderen Namen wählen.")
    library = Path(location) if location else storage.preferred_library()
    base = templates.templates_dir(library)
    target = base / name
    if target.exists():
        raise FileExistsError(f"Ordner {target} existiert bereits")
    base.mkdir(parents=True, exist_ok=True)
    disk_size = m["files"][DISK]["size"]
    if shutil.disk_usage(base).free < disk_size + storage.GB:
        raise RuntimeError(f"Zu wenig Platz in {library} ({disk_size / storage.GB:.1f} GB nötig).")

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled("Import abgebrochen.")

    part = base / f".{name}.import"
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir()
    try:
        with tarfile.open(file, "r:") as tar:
            members = _members(tar, m)
            total = sum(members[n].size for n in m["files"]) or 1
            done = 0
            for fname, meta in m["files"].items():
                src = tar.extractfile(members[fname])
                h = hashlib.sha256()
                with (part / fname).open("wb") as out:
                    while chunk := src.read(8 * 1024 * 1024):
                        h.update(chunk)
                        out.write(chunk)
                        done += len(chunk)
                        check_cancel()
                        if progress:
                            progress("import", 0.95 * done / total,
                                     f"Entpacke und prüfe … {done // host.MB} / {total // host.MB} MB")
                if h.hexdigest() != meta["sha256"]:
                    raise ValueError(f"Prüfsumme von {fname} stimmt nicht – die Datei ist beschädigt oder verändert. "
                                     "Bitte neu herunterladen bzw. kopieren.")
        if progress:
            progress("import", 0.96, "Prüfe die Festplatte (qemu-img check) …")
        qemu_img = qemu.find_binary("qemu-img", host.detect().os)
        qemu.check_disk(qemu_img, part / DISK)
        if qemu.backing_file(part / DISK) is not None:
            raise ValueError("Die Festplatte in der Datei ist nicht eigenständig.")
        vsize = qemu.virtual_size(qemu_img, part / DISK)
        rec = m.get("recommended", {})
        disk_gb = max(int(rec.get("disk_gb", 0)), -(-vsize // storage.GB))
        app_info = {k: v for k, v in (m.get("app_info") or {}).items()
                    if k in apps.APPS and isinstance(v, dict) and isinstance(v.get("version", ""), str)}
        tpl = templates.Template(
            path=part, name=name, description=m.get("description", ""),
            created=m.get("template_created") or m.get("exported", ""), debian=m.get("debian", ""),
            arch=ARCH_FROM_NAME[m["arch"]], apps=app_ids(m), size=(part / DISK).stat().st_size,
            disk_gb=disk_gb, source=f"Import von {m.get('creator') or 'unbekannt'}",
            username=m["username"], keyboard=m.get("keyboard", "de"), timezone=m.get("timezone", "Europe/Berlin"),
            personal_data_removed=True, desktop=m.get("desktop", desktops.DEFAULT),
            extra_desktops=list(m.get("extra_desktops", [])), app_info=app_info,
            creator=m.get("creator", ""), version=m.get("version", ""), reinstall=reinstall_ids(m),
            preview=m.get("preview") or "",
        )
        (part / MANIFEST).write_text(json.dumps(m, indent=2, ensure_ascii=False), "utf-8")
        tpl.save()
        os.replace(part, target)
        tpl.path = target
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    storage.add_location(library)
    if progress:
        progress("import", 1.0, f"Vorlage „{name}“ importiert.")
    return tpl


def import_any(file: Path, location: Path | None = None, name: str | None = None,
               progress: ProgressFn | None = None, cancel: threading.Event | None = None) -> templates.Template:
    """.bonys oder das alte .bonys-template (bis 0.16) importieren."""
    if is_bonys(file):
        return import_bundle(file, location, name, progress, cancel)
    return templates.import_file(file, location=location, name=name, progress=progress)


def recipe(m: dict) -> dict:
    """Rezept: Argumente für ``vm.create``, um dieselbe Vorlage hier neu einzurichten (passendes Debian-Image)."""
    known = [a for a in app_ids(m) + reinstall_ids(m) if a in apps.APPS and not apps.APPS[a].hidden]
    rec = m.get("recommended", {})
    return {
        "app_ids": known,   # Abhängigkeiten (z. B. Docker) ergänzt vm.create selbst
        "desktop": m.get("desktop", desktops.DEFAULT),
        "username": m["username"],
        "keyboard": m.get("keyboard", "de"),
        "timezone_name": m.get("timezone", "Europe/Berlin"),
        "ram_mb": rec.get("ram_mb"),
        "cpus": rec.get("cpus"),
        "disk_gb": rec.get("disk_gb"),
    }


def read_preview(file: Path) -> bytes | None:
    """Vorschaubild aus einer .bonys-Datei (oder None) – nur, wenn es im Manifest steht und die Größe passt."""
    m = read_manifest(file)
    name = m.get("preview")
    if not name:
        return None
    with tarfile.open(file, "r:") as tar:
        for info in tar:
            if info.name == name and info.isfile() and info.size <= MAX_PREVIEW:
                data = tar.extractfile(info).read()
                return data if hashlib.sha256(data).hexdigest() == m["files"][name]["sha256"] else None
            if info.name == DISK:
                break
    return None
