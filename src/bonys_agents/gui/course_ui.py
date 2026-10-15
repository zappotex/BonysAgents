# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen, Hilfe-Modus in der Oberfläche.

Teilnehmer (beide Editionen): ``HelpManager`` hält die Verbindungen zum Kurs, ``HelpRequestDialog`` fordert Hilfe
an, ``HelpBanner`` zeigt gut sichtbar, wenn jemand zusieht oder steuert, ``ask_consent`` fragt nach Zustimmung.
Die Kursleiter-Seite (``CourseHub``, ``HelpDeskDialog``) steht in ``bonys_agents.trainer.gui.helpdesk_dialog``.
"""

from __future__ import annotations

import json
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from bonys_agents import APP_NAME, helpmode, share, storage, vm

from . import style
from .template_dialogs import FnWorker
from .widgets import make_scrollable


# ================================================================ Teilnehmer
def _course_file():
    return storage.data_dir() / "schulung" / "kurs.json"


def last_course() -> dict:
    try:
        data = json.loads(_course_file().read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_course(target: share.Target, name: str) -> None:
    f = _course_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"link": share.share_link(target.host, target.port, target.code, target.fingerprint),
                                 "name": name}), "utf-8")
    except OSError:
        pass


def probe_fingerprint(target: share.Target) -> str:
    """Nur TLS aufbauen und den Fingerabdruck holen (zum Vergleichen, wenn keiner mitkam)."""
    import hashlib
    import socket

    with socket.create_connection((target.host, target.port), timeout=10) as raw, \
            share.client_context().wrap_socket(raw) as tls:
        return hashlib.sha256(tls.getpeercert(binary_form=True) or b"").hexdigest()


class HelpManager(QObject):
    """Teilnehmer: offene Hilfe-Verbindungen (je Agent-PC eine). Rückrufe kommen als Qt-Signale an."""

    view_requested = Signal(str)
    control_requested = Signal(str)
    changed = Signal(str)
    closed = Signal(str, str)
    _instance: HelpManager | None = None

    @classmethod
    def get(cls) -> HelpManager:
        if cls._instance is None:
            cls._instance = HelpManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.clients: dict[str, helpmode.HelpClient] = {}
        self.machines: dict[str, vm.VM] = {}
        self._shown: dict[str, str] = {}
        self.changed.connect(self._notify_guest)
        self.closed.connect(self._forget)

    def client(self, name: str) -> helpmode.HelpClient | None:
        c = self.clients.get(name)
        return c if c is not None and not c.closed.is_set() else None

    def create(self, machine: vm.VM, target: share.Target, name: str) -> helpmode.HelpClient:
        """Verbindung vorbereiten (``connect()`` im Hintergrund aufrufen)."""
        n = machine.name
        old = self.clients.get(n)
        if old is not None:
            old.close("Neue Verbindung.")
        c = helpmode.HelpClient(target, machine, name,
                                on_view_request=lambda: self.view_requested.emit(n),
                                on_control_request=lambda: self.control_requested.emit(n),
                                on_change=lambda: self.changed.emit(n),
                                on_closed=lambda reason: self.closed.emit(n, reason))
        self.clients[n] = c
        self.machines[n] = machine
        return c

    def _forget(self, name: str, _reason: str) -> None:
        self.changed.emit(name)

    def active(self) -> list[tuple[str, helpmode.HelpClient]]:
        return [(n, c) for n, c in self.clients.items() if not c.closed.is_set()]

    def _notify_guest(self, name: str) -> None:
        """Hinweis auch im Agent-PC selbst (Desktop-Benachrichtigung), wenn möglich."""
        c, m = self.clients.get(name), self.machines.get(name)
        if c is None or m is None:
            return
        state = c.state
        if state == self._shown.get(name):
            return
        self._shown[name] = state
        texts = {"sieht zu": "Der Kursleiter sieht diesen Agent-PC jetzt (nur ansehen).",
                 "steuert": "Der Kursleiter steuert diesen Agent-PC jetzt (Tastatur und Maus)."}
        if state in texts:
            text = texts[state]
        elif state in ("verbunden", "getrennt", "wartet") and name in self._shown:
            text = "Der Kursleiter sieht nicht mehr zu."
        else:
            return
        threading.Thread(target=m.guest_notify, args=("Bony's Agents – Hilfe", text), daemon=True).start()


class HelpRequestDialog(QDialog):
    """Teilnehmer: Hilfe beim Kursleiter anfordern – Kurs finden bzw. eingeben, Nachricht, Fingerabdruck prüfen."""

    def __init__(self, machine: vm.VM, parent=None, restart=None):
        super().__init__(parent)
        self.m = machine
        self.restart = restart
        self.manager = HelpManager.get()
        self.worker: FnWorker | None = None
        self.known_fp = ""
        self.setWindowTitle("Hilfe anfordern")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(f"Hilfe anfordern – „{machine.name}“")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Der Kursleiter bekommt deine Anfrage. Ansehen kann er deinen Agent-PC erst, wenn du zustimmst "
                       "– und steuern nur nach einer zweiten Zustimmung. Er sieht nur diesen Agent-PC, nie deinen "
                       "übrigen Bildschirm; die Zwischenablage wird nie übertragen. Du kannst jederzeit beenden.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        self.restart_box = QFrame()
        self.restart_box.setObjectName("Hint")
        rb = QHBoxLayout(self.restart_box)
        rt = QLabel("Dieser Agent-PC wurde mit einer älteren Version gestartet – für den Hilfe-Modus einmal neu "
                    "starten.")
        rt.setWordWrap(True)
        self.restart_btn = QPushButton("Jetzt neu starten")
        rb.addWidget(rt, 1)
        rb.addWidget(self.restart_btn)
        self.restart_box.setVisible(machine.is_running() and not machine.vnc_available())
        root.addWidget(self.restart_box)
        found_row = QHBoxLayout()
        sec = QLabel("KURS IM NETZ")
        sec.setObjectName("Section")
        found_row.addWidget(sec)
        found_row.addStretch(1)
        self.search_btn = QPushButton("Erneut suchen")
        self.search_btn.setObjectName("Small")
        found_row.addWidget(self.search_btn)
        root.addLayout(found_row)
        self.found = QListWidget()
        self.found.setMaximumHeight(style.px(80))
        root.addWidget(self.found)
        form = QFormLayout()
        last = last_course()
        self.address = QLineEdit(last.get("link", ""))
        self.address.setPlaceholderText("z. B. 192.168.1.5:47120 oder bonys://… (Link vom Kursleiter)")
        self.code = QLineEdit()
        self.code.setPlaceholderText("z. B. 4711-BONY (steht im Link schon drin)")
        self.name = QLineEdit(last.get("name") or share._client_name())
        self.name.setMaxLength(40)
        self.message = QLineEdit()
        self.message.setMaxLength(300)
        self.message.setPlaceholderText("Optional, z. B. „Hermes antwortet nicht“")
        form.addRow("Kurs", self.address)
        form.addRow("Code", self.code)
        form.addRow("Dein Name", self.name)
        form.addRow("Nachricht", self.message)
        root.addLayout(form)
        self.fp_label = QLabel()
        self.fp_label.setWordWrap(True)
        self.fp_label.setVisible(False)
        self.fp_ok = QCheckBox("Der Fingerabdruck stimmt mit dem auf dem Bildschirm des Kursleiters überein")
        self.fp_ok.setVisible(False)
        root.addWidget(self.fp_label)
        root.addWidget(self.fp_ok)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Hilfe anfordern")
        self.ok_btn.setObjectName("Primary")
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        root.addLayout(buttons)
        make_scrollable(self, 620)

        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._go)
        self.search_btn.clicked.connect(self._search)
        self.found.currentItemChanged.connect(self._pick)
        self.address.textChanged.connect(self._reset_fp)
        self.restart_btn.clicked.connect(self._restart)
        self.ok_btn.setEnabled(machine.vnc_available())
        QTimer.singleShot(0, self._search)

    def _restart(self) -> None:
        if QMessageBox.question(self, APP_NAME, f"„{self.m.name}“ jetzt neu starten? Nicht gespeicherte Arbeit im "
                                "Agent-PC geht verloren.") == QMessageBox.Yes and self.restart:
            self.restart()
            self.reject()

    def _busy(self, busy: bool) -> None:
        for w in (self.search_btn, self.address, self.code, self.ok_btn, self.found, self.name, self.message):
            w.setEnabled(not busy)

    def _search(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.found.clear()
        self.worker = FnWorker(lambda progress: [f for f in share.discover() if f.txt.get("kind") == "present"])
        self.worker.done.connect(self._found)
        self.worker.failed.connect(lambda msg: self._error(msg))
        self._busy(True)
        self.worker.start()

    def _found(self, items) -> None:
        self.worker = None
        self._busy(False)
        self.ok_btn.setEnabled(self.m.vnc_available())
        for f in items:
            it = QListWidgetItem(f"{f.txt.get('name', 'Kurs')} – {f.txt.get('creator') or '?'} · {f.address}")
            it.setData(Qt.UserRole, f.address)
            self.found.addItem(it)
        if len(items) == 1 and not self.address.text().strip():
            self.found.setCurrentRow(0)
        self.status.setText("" if items or self.address.text() else
                            "Kein Kurs gefunden – im VPN den Link bzw. Adresse und Code des Kursleiters eingeben.")

    def _pick(self, item) -> None:
        if item is None:
            return
        # Nur die Adresse: Fingerabdruck aus mDNS ist fälschbar – Vergleich mit dem Kursleiter bleibt Pflicht
        self.address.setText(item.data(Qt.UserRole))
        self.code.setFocus()

    def _reset_fp(self, *_) -> None:
        self.known_fp = ""
        self.fp_label.setVisible(False)
        self.fp_ok.setVisible(False)

    def _error(self, msg: str) -> None:
        self.worker = None
        self._busy(False)
        self.ok_btn.setEnabled(self.m.vnc_available())
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _go(self) -> None:
        try:
            target = share.parse_target(self.address.text(), self.code.text())
        except ValueError as e:
            self._error(str(e))
            return
        if not target.code:
            self._error("Bitte den Code des Kurses eingeben.")
            return
        self.status.setStyleSheet("")
        if not target.fingerprint:
            if not self.known_fp:      # erst Fingerabdruck holen und vergleichen lassen
                self.status.setText(f"Verbinde mit {target.netloc} …")
                self.worker = FnWorker(lambda progress: probe_fingerprint(target))
                self.worker.done.connect(self._probed)
                self.worker.failed.connect(lambda msg: self._error(f"Keine Verbindung zu {target.netloc}: {msg}"))
                self._busy(True)
                self.worker.start()
                return
            if not self.fp_ok.isChecked():
                self.status.setText("Bitte zuerst den Fingerabdruck mit dem Bildschirm des Kursleiters vergleichen.")
                return
            target.fingerprint = self.known_fp
        name, message = self.name.text().strip(), self.message.text().strip()
        client = self.manager.create(self.m, target, name)
        self.status.setText(f"Verbinde mit {target.netloc} …")

        def run(progress):
            client.connect()
            client.request(message)
            return client
        self.worker = FnWorker(run)
        self.worker.done.connect(lambda c: self._done(target, name))
        self.worker.failed.connect(self._error)
        self._busy(True)
        self.worker.start()

    def _probed(self, fp: str) -> None:
        self.worker = None
        self._busy(False)
        self.known_fp = fp
        self.fp_label.setText(f"Fingerabdruck des Kurses: <b>{share.short_fingerprint(fp)}</b> – vergleiche ihn mit "
                              "dem auf dem Bildschirm des Kursleiters.")
        self.fp_label.setVisible(True)
        self.fp_ok.setVisible(True)
        self.fp_ok.setChecked(False)
        self.status.setText("")

    def _done(self, target: share.Target, name: str) -> None:
        self.worker = None
        remember_course(target, name)
        self.accept()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()


class HelpBanner(QFrame):
    """Gut sichtbarer Hinweis im Hauptfenster: Hilfe angefordert / Kursleiter sieht zu / Kursleiter steuert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = HelpManager.get()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text, 1)
        self.view_only_btn = QPushButton("Nur ansehen")
        self.view_only_btn.setToolTip("Kursleiter darf nicht mehr steuern – nur noch zusehen")
        self.end_btn = QPushButton("Beenden")
        self.end_btn.setObjectName("Danger")
        self.cancel_btn = QPushButton("Anfrage zurückziehen")
        self.disconnect_btn = QPushButton("Trennen")
        self.disconnect_btn.setToolTip("Verbindung zum Kurs trennen")
        for b in (self.view_only_btn, self.end_btn, self.cancel_btn, self.disconnect_btn):
            b.setObjectName(b.objectName() or "Small")
            lay.addWidget(b)
        self.view_only_btn.clicked.connect(lambda: self._client() and self._client().view_only())
        self.end_btn.clicked.connect(lambda: self._client() and self._client().end())
        self.cancel_btn.clicked.connect(lambda: self._client() and self._client().cancel())
        self.disconnect_btn.clicked.connect(lambda: self._client() and self._client().close("Vom Teilnehmer getrennt."))
        self.manager.changed.connect(lambda _n: self.refresh())
        self.manager.closed.connect(lambda _n, _r: self.refresh())
        self.refresh()

    def _client(self) -> helpmode.HelpClient | None:
        active = self.manager.active()
        if not active:
            return None
        # wichtigster Zustand zuerst: steuert > sieht zu > erlaubt > wartet > verbunden
        order = {"steuert": 0, "sieht zu": 1, "erlaubt": 2, "wartet": 3, "verbunden": 4}
        return min((c for _n, c in active), key=lambda c: order.get(c.state, 9))

    def refresh(self) -> None:
        c = self._client()
        if c is None:
            self.setVisible(False)
            return
        state, vm_name = c.state, c.machine.name
        colors = {"steuert": style.DANGER, "sieht zu": style.WARN, "erlaubt": style.WARN}
        bg = colors.get(state)
        self.setStyleSheet(f"HelpBanner {{ background: {bg}; border-radius: 8px; }} QLabel {{ color: #111; "
                           "font-weight: bold; }" if bg else
                           f"HelpBanner {{ border: 1px solid {style.BORDER}; border-radius: 8px; }}")
        texts = {
            "steuert": f"Der Kursleiter STEUERT gerade deinen Agent-PC „{vm_name}“ (Tastatur und Maus).",
            "sieht zu": f"Der Kursleiter sieht gerade deinen Agent-PC „{vm_name}“ (nur ansehen).",
            "erlaubt": f"Du hast dem Kursleiter das Ansehen von „{vm_name}“ erlaubt.",
            "wartet": f"Hilfe für „{vm_name}“ angefordert – der Kursleiter meldet sich.",
            "verbunden": f"Mit dem Kurs verbunden ({c.course}).",
        }
        self.text.setText(texts.get(state, state))
        self.view_only_btn.setVisible(c.control_allowed)
        self.end_btn.setVisible(c.view_allowed)
        self.cancel_btn.setVisible(state == "wartet")
        self.disconnect_btn.setVisible(state in ("wartet", "verbunden"))
        self.setVisible(True)


