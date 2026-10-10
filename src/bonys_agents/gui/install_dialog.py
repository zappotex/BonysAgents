# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Programme hinzufügen“: fehlende Apps per SSH in einen laufenden Agent-PC installieren."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from bonys_agents import apps, vm

from . import style
from .widgets import PercentBar, make_scrollable


class InstallWorker(QThread):
    log = Signal(str)
    step = Signal(int, str)       # (Nummer, App-Name)
    done = Signal(bool, str)      # (Erfolg, Meldung)

    def __init__(self, machine: vm.VM, app_ids: list[str], password: str):
        super().__init__()
        self.machine = machine
        self.app_ids = app_ids
        self.password = password

    def run(self) -> None:
        try:
            for i, app_id in enumerate(self.app_ids):
                self.step.emit(i, apps.APPS[app_id].name)
                self.machine.install_app(app_id, password=self.password or None, log=self.log.emit)
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            self.done.emit(False, str(e))
        else:
            self.done.emit(True, "Fertig – die Symbole liegen auf dem Schreibtisch des Agent-PCs.")
        finally:
            self.password = ""  # nicht länger als nötig im Speicher halten


class InstallAppsDialog(QDialog):
    def __init__(self, machine: vm.VM, parent=None, preselect: list[str] | tuple[str, ...] = ()):
        super().__init__(parent)
        self.machine = machine
        self.worker: InstallWorker | None = None
        self.setWindowTitle("Programme hinzufügen")

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Programme hinzufügen")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(f"Installiert fehlende Programme in „{machine.name}“, während er läuft.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.boxes: dict[str, QCheckBox] = {}
        choices = QVBoxLayout()
        choices.setSpacing(2)
        root.addLayout(choices)
        for a in machine.missing_apps():
            cb = QCheckBox(a.name)
            cb.setToolTip(a.description)
            desc = QLabel(a.description)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            desc.setContentsMargins(26, 0, 0, 4)
            choices.addWidget(cb)
            choices.addWidget(desc)
            self.boxes[a.id] = cb
            cb.setChecked(a.id in preselect)
            cb.toggled.connect(self._update)

        pw_label = QLabel(f"Passwort des Benutzers „{machine.config.username}“ im Agent-PC")
        pw_label.setObjectName("Section")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("wird nur für diese Installation verwendet und nicht gespeichert")
        root.addSpacing(6)
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
        self._update()

    def selected(self) -> list[str]:
        return [i for i, cb in self.boxes.items() if cb.isChecked()]

    def _update(self, *_):
        busy = bool(self.worker and self.worker.isRunning())
        self.ok_btn.setEnabled(not busy and bool(self.selected()) and bool(self.pw.text()))

    def _install(self) -> None:
        ids = self.selected()
        self.log.clear()
        self.log.setVisible(True)
        self.progress.setVisible(True)
        self.progress.set_percent(None)
        self.status.setText("")
        for w in (*self.boxes.values(), self.pw, self.close_btn):
            w.setEnabled(False)
        self.worker = InstallWorker(self.machine, ids, self.pw.text())
        self.pw.clear()
        self.worker.log.connect(self._log)
        self.worker.step.connect(lambda i, name: self.status.setText(f"Installiere {name} ({i + 1} von {len(ids)}) …"))
        self.worker.done.connect(self._done)
        self.worker.start()
        self._update()

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)

    def _done(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(msg)
        self.status.setStyleSheet(f"color: {style.OK if ok else style.DANGER};")
        self.close_btn.setEnabled(True)
        self.pw.setEnabled(True)
        # Erfolgreich installierte Apps aus der Auswahl nehmen
        for app_id, cb in self.boxes.items():
            installed = app_id in self.machine.config.apps
            cb.setEnabled(not installed)
            if installed:
                cb.setChecked(False)
                cb.setText(f"{apps.APPS[app_id].name} – installiert")
        self._update()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
