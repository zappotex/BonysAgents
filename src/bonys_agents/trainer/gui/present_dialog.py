# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: „Vorführen …“ – laufenden Agent-PC live im Browser der Teilnehmer zeigen (nur Kursleiter-Version)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from bonys_agents import APP_NAME, host, rfb, share, vm
from bonys_agents.gui import style
from bonys_agents.gui.share_dialogs import code_style, qr_pixmap
from bonys_agents.gui.widgets import make_scrollable
from bonys_agents.trainer import present, share_server


class PresentDialog(QDialog):
    """Kursleiter: Vorführung starten – Code, Adressen, QR-Code, Zuschauer, Pause, Entfernen, Beenden."""

    def __init__(self, machine: vm.VM, parent=None, restart: Callable[[], None] | None = None,
                 help_desk: Callable[[], None] | None = None):
        super().__init__(parent)
        from .helpdesk_dialog import CourseHub

        self.hub = CourseHub.get()
        self.m = machine
        self.restart = restart
        self.help_desk = help_desk
        self.pres: present.Presentation | None = None
        self.setWindowTitle("Vorführen")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(f"„{machine.name}“ vorführen")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Die Teilnehmer sehen den Bildschirm dieses Agent-PCs live im Browser (Laptop, Tablet, Handy) – "
                       "nur ansehen: Tippen und Klicken der Zuschauer kommt nie im Agent-PC an. Im selben Netz oder im "
                       "VPN, nur mit Code, verschlüsselt (HTTPS). " + present.SOUND_HINT)
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)

        # Agent-PC wurde mit einer älteren Version gestartet → erst neu starten
        self.restart_box = QFrame()
        self.restart_box.setObjectName("Hint")
        rb = QHBoxLayout(self.restart_box)
        self.restart_text = QLabel("Dieser Agent-PC wurde mit einer älteren Version gestartet und zeigt seinen "
                                   "Bildschirm noch nicht für Schulungen. Einmal neu starten – danach geht "
                                   "„Vorführen“ immer.")
        self.restart_text.setWordWrap(True)
        self.restart_btn = QPushButton("Jetzt neu starten")
        self.restart_btn.setObjectName("Primary")
        rb.addWidget(self.restart_text, 1)
        rb.addWidget(self.restart_btn)
        root.addWidget(self.restart_box)

        self.settings_box = QFrame()
        self.settings = QFormLayout(self.settings_box)
        self.settings.setContentsMargins(0, 0, 0, 0)
        self.quality = QComboBox()
        for key, label in present.QUALITY_LABELS.items():
            self.quality.addItem(f"{label} – {rfb.QUALITY[key][2]} Bilder/s", key)
        self.quality.setCurrentIndex(self.quality.findData(present.DEFAULT_QUALITY))
        self.quality.setToolTip("Bei vielen Zuschauern oder hoher Last senkt Bony's Agents die Bildrate automatisch.")
        self.viewers = QSpinBox()
        self.viewers.setRange(1, 200)
        self.viewers.setValue(present.DEFAULT_MAX_VIEWERS)
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 24 * 60)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(present.DEFAULT_TIMEOUT_MIN)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(present.DEFAULT_PORT)
        self.settings.addRow("Qualität", self.quality)
        self.settings.addRow("Höchstens Zuschauer", self.viewers)
        self.settings.addRow("Endet nach", self.minutes)
        self.settings.addRow("Port", self.port)
        root.addWidget(self.settings_box)

        # Während der Vorführung
        self.pause_banner = QLabel("PAUSE – die Teilnehmer sehen „Gleich geht's weiter“, kein Bild.")
        self.pause_banner.setAlignment(Qt.AlignCenter)
        self.pause_banner.setStyleSheet(f"background: {style.WARN}; color: #111; font-weight: bold; padding: 8px; "
                                        "border-radius: 6px;")
        root.addWidget(self.pause_banner)
        self.live = QHBoxLayout()
        left = QVBoxLayout()
        self.code = QLabel()
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Schrift per Stylesheet – das App-Stylesheet überschreibt setFont() bei QLabel
        self.code.setStyleSheet(code_style())
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        left.addWidget(self.code)
        left.addWidget(self.info)
        left.addStretch(1)
        self.live.addLayout(left, 1)
        self.qr = QLabel()
        self.qr.setToolTip("Mit der Handy-Kamera scannen: öffnet die Vorführung im Browser, der Code ist schon "
                           "eingetragen.")
        self.live.addWidget(self.qr, 0, Qt.AlignTop)
        root.addLayout(self.live)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Zuschauer", "Adresse", "Status", "Eingaben verworfen"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(style.px(110))
        root.addWidget(self.table, 1)
        # Knöpfe zur Liste – nicht in der Knopfzeile unten, die sonst unter Windows zu breit wird
        table_buttons = QHBoxLayout()
        self.help_btn = QPushButton("Hilfe-Anfragen …")
        self.help_btn.setToolTip("Teilnehmer, die Hilfe angefordert haben – gleicher Code wie die Vorführung")
        self.help_btn.setVisible(help_desk is not None)
        table_buttons.addWidget(self.help_btn)
        self.remove_btn = QPushButton("Zuschauer entfernen")
        self.remove_btn.setToolTip("Ausgewählten Zuschauer trennen – von seiner Adresse aus 5 Minuten gesperrt")
        table_buttons.addWidget(self.remove_btn)
        table_buttons.addStretch(1)
        root.addLayout(table_buttons)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumHeight(style.px(80))
        root.addWidget(self.events)
        self.firewall = QLabel(share_server.FIREWALL_HINTS.get(host.detect().os, "").format(port=present.DEFAULT_PORT))
        self.firewall.setWordWrap(True)
        self.firewall.setObjectName("Muted")
        root.addWidget(self.firewall)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setToolTip("Vor dem Eingeben von Passwörtern oder Tokens: niemand sieht etwas, bis „Weiter“")
        self.start_btn = QPushButton("Vorführung starten")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Vorführung beenden")
        self.stop_btn.setObjectName("Danger")
        for b in (self.close_btn, self.pause_btn, self.stop_btn, self.start_btn):
            buttons.addWidget(b)
        root.addLayout(buttons)
        for w in (self.pause_banner, self.code, self.info, self.qr, self.table, self.events, self.remove_btn,
                  self.pause_btn, self.stop_btn):
            w.setVisible(False)
        make_scrollable(self, 760)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.port.valueChanged.connect(lambda v: self.firewall.setText(
            share_server.FIREWALL_HINTS.get(host.detect().os, "").format(port=v)))
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.remove_btn.clicked.connect(self._remove)
        self.close_btn.clicked.connect(self.reject)
        self.restart_btn.clicked.connect(self._restart)
        if help_desk is not None:
            self.help_btn.clicked.connect(help_desk)
        self._check_ready()
        running = self.hub.running()
        if running is not None:   # Kurs-Server läuft schon (Hilfe-Schalter) – Code und Port bleiben
            self.port.setValue(running.port)
            self.port.setEnabled(False)
            self.minutes.setEnabled(False)
            if running.has_screen and running.title == machine.name:
                self.pres = running
                self._show_live()

    # ---------- vor dem Start ----------
    def _check_ready(self) -> None:
        running = self.m.is_running()
        needs_restart = running and not self.m.vnc_available()
        self.restart_box.setVisible(needs_restart)
        ok = running and not needs_restart and present.novnc_dir() is not None
        self.start_btn.setEnabled(ok)
        if not running:
            self.status.setText("Der Agent-PC läuft nicht – bitte zuerst starten.")
        elif present.novnc_dir() is None:
            self.status.setText("noVNC fehlt in dieser Installation – Vorführen geht nicht.")
        elif not needs_restart:
            self.status.setText("")

    def _restart(self) -> None:
        if QMessageBox.question(self, APP_NAME, f"„{self.m.name}“ jetzt herunterfahren und wieder starten? Nicht "
                                "gespeicherte Arbeit im Agent-PC geht verloren.") != QMessageBox.Yes:
            return
        if self.restart:
            self.restart()
        self.restart_btn.setEnabled(False)
        self.status.setText("Startet neu … „Vorführung starten“ geht, sobald der Agent-PC wieder läuft.")
        QTimer.singleShot(2000, self._wait_restart)

    def _wait_restart(self) -> None:
        if self.m.vnc_available():
            self.restart_btn.setEnabled(True)
            self._check_ready()
            return
        if self.isVisible():
            QTimer.singleShot(2000, self._wait_restart)

    def _start(self) -> None:
        box = QMessageBox(QMessageBox.Warning, "Vorführen", present.WARNING, QMessageBox.Ok | QMessageBox.Cancel, self)
        box.button(QMessageBox.Ok).setText("Verstanden – starten")
        box.button(QMessageBox.Cancel).setText("Abbrechen")
        if box.exec() != QMessageBox.Ok:
            return
        try:
            running = self.hub.running()
            if running is not None:
                if not self.m.vnc_available():
                    raise present.NeedsRestart("Der Agent-PC zeigt seinen Bildschirm noch nicht – neu starten.")
                running.set_screen(self.m.name, self.m.vnc_connect, is_alive=self.m.is_running,
                                   quality=self.quality.currentData(), max_viewers=self.viewers.value())
                p = running
            else:
                p = present.for_vm(self.m, port=self.port.value(), timeout_min=self.minutes.value(),
                                   max_viewers=self.viewers.value(), quality=self.quality.currentData())
                p.start()
                self.hub.adopt(p)
        except (OSError, ValueError, present.PresentError) as e:
            self.status.setText(f"Fehler: {e}")
            self.status.setStyleSheet(f"color: {style.DANGER};")
            self._check_ready()
            return
        self.pres = p
        self._show_live()

    def _show_live(self) -> None:
        p = self.pres
        self.settings_box.setVisible(False)
        self.start_btn.setVisible(False)
        for w in (self.code, self.info, self.table, self.events, self.remove_btn, self.pause_btn, self.stop_btn):
            w.setVisible(True)
        self.code.setText(p.code)
        rows = []
        for a in p.addresses():
            kind = share.address_kind(a)
            rows.append(f"Im Browser öffnen: <b>https://{a}:{p.port}</b>" + (f" ({kind})" if kind else ""))
        rows.append(f"Fingerabdruck: <b>{share.short_fingerprint(p.fingerprint)}</b> – der Browser warnt vor dem "
                    "Zertifikat; Teilnehmer können ihn in den Zertifikatsdetails vergleichen")
        rows.append(f"<span style='font-size:small'>{share.format_fingerprint(p.fingerprint)}</span>")
        rows.append("In Bony's Agents: „Kurse“ → „Schulung im Netzwerk beitreten“ zeigt die Vorführung auch an.")
        self.info.setText("<br>".join(rows))
        pix = qr_pixmap(p.url(), style.px(200))
        if pix is not None:
            self.qr.setPixmap(pix)
            self.qr.setVisible(True)
        self.status.setStyleSheet("")
        self.timer.start()
        self._refresh()

    # ---------- während der Vorführung ----------
    def _refresh(self) -> None:
        p = self.pres
        if p is None:
            return
        viewers = p.viewer_list()
        with p.lock:
            events = list(p.events)
        self.table.setRowCount(len(viewers))
        for i, v in enumerate(viewers):
            state = "verbunden" if v.connected else "getrennt (verbindet neu …)"
            if p.paused:
                state = "Pause"
            for col, text in enumerate((v.name, v.address, state, str(v.dropped_input) if v.dropped_input else "")):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, v.id)
                self.table.setItem(i, col, item)
        text = "\n".join(events)
        if text != self.events.toPlainText():
            self.events.setPlainText(text)
            self.events.verticalScrollBar().setValue(self.events.verticalScrollBar().maximum())
        self.pause_banner.setVisible(p.paused and not p.stopped.is_set())
        self.pause_btn.setText("Weiter" if p.paused else "Pause")
        self.pause_btn.setObjectName("Primary" if p.paused else "")
        self.pause_btn.style().unpolish(self.pause_btn)
        self.pause_btn.style().polish(self.pause_btn)
        if p.stopped.is_set() or not p.has_screen:
            self.timer.stop()
            self.pause_banner.setVisible(False)
            self.status.setText(p.stop_reason if p.stopped.is_set() else "Vorführung beendet – der Hilfe-Schalter "
                                "läuft weiter (gleicher Code).")
            for w in (self.stop_btn, self.pause_btn, self.remove_btn):
                w.setVisible(False)
            self.code.setStyleSheet(code_style() + " text-decoration: line-through;")
            return
        left = p.remaining()
        self.status.setText(f"Vorführung läuft – endet in {int(left // 60)} min {int(left % 60):02d} s · "
                            f"{len(viewers)} von höchstens {p.max_viewers} Zuschauern · {p.fps():.0f} Bilder/s"
                            + (f" · CPU {p.cpu_percent:.0f} %" if p.cpu_percent else ""))

    def _toggle_pause(self) -> None:
        if self.pres:
            self.pres.set_paused(not self.pres.paused)
            self._refresh()

    def _remove(self) -> None:
        if not self.pres:
            return
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, APP_NAME, "Bitte zuerst einen Zuschauer in der Liste auswählen.")
            return
        if QMessageBox.question(self, APP_NAME, f"„{item.text()}“ von der Vorführung entfernen?") == QMessageBox.Yes:
            self.pres.remove_viewer(item.data(Qt.UserRole))
            self._refresh()

    def _live(self) -> bool:
        return bool(self.pres) and not self.pres.stopped.is_set() and self.pres.has_screen

    def _stop(self) -> None:
        if self._live():
            self.hub.end_presentation()
            self._refresh()

    def reject(self) -> None:
        if self._live():
            if QMessageBox.question(self, APP_NAME, "Vorführung beenden?") != QMessageBox.Yes:
                return
            self._stop()
        self.timer.stop()
        super().reject()
