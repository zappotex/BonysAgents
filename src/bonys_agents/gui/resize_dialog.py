# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Festplatte vergrößern“."""

from __future__ import annotations

import shutil

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from bonys_agents import APP_NAME, storage, vm

from . import style
from .widgets import DiskSlider, make_scrollable


class ResizeDialog(QDialog):
    def __init__(self, machine: vm.VM, parent=None):
        super().__init__(parent)
        self.machine = machine
        current = machine.config.disk_gb
        self.setWindowTitle("Festplatte vergrößern")

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Festplatte vergrößern")
        title.setObjectName("Title")
        root.addWidget(title)
        info = QLabel(f"„{machine.name}“ hat zurzeit {vm.format_gb(current)}. "
                      "Vergrößern geht jederzeit, verkleinern nicht.")
        info.setWordWrap(True)
        root.addWidget(info)

        bigger = next(gb for gb in vm.DISK_STEPS_GB if gb > current)
        self.slider = DiskSlider(bigger, minimum=bigger)
        root.addWidget(self.slider)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        root.addWidget(self.msg)
        note = QLabel("Der Agent-PC nutzt den neuen Platz automatisch beim nächsten Start.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Vergrößern")
        self.ok_btn.setObjectName("Primary")
        row.addWidget(cancel)
        row.addWidget(self.ok_btn)
        root.addLayout(row)
        make_scrollable(self, 480)

        cancel.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._resize)
        self.slider.valueChanged.connect(self._check)
        self._check()

    def _check(self, *_):
        gb = self.slider.value()
        try:
            free = shutil.disk_usage(self.machine.location).free
        except OSError:
            free = None
        if free is not None and free < gb * storage.GB:
            self.msg.setText(f"⚠  Auf dem Laufwerk sind nur {free / storage.GB:.0f} GB frei. Die Festplatte "
                             f"({vm.format_gb(gb)}) wächst erst bei Bedarf, kann das Laufwerk aber irgendwann füllen.")
            self.msg.setStyleSheet(f"color: {style.WARN};")
        else:
            self.msg.setText("")

    def _resize(self) -> None:
        try:
            self.machine.resize(self.slider.value())
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            QMessageBox.critical(self, APP_NAME, str(e))
            return
        self.accept()
