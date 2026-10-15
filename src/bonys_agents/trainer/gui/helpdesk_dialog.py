# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: der eine Kurs-Server (``CourseHub``) und die Hilfe-Anfragen (``HelpDeskDialog``).

Nur in der Kursleiter-Version. Vorführen und Hilfe-Schalter teilen sich Code und Zertifikat.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from bonys_agents import APP_NAME, host, share
from bonys_agents.gui import style
from bonys_agents.gui.share_dialogs import code_style
from bonys_agents.gui.widgets import make_scrollable, open_url
from bonys_agents.helpmode import HelpError
from bonys_agents.trainer import helpdesk, present, share_server

HELP_TIMEOUT_MIN = 240


# ================================================================ Kursleiter
class CourseHub(QObject):
    """Der eine Kurs-Server dieses Programms. Vorführen und Hilfe-Schalter nutzen ihn gemeinsam."""

    changed = Signal()
    new_request = Signal(str)
    _instance: CourseHub | None = None

    @classmethod
    def get(cls) -> CourseHub:
        if cls._instance is None:
            cls._instance = CourseHub()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.server: present.Presentation | None = None
        self.helpdesk_open = False
        self._seen = 0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def running(self) -> present.Presentation | None:
        s = self.server
        return s if s is not None and not s.stopped.is_set() else None

    def adopt(self, server: present.Presentation) -> None:
        self.server = server
        self._seen = server.helpdesk.requests_total
        self._update_keep()
        self.changed.emit()

    def start_help_desk(self, port: int, timeout_min: int) -> present.Presentation:
        s = present.Presentation(port=port, timeout_min=timeout_min)
        s.start()
        self.adopt(s)
        return s

    def help_in_use(self) -> bool:
        s = self.running()
        return bool(s) and (self.helpdesk_open or any(x.connected for x in s.helpdesk.session_list()))

    def _update_keep(self) -> None:
        s = self.running()
        if s is not None:
            s.keep_running = self.help_in_use()

    def end_presentation(self) -> None:
        """„Vorführung beenden“: Läuft der Hilfe-Schalter noch, bleibt der Server an – sonst ganz aus."""
        s = self.running()
        if s is None:
            return
        if self.help_in_use():
            s.clear_screen("Vorführung beendet – der Hilfe-Schalter läuft weiter.")
        else:
            s.stop("Vorführung beendet.")
        self.changed.emit()

    def _poll(self) -> None:
        s = self.running()
        if s is None:
            return
        self._update_keep()
        total = s.helpdesk.requests_total
        if total > self._seen:
            self._seen = total
            latest = max(s.helpdesk.session_list(), key=lambda x: x.requested_at or 0, default=None)
            if latest is not None:
                text = f"Hilfe-Anfrage von {latest.name} ({latest.vm})" + (f": {latest.message}" if latest.message
                                                                            else "")
                self.new_request.emit(text)


