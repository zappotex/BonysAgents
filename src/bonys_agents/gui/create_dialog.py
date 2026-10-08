# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Neuer Agent-PC“."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from bonys_agents import apps, desktops, host, storage, templates, vm
from bonys_agents import progress as pct

from . import style
from .location_picker import LocationPicker
from .widgets import DiskSlider, PercentBar, fit_to_screen
from .workers import CreateWorker

TCG_WARNING = ("⚠ Keine Hardware-Beschleunigung (nur Software-Emulation): Die Einrichtung kann mehrere "
               "Stunden dauern und der Agent-PC läuft sehr langsam.\n"
               "Läuft Bony's Agents selbst in einer VM? Dann dort verschachtelte Virtualisierung "
               "aktivieren (z. B. in VirtualBox, VMware, Proxmox oder virt-manager).")

KEYBOARDS = [("Deutsch", "de"), ("Schweiz", "ch"), ("Englisch (US)", "us"), ("Englisch (UK)", "gb"),
             ("Französisch", "fr"), ("Spanisch", "es"), ("Italienisch", "it")]


def _slider_row(slider: QSlider, label: QLabel) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(slider, 1)
    label.setMinimumWidth(style.px(110))
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(label)
    return w


class CreateDialog(QDialog):
    def __init__(self, info: host.HostInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.worker: CreateWorker | None = None
        self.created_name: str | None = None
        self.setWindowTitle("Neuer Agent-PC")

        # Inhalt scrollbar, Knöpfe immer sichtbar – passt so auch auf kleine Laptop-Bildschirme.
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 8, 0)
        root.setSpacing(14)
        title = QLabel("Neuer Agent-PC")
        title.setObjectName("Title")
        root.addWidget(title)

        # Grundlage: neu installieren oder aus einer Vorlage (sofort fertig, keine Downloads)
        self.templates = {t.name: t for t in templates.list_templates() if t.arch == info.arch}
        base_form = QFormLayout()
        base_form.setHorizontalSpacing(16)
        self.base = QComboBox()
        self.base.addItem("Neu installieren (Debian 13)", "")
        for t in self.templates.values():
            self.base.addItem(f"Vorlage: {t.name}", t.name)
        base_form.addRow("Grundlage", self.base)
        root.addLayout(base_form)
        self.base_info = QLabel()
        self.base_info.setObjectName("Muted")
        self.base_info.setWordWrap(True)
        root.addWidget(self.base_info)
        self.kind_box = QWidget()
        kl = QVBoxLayout(self.kind_box)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(2)
        self.linked = QRadioButton("Schnell (verknüpft)")
        self.full = QRadioButton("Unabhängig (vollständige Kopie)")
        kind = QButtonGroup(self)
        kind.addButton(self.linked)
        kind.addButton(self.full)
        self.linked.setChecked(True)
        for rb, text in ((self.linked, "Sofort fertig, braucht kaum Platz – die Vorlage muss auf demselben Laufwerk "
                                       "bleiben."),
                         (self.full, "Braucht mehr Platz und ein paar Minuten, funktioniert aber auch ohne die "
                                     "Vorlage.")):
            desc = QLabel(text)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            desc.setContentsMargins(26, 0, 0, 4)
            kl.addWidget(rb)
            kl.addWidget(desc)
        root.addWidget(self.kind_box)
        self._kind_auto = True  # Auswahl folgt dem Laufwerk, bis jemand selbst wählt

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        n = len(vm.list_vms()) + 1
        self.name = QLineEdit(f"agent-pc-{n}")
        self.user = QLineEdit("agent")
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        form.addRow("Name", self.name)
        form.addRow("Benutzer", self.user)
        form.addRow("Passwort", self.pw1)
        form.addRow("Wiederholen", self.pw2)

        self.cpu = QSlider(Qt.Horizontal)
        self.cpu.setRange(1, info.cpus)
        self.cpu.setValue(info.default_vm_cpus)
        self.cpu_label = QLabel()
        form.addRow("CPU-Kerne", _slider_row(self.cpu, self.cpu_label))

        self.ram = QSlider(Qt.Horizontal)
        self.ram.setRange(host.MIN_VM_RAM_MB // 512, max(info.max_vm_ram_mb // 512, host.MIN_VM_RAM_MB // 512))
        self.ram.setValue(info.default_vm_ram_mb // 512)
        self.ram_label = QLabel()
        form.addRow("Arbeitsspeicher", _slider_row(self.ram, self.ram_label))
        self.ram_warn = QLabel()
        self.ram_warn.setWordWrap(True)
        self.ram_warn.setStyleSheet(f"color: {style.WARN};")
        self.ram_warn.setVisible(False)
        form.addRow("", self.ram_warn)

        self.disk = DiskSlider(vm.DEFAULT_DISK_GB)
        form.addRow("Festplatte", self.disk)

        self.keyboard = QComboBox()
        for label, code in KEYBOARDS:
            self.keyboard.addItem(label, code)
        form.addRow("Tastatur", self.keyboard)

        # Desktop-Umgebung (alle aus Debian 13), mit kurzer Beschreibung und RAM-Empfehlung
        self.desktop = QComboBox()
        for d in desktops.DESKTOPS.values():
            self.desktop.addItem(f"{d.name}  (ab {desktops.format_ram(d.min_ram_mb)} RAM)", d.id)
        self.desktop_info = QLabel()
        self.desktop_info.setObjectName("Muted")
        self.desktop_info.setWordWrap(True)
        dbox = QWidget()
        dl = QVBoxLayout(dbox)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(2)
        dl.addWidget(self.desktop)
        dl.addWidget(self.desktop_info)
        form.addRow("Desktop", dbox)

        root.addLayout(form)

        sec_loc = QLabel("SPEICHERORT – WO SOLL DER AGENT-PC LIEGEN?")
        sec_loc.setObjectName("Section")
        root.addWidget(sec_loc)
        self.location = LocationPicker(self.disk.value())
        self.remember_loc = QCheckBox("Als Standard-Speicherort merken")
        root.addWidget(self.location)
        root.addWidget(self.remember_loc)

        sec = QLabel("PROGRAMME")
        sec.setObjectName("Section")
        root.addWidget(sec)
        self.app_boxes: dict[str, QCheckBox] = {}
        app_row = QHBoxLayout()
        for a in apps.APPS.values():
            if a.category != apps.PROGRAM:
                continue
            cb = QCheckBox(a.name)
            cb.setChecked(a.default)
            cb.setToolTip(a.description)
            self.app_boxes[a.id] = cb
            app_row.addWidget(cb)
        app_row.addStretch(1)
        root.addLayout(app_row)

        # KI-Werkzeuge: frei kombinierbar, auch keins – je mit kurzer Erklärung
        sec_ai = QLabel("KI-WERKZEUGE")
        sec_ai.setObjectName("Section")
        root.addWidget(sec_ai)
        ai_box = QVBoxLayout()
        ai_box.setSpacing(2)
        for a in apps.APPS.values():
            if a.category != apps.AGENT:
                continue
            cb = QCheckBox(a.name)
            cb.setChecked(a.default)
            cb.setToolTip(a.description)
            self.app_boxes[a.id] = cb
            desc = QLabel(a.description)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            desc.setContentsMargins(26, 0, 0, 6)  # unter dem Text des Häkchens
            ai_box.addWidget(cb)
            ai_box.addWidget(desc)
        root.addLayout(ai_box)

        reserve = info.ram_mb - info.max_vm_ram_mb
        hint = QLabel(
            f"Host: {info.cpus} Kerne, {info.ram_mb // 1024} GB RAM. "
            f"{reserve / 1024:.1f} GB RAM bleiben für den Host reserviert (mindestens "
            f"{host.MIN_HOST_RESERVE_MB // 1024} GB), damit er nicht einfriert und QEMU nicht wegen "
            "Speichermangels beendet wird."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        root.addWidget(hint)
        if not info.accel_is_fast:
            warn = QLabel(TCG_WARNING)
            warn.setWordWrap(True)
            warn.setObjectName("Hint")
            warn.setStyleSheet(f"color: {style.WARN}; font-weight: 600; padding: 8px;")
            # ganz oben, damit es niemand übersieht
            root.insertWidget(1, warn)

        self.progress = PercentBar()
        self.progress.setVisible(False)
        self._eta_start: tuple[float, float] | None = None  # (Zeit, Prozent) beim ersten Messwert
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.progress)
        outer.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Erstellen und starten")
        self.ok_btn.setObjectName("Primary")
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        outer.addLayout(buttons)
        root.addStretch(1)
        self.setSizeGripEnabled(True)
        fit_to_screen(self, style.px(600), style.px(860))

        self.disk.valueChanged.connect(self.location.set_disk_gb)
        self.location.changed.connect(self._update_ok)
        self.location.changed.connect(self._update_kind)
        self.base.currentIndexChanged.connect(self._base_changed)
        self.linked.clicked.connect(lambda: setattr(self, "_kind_auto", False))
        self.full.clicked.connect(lambda: setattr(self, "_kind_auto", False))
        self.cpu.valueChanged.connect(self._update_labels)
        self.ram.valueChanged.connect(self._update_labels)
        self.desktop.currentIndexChanged.connect(self._update_labels)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._create)
        self._update_labels()
        self._base_changed()
        self._update_ok()

    def template(self) -> templates.Template | None:
        return self.templates.get(self.base.currentData() or "")

    def _base_changed(self, *_) -> None:
        t = self.template()
        self.kind_box.setVisible(t is not None)
        self.base_info.setVisible(t is not None)
        self.user.setEnabled(t is None)
        self.keyboard.setEnabled(t is None)
        self.desktop.setEnabled(t is None)
        idx = self.desktop.findData(t.desktop if t else desktops.DEFAULT)
        if idx >= 0:
            self.desktop.setCurrentIndex(idx)
        for a, cb in self.app_boxes.items():
            cb.setEnabled(t is None)
            cb.setChecked(a in t.apps if t else apps.APPS[a].default)
        if t is None:
            self.user.setText("agent")
            self.disk.setValue(vm.DEFAULT_DISK_GB)
            self.ok_btn.setText("Erstellen und starten")
            return
        self.user.setText(t.username)
        self.disk.setValue(t.disk_gb)
        idx = self.keyboard.findData(t.keyboard)
        if idx >= 0:
            self.keyboard.setCurrentIndex(idx)
        warn = "" if t.personal_data_removed else "  ⚠ enthält persönliche Daten"
        self.base_info.setText(f"{t.description}\n{templates.describe(t)}{warn}\n"
                               "Programme kommen aus der Vorlage – „Programme hinzufügen …“ geht danach wie gewohnt."
                               if t.description else f"{templates.describe(t)}{warn}\nProgramme kommen aus der "
                               "Vorlage – „Programme hinzufügen …“ geht danach wie gewohnt.")
        self.ok_btn.setText("Erstellen und starten")
        self._kind_auto = True
        self._update_kind()

    def _update_kind(self) -> None:
        t = self.template()
        loc = self.location.path()
        if t is None or loc is None:
            return
        same = templates.same_drive(t, loc)
        self.linked.setEnabled(same)
        self.linked.setToolTip("" if same else "Geht nur, wenn der Agent-PC auf demselben Laufwerk liegt wie die "
                                               f"Vorlage ({t.library}).")
        if not same:
            self.full.setChecked(True)
        elif self._kind_auto:
            self.linked.setChecked(True)

    def _update_ok(self) -> None:
        chk = self.location.check()
        self.ok_btn.setEnabled(bool(chk and chk.ok))

    def _update_labels(self) -> None:
        self.cpu_label.setText(f"{self.cpu.value()} von {self.info.cpus}")
        d = desktops.get(self.desktop.currentData() or desktops.DEFAULT)
        self.desktop_info.setText(d.description)
        warning = desktops.ram_warning(d.id, self.ram.value() * 512)
        self.ram_warn.setText(f"⚠ {warning}")
        self.ram_warn.setVisible(bool(warning))
        self.ram_label.setText(f"{self.ram.value() * 512 / 1024:.1f} GB")

    def _set_busy(self, busy: bool) -> None:
        for w in (self.name, self.user, self.pw1, self.pw2, self.cpu, self.ram, self.disk,
                  self.keyboard, self.desktop, self.ok_btn, self.location, self.remember_loc, *self.app_boxes.values(),
                  self.base, self.linked, self.full):
            w.setEnabled(not busy)
        self.cancel_btn.setEnabled(not busy)
        self.progress.setVisible(busy)
        if not busy:
            self._base_changed()

    def _create(self) -> None:
        if self.pw1.text() != self.pw2.text():
            self.status.setText("Die Passwörter stimmen nicht überein.")
            return
        params = dict(
            name=self.name.text().strip(),
            password=self.pw1.text(),
            cpus=self.cpu.value(),
            ram_mb=self.ram.value() * 512,
            disk_gb=self.disk.value(),
            username=self.user.text().strip(),
            app_ids=[i for i, cb in self.app_boxes.items() if cb.isChecked()],
            keyboard=self.keyboard.currentData(),
            location=self.location.path(),
            desktop=self.desktop.currentData(),
        )
        t = self.template()
        if t is not None:
            if params["disk_gb"] < t.disk_gb:
                self.status.setText(f"Festplatte: mindestens {vm.format_gb(t.disk_gb)} (Größe der Vorlage).")
                return
            for key in ("username", "app_ids", "keyboard", "desktop"):
                params.pop(key)
            params.update(template=t.name, linked=self.linked.isChecked())
        if self.remember_loc.isChecked() and params["location"]:
            storage.set_preferred_library(params["location"])
        self._set_busy(True)
        self.progress.set_percent(0)
        self._eta_start = None
        self.status.setText("Bereite vor …")
        self.worker = CreateWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, phase: str, frac: float, msg: str) -> None:
        if self.template() is not None:
            self.progress.set_percent({"disk": frac * 90, "seed": 92, "done": 95, "start": 98}.get(phase, 0))
            self.status.setText(msg)
            return
        self.progress.set_percent(pct.creation_percent(phase, frac))
        eta = ""
        if phase == "download" and frac > 0:
            # Restzeit nur für den Download – danach schließt sich der Dialog ohnehin.
            now = time.monotonic()
            if self._eta_start is None:
                self._eta_start = (now, frac * 100)
            eta = pct.format_eta(pct.eta_seconds(*self._eta_start, now, frac * 100, min_progress=2, min_elapsed=10))
        self.status.setText(f"{msg} · {eta}" if eta else msg)

    def _on_done(self, name: str) -> None:
        self.created_name = name
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._set_busy(False)
        self._update_ok()
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return  # Während des Anlegens nicht schließen
        super().reject()
