# SPDX-License-Identifier: GPL-3.0-or-later
"""bonys-vpn-helper – läuft als root (über pkexec) und darf nur genau diese Aktionen:

  list | status [NAME] | show NAME | up NAME | down [NAME] | import NAME [--allow-hooks] [--replace]
  delete NAME | rename ALT NEU | export NAME | autostart NAME on|off
  killswitch on [--exception NETZ ...] | killswitch off | killswitch status

Regeln: Tunnelnamen nur ``[a-zA-Z0-9_=+.-]{1,15}``, keine Pfade (Konfigurationen kommen über die
Standardeingabe), keine Shell (subprocess nur mit Argumentlisten und festem PATH), Dateien in
/etc/wireguard mit Rechten 600 und root:root. Private Schlüssel erscheinen nie in Ausgaben –
außer bei ``export``, das genau dafür da ist.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from . import conf as wgconf
from . import killswitch

ETC_WG = Path("/etc/wireguard")
STATE_DIR = Path("/etc/bonys-vpn")
KS_UNIT = "bonys-vpn-killswitch.service"
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
_KEYLIKE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=")


class HelperError(Exception):
    """Fehler mit deutscher Meldung für den Benutzer."""


def scrub(text: str) -> str:
    """Alles, was wie ein WireGuard-Schlüssel aussieht, aus Ausgaben fremder Programme entfernen."""
    return _KEYLIKE.sub(wgconf.HIDDEN, text)


def clean_env(path: str = SAFE_PATH) -> dict[str, str]:
    """Umgebung für Programme, die der Helfer als root startet: nur ein fester PATH und die Sprache."""
    return {"PATH": path, "LC_ALL": "C.UTF-8"}


def wg_unit(name: str) -> str:
    """systemd-Unit ``wg-quick@NAME.service``. Die Unit gibt den Namen roh (%i) an wg-quick weiter –
    Zeichen, die systemd escapen müsste („+“, „=“), gehen deshalb nicht."""
    if not re.fullmatch(r"[A-Za-z0-9:_.-]+", wgconf.check_name(name)):
        raise HelperError(f"Automatisch verbinden geht nicht bei „{name}“ – „+“ und „=“ sind im Namen "
                          "einer systemd-Unit nicht erlaubt. Bitte den Tunnel umbenennen.")
    return f"wg-quick@{name}.service"


class Helper:
    def __init__(self, etc_wg: Path = ETC_WG, state_dir: Path = STATE_DIR, path: str = SAFE_PATH,
                 as_root: bool = True, resolve=socket.getaddrinfo):
        self.etc_wg = Path(etc_wg)
        self.state_dir = Path(state_dir)
        self.path = path
        self.as_root = as_root
        self.resolve = resolve

    # ---------- Grundlagen ----------
    def _run(self, *args: str, check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
        tool = shutil.which(args[0], path=self.path)
        if not tool:
            pkg = {"wg": "wireguard-tools", "wg-quick": "wireguard-tools", "nft": "nftables"}.get(args[0], args[0])
            raise HelperError(f"Das Programm „{args[0]}“ fehlt (Paket {pkg}).")
        try:
            proc = subprocess.run([tool, *args[1:]], input=input, capture_output=True, text=True, timeout=90,
                                  env=clean_env(self.path),
                                  stdin=None if input else subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise HelperError(f"„{args[0]}“ hat nicht rechtzeitig geantwortet.") from None
        if check and proc.returncode != 0:
            detail = scrub((proc.stderr or proc.stdout).strip())[-600:]
            raise HelperError(f"„{' '.join(args[:2])}“ ist fehlgeschlagen (Code {proc.returncode}): {detail}")
        return proc

    def _conf_path(self, name: str) -> Path:
        return self.etc_wg / f"{wgconf.check_name(name)}.conf"

    def _ensure_dirs(self) -> None:
        for d in (self.etc_wg, self.state_dir):
            if d.is_symlink():
                raise HelperError(f"{d} ist ein symbolischer Link – aus Sicherheitsgründen abgebrochen.")
        self.etc_wg.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    @contextlib.contextmanager
    def _lock(self):
        self._ensure_dirs()
        fd = os.open(self.state_dir / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _write_atomic(self, path: Path, text: str, mode: int = 0o600) -> None:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".bonys-vpn-")
        try:
            os.fchmod(fd, mode)
            if self.as_root:
                os.fchown(fd, 0, 0)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def _read_conf(self, name: str) -> str:
        path = self._conf_path(name)
        if path.is_symlink() or not path.is_file():
            raise HelperError(f"Den Tunnel „{name}“ gibt es nicht.")
        return path.read_text("utf-8", errors="replace")

    def _require_managed(self, name: str) -> str:
        text = self._read_conf(name)
        if not wgconf.is_managed(text):
            raise HelperError(f"Der Tunnel „{name}“ wurde nicht mit Bony's VPN angelegt – "
                              "ändern, exportieren und löschen geht nur bei eigenen Tunneln.")
        return text

    # ---------- Zustand ----------
    def names(self) -> list[str]:
        if not self.etc_wg.is_dir():
            return []
        out = []
        for p in sorted(self.etc_wg.glob("*.conf")):
            try:
                wgconf.check_name(p.stem)
            except wgconf.ConfError:
                continue
            if p.is_file() and not p.is_symlink():
                out.append(p.stem)
        return out

    def managed_names(self) -> list[str]:
        out = []
        for n in self.names():
            with contextlib.suppress(OSError):
                if wgconf.is_managed(self._read_conf(n)):
                    out.append(n)
        return out

    def active(self) -> list[str]:
        proc = self._run("wg", "show", "interfaces", check=False)
        return proc.stdout.split() if proc.returncode == 0 else []

    def autostart_enabled(self, name: str) -> bool:
        try:
            unit = wg_unit(name)
        except HelperError:
            return False
        proc = self._run("systemctl", "is-enabled", unit, check=False)
        return proc.stdout.strip() == "enabled"

    def _ks_config(self) -> dict:
        try:
            data = json.loads((self.state_dir / "killswitch.json").read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        exceptions = []
        for n in data.get("exceptions", []):
            with contextlib.suppress(ValueError, AttributeError):
                exceptions.append(killswitch.check_exception(n))
        return {"enabled": bool(data.get("enabled")), "exceptions": exceptions,
                "resolved": data.get("resolved") if isinstance(data.get("resolved"), dict) else {}}

    def _save_ks_config(self, cfg: dict) -> None:
        self._write_atomic(self.state_dir / "killswitch.json", json.dumps(cfg, indent=2) + "\n", 0o644)

    def ks_active(self) -> bool:
        return self._run("nft", "list", "table", "inet", killswitch.TABLE, check=False).returncode == 0

    def _tunnel_info(self, name: str, active: list[str]) -> dict:
        info: dict = {"name": name, "active": name in active, "autostart": self.autostart_enabled(name)}
        try:
            text = self._read_conf(name)
            info["managed"] = wgconf.is_managed(text)
            info.update(wgconf.parse(text).summary())
        except (wgconf.ConfError, HelperError) as e:
            info["error"] = str(e)
        return info

    def _live(self, name: str) -> dict:
        """Laufzeitwerte eines aktiven Tunnels – nur über die Teilbefehle von ``wg show``, die keine
        geheimen Schlüssel enthalten (nicht ``dump``)."""
        peers: dict[str, dict] = {}
        for sub, fields in (("endpoints", ("endpoint",)), ("latest-handshakes", ("handshake",)),
                            ("transfer", ("rx", "tx"))):
            proc = self._run("wg", "show", name, sub, check=False)
            for line in proc.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) != len(fields) + 1:
                    continue
                p = peers.setdefault(parts[0], {"public_key": parts[0]})
                for f, v in zip(fields, parts[1:], strict=True):
                    p[f] = int(v) if v.isdigit() else (None if v == "(none)" else v)
        handshakes = [p.get("handshake") or 0 for p in peers.values()]
        return {"handshake": max(handshakes, default=0) or None,
                "rx": sum(p.get("rx", 0) for p in peers.values()),
                "tx": sum(p.get("tx", 0) for p in peers.values()),
                "peers_live": list(peers.values())}

    # ---------- Aktionen ----------
    def list(self) -> dict:
        active = self.active()
        return {"tunnels": [{"name": n, "active": n in active, "autostart": self.autostart_enabled(n),
                             "managed": n in self.managed_names()} for n in self.names()]}

    def status(self, name: str | None = None) -> dict:
        active = self.active()
        names = [wgconf.check_name(name)] if name else self.names()
        if name and name not in self.names():
            raise HelperError(f"Den Tunnel „{name}“ gibt es nicht.")
        tunnels = []
        for n in names:
            info = self._tunnel_info(n, active)
            if info["active"]:
                info.update(self._live(n))
            tunnels.append(info)
        cfg = self._ks_config()
        return {"tunnels": tunnels,
                "active": next((n for n in self.names() if n in active), None),
                "killswitch": {"enabled": cfg["enabled"], "active": self.ks_active(),
                               "exceptions": cfg["exceptions"]}}

    def show(self, name: str) -> dict:
        text = self._read_conf(name)
        body = "\n".join(line for line in text.split("\n") if line.strip() != wgconf.MARKER).strip("\n") + "\n"
        return {"name": name, "managed": wgconf.is_managed(text), "conf": wgconf.mask(body)}

    def up(self, name: str) -> None:
        with self._lock():
            wgconf.parse(self._read_conf(name))  # vor dem Start noch einmal prüfen
            active = self.active()
            if name in active:
                return
            for other in self.managed_names():
                if other in active:
                    self._run("wg-quick", "down", other)
            if self._ks_config()["enabled"]:
                self._apply_killswitch()
            self._run("wg-quick", "up", name)

    def down(self, name: str | None = None) -> None:
        with self._lock():
            active = self.active()
            if name:
                self._read_conf(name)
                targets = [name] if name in active else []
            else:
                targets = [n for n in self.managed_names() if n in active]
            for n in targets:
                self._run("wg-quick", "down", n)

    def import_conf(self, name: str, data: bytes, allow_hooks: bool = False, replace: bool = False) -> dict:
        wgconf.check_name(name)
        text = wgconf.decode(data)
        with self._lock():
            path = self._conf_path(name)
            if path.exists() or path.is_symlink():
                if not replace:
                    raise HelperError(f"Den Tunnel „{name}“ gibt es schon.")
                text = wgconf.unmask(text, self._require_managed(name))
            parsed = wgconf.parse(text)
            if parsed.hooks and not allow_hooks:
                raise HelperError("Die Konfiguration enthält Befehle, die beim Verbinden als root laufen ("
                                  + ", ".join(parsed.hooks) + "). Sie wird nur nach ausdrücklicher "
                                  "Bestätigung importiert (--allow-hooks).")
            self._write_atomic(path, wgconf.with_marker(text))
            if self._ks_config()["enabled"]:
                self._apply_killswitch()
        return {"name": name, **parsed.summary()}

    def delete(self, name: str) -> None:
        with self._lock():
            self._require_managed(name)
            if name in self.active():
                self._run("wg-quick", "down", name)
            if self.autostart_enabled(name):
                self._run("systemctl", "disable", wg_unit(name))
            self._conf_path(name).unlink()
            if self._ks_config()["enabled"]:
                self._apply_killswitch()

    def rename(self, old: str, new: str) -> None:
        wgconf.check_name(new)
        with self._lock():
            text = self._require_managed(old)
            new_path = self._conf_path(new)
            if new_path.exists() or new_path.is_symlink():
                raise HelperError(f"Den Tunnel „{new}“ gibt es schon.")
            if old in self.active():
                raise HelperError(f"Der Tunnel „{old}“ ist verbunden – bitte zuerst trennen.")
            autostart = self.autostart_enabled(old)
            if autostart:
                self._run("systemctl", "disable", wg_unit(old))
            self._write_atomic(new_path, text)
            self._conf_path(old).unlink()
            if autostart:
                self._run("systemctl", "enable", wg_unit(new))
            if self._ks_config()["enabled"]:
                self._apply_killswitch()

    def export(self, name: str) -> str:
        text = self._require_managed(name)
        return "\n".join(line for line in text.split("\n") if line.strip() != wgconf.MARKER).lstrip("\n")

    def autostart(self, name: str, on: bool) -> None:
        with self._lock():
            self._read_conf(name)
            if on:
                for other in self.managed_names():  # nur ein Tunnel verbindet sich automatisch
                    if other != name and self.autostart_enabled(other):
                        self._run("systemctl", "disable", wg_unit(other))
            self._run("systemctl", "enable" if on else "disable", wg_unit(name))

    # ---------- Kill-Switch ----------
    def _endpoints(self, cfg: dict) -> list[tuple[str, int]]:
        """Endpunkte aller Tunnel als (IP, Port). DNS-Namen werden aufgelöst; klappt das nicht,
        gelten die zuletzt bekannten Adressen weiter."""
        result: list[tuple[str, int]] = []
        resolved: dict[str, list] = {}
        for n in self.names():
            try:
                parsed = wgconf.parse(self._read_conf(n))
            except (wgconf.ConfError, HelperError):
                continue
            for peer in parsed.peers:
                if not peer.endpoint:
                    continue
                host, port = peer.endpoint
                key = wgconf.format_endpoint(peer.endpoint)
                try:
                    killswitch.check_exception(host)
                    ips = [host]
                except ValueError:
                    try:
                        ips = sorted({ai[4][0] for ai in self.resolve(host, port, 0, socket.SOCK_DGRAM)})
                    except OSError:
                        ips = [ip for ip in cfg["resolved"].get(key, []) if isinstance(ip, str)]
                        print(f"Hinweis: Der Endpunkt „{host}“ ließ sich nicht auflösen"
                              + (" – die zuletzt bekannte Adresse gilt weiter." if ips else "."), file=sys.stderr)
                    resolved[key] = ips
                for ip in ips:
                    with contextlib.suppress(ValueError):
                        killswitch.check_exception(ip)
                        result.append((ip, port))
        cfg["resolved"] = resolved
        return result

    def _dns_uids(self) -> list[int]:
        uids = [0]
        with contextlib.suppress(KeyError):
            uids.append(pwd.getpwnam("systemd-resolve").pw_uid)
        return uids

    def _apply_killswitch(self) -> None:
        cfg = self._ks_config()
        rules = killswitch.ruleset(self.names(), self._endpoints(cfg), cfg["exceptions"], self._dns_uids())
        path = self.state_dir / "killswitch.nft"
        self._write_atomic(path, rules, 0o644)
        self._run("nft", "-f", str(path))
        self._save_ks_config(cfg)

    def killswitch_on(self, exceptions: list[str] | None = None) -> None:
        with self._lock():
            cfg = self._ks_config()
            if exceptions is not None:
                try:
                    cfg["exceptions"] = [killswitch.check_exception(n) for n in exceptions]
                except ValueError:
                    raise HelperError("Ungültige Ausnahme – erwartet wird eine IP-Adresse oder ein Netz "
                                      "wie 10.0.2.0/24.") from None
            cfg["enabled"] = True
            self._save_ks_config(cfg)
            self._apply_killswitch()
            self._run("systemctl", "enable", KS_UNIT)

    def killswitch_off(self) -> None:
        with self._lock():
            cfg = self._ks_config()
            cfg["enabled"] = False
            self._save_ks_config(cfg)
            self._run("systemctl", "disable", KS_UNIT, check=False)
            if self.ks_active():
                self._run("nft", "delete", "table", "inet", killswitch.TABLE)
            (self.state_dir / "killswitch.nft").unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bonys-vpn-helper", description="Root-Helfer von Bony's VPN (über pkexec).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("status").add_argument("name", nargs="?")
    sub.add_parser("show").add_argument("name")
    sub.add_parser("up").add_argument("name")
    sub.add_parser("down").add_argument("name", nargs="?")
    imp = sub.add_parser("import")
    imp.add_argument("name")
    imp.add_argument("--allow-hooks", action="store_true")
    imp.add_argument("--replace", action="store_true")
    sub.add_parser("delete").add_argument("name")
    ren = sub.add_parser("rename")
    ren.add_argument("old")
    ren.add_argument("new")
    sub.add_parser("export").add_argument("name")
    auto = sub.add_parser("autostart")
    auto.add_argument("name")
    auto.add_argument("state", choices=["on", "off"])
    ks = sub.add_parser("killswitch")
    ks.add_argument("state", choices=["on", "off", "status"])
    ks.add_argument("--exception", action="append", metavar="NETZ")
    return p


def main(argv: list[str] | None = None, helper: Helper | None = None, stdin=None, stdout=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout
    args = _parser().parse_args(argv)
    if helper is None:
        if os.geteuid() != 0:
            print("Fehler: Der Helfer muss als root laufen (Aufruf über pkexec).", file=sys.stderr)
            return 1
        os.umask(0o077)
        helper = Helper()

    def out(data) -> None:
        stdout.write(json.dumps(data, ensure_ascii=False) + "\n")

    try:
        for attr in ("name", "old", "new"):
            if getattr(args, attr, None) is not None:
                wgconf.check_name(getattr(args, attr))
        cmd = args.cmd
        if cmd == "list":
            out(helper.list())
        elif cmd == "status":
            out(helper.status(args.name))
        elif cmd == "show":
            out(helper.show(args.name))
        elif cmd == "up":
            helper.up(args.name)
        elif cmd == "down":
            helper.down(args.name)
        elif cmd == "import":
            data = stdin.read(wgconf.MAX_SIZE + 1)
            out(helper.import_conf(args.name, data, allow_hooks=args.allow_hooks, replace=args.replace))
        elif cmd == "delete":
            helper.delete(args.name)
        elif cmd == "rename":
            helper.rename(args.old, args.new)
        elif cmd == "export":
            stdout.write(helper.export(args.name))
        elif cmd == "autostart":
            helper.autostart(args.name, args.state == "on")
        elif cmd == "killswitch":
            if args.state == "on":
                helper.killswitch_on(args.exception)
            elif args.state == "off":
                helper.killswitch_off()
            out(helper.status()["killswitch"])
    except (HelperError, wgconf.ConfError) as e:
        print(f"Fehler: {scrub(str(e))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
