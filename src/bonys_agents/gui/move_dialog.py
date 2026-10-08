# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Agent-PC verschieben“ – z. B. vom Hauptsystem auf eine externe SSD."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from bonys_agents import storage, vm

from . import style
from .location_picker import LocationPicker
from .widgets import PathLabel, make_scrollable


class MoveWorker(QThread):
    progress = Signal(str, float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, name: str, target):
        super().__init__()
        self.name = name
        self.target = target

    def run(self) -> None:
        try:
            moved = vm.move(self.name, self.target, progress=self.progress.emit)
            self.finished_ok.emit(str(moved.path))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class MoveDialog(QDialog):
    def __init__(self, machine: vm.VM, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.worker: MoveWorker | None = None
        self.setWindowTitle("Agent-PC verschieben")

        root = QVBoxLayout(self)
        root.setSpacing(12)
        title = QLabel(f"„{machine.name}“ verschieben")
        title.setObjectName("Title")
        root.addWidget(title)
        size_gb = machine.size_on_disk() / storage.GB
        now = PathLabel(machine.path, prefix="Liegt jetzt in: ")
        now.setObjectName("Muted")
        used = QLabel(f"Belegt: {size_gb:.1f} GB")
        used.setObjectName("Muted")
        root.addWidget(now)
        root.addWidget(used)

        root.addWidget(QLabel("Neuer Speicherort:"))
        self.picker = LocationPicker(
            max(1, int(size_gb + 0.999)), exclude=machine.location, min_free_gb=size_gb + 0.25
        )
        root.addWidget(self.picker)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Verschieben")
        self.ok_btn.setObjectName("Primary")
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        root.addLayout(buttons)
        make_scrollable(self, 560)

        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._move)
        self.picker.changed.connect(self._update_ok)
        self._update_ok()

    def _update_ok(self) -> None:
        chk = self.picker.check()
        self.ok_btn.setEnabled(bool(chk and chk.ok))
        target = self.picker.path()
        if target is not None and vm.move_makes_independent(self.machine, target):
            self.status.setStyleSheet(f"color: {style.WARN};")
            self.status.setText("Hinweis: Dieser Agent-PC ist mit einer Vorlage verknüpft, die auf dem alten Laufwerk "
                                "bleibt. Beim Verschieben wird er automatisch zu einer unabhängigen Kopie (braucht "
                                "mehr Platz und etwas länger).")
        elif not (self.worker and self.worker.isRunning()):
            self.status.setStyleSheet("")
            self.status.setText("")

    def _move(self) -> None:
        target = self.picker.path()
        if target is None:
            return
        for w in (self.ok_btn, self.cancel_btn, self.picker):
            w.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setStyleSheet("")
        self.status.setText("Starte …")
        self.worker = MoveWorker(self.machine.name, target)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, _phase: str, frac: float, msg: str) -> None:
        self.progress.setValue(int(frac * 1000))
        self.status.setText(msg)

    def _on_done(self, path: str) -> None:
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        for w in (self.cancel_btn, self.picker):
            w.setEnabled(True)
        self._update_ok()
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
