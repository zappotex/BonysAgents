# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's Agents Mission Control im Agent-PC – die Seite von Bony's Agents (Host).

Mission Control ist ein eigenes Projekt (https://github.com/zappotex/bonys-agents-mission-control) und
läuft im Agent-PC als Docker-Container. Bony's Agents nutzt nur dessen offizielle Installations-Schnittstelle
(``docs/installation-agent-pc.md`` und ``agentpc.json`` dort):

- ``install.sh`` aus einem FESTEN Release (``VERSION``, Prüfsumme ``INSTALL_SHA256`` und ``SHA256SUMS``
  des Release), danach ``update.sh``, ``uninstall.sh`` und – für frische Vorlagen – ``reset-secrets.sh``.
- Die Weboberfläche lauscht im Agent-PC nur an 127.0.0.1. Auf Wunsch (standardmäßig aus) leitet QEMU
  einen Port an 127.0.0.1 dieses Rechners weiter – nie ins Heimnetz.

Geheimnisse von Mission Control (``.env`` im Agent-PC) verlassen den Agent-PC nie: Der Status liest nur
den Port aus ``.env``, alles andere gibt kein Skript hier aus, und in vm.json steht nur die Version.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bonys_agents import storage

if TYPE_CHECKING:
    from bonys_agents.apps import AppSpec
    from bonys_agents.vm import VM

APP_ID = "mission-control"
NAME = "Mission Control"
REPO = "zappotex/bonys-agents-mission-control"
REPO_URL = f"https://github.com/{REPO}"
# Release, das neue Agent-PCs bekommen – mit einem Update von Bony's Agents anhebbar (dann auch die Prüfsumme).
VERSION = "0.1.0"
INSTALL_SHA256 = "222bff0b91620b7695c7010dea0b6b3af6981e3d3816bec4ce4b24d13c68b237"

PORT = 8787
URL = f"http://127.0.0.1:{PORT}/"
INSTALL_DIR = "/opt/bonys-mission-control"
SCRIPTS = f"{INSTALL_DIR}/scripts"
UNIT = "bonys-mission-control.service"
VOLUME = "bonys-mission-control-data"
SECRET_PLACEHOLDER = "__GENERATE__"
# Eigener Starter: öffnet die Oberfläche in Brave (sonst im Standard-Browser des Agent-PCs)
OPENER = "/usr/local/bin/bonys-mission-control-open"
LAUNCHER = "bonys-mission-control.desktop"
STATUS_MARKER = "BONYS-MC-STATUS"
# Weiterleitung an diesen Rechner (nur 127.0.0.1): erster Port, je Agent-PC eindeutig. Mission Control lauscht im
# Agent-PC nur an dessen 127.0.0.1 – dorthin kommt die QEMU-Weiterleitung nicht. Deshalb reicht ein systemd-Socket-
# Proxy im Agent-PC (nur an seiner Adresse im QEMU-Netz, von außen nicht erreichbar) an 127.0.0.1:PORT weiter.
FIRST_FORWARD_PORT = 18787
GUEST_NET_ADDR = "10.0.2.15"     # Adresse des Agent-PCs im QEMU-Netz (immer dieselbe)
GUEST_FORWARD_PORT = 8788
FORWARD_UNIT = "bonys-mc-forward"
FORWARD_WARNING = ("Die Weiterleitung macht Mission Control auch im Browser DIESES Rechners erreichbar – nur "
                   "unter 127.0.0.1, nicht im Heimnetz. Jedes Programm auf diesem Rechner kann die Oberfläche dann "
                   "aufrufen. Nur einschalten, wenn du sie hier wirklich brauchst.")
FRESH_CLEANUP = ("Mission Control: Geheimnisse (.env) und Benutzerdaten (Docker-Volume) – jeder neue Agent-PC "
                 "erzeugt beim ersten Start eigene; Programm und Docker-Images bleiben")
CLONE_NOTE = ("Mission Control behält seine Geheimnisse und Daten – alle Agent-PCs aus diesem Klon teilen sie.")
# Platz, den ein Agent-PC ohne Mission Control ungefähr belegt (System, Desktop, Programme)
BASE_DISK_GB = 16


@dataclass(frozen=True)
class Requirements:
    """Zusätzlicher Bedarf laut ``agentpc.json`` (inklusive Docker)."""

    min_ram_mb: int = 512
    min_free_disk_gb: int = 2
    version: str = VERSION
    fetched: bool = False   # False = Standardwerte (agentpc.json nicht abrufbar)


DEFAULT_REQUIREMENTS = Requirements()
_cache: Requirements | None = None


def release_url(name: str, version: str = VERSION) -> str:
    return f"{REPO_URL}/releases/download/v{version}/{name}"


def parse_requirements(data: object) -> Requirements:
    """Werte aus ``agentpc.json`` – Unsinniges fällt auf die Standardwerte zurück."""
    if not isinstance(data, dict):
        return DEFAULT_REQUIREMENTS
    ram, disk = data.get("min_ram_mb"), data.get("min_free_disk_gb")
    ok_ram = isinstance(ram, int) and not isinstance(ram, bool) and 0 < ram <= 64 * 1024
    ok_disk = isinstance(disk, (int, float)) and not isinstance(disk, bool) and 0 < disk <= 512
    version = data.get("version") if isinstance(data.get("version"), str) else VERSION
    return Requirements(
        min_ram_mb=ram if ok_ram else DEFAULT_REQUIREMENTS.min_ram_mb,
        min_free_disk_gb=int(-(-disk // 1)) if ok_disk else DEFAULT_REQUIREMENTS.min_free_disk_gb,
        version=version, fetched=ok_ram and ok_disk,
    )


def _cache_file():
    return storage.data_dir() / "mission-control-agentpc.json"


def _download(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "bonys-agents"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 – feste https-Adresse
        return resp.read(64 * 1024)


def requirements(fetch: bool = True, timeout: float = 5.0) -> Requirements:
    """Mindestanforderungen von Mission Control ``VERSION``: zwischengespeichert, sonst aus dem Release.

    Ohne Netz (oder mit ``fetch=False``) gelten die Standardwerte.
    """
    global _cache
    if _cache is not None and _cache.version == VERSION:
        return _cache
    try:
        req = parse_requirements(json.loads(_cache_file().read_text("utf-8")))
        if req.fetched and req.version == VERSION:
            _cache = req
            return req
    except (OSError, ValueError):
        pass
    if not fetch:
        return DEFAULT_REQUIREMENTS
    try:
        data = json.loads(_download(release_url("agentpc.json"), timeout).decode("utf-8"))
    except (OSError, ValueError):
        return DEFAULT_REQUIREMENTS
    req = parse_requirements(data)
    if req.fetched:
        _cache = req
        try:
            _cache_file().parent.mkdir(parents=True, exist_ok=True)
            _cache_file().write_text(json.dumps(data), "utf-8")
        except OSError:
            pass
    return req


def requirement_note(req: Requirements | None = None) -> str:
    req = req or requirements(fetch=False)
    ram = f"{req.min_ram_mb / 1024:.1f} GB".replace(".0 GB", " GB") if req.min_ram_mb >= 1024 else \
        f"{req.min_ram_mb} MB"
    return f"benötigt Docker, ca. {req.min_free_disk_gb} GB zusätzlich auf der Festplatte und {ram} mehr RAM"


def resource_warnings(app_ids: list[str], ram_mb: int, disk_gb: int, desktop_min_ram_mb: int,
                      req: Requirements | None = None, free_disk_gb: float | None = None) -> list[str]:
    """Warnungen, wenn RAM oder Festplatte für Mission Control knapp sind (leer = alles gut).

    ``free_disk_gb``: freier Platz im laufenden Agent-PC (beim Nachinstallieren) – sonst wird aus der Größe der
    Festplatte geschätzt.
    """
    from bonys_agents import apps

    if APP_ID not in apps.with_dependencies(app_ids):
        return []
    req = req or requirements(fetch=False)
    out = []
    need_ram = desktop_min_ram_mb + req.min_ram_mb
    if ram_mb < need_ram:
        out.append(f"{NAME} braucht etwa {req.min_ram_mb} MB RAM zusätzlich – empfohlen sind mindestens "
                   f"{need_ram / 1024:.1f} GB für den Agent-PC (eingestellt: {ram_mb / 1024:.1f} GB). "
                   "Vorschlag: Arbeitsspeicher erhöhen.")
    if free_disk_gb is not None:
        if free_disk_gb < req.min_free_disk_gb:
            out.append(f"{NAME} braucht etwa {req.min_free_disk_gb} GB freien Platz, im Agent-PC sind nur "
                       f"{free_disk_gb:.1f} GB frei. Vorschlag: Festplatte vergrößern (ausgeschaltet).")
    else:
        need_disk = BASE_DISK_GB + req.min_free_disk_gb
        if disk_gb < need_disk:
            out.append(f"{NAME} braucht etwa {req.min_free_disk_gb} GB zusätzlich – empfohlen sind mindestens "
                       f"{need_disk} GB Festplatte (eingestellt: {disk_gb} GB). Vorschlag: Festplatte vergrößern.")
    return out


def _sq(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def install_script(version: str = VERSION, sha256: str = INSTALL_SHA256) -> str:
    """App-Schritt (als root im Gast, $AGENT_USER und $DESKTOP_DIR gesetzt): Mission Control installieren."""
    return r"""
MC_VERSION=""" + _sq(version) + r"""
MC_SHA256=""" + _sq(sha256) + r"""
MC_BASE=""" + _sq(release_url("", version).rstrip("/")) + r"""
apt-get install -y curl ca-certificates
MC_TMP="$(mktemp -d)"
trap 'rm -rf "$MC_TMP"' EXIT
mc_get() { curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --max-time 300 -o "$MC_TMP/$1" "$MC_BASE/$1"; }
echo "Mission Control $MC_VERSION: lade install.sh aus dem offiziellen Release ($MC_BASE) …"
mc_get install.sh
if [ -n "$MC_SHA256" ]; then
  echo "$MC_SHA256  $MC_TMP/install.sh" | sha256sum -c --strict --quiet - || {
    echo "FEHLER: Die Prüfsumme von install.sh stimmt nicht – nichts installiert." >&2; exit 1; }
fi
if mc_get SHA256SUMS; then
  ( cd "$MC_TMP" && grep -E '^[0-9a-f]{64} [ *]?install\.sh$' SHA256SUMS | sha256sum -c --strict --quiet - ) || {
    echo "FEHLER: install.sh passt nicht zu SHA256SUMS des Release – nichts installiert." >&2; exit 1; }
  echo "Prüfsumme von install.sh in Ordnung."
else
  echo "HINWEIS: Das Release hat keine SHA256SUMS – nur die eingebaute Prüfsumme wurde geprüft."
fi
# Docker kommt aus der offiziellen Paketquelle (App „docker“) – deshalb ohne --install-deps.
# Verknüpfungen legt Bony's Agents selbst an (öffnen in Brave), deshalb --no-desktop.
bash "$MC_TMP/install.sh" --version "$MC_VERSION" --user "$AGENT_USER" --no-desktop
""" + launcher_script()


def launcher_script() -> str:
    """Starter und Verknüpfungen: Oberfläche in Brave öffnen (fehlt Brave, im Standard-Browser)."""
    return r"""
cat > """ + OPENER + r""" <<'EOF'
#!/bin/sh
# Von Bony's Agents: Mission Control im Browser öffnen (Brave, sonst Standard-Browser)
URL=""" + _sq(URL) + r"""
if command -v brave-browser >/dev/null 2>&1; then
  exec brave-browser --no-first-run --no-default-browser-check "$URL"
fi
exec xdg-open "$URL"
EOF
chmod 755 """ + OPENER + r"""
cat > /usr/share/applications/""" + LAUNCHER + r""" <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=Mission Control
Comment=Bony's Agents Mission Control im Browser öffnen
Exec=""" + OPENER + r"""
Icon=""" + INSTALL_DIR + r"""/share/mission-control.svg
Terminal=false
Categories=Network;Utility;
StartupNotify=false
EOF
chmod 644 /usr/share/applications/""" + LAUNCHER + r"""
cp /usr/share/applications/""" + LAUNCHER + r""" "$DESKTOP_DIR/"
chown "$AGENT_USER:$AGENT_USER" "$DESKTOP_DIR/""" + LAUNCHER + r""""
chmod 755 "$DESKTOP_DIR/""" + LAUNCHER + r""""
"""


# Prüfung nach dem Installieren (als Agent-Benutzer): Oberfläche antwortet (bis zu 60 s Anlauf)
CHECK = ("for i in $(seq 30); do curl -fsS --max-time 5 " + URL + "api/health >/dev/null 2>&1 && exit 0; "
         "sleep 2; done; exit 1")


def app_spec() -> AppSpec:
    from bonys_agents.apps import AppSpec

    return AppSpec(
        id=APP_ID,
        name=NAME,
        description="Übersicht und Steuerzentrale für deine Agenten im Browser (Open Source, läuft als "
                    "Docker-Container nur im Agent-PC)",
        default=False,
        weight=14.0,   # Image und Start dauern – mit Docker zusammen etwa wie ein großes Programm
        requires=("docker",),
        check=CHECK,
        launcher=LAUNCHER,
        install=install_script(),
    )


# ---------------------------------------------------------------- im laufenden Agent-PC
def status_script() -> str:
    """Zustand als eine JSON-Zeile – nur Version, Dienst, Healthcheck und Port, nie Werte aus .env."""
    return r"""python3 - <<'PY'
import json, os, subprocess, urllib.request
d = """ + repr(INSTALL_DIR) + r"""
st = {"installed": os.path.isfile(d + "/VERSION"), "version": "", "active": False, "healthy": False,
      "health_version": "", "docker": False, "port": """ + str(PORT) + r"""}
try:
    st["version"] = open(d + "/VERSION", encoding="utf-8").read().strip()[:40]
except OSError:
    pass
try:
    for line in open(d + "/.env", encoding="utf-8"):   # nur der Port – Geheimnisse bleiben, wo sie sind
        if line.startswith("MISSION_CONTROL_PORT=") and line.strip().split("=", 1)[1].isdigit():
            st["port"] = int(line.strip().split("=", 1)[1])
except OSError:
    pass
run = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.strip()
st["active"] = run("systemctl", "is-active", """ + repr(UNIT) + r""") == "active"
st["docker"] = run("systemctl", "is-active", "docker.service") == "active"
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{st['port']}/api/health", timeout=4) as r:
        h = json.loads(r.read(4096))
    st["healthy"] = h.get("ok") is True
    st["health_version"] = str(h.get("version", ""))[:40]
except Exception:
    pass
print(""" + repr(STATUS_MARKER + " ") + r""" + json.dumps(st))
PY
"""


_STATUS_KEYS = {"installed": bool, "version": str, "active": bool, "healthy": bool, "health_version": str,
                "docker": bool, "port": int}


def parse_status(out: str) -> dict:
    """Statuszeile lesen – nur bekannte Felder mit passendem Typ (alles andere wird verworfen)."""
    for line in reversed(out.splitlines()):
        if line.startswith(STATUS_MARKER + " "):
            try:
                data = json.loads(line[len(STATUS_MARKER) + 1:])
            except ValueError:
                break
            if not isinstance(data, dict):
                break
            st = {k: data[k] for k, t in _STATUS_KEYS.items() if isinstance(data.get(k), t)}
            if not isinstance(st.get("port"), int) or isinstance(st.get("port"), bool) \
                    or not 0 < st["port"] < 65536:
                st["port"] = PORT
            return st
    raise RuntimeError("Der Zustand von Mission Control ließ sich nicht lesen.")


def status_text(st: dict) -> str:
    if not st.get("installed"):
        return "nicht installiert"
    if st.get("healthy"):
        return f"läuft (Version {st.get('health_version') or st.get('version')})"
    if st.get("active"):
        return "gestartet, antwortet aber nicht (Healthcheck rot)"
    return "gestoppt"


def status(machine: VM, password: str | None = None, ssh_prompt: bool = False) -> dict:
    _require_running(machine)
    rc, out = machine.run_logged(status_script(), password=password, ssh_prompt=ssh_prompt, timeout=60)
    st = parse_status(out)
    if st.get("installed") and st.get("version"):
        _remember_version(machine, st["version"])
    return st


def open_script(username: str) -> str:
    """Oberfläche im Agent-PC öffnen – im Desktop des angemeldeten Agent-Benutzers."""
    return r"""U=""" + _sq(username) + r"""
[ -x """ + OPENER + r""" ] || { echo "Mission Control ist nicht installiert." >&2; exit 3; }
ENVS=""
for pid in $(pgrep -u "$U" 2>/dev/null | sort -rn); do
  e="$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -E \
    '^(DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|XDG_CURRENT_DESKTOP|LANG|HOME)=' \
    || true)"
  if printf '%s\n' "$e" | grep -qE '^(DISPLAY|WAYLAND_DISPLAY)='; then ENVS="$e"; break; fi
done
[ -n "$ENVS" ] || { echo "Im Agent-PC ist kein Desktop angemeldet." >&2; exit 4; }
# shellcheck disable=SC2086
runuser -u "$U" -- env -i PATH=/usr/local/bin:/usr/bin:/bin $ENVS setsid -f """ + OPENER + r""" \
  </dev/null >/dev/null 2>&1
echo "Mission Control geöffnet."
"""


def open_in_guest(machine: VM, password: str | None = None, ssh_prompt: bool = False) -> str:
    _require_running(machine)
    rc, out = machine.run_logged(open_script(machine.config.username), password=password,
                                 ssh_prompt=ssh_prompt, timeout=60)
    if rc == 3:
        raise RuntimeError("Mission Control ist in diesem Agent-PC nicht installiert.")
    if rc == 4:
        raise RuntimeError("Im Agent-PC ist (noch) kein Desktop angemeldet – bitte kurz warten.")
    if rc != 0:
        raise RuntimeError(f"Mission Control ließ sich nicht öffnen (Code {rc}).")
    return "Mission Control öffnet sich im Fenster des Agent-PCs (Brave)."


VERSION_RE = re.compile(r"^(latest|v?\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?)$")


def update_script(version: str = "latest") -> str:
    if not VERSION_RE.match(version):
        raise ValueError("Version: z. B. 0.2.0 oder latest")
    return _logged("update", r"""
[ -x """ + SCRIPTS + r"""/update.sh ] || { echo "Mission Control ist nicht installiert." >&2; exit 3; }
""" + SCRIPTS + r"""/update.sh --version """ + _sq(version) + r"""
""" + _with_desktop_dir(launcher_script()))


def uninstall_script(purge: bool = False) -> str:
    return _logged("uninstall", r"""
if [ -x """ + SCRIPTS + r"""/uninstall.sh ]; then
  """ + SCRIPTS + r"""/uninstall.sh""" + (" --purge" if purge else "") + r"""
elif [ -d """ + INSTALL_DIR + r""" ] && [ """ + ("1" if purge else "0") + r""" = 1 ]; then
  docker volume rm """ + VOLUME + r""" >/dev/null 2>&1 || true
  rm -rf """ + INSTALL_DIR + r"""
fi
rm -f """ + OPENER + r""" /usr/share/applications/""" + LAUNCHER + r"""
""" + guest_forward_script(False) + r"""
rm -f /var/lib/bonys-agents/apps/""" + APP_ID + r""".done
for d in /home/*/Schreibtisch /home/*/Desktop; do rm -f "$d/""" + LAUNCHER + r""""; done
F=/etc/bonys-agents/favorites
[ -f "$F" ] && sed -i '/^""" + re.escape(LAUNCHER) + r"""$/d' "$F"
echo "Mission Control entfernt.""" + ("" if purge else " Einstellungen und Daten bleiben im Agent-PC für eine "
                                     "spätere Neuinstallation.") + r""""
""")


def _with_desktop_dir(body: str) -> str:
    """$AGENT_USER/$DESKTOP_DIR aus install.conf bzw. dem Benutzer des Agent-PCs (für den Starter)."""
    return r"""
AGENT_USER="$(sed -n 's/^AGENT_USER=//p' """ + INSTALL_DIR + r"""/install.conf 2>/dev/null)"
[ -n "$AGENT_USER" ] || AGENT_USER="$(getent passwd 1000 | cut -d: -f1)"
AGENT_HOME="$(getent passwd "$AGENT_USER" | cut -d: -f6)"
DESKTOP_DIR="$AGENT_HOME/Schreibtisch"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$AGENT_HOME/Desktop"
mkdir -p "$DESKTOP_DIR"
""" + body


def _logged(what: str, body: str) -> str:
    """Als root im Gast, Ausgabe zusätzlich auf die serielle Konsole (dort liest die App live mit)."""
    from bonys_agents import cloudinit

    return "\n".join([
        "#!/usr/bin/env bash",
        f"# Von Bony's Agents erzeugt – Mission Control: {what}",
        "set -euo pipefail",
        f"exec > >(tee -a /var/log/bonys-agents-apps.log {cloudinit.GUEST_CONSOLE}) 2>&1",
        body,
    ]) + "\n"


def _require_running(machine: VM) -> None:
    if not machine.is_running() or not machine.progress().ready or machine.config.first_boot_pending:
        raise RuntimeError(f"„{machine.name}“ muss laufen und fertig eingerichtet sein.")


def _require_installed(machine: VM) -> None:
    if APP_ID not in machine.config.apps:
        raise RuntimeError(f"{NAME} ist in „{machine.name}“ nicht installiert – „Programme hinzufügen …“ bzw. "
                           f"„bonys-agents install {machine.name} {APP_ID}“.")


def _remember_version(machine: VM, version: str) -> None:
    info = dict(machine.config.app_info.get(APP_ID) or {})
    if info.get("version") != version:
        info["version"] = version
        info.setdefault("installed", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        machine.config.app_info[APP_ID] = info
        machine.save()


def update(machine: VM, version: str = "latest", password: str | None = None, ssh_prompt: bool = False,
           log: Callable[[str], None] | None = None) -> str:
    """Auf ein anderes Release umstellen (``update.sh``) – Einstellungen, Geheimnisse und Daten bleiben."""
    _require_running(machine)
    _require_installed(machine)
    rc, out = machine.run_logged(update_script(version), password=password, ssh_prompt=ssh_prompt, log=log,
                                 timeout=2 * 3600)
    if rc != 0:
        raise RuntimeError(f"Aktualisieren von {NAME} fehlgeschlagen (Code {rc}) – siehe Ausgabe.")
    st = status(machine, password=password, ssh_prompt=ssh_prompt)
    return f"{NAME} ist aktuell: {status_text(st)}."


def uninstall(machine: VM, purge: bool = False, password: str | None = None, ssh_prompt: bool = False,
              log: Callable[[str], None] | None = None) -> str:
    """Mission Control entfernen. ``purge``: auch Einstellungen, Geheimnisse, Daten und Image. Docker bleibt."""
    _require_running(machine)
    _require_installed(machine)
    rc, out = machine.run_logged(uninstall_script(purge), password=password, ssh_prompt=ssh_prompt, log=log,
                                 timeout=1800)
    if rc != 0:
        raise RuntimeError(f"Deinstallieren von {NAME} fehlgeschlagen (Code {rc}) – siehe Ausgabe.")
    c = machine.config
    c.apps = [a for a in c.apps if a != APP_ID]
    c.app_info.pop(APP_ID, None)
    if c.mc_forward:
        _forward_off(machine)
    machine.save()
    return f"{NAME} ist entfernt" + (" – mit allen Daten." if purge else
                                     " – Einstellungen und Daten bleiben im Agent-PC.") + " Docker bleibt installiert."


# ---------------------------------------------------------------- Weiterleitung an diesen Rechner
def forward_rule(host_port: int, guest_port: int = GUEST_FORWARD_PORT) -> str:
    """Nur 127.0.0.1 auf dem Host – nie ins Heimnetz."""
    return f"tcp:127.0.0.1:{host_port}-:{guest_port}"


def forward_url(machine: VM) -> str:
    return f"http://127.0.0.1:{machine.config.mc_forward_port}/"


def launch_forwards(machine: VM) -> tuple[str, ...]:
    c = machine.config
    if c.mc_forward and c.mc_forward_port and APP_ID in c.apps:
        return (forward_rule(c.mc_forward_port),)
    return ()


def _ensure_forward_port(machine: VM) -> int:
    from bonys_agents import remote, vm

    c = machine.config
    if not c.mc_forward_port:
        used = {m.config.mc_forward_port for m in vm.list_vms() if m.path.resolve() != machine.path.resolve()}
        c.mc_forward_port = remote.next_free_port(FIRST_FORWARD_PORT, used)
    return c.mc_forward_port


def guest_forward_script(on: bool) -> str:
    """Socket-Proxy im Agent-PC ein/aus (als root): nur an der Adresse des QEMU-Netzes → 127.0.0.1:PORT."""
    unit = f"/etc/systemd/system/{FORWARD_UNIT}"
    if not on:
        return (f"systemctl disable --now {FORWARD_UNIT}.socket {FORWARD_UNIT}.service >/dev/null 2>&1 || true\n"
                f"rm -f {unit}.socket {unit}.service\n"
                "systemctl daemon-reload\n")
    socket_unit = "\n".join([
        "[Unit]",
        "Description=Bony's Agents: Mission Control für den Host (nur über die QEMU-Weiterleitung an 127.0.0.1)",
        "",
        "[Socket]",
        f"ListenStream={GUEST_NET_ADDR}:{GUEST_FORWARD_PORT}",
        "FreeBind=yes",
        "",
        "[Install]",
        "WantedBy=sockets.target",
    ])
    service_unit = "\n".join([
        "[Unit]",
        "Description=Bony's Agents: Weiterleitung zu Mission Control",
        f"Requires={FORWARD_UNIT}.socket",
        f"After={FORWARD_UNIT}.socket",
        "",
        "[Service]",
        f"ExecStart=PROXY 127.0.0.1:{PORT}",
        "DynamicUser=yes",
        "PrivateTmp=yes",
    ])
    return "\n".join([
        "set -e",
        'P="$(command -v systemd-socket-proxyd || echo /usr/lib/systemd/systemd-socket-proxyd)"',
        '[ -x "$P" ] || { echo "systemd-socket-proxyd fehlt im Agent-PC." >&2; exit 1; }',
        f"cat > {unit}.socket <<'BONYS_UNIT'",
        socket_unit,
        "BONYS_UNIT",
        f"cat > {unit}.service <<'BONYS_UNIT'",
        service_unit,
        "BONYS_UNIT",
        f'sed -i "s|^ExecStart=PROXY |ExecStart=$P |" {unit}.service',
        "systemctl daemon-reload",
        f"systemctl enable {FORWARD_UNIT}.socket",
        f"systemctl restart {FORWARD_UNIT}.socket",
    ]) + "\n"


def _forward_off(machine: VM) -> None:
    from bonys_agents import qemu

    c = machine.config
    if machine.is_running() and c.mc_forward_port:
        try:
            with qemu.QMP(machine.runtime()["qmp_port"]) as q:
                q.hostfwd_remove(forward_rule(c.mc_forward_port))
        except (OSError, RuntimeError, KeyError, TypeError, ValueError):
            pass
    c.mc_forward = False


def set_forward(machine: VM, on: bool, password: str | None = None, ssh_prompt: bool = False) -> str:
    """Weiterleitung an 127.0.0.1 dieses Rechners ein/aus – bei laufendem Agent-PC sofort.

    Zwei Teile: die QEMU-Weiterleitung (Host 127.0.0.1:Port → Agent-PC) und der Socket-Proxy im Agent-PC.
    Ohne QEMU-Weiterleitung ist der Proxy von außen nicht erreichbar.
    """
    from bonys_agents import qemu

    c = machine.config
    if not on:
        _forward_off(machine)
        machine.save()
        if machine.is_running() and machine.progress().ready:
            try:
                machine.run_logged(guest_forward_script(False), password=password, ssh_prompt=ssh_prompt,
                                   timeout=60)
            except RuntimeError:
                pass  # die QEMU-Seite ist schon zu
        return "Weiterleitung ausgeschaltet – Mission Control ist nur noch im Agent-PC erreichbar."
    _require_installed(machine)
    if not machine.is_running():
        raise RuntimeError("Der Agent-PC muss laufen, damit die Weiterleitung eingerichtet werden kann.")
    _require_running(machine)
    port = _ensure_forward_port(machine)
    rc, _out = machine.run_logged(guest_forward_script(True), password=password, ssh_prompt=ssh_prompt, timeout=60)
    if rc != 0:
        raise RuntimeError(f"Die Weiterleitung ließ sich im Agent-PC nicht einrichten (Code {rc}).")
    rule = forward_rule(port)
    with qemu.QMP(machine.runtime()["qmp_port"]) as q:
        q.hostfwd_remove(rule)
        q.hostfwd_add(rule)
    c.mc_forward = True
    machine.save()
    return f"Weiterleitung an: Mission Control ist auf diesem Rechner unter http://127.0.0.1:{port}/ erreichbar."


# ---------------------------------------------------------------- Vorlagen
def fresh_template_script() -> str:
    """Teil von ``generalize_script`` (frische Vorlage): Geheimnisse und Benutzerdaten entfernen, prüfen.

    Läuft mit ``$DRY`` (1 = nur anzeigen) und der Funktion ``wipe`` aus dem Verallgemeinern.
    """
    return r"""echo "== Mission Control =="
MC=""" + INSTALL_DIR + r"""
if [ -x "$MC/scripts/reset-secrets.sh" ] || [ -f "$MC/.env" ]; then
  if [ "$DRY" = 1 ]; then
    echo "WÜRDE AUSFÜHREN: $MC/scripts/reset-secrets.sh (Geheimnisse und Benutzerdaten von Mission Control)"
  else
    systemctl start docker.service >/dev/null 2>&1 || true
    if [ -x "$MC/scripts/reset-secrets.sh" ]; then
      "$MC/scripts/reset-secrets.sh" || { echo "FEHLER: reset-secrets.sh von Mission Control fehlgeschlagen."; exit 1; }
    else
      # deinstalliert, aber Einstellungen und Daten noch da
      rm -f "$MC/.env" && echo "gelöscht: $MC/.env"
      docker volume rm """ + VOLUME + r""" >/dev/null 2>&1 || true
    fi
    if command -v docker >/dev/null 2>&1 && docker volume inspect """ + VOLUME + r""" >/dev/null 2>&1; then
      echo "FEHLER: Die Benutzerdaten von Mission Control (Docker-Volume) sind noch da."; exit 1
    fi
    if [ -f "$MC/.env" ] && [ -f "$MC/.env.example" ]; then
      for k in $(sed -n 's/^\([A-Z0-9_]*\)=""" + SECRET_PLACEHOLDER + r"""$/\1/p' "$MC/.env.example"); do
        grep -qx "$k=""" + SECRET_PLACEHOLDER + r"""" "$MC/.env" || {
          echo "FEHLER: Ein Geheimnis von Mission Control ($k) wurde nicht zurückgesetzt."; exit 1; }
      done
    fi
    echo "Mission Control: Geheimnisse und Benutzerdaten entfernt – neue entstehen beim ersten Start."
  fi
fi"""
