# SPDX-License-Identifier: GPL-3.0-or-later
"""Bildschirmfotos für das Handbuch – Bony's Agents im Vorführmodus mit erfundenen Beispieldaten.

    python docs/handbuch/vorfuehrung/bildschirmfotos.py --edition anwender  --ziel docs/handbuch/bilder
    python docs/handbuch/vorfuehrung/bildschirmfotos.py --edition kursleiter --ziel docs/handbuch/bilder

(``docs/handbuch/erstellen.sh`` ruft beides auf.) Jedes Fenster wird mit Qt selbst aufgenommen (``QWidget.grab()``)
– ohne Bildschirm (``QT_QPA_PLATFORM=offscreen``), auch unter Wayland.

Der Vorführmodus fasst nichts auf diesem Rechner an und liest nichts davon:

- Datenordner, Einstellungen und Bony-Netz-Anmeldung liegen in einem leeren Ordner unter /tmp (wird gelöscht).
- Agent-PCs, Vorlagen, Laufwerke, Rechnername, Netzadressen und der Host sind erfunden. Kein QEMU wird gestartet.
- Die Zentrale (``zentrale.py``) antwortet aus dem Speicher, der Kursraum läuft mit einer Attrappe von LiveKit
  (``livekit-attrappe.js``). Freigabe, Vorführung und Hilfe-Schalter zeigen erfundene Teilnehmer; es wird kein Port
  geöffnet und nichts im Netz angekündigt.
- Netzadressen kommen nur aus 192.168.178.0/24 (Beispiel-Heimnetz) und 100.64.0.0/10 (Bony-Netz).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
REPO = HIER.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HIER))

BREITE, HOEHE = 1280, 800
RECHNERNAME_ANWENDER = "annas-laptop"
RECHNERNAME_KURSLEITER = "kursleitung-pc"
ANZEIGE_HOME = "/home/anna"           # so sehen die Pfade aus (Kursleiter-Version: /home/eva)


def umgebung(edition: str) -> Path:
    """Vor dem ersten Import von bonys_agents: eigener, leerer Ordner für alles, Qt ohne Bildschirm."""
    wurzel = Path(tempfile.mkdtemp(prefix="bonys-handbuch-"))
    home = wurzel / "home"
    for d in ("daten", "config", "cache", "laufzeit", "bony-netz"):
        (wurzel / d).mkdir(parents=True)
    home.mkdir()
    (wurzel / "laufzeit").chmod(0o700)
    os.environ.update({
        "HOME": str(home), "XDG_DATA_HOME": str(wurzel / "daten"), "XDG_CONFIG_HOME": str(wurzel / "config"),
        "XDG_CACHE_HOME": str(wurzel / "cache"), "XDG_RUNTIME_DIR": str(wurzel / "laufzeit"),
        "BONY_NETZ_ORDNER": str(wurzel / "bony-netz"), "BONYS_AGENTS_EDITION": edition,
        "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_SCALE_FACTOR": "1",
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --disable-gpu-compositing --no-sandbox",
        "XDG_SESSION_TYPE": "x11", "LANG": "de_DE.UTF-8", "TZ": "Europe/Berlin",
        # Login-Name (z. B. „Ersteller“ beim Weitergeben einer Vorlage) – nie der echte
        "USER": "eva" if edition == "kursleiter" else "anna", "LOGNAME": "eva" if edition == "kursleiter" else "anna",
    })
    os.environ.pop("USERNAME", None)
    for weg in ("WAYLAND_DISPLAY", "DISPLAY", "SSH_AUTH_SOCK"):
        os.environ.pop(weg, None)
    time.tzset()
    return wurzel


# ====================================================================== Beispieldaten
# Agent-PCs: Name → (läuft, Einstellungen, Konsole)
def _konsole(schritte: list[str], bis: int, fertig: bool) -> str:
    gesamt = len(schritte)
    zeilen = ["[    0.000000] Linux version 6.12.48+deb13-amd64 (Debian 6.12.48-1)",
              "[    2.412093] systemd[1]: Detected virtualization kvm.",
              "[  OK  ] Started bonys-provision.service - Einrichtung von Bony's Agents."]
    for i, titel in enumerate(schritte[:bis], 1):
        zeilen.append(f"BONYS-STEP {i}/{gesamt} {titel}")
        zeilen.append(f"[bonys] {titel} …")
    if fertig:
        zeilen += ["[bonys] Alles eingerichtet.", "BONYS-AGENTS-READY",
                   "[  OK  ] Reached target graphical.target - Graphical Interface.",
                   "", "Debian GNU/Linux 13 agent-buero ttyS0", "", "agent-buero login:"]
    return "\n".join(zeilen) + "\n"


SCHRITTE = ["Sprache und Tastatur", "Mit dem Bony-Netz verbinden", "Desktop Cinnamon installieren",
            "Anmeldung und Bildschirm einrichten", "Brave Browser installieren", "Telegram Desktop installieren",
            "Hermes Agent installieren", "Fernzugriff (RDP) vorbereiten", "Bony's VPN installieren",
            "Aufräumen"]


def agent_pcs(bibliothek: Path, mit_netz: bool) -> None:
    from bonys_agents import vm

    pcs = {
        "agent-buero": dict(cpus=4, ram_mb=8192, disk_gb=64, desktop="cinnamon",
                            apps=["brave", "telegram", "hermes", "xrdp", "vpn", "mission-control", "docker"],
                            provisioned=True, rdp_port=3390, spice_port=5901, netz_name="agent-buero"),
        "agent-kurs": dict(cpus=4, ram_mb=6144, disk_gb=64, desktop="xfce", apps=["brave", "telegram", "hermes",
                           "xrdp"], provisioned=True, rdp_port=3391, spice_port=5902, netz_name="agent-kurs",
                           template="kurs-basis"),
        "agent-test": dict(cpus=2, ram_mb=4096, disk_gb=64, desktop="cinnamon", apps=["brave", "telegram", "hermes"],
                           first_boot_pending=True, setup_step=5, setup_total=len(SCHRITTE),
                           setup_title=SCHRITTE[4], rdp_port=3392, spice_port=5903),
    }
    konsolen = {"agent-buero": _konsole(SCHRITTE, len(SCHRITTE), True),
                "agent-kurs": _konsole(SCHRITTE, len(SCHRITTE), True),
                "agent-test": _konsole(SCHRITTE, 5, False)}
    for name, werte in pcs.items():
        if not mit_netz:
            werte.pop("netz_name", None)
        p = bibliothek / name
        p.mkdir(parents=True, exist_ok=True)
        cfg = vm.VMConfig(name=name, arch="x86_64", created="2026-10-12T09:30:00+00:00", **werte)
        app_info = {"hermes": {"version": "0.9.2"}, "mission-control": {"version": "0.1.0"}}
        cfg.app_info = {k: v for k, v in app_info.items() if k in cfg.apps}
        (p / "vm.json").write_text(json.dumps(cfg.__dict__), "utf-8")
        (p / "console.log").write_text(konsolen[name], "utf-8")


def vorlagen(bibliothek: Path) -> None:
    from bonys_agents import storage

    for name, text, apps, desktop, groesse in (
            ("kurs-basis", "Für den Kurs „Einführung in Hermes Agent“: Brave, Telegram, Hermes",
             ["brave", "telegram", "hermes", "xrdp"], "xfce", 3.4),
            ("buero-basis", "Mein fertig eingerichteter Büro-PC", ["brave", "telegram", "hermes", "xrdp"], "cinnamon",
             4.1)):
        d = bibliothek / "_templates" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "template.json").write_text(json.dumps({
            "name": name, "description": text, "created": "2026-10-14T18:05:00+00:00", "debian": "13.1",
            "arch": "x86_64", "apps": apps, "size": int(groesse * storage.GB), "disk_gb": 64, "source": "agent-buero",
            "desktop": desktop, "personal_data_removed": True, "format": 2}), "utf-8")
        (d / "disk.qcow2").write_bytes(b"")


# ====================================================================== Vorführmodus: Rechner ersetzen
class Laufend:
    """Welche Agent-PCs „laufen“ und was ihre Laufzeitdaten sind (statt QEMU)."""

    pcs: dict[str, dict] = {}


def vorfuehrmodus(wurzel: Path, kursleiter: bool) -> None:
    global ANZEIGE_HOME
    if kursleiter:
        ANZEIGE_HOME = "/home/eva"
    import psutil
    try:
        from psutil._ntuples import snicaddr
    except ImportError:   # psutil vor 7.2
        from psutil._common import snicaddr

    from bonys_agents import (
        deps, diagnose, host, mission_control, remote, share, storage, updates, vm, vpnlink,
    )

    rechner = RECHNERNAME_KURSLEITER if kursleiter else RECHNERNAME_ANWENDER
    socket.gethostname = lambda: rechner
    import platform

    platform.node = lambda: rechner

    # Host: ein typischer Linux-Rechner mit 8 Kernen und 16 GB
    echt = host.detect()

    def erfunden() -> host.HostInfo:
        felder = {**echt.__dict__, "os": "linux", "arch": "x86_64", "cpus": 8, "ram_mb": 16384, "accel": "kvm"}
        return type(echt)(**felder)

    host.detect = erfunden

    # Netzwerkkarten: Heimnetz 192.168.178.20, beim Kursleiter zusätzlich ein WireGuard-Tunnel
    karten = {"eth0": [snicaddr(socket.AF_INET, "192.168.178.20", "255.255.255.0", None, None)]}
    if kursleiter:
        karten["wg0"] = [snicaddr(socket.AF_INET, "10.8.0.1", "255.255.255.0", None, None)]
    psutil.net_if_addrs = lambda: karten

    # Laufwerke: Hauptsystem und eine externe SSD
    gb = storage.GB
    laufwerke = [storage.Drive(Path("/"), "/", "ext4", 512 * gb, 380 * gb, False, True),
                 storage.Drive(Path("/media/anna/T7"), "T7", "exfat", 1000 * gb, 820 * gb, True, False)]
    storage.drives = lambda: laufwerke
    storage._partitions = lambda: []
    storage.invalidate_cache()

    class _Platz:
        total, used, free = 512 * gb, 132 * gb, 380 * gb

    class _Shutil:
        """Wie shutil, nur der freie Platz ist erfunden."""

        def __getattr__(self, name):
            return getattr(shutil, name)

        @staticmethod
        def disk_usage(_pfad):
            return _Platz()

    storage.shutil = _Shutil()

    # Pfade so zeigen, wie sie bei Anna aussähen
    from bonys_agents.gui import widgets

    echt_set_path = widgets.PathLabel.set_path

    def set_path(self, path) -> None:
        text = str(path)
        if text.startswith(str(wurzel / "daten")):
            text = ANZEIGE_HOME + "/.local/share" + text[len(str(wurzel / "daten")):]
        elif text.startswith(str(wurzel)):
            text = ANZEIGE_HOME + text[len(str(wurzel / "home")):]
        echt_set_path(self, text)

    widgets.PathLabel.set_path = set_path

    # Kein QEMU: „läuft“ heißt hier nur, dass der Agent-PC in Laufend.pcs steht
    vm.VM.pid = lambda self: 4242 if self.name in Laufend.pcs else None
    vm.VM.runtime = lambda self: dict(Laufend.pcs.get(self.name, {}))
    vm.VM._update_runtime = lambda self, **werte: Laufend.pcs.get(self.name, {}).update(werte)
    vm.VM.capabilities = lambda self: {"spice": True, "audio": ["pipewire", "spice"]}
    vm.VM.vnc_available = lambda self: True
    vm.VM.sync_remmina = lambda self: None
    vm.VM.template_lock_pid = lambda self: None
    vm.VM.abort_reason = lambda self: diagnose.AbortInfo(
        "Der Rechner wurde während der Einrichtung neu gestartet.",
        "Die Einrichtung macht beim unterbrochenen Schritt weiter.")
    vm.reap_children = lambda: None
    remote.remmina_command = lambda: None
    remote.port_free = lambda port: True
    remote.remmina_dirs = lambda native=None, flatpak=None: []

    # QEMU und KVM fehlen beim ersten Start (für „Rechner vorbereiten“); danach ist alles da
    deps.check = lambda info=None: deps.Report(Laufend.pcs.get("__deps__", {}).get("issues", []))

    updates.auto_check_due = lambda: False
    updates.needs_consent = lambda: False

    def offline(*_a, **_k):
        raise OSError("Vorführmodus: kein Netz")

    mission_control._download = offline
    mission_control._cache = None
    mission_control.status = lambda machine, **kw: {
        "installed": True, "version": "0.1.0", "active": True, "healthy": True, "health_version": "0.1.0",
        "docker": True, "port": 8787}

    vpn_status = {"installed": True, "version": vpnlink.MIN_VERSION, "schema": vpnlink.SCHEMA, "active": "fritzbox",
                  "tunnels": [{"name": "fritzbox", "active": True, "autostart": True,
                               "addresses": ["192.168.179.201/24"], "peers": [{"endpoint": "vpn.example.net:51820"}],
                               "handshake": int(time.time()) - 42, "rx": 48_300_000, "tx": 5_100_000}],
                  "killswitch": {"enabled": True, "active": True, "exceptions": ["10.0.2.0/24"]}}
    vpn_status["compat"] = vpnlink.compat(vpn_status)
    vpnlink.status = lambda machine, **kw: dict(vpn_status)
    vpnlink.public_ip = lambda machine, **kw: "203.0.113.57"

    # Freigaben im Netz: eine Vorlage und eine Vorführung des Kursleiters
    from bonys_agents import mdns

    gefunden = [
        mdns.Found("kurs-basis", "kursleitung-pc.local", 47110, ["192.168.178.30"],
                   {"kind": "share", "name": "kurs-basis", "version": "1.0", "creator": "Eva"}),
        mdns.Found("Vorführung", "kursleitung-pc.local", 47120, ["192.168.178.30"],
                   {"kind": "present", "name": "agent-kursleitung", "creator": "Eva"}),
    ]
    share.discover = lambda timeout=2.5: list(gefunden)

    from bonys_agents import hilfe

    hilfe.tailscale_status = lambda run=None: None


# ====================================================================== Aufnehmen
class Kamera:
    def __init__(self, app, ziel: Path, nur: set[str]):
        self.app = app
        self.ziel = ziel
        self.nur = nur
        self.liste: list[str] = []

    def warten(self, sekunden: float = 0.3) -> None:
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self.app.processEvents()
            time.sleep(0.02)

    def bis(self, bedingung, sekunden: float = 10) -> bool:
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self.app.processEvents()
            if bedingung():
                return True
            time.sleep(0.03)
        return False

    def gewuenscht(self, name: str) -> bool:
        return not self.nur or name in self.nur

    def speichern(self, pix, name: str, marken=(), quelle=None) -> None:
        from PySide6.QtCore import QPoint, QRect, Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPen

        if marken:
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            r = 13
            breite = pix.width() / pix.devicePixelRatio()
            hoehe = pix.height() / pix.devicePixelRatio()
            for nummer, ziel in enumerate(marken, 1):
                if isinstance(ziel, tuple):
                    mitte = QPoint(*ziel)
                else:
                    # Rahmen um das Element, die Nummer auf seiner linken oberen Ecke
                    oben_links = ziel.mapTo(quelle, QPoint(0, 0))
                    rahmen = QRect(oben_links, ziel.size()).adjusted(-3, -3, 3, 3)
                    p.setPen(QPen(QColor("#f5a623"), 2.5))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(rahmen, 6, 6)
                    mitte = rahmen.topLeft()
                mitte.setX(int(max(r + 2, min(breite - r - 2, mitte.x()))))
                mitte.setY(int(max(r + 2, min(hoehe - r - 2, mitte.y()))))
                p.setPen(QPen(QColor("#0d141d"), 2.5))
                p.setBrush(QColor("#f5a623"))
                p.drawEllipse(mitte, r, r)
                p.setPen(QColor("#0d141d"))
                f = QFont("Source Sans 3")
                f.setPixelSize(17)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRect(mitte.x() - r, mitte.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(nummer))
            p.end()
        datei = self.ziel / f"{name}.png"
        pix.save(str(datei), "PNG")
        self.liste.append(name)
        print(f"  {datei.name}  ({pix.width()} × {pix.height()})", flush=True)

    def fenster(self, w, name: str, marken=(), groesse=None, vorher=None) -> None:
        """Ein Fenster aufnehmen. ``marken``: Widgets (oder Punkte), neben die eine Nummer ①②③ gezeichnet wird."""
        if not self.gewuenscht(name):
            return
        if groesse:
            w.resize(*groesse)
        w.show()
        self.warten(0.4)
        if vorher:
            vorher()
            self.warten(0.4)
        self.speichern(w.grab(), name, marken, w)


def _menue_bild(kamera: Kamera, fenster, menue, ort, name: str) -> None:
    """Hauptfenster mit aufgeklapptem Menü an ``ort`` (Fensterkoordinaten)."""
    from PySide6.QtGui import QPainter

    if not kamera.gewuenscht(name):
        return
    menue.popup(fenster.mapToGlobal(ort))
    kamera.warten(0.4)
    bild = fenster.grab()
    m = menue.grab()
    p = QPainter(bild)
    p.drawPixmap(ort, m)
    p.end()
    menue.hide()
    kamera.speichern(bild, name)


# ====================================================================== Bilder: Anwender
def bilder_anwender(kamera: Kamera, wurzel: Path) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMessageBox

    from bony_netz import Konto
    from bonys_agents import APP_NAME, deps, netz, storage, updates, vm
    from bonys_agents.gui.main_window import MainWindow
    import zentrale

    bib = storage.default_library()
    bib.mkdir(parents=True, exist_ok=True)

    # ---------- erster Start: noch kein Agent-PC, QEMU fehlt
    Laufend.pcs = {"__deps__": {"issues": [
        deps.Issue("qemu", "QEMU (die Virtualisierungs-Software) ist nicht installiert.", True, True),
        deps.Issue("kvm-access", "Dein Benutzer darf KVM noch nicht verwenden.", True, False)]}}
    MainWindow.show_doctor = lambda self: None
    MainWindow._check_kurse = lambda self: None   # „Kurs hat begonnen“ zeigt nur das eigene Bild
    win = MainWindow()
    win.timer.stop()
    win.resize(BREITE, HOEHE)
    kamera.fenster(win, "hauptfenster-leer", marken=[win.new_btn])

    from bonys_agents.gui.setup_dialog import SetupDialog

    d = SetupDialog(win.info, win)
    kamera.fenster(d, "rechner-vorbereiten", groesse=(620, 470), marken=[d.fix_btn])
    d.close()
    Laufend.pcs = {}
    from bonys_agents import remote

    remote.remmina_command = lambda: ["remmina"]   # nach der Einrichtung ist Remmina da

    box = QMessageBox(QMessageBox.Question, APP_NAME, updates.CONSENT_QUESTION, QMessageBox.Yes | QMessageBox.No, win)
    kamera.fenster(box, "update-frage")
    box.close()

    # ---------- Bony-Netz einschalten (Fenster „Bony-Netz“)
    zentrale.einsetzen(zentrale.Beispiel("teilnehmer"))
    from bonys_agents.gui.netz_dialog import NetzDialog

    d = NetzDialog(win)
    kamera.fenster(d, "bony-netz-aus", vorher=lambda: kamera.warten(0.6), marken=[d.active, d.server, d.create_btn])
    d.close()
    konto = Konto(server=zentrale.SERVER, instanz_id="inst-anna-0001", token=zentrale.TOKEN,
                  login_server="https://netz.example", extra={netz.AKTIV: True, "anzeigename": "Anna"})
    konto.speichern()
    d = NetzDialog(win)
    kamera.fenster(d, "bony-netz-an", vorher=lambda: kamera.warten(1.0),
                   marken=[d.active, d.server, d.instance, d.delete_btn])
    d.close()

    # ---------- Neuer Agent-PC
    from bonys_agents.gui.create_dialog import CreateDialog

    d = CreateDialog(win.info, win)
    d.name.setText("agent-buero")
    d.pw1.setText("geheim123")
    d.pw2.setText("geheim123")
    kamera.fenster(d, "neuer-agent-pc", groesse=(720, 860), marken=[d.base, d.name, d.pw1, d.cpu])
    from PySide6.QtWidgets import QScrollArea

    scroll = d.findChild(QScrollArea)

    def runter() -> None:
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())

    kamera.fenster(d, "neuer-agent-pc-programme", groesse=(720, 860), vorher=runter)
    d.close()

    # ---------- Agent-PCs anlegen: Einrichtung, abgebrochen, fertig
    agent_pcs(bib, mit_netz=True)
    vorlagen(bib)
    Laufend.pcs = {"agent-test": {"started": time.time() - 900, "pid": 4242}}
    win.refresh()
    _waehlen(win, "agent-test")
    kamera.fenster(win, "einrichtung-laeuft", marken=[win.d_prog, win.peek_btn])

    Laufend.pcs = {}
    win.refresh()
    _waehlen(win, "agent-test")
    kamera.fenster(win, "einrichtung-abgebrochen", marken=[win.resume_btn])

    # agent-test ist ab hier fertig eingerichtet (aber aus)
    m = vm.get("agent-test")
    m.config.first_boot_pending = False
    m.config.provisioned = True
    m.save()
    (m.path / "console.log").write_text(_konsole(SCHRITTE, len(SCHRITTE), True), "utf-8")

    Laufend.pcs = {"agent-buero": {"started": time.time() - 3600, "pid": 4242, "remote_on": True}}
    # Netz-Symbole: agent-buero im Netz, agent-kurs offline
    win._netz_geraete = {"agent-buero": {"name": "agent-buero", "online": True},
                         "agent-kurs": {"name": "agent-kurs", "online": False}}
    win._netz_zuletzt = time.monotonic()
    win._check_netz = lambda netz_on: None
    win.refresh()
    _waehlen(win, "agent-buero")
    _konsole_unten(win)
    kamera.fenster(win, "hauptfenster", marken=[win.list, win.d_name, win.new_btn, win.join_btn])

    _menue_bild(kamera, win, win.about_btn.menu(), win.about_btn.geometry().bottomLeft()
                + win.about_btn.parentWidget().mapTo(win, QPoint(0, 0)), "menue")

    # Kontextmenü der Liste (wie Rechtsklick) – exec() blockiert, deshalb vorher Aufnahme planen
    _kontextmenue(kamera, win)

    win._show_tab(1)
    kamera.fenster(win, "fernzugriff", marken=[win.remote_btn, win.tab_remote])
    win._show_tab(2)
    kamera.bis(lambda: win.vpn_panel.state is not None, 5)
    kamera.fenster(win, "vpn", marken=[win.tab_vpn])
    win._show_tab(3)
    kamera.warten(1.0)
    kamera.fenster(win, "mission-control", marken=[win.tab_mc])
    win._show_tab(0)

    from bonys_agents.gui.install_dialog import InstallAppsDialog

    d = InstallAppsDialog(vm.get("agent-buero"), win)
    kamera.fenster(d, "programme-hinzufuegen")
    d.close()

    from bonys_agents.gui.template_dialogs import ExportDialog, SaveTemplateDialog, TemplatesDialog
    from bonys_agents import templates

    Laufend.pcs = {}
    win.refresh()
    d = SaveTemplateDialog(vm.get("agent-buero"), win)
    d_name = getattr(d, "name", None)
    if d_name is not None and hasattr(d_name, "setText"):
        d_name.setText("buero-basis-2")
    kamera.fenster(d, "vorlage-speichern")
    d.close()
    d = TemplatesDialog(win)
    kamera.fenster(d, "vorlagen", groesse=(860, 560))
    d.close()
    d = ExportDialog(templates.get("kurs-basis"), win)
    d.file.setText(f"{ANZEIGE_HOME}/kurs-basis-1.0.bonys")   # zeigt sonst den Ordner des Vorführmodus
    kamera.fenster(d, "vorlage-weitergeben", marken=[d.creator, d.version, d.ok_btn])
    d.close()

    # ---------- Kurse (Teilnehmerin Anna)
    from bonys_agents.gui.kurse_dialog import KurseDialog

    Laufend.pcs = {"agent-kurs": {"started": time.time() - 600, "pid": 4242}}
    win.refresh()
    netz.aktiv_setzen(False)
    d = KurseDialog(win)
    kamera.fenster(d, "kurse-ohne-netz", groesse=(720, 640))
    d.close()
    netz.aktiv_setzen(True)
    d = KurseDialog(win)
    d.resize(720, 700)
    d.show()
    seite = d.teilnahme
    kamera.bis(lambda: seite.geladen and not seite.busy, 10)
    seite.code.setText("K7QX-M3PA")
    seite.table.selectRow(0)
    kamera.fenster(d, "kurse-teilnahme", marken=[seite.code, seite.geraet, seite.name, seite.join_btn,
                                                 seite.room_btn])
    d.close()

    # ---------- Kurspakete: Bibliothek und Anleitung (Anna arbeitet „Einführung in Hermes Agent“ durch)
    from bonys_agents import kurslauf, kurspaket
    from bonys_agents.gui import kurspaket_anleitung

    paket = kurspaket.holen("einfuehrung-hermes-agent")
    f = kurspaket.agent_pc_merken(paket, "agent-kurs")
    f.erledigt = [lek.ordner for lek in paket.lektionen[:3]]
    f.gehe_zu(paket, 3)
    d = KurseDialog(win)
    d.tabs.setCurrentWidget(d.pakete)
    d.resize(900, 660)
    d.show()
    kamera.warten(0.5)
    d.pakete.tabelle.selectRow(0)
    kamera.fenster(d, "kurspakete")
    d.close()
    lek = paket.lektionen[3]
    kurslauf.startzustaende = lambda m, p: {x.ordner for x in p.lektionen[:4]}   # nichts im Agent-PC ansehen
    kurslauf.bereit = lambda m: False
    a = kurspaket_anleitung.AnleitungFenster(paket)
    a.timer.stop()
    a.oben.setChecked(False)
    a.startzustaende = {x.ordner for x in paket.lektionen[:4]}
    a.ergebnis[lek.ordner] = kurslauf.Ergebnis(True, lek.pruefung.geschafft)
    a._zeigen()
    kamera.fenster(a, "kurspaket-anleitung", groesse=(440, 780),
                   marken=[a.auswahl, a.pruefen_knopf, a.quiz_knopf, a.reset_knopf, a.weiter])
    a.close()

    from bonys_agents import kurse

    win.statusBar().showMessage(kurse.begonnen_text(kurse.teilnahmen()))
    _waehlen(win, "agent-kurs")
    kamera.fenster(win, "kurs-begonnen", marken=[(14, 778)])
    win.statusBar().clearMessage()

    # ---------- Hilfe-Funktion beim Teilnehmer
    from bonys_agents import hilfe
    from bonys_agents.gui.hilfe_ui import Hinweis, Zustimmung

    z = Zustimmung(zentrale.KURSLEITUNG, "agent-kurs")
    kamera.fenster(z, "hilfe-rueckfrage", marken=[z.nein, z.ansehen, z.bedienen])
    z.gemeldet = True
    z.close()
    h = Hinweis(zentrale.KURSLEITUNG, "agent-kurs", hilfe.ANSEHEN)
    kamera.fenster(h, "hilfe-laeuft", marken=[h.knopf])
    h.zu = True
    h.uhr.stop()
    h.hide()

    # ---------- Schulung im eigenen Netz
    from bonys_agents.gui.share_dialogs import JoinDialog

    d = JoinDialog(win)
    d.show()
    kamera.bis(lambda: d.found.count() > 0, 5)
    d.found.setCurrentRow(0)
    d.code.setText("4711-BONY")
    kamera.fenster(d, "schulung-beitreten")
    d.close()

    from bonys_agents.gui.course_ui import HelpRequestDialog

    d = HelpRequestDialog(vm.get("agent-kurs"), win)
    kamera.fenster(d, "schulung-hilfe-anfordern", vorher=lambda: kamera.warten(1.0))
    d.close()

    # ---------- Kursraum (Teilnehmerin Anna)
    kursraum_bilder(kamera, "teilnehmer")
    win.close()


def _konsole_unten(win) -> None:
    bar = win.console.verticalScrollBar()
    bar.setValue(bar.maximum())


def _waehlen(win, name: str) -> None:
    for i in range(win.list.count()):
        if win.list.item(i).text().startswith(name):
            win.list.setCurrentRow(i)
    win.refresh_detail()


def _kontextmenue(kamera: Kamera, win) -> None:
    """Rechtsklick auf einen Agent-PC, der noch nicht im Bony-Netz ist (läuft und ist eingerichtet)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication

    if not kamera.gewuenscht("kontextmenue"):
        return
    vorher = dict(Laufend.pcs)
    Laufend.pcs["agent-test"] = {"started": time.time() - 300, "pid": 4242}
    win.refresh()
    _waehlen(win, "agent-test")
    _konsole_unten(win)
    item = win.list.currentItem()
    ort = win.list.visualItemRect(item).center()

    def aufnehmen() -> None:
        menue = QApplication.activePopupWidget()
        if menue is None:
            QTimer.singleShot(100, aufnehmen)
            return
        bild = win.grab()
        p = QPainter(bild)
        p.drawPixmap(win.list.viewport().mapTo(win, ort), menue.grab())
        p.end()
        kamera.speichern(bild, "kontextmenue")
        menue.close()

    QTimer.singleShot(300, aufnehmen)
    win._list_menu(ort)
    Laufend.pcs = vorher
    win.refresh()
    _waehlen(win, "agent-buero")


