# SPDX-License-Identifier: GPL-3.0-or-later
"""Updates in der Desktop-App: dezente Leiste, „Was ist neu?“, Installation und Agent-PCs aktualisieren."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, __version__, host, procutil, updates, vm

from . import style
from .widgets import FlowLayout, PercentBar, fit_to_screen, make_scrollable, open_url


class CheckWorker(QThread):
    """Versionsabfrage im Hintergrund – blockiert nie das Fenster."""

    found = Signal(object)  # UpdateInfo oder None

    def __init__(self, manual: bool):
        super().__init__()
        self.manual = manual

    def run(self) -> None:
        try:
            info = updates.check_now(manual=self.manual)
        except Exception:  # noqa: BLE001 – nie abstürzen: „keine Updates“
            info = None
        self.found.emit(info)


class UpdateBanner(QFrame):
    """Leiste oben im Hauptfenster: „Version X.Y.Z ist verfügbar“ – kein Pop-up, das die Arbeit unterbricht."""

    update_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Hint")
        self.info: updates.UpdateInfo | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(10)
        self.text = QLabel()
        self.notes_btn = QPushButton("Was ist neu?")
        self.install_btn = QPushButton("Jetzt aktualisieren")
        self.install_btn.setObjectName("Primary")
        self.later_btn = QPushButton("Später")
        self.skip_btn = QPushButton("Diese Version überspringen")
        for b in (self.notes_btn, self.later_btn, self.skip_btn):
            b.setObjectName("Small")
        self.text.setWordWrap(True)
        buttons = FlowLayout(align_right=True)
        row.addWidget(self.text, 1)
        row.addLayout(buttons, 1)
        for b in (self.notes_btn, self.install_btn, self.later_btn, self.skip_btn):
            buttons.addWidget(b)
        self.notes_btn.clicked.connect(self._notes)
        self.install_btn.clicked.connect(lambda: self.info and self.update_requested.emit(self.info))
        self.later_btn.clicked.connect(self.hide)
        self.skip_btn.clicked.connect(self._skip)
        self.hide()

    def show_update(self, info: updates.UpdateInfo) -> None:
        self.info = info
        kind = " (Testversion)" if info.prerelease else ""
        self.text.setText(f"<b>Version {info.version}{kind} ist verfügbar</b> – du hast {__version__}.")
        self.show()

    def _notes(self) -> None:
        if self.info:
            ReleaseNotesDialog(self.info, self.window()).exec()

    def _skip(self) -> None:
        if self.info:
            updates.set_setting("skip", self.info.version)
        self.hide()


class ReleaseNotesDialog(QDialog):
    def __init__(self, info: updates.UpdateInfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Was ist neu in {info.version}?")
        fit_to_screen(self, 640, 480)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenLinks(False)
        view.anchorClicked.connect(lambda url: open_url(url.toString()))
        view.setMarkdown(f"# {info.title}\n\n{info.notes or 'Keine Beschreibung.'}")
        lay.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        if info.html_url:
            web = buttons.addButton("Release-Seite öffnen", QDialogButtonBox.ActionRole)
            web.clicked.connect(lambda: open_url(info.html_url))
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class InstallWorker(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, info: updates.UpdateInfo, stop_vms: list[vm.VM]):
        super().__init__()
        self.info = info
        self.stop_vms = stop_vms

    def run(self) -> None:
        h = host.detect()
        try:
            for m in self.stop_vms:
                self.log.emit(f"Fahre „{m.name}“ herunter …")
                if m.stop():
                    self.log.emit(f"„{m.name}“ hat nicht reagiert und wurde hart ausgeschaltet.")
            if h.os == "linux":
                updates.install_linux(self.info, h.arch, gui=True, log=self.log.emit)
            elif h.os == "windows":
                updates.install_windows(self.info, log=self.log.emit)
            elif h.os == "macos":
                updates.install_macos(self.info, h.arch, log=self.log.emit)
                self.done.emit(True, f"{APP_NAME} {self.info.version} ist geladen und geprüft. Im Finder-Fenster "
                               f"„{APP_NAME}“ auf „Programme“ ziehen und „Ersetzen“ wählen. Dafür beendet sich "
                               "die App jetzt.")
                return
            else:
                raise updates.UpdateError("Automatische Updates gibt es für dieses System nicht.")
        except Exception as e:  # noqa: BLE001 – Meldung an die Oberfläche
            self.done.emit(False, str(e))
            return
        self.done.emit(True, f"{APP_NAME} {self.info.version} ist installiert. Die App startet jetzt neu.")


class InstallDialog(QDialog):
    """Fortschritt der Installation; danach startet die App neu."""

    def __init__(self, info: updates.UpdateInfo, stop_vms: list[vm.VM], parent=None):
        super().__init__(parent)
        self.info = info
        self.ok = False
        self.setWindowTitle(f"Aktualisieren auf {info.version}")
        lay = QVBoxLayout(self)
        self.status = QLabel(f"{APP_NAME} wird auf Version {info.version} aktualisiert …")
        self.status.setWordWrap(True)
        self.bar = PercentBar()
        self.bar.set_percent(None)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(style.px(140))
        self.close_btn = QPushButton("Schließen")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.close_btn)
        for w in (self.status, self.bar, self.log):
            lay.addWidget(w)
        lay.addLayout(row)
        make_scrollable(self, 620)
        self.worker = InstallWorker(info, stop_vms)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _done(self, ok: bool, msg: str) -> None:
        self.ok = ok
        self.bar.setVisible(False)
        self.close_btn.setEnabled(True)
        self.status.setText(msg)
        self.status.setStyleSheet(f"color: {style.OK if ok else style.DANGER};")
        if ok:
            self.close_btn.setText("Beenden" if host.detect_os() == "macos" else "Neu starten")

    def reject(self) -> None:
        if self.worker.isRunning():
            return
        super().reject()


def start_update(parent: QWidget, info: updates.UpdateInfo) -> None:
    """„Jetzt aktualisieren“: zustimmen lassen, laufende Agent-PCs klären, installieren, neu starten."""
    from PySide6.QtWidgets import QApplication

    h = host.detect()
    if not updates.can_self_update(h.os):
        QMessageBox.information(
            parent, APP_NAME,
            f"Version {info.version} gibt es auf der Release-Seite zum Herunterladen.\n\n"
            "Diese Installation (aus dem Quellcode) aktualisiert sich nicht selbst.")
        open_url(info.html_url or updates.release_page())
        return
    if h.os == "macos":
        question = (f"Version {info.version} jetzt laden?\n\n"
                    f"Bony's Agents lädt die Datei für deinen Mac ({updates.asset_for(info.version, 'macos', h.arch)}) "
                    "in den Ordner „Downloads“, prüft Signatur und Prüfsumme und öffnet sie im Finder. "
                    "Dort die App auf „Programme“ ziehen und „Ersetzen“ wählen.")
    else:
        how = ("über die Paketverwaltung (fragt nach deinem Passwort)" if h.os == "linux"
               else "mit dem Windows-Installer (Windows fragt nach Zustimmung)")
        question = (f"{APP_NAME} jetzt auf Version {info.version} aktualisieren?\n\n"
                    f"Die Installation läuft {how}. Signatur und Prüfsumme werden vorher geprüft. "
                    "Danach startet die App neu.")
    answer = QMessageBox.question(parent, APP_NAME, question)
    if answer != QMessageBox.Yes:
        return
    running = [m for m in vm.list_vms() if m.is_running()]
    stop_vms: list[vm.VM] = []
    if running:
        box = QMessageBox(parent)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Question)
        box.setText(f"Gerade laufen: {', '.join(m.name for m in running)}.\n\n"
                    "Agent-PCs laufen beim Update unabhängig weiter – nur die App startet neu. "
                    "Sollen sie vorher heruntergefahren werden?")
        stop = box.addButton("Herunterfahren", QMessageBox.YesRole)
        keep = box.addButton("Weiterlaufen lassen", QMessageBox.NoRole)
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() not in (stop, keep):
            return
        if box.clickedButton() is stop:
            stop_vms = running
    dlg = InstallDialog(info, stop_vms, parent)
    dlg.exec()
    if dlg.ok:
        if h.os == "linux":  # unter Windows startet der Installer die App neu
            procutil.spawn_detached(updates.restart_command())
        QApplication.quit()


# ---------------------------------------------------------------- Agent-PCs aktualisieren
class UpgradeWorker(QThread):
    log = Signal(str)
    machine_started = Signal(str)
    need_password = Signal(str, str)   # (Name, Meldung)
    done = Signal(list)                # [(Name, ok, Meldung, Neustart nötig)]

    def __init__(self, machines: list[vm.VM]):
        super().__init__()
        self.machines = machines
        self._answer = threading.Event()
        self._password: str | None = None

    def provide_password(self, password: str | None) -> None:
        self._password = password
        self._answer.set()

    def run(self) -> None:
        results = []
        for m in self.machines:
            self.machine_started.emit(m.name)
            password = None
            while True:
                try:
                    r = m.upgrade(password=password, log=self.log.emit)
                    results.append((m.name, r.ok, r.message(m.name), r.reboot_required))
                except vm.NeedsPassword as e:
                    self._answer.clear()
                    self.need_password.emit(m.name, str(e))
                    self._answer.wait()
                    password, self._password = self._password, None
                    if password:
                        continue
                    results.append((m.name, False, f"„{m.name}“ übersprungen (kein Passwort).", False))
                except Exception as e:  # noqa: BLE001
                    results.append((m.name, False, f"„{m.name}“: {e}", False))
                break
        self.done.emit(results)


class UpgradeDialog(QDialog):
    """„Agent-PC aktualisieren“ bzw. „Alle Agent-PCs aktualisieren“ mit Live-Ausgabe."""

    def __init__(self, machines: list[vm.VM], parent=None):
        super().__init__(parent)
        self.machines = machines
        self.results: list = []
        title = "Agent-PC aktualisieren" if len(machines) == 1 else "Alle Agent-PCs aktualisieren"
        self.setWindowTitle(title)
        fit_to_screen(self, 760, 520)
        lay = QVBoxLayout(self)
        intro = QLabel("Aktualisiert Systempakete (apt), Flatpak-Programme und installierte KI-Werkzeuge mit "
                       "ihren offiziellen Update-Befehlen. Die Agent-PCs laufen dabei weiter.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.bar = PercentBar()
        self.bar.set_percent(None)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.reboot_btn = QPushButton("Jetzt neu starten")
        self.reboot_btn.setVisible(False)
        self.close_btn = QPushButton("Schließen")
        self.close_btn.setEnabled(False)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.reboot_btn)
        row.addWidget(self.close_btn)
        for w in (intro, self.status, self.bar):
            lay.addWidget(w)
        lay.addWidget(self.log, 1)
        lay.addLayout(row)
        self.close_btn.clicked.connect(self.accept)
        self.reboot_btn.clicked.connect(self._reboot)
        self.worker = UpgradeWorker(machines)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.machine_started.connect(lambda n: self.status.setText(f"Aktualisiere „{n}“ … "
                                                                          "(kann einige Minuten dauern)"))
        self.worker.need_password.connect(self._ask_password)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _ask_password(self, name: str, msg: str) -> None:
        pw, ok = QInputDialog.getText(self, APP_NAME, f"{msg}\n\nPasswort von „{name}“:", QLineEdit.Password)
        self.worker.provide_password(pw if ok and pw else None)

    def _done(self, results: list) -> None:
        self.results = results
        self.bar.setVisible(False)
        self.close_btn.setEnabled(True)
        ok = all(r[1] for r in results)
        self.status.setText("\n".join(r[2] for r in results) or "Nichts zu tun.")
        self.status.setStyleSheet(f"color: {style.OK if ok else style.WARN};")
        self.reboot_btn.setVisible(any(r[3] for r in results))

    def _reboot(self) -> None:
        names = [r[0] for r in self.results if r[3]]
        for m in self.machines:
            if m.name in names:
                try:
                    m.guest_run("systemctl --no-block reboot", timeout=30)
                except Exception as e:  # noqa: BLE001
                    QMessageBox.warning(self, APP_NAME, f"„{m.name}“ konnte nicht neu gestartet werden: {e}\n"
                                        "Bitte im Agent-PC selbst neu starten.")
        self.reboot_btn.setEnabled(False)

    def reject(self) -> None:
        if self.worker.isRunning():
            return
        super().reject()
