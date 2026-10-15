# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN im Agent-PC – die Seite von Bony's Agents (Host).

Bony's VPN ist ein eigenes Projekt (https://github.com/zappotex/bonys-vpn). Im Agent-PC laufen die
Pakete ``bonys-vpn`` und ``bonys-vpn-agentpc`` aus dem offiziellen Release (siehe ``apps.VPN``).
Bony's Agents spricht nur über die offizielle Schnittstelle mit ihm: ``bonys-vpn … --json`` und den
Root-Helfer ``bonys-vpn-helper`` (beschrieben in ``docs/cli.md`` von bonys-vpn, Schema-Version 1).

Eine WireGuard-Konfiguration wird hier nur gelesen, grob geprüft (die vollständige Prüfung macht
der Helfer im Gast) und dann direkt in den Agent-PC gereicht:

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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bonys_agents.vm import VM

APP_ID = "vpn"
VPN_REPO = "zappotex/bonys-vpn"
VPN_REPO_URL = f"https://github.com/{VPN_REPO}"
# Schnittstelle von Bony's VPN, die diese Version von Bony's Agents versteht (docs/cli.md in bonys-vpn).
SCHEMA = 1
MIN_VERSION = "1.0.0"   # ältere Pakete werden über „VPN-App aktualisieren“ ersetzt

SEED_FILE = "bonys-vpn.conf"            # Name im Seed-ISO (Rock Ridge/Joliet)
GUEST_HELPER = "/usr/sbin/bonys-vpn-helper"
GUEST_CLI = "/usr/bin/bonys-vpn"
# Alte, eingebaute Fassung (Bony's Agents bis 0.14): lag unter /usr/local
LEGACY_HELPER = "/usr/local/sbin/bonys-vpn-helper"
LEGACY_CLI = "/usr/local/bin/bonys-vpn"
DONE_FILE = "/var/lib/bonys-agents/vpn-config.done"
IP_SERVICE = "https://api.ipify.org"
IP_SERVICE_NAME = "api.ipify.org"

CLONE_WARNING = ("Bony's VPN: Der Klon behält alle WireGuard-Tunnel samt Schlüssel. Zwei Agent-PCs mit demselben "
                 "Schlüssel können bei den meisten Anbietern (auch bei der FRITZ!Box) nicht gleichzeitig "
                 "verbunden sein – sie werfen sich gegenseitig aus dem Tunnel. Für jeden Agent-PC am besten "
                 "eine eigene Konfiguration verwenden.")
FRESH_CLEANUP = ("Bony's VPN: alle WireGuard-Tunnel und Schlüssel in /etc/wireguard, automatisches Verbinden "
                 "und Kill-Switch aus")

# ---------------------------------------------------------------- .conf grob prüfen
MAX_SIZE = 64 * 1024
HIDDEN = "(verborgen)"
HOOK_KEYS = ("PreUp", "PostUp", "PreDown", "PostDown")
_NAME_RE = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")
_ENDPOINT_RE = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9_.-]{1,253}):(\d{1,5})$")
_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw480]=$")  # 32 Byte in Base64
NAME_RULE = "Tunnelname: 1–15 Zeichen, nur A–Z, a–z, 0–9 und _ = + . -"


class VpnError(RuntimeError):
    pass


def check_name(name: str) -> str:
    """Gültiger Tunnelname (wie in Bony's VPN) – sonst ValueError."""
    if not isinstance(name, str) or not _NAME_RE.match(name) or name in (".", ".."):
        raise ValueError(NAME_RULE)
    return name


def suggest_name(stem: str) -> str:
    """Gültiger Tunnelname aus einem Dateinamen."""
    base = re.sub(r"[^a-zA-Z0-9_=+.-]", "_", stem).lstrip("-.")[:15] or "tunnel"
    return "tunnel" if base in (".", "..") else base


@dataclass(frozen=True)
class ConfInfo:
    hooks: tuple[str, ...]
    endpoint: str


