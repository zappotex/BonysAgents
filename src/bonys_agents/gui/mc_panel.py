# SPDX-License-Identifier: GPL-3.0-or-later
"""Bereich „Mission Control“ der Detailansicht: Status, öffnen, aktualisieren, deinstallieren, Weiterleitung.

Mission Control läuft im Agent-PC (Docker, nur 127.0.0.1). Der Status kommt über den Gast-Agent, notfalls per
SSH – dabei werden nur Version, Dienst, Healthcheck und Port gelesen, nie Geheimnisse.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, mission_control, vm
from bonys_agents.i18n import tr

from . import style
from .widgets import FlowLayout, open_url
from .workers import TaskWorker

POLL_MS = 15_000  # Status bei sichtbarem Bereich alle 15 s
MC = mission_control


class McPanel(QWidget):
    install_requested = Signal()   # „Installieren“ – das Hauptfenster öffnet „Programme hinzufügen“
    changed = Signal()             # Programme in vm.json geändert (z. B. deinstalliert)
    log_line = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.machine: vm.VM | None = None
        self.state: dict | None = None
        self.error = ""
        self.workers: list[TaskWorker] = []
        self._loaded_for = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self.headline = QLabel()
        self.headline.setObjectName("Title")
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.note = QLabel()
        self.note.setObjectName("Muted")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        self.install_btn = QPushButton(tr("Mission Control installieren"))
        self.install_btn.setObjectName("Primary")
        self.install_btn.setToolTip(tr("Installiert Mission Control samt Docker im laufenden Agent-PC – wie "
                                       "„Programme hinzufügen“"))
        lay.addWidget(self.install_btn)

        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        buttons = FlowLayout()
        self.open_btn = QPushButton(tr("Öffnen"))
        self.open_btn.setObjectName("Primary")
        self.open_btn.setToolTip(tr("Öffnet die Oberfläche im Agent-PC (Brave)"))
        self.update_btn = QPushButton(tr("Aktualisieren"))
        self.update_btn.setToolTip(tr("Auf das neueste Release von Mission Control umstellen – Einstellungen, "
                                      "Geheimnisse und Daten bleiben"))
        self.uninstall_btn = QPushButton(tr("Deinstallieren …"))
        self.uninstall_btn.setObjectName("Danger")
        self.refresh_btn = QPushButton(tr("Status prüfen"))
        self.refresh_btn.setObjectName("Small")
        for b in (self.open_btn, self.update_btn, self.uninstall_btn, self.refresh_btn):
            buttons.addWidget(b)
        bl.addLayout(buttons)

        self.forward = QCheckBox(tr("Auch im Browser dieses Rechners öffnen (Weiterleitung, nur 127.0.0.1)"))
        self.forward.setToolTip(tr(MC.FORWARD_WARNING))
        bl.addWidget(self.forward)
        self.forward_note = QLabel()
        self.forward_note.setWordWrap(True)
        self.forward_note.setObjectName("Muted")
        bl.addWidget(self.forward_note)
        self.host_open_btn = QPushButton(tr("Hier im Browser öffnen"))
        self.host_open_btn.setObjectName("Small")
        frow = FlowLayout()
        frow.addWidget(self.host_open_btn)
        bl.addLayout(frow)
        lay.addWidget(self.body)

        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setMinimumHeight(style.px(120))
        self.output.setVisible(False)
        lay.addWidget(self.output, 1)
        lay.addStretch(0)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(lambda: self.reload(quiet=True))
        self.install_btn.clicked.connect(self.install_requested.emit)
        self.refresh_btn.clicked.connect(lambda: self.reload())
        self.open_btn.clicked.connect(self._open)
        self.update_btn.clicked.connect(self._update_app)
        self.uninstall_btn.clicked.connect(self._uninstall)
        self.forward.clicked.connect(self._toggle_forward)
        self.host_open_btn.clicked.connect(lambda: self.machine and open_url(MC.forward_url(self.machine)))
        self.log_line.connect(self._append)

    # ---------- Anzeige ----------
    def busy(self) -> bool:
        return any(w.isRunning() for w in self.workers)

    def usable(self) -> bool:
        m = self.machine
        return bool(m and m.status() == "läuft")

    def update_for(self, m: vm.VM, status: str) -> None:
        """Vom Hauptfenster bei jedem Auffrischen (nur wenn der Bereich sichtbar ist)."""
        if self.machine is None or self.machine.path != m.path:
            self.state, self.error, self._loaded_for = None, "", ""
            self.output.clear()
            self.output.setVisible(False)
            self.status.setText("")
        self.machine = m
        running = status == "läuft"
        if running and not self.timer.isActive():
            self.timer.start()
        elif not running:
            self.timer.stop()
            self.state, self._loaded_for = None, ""
        if running and MC.APP_ID in m.config.apps and self._loaded_for != m.name and not self.busy():
            self.reload()
        self._show()

    def hideEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self.timer.stop()
        super().hideEvent(event)

    def _show(self) -> None:
        m = self.machine
        if m is None:
            return
        c = m.config
        installed = MC.APP_ID in c.apps
        running = self.usable()
        busy = self.busy()
        self.install_btn.setVisible(not installed)
        self.install_btn.setEnabled(running and not busy)
        self.body.setVisible(installed)
        self.headline.setStyleSheet("")
        if not installed:
            self.headline.setText(tr("Mission Control ist nicht installiert"))
            self.note.setText(tr("Mission Control ist eine Übersicht und Steuerzentrale für deine Agenten im Browser "
                                 "(Open Source, {REPO_URL}). Sie läuft als Docker-Container nur im Agent-PC – "
                                 "{wert}. ", REPO_URL=MC.REPO_URL, wert=MC.requirement_note())
                              + ("" if running else tr("Zum Installieren muss der Agent-PC laufen.")))
        else:
            version = (c.app_info.get(MC.APP_ID) or {}).get("version", "")
            st = self.state
            if not running:
                self.headline.setText("Mission Control" + (f" {version}" if version else ""))
                self.note.setText(tr("Status, Öffnen und Aktualisieren gibt es, solange der Agent-PC läuft."))
            elif st is None:
                self.headline.setText("Mission Control")
                self.note.setText(self.error or tr("Frage den Status im Agent-PC ab …"))
            else:
                healthy = st.get("healthy")
                self.headline.setText(f"●  {MC.status_text(st)}")
                self.headline.setStyleSheet(f"color: {style.OK if healthy else style.WARN};")
                notes = [tr("Adresse im Agent-PC: http://127.0.0.1:{wert}/ (nur dort erreichbar)",
                            wert=st.get('port', MC.PORT))]
                if not st.get("installed"):
                    notes = [tr("Laut Einstellungen installiert, im Agent-PC aber nicht gefunden – über „Programme "
                                "hinzufügen“ bzw. Deinstallieren und neu installieren reparieren.")]
                elif not st.get("docker"):
                    notes.append(tr("⚠ Docker läuft im Agent-PC nicht."))
                if self.error:
                    notes.append(f"⚠ {self.error}")
                self.note.setText("\n".join(notes))
        self.note.setVisible(bool(self.note.text()))
        ok = running and not busy
        self.open_btn.setEnabled(ok and bool(self.state and self.state.get("installed")))
        self.update_btn.setEnabled(ok)
        self.uninstall_btn.setEnabled(ok)
        self.refresh_btn.setEnabled(ok)
        self.forward.setEnabled(not busy)
        self.forward.setChecked(c.mc_forward)
        fwd = c.mc_forward and bool(c.mc_forward_port)
        self.forward_note.setText(
            (tr("An: {wert} – nur auf diesem Rechner erreichbar.",
                wert=MC.forward_url(m)) if fwd else tr("Aus (Standard). Mission Control ist nur im Agent-PC "
                                                       "erreichbar."))
            + ("" if not fwd or m.is_running() else tr(" Wirkt beim nächsten Start.")))
        self.host_open_btn.setVisible(fwd)
        self.host_open_btn.setEnabled(fwd and m.is_running())

    def _append(self, line: str) -> None:
        self.output.setVisible(True)
        self.output.appendPlainText(line)

    # ---------- Aktionen ----------
    def _start(self, fn, done=None, message: str = "") -> None:
        """``fn(password)`` im Hintergrund. Antwortet der Gast-Agent nicht, wird nach dem Passwort gefragt."""
        m = self.machine
        if m is None:
            return
        w = TaskWorker(lambda: fn(None))
        if message:
            self.status.setText(message)
            self.status.setStyleSheet("")

        def finished() -> None:
            self.workers = [x for x in self.workers if x.isRunning()]
            if w.error is None:
                if message:
                    self.status.setText("")
                if done:
                    done(w.result)
            elif isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, tr("{error}\n\nPasswort "
                                                                 "von „{name}“:", error=w.error, name=m.name),
                                              QLineEdit.Password)
                if ok and pw:
                    self._start(lambda _pw: fn(pw), done, message)
                    return
                self.status.setText("")
            else:
                self.status.setText(tr("Fehler: {error}", error=w.error))
                self.status.setStyleSheet(f"color: {style.DANGER};")
            self._show()

        w.finished.connect(finished)
        self.workers.append(w)
        w.start()
        self._show()

    def reload(self, quiet: bool = False) -> None:
        m = self.machine
        if m is None or not self.usable() or self.busy() or MC.APP_ID not in m.config.apps:
            return

        def fetch(pw):
            try:
                return MC.status(m, password=pw)
            except vm.NeedsPassword:
                if quiet:
                    return {"_error": tr("Der Gast-Agent antwortet nicht – „Status prüfen“ fragt nach dem Passwort.")}
                raise

        def done(result) -> None:
            self._loaded_for = m.name
            if "_error" in result:
                self.error = result["_error"]
                return
            self.state, self.error = result, ""

        self._start(fetch, done, "" if quiet else tr("Frage den Status ab …"))

    def _done_message(self, text: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {style.OK};")

    def _open(self) -> None:
        m = self.machine
        if m is None:
            return
        self._start(lambda pw: MC.open_in_guest(m, password=pw), self._done_message, tr("Öffne Mission Control …"))

    def _update_app(self) -> None:
        m = self.machine
        if m is None:
            return
        if QMessageBox.question(
                self, APP_NAME, tr("Mission Control in "
                                   "„{name}“ auf das neueste "
                                   "Release "
                                   "umstellen?\n\nQuelle: "
                                   "{REPO_URL} (Prüfsumme "
                                   "wird geprüft). "
                                   "Einstellungen, "
                                   "Geheimnisse und Daten "
                                   "bleiben. Dauert je nach "
                                   "Download ein paar "
                                   "Minuten.", name=m.name, REPO_URL=MC.REPO_URL)) != QMessageBox.Yes:
            return
        self.output.clear()

        def run(pw):
            msg = MC.update(m, version="latest", password=pw, log=self.log_line.emit)
            self.state = MC.status(m, password=pw)
            return msg

        self._start(run, self._done_message, tr("Aktualisiere Mission Control im Agent-PC …"))

    def _uninstall(self) -> None:
        m = self.machine
        if m is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Question)
        box.setText(tr("Mission Control aus „{name}“ entfernen?", name=m.name))
        box.setInformativeText(tr("Einstellungen und Daten bleiben im Agent-PC, eine spätere Neuinstallation übernimmt "
                                  "sie. Docker bleibt installiert."))
        purge_cb = QCheckBox(tr("Auch alle Daten und Einstellungen löschen (nicht umkehrbar)"))
        box.setCheckBox(purge_cb)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText(tr("Deinstallieren"))
        if box.exec() != QMessageBox.Yes:
            return
        purge = purge_cb.isChecked()
        if purge and QMessageBox.warning(
                self, APP_NAME, tr("Wirklich ALLE Daten, Einstellungen und Geheimnisse von Mission "
                                   "Control in „{name}“ löschen?\n\nDas lässt sich nicht rückgängig "
                                   "machen.", name=m.name),
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self.output.clear()

        def done(msg: str) -> None:
            self.state = None
            self._done_message(msg)
            self.changed.emit()

        self._start(lambda pw: MC.uninstall(m, purge=purge, password=pw, log=self.log_line.emit), done,
                    "Entferne Mission Control …")

    def _toggle_forward(self, on: bool) -> None:
        m = self.machine
        if m is None:
            return
        if on and QMessageBox.warning(self, APP_NAME, tr(MC.FORWARD_WARNING) + "\n\n" + tr("Weiterleitung "
                                                                                           "einschalten?"),
                                      QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            self._show()
            return
        self._start(lambda pw: MC.set_forward(m, on, password=pw), self._done_message,
                    tr("Richte die Weiterleitung ein …") if on else tr("Schalte die Weiterleitung aus …"))
