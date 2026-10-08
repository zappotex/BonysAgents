# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Desktop hinzufügen“: weiteren Desktop per SSH in einen laufenden Agent-PC installieren."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QVBoxLayout,
)

from bonys_agents import desktops, vm

from . import style
from .widgets import PercentBar, make_scrollable


class DesktopWorker(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, machine: vm.VM, desktop_id: str, make_default: bool, password: str):
        super().__init__()
        self.machine, self.desktop_id, self.make_default, self.password = machine, desktop_id, make_default, password

    def run(self) -> None:
        name = desktops.name(self.desktop_id)
        try:
            self.machine.install_desktop(self.desktop_id, self.make_default, password=self.password or None,
                                         log=self.log.emit)
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            self.done.emit(False, str(e))
        else:
            self.done.emit(True, f"Fertig – ab dem nächsten Start meldet sich der Agent-PC in {name} an."
                           if self.make_default else f"Fertig – {name} lässt sich am Anmeldebildschirm wählen.")
        finally:
            self.password = ""


class AddDesktopDialog(QDialog):
    def __init__(self, machine: vm.VM, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.worker: DesktopWorker | None = None
        self.setWindowTitle("Desktop hinzufügen")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Desktop hinzufügen")
        title.setObjectName("Title")
        root.addWidget(title)
        current = desktops.name(machine.config.desktop)
        intro = QLabel(f"Installiert einen weiteren Desktop in „{machine.name}“, während er läuft. Der bisherige "
                       f"Desktop ({current}) bleibt installiert und lässt sich am Anmeldebildschirm weiter wählen.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.group = QButtonGroup(self)
        installed = machine.installed_desktops()
        for d in desktops.DESKTOPS.values():
            rb = QRadioButton(f"{d.name}  (ab {desktops.format_ram(d.min_ram_mb)} RAM)"
                              + ("  – installiert" if d.id in installed else ""))
            rb.setProperty("desktop", d.id)
            rb.setEnabled(d.id != machine.config.desktop)
            desc = QLabel(d.description)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            desc.setContentsMargins(26, 0, 0, 4)
            self.group.addButton(rb)
            root.addWidget(rb)
            root.addWidget(desc)
        self.default = QCheckBox("Als Standard: künftig automatisch in diesen Desktop anmelden")
        self.default.setChecked(True)
        root.addWidget(self.default)
        self.ram_warn = QLabel()
        self.ram_warn.setWordWrap(True)
        self.ram_warn.setStyleSheet(f"color: {style.WARN};")
        root.addWidget(self.ram_warn)

        pw_label = QLabel(f"Passwort des Benutzers „{machine.config.username}“ im Agent-PC")
        pw_label.setObjectName("Section")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("wird nur für diese Installation verwendet und nicht gespeichert")
        root.addWidget(pw_label)
        root.addWidget(self.pw)
        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        self.log.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.log, 1)
        root.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.ok_btn = QPushButton("Installieren")
        self.ok_btn.setObjectName("Primary")
        row.addWidget(self.close_btn)
        row.addWidget(self.ok_btn)
        root.addLayout(row)
        make_scrollable(self, 560)
        self.close_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._install)
        self.pw.textChanged.connect(self._update)
        self.group.buttonToggled.connect(self._update)
        self.default.toggled.connect(self._update)
        self._update()

    def selected(self) -> str | None:
        b = self.group.checkedButton()
        return b.property("desktop") if b else None

    def _update(self, *_) -> None:
        busy = bool(self.worker and self.worker.isRunning())
        d = self.selected()
        installed = d in self.machine.installed_desktops() if d else False
        # schon installiert: nur noch „als Standard“ sinnvoll
        if installed:
            self.default.setChecked(True)
        self.default.setEnabled(not installed and not busy)
        warning = desktops.ram_warning(d, self.machine.config.ram_mb) if d else ""
        self.ram_warn.setText(f"⚠ {warning}" if warning else "")
        self.ram_warn.setVisible(bool(warning))
        self.ok_btn.setText("Als Standard festlegen" if installed else "Installieren")
        self.ok_btn.setEnabled(not busy and d is not None and bool(self.pw.text()))

    def _install(self) -> None:
        d = self.selected()
        if not d:
            return
        self.log.clear()
        self.log.setVisible(True)
        self.progress.setVisible(True)
        self.progress.set_percent(None)
        self.status.setStyleSheet("")
        self.status.setText(f"Installiere {desktops.name(d)} … (kann je nach Desktop 5–30 Minuten dauern)")
        for b in self.group.buttons():
            b.setEnabled(False)
        for w in (self.pw, self.close_btn, self.default):
            w.setEnabled(False)
        self.worker = DesktopWorker(self.machine, d, self.default.isChecked(), self.pw.text())
        self.pw.clear()
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.done.connect(self._done)
        self.worker.start()
        self._update()

    def _done(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(msg)
        self.status.setStyleSheet(f"color: {style.OK if ok else style.DANGER};")
        for w in (self.close_btn, self.pw):
            w.setEnabled(True)
        for b in self.group.buttons():
            b.setEnabled(b.property("desktop") != self.machine.config.desktop)
        self._update()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