def inspect_conf(data: bytes) -> ConfInfo:
    """Grobe Prüfung einer WireGuard-Konfiguration – ValueError nennt nur Zeilennummern, nie Werte.

    Die vollständige Prüfung macht der Helfer von Bony's VPN im Agent-PC. Hier geht es darum,
    offensichtlich falsche Dateien gleich beim Auswählen abzulehnen und Hook-Zeilen zu erkennen.
    """
    if len(data) > MAX_SIZE:
        raise ValueError("Die Datei ist zu groß für eine WireGuard-Konfiguration (höchstens 64 KiB).")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Die Datei ist keine Textdatei (UTF-8).") from None
    if not text.strip():
        raise ValueError("Die Datei ist leer.")
    section, interfaces, peers, private_key = "", 0, 0, False
    peer_keys: list[bool] = []
    hooks: list[str] = []
    endpoint = ""
    for no, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            if section == "interface":
                interfaces += 1
            elif section == "peer":
                peers += 1
                peer_keys.append(False)
            else:
                raise ValueError(f"Zeile {no}: unbekannter Abschnitt (erlaubt: [Interface], [Peer]).")
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise ValueError(f"Zeile {no}: erwartet „Name = Wert“.")
        if not section:
            raise ValueError(f"Zeile {no}: steht vor [Interface].")
        lkey = key.lower()
        if section == "interface" and lkey == "privatekey":
            if not _KEY_RE.match(value):
                raise ValueError(f"Zeile {no}: PrivateKey ist kein gültiger WireGuard-Schlüssel.")
            private_key = True
        elif section == "interface" and lkey in (h.lower() for h in HOOK_KEYS):
            hooks.append(next(h for h in HOOK_KEYS if h.lower() == lkey))
        elif section == "peer" and lkey == "publickey":
            if not _KEY_RE.match(value):
                raise ValueError(f"Zeile {no}: PublicKey ist kein gültiger WireGuard-Schlüssel.")
            peer_keys[-1] = True
        elif section == "peer" and lkey == "endpoint":
            m = _ENDPOINT_RE.match(value)
            if not m or not 1 <= int(m.group(2)) <= 65535:
                raise ValueError(f"Zeile {no}: Endpoint muss „Server:Port“ sein (Port 1–65535).")
            endpoint = endpoint or value
    if interfaces != 1 or not private_key:
        raise ValueError("Es fehlt genau ein Abschnitt [Interface] mit PrivateKey.")
    if not peers or not all(peer_keys):
        raise ValueError("Es fehlt ein Abschnitt [Peer] mit PublicKey.")
    return ConfInfo(hooks=tuple(dict.fromkeys(hooks)), endpoint=endpoint)


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
    """.conf lesen und grob prüfen. Fehler → ValueError (nennt nie Werte aus der Datei)."""
    path = Path(path).expanduser()
    try:
        if path.stat().st_size > MAX_SIZE:
            raise ValueError(f"{path.name} ist zu groß für eine WireGuard-Konfiguration (höchstens 64 KiB).")
        data = path.read_bytes()
    except OSError as e:
        raise ValueError(f"{path} lässt sich nicht lesen: {e.strerror}") from None
    try:
        info = inspect_conf(data)
    except ValueError as e:
        raise ValueError(f"{path.name} ist keine gültige WireGuard-Konfiguration: {e}") from None
    if info.hooks:
        raise ValueError(f"{path.name} enthält Befehle, die beim Verbinden als root laufen "
                         f"({', '.join(info.hooks)}). Solche Konfigurationen nur im Agent-PC über Bony's VPN "
                         "importieren – dort mit ausdrücklicher Warnung.")
    name = name or suggest_name(path.stem)
    try:
        check_name(name)
    except ValueError:
        raise ValueError(f"Tunnelname „{name}“: 1–15 Zeichen, nur A–Z, a–z, 0–9 und _ = + . -") from None
    return VpnSetup(name=name, data=data, autoconnect=autoconnect, killswitch=killswitch, endpoint=info.endpoint)