def _age(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""


class HelpDeskDialog(QDialog):
    """Kursleiter: Hilfe-Anfragen der Teilnehmer – ansehen (nach Zustimmung), Steuerung anfragen, beenden."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hub = CourseHub.get()
        self.setWindowTitle("Hilfe-Anfragen")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Hilfe-Anfragen")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Teilnehmer fordern in Bony's Agents bei ihrem Agent-PC „Hilfe anfordern“ an. Du siehst ihren "
                       "Agent-PC erst, wenn sie zustimmen – und steuern kannst du ihn nur nach einer zweiten "
                       "Zustimmung. Die Teilnehmer verbinden sich von sich aus mit diesem Rechner (auch über VPN).")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)

        self.settings_box = QFrame()
        form = QFormLayout(self.settings_box)
        form.setContentsMargins(0, 0, 0, 0)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(present.DEFAULT_PORT)
        self.minutes = QSpinBox()
        self.minutes.setRange(10, 24 * 60)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(HELP_TIMEOUT_MIN)
        form.addRow("Port", self.port)
        form.addRow("Endet nach", self.minutes)
        root.addWidget(self.settings_box)

        self.code = QLabel()
        self.code.setStyleSheet(code_style())
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.code)
        root.addWidget(self.info)
        link_row = QHBoxLayout()
        self.link = QLineEdit()
        self.link.setReadOnly(True)
        self.copy_btn = QPushButton("Kopieren")
        self.copy_btn.setObjectName("Small")
        link_row.addWidget(self.link, 1)
        link_row.addWidget(self.copy_btn)
        root.addLayout(link_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Teilnehmer", "Agent-PC", "Nachricht", "Zeit", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setMinimumHeight(style.px(130))
        root.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.view_btn = QPushButton("Ansehen")
        self.view_btn.setObjectName("Primary")
        self.view_btn.setToolTip("Fragt den Teilnehmer – nach seiner Zustimmung öffnet sich der Agent-PC im Browser")
        self.control_btn = QPushButton("Steuerung anfragen")
        self.end_btn = QPushButton("Beenden")
        self.forget_btn = QPushButton("Aus Liste entfernen")
        for b in (self.view_btn, self.control_btn, self.end_btn, self.forget_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        root.addLayout(actions)
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
        self.start_btn = QPushButton("Hilfe-Schalter starten")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Hilfe-Schalter beenden")
        self.stop_btn.setObjectName("Danger")
        for b in (self.close_btn, self.stop_btn, self.start_btn):
            buttons.addWidget(b)
        root.addLayout(buttons)
        make_scrollable(self, 760)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.close_btn.clicked.connect(self.reject)
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.link.text()))
        self.view_btn.clicked.connect(self._view)
        self.control_btn.clicked.connect(lambda: self._act(lambda s, sid: s.helpdesk.request_control(sid)))
        self.end_btn.clicked.connect(lambda: self._act(lambda s, sid: s.helpdesk.end_view(sid)))
        self.forget_btn.clicked.connect(lambda: self._act(lambda s, sid: s.helpdesk.forget(sid)))
        self.port.valueChanged.connect(lambda v: self.firewall.setText(
            share_server.FIREWALL_HINTS.get(host.detect().os, "").format(port=v)))
        self.hub.changed.connect(self._refresh)
        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        super().showEvent(event)
        self.hub.helpdesk_open = True
        self.timer.start()
        self._refresh()

    def _start(self) -> None:
        try:
            self.hub.start_help_desk(self.port.value(), self.minutes.value())
        except (OSError, ValueError, present.PresentError) as e:
            self.status.setText(f"Fehler: {e}")
            self.status.setStyleSheet(f"color: {style.DANGER};")
            return
        self.status.setStyleSheet("")
        self._refresh()

    def _stop(self) -> None:
        s = self.hub.running()
        if s is None:
            return
        busy = [x for x in s.helpdesk.session_list() if x.view_allowed]
        extra = " Die Vorführung endet dann ebenfalls." if s.has_screen else ""
        if QMessageBox.question(self, APP_NAME, (f"{len(busy)} Hilfe läuft gerade. " if busy else "")
                                + "Hilfe-Schalter beenden? Teilnehmer können dann keine Hilfe mehr anfordern."
                                + extra) != QMessageBox.Yes:
            return
        s.stop("Kurs beendet.")
        self.hub.changed.emit()
        self._refresh()

    def _selected(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _act(self, fn) -> None:
        s, sid = self.hub.running(), self._selected()
        if s is None or sid is None:
            return
        try:
            fn(s, sid)
        except HelpError as e:
            QMessageBox.information(self, APP_NAME, str(e))
        self._refresh()

    def _view(self) -> None:
        s, sid = self.hub.running(), self._selected()
        if s is None or sid is None:
            QMessageBox.information(self, APP_NAME, "Bitte zuerst einen Teilnehmer in der Liste auswählen.")
            return
        try:
            url = s.helpdesk.view_url(sid)
        except HelpError as e:
            QMessageBox.information(self, APP_NAME, str(e))
            return
        open_url(url)
        self.status.setText("Die Ansicht öffnet sich im Browser – sie zeigt den Agent-PC, sobald der Teilnehmer "
                            "zustimmt. Der Browser warnt einmal vor dem Zertifikat (gilt nur für diesen Kurs).")

    def _refresh(self) -> None:
        s = self.hub.running()
        live = s is not None
        self.settings_box.setVisible(not live)
        self.start_btn.setVisible(not live)
        self.stop_btn.setVisible(live)
        for w in (self.code, self.info, self.link, self.copy_btn, self.table, self.view_btn, self.control_btn,
                  self.end_btn, self.forget_btn):
            w.setVisible(live)
        if not live:
            self.status.setText("Der Hilfe-Schalter läuft nicht." if not self.status.text().startswith("Fehler")
                                else self.status.text())
            return
        self.code.setText(s.code)
        addrs = s.addresses()
        rows = [f"Adresse: <b>{a}:{s.port}</b>" + (f" ({share.address_kind(a)})" if share.address_kind(a) else "")
                for a in addrs]
        rows.append(f"Fingerabdruck: <b>{share.short_fingerprint(s.fingerprint)}</b>")
        rows.append("Teilnehmer: beim Agent-PC „Hilfe anfordern …“ – im selben Netz wird der Kurs gefunden, sonst den "
                    "Link unten einfügen bzw. Adresse und Code eingeben.")
        self.info.setText("<br>".join(rows))
        link = share.share_link(addrs[0] if addrs else "127.0.0.1", s.port, s.code, s.fingerprint)
        if self.link.text() != link:
            self.link.setText(link)
        sessions = s.helpdesk.session_list()
        keep = self._selected()
        self.table.setRowCount(len(sessions))
        for i, x in enumerate(sessions):
            for col, text in enumerate((x.name, x.vm, x.message, _age(x.requested_at), x.state)):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, x.id)
                if x.requested_at and x.state == helpdesk.WAITING:
                    item.setForeground(QColor(style.WARN))
                self.table.setItem(i, col, item)
            if x.id == keep:
                self.table.selectRow(i)
        left = s.remaining()
        waiting = sum(1 for x in sessions if x.state == helpdesk.WAITING)
        self.setWindowTitle(f"Hilfe-Anfragen ({waiting})" if waiting else "Hilfe-Anfragen")
        if not self.status.text().startswith("Die Ansicht"):
            self.status.setText(f"Hilfe-Schalter läuft – endet in {int(left // 60)} min · {len(sessions)} verbunden, "
                                f"{waiting} warten" + (" · Vorführung läuft" if s.has_screen else ""))

    def reject(self) -> None:
        self.timer.stop()
        self.hub.helpdesk_open = False
        s = self.hub.running()
        if s is not None and not s.has_screen and not any(x.connected for x in s.helpdesk.session_list()):
            s.stop("Hilfe-Schalter beendet.")
            self.hub.changed.emit()
        super().reject()
