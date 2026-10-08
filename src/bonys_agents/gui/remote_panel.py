# SPDX-License-Identifier: GPL-3.0-or-later
"""Bereich „Fernzugriff“ der Detailansicht: Ein-/Ausschalten, Verbinden, Verbindungsdaten."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, deps, remote, vm
from bonys_agents.procutil import clean_env

from . import style
from .widgets import FlowLayout, make_scrollable
from .workers import TaskWorker


def _small(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Small")
    if tip:
        b.setToolTip(tip)
    return b


def install_remmina(parent: QWidget, done=None) -> TaskWorker | None:
    """Remmina samt RDP- und SPICE-Plugin per pkexec installieren – nach Rückfrage."""
    answer = QMessageBox.question(
        parent, APP_NAME,
        "Remmina (mit RDP- und SPICE-Erweiterung) jetzt installieren?\n\n"
        f"Pakete: {', '.join(remote.REMMINA_PACKAGES)}\nDafür wird einmal dein Passwort abgefragt.",
    )
    if answer != QMessageBox.Yes:
        return None

    def run() -> None:
        cmd = deps._elevate_linux(remote.remmina_install_script(), gui=True)
        rc = subprocess.run(cmd, env=clean_env()).returncode
        if rc != 0:
            raise RuntimeError(f"Remmina konnte nicht installiert werden (Code {rc}).")

    w = TaskWorker(run)
    w.failed.connect(lambda msg: QMessageBox.warning(parent, APP_NAME, msg))
    if done:
        w.finished.connect(done)
    w.start()
    return w


def remote_state_text(r: dict) -> str:
    if r["active"]:
        return "an – dauerhaft" if r["permanent"] else "an – bis zum Herunterfahren"
    return "aus – beim nächsten Start dauerhaft an" if r["permanent"] else "aus"


class RemoteDialog(QDialog):
    """„Fernzugriff einschalten“: nur bis zum Herunterfahren (Standard) oder dauerhaft."""

    def __init__(self, machine: vm.VM, running: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Fernzugriff – {machine.name}")
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        intro = QLabel(f"„{machine.name}“ wird per RDP aus dem Heimnetz erreichbar "
                       f"(Port {machine.config.rdp_port}). Anmeldung mit Benutzer und Passwort des Agent-PCs.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.temporary = QRadioButton("Nur bis zum Herunterfahren")
        self.permanent = QRadioButton("Dauerhaft – auch nach jedem Neustart")
        self.temporary.setEnabled(running)
        (self.temporary if running else self.permanent).setChecked(True)
        lay.addWidget(self.temporary)
        if not running:
            note = QLabel("Der Agent-PC ist aus – „nur bis zum Herunterfahren“ geht erst, wenn er läuft.")
            note.setObjectName("Muted")
            note.setWordWrap(True)
            lay.addWidget(note)
        lay.addWidget(self.permanent)
        warn = QLabel(f"⚠ {remote.LAN_WARNING}")
        warn.setStyleSheet(f"color: {style.WARN};")
        warn.setWordWrap(True)
        lay.addWidget(warn)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Einschalten")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        make_scrollable(self, 460)


def switch_remote(parent: QWidget, machine: vm.VM, on: bool, permanent: bool = False,
                  done=None, password: str | None = None) -> TaskWorker:
    """Fernzugriff im Hintergrund schalten. Antwortet der Gast-Agent nicht, wird nach dem
    Passwort des Agent-PCs gefragt und per SSH weitergemacht."""
    w = TaskWorker(lambda: machine.set_remote(on, permanent=permanent, password=password))

    def failed(msg: str) -> None:
        if isinstance(w.error, vm.NeedsPassword):
            pw, ok = QInputDialog.getText(
                parent, APP_NAME, f"{msg}\n\nPasswort von „{machine.name}“:", QLineEdit.Password)
            if ok and pw:
                switch_remote(parent, machine, on, permanent, done, pw)
                return
        else:
            QMessageBox.warning(parent, APP_NAME, msg)
        if done:
            done(None)

    w.failed.connect(failed)
    w.finished.connect(lambda: w.error is None and done and done(w.result))
    _keep(parent, w)
    w.start()
    return w


def _keep(parent: QWidget, w: TaskWorker) -> None:
    """Worker am Fenster festhalten, bis er fertig ist."""
    win = parent.window()
    workers = getattr(win, "workers", None)
    if isinstance(workers, list):
        workers[:] = [x for x in workers if x.isRunning()] + [w]
    else:
        win._remote_workers = [x for x in getattr(win, "_remote_workers", []) if x.isRunning()] + [w]


class RemotePanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.machine: vm.VM | None = None
        self.workers: list[TaskWorker] = []
        self._signature = None
        self._show_pw = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        row = FlowLayout()
        self.rdp_btn = QPushButton("Verbinden (RDP)")
        self.rdp_btn.setObjectName("Primary")
        self.spice_btn = QPushButton("Verbinden (SPICE)")
        self.connect_hint = QLabel()
        self.connect_hint.setObjectName("Muted")
        self.connect_hint.setWordWrap(True)
        row.addWidget(self.rdp_btn)
        row.addWidget(self.spice_btn)
        lay.addLayout(row)
        lay.addWidget(self.connect_hint)

        opt = QHBoxLayout()
        self.state = QLabel()
        self.display = QComboBox()
        self.display.addItem("Anzeige: QEMU-Fenster", "qemu")
        self.display.addItem("Anzeige: SPICE-Fenster", "spice")
        opt.addWidget(self.state)
        opt.addStretch(1)
        opt.addWidget(self.display)
        lay.addLayout(opt)

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        lay.addWidget(self.notice)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(4)
        lay.addLayout(self.grid)

        tools = FlowLayout()
        self.remmina_btn = _small("Remmina installieren", "Verbindungsprogramm für RDP und SPICE")
        self.export_btn = _small("Profile für anderen PC exportieren …",
                                 "Remmina- und Windows-Profile (.rdp) mit der Heimnetz-Adresse dieses Rechners")
        self.firewall_btn = _small("Firewall freigeben …", "Ports nur für das Heimnetz öffnen")
        for b in (self.remmina_btn, self.export_btn, self.firewall_btn):
            tools.addWidget(b)
        lay.addLayout(tools)
        lay.addStretch(1)

        self.rdp_btn.clicked.connect(lambda: self._connect("RDP"))
        self.spice_btn.clicked.connect(lambda: self._connect("SPICE"))
        self.display.activated.connect(self._set_display)
        self.remmina_btn.clicked.connect(self._install_remmina)
        self.export_btn.clicked.connect(self._export)
        self.firewall_btn.clicked.connect(lambda: self._firewall(ask=True))

    # ---------- Anzeige ----------
    def update_for(self, machine: vm.VM, status: str) -> None:
        self.machine = machine
        machine.ensure_remote_ports()
        r = machine.remote_info()
        running = machine.is_running()
        desktop = status == "läuft"
        linux = sys.platform.startswith("linux")

        self.rdp_btn.setEnabled(running and desktop and r["rdp_installed"] and r["active"])
        self.spice_btn.setEnabled(running and r["spice_supported"])
        self.spice_btn.setToolTip("" if r["spice_supported"] else "Dieser QEMU-Build kann kein SPICE")
        hints = []
        if not r["rdp_installed"]:
            hints.append("RDP: „Fernzugriff (RDP)“ über „Programme hinzufügen …“ nachrüsten.")
        elif running and not r["active"]:
            hints.append("RDP: oben „Fernzugriff einschalten“.")
        if not r["spice_supported"]:
            hints.append("SPICE: von diesem QEMU-Build nicht unterstützt – RDP geht trotzdem.")
        elif not remote.spice_viewer_available():
            hints.append("SPICE: Remmina oder remote-viewer installieren.")
        if not running:
            hints.append("Zum Verbinden den Agent-PC starten.")
        self.connect_hint.setText(" ".join(hints))

        color = style.OK if r["active"] else style.MUTED
        self.state.setText(f"Fernzugriff: <span style='color:{color}'>{remote_state_text(r)}</span>")
        self.display.setCurrentIndex(1 if r["display"] == "spice" else 0)
        self.display.setEnabled(r["spice_supported"])
        self.display.setToolTip("SPICE-Fenster: QEMU startet ohne eigenes Fenster, Bony's Agents öffnet "
                                "Remmina bzw. remote-viewer – mit Ton und Zwischenablage."
                                if r["spice_supported"] else "Dieser QEMU-Build kann kein SPICE")

        notes = []
        if r["active"] or r["spice_lan"]:
            notes.append(f"<span style='color:{style.WARN}'>⚠ {remote.LAN_WARNING}</span>")
        if r["needs_restart"]:
            notes.append(f"<span style='color:{style.HIGHLIGHT}'>SPICE aus dem Heimnetz erst nach einem "
                         "Neustart des Agent-PCs – RDP geht sofort.</span>")
        self.notice.setText("<br>".join(notes))
        self.notice.setVisible(bool(notes))

        self.remmina_btn.setVisible(linux and remote.remmina_command() is None)
        self.export_btn.setEnabled(bool(remote.lan_addresses()))
        self.firewall_btn.setVisible((r["active"] or r["permanent"]) and remote.firewall_needed())

        sig = (tuple(r["addresses"]), r["rdp_port"], r["spice_port"], r["username"], r["spice_password"],
               r["active"], r["spice_lan"], self._show_pw)
        if sig != self._signature:
            self._signature = sig
            self._rebuild_grid(r)

    def _rebuild_grid(self, r: dict) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()  # sofort weg – deleteLater greift erst später
                w.deleteLater()
        row = 0

        def add(label: str, value: str, copy: str | None = None, extra: QPushButton | None = None) -> None:
            nonlocal row
            k = QLabel(label.upper())
            k.setObjectName("Section")
            v = QLabel(value)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(k, row, 0)
            self.grid.addWidget(v, row, 1)
            col = 2
            if copy is not None:
                b = _small("Kopieren")
                b.clicked.connect(lambda _=False, t=copy: self._copy(t))
                self.grid.addWidget(b, row, col)
                col += 1
            if extra:
                self.grid.addWidget(extra, row, col)
            row += 1

        if r["spice_port"]:
            local = f"spice://127.0.0.1:{r['spice_port']}"
            add("SPICE", f"{local}  (an diesem Rechner)", local)
        if r["active"]:
            addrs = r["addresses"] or []
            if not addrs:
                add("Adresse", "keine Heimnetz-Adresse gefunden")
            for a in addrs:
                add("RDP", f"{a}:{r['rdp_port']}", f"{a}:{r['rdp_port']}")
                if r["spice_lan"]:
                    add("SPICE", f"spice://{a}:{r['spice_port']}", f"spice://{a}:{r['spice_port']}")
            add("Benutzer", f"{r['username']}  (Passwort des Agent-PCs)", r["username"])
        if r["spice_password"] and r["spice_port"]:
            show = _small("Verbergen" if self._show_pw else "Anzeigen")
            show.clicked.connect(self._toggle_pw)
            add("SPICE-Passwort", r["spice_password"] if self._show_pw else "•" * 10, r["spice_password"], show)
        self.grid.setColumnStretch(1, 1)

    # ---------- Aktionen ----------
    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.window().statusBar().showMessage(f"Kopiert: {text if 'spice://' in text or ':' in text else '…'}", 3000)

    def _toggle_pw(self) -> None:
        self._show_pw = not self._show_pw
        self._signature = None
        self.changed.emit()

    def _connect(self, protocol: str) -> None:
        if not self.machine:
            return
        try:
            self.machine.connect(protocol)
        except RuntimeError as e:
            QMessageBox.information(self, APP_NAME, str(e))

    def _set_display(self) -> None:
        if self.machine:
            self.machine.set_display(self.display.currentData())
            self.changed.emit()

    def _install_remmina(self) -> None:
        w = install_remmina(self, done=self._after_remmina)
        if w:
            self.workers.append(w)

    def _after_remmina(self) -> None:
        for m in vm.list_vms():
            m.sync_remmina()
        self.changed.emit()

    def _export(self) -> None:
        m = self.machine
        if not m:
            return
        addrs = remote.lan_addresses()
        ip = addrs[0].ip
        if len(addrs) > 1:
            ip, ok = QInputDialog.getItem(self, APP_NAME, "Welche Adresse dieses Rechners soll der andere PC nutzen?",
                                          [a.ip for a in addrs], 0, False)
            if not ok:
                return
        folder = QFileDialog.getExistingDirectory(self, "Ordner für die Profile wählen", str(Path.home()))
        if not folder:
            return
        r = m.remote_info()
        files = remote.export_profiles(Path(folder), m.name, m.config.username, m.config.rdp_port,
                                       r["spice_port"], ip)
        msg = "Gespeichert:\n" + "\n".join(f.name for f in files)
        if not r["active"]:
            msg += "\n\nDamit der andere PC sich verbinden kann, „Fernzugriff einschalten“."
        QMessageBox.information(self, APP_NAME, msg)

    def _firewall(self, ask: bool, machine: vm.VM | None = None) -> None:
        m = machine or self.machine
        if not m:
            return
        r = m.remote_info()
        ports = [m.config.rdp_port] + ([r["spice_port"]] if r["spice_lan"] else [])
        nets = ", ".join(sorted({a.network for a in remote.lan_addresses()})) or "Heimnetz"
        q = (f"Die Firewall dieses Rechners ist aktiv.\n\nPorts {', '.join(map(str, ports))} jetzt nur für das "
             f"Heimnetz ({nets}) freigeben?\nDafür werden Administratorrechte abgefragt.\n\n{remote.LAN_WARNING}")
        if ask and QMessageBox.question(self, APP_NAME, q) != QMessageBox.Yes:
            return
        result: list = []
        w = TaskWorker(lambda: result.append(remote.allow_firewall(m.name, ports, gui=True)))
        w.failed.connect(lambda msg: QMessageBox.warning(self, APP_NAME, msg))
        w.finished.connect(lambda: result and QMessageBox.information(self, APP_NAME, result[0][1]))
        self.workers.append(w)
        w.start()
