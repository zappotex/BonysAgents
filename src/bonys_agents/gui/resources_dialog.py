# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Leistung ändern“: CPU-Kerne und Arbeitsspeicher eines bestehenden Agent-PCs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from bonys_agents import desktops, host, vm

from . import style
from .create_dialog import _slider_row
from .widgets import make_scrollable


class ResourcesDialog(QDialog):
    """Wählt nur die Werte – ändern (und bei Bedarf neu starten) erledigt das Hauptfenster."""

    def __init__(self, machine: vm.VM, info: host.HostInfo, running: bool, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.info = info
        c = machine.config
        self.recommended = min(machine.recommended_ram_mb(), info.max_vm_ram_mb)
        self.setWindowTitle("Leistung ändern")

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Leistung ändern")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(f"„{machine.name}“ hat zurzeit {c.cpus} Kerne und {desktops.format_ram(c.ram_mb)} "
                       "Arbeitsspeicher. Hängen Programme oder öffnet sich ein Fenster nicht, hilft oft mehr "
                       "Arbeitsspeicher.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        self.cpu = QSlider(Qt.Horizontal)
        self.cpu.setRange(1, info.cpus)
        self.cpu.setValue(min(c.cpus, info.cpus))
        self.cpu_label = QLabel()
        form.addRow("CPU-Kerne", _slider_row(self.cpu, self.cpu_label))
        self.ram = QSlider(Qt.Horizontal)
        self.ram.setRange(host.MIN_VM_RAM_MB // 512, info.max_vm_ram_mb // 512)
        self.ram.setValue(min(max(c.ram_mb, host.MIN_VM_RAM_MB), info.max_vm_ram_mb) // 512)
        self.ram_label = QLabel()
        form.addRow("Arbeitsspeicher", _slider_row(self.ram, self.ram_label))
        root.addLayout(form)

        rec_row = QHBoxLayout()
        rec = QLabel(f"Empfohlen für diesen Agent-PC: {desktops.format_ram(self.recommended)} "
                     f"({desktops.name(c.desktop)}, Programme und etwas Puffer für Browser und Agent)")
        rec.setObjectName("Muted")
        rec.setWordWrap(True)
        rec_row.addWidget(rec, 1)
        self.rec_btn = QPushButton("Empfehlung übernehmen")
        self.rec_btn.setObjectName("Small")
        rec_row.addWidget(self.rec_btn)
        root.addLayout(rec_row)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(f"color: {style.WARN};")
        root.addWidget(self.msg)
        reserve = info.ram_mb - info.max_vm_ram_mb
        note = QLabel(f"Dieser Rechner hat {info.ram_mb // 1024} GB RAM – {desktops.format_ram(reserve)} bleiben für "
                      "ihn reserviert. Laufen mehrere Agent-PCs gleichzeitig, teilen sie sich den Rest."
                      + ("\nDer Agent-PC wird dafür heruntergefahren und mit den neuen Werten neu gestartet."
                         if running else "\nDie neuen Werte gelten ab dem nächsten Start."))
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Übernehmen und neu starten" if running else "Übernehmen")
        self.ok_btn.setObjectName("Primary")
        row.addWidget(cancel)
        row.addWidget(self.ok_btn)
        root.addLayout(row)
        make_scrollable(self, 520)

        cancel.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self.accept)
        self.rec_btn.clicked.connect(lambda: self.ram.setValue(self.recommended // 512))
        self.cpu.valueChanged.connect(self._check)
        self.ram.valueChanged.connect(self._check)
        self._check()

    @property
    def cpus(self) -> int:
        return self.cpu.value()

    @property
    def ram_mb(self) -> int:
        return self.ram.value() * 512

    def _check(self, *_) -> None:
        c = self.machine.config
        self.cpu_label.setText(f"{self.cpus} von {self.info.cpus}")
        self.ram_label.setText(desktops.format_ram(self.ram_mb))
        warning = desktops.ram_warning(c.desktop, self.ram_mb)
        if not warning and self.ram_mb < self.recommended:
            warning = (f"Weniger als empfohlen ({desktops.format_ram(self.recommended)}) – mit Browser, Docker und "
                       "Agent gleichzeitig kann es eng werden.")
        self.msg.setText(f"⚠  {warning}" if warning else "")
        self.msg.setVisible(bool(warning))
        self.rec_btn.setEnabled(self.ram_mb != self.recommended)
        self.ok_btn.setEnabled((self.cpus, self.ram_mb) != (c.cpus, c.ram_mb))
