# SPDX-License-Identifier: GPL-3.0-or-later
"""Auswahl des Speicherorts: Laufwerke mit freiem Platz, eigener Ordner, Prüfung."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget,
)

from bonys_agents import storage

from . import style
from .widgets import PathLabel

CUSTOM = "__custom__"


class LocationPicker(QWidget):
    """Kombi-Box mit allen Laufwerken + „Anderer Ordner …“ und Live-Prüfung."""

    changed = Signal()

    def __init__(self, disk_gb: int = 50, exclude: Path | None = None, min_free_gb: float | None = None, parent=None):
        super().__init__(parent)
        self.disk_gb = disk_gb
        self.min_free_gb = storage.MIN_FREE_GB if min_free_gb is None else min_free_gb
        self.exclude = exclude
        self._custom: Path | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(style.px(260))
        self.combo.setMinimumHeight(style.px(34))
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_btn.setMinimumHeight(style.px(34))
        self.refresh_btn.setToolTip("Laufwerke neu einlesen (z. B. nach dem Einstecken einer SSD)")
        row.addWidget(self.combo, 1)
        row.addWidget(self.refresh_btn)
        lay.addLayout(row)

        self.path_label = PathLabel(prefix="Ordner: ")
        self.path_label.setObjectName("Muted")
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        lay.addWidget(self.path_label)
        lay.addWidget(self.msg)

        self.combo.activated.connect(self._on_activated)
        self.combo.currentIndexChanged.connect(lambda *_: self._update())
        self.refresh_btn.clicked.connect(self.reload)
        self.reload()

    # ---------- Einträge ----------
    def reload(self) -> None:
        current = self.path()
        self.combo.blockSignals(True)
        self.combo.clear()
        seen: set[str] = set()

        def add(text: str, path: Path) -> None:
            key = str(path)
            if key in seen or (self.exclude and Path(key) == self.exclude):
                return
            seen.add(key)
            self.combo.addItem(text, key)

        default = storage.default_library()
        sys_drive = storage.drive_for(default)
        free = f", {sys_drive.free / storage.GB:.0f} GB frei" if sys_drive else ""
        add(f"Hauptsystem (Benutzerordner){free}", default)

        for d in storage.drives():
            if sys_drive and d.mount == sys_drive.mount:
                continue  # Hauptsystem steht schon oben
            add(d.describe(), d.library)

        for loc in storage.load_settings()["locations"]:
            p = Path(loc)
            if p.exists():
                add(f"Gespeichert: {p}", p)
        if self._custom:
            add(f"Ordner: {self._custom}", self._custom)
        self.combo.addItem("Anderer Ordner …", CUSTOM)

        want = str(current) if current else str(storage.preferred_library())
        idx = self.combo.findData(want)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo.blockSignals(False)
        self._update()

    def _on_activated(self, _index: int) -> None:
        if self.combo.currentData() != CUSTOM:
            return
        start = str(self._custom or storage.preferred_library().parent)
        chosen = QFileDialog.getExistingDirectory(self, "Speicherort wählen", start)
        if chosen:
            p = Path(chosen)
            # Wer direkt ein Laufwerk wählt, bekommt einen aufgeräumten Unterordner.
            if p.parent == p or p == Path(p.anchor):
                p = p / storage.LIBRARY_DIRNAME
            self._custom = p
            self.reload()
            self.combo.setCurrentIndex(self.combo.findData(str(p)))
        else:
            self.combo.setCurrentIndex(0)

    # ---------- Zustand ----------
    def path(self) -> Path | None:
        data = self.combo.currentData() if hasattr(self, "combo") else None
        return Path(data) if data and data != CUSTOM else None

    def set_disk_gb(self, gb: int) -> None:
        self.disk_gb = gb
        self._update()

    def check(self) -> storage.LocationCheck | None:
        p = self.path()
        return storage.check_location(p, self.disk_gb, min_free_gb=self.min_free_gb) if p else None

    def _update(self) -> None:
        p = self.path()
        if p is None:
            self.path_label.set_path("")
            self.msg.setText("")
            self.changed.emit()
            return
        self.path_label.set_path(p)
        chk = self.check()
        if chk.errors:
            self.msg.setText("✕  " + " ".join(chk.errors))
            self.msg.setStyleSheet(f"color: {style.DANGER};")
        elif chk.warnings:
            self.msg.setText("⚠  " + " ".join(chk.warnings))
            self.msg.setStyleSheet(f"color: {style.WARN};")
        else:
            self.msg.setText("✓  Passt.")
            self.msg.setStyleSheet(f"color: {style.OK};")
        self.changed.emit()