def ask_consent(parent, name: str, what: str) -> None:
    """Rückfrage beim Teilnehmer – „view“ (Ansehen) oder „control“ (Steuerung, zweite Zustimmung)."""
    c = HelpManager.get().client(name)
    if c is None:
        return
    QApplication.alert(parent, 0)
    parent.raise_()
    parent.activateWindow()
    if what == "view":
        text = (f"Der Kursleiter ({c.course}) möchte deinen Agent-PC „{name}“ ansehen.\n\nEr sieht nur diesen "
                "Agent-PC – nicht deinen übrigen Bildschirm – und kann nichts eingeben. Du kannst jederzeit beenden.")
    else:
        text = (f"Der Kursleiter möchte deinen Agent-PC „{name}“ steuern (Tastatur und Maus).\n\nDie Zwischenablage "
                "wird nie übertragen. Du kannst jederzeit auf „Nur ansehen“ zurückstellen oder beenden.")
    box = QMessageBox(QMessageBox.Question, "Kursleiter möchte steuern" if what == "control" else
                      "Kursleiter möchte ansehen", text, parent=parent)
    allow = box.addButton("Erlauben", QMessageBox.AcceptRole)
    box.addButton("Ablehnen", QMessageBox.RejectRole)
    box.exec()
    granted = box.clickedButton() is allow
    if c.closed.is_set():
        return
    if what == "view":
        c.allow_view(granted)
    else:
        c.allow_control(granted)
