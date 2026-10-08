# SPDX-License-Identifier: GPL-3.0-or-later
"""Einrichtungs-Assistent: prüft den Rechner und installiert QEMU & Co. per Knopfdruck."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from bonys_agents import deps, host, remote, selftest

from . import style
from .remote_panel import install_remmina
from .widgets import make_scrollable


class InstallWorker(QThread):
    log = Signal(str)
    done = Signal(object)

    def __init__(self, info: host.HostInfo, report: deps.Report):
        super().__init__()
        self.info = info
        self.report = report

    def run(self) -> None:
        try:
            result = deps.install(self.info, self.report, log=self.log.emit, gui=True)
        except Exception as e:  # noqa: BLE001
            result = deps.InstallResult(False, message=str(e))
        self.done.emit(result)


class SelftestWorker(QThread):
    result = Signal(object)

    def run(self) -> None:
        try:
            # Qt ist in der laufenden App ohnehin geladen
            checks = selftest.run(include_qt=False)
        except Exception as e:  # noqa: BLE001
            checks = [selftest.Check("Selbsttest", False, str(e))]
        self.result.emit(checks)


class SetupDialog(QDialog):
    def __init__(self, info: host.HostInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.worker: InstallWorker | None = None
        self.setWindowTitle("Einrichtung")

        root = QVBoxLayout(self)
        root.setSpacing(12)
        title = QLabel("Rechner vorbereiten")
        title.setObjectName("Title")
        root.addWidget(title)

        sysinfo = QLabel(
            f"{info.os} / {info.arch}  ·  {info.cpus} Kerne  ·  {info.ram_mb // 1024} GB RAM  ·  "
            f"Beschleuniger: {info.accel}"
        )
        sysinfo.setObjectName("Muted")
        root.addWidget(sysinfo)

        self.issues_label = QLabel()
        self.issues_label.setWordWrap(True)
        root.addWidget(self.issues_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)
        self.log.setVisible(False)
        root.addWidget(self.log)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)

        # Empfehlung für den Fernzugriff (Linux): Remmina mit RDP- und SPICE-Erweiterung
        self.remmina_row = QHBoxLayout()
        self.remmina_label = QLabel("Empfohlen für den Fernzugriff auf Agent-PCs (RDP und SPICE): Remmina")
        self.remmina_label.setObjectName("Muted")
        self.remmina_label.setWordWrap(True)
        self.remmina_btn = QPushButton("Remmina installieren")
        self.remmina_btn.setObjectName("Small")
        self.remmina_row.addWidget(self.remmina_label, 1)
        self.remmina_row.addWidget(self.remmina_btn)
        root.addLayout(self.remmina_row)
        self.remmina_btn.clicked.connect(self._install_remmina)
        self._remmina_worker = None
        self._update_remmina()

        # Selbsttest: startet QEMU genauso wie beim Agent-PC (findet z. B. Bibliotheks-Konflikte)
        test_row = QHBoxLayout()
        self.test_label = QLabel("Selbsttest: prüft, ob QEMU auf diesem Rechner startet.")
        self.test_label.setObjectName("Muted")
        self.test_label.setWordWrap(True)
        self.test_btn = QPushButton("Selbsttest ausführen")
        self.test_btn.setObjectName("Small")
        test_row.addWidget(self.test_label, 1)
        test_row.addWidget(self.test_btn)
        root.addLayout(test_row)
        self.test_details = QLabel()
        self.test_details.setWordWrap(True)
        self.test_details.setVisible(False)
        root.addWidget(self.test_details)
        self.test_btn.clicked.connect(self._selftest)
        self._test_worker: SelftestWorker | None = None

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.fix_btn = QPushButton("Automatisch einrichten")
        self.fix_btn.setObjectName("Primary")
        buttons.addWidget(self.close_btn)
        buttons.addWidget(self.fix_btn)
        root.addLayout(buttons)
        make_scrollable(self, 600)

        self.close_btn.clicked.connect(self.reject)
        self.fix_btn.clicked.connect(self._install)
        self._refresh()
        if not any(i.key == "qemu" for i in self.report.issues):
            self._selftest()

    def _selftest(self) -> None:
        if self._test_worker and self._test_worker.isRunning():
            return
        self.test_btn.setEnabled(False)
        self.test_label.setText("Selbsttest läuft …")
        self.test_label.setStyleSheet("")
        self._test_worker = SelftestWorker()
        self._test_worker.result.connect(self._selftest_done)
        self._test_worker.start()

    def _selftest_done(self, checks: list) -> None:
        self.test_btn.setEnabled(True)
        ok = selftest.passed(checks)
        self.test_label.setText("✓  Selbsttest OK – QEMU startet auf diesem Rechner." if ok
                                else "✕  Selbsttest fehlgeschlagen – Details unten.")
        self.test_label.setStyleSheet(f"color: {style.OK if ok else style.DANGER};")
        lines = []
        for c in checks:
            color = style.OK if c.ok else style.DANGER
            detail = c.detail.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
            lines.append(f"<span style='color:{color}'>{'OK' if c.ok else 'FEHLER'}</span> &nbsp;{c.name}"
                         + (f"<br><span style='color:{style.MUTED}'>{detail}</span>" if detail else ""))
        self.test_details.setText("<br>".join(lines))
        self.test_details.setVisible(not ok)

    def _refresh(self) -> None:
        self.report = deps.check(self.info)
        if self.report.ok:
            self.issues_label.setText("✓  Alles ist installiert. Du kannst Agent-PCs erstellen.")
            self.issues_label.setStyleSheet(f"color: {style.OK};")
            self.fix_btn.setVisible(False)
            self.close_btn.setText("Weiter")
            return
        lines = []
        for i in self.report.issues:
            mark = "•" if i.fixable else "⚠"
            extra = "" if i.fixable else "  (muss von Hand behoben werden)"
            lines.append(f"{mark}  {i.text}{extra}")
        intro = "Es fehlt noch etwas. Bony's Agents kann das selbst installieren:" if self.report.fixable \
            else "Folgendes muss von Hand behoben werden:"
        self.issues_label.setText(intro + "\n\n" + "\n".join(lines))
        self.issues_label.setStyleSheet("")
        self.fix_btn.setVisible(bool(self.report.fixable))
        if self.info.os == "linux":
            self.fix_btn.setToolTip("Fragt einmal nach deinem Passwort (Administratorrechte).")
        elif self.info.os == "windows":
            self.fix_btn.setToolTip("Windows fragt einmal nach Zustimmung (Administratorrechte).")
        elif self.info.os == "macos":
            self.fix_btn.setToolTip("Installiert QEMU über Homebrew – fehlt Homebrew, öffnet sich dessen "
                                    "offizieller Installer im Terminal.")

    def _update_remmina(self) -> None:
        show = self.info.os == "linux" and remote.remmina_command() is None
        self.remmina_label.setVisible(show)
        self.remmina_btn.setVisible(show)

    def _install_remmina(self) -> None:
        self._remmina_worker = install_remmina(self, done=self._update_remmina)

    def _install(self) -> None:
        self._refresh()  # z. B. nach dem Homebrew-Installer im Terminal: vielleicht ist schon alles da
        if self.report.ok:
            self._selftest()
            return
        if any(i.key == "homebrew" for i in self.report.issues):
            self._install_homebrew()
            return
        self.fix_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.log.setVisible(True)
        self.result_label.setText("")
        self.worker = InstallWorker(self.info, self.report)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _install_homebrew(self) -> None:
        """macOS ohne Homebrew: erklären, dann den offiziellen Installer im Terminal öffnen."""
        box = QMessageBox(self)
        box.setWindowTitle("Homebrew installieren")
        box.setIcon(QMessageBox.Information)
        box.setText(deps.homebrew_explanation())
        go = box.addButton("Terminal öffnen", QMessageBox.AcceptRole)
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        try:
            deps.open_homebrew_installer(self.info.arch)
        except (OSError, RuntimeError) as e:
            self.result_label.setText(f"Terminal ließ sich nicht öffnen: {e}\nBitte Homebrew selbst installieren "
                                      "(https://brew.sh) und danach im Terminal: brew install qemu")
            self.result_label.setStyleSheet(f"color: {style.DANGER};")
            return
        self.result_label.setText("Das Terminal-Fenster ist offen – bitte dort weitermachen. "
                                  "Wenn dort „Fertig!“ steht, hier auf „Erneut prüfen“ klicken.")
        self.result_label.setStyleSheet(f"color: {style.WARN};")
        self.fix_btn.setText("Erneut prüfen")

    def _done(self, result: deps.InstallResult) -> None:
        self.progress.setVisible(False)
        self.fix_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        color = style.OK if result.success else style.DANGER
        if result.reboot_required:
            color = style.WARN
        self.result_label.setText(result.message)
        self.result_label.setStyleSheet(f"color: {color};")
        self.info = host.detect()
        self._refresh()
        if result.success:
            self._selftest()
        if result.reboot_required:
            self.fix_btn.setVisible(False)

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.wait(30000)
        super().reject()
