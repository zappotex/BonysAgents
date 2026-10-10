# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN installieren: Helfer, Kommandozeile, polkit-Dateien und systemd-Unit an ihren Platz legen.

Eigenständig lauffähig (nur Standardbibliothek, keine Importe aus dem Paket), als root:

    python3 -I install.py --variant agent --user agent --autostart-tray   # im Agent-PC: ohne Passwort
    python3 -I install.py --variant host                   # auf dem Host: Administrator-Passwort
    python3 -I install.py --uninstall

Braucht die Debian-Pakete python3, wireguard-tools, nftables, pkexec, polkitd, für die Oberfläche
zusätzlich python3-gi, gir1.2-gtk-3.0 und (Tray) gir1.2-ayatanaappindicator3-0.1. Für das DNS-Feld
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
MODULES = ("__init__.py", "conf.py", "killswitch.py", "helper.py", "cli.py", "install.py", "model.py", "gui.py")
# Von der Oberfläche zur Laufzeit gebraucht (relativ zu data/)
GUI_DATA = ("bonys-vpn.png", "icons/bonys-vpn-connected.svg", "icons/bonys-vpn-disconnected.svg",
            "icons/bonys-vpn-blocked.svg", "icons/bonys-vpn-warning.svg")

LIB_DIR = "usr/local/lib/bonys-vpn"
PKG = "bonys_vpn"
HELPER = "usr/local/sbin/bonys-vpn-helper"
CLI = "usr/local/bin/bonys-vpn"
GUI = "usr/local/bin/bonys-vpn-gui"
DESKTOP = "usr/local/share/applications/io.github.bonys_agents.vpn.desktop"
AUTOSTART = "etc/xdg/autostart/bonys-vpn-tray.desktop"
POLICY = "usr/share/polkit-1/actions/io.github.bonys-agents.vpn.policy"
RULES = "etc/polkit-1/rules.d/50-bonys-vpn.rules"
UNIT = "etc/systemd/system/bonys-vpn-killswitch.service"
# Layout „system“: Dateien im .deb von Bony's Agents (eigener Rechner). Die Oberfläche ist dort die
# Qt-Fassung in Bony's Agents, deshalb ohne GTK-Oberfläche. Nichts unter /etc (keine Conffiles) –
# /etc/bonys-vpn und /etc/wireguard legt der Helfer bei Bedarf selbst an.
SYSTEM = {
    "lib": "usr/lib/bonys-agents/vpn",
    "helper": "usr/sbin/bonys-vpn-helper",
    "cli": "usr/bin/bonys-vpn",
    "rules": "usr/share/polkit-1/rules.d/50-bonys-vpn.rules",
    "unit": "usr/lib/systemd/system/bonys-vpn-killswitch.service",
}
STATE_DIR = "etc/bonys-vpn"
# Steuerung des Agent-PCs: QEMU-User-Netz (SSH-Weiterleitung, Host 10.0.2.2, DNS 10.0.2.3).
# Der Gast-Agent läuft über virtio-serial und braucht kein Netz.
AGENT_EXCEPTIONS = ["10.0.2.0/24"]
PACKAGES = ["wireguard-tools", "nftables", "pkexec", "polkitd"]
GUI_PACKAGES = ["python3-gi", "gir1.2-gtk-3.0", "gir1.2-ayatanaappindicator3-0.1"]

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


def _write_bytes(path: Path, data: bytes, as_root: bool, mode: int = 0o644) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    if as_root:
        os.chown(tmp, 0, 0)
    os.replace(tmp, path)


