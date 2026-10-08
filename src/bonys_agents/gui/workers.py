# SPDX-License-Identifier: GPL-3.0-or-later
"""Hintergrund-Threads, damit das Fenster während langer Aufgaben reagiert."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from bonys_agents import vm


class CreateWorker(QThread):
    progress = Signal(str, float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, params: dict, start_after: bool = True):
        super().__init__()
        self.params = params
        self.start_after = start_after

    def run(self) -> None:
        try:
            machine = vm.create(progress=self.progress.emit, **self.params)
            if self.start_after:
                self.progress.emit("start", 1.0, "Starte Agent-PC …")
                machine.start()
            self.finished_ok.emit(machine.name)
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            self.failed.emit(str(e))


class TaskWorker(QThread):
    """Führt eine kurze Aktion (Start/Stop/Löschen) aus."""

    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self.fn = fn
        self.result = None
        self.error: Exception | None = None  # z. B. vm.NeedsPassword – die Oberfläche fragt dann nach

    def run(self) -> None:
        try:
            self.result = self.fn()
        except Exception as e:  # noqa: BLE001
            self.error = e
            self.failed.emit(str(e))
