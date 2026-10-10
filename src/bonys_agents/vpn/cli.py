# SPDX-License-Identifier: GPL-3.0-or-later
"""bonys-vpn – WireGuard-Tunnel verwalten (Kommandozeile für den Benutzer).

Läuft als normaler Benutzer und ruft für alles, was root braucht, ``bonys-vpn-helper`` über
``pkexec`` auf. Konfigurationsdateien liest die Kommandozeile selbst (mit den Rechten des
Benutzers) und reicht sie über die Standardeingabe weiter – der Helfer bekommt nie einen Pfad.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import conf as wgconf

HELPER = "/usr/local/sbin/bonys-vpn-helper"     # install.py (Agent-PC)
DEB_HELPER = "/usr/sbin/bonys-vpn-helper"        # .deb von Bony's Agents (eigener Rechner)


def clean_env() -> dict[str, str]:
    """Umgebung für externe Programme – ohne Variablen, die fremde Bibliotheken oder Python-Pfade einschleusen."""
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME"):
        env.pop(var, None)
    return env


class CliError(Exception):
    pass


def helper_path() -> str:
    """Pfad des Helfers: ``BONYS_VPN_HELPER``, sonst der installierte (install.py vor .deb)."""
    if os.environ.get("BONYS_VPN_HELPER"):
        return os.environ["BONYS_VPN_HELPER"]
    return next((p for p in (HELPER, DEB_HELPER) if Path(p).exists()), HELPER)


def call(args: list[str], data: bytes | None = None) -> str:
    """Helfer aufrufen (als root direkt, sonst über pkexec). Gibt stdout zurück, Fehler → CliError."""
    helper = helper_path()
    if os.geteuid() == 0:
        cmd = [helper, *args]
    else:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise CliError("pkexec fehlt (Paket pkexec) – ohne geht es nur als root.")
        cmd = [pkexec, helper, *args]
    if not Path(helper).exists():
        raise CliError(f"Der Helfer {helper} ist nicht installiert.")
    proc = subprocess.run(cmd, input=data if data is not None else b"", capture_output=True, env=clean_env())
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode in (126, 127) and not err.startswith("Fehler:"):
        raise CliError("Keine Berechtigung – die Anmeldung wurde abgebrochen oder abgelehnt.")
    if proc.returncode != 0:
        raise CliError(err.removeprefix("Fehler: ") or f"Der Helfer ist mit Code {proc.returncode} beendet.")
    if err:
        print(err, file=sys.stderr)  # Hinweise des Helfers
    return proc.stdout.decode("utf-8", errors="replace")


def call_json(args: list[str], data: bytes | None = None):
    out = call(args, data)
    try:
        return json.loads(out)
    except ValueError:
        raise CliError("Unerwartete Antwort des Helfers.") from None


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


def confs_from(path: Path) -> list[tuple[str, bytes]]:
    """(Vorschlag für den Namen, Inhalt) aus einer .conf oder einer ZIP-Datei mit .conf-Dateien."""
    try:
        if zipfile.is_zipfile(path):
            out = []
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    base = info.filename.rsplit("/", 1)[-1]
                    if info.is_dir() or not base.lower().endswith(".conf"):
                        continue
                    if info.file_size > wgconf.MAX_SIZE:
                        raise CliError(f"{base} in {path.name} ist zu groß.")
                    out.append((base[:-5], z.read(info)))
            if not out:
                raise CliError(f"In {path.name} ist keine .conf-Datei.")
            return out
        if path.stat().st_size > wgconf.MAX_SIZE:
            raise CliError(f"{path.name} ist zu groß für eine WireGuard-Konfiguration.")
        return [(path.stem, path.read_bytes())]
    except OSError as e:
        raise CliError(f"{path} lässt sich nicht lesen: {e.strerror}") from None


def cmd_list(_args) -> None:
    data = call_json(["list"])
    if not data["tunnels"]:
        print("Noch keine Tunnel. Importieren mit: bonys-vpn import DATEI.conf")
        return
    print(f"{'NAME':<16} {'STATUS':<10} {'AUTOSTART':<10}")
    for t in data["tunnels"]:
        extra = "" if t.get("managed") else "  (nicht von Bony's VPN angelegt)"
        print(f"{t['name']:<16} {'verbunden' if t['active'] else 'getrennt':<10} "
              f"{'an' if t['autostart'] else 'aus':<10}{extra}")


def print_status(data: dict) -> None:
    ks = data["killswitch"]
    ks_text = "an" if ks["enabled"] else "aus"
    if ks["enabled"] != ks["active"]:
        ks_text += " (Regeln " + ("aktiv" if ks["active"] else "nicht geladen") + ")"
    print(f"Kill-Switch: {ks_text}" + (f" – Ausnahmen: {', '.join(ks['exceptions'])}" if ks["exceptions"] else ""))
    if not data["tunnels"]:
        print("Noch keine Tunnel.")
    for t in data["tunnels"]:
        print()
        print(f"{t['name']}: {'verbunden' if t['active'] else 'getrennt'}"
              f"{', verbindet sich automatisch' if t['autostart'] else ''}")
        if t.get("error"):
            print(f"  Fehler in der Konfiguration: {t['error']}")
            continue
        print(f"  Adresse:   {', '.join(t.get('addresses', [])) or '–'}")
        print(f"  DNS:       {', '.join(t.get('dns', [])) or '–'}")
        eps = [p["endpoint"] for p in t.get("peers", []) if p.get("endpoint")]
        print(f"  Endpunkt:  {', '.join(eps) or '–'}")
        if t["active"]:
            print(f"  Handshake: {human_age(t.get('handshake'))}")
            print(f"  Daten:     {human_bytes(t.get('rx'))} empfangen, {human_bytes(t.get('tx'))} gesendet")
        if t.get("hooks"):
            print(f"  Achtung:   führt beim Verbinden Befehle als root aus ({', '.join(t['hooks'])})")


def cmd_status(args) -> None:
    data = call_json(["status"] + ([args.name] if args.name else []))
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_status(data)


def cmd_up(args) -> None:
    call(["up", args.name])
    print(f"„{args.name}“ ist verbunden.")


def cmd_down(args) -> None:
    call(["down"] + ([args.name] if args.name else []))
    print(f"„{args.name}“ ist getrennt." if args.name else "Alle Tunnel sind getrennt.")


def cmd_import(args) -> None:
    items: list[tuple[str, bytes]] = []
    for f in args.files:
        items += confs_from(Path(f).expanduser())
    if args.name and len(items) != 1:
        raise CliError("--name geht nur beim Import einer einzelnen Konfiguration.")
    if args.allow_hooks:
        print("Achtung: Hook-Zeilen (PreUp/PostUp/PreDown/PostDown) laufen beim Verbinden als root. "
              "Nur importieren, wenn du der Datei vertraust.", file=sys.stderr)
    failed = 0
    for name, data in items:
        name = args.name or name
        try:
            wgconf.check_name(name)
        except wgconf.ConfError as e:
            print(f"{name}: {e} Mit --name einen anderen Namen wählen.", file=sys.stderr)
            failed += 1
            continue
        extra = (["--allow-hooks"] if args.allow_hooks else []) + (["--replace"] if args.replace else [])
        try:
            call(["import", name, *extra], data)
        except CliError as e:
            print(f"{name}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"„{name}“ importiert.")
    if failed:
        raise CliError(f"{failed} von {len(items)} Konfiguration(en) nicht importiert.")


def cmd_delete(args) -> None:
    if not args.yes:
        if not sys.stdin.isatty():
            raise CliError("Zum Löschen ohne Rückfrage --ja angeben.")
        if input(f"Tunnel „{args.name}“ mit seinem Schlüssel löschen? [j/N] ").strip().lower() not in ("j", "ja"):
            print("Abgebrochen.")
            return
    call(["delete", args.name])
    print(f"„{args.name}“ gelöscht.")


def cmd_rename(args) -> None:
    call(["rename", args.old, args.new])
    print(f"„{args.old}“ heißt jetzt „{args.new}“.")


def cmd_export(args) -> None:
    target = Path(args.file).expanduser() if args.file else Path(f"{args.name}.conf")
    if target.exists():
        raise CliError(f"{target} gibt es schon.")
    text = call(["export", args.name])
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Exportiert nach {target} (nur für dich lesbar – enthält den privaten Schlüssel).")


def cmd_autostart(args) -> None:
    on = args.state in ("on", "an")
    call(["autostart", args.name, "on" if on else "off"])
    print(f"„{args.name}“ verbindet sich {'jetzt' if on else 'nicht mehr'} automatisch beim Start.")


def cmd_killswitch(args) -> None:
    state = {"an": "on", "aus": "off"}.get(args.state, args.state)
    extra = [x for net in (args.exception or []) for x in ("--exception", net)]
    data = call_json(["killswitch", state, *extra])
    text = "an" if data["enabled"] else "aus"
    print(f"Kill-Switch: {text}" + (f" – Ausnahmen: {', '.join(data['exceptions'])}" if data["exceptions"] else ""))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bonys-vpn", description="Bony's VPN – WireGuard-Tunnel verwalten.")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="BEFEHL")
    sub.add_parser("list", help="Tunnel auflisten").set_defaults(func=cmd_list)
    st = sub.add_parser("status", help="Status, Handshake, Datenmenge, Kill-Switch")
    st.add_argument("name", nargs="?")
    st.add_argument("--json", action="store_true", help="maschinenlesbar")
    st.set_defaults(func=cmd_status)
    up = sub.add_parser("up", help="Tunnel verbinden (trennt einen anderen)")
    up.add_argument("name")
    up.set_defaults(func=cmd_up)
    down = sub.add_parser("down", help="Tunnel trennen (ohne Namen: alle)")
    down.add_argument("name", nargs="?")
    down.set_defaults(func=cmd_down)
    imp = sub.add_parser("import", help="Konfiguration(en) importieren (.conf oder .zip)")
    imp.add_argument("files", nargs="+", metavar="DATEI")
    imp.add_argument("--name", help="Name des Tunnels (sonst der Dateiname)")
    imp.add_argument("--hooks-erlauben", dest="allow_hooks", action="store_true",
                     help="PreUp/PostUp/PreDown/PostDown zulassen (laufen als root!)")
    imp.add_argument("--ersetzen", dest="replace", action="store_true", help="vorhandenen Tunnel ersetzen")
    imp.set_defaults(func=cmd_import)
    de = sub.add_parser("delete", help="Tunnel löschen")
    de.add_argument("name")
    de.add_argument("--ja", dest="yes", action="store_true", help="ohne Rückfrage")
    de.set_defaults(func=cmd_delete)
    ren = sub.add_parser("rename", help="Tunnel umbenennen")
    ren.add_argument("old", metavar="ALT")
    ren.add_argument("new", metavar="NEU")
    ren.set_defaults(func=cmd_rename)
    ex = sub.add_parser("export", help="Konfiguration exportieren (mit privatem Schlüssel)")
    ex.add_argument("name")
    ex.add_argument("file", nargs="?", metavar="DATEI")
    ex.set_defaults(func=cmd_export)
    au = sub.add_parser("autostart", help="beim Start automatisch verbinden")
    au.add_argument("name")
    au.add_argument("state", choices=["on", "off", "an", "aus"])
    au.set_defaults(func=cmd_autostart)
    ks = sub.add_parser("killswitch", help="Kill-Switch: ohne Tunnel kein Internet")
    ks.add_argument("state", choices=["on", "off", "status", "an", "aus"])
    ks.add_argument("--ausnahme", dest="exception", action="append", metavar="NETZ",
                    help="Netz, das immer erreichbar bleibt (z. B. 192.168.178.0/24); ersetzt die Liste")
    ks.set_defaults(func=cmd_killswitch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except CliError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