def install(variant: str, user: str = "agent", root: Path = Path("/"), as_root: bool = True,
            autostart_tray: bool = False, layout: str = "local") -> list[Path]:
    """Alle Dateien schreiben. Gibt die geschriebenen Pfade zurück.

    ``layout="local"``: feste Orte unter /usr/local (Agent-PC). ``layout="system"``: Orte im .deb
    (nur ``variant="host"``, ohne GTK-Oberfläche, nichts unter /etc).
    """
    if variant not in ("agent", "host"):
        raise ValueError("variant muss agent oder host sein")
    if layout not in ("local", "system"):
        raise ValueError("layout muss local oder system sein")
    if layout == "system" and variant != "host":
        raise ValueError("layout system gibt es nur für den eigenen Rechner (host)")
    if variant == "agent" and not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise ValueError("ungültiger Benutzername")
    system = layout == "system"
    lib = SYSTEM["lib"] if system else LIB_DIR
    helper = SYSTEM["helper"] if system else HELPER
    root = Path(root)
    written = []

    def put(rel: str, text: str, mode: int = 0o644) -> None:
        p = root / rel
        _write(p, text, mode, as_root)
        written.append(p)

    modules = [m for m in MODULES if not (system and m == "gui.py")]
    for m in modules:
        put(f"{lib}/{PKG}/{m}", (HERE / m).read_text("utf-8"))
    put(helper, WRAPPER.format(what="Root-Helfer (über pkexec)", lib=lib, pkg=PKG, module="helper"), 0o755)
    put(SYSTEM["cli"] if system else CLI, WRAPPER.format(what="Kommandozeile", lib=lib, pkg=PKG, module="cli"), 0o755)
    data = HERE / "data"
    policy = (data / "io.github.bonys-agents.vpn.policy").read_text("utf-8").replace("@HELPER@", f"/{helper}")
    rules = (data / f"{variant}.rules").read_text("utf-8").replace("@USER@", user).replace("@HELPER@", f"/{helper}")
    unit = (data / "bonys-vpn-killswitch.service").read_text("utf-8")
    if system:
        put(POLICY, policy)
        put(SYSTEM["rules"], rules)
        put(SYSTEM["unit"], unit)
        return written
    put(GUI, WRAPPER.format(what="Oberfläche", lib=LIB_DIR, pkg=PKG, module="gui"), 0o755)
    for rel in GUI_DATA:
        p = root / LIB_DIR / PKG / "data" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes(p, (data / rel).read_bytes(), as_root)
        written.append(p)
    icon = f"/{LIB_DIR}/{PKG}/data/bonys-vpn.png"
    put(DESKTOP, (data / "io.github.bonys_agents.vpn.desktop").read_text("utf-8")
        .replace("@GUI@", f"/{GUI}").replace("@ICON@", icon))
    if autostart_tray:
        put(AUTOSTART, (data / "bonys-vpn-tray.desktop").read_text("utf-8")
            .replace("@GUI@", f"/{GUI}").replace("@ICON@", icon))
    else:
        (root / AUTOSTART).unlink(missing_ok=True)
    put(POLICY, policy)
    put(RULES, rules)
    put(UNIT, unit)
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
    for rel in (HELPER, CLI, GUI, DESKTOP, AUTOSTART, POLICY, RULES, UNIT):
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
    p.add_argument("--autostart-tray", action="store_true",
                   help="Tray-Symbol nach der Anmeldung starten (/etc/xdg/autostart)")
    p.add_argument("--layout", choices=["local", "system"], default="local",
                   help="system: Orte im .deb von Bony's Agents (nur mit --root zum Paketbau)")
    p.add_argument("--uninstall", action="store_true")
    args = p.parse_args(argv)
    as_root = os.geteuid() == 0
    if args.root == "/" and not as_root:
        print("Fehler: Bitte als root ausführen.", file=sys.stderr)
        return 1
    if args.layout == "system" and args.root == "/":
        print("Fehler: --layout system nur mit --root (die Dateien gehören dem .deb).", file=sys.stderr)
        return 1
    if args.uninstall:
        uninstall(Path(args.root))
    else:
        install(args.variant, args.user, Path(args.root), as_root, args.autostart_tray, args.layout)
    if args.root == "/" and shutil.which("systemctl"):
        subprocess.run(["systemctl", "daemon-reload"], check=False, env=clean_env())
    print("Bony's VPN " + ("entfernt." if args.uninstall else f"installiert ({args.variant})."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