# ====================================================================== Kursraum
def kursraum_bilder(kamera: Kamera, rolle: str) -> None:
    """Kursraum-Fenster mit der LiveKit-Attrappe – Teilnehmerin Anna bzw. Kursleiterin Eva."""
    from bonys_agents import kursraum
    from bonys_agents.gui import kursraum_fenster

    namen = {"teilnehmer": ["kursraum-teilnehmer", "kursraum-getrennt"],
             "kursleiter": ["kursraum-kursleiter", "kursraum-bildschirm-waehlen"]}[rolle]
    if not any(kamera.gewuenscht(n) for n in namen):
        return
    if not kursraum_fenster.verfuegbar():
        print("  (Kursraum übersprungen: Qt WebEngine fehlt)")
        return
    echt = kursraum.seiten_datei

    def seiten_datei(pfad, ordner=None):
        if pfad.lstrip("/") == "vendor/livekit-client.umd.js":
            return HIER / "livekit-attrappe.js", "text/javascript"
        return echt(pfad, ordner)

    kursraum.seiten_datei = seiten_datei
    kursraum.livekit_da = lambda ordner=None: True
    from bonys_agents.gui import style

    hintergrund = style.resource("wallpaper.jpg").read_bytes()
    kursraum_fenster.ZUSATZ["vorfuehrung"] = lambda rest: (hintergrund, "image/jpeg") if rest == "hintergrund.jpg" \
        else None

    import zentrale

    karte = kursraum.eintreten(zentrale.KURS_ID)
    f = kursraum_fenster.KursraumFenster(karte, "Einführung in Hermes Agent")
    f.resize(BREITE, HOEHE)
    f.show()
    js = f.seite.runJavaScript
    kamera.bis(lambda: f._bereit, 20)
    kamera.warten(1.5)

    def ausfuehren(code: str, sekunden: float = 0.4) -> None:
        js(code)
        kamera.warten(sekunden)

    if rolle == "teilnehmer":
        ausfuehren("Vorfuehrung.chat('eva', 'Willkommen! Öffnet bitte euren Agent-PC und das Symbol Hermes Agent.')")
        ausfuehren("Vorfuehrung.chat('ben', 'Bei mir steht „hermes: command not found“.')")
        ausfuehren("Vorfuehrung.chat('eva', 'Ben, ich schaue gleich bei dir vorbei.')")
        ausfuehren("Vorfuehrung.hand('clara', true)")
        ausfuehren("Vorfuehrung.klicken('hand')", 2.5)
        if kamera.gewuenscht(namen[0]):
            kamera.speichern(f.grab(), namen[0], marken=[(26, 62), (1264, 62), (1264, 398), (16, 752),
                                                         (376, 752)], quelle=f)
        ausfuehren("Vorfuehrung.getrennt('ROOM_DELETED')", 1.0)
        if kamera.gewuenscht(namen[1]):
            kamera.speichern(f.grab(), namen[1])
    else:
        ausfuehren("Vorfuehrung.bildschirmTeilen(true)")
        ausfuehren("Vorfuehrung.chat('anna', 'Bei mir hat es geklappt!')")
        ausfuehren("Vorfuehrung.hand('ben', true)")
        ausfuehren("Vorfuehrung.daten('clara', 'hilfe-bitte', {an: true})", 2.5)
        if kamera.gewuenscht(namen[0]):
            kamera.speichern(f.grab(), namen[0], marken=[(378, 752), (514, 752), (1264, 62), (548, 690)], quelle=f)
        if kamera.gewuenscht(namen[1]):
            _bildschirm_waehlen(kamera, f, namen[1])
    f.fertig = True
    f.close()
    kamera.warten(0.5)


