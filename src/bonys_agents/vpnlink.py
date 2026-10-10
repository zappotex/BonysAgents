# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN im Agent-PC – die Seite von Bony's Agents (Host).

Eine WireGuard-Konfiguration wird hier nur gelesen und geprüft (mit derselben Prüfung wie der
Root-Helfer im Gast) und dann direkt in den Agent-PC gereicht:

- beim Erstellen über das Seed-ISO (Datei ``bonys-vpn.conf`` neben user-data). Der Gast importiert
  sie am Ende der Einrichtung über den Helfer. Das Seed-ISO löscht Bony's Agents nach der
  Einrichtung ohnehin (es enthält auch das Passwort),
- im laufenden Agent-PC über die Standardeingabe des Helfers (Gast-Agent, sonst SSH).

Auf dem Host bleibt nichts liegen: kein Feld in vm.json, keine Protokollzeile, kein Fortschrittstext
mit Inhalt. ``VpnSetup`` zeigt die Daten auch in ``repr`` nicht.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from bonys_agents.vpn import conf as wgconf
from bonys_agents.vpn.model import suggest_name

if TYPE_CHECKING:
    from bonys_agents.vm import VM

APP_ID = "vpn"
SEED_FILE = "bonys-vpn.conf"            # Name im Seed-ISO (Rock Ridge/Joliet)
GUEST_HELPER = "/usr/local/sbin/bonys-vpn-helper"
GUEST_CLI = "/usr/local/bin/bonys-vpn"
DONE_FILE = "/var/lib/bonys-agents/vpn-config.done"
IP_SERVICE = "https://api.ipify.org"
IP_SERVICE_NAME = "api.ipify.org"

CLONE_WARNING = ("Bony's VPN: Der Klon behält alle WireGuard-Tunnel samt Schlüssel. Zwei Agent-PCs mit demselben "
                 "Schlüssel können bei den meisten Anbietern (auch bei der FRITZ!Box) nicht gleichzeitig "
                 "verbunden sein – sie werfen sich gegenseitig aus dem Tunnel. Für jeden Agent-PC am besten "
                 "eine eigene Konfiguration verwenden.")
FRESH_CLEANUP = ("Bony's VPN: alle WireGuard-Tunnel und Schlüssel in /etc/wireguard, automatisches Verbinden "
                 "und Kill-Switch aus")


class VpnError(RuntimeError):
    pass


@dataclass(frozen=True)
class VpnSetup:
    """Mitgebrachte WireGuard-Konfiguration für einen neuen Agent-PC (nur im Speicher)."""

    name: str
    data: bytes = field(repr=False)
    autoconnect: bool = False
    killswitch: bool = False
    endpoint: str = ""   # nur zur Anzeige


def load_conf(path: Path | str, name: str | None = None, autoconnect: bool = False,
              killswitch: bool = False) -> VpnSetup:
    """.conf lesen und prüfen wie der Helfer. Fehler → ValueError (nennt nie Werte aus der Datei)."""
    path = Path(path).expanduser()
    try:
        if path.stat().st_size > wgconf.MAX_SIZE:
            raise ValueError(f"{path.name} ist zu groß für eine WireGuard-Konfiguration (höchstens 64 KiB).")
        data = path.read_bytes()
    except OSError as e:
        raise ValueError(f"{path} lässt sich nicht lesen: {e.strerror}") from None
    try:
        parsed = wgconf.parse(wgconf.decode(data))
    except wgconf.ConfError as e:
        raise ValueError(f"{path.name} ist keine gültige WireGuard-Konfiguration: {e}") from None
    if parsed.hooks:
        raise ValueError(f"{path.name} enthält Befehle, die beim Verbinden als root laufen "
                         f"({', '.join(parsed.hooks)}). Solche Konfigurationen nur im Agent-PC über Bony's VPN "
                         "importieren – dort mit ausdrücklicher Warnung.")
    name = name or suggest_name(path.stem)
    try:
        wgconf.check_name(name)
    except wgconf.ConfError:
        raise ValueError(f"Tunnelname „{name}“: 1–15 Zeichen, nur A–Z, a–z, 0–9 und _ = + . -") from None
    endpoint = next((wgconf.format_endpoint(p.endpoint) for p in parsed.peers if p.endpoint), "")
    return VpnSetup(name=name, data=data, autoconnect=autoconnect, killswitch=killswitch, endpoint=endpoint)


