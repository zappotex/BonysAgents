# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN installieren: Helfer, Kommandozeile, polkit-Dateien und systemd-Unit an ihren Platz legen.

Eigenständig lauffähig (nur Standardbibliothek, keine Importe aus dem Paket), als root:

    python3 -I install.py --variant agent --user agent     # im Agent-PC: Benutzer ohne Passwort
    python3 -I install.py --variant host                   # auf dem Host: Administrator-Passwort
    python3 -I install.py --uninstall

Braucht die Debian-Pakete python3, wireguard-tools, nftables, pkexec, polkitd. Für das DNS-Feld
einer .conf ruft wg-quick ``resolvconf`` auf – das bringt systemd-resolved mit (so im Agent-PC),
sonst openresolv.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ("__init__.py", "conf.py", "killswitch.py", "helper.py", "cli.py", "install.py")

LIB_DIR = "usr/local/lib/bonys-vpn"
PKG = "bonys_vpn"
HELPER = "usr/local/sbin/bonys-vpn-helper"
CLI = "usr/local/bin/bonys-vpn"
POLICY = "usr/share/polkit-1/actions/io.github.bonys-agents.vpn.policy"
RULES = "etc/polkit-1/rules.d/50-bonys-vpn.rules"
UNIT = "etc/systemd/system/bonys-vpn-killswitch.service"
STATE_DIR = "etc/bonys-vpn"
# Steuerung des Agent-PCs: QEMU-User-Netz (SSH-Weiterleitung, Host 10.0.2.2, DNS 10.0.2.3).
# Der Gast-Agent läuft über virtio-serial und braucht kein Netz.
AGENT_EXCEPTIONS = ["10.0.2.0/24"]
PACKAGES = ["wireguard-tools", "nftables", "pkexec", "polkitd"]

def clean_env() -> dict[str, str]:
    """Umgebung für externe Programme – ohne Variablen, die fremde Bibliotheken oder Python-Pfade einschleusen."""
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME"):
        env.pop(var, None)
    return env


WRAPPER = """#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-3.0-or-later
# {what} – installiert von Bony's VPN
import sys

sys.path.insert(0, "/{lib}")
from {pkg}.{module} import main  # noqa: E402

sys.exit(main())
"""


def _write(path: Path, text: str, mode: int, as_root: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    if as_root:
        os.chown(tmp, 0, 0)
    os.replace(tmp, path)


def install(variant: str, user: str = "agent", root: Path = Path("/"), as_root: bool = True) -> list[Path]:
    """Alle Dateien schreiben. Gibt die geschriebenen Pfade zurück."""
    if variant not in ("agent", "host"):
        raise ValueError("variant muss agent oder host sein")
    if variant == "agent" and not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise ValueError("ungültiger Benutzername")
    root = Path(root)
    written = []

    def put(rel: str, text: str, mode: int = 0o644) -> None:
        p = root / rel
        _write(p, text, mode, as_root)
        written.append(p)

    for m in MODULES:
        put(f"{LIB_DIR}/{PKG}/{m}", (HERE / m).read_text("utf-8"))
    put(HELPER, WRAPPER.format(what="Root-Helfer (über pkexec)", lib=LIB_DIR, pkg=PKG, module="helper"), 0o755)
    put(CLI, WRAPPER.format(what="Kommandozeile", lib=LIB_DIR, pkg=PKG, module="cli"), 0o755)
    data = HERE / "data"
    put(POLICY, (data / "io.github.bonys-agents.vpn.policy").read_text("utf-8").replace("@HELPER@", f"/{HELPER}"))
    put(RULES, (data / f"{variant}.rules").read_text("utf-8").replace("@USER@", user))
    put(UNIT, (data / "bonys-vpn-killswitch.service").read_text("utf-8"))
    state = root / STATE_DIR
    state.mkdir(mode=0o755, parents=True, exist_ok=True)
    cfg = state / "killswitch.json"
    if not cfg.exists():
        put(f"{STATE_DIR}/killswitch.json", json.dumps(
            {"enabled": False, "exceptions": AGENT_EXCEPTIONS if variant == "agent" else []}, indent=2) + "\n")
    (root / "etc/wireguard").mkdir(mode=0o700, parents=True, exist_ok=True)
    return written


def uninstall(root: Path = Path("/")) -> None:
    """Programmdateien entfernen. Tunnel in /etc/wireguard bleiben, der Kill-Switch wird abgeschaltet."""
    root = Path(root)
    helper = root / HELPER
    if root == Path("/") and helper.exists():
        subprocess.run([str(helper), "killswitch", "off"], capture_output=True, env=clean_env())
    for rel in (HELPER, CLI, POLICY, RULES, UNIT):
        (root / rel).unlink(missing_ok=True)
    shutil.rmtree(root / LIB_DIR, ignore_errors=True)
    for rel in ("killswitch.json", "killswitch.nft", ".lock"):
        (root / STATE_DIR / rel).unlink(missing_ok=True)
    try:
        (root / STATE_DIR).rmdir()
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bony's VPN installieren (als root).")
    p.add_argument("--variant", choices=["agent", "host"], default="host")
    p.add_argument("--user", default="agent", help="Benutzer im Agent-PC, der ohne Passwort darf")
    p.add_argument("--root", default="/", help="Zielverzeichnis (zum Bauen von Paketen)")
    p.add_argument("--uninstall", action="store_true")
    args = p.parse_args(argv)
    as_root = os.geteuid() == 0
    if args.root == "/" and not as_root:
        print("Fehler: Bitte als root ausführen.", file=sys.stderr)
        return 1
    if args.uninstall:
        uninstall(Path(args.root))
    else:
        install(args.variant, args.user, Path(args.root), as_root)
    if args.root == "/" and shutil.which("systemctl"):
        subprocess.run(["systemctl", "daemon-reload"], check=False, env=clean_env())
    print("Bony's VPN " + ("entfernt." if args.uninstall else f"installiert ({args.variant})."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