def _bildschirm_waehlen(kamera: Kamera, fenster, name: str) -> None:
    """Auswahl „Was sollen die Teilnehmer sehen?“ mit Beispiel-Bildschirmen und -Fenstern."""
    from PySide6.QtGui import QStandardItem, QStandardItemModel

    from bonys_agents.gui import kursraum_fenster

    def modell(eintraege):
        m = QStandardItemModel()
        for e in eintraege:
            m.appendRow(QStandardItem(e))
        return m

    class Anfrage:
        def __init__(self):
            self.b = modell(["DP-1"])
            self.f = modell(["Agent-PC „agent-kursleitung“ – QEMU", "Kursraum – Einführung in Hermes Agent",
                             "Präsentation.pdf – Dokumentenbetrachter"])

        def screensModel(self):  # noqa: N802
            return self.b

        def windowsModel(self):  # noqa: N802
            return self.f

    d = kursraum_fenster._BildschirmWahl(Anfrage(), fenster.view)
    kamera.fenster(d, name)
    d.close()


# ====================================================================== Bilder: Kursleiter
class _Ereignis:
    def __init__(self, gesetzt=False):
        self._an = gesetzt

    def is_set(self):
        return self._an


class _Sperre:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class KursServer:
    """Erfundener Kurs-Server (Freigabe, Vorführung, Hilfe-Schalter) – öffnet keinen Port."""

    code = "4711-BONY"
    fingerprint = "3f9a2c7e" * 8
    size = int(3.4 * 1024 ** 3)
    max_viewers = 30
    cpu_percent = 18.0
    has_screen = True
    title = "agent-kursleitung"
    keep_running = False

    def __init__(self, port: int):
        from types import SimpleNamespace as NS

        self.port = port
        self.lock = _Sperre()
        self.stopped = _Ereignis()
        self.stop_reason = ""
        self.paused = False
        self.events = ["10:02  Anna (annas-laptop) verbunden", "10:03  Ben (ben-laptop) verbunden",
                       "10:03  Clara (clara-pc) verbunden"]
        self.participants = {
            "a": NS(name="annas-laptop", address="192.168.178.41", status="fertig", queue=0, percent=100, total=1,
                    eta=lambda: None, lektion=3, geschafft=True),
            "b": NS(name="ben-laptop", address="192.168.178.42", status="lädt", queue=0, percent=63, total=1,
                    eta=lambda: 95, lektion=0, geschafft=None),
            "c": NS(name="clara-pc", address="192.168.178.43", status="wartet", queue=1, percent=0, total=0,
                    eta=lambda: None, lektion=0, geschafft=None),
        }
        self._zuschauer = [NS(id="v1", name="Anna", address="192.168.178.41", connected=True, dropped_input=0),
                           NS(id="v2", name="Ben", address="192.168.178.42", connected=True, dropped_input=3),
                           NS(id="v3", name="Clara", address="192.168.178.43", connected=False, dropped_input=0)]
        jetzt = time.time()
        self.helpdesk = NS(
            requests_total=1,
            session_list=lambda: [
                NS(id="s1", name="Ben", vm="agent-pc-ben", message="Hermes startet nicht", requested_at=jetzt - 120,
                   state="wartet auf Hilfe", connected=True, view_allowed=False),
                NS(id="s2", name="Clara", vm="agent-pc-clara", message="", requested_at=jetzt - 600,
                   state="verbunden", connected=True, view_allowed=False)])

    def start(self):
        pass   # kein Port, keine Ankündigung im Netz

    def addresses(self):
        return ["192.168.178.30", "10.8.0.1"]

    def link(self, adresse=None):
        from bonys_agents import share

        return share.share_link(adresse or "192.168.178.30", self.port, self.code, self.fingerprint)

    def url(self):
        return f"https://192.168.178.30:{self.port}/#code={self.code}"

    def viewer_list(self):
        return list(self._zuschauer)

    def remaining(self):
        return 74 * 60 + 12

    def fps(self):
        return 10.0

    def stop(self, grund=""):
        self.stopped = _Ereignis(True)
        self.stop_reason = grund