def guest_import_script(setup: VpnSetup, helper: str = GUEST_HELPER, done_file: str = DONE_FILE) -> str:
    """POSIX-Shell (als root im Gast, am Ende der Einrichtung): Konfiguration aus dem Seed-ISO übernehmen.

    Der Inhalt steht nirgends im Skript. Der Helfer liest ihn von der Standardeingabe und schreibt
    ihn nur nach /etc/wireguard (600). Das ISO wird nur lesend eingehängt. Ausgaben des Helfers gehen
    nach /dev/null, damit nichts davon in Konsole oder Protokoll landet. ``helper``/``done_file`` nur für Tests.
    """
    helper, done = shlex.quote(helper), shlex.quote(done_file)
    name = shlex.quote(setup.name)
    lines = [
        "# Bony's VPN: mitgebrachte WireGuard-Konfiguration übernehmen (liegt nur im Seed-ISO)",
        f'if [ ! -f {done} ]; then',
        f'  echo "Bony\'s VPN: übernehme die WireGuard-Konfiguration „{setup.name}“ …"',
        '  VPN_MNT="$(mktemp -d)"',
        '  VPN_DEV="$(blkid -t LABEL=cidata -o device 2>/dev/null | head -n1)"',
        '  [ -n "$VPN_DEV" ] || VPN_DEV="$(blkid -t LABEL=CIDATA -o device 2>/dev/null | head -n1)"',
        '  VPN_OK=""',
        '  if [ -n "$VPN_DEV" ] && mount -o ro "$VPN_DEV" "$VPN_MNT" 2>/dev/null; then',
        f'    if [ -x {helper} ] && [ -f "$VPN_MNT/{SEED_FILE}" ] \\',
        f'       && {helper} import {name} --replace < "$VPN_MNT/{SEED_FILE}" >/dev/null; then',
        "      VPN_OK=1",
        "    fi",
        '    umount "$VPN_MNT" 2>/dev/null || true',
        "  fi",
        '  rmdir "$VPN_MNT" 2>/dev/null || true',
        '  if [ -n "$VPN_OK" ]; then',
    ]
    if setup.autoconnect:
        lines += [f"    {helper} autostart {name} on >/dev/null "
                  '|| echo "WARNUNG: Automatisches Verbinden ließ sich nicht einschalten."',
                  '    echo "Bony\'s VPN: verbindet sich ab dem nächsten Start automatisch."']
    if setup.killswitch:
        # Zuletzt: Ab hier geht ohne Tunnel nichts mehr ins Internet (Steuerung über 10.0.2.0/24 bleibt).
        lines += [f"    {helper} killswitch on >/dev/null "
                  '|| echo "WARNUNG: Kill-Switch ließ sich nicht einschalten."',
                  '    echo "Bony\'s VPN: Kill-Switch ist an – ohne Tunnel kein Internet."']
    lines += [
        f'    mkdir -p "$(dirname {done})" && touch {done}',
        '    echo "Bony\'s VPN: Konfiguration übernommen."',
        "  else",
        '    echo "WARNUNG: Die WireGuard-Konfiguration ließ sich nicht übernehmen – später im Agent-PC importieren."',
        "  fi",
        "fi",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- Laufender Agent-PC
def _guest(machine: VM, argv: list[str], stdin: bytes | None = None, password: str | None = None,
           ssh_prompt: bool = False, timeout: float = 90) -> str:
    """Programm im Gast als root: Gast-Agent, sonst SSH mit sudo. Gibt stdout zurück, Fehler → VpnError."""
    from bonys_agents import qemu, vm

    if not machine.is_running():
        raise VpnError(f"„{machine.name}“ läuft nicht.")
    try:
        with qemu.GuestAgent(machine.runtime().get("qga_port") or 0, timeout=5) as ga:
            rc, out, err = ga.exec(argv[0], argv[1:], stdin=stdin if stdin is not None else b"", timeout=timeout)
    except qemu.GuestAgentError:
        if not password and not ssh_prompt:
            raise vm.NeedsPassword("Der Gast-Agent antwortet nicht – für SSH wird das Passwort "
                                   "des Agent-PCs gebraucht.") from None
        lines: list[str] = []
        rc = machine._ssh("sudo " + shlex.join(argv), (stdin or b"").decode("utf-8"), password, lines.append)
        if rc == 255:
            raise VpnError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?") from None
        out, err = "\n".join(lines), "\n".join(lines)
    except RuntimeError as e:  # z. B. Programm fehlt im Gast
        raise VpnError(f"Befehl im Agent-PC fehlgeschlagen: {e}") from None
    if rc != 0:
        msg = wgconf_scrub(err.strip() or out.strip())
        raise VpnError(msg.removeprefix("Fehler: ") or f"Befehl im Agent-PC mit Code {rc} beendet.")
    return out


_KEYLIKE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=")


def wgconf_scrub(text: str) -> str:
    """Alles entfernen, was wie ein WireGuard-Schlüssel aussieht (doppelte Sicherung, wie im Helfer)."""
    return _KEYLIKE.sub(wgconf.HIDDEN, text)[-400:]


def installed(machine: VM, **kw) -> bool:
    out = _guest(machine, ["/bin/sh", "-c", f"[ -x {GUEST_HELPER} ] && [ -x {GUEST_CLI} ] && echo ja || echo nein"],
                 **kw)
    return out.strip().endswith("ja")


def status(machine: VM, **kw) -> dict:
    """``bonys-vpn status --json`` im Gast. Ohne Bony's VPN: ``{"installed": False}``."""
    script = (f"if [ -x {GUEST_CLI} ]; then exec {GUEST_CLI} status --json; "
              "else echo '{\"installed\": false}'; fi")
    out = _guest(machine, ["/bin/sh", "-c", script], **kw)
    try:
        data = json.loads(out[out.find("{"):])
    except ValueError:
        raise VpnError("Unerwartete Antwort von Bony's VPN im Agent-PC.") from None
    data.setdefault("installed", True)
    return data


def default_tunnel(st: dict) -> str | None:
    """Tunnel für „Verbinden“ ohne Namen: der aktive, sonst der mit Autostart, sonst der einzige."""
    tunnels = st.get("tunnels") or []
    if st.get("active"):
        return st["active"]
    auto = [t["name"] for t in tunnels if t.get("autostart")]
    if auto:
        return auto[0]
    return tunnels[0]["name"] if len(tunnels) == 1 else None


def up(machine: VM, tunnel: str, **kw) -> None:
    _guest(machine, [GUEST_CLI, "up", wgconf.check_name(tunnel)], **kw)


def down(machine: VM, tunnel: str | None = None, **kw) -> None:
    _guest(machine, [GUEST_CLI, "down"] + ([wgconf.check_name(tunnel)] if tunnel else []), **kw)


def set_killswitch(machine: VM, on: bool, **kw) -> None:
    _guest(machine, [GUEST_CLI, "killswitch", "an" if on else "aus"], **kw)


def set_autostart(machine: VM, tunnel: str, on: bool, **kw) -> None:
    _guest(machine, [GUEST_CLI, "autostart", wgconf.check_name(tunnel), "an" if on else "aus"], **kw)


def import_conf(machine: VM, setup: VpnSetup, replace: bool = False, **kw) -> None:
    """Konfiguration über die Standardeingabe des Helfers importieren – keine Datei im Gast oder auf dem Host."""
    _guest(machine, [GUEST_HELPER, "import", wgconf.check_name(setup.name)] + (["--replace"] if replace else []),
           stdin=setup.data, **kw)
    if setup.autoconnect:
        set_autostart(machine, setup.name, True, **kw)
    if setup.killswitch:
        set_killswitch(machine, True, **kw)


def public_ip(machine: VM, **kw) -> str:
    """Öffentliche IP, wie sie Programme im Agent-PC sehen (als dessen Benutzer, über ``IP_SERVICE``)."""
    user = shlex.quote(machine.config.username)
    script = f"runuser -u {user} -- curl -fsS --max-time 10 {IP_SERVICE}"
    try:
        out = _guest(machine, ["/bin/sh", "-c", script], timeout=30, **kw)
    except VpnError:
        raise VpnError(f"Kein Internet im Agent-PC ({IP_SERVICE_NAME} nicht erreichbar).") from None
    try:
        return str(ipaddress.ip_address(out.strip()))
    except ValueError:
        raise VpnError(f"Unerwartete Antwort von {IP_SERVICE_NAME}.") from None


def human_bytes(n: int | None) -> str:
    from bonys_agents.vpn.cli import human_bytes as hb

    return hb(n)


def human_age(ts: int | None) -> str:
    from bonys_agents.vpn.cli import human_age as ha

    return ha(ts)


def summary(st: dict) -> str:
    """Eine Zeile für Anzeige und Kommandozeile."""
    if not st.get("installed", True):
        return "Bony's VPN ist nicht installiert."
    ks = st.get("killswitch") or {}
    active = st.get("active")
    parts = [f"verbunden – Tunnel „{active}“" if active else "getrennt"]
    if ks.get("enabled"):
        parts.append("Kill-Switch an" + ("" if active else " – ohne Tunnel kein Internet"))
    if not st.get("tunnels"):
        parts.append("noch kein Tunnel eingerichtet")
    return " · ".join(parts)
