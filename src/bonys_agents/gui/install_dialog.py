# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog „Programme hinzufügen“: fehlende Apps in einen laufenden Agent-PC installieren.

Über den Gast-Agent (ohne Passwort), sonst per SSH. Abhängigkeiten (z. B. Docker für Mission Control) kommen
automatisch mit. Jede fertige App steht sofort in vm.json – bricht etwas ab, setzt „Installieren“ fort.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from bonys_agents import apps, desktops, mission_control, n8n, vm
from bonys_agents import progress as pct
from bonys_agents.i18n import tr

from . import style
from .widgets import PercentBar, make_scrollable


class InstallWorker(QThread):
    log = Signal(str)
    step = Signal(int, int, str)  # (Nummer, Anzahl, App-ID)
    done = Signal(bool, str)      # (Erfolg, Meldung)
    needs_password = Signal()

    def __init__(self, machine: vm.VM, app_ids: list[str], password: str):
        super().__init__()
        self.machine = machine
        self.app_ids = app_ids
        self.password = password

    def run(self) -> None:
        try:
            self.machine.install_apps(self.app_ids, password=self.password or None, log=self.log.emit,
                                      step=self.step.emit)
        except vm.NeedsPassword:
            self.needs_password.emit()
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            self.done.emit(False, str(e))
        else:
            self.done.emit(True, tr("Fertig – die Symbole liegen auf dem Schreibtisch des Agent-PCs."))
        finally:
            self.password = ""  # nicht länger als nötig im Speicher halten