def bilder_kursleiter(kamera: Kamera, wurzel: Path) -> None:
    from bony_netz import Konto
    from bonys_agents import kurse, netz, storage, templates, vm
    from bonys_agents.gui.main_window import MainWindow
    import zentrale

    bib = storage.default_library()
    bib.mkdir(parents=True, exist_ok=True)
    vorlagen(bib)
    p = bib / "agent-kursleitung"
    p.mkdir(parents=True)
    cfg = vm.VMConfig(name="agent-kursleitung", arch="x86_64", cpus=6, ram_mb=8192, desktop="cinnamon",
                      apps=["brave", "telegram", "hermes", "xrdp"], provisioned=True, rdp_port=3390,
                      spice_port=5901, netz_name="agent-kursleitung", created="2026-10-10T08:00:00+00:00")
    (p / "vm.json").write_text(json.dumps(cfg.__dict__), "utf-8")
    (p / "console.log").write_text(_konsole(SCHRITTE, len(SCHRITTE), True), "utf-8")
    Laufend.pcs = {"agent-kursleitung": {"started": time.time() - 1800, "pid": 4242}}

    beispiel = zentrale.Beispiel("kursleiter")
    beispiel.kursleiter = False   # erst nach dem Einlösen des Kursleiter-Codes
    zentrale.einsetzen(beispiel)
    Konto(server=zentrale.SERVER, instanz_id=beispiel.instanz_id, token=zentrale.TOKEN,
          login_server="https://netz.example", extra={netz.AKTIV: True, "kursleiter_name": "Eva"}).speichern()

    MainWindow.show_doctor = lambda self: None
    win = MainWindow()
    win.timer.stop()
    win.resize(BREITE, HOEHE)
    win._netz_geraete = {"agent-kursleitung": {"name": "agent-kursleitung", "online": True}}
    win._netz_zuletzt = time.monotonic()
    win._check_netz = lambda netz_on: None
    win.refresh()
    _waehlen(win, "agent-kursleitung")
    kamera.fenster(win, "kl-hauptfenster", marken=[win.present_btn, win.join_btn, win.templates_btn])

    from bonys_agents.gui.kurse_dialog import KurseDialog

    d = KurseDialog(win)
    d.resize(760, 640)
    d.show()
    kamera.bis(lambda: d.leitung.geladen and not d.leitung.busy, 10)
    kamera.fenster(d, "kl-code-einloesen", marken=[d.leitung.code, d.leitung.redeem_btn])
    beispiel.kursleiter = True
    d.leitung.code.setText(zentrale.KURSLEITER_CODE)
    d.leitung._redeem()
    kamera.bis(lambda: d.leitung.kursleiter and not d.leitung.busy, 10)
    d.leitung.tick(sofort=True)
    kamera.bis(lambda: d.leitung.kurse and not d.leitung.busy, 10)
    d.leitung.ended.setChecked(True)
    kamera.bis(lambda: len(d.leitung.kurse) == 2 and not d.leitung.busy, 10)
    kamera.fenster(d, "kl-kursliste", marken=[d.leitung.new_btn, d.leitung.open_btn, d.leitung.ended])

    from bonys_agents.trainer.gui.kurse_leiten import KursAnsicht, NeuerKursDialog

    n = NeuerKursDialog(d)
    n.name.setText("Einführung in Hermes Agent")
    n.days.setValue(14)
    kamera.fenster(n, "kl-neuer-kurs", marken=[n.name, n.leader, n.days, n.ok_btn])
    n.close()

    kurs = next(k for k in d.leitung.kurse if k.kurs_id == zentrale.KURS_ID)
    a = KursAnsicht(kurs, d)
    a.table.selectRow(1)
    kamera.fenster(a, "kl-kursansicht", groesse=(820, 860),
                   marken=[a.code, a.pause_btn, a.room_btn, a.table, a.help_btn])
    a.table.clearSelection()
    kamera.fenster(a, "kl-kurspaket-kursansicht", groesse=(820, 860),
                   marken=[a.paket_text, a.anleitung_btn, a.paket_btn, a.table])
    a.close()

    # Kurspaket-Editor mit einer Kopie von „Einführung in Hermes Agent“ (Lektion 4, Reiter „Prüfung“)
    from bonys_agents.trainer.gui.kurspaket_editor import EditorFenster

    kopie = Path(os.environ["HOME"]) / "Kurspakete" / "einfuehrung-hermes-agent"
    shutil.copytree(REPO / "kurspakete" / "einfuehrung-hermes-agent", kopie)
    e = EditorFenster(kopie)
    e.gliederung.setCurrentRow(7)
    e.lektion_seite.tabs.setCurrentIndex(3)                      # „Prüfung“
    e.status.setText("Ordner: ~/Kurspakete/hermes")   # nicht der Ordner des Vorführmodus
    kamera.warten(0.3)
    kamera.fenster(e, "kl-kurspaket-editor", groesse=(1180, 760))
    e.close()

    # Kursstart: dieser Rechner ist noch nicht im Bony-Netz
    from bonys_agents import hilfe
    from PySide6.QtWidgets import QApplication, QMessageBox

    kurs_offen = kurse.Kurs.aus({**beispiel.kurse[zentrale.KURS_ID], "status": "offen"})
    a = KursAnsicht(kurs_offen, d)
    a.resize(780, 760)
    a.show()
    kamera.warten(0.4)
    a._netz_anbieten(hilfe.rechner_im_netz(status=None, geraete=[]))
    box = None
    kamera.bis(lambda: any(isinstance(w, QMessageBox) and w.isVisible() for w in QApplication.topLevelWidgets()), 3)
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QMessageBox) and w.isVisible():
            box = w
    if box is not None:
        kamera.fenster(box, "kl-netz-pruefung")
        box.close()
    a.close()
    d.close()

    # ---------- Schulung im eigenen Netz: Freigeben, Vorführen, Hilfe-Schalter
    from bonys_agents.trainer.gui import helpdesk_dialog, present_dialog, share_dialog

    t = templates.get("kurs-basis")
    s = share_dialog.ShareDialog(t, win)
    s.paket.setCurrentIndex(max(0, s.paket.findData("einfuehrung-hermes-agent")))
    server = KursServer(47110)

    echt_share = share_dialog.share_server.Share
    share_dialog.share_server.Share = lambda *a, **k: server
    s._serve((Path("/home/eva/kurs-basis-1.0.bonys"), "0" * 64))
    share_dialog.share_server.Share = echt_share
    s.timer.stop()
    s._refresh()
    kamera.fenster(s, "kl-freigeben", groesse=(1000, 820), marken=[s.code, s.qr, s.table])
    s.share = None
    s.close()

    pres = KursServer(47120)
    hub = helpdesk_dialog.CourseHub.get()
    hub.timer.stop()
    hub.server = pres
    pdlg = present_dialog.PresentDialog(vm.get("agent-kursleitung"), win, help_desk=lambda: None)
    pdlg.timer.stop()
    kamera.fenster(pdlg, "kl-vorfuehren", groesse=(820, 820),
                   marken=[pdlg.code, pdlg.qr, pdlg.pause_btn, pdlg.remove_btn])
    pdlg.pres = None
    pdlg.close()

    h = helpdesk_dialog.HelpDeskDialog(win)
    h.show()
    kamera.warten(0.3)
    h.timer.stop()
    h.table.selectRow(0)
    kamera.fenster(h, "kl-hilfe-anfragen", groesse=(820, 720), marken=[h.table, h.view_btn, h.control_btn])
    h.timer.stop()
    hub.server = None
    h.done(0)

    # ---------- Kursraum (Kursleiterin Eva)
    kursraum_bilder(kamera, "kursleiter")
    win.close()


