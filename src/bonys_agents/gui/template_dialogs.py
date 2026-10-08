# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen: „Als Vorlage speichern …“ und das Fenster „Vorlagen“ (verwalten, exportieren, importieren)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from bonys_agents import APP_NAME, apps, cloudinit, storage, templates, vm

from . import style
from .widgets import FlowLayout, PathLabel, PercentBar, make_scrollable


class FnWorker(QThread):
    """Lange Aufgabe mit Fortschritt (phase, 0..1, Text) im Hintergrund."""

    progress = Signal(str, float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
            self.error = e
            self.failed.emit(str(e))


def deletion_text(username: str, remove_personal: bool) -> str:
    lines = []
    if remove_personal:
        lines.append("PERSÖNLICHE DATEN (die Programme selbst bleiben installiert):")
        for item in cloudinit.PERSONAL_DATA:
            lines.append(f"• {item.title}")
            for p in item.paths:
                lines.append(f"      /home/{username}/{p}{item.note()}")
    else:
        lines.append("PERSÖNLICHE DATEN BLEIBEN ERHALTEN – Anmeldungen und API-Schlüssel stecken dann in der "
                     "Vorlage. Nicht weitergeben!")
    lines.append("")
    lines.append("SYSTEM (immer):")
    lines += [f"• {line}" for line in cloudinit.SYSTEM_CLEANUP]
    return "\n".join(lines)


class SaveTemplateDialog(QDialog):
    """„Als Vorlage speichern …“ – Name, Beschreibung, persönliche Daten entfernen, Vorschau."""

    def __init__(self, machine: vm.VM, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.worker: FnWorker | None = None
        self.password: str | None = None
        self.result_template: templates.Template | None = None
        self.setWindowTitle("Als Vorlage speichern")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(f"„{machine.name}“ als Vorlage speichern")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Aus der Vorlage entstehen neue Agent-PCs in Sekunden – ohne Downloads und Einrichtung. "
                       "Das Original bleibt unverändert: Verallgemeinert wird eine Kopie seiner Festplatte, "
                       "ohne Internetverbindung.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)

        form = QFormLayout()
        self.name = QLineEdit(templates.suggest_name(machine.name))
        self.description = QLineEdit()
        self.description.setPlaceholderText("z. B. Brave, Telegram und Hermes – frisch, ohne Anmeldungen")
        form.addRow("Name", self.name)
        form.addRow("Beschreibung", self.description)
        root.addLayout(form)
        self.personal = QCheckBox("Persönliche Daten entfernen (Anmeldungen, API-Schlüssel, Gedächtnis …)")
        self.personal.setChecked(True)
        root.addWidget(self.personal)

        sec = QLabel("WAS IN DER VORLAGE GELÖSCHT WIRD")
        sec.setObjectName("Section")
        root.addWidget(sec)
        self.listing = QPlainTextEdit()
        self.listing.setReadOnly(True)
        self.listing.setMinimumHeight(style.px(160))
        root.addWidget(self.listing, 1)
        prow = QHBoxLayout()
        self.preview_btn = QPushButton("Im Agent-PC nachsehen (Probelauf) …")
        self.preview_btn.setObjectName("Small")
        self.preview_btn.setToolTip("Startet kurz eine Kopie (ohne Netz) und listet auf, was dort tatsächlich "
                                    "gelöscht würde – mit Größen. Ändert nichts.")
        prow.addWidget(self.preview_btn)
        prow.addStretch(1)
        root.addLayout(prow)

        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Vorlage erstellen")
        self.ok_btn.setObjectName("Primary")
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        root.addLayout(buttons)
        make_scrollable(self, 640)

        self.personal.toggled.connect(self._update_listing)
        self.preview_btn.clicked.connect(self._preview)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._create)
        self._update_listing()
        if machine.is_running():
            self.status.setText(f"„{machine.name}“ läuft – er wird vorher heruntergefahren.")

    def _update_listing(self) -> None:
        self.listing.setPlainText(deletion_text(self.machine.config.username, self.personal.isChecked()))

    def _set_busy(self, busy: bool) -> None:
        for w in (self.name, self.description, self.personal, self.preview_btn, self.ok_btn, self.cancel_btn):
            w.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.progress.set_percent(0)
            self.status.setStyleSheet("")

    def _ensure_stopped(self) -> bool:
        m = self.machine
        if not m.is_running():
            return True
        if QMessageBox.question(self, APP_NAME, f"„{m.name}“ läuft. Jetzt herunterfahren?\n\nDie Vorlage entsteht "
                                "aus der ausgeschalteten Festplatte.") != QMessageBox.Yes:
            return False
        return True

    def _run(self, fn, on_done) -> None:
        stop_first = self.machine.is_running()
        machine = self.machine

        def job(progress):
            if stop_first:
                progress("shutdown", 0.0, f"Fahre „{machine.name}“ herunter …")
                machine.stop()
            return fn(progress)

        self._set_busy(True)
        self.worker = FnWorker(job)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, _phase: str, frac: float, msg: str) -> None:
        self.progress.set_percent(frac * 100)
        self.status.setText(msg)

    def _on_failed(self, msg: str) -> None:
        self._set_busy(False)
        if self.worker and isinstance(self.worker.error, vm.NeedsPassword):
            pw, ok = QInputDialog.getText(self, APP_NAME, f"{msg}\n\nPasswort von „{self.machine.name}“:",
                                          QLineEdit.Password)
            if ok and pw:
                self.password = pw
                self.status.setText("Passwort übernommen – bitte erneut starten.")
            return
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _preview(self) -> None:
        if not self._ensure_stopped():
            return
        remove = self.personal.isChecked()
        name, pw = self.machine.name, self.password

        def show(out: str) -> None:
            self._set_busy(False)
            self.status.setText("Probelauf fertig – nichts wurde gelöscht.")
            self.listing.setPlainText(deletion_text(self.machine.config.username, remove)
                                      + "\n\nGEFUNDEN IM AGENT-PC (Probelauf):\n" + out)

        self._run(lambda progress: templates.preview(name, remove, password=pw, progress=progress), show)

    def _create(self) -> None:
        try:
            templates.check_name(self.name.text().strip())
        except ValueError as e:
            self.status.setText(str(e))
            return
        if not self._ensure_stopped():
            return
        if not self.personal.isChecked() and QMessageBox.warning(
                self, APP_NAME, "Persönliche Daten bleiben in der Vorlage – Anmeldungen, Sitzungen und API-Schlüssel "
                "stecken dann in jedem Agent-PC, der daraus entsteht.\n\nTrotzdem fortfahren?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        name, desc = self.name.text().strip(), self.description.text().strip()
        remove, mname, pw = self.personal.isChecked(), self.machine.name, self.password

        def finished(t) -> None:
            self.result_template = t
            self.worker = None
            self.accept()

        self._run(lambda progress: templates.create(mname, name, desc, remove_personal=remove, password=pw,
                                                    progress=progress), finished)

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()


class TemplatesDialog(QDialog):
    """Vorlagen verwalten: Liste mit Größe, Datum und verknüpften Agent-PCs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: FnWorker | None = None
        self.setWindowTitle("Vorlagen")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Vorlagen")
        title.setObjectName("Title")
        root.addWidget(title)
        hint = QLabel("Neue Agent-PCs aus einer Vorlage: „+ Neuer Agent-PC“ → Grundlage. Eine Vorlage entsteht über "
                      "„Als Vorlage speichern …“ bei einem fertig eingerichteten Agent-PC.")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        root.addWidget(hint)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(style.px(180))
        body.addWidget(self.list)
        right = QVBoxLayout()
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        right.addWidget(self.details)
        self.where = PathLabel(prefix="Ort: ")
        right.addWidget(self.where)
        right.addStretch(1)
        actions = FlowLayout()
        self.rename_btn = QPushButton("Umbenennen …")
        self.desc_btn = QPushButton("Beschreibung ändern …")
        self.export_btn = QPushButton("Exportieren …")
        self.delete_btn = QPushButton("Löschen")
        self.delete_btn.setObjectName("Danger")
        for b in (self.rename_btn, self.desc_btn, self.export_btn, self.delete_btn):
            actions.addWidget(b)
        right.addLayout(actions)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        self.import_btn = QPushButton("Importieren …")
        bottom.addWidget(self.import_btn)
        bottom.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)
        make_scrollable(self, 760)

        self.list.currentItemChanged.connect(lambda *_: self._show())
        self.rename_btn.clicked.connect(self._rename)
        self.desc_btn.clicked.connect(self._describe)
        self.export_btn.clicked.connect(self._export)
        self.delete_btn.clicked.connect(self._delete)
        self.import_btn.clicked.connect(self._import)
        self.close_btn.clicked.connect(self.reject)
        self.reload()

    def reload(self, select: str | None = None) -> None:
        current = select or (self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None)
        self.items = {t.name: t for t in templates.list_templates()}
        self.list.clear()
        for t in self.items.values():
            n = len(t.linked_vms())
            it = QListWidgetItem(f"{t.name}\n{t.size / storage.GB:.1f} GB · {t.created_local()}"
                                 + (f" · {n} verknüpft" if n else ""))
            it.setData(Qt.UserRole, t.name)
            self.list.addItem(it)
            if t.name == current:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._show()

    def current(self) -> templates.Template | None:
        it = self.list.currentItem()
        return self.items.get(it.data(Qt.UserRole)) if it else None

    def _show(self) -> None:
        t = self.current()
        busy = bool(self.worker and self.worker.isRunning())
        for b in (self.rename_btn, self.desc_btn, self.export_btn, self.delete_btn):
            b.setEnabled(t is not None and not busy)
        self.import_btn.setEnabled(not busy)
        if t is None:
            self.details.setText("Noch keine Vorlagen.")
            self.where.set_path("")
            return
        linked = t.linked_vms()
        rows = [
            f"<b style='font-size:{style.px(15)}px'>{t.name}</b>",
            t.description or "<i>keine Beschreibung</i>",
            "",
            f"Erstellt: {t.created_local()} aus „{t.source}“",
            f"Debian {t.debian or '?'} · {t.arch} · Festplatte {vm.format_gb(t.disk_gb)}",
            f"Programme: {', '.join(apps.names(t.apps)) or '–'}",
            f"Größe: {t.size / storage.GB:.2f} GB",
            "Persönliche Daten: " + ("entfernt" if t.personal_data_removed
                                     else f"<b style='color:{style.DANGER}'>enthalten</b>"),
            "Verknüpfte Agent-PCs: " + (", ".join(m.name for m in linked) if linked else "keine"),
        ]
        self.details.setText("<br>".join(rows))
        self.where.set_path(t.path)

    def _busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.close_btn.setEnabled(not busy)
        if busy:
            self.progress.set_percent(0)
            self.status.setStyleSheet("")
        self._show()

    def _run(self, fn, done_text) -> None:
        self.worker = FnWorker(fn)
        self.worker.progress.connect(lambda _p, f, msg: (self.progress.set_percent(f * 100), self.status.setText(msg)))
        self.worker.done.connect(lambda result: self._finished(done_text(result)))
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _finished(self, text: str) -> None:
        self.worker = None
        self._busy(False)
        self.status.setText(text)
        self.reload()

    def _failed(self, msg: str) -> None:
        self.worker = None
        self._busy(False)
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _rename(self) -> None:
        t = self.current()
        if not t:
            return
        new, ok = QInputDialog.getText(self, APP_NAME, "Neuer Name der Vorlage:", text=t.name)
        if not ok or not new.strip() or new.strip() == t.name:
            return
        try:
            templates.rename(t.name, new.strip())
        except (ValueError, RuntimeError, FileExistsError, OSError, KeyError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.reload(new.strip())

    def _describe(self) -> None:
        t = self.current()
        if not t:
            return
        text, ok = QInputDialog.getText(self, APP_NAME, "Beschreibung:", text=t.description)
        if ok:
            templates.set_description(t.name, text.strip())
            self.reload(t.name)

    def _delete(self) -> None:
        t = self.current()
        if not t:
            return
        linked = t.linked_vms()
        if linked:
            names = ", ".join(m.name for m in linked)
            running = [m.name for m in linked if m.is_running()]
            if running:
                QMessageBox.information(self, APP_NAME, f"Löschen gesperrt: Diese Agent-PCs bauen auf „{t.name}“ auf: "
                                        f"{names}.\n\nZum Unabhängig-Machen bitte erst herunterfahren: "
                                        f"{', '.join(running)}.")
                return
            if QMessageBox.question(
                    self, APP_NAME, f"Löschen gesperrt: Diese Agent-PCs bauen auf „{t.name}“ auf: {names}.\n\n"
                    "Sollen sie jetzt zu unabhängigen Kopien werden (übernimmt die Daten der Vorlage, braucht "
                    "mehr Platz)? Danach kann die Vorlage gelöscht werden.") != QMessageBox.Yes:
                return

            def detach(progress):
                for i, m in enumerate(linked):
                    progress("detach", i / len(linked), f"Mache „{m.name}“ unabhängig …")
                    m.make_independent(lambda f, i=i: progress("detach", (i + f) / len(linked),
                                                               f"Mache „{linked[i].name}“ unabhängig …"))
                return len(linked)

            self._run(detach, lambda n: f"{n} Agent-PC(s) sind jetzt unabhängig – die Vorlage kann gelöscht werden.")
            return
        if QMessageBox.question(self, APP_NAME, f"Vorlage „{t.name}“ ({t.size / storage.GB:.1f} GB) löschen?"
                                ) != QMessageBox.Yes:
            return
        try:
            templates.delete(t.name)
        except (RuntimeError, OSError, KeyError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))
        self.reload()

    def _export(self) -> None:
        t = self.current()
        if not t:
            return
        if QMessageBox.information(self, APP_NAME, templates.EXPORT_WARNING + (
                "" if t.personal_data_removed else "\n\nACHTUNG: Diese Vorlage wurde MIT persönlichen Daten erstellt."),
                QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return
        start = str(Path.home() / f"{t.name}{templates.FILE_SUFFIX}")
        file, _ = QFileDialog.getSaveFileName(self, "Vorlage exportieren", start,
                                              f"Vorlage (*{templates.FILE_SUFFIX})")
        if not file:
            return
        name = t.name
        self._run(lambda progress: templates.export(name, Path(file), progress=progress),
                  lambda out: f"Exportiert: {out}")

    def _import(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Vorlage importieren", str(Path.home()),
                                              f"Vorlage (*{templates.FILE_SUFFIX})")
        if not file:
            return
        try:
            info = templates.read_export_info(Path(file))
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, APP_NAME, f"Datei lässt sich nicht lesen: {e}")
            return
        name = info.name
        if name in self.items:
            new, ok = QInputDialog.getText(self, APP_NAME, f"Eine Vorlage „{name}“ gibt es schon. Name für die "
                                           "importierte Vorlage:", text=f"{name}-2")
            if not ok or not new.strip():
                return
            name = new.strip()
        library = storage.preferred_library()
        self._run(lambda progress: templates.import_file(Path(file), location=library, name=name,
                                                         progress=progress),
                  lambda t: f"Vorlage „{t.name}“ importiert nach {t.path}")

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