class InstallAppsDialog(QDialog):
    def __init__(self, machine: vm.VM, parent=None, preselect: list[str] | tuple[str, ...] = ()):
        super().__init__(parent)
        self.machine = machine
        self.worker: InstallWorker | None = None
        self.plan: list[str] = []
        self.current = -1
        self.step_text = ""
        self.mc_req = mission_control.requirements(fetch=False)
        self.setWindowTitle(tr("Programme hinzufügen"))

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("Programme hinzufügen"))
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(tr("Installiert fehlende Programme in „{name}“, während er läuft. Bricht "
                          "etwas ab, einfach erneut „Installieren“ – fertige Programme werden "
                          "übersprungen.", name=machine.name))
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.boxes: dict[str, QCheckBox] = {}
        choices = QVBoxLayout()
        choices.setSpacing(2)
        root.addLayout(choices)
        for a in machine.missing_apps():
            cb = QCheckBox(tr(a.name))
            cb.setToolTip(tr(a.description))
            text = tr(a.description)
            if a.id == mission_control.APP_ID:
                text += " – " + tr("Open Source, {bedarf}", bedarf=mission_control.requirement_note(self.mc_req))
            elif a.id == n8n.APP_ID:
                text += f". {tr(n8n.LICENSE_NOTE)} – {n8n.requirement_note()}"
            desc = QLabel(text)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            desc.setContentsMargins(26, 0, 0, 4)
            choices.addWidget(cb)
            choices.addWidget(desc)
            self.boxes[a.id] = cb
            cb.setChecked(a.id in preselect)
            cb.toggled.connect(self._update)

        self.plan_label = QLabel()
        self.plan_label.setWordWrap(True)
        root.addWidget(self.plan_label)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {style.WARN};")
        root.addWidget(self.warn)

        # Passwort nur, wenn der Gast-Agent nicht antwortet (dann geht es per SSH)
        self.pw_box = QLabel(tr("Passwort des Benutzers „{username}“ im Agent-PC", username=machine.config.username))
        self.pw_box.setObjectName("Section")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText(tr("nur nötig, wenn der Gast-Agent nicht antwortet – wird nicht gespeichert"))
        root.addSpacing(6)
        root.addWidget(self.pw_box)
        root.addWidget(self.pw)
        self.need_pw = not machine.guest_agent_ready()
        self.pw_box.setVisible(self.need_pw)
        self.pw.setVisible(self.need_pw)

        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(160)
        self.log.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.log, 1)
        root.addWidget(self.status)

        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton(tr("Schließen"))
        self.ok_btn = QPushButton(tr("Installieren"))
        self.ok_btn.setObjectName("Primary")
        row.addWidget(self.close_btn)
        row.addWidget(self.ok_btn)
        root.addLayout(row)
        make_scrollable(self, 600)

        self.close_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._install)
        self.pw.textChanged.connect(self._update)
        if mission_control.APP_ID in self.boxes:
            # Mindestwerte aus dem Release nachladen (höchstens 5 s), ohne das Fenster aufzuhalten
            threading.Thread(target=mission_control.requirements, daemon=True).start()
            QTimer.singleShot(6000, self, self._reload_requirements)
        self._update()

    def _reload_requirements(self) -> None:
        self.mc_req = mission_control.requirements(fetch=False)
        self._update()

    def selected(self) -> list[str]:
        return [i for i, cb in self.boxes.items() if cb.isChecked()]

    def _update(self, *_):
        busy = bool(self.worker and self.worker.isRunning())
        ids = self.selected()
        plan = self.machine.install_plan(ids) if ids else []
        deps = [i for i in plan if i not in ids]
        self.plan_label.setText(tr("Wird mitinstalliert: {wert}", wert=', '.join(apps.names(deps))) if deps else "")
        self.plan_label.setVisible(bool(deps))
        c = self.machine.config
        desktop_ram = desktops.get(c.desktop).min_ram_mb
        warnings = mission_control.resource_warnings(plan, c.ram_mb, c.disk_gb, desktop_ram, self.mc_req)
        # n8n zusammen mit einem schon installierten oder gleichzeitig gewählten Mission Control
        mc_ram = self.mc_req.min_ram_mb if mission_control.APP_ID in [*plan, *c.apps] else 0
        warnings += n8n.resource_warnings(plan, c.ram_mb, desktop_ram, mc_ram)
        if warnings:
            warnings.append(tr("Installieren geht trotzdem – RAM und Festplatte lassen sich im ausgeschalteten "
                               "Agent-PC anpassen."))
        self.warn.setText("\n".join(f"⚠ {w}" for w in warnings))
        self.warn.setVisible(bool(warnings))
        self.ok_btn.setEnabled(not busy and bool(ids) and (not self.need_pw or bool(self.pw.text())))

    def _install(self) -> None:
        ids = self.selected()
        self.plan = self.machine.install_plan(ids)
        self.current, self.step_text = -1, ""
        self.log.clear()
        self.log.setVisible(True)
        self.progress.setVisible(True)
        self.progress.set_percent(0)
        self.status.setText("")
        self.status.setStyleSheet("")
        for w in (*self.boxes.values(), self.pw, self.close_btn):
            w.setEnabled(False)
        self.worker = InstallWorker(self.machine, ids, self.pw.text())
        self.pw.clear()
        self.worker.log.connect(self._log)
        self.worker.step.connect(self._step)
        self.worker.done.connect(self._done)
        self.worker.needs_password.connect(self._ask_password)
        self.worker.start()
        self._update()

    def _step(self, n: int, total: int, app_id: str) -> None:
        self.current = self.plan.index(app_id) if app_id in self.plan else n - 1
        self.step_text = ""
        self.status.setText(tr("Installiere {name} ({n} von {total}) …", name=apps.APPS[app_id].name, n=n, total=total))
        self.progress.set_percent(pct.install_percent(self.plan, self.current, ""))

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)
        self.step_text += line + "\n"
        if self.current >= 0:
            self.progress.set_percent(pct.install_percent(self.plan, self.current, self.step_text))

    def _ask_password(self) -> None:
        self.need_pw = True
        self.pw_box.setVisible(True)
        self.pw.setVisible(True)
        self._finish(False, tr("Der Gast-Agent antwortet nicht – bitte das Passwort eingeben, dann geht es per SSH "
                               "weiter."))

    def _done(self, ok: bool, msg: str) -> None:
        self._finish(ok, msg)

    def _finish(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(msg)
        self.status.setStyleSheet(f"color: {style.OK if ok else style.DANGER};")
        self.close_btn.setEnabled(True)
        self.pw.setEnabled(True)
        # Erfolgreich installierte Apps aus der Auswahl nehmen
        for app_id, cb in self.boxes.items():
            installed = app_id in self.machine.config.apps
            cb.setEnabled(not installed)
            if installed:
                cb.setChecked(False)
                cb.setText(tr("{name} – installiert", name=apps.APPS[app_id].name))
        self._update()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