# ====================================================================== Start
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--edition", choices=["anwender", "kursleiter"], required=True)
    ap.add_argument("--ziel", type=Path, default=REPO / "docs" / "handbuch" / "bilder")
    ap.add_argument("--nur", nargs="*", default=[], help="nur diese Bilder (Namen ohne .png)")
    args = ap.parse_args()
    wurzel = umgebung(args.edition)
    try:
        args.ziel.mkdir(parents=True, exist_ok=True)
        from bonys_agents.gui import kursraum_fenster

        kursraum_fenster.vorbereiten()
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication

        app = QApplication(["bonys-agents"])
        app.setApplicationName("Bony's Agents")
        from bonys_agents import edition
        from bonys_agents.gui import style
        from bonys_agents.gui.app import install_german

        if edition.EDITION != args.edition:
            print(f"Edition {args.edition} ist hier nicht verfügbar (bonys_agents.trainer fehlt?)", file=sys.stderr)
            return 2
        app.setApplicationDisplayName(edition.NAME)
        schriften = REPO / "docs" / "handbuch" / "vorlage" / "schriften"
        for f in sorted(schriften.glob("SourceSans3-*.ttf")):
            QFontDatabase.addApplicationFont(str(f))
        app.setFont(QFont("Source Sans 3", 10))
        install_german(app)
        style.apply(app)
        vorfuehrmodus(wurzel, args.edition == "kursleiter")
        kamera = Kamera(app, args.ziel, set(args.nur))
        print(f"Bildschirmfotos ({edition.NAME}) → {args.ziel}")
        if args.edition == "anwender":
            bilder_anwender(kamera, wurzel)
        else:
            bilder_kursleiter(kamera, wurzel)
        print(f"{len(kamera.liste)} Bilder.")
        app.closeAllWindows()
        app.processEvents()
        return 0
    finally:
        shutil.rmtree(wurzel, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