def guest_import_script(setup: VpnSetup, helper: str = GUEST_HELPER, done_file: str = DONE_FILE,
                        legacy_helper: str = LEGACY_HELPER) -> str:
    """POSIX-Shell (als root im Gast, am Ende der Einrichtung): Konfiguration aus dem Seed-ISO übernehmen.

    Der Inhalt steht nirgends im Skript. Der Helfer liest ihn von der Standardeingabe und schreibt
    ihn nur nach /etc/wireguard (600). Das ISO wird nur lesend eingehängt. Ausgaben des Helfers gehen
    nach /dev/null, damit nichts davon in Konsole oder Protokoll landet. Vorlagen aus Bony's Agents 0.14 haben
    noch die alte Fassung unter /usr/local – dann deren Helfer (umgestellt wird beim ersten Start).
    ``helper``/``done_file``/``legacy_helper`` nur für Tests.
    """
    done = shlex.quote(done_file)
    pick = f'VPN_H={shlex.quote(helper)}; [ -x "$VPN_H" ] || VPN_H={shlex.quote(legacy_helper)}'
    helper = '"$VPN_H"'
    name = shlex.quote(setup.name)
    lines = [
        "# Bony's VPN: mitgebrachte WireGuard-Konfiguration übernehmen (liegt nur im Seed-ISO)",
        f'if [ ! -f {done} ]; then',
        f"  {pick}",
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


# ---------------------------------------------------------------- Versionen
def _version_key(text: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def compat(st: dict) -> str:
    """Passt Bony's VPN im Agent-PC zu dieser Version von Bony's Agents?

    ``""`` = ja · ``"missing"`` = nicht installiert · ``"legacy"`` = alte, eingebaute Fassung (bis 0.14)
    · ``"outdated"`` = Paket älter als ``MIN_VERSION`` · ``"newer"`` = neueres Schema, Bony's Agents zu alt.
    """
    if not st.get("installed", True):
        return "missing"
    if st.get("legacy") or "schema" not in st:
        return "legacy"
    if st.get("schema") != SCHEMA:
        return "newer" if isinstance(st.get("schema"), int) and st["schema"] > SCHEMA else "outdated"
    have, need = _version_key(st.get("version", "")), _version_key(MIN_VERSION)
    if have is None or need is None or have < need:
        return "outdated"
    return ""


COMPAT_TEXT = {
    "legacy": "Im Agent-PC läuft noch die alte, eingebaute Fassung von Bony's VPN. „VPN-App aktualisieren“ "
              "stellt auf das Paket bonys-vpn um – Tunnel und Schlüssel bleiben, wie sie sind.",
    "outdated": f"Bony's VPN im Agent-PC ist älter als {MIN_VERSION} – bitte „VPN-App aktualisieren“.",
    "newer": "Bony's VPN im Agent-PC ist neuer, als diese Version von Bony's Agents versteht – bitte Bony's "
             "Agents aktualisieren. Status und Steuerung gehen bis dahin über die App im Agent-PC.",
}


# ---------------------------------------------------------------- Laufender Agent-PC
def _guest(machine: VM, argv: list[str], stdin: bytes | None = None, password: str | None = None,
           ssh_prompt: bool = False, timeout: float = 90) -> str:
    """Programm im Gast als root: Gast-Agent, sonst SSH mit sudo. Gibt stdout zurück, Fehler → VpnError."""
    from bonys_agents import qemu, vm

    if not machine.is_running():
        raise VpnError(f"„{machine.name}“ läuft nicht.")
    try:
        with qemu.GuestAgent(qemu.runtime_target(machine.runtime(), "qga"), timeout=5) as ga:
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
        msg = scrub(err.strip() or out.strip())
        raise VpnError(_error_text(msg) or f"Befehl im Agent-PC mit Code {rc} beendet.")
    return out


def _error_text(msg: str) -> str:
    """Fehlermeldung aus ``bonys-vpn … --json`` ({"error": …}) oder vom Helfer („Fehler: …“)."""
    start = msg.find("{")
    if start >= 0:
        try:
            data = json.loads(msg[start:])
            if isinstance(data, dict) and data.get("error"):
                return str(data["error"])
        except ValueError:
            pass
    return msg.removeprefix("Fehler: ")


_KEYLIKE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=")


def scrub(text: str) -> str:
    """Alles entfernen, was wie ein WireGuard-Schlüssel aussieht (doppelte Sicherung, wie im Helfer)."""
    return _KEYLIKE.sub(HIDDEN, text)[-400:]


def _json(out: str) -> dict:
    try:
        data = json.loads(out[out.find("{"):])
    except ValueError:
        raise VpnError("Unerwartete Antwort von Bony's VPN im Agent-PC.") from None
    if not isinstance(data, dict):
        raise VpnError("Unerwartete Antwort von Bony's VPN im Agent-PC.")
    return data


# Status: neues Paket, sonst alte Fassung unter /usr/local (dort ohne „schema“), sonst „nicht installiert“
STATUS_SCRIPT = (f"if [ -x {GUEST_CLI} ] && [ -x {GUEST_HELPER} ]; then exec {GUEST_CLI} status --json; "
                 f"elif [ -x {LEGACY_CLI} ]; then printf '{{\"legacy\": true}}\\n'; {LEGACY_CLI} status --json; "
                 "else echo '{\"installed\": false}'; fi")


def status(machine: VM, **kw) -> dict:
    """``bonys-vpn status --json`` im Gast, dazu ``installed`` und ``compat`` (siehe ``compat``)."""
    out = _guest(machine, ["/bin/sh", "-c", STATUS_SCRIPT], **kw)
    legacy = out.lstrip().startswith('{"legacy": true}')
    if legacy:
        out = out.split("\n", 1)[1] if "\n" in out.lstrip() else "{}"
        try:
            data = _json(out)
        except VpnError:
            data = {}
        data["legacy"] = True
    else:
        data = _json(out)
    data.setdefault("installed", True)
    data["compat"] = compat(data)
    return data


def usable(st: dict) -> bool:
    """Lässt sich Bony's VPN mit diesem Status steuern? (alte Fassung: ja, ihre CLI kennt dieselben Befehle)"""
    return bool(st.get("installed", True)) and st.get("compat") != "newer"


def default_tunnel(st: dict) -> str | None:
    """Tunnel für „Verbinden“ ohne Namen: der aktive, sonst der mit Autostart, sonst der einzige."""
    tunnels = [t for t in st.get("tunnels") or [] if isinstance(t, dict) and t.get("name")]
    if st.get("active"):
        return st["active"]
    auto = [t["name"] for t in tunnels if t.get("autostart")]
    if auto:
        return auto[0]
    return tunnels[0]["name"] if len(tunnels) == 1 else None


def _cli(machine: VM, args: list[str], **kw) -> str:
    """``bonys-vpn ARGS`` im Gast (als root ruft die CLI den Helfer direkt auf). Alte Fassung als Ausweich."""
    script = (f'if [ -x {GUEST_CLI} ]; then exec {GUEST_CLI} "$@"; '
              f'elif [ -x {LEGACY_CLI} ]; then exec {LEGACY_CLI} "$@"; '
              "else echo \"Fehler: Bony's VPN ist im Agent-PC nicht installiert.\" >&2; exit 1; fi")
    return _guest(machine, ["/bin/sh", "-c", script, "bonys-vpn", *args], **kw)


def _helper_path_script() -> str:
    return f'H={GUEST_HELPER}; [ -x "$H" ] || H={LEGACY_HELPER}; exec "$H" "$@"'


def up(machine: VM, tunnel: str, **kw) -> None:
    _cli(machine, ["up", check_name(tunnel)], **kw)


def down(machine: VM, tunnel: str | None = None, **kw) -> None:
    _cli(machine, ["down"] + ([check_name(tunnel)] if tunnel else []), **kw)


def set_killswitch(machine: VM, on: bool, **kw) -> None:
    _cli(machine, ["killswitch", "an" if on else "aus"], **kw)


def set_autostart(machine: VM, tunnel: str, on: bool, **kw) -> None:
    _cli(machine, ["autostart", check_name(tunnel), "an" if on else "aus"], **kw)


def import_conf(machine: VM, setup: VpnSetup, replace: bool = False, **kw) -> None:
    """Konfiguration über die Standardeingabe des Helfers importieren – keine Datei im Gast oder auf dem Host."""
    _guest(machine, ["/bin/sh", "-c", _helper_path_script(), "bonys-vpn-helper", "import", check_name(setup.name)]
           + (["--replace"] if replace else []), stdin=setup.data, **kw)
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


# ---------------------------------------------------------------- VPN-App installieren / umstellen
def update_app(machine: VM, password: str | None = None, ssh_prompt: bool = False,
               log: Callable[[str], None] | None = None) -> None:
    """Bony's VPN im laufenden Agent-PC installieren bzw. auf das neueste Paket umstellen.

    Derselbe Installationsschritt wie bei „Programme hinzufügen“ (``apps.VPN``): lädt die Pakete aus dem
    offiziellen Release, prüft Signatur und SHA-256 und installiert sie mit apt. Die alte Fassung unter
    /usr/local räumt das Paket dabei selbst auf. /etc/wireguard (Tunnel und Schlüssel) und der Zustand des
    Kill-Switch bleiben unverändert.
    """
    from bonys_agents import apps, cloudinit

    if not machine.is_running() or not machine.progress().ready or machine.config.first_boot_pending:
        raise VpnError(f"„{machine.name}“ muss laufen und fertig eingerichtet sein.")
    # Ausgabe geht auch auf die serielle Konsole – so zeigt die App sie live (wie beim Aktualisieren)
    script = cloudinit.app_install_script(apps.VPN, machine.config.username, force=True)
    rc, out = machine.run_logged(script, password=password, ssh_prompt=ssh_prompt, log=log, timeout=20 * 60)
    if apps.VPN_BLOCKED_HINT in out:
        raise VpnError("Der Kill-Switch ist an, aber kein Tunnel verbunden – ohne VPN kann der Agent-PC das Paket "
                       "nicht laden. Erst den Tunnel verbinden, dann aktualisieren.")
    if rc != 0:
        raise VpnError(f"Bony's VPN ließ sich nicht installieren (Code {rc}) – siehe Ausgabe.")
    if APP_ID not in machine.config.apps:
        machine.config.apps = [a for a in apps.APPS if a in machine.config.apps or a == APP_ID] \
            + [a for a in machine.config.apps if a not in apps.APPS]
        machine.save()


def needs_update(machine: VM) -> bool:
    """Nur über den Gast-Agent (ohne Passwort): Läuft im Agent-PC eine alte bzw. zu alte Fassung?"""
    from bonys_agents import vm

    try:
        st = status(machine)
    except (VpnError, vm.NeedsPassword):
        return False
    return st.get("compat") in ("legacy", "outdated")


# ---------------------------------------------------------------- Anzeige
def human_bytes(n: int | None) -> str:
    n = float(n or 0)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


def human_age(ts: int | None, now: float | None = None) -> str:
    if not ts:
        return "noch keiner"
    s = int((now or time.time()) - ts)
    if s < 60:
        return f"vor {s} s"
    if s < 3600:
        return f"vor {s // 60} min"
    return f"vor {s // 3600} h {s % 3600 // 60} min"


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
    if st.get("version") and not st.get("legacy"):
        parts.append(f"Bony's VPN {st['version']}")
    return " · ".join(parts)
