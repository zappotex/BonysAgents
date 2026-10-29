# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen: „Als Vorlage speichern …“ und das Fenster „Vorlagen“ (verwalten, weitergeben, importieren)."""

from __future__ import annotations

import getpass
import html
import tarfile
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from bonys_agents import (
    APP_NAME, apps, bonysfile, cloudinit, edition, host, mission_control, n8n, storage, templates, vm, vpnlink,
)
from bonys_agents.i18n import tr

from . import style
from .widgets import FlowLayout, PathLabel, PercentBar, confirm_delete, make_scrollable


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


def deletion_text(username: str, remove_personal: bool, vpn: bool = False, mission: bool = False,
                  workflows: bool = False) -> str:
    """``vpn``/``mission``/``workflows``: Bony's VPN, Mission Control bzw. n8n ist im Agent-PC installiert."""
    lines = []
    if remove_personal:
        lines.append(tr("PERSÖNLICHE DATEN (die Programme selbst bleiben installiert):"))
        lines.append(f"• {tr(vpnlink.FRESH_CLEANUP)}")
        if mission:
            lines.append(f"• {tr(mission_control.FRESH_CLEANUP)}")
        if workflows:
            lines.append(f"• {tr(n8n.FRESH_CLEANUP)}")
        for item in cloudinit.PERSONAL_DATA:
            lines.append(f"• {tr(item.title)}")
            for p in item.paths:
                lines.append(f"      /home/{username}/{p}{item.note()}")
    else:
        lines.append(tr("PERSÖNLICHE DATEN BLEIBEN ERHALTEN – Anmeldungen und API-Schlüssel stecken dann in der "
                        "Vorlage. Nicht weitergeben!"))
        if vpn:
            lines.append(f"⚠ {tr(vpnlink.CLONE_WARNING)}")
        if mission:
            lines.append(f"⚠ {tr(mission_control.CLONE_NOTE)}")
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
        self.setWindowTitle(tr("Als Vorlage speichern"))
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("„{name}“ als Vorlage speichern", name=machine.name))
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(tr("Aus der Vorlage entstehen neue Agent-PCs in Sekunden – ohne Downloads und Einrichtung. "
                          "Das Original bleibt unverändert: Verallgemeinert wird eine Kopie seiner Festplatte, "
                          "ohne Internetverbindung."))
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)

        form = QFormLayout()
        self.name = QLineEdit(templates.suggest_name(machine.name))
        self.description = QLineEdit()
        self.description.setPlaceholderText(tr("z. B. Brave, Telegram und Hermes – frisch, ohne Anmeldungen"))
        form.addRow(tr("Name"), self.name)
        form.addRow(tr("Beschreibung"), self.description)
        root.addLayout(form)
        self.personal = QCheckBox(tr("Persönliche Daten entfernen (Anmeldungen, API-Schlüssel, Gedächtnis …)"))
        self.personal.setChecked(True)
        root.addWidget(self.personal)

        sec = QLabel(tr("WAS IN DER VORLAGE GELÖSCHT WIRD"))
        sec.setObjectName("Section")
        root.addWidget(sec)
        self.listing = QPlainTextEdit()
        self.listing.setReadOnly(True)
        self.listing.setMinimumHeight(style.px(160))
        root.addWidget(self.listing, 1)
        prow = QHBoxLayout()
        self.preview_btn = QPushButton(tr("Im Agent-PC nachsehen (Probelauf) …"))
        self.preview_btn.setObjectName("Small")
        self.preview_btn.setToolTip(tr("Startet kurz eine Kopie (ohne Netz) und listet auf, was dort tatsächlich "
                                       "gelöscht würde – mit Größen. Ändert nichts."))
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
        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.ok_btn = QPushButton(tr("Vorlage erstellen"))
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
            self.status.setText(tr("„{name}“ läuft – er wird vorher heruntergefahren.", name=machine.name))

    def _update_listing(self) -> None:
        self.listing.setPlainText(deletion_text(self.machine.config.username, self.personal.isChecked(),
                                                self._has_vpn(), self._has_mc(), self._has_n8n()))

    def _has_vpn(self) -> bool:
        return vpnlink.APP_ID in self.machine.config.apps

    def _has_mc(self) -> bool:
        return mission_control.APP_ID in self.machine.config.apps

    def _has_n8n(self) -> bool:
        return n8n.APP_ID in self.machine.config.apps

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
        if QMessageBox.question(self, APP_NAME, tr("„{name}“ läuft. Jetzt herunterfahren?\n\nDie Vorlage entsteht "
                                                   "aus der ausgeschalteten Festplatte.",
                                                   name=m.name)) != QMessageBox.Yes:
            return False
        return True

    def _run(self, fn, on_done) -> None:
        stop_first = self.machine.is_running()
        machine = self.machine

        def job(progress):
            if stop_first:
                progress("shutdown", 0.0, tr("Fahre „{name}“ herunter …", name=machine.name))
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
            pw, ok = QInputDialog.getText(self, APP_NAME, tr("{msg}\n\nPasswort von „{name}“:", msg=msg,
                                                             name=self.machine.name),
                                          QLineEdit.Password)
            if ok and pw:
                self.password = pw
                self.status.setText(tr("Passwort übernommen – bitte erneut starten."))
            return
        self.status.setText(tr("Fehler: {msg}", msg=msg))
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _preview(self) -> None:
        if not self._ensure_stopped():
            return
        remove = self.personal.isChecked()
        name, pw = self.machine.name, self.password

        def show(out: str) -> None:
            self._set_busy(False)
            self.status.setText(tr("Probelauf fertig – nichts wurde gelöscht."))
            self.listing.setPlainText(deletion_text(self.machine.config.username, remove, self._has_vpn(),
                                                    self._has_mc(), self._has_n8n())
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
        vpn_note = f"\n\n{tr(vpnlink.CLONE_WARNING)}" if self._has_vpn() else ""
        if not self.personal.isChecked() and QMessageBox.warning(
                self, APP_NAME, tr("Persönliche Daten bleiben in der Vorlage – Anmeldungen, Sitzungen und "
                                   "API-Schlüssel stecken dann in jedem Agent-PC, der daraus "
                                   "entsteht.{vpn_note}\n\nTrotzdem fortfahren?", vpn_note=vpn_note),
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




def creator_default() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return ""


class ExportDialog(QDialog):
    """„Weitergeben (.bonys) …“: Frisch-Prüfung, Lizenzen, Ersteller/Version/Vorschaubild, Fortschritt, Abbrechen."""

    def __init__(self, t: templates.Template, parent=None, target: Path | None = None):
        """``target``: feste Zieldatei (z. B. Zwischenspeicher für eine Freigabe) – dann ohne Dateiauswahl."""
        super().__init__(parent)
        self.t = t
        self.worker: FnWorker | None = None
        self.cancel = threading.Event()
        self.password: str | None = None
        self.preview: Path | None = None
        self.result_file: Path | None = None
        self.clean = False
        self.setWindowTitle(tr("Vorlage weitergeben"))
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("„{name}“ weitergeben", name=t.name))
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(tr("Speichert die Vorlage als eine .bonys-Datei – z. B. für eine Schulung. Vorher startet eine "
                          "Kopie ohne Netz und wird geprüft: Anmeldungen, Tokens, Schlüssel, Browser-Daten, Verläufe "
                          "dürfen nicht mit. Die Vorlage selbst bleibt unverändert."))
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        if not t.personal_data_removed:
            warn = QLabel(tr("⚠ Diese Vorlage wurde MIT persönlichen Daten erstellt (Klon). Weitergeben geht nur "
                             "„frisch gemacht“: Die persönlichen Daten werden dabei in der Export-Kopie entfernt."))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {style.WARN}; font-weight: 600;")
            root.addWidget(warn)
            self.fresh = QCheckBox(tr("Frisch machen (persönliche Daten in der Export-Kopie entfernen)"))
            root.addWidget(self.fresh)
        else:
            self.fresh = None
        removed = apps.not_redistributable(t.apps)
        if removed:
            lic = QLabel(tr("Lizenz: {wert} darf nicht weitergegeben werden – wird aus der Kopie entfernt. Im "
                            "Manifest steht „beim Empfänger neu installieren (offizielle Quelle)“; der Empfänger "
                            "installiert es mit „Programme hinzufügen …“.", wert=', '.join(apps.names(removed))))
            lic.setWordWrap(True)
            lic.setObjectName("Muted")
            root.addWidget(lic)

        form = QFormLayout()
        self.creator = QLineEdit(t.creator or creator_default())
        self.creator.setPlaceholderText(tr("z. B. dein Name oder der Kurs"))
        self.version = QLineEdit(t.version or "1.0")
        self.file = QLineEdit(str(Path.home() / bonysfile.default_filename(t.name, self.version.text())))
        file_row = QHBoxLayout()
        file_row.addWidget(self.file, 1)
        browse = QPushButton("…")
        browse.setObjectName("Small")
        file_row.addWidget(browse)
        self.preview_btn = QPushButton(tr("Vorschaubild wählen … (optional)"))
        self.preview_btn.setObjectName("Small")
        form.addRow(tr("Ersteller"), self.creator)
        form.addRow(tr("Version"), self.version)
        if target is None:
            form.addRow(tr("Datei"), file_row)
        else:
            self.file.setText(str(target))
            self.file.setVisible(False)
            browse.setVisible(False)
        form.addRow(tr("Bild"), self.preview_btn)
        root.addLayout(form)

        self.findings = QPlainTextEdit()
        self.findings.setReadOnly(True)
        self.findings.setVisible(False)
        self.findings.setMinimumHeight(style.px(140))
        root.addWidget(self.findings, 1)
        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.clean_btn = QPushButton(tr("In der Kopie bereinigen und exportieren"))
        self.clean_btn.setVisible(False)
        self.ok_btn = QPushButton(tr("Prüfen und exportieren"))
        self.ok_btn.setObjectName("Primary")
        for b in (self.cancel_btn, self.clean_btn, self.ok_btn):
            buttons.addWidget(b)
        root.addLayout(buttons)
        make_scrollable(self, 640)

        self.version.textChanged.connect(self._version_changed)
        browse.clicked.connect(self._browse)
        self.preview_btn.clicked.connect(self._choose_preview)
        self.cancel_btn.clicked.connect(self._cancel_or_close)
        self.ok_btn.clicked.connect(lambda: self._start(clean=False))
        self.clean_btn.clicked.connect(lambda: self._start(clean=True))

    def _version_changed(self, v: str) -> None:
        current = Path(self.file.text())
        self.file.setText(str(current.with_name(bonysfile.default_filename(self.t.name, v.strip() or "1"))))

    def _browse(self) -> None:
        file, _ = QFileDialog.getSaveFileName(self, tr("Speichern unter"), self.file.text(),
                                              tr("Bony's-Agents-Vorlage (*{SUFFIX})", SUFFIX=bonysfile.SUFFIX))
        if file:
            self.file.setText(file)

    def _choose_preview(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, tr("Vorschaubild"), str(Path.home()), tr("Bilder (*.png *.jpg "
                                                                                             "*.jpeg)"))
        if not file:
            return
        try:
            bonysfile._check_preview(Path(file))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.preview = Path(file)
        self.preview_btn.setText(tr("Bild: {name}", name=self.preview.name))

    def _busy(self, busy: bool) -> None:
        for w in (self.creator, self.version, self.file, self.preview_btn, self.ok_btn, self.clean_btn):
            w.setEnabled(not busy)
        if self.fresh is not None:
            self.fresh.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.cancel_btn.setText(tr("Export abbrechen") if busy else tr("Schließen"))
        if busy:
            self.progress.set_percent(0)
            self.status.setStyleSheet("")

    def _start(self, clean: bool) -> None:
        if self.fresh is not None and not self.fresh.isChecked() and not clean:
            self.status.setText(tr("Bitte „Frisch machen“ ankreuzen – Klone lassen sich nur so weitergeben."))
            return
        clean = clean or (self.fresh is not None and self.fresh.isChecked())
        target = Path(self.file.text().strip()).expanduser()
        if target.exists():
            if QMessageBox.question(self, APP_NAME, tr("{name} gibt es schon. Ersetzen?",
                                                       name=target.name)) != QMessageBox.Yes:
                return
            target.unlink()
        self.cancel.clear()
        self.findings.setVisible(False)
        self.clean_btn.setVisible(False)
        name, creator, version, preview, pw, cancel = (self.t.name, self.creator.text(), self.version.text(),
                                                       self.preview, self.password, self.cancel)
        self.worker = FnWorker(lambda progress: bonysfile.export(
            name, target, creator=creator, version=version, clean=clean, preview=preview, password=pw,
            progress=progress, cancel=cancel))
        self.worker.progress.connect(lambda _p, f, msg: (self.progress.set_percent(f * 100), self.status.setText(msg)))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self._busy(True)
        self.worker.start()

    def _done(self, file: Path) -> None:
        self.worker = None
        self._busy(False)
        self.result_file = file
        self.status.setText(tr("Fertig: {file} ({wert:.2f} GB). Diese Datei kannst du weitergeben – der Empfänger "
                               "importiert sie unter „Vorlagen“ (oder per Drag & Drop).", file=file,
                               wert=file.stat().st_size / storage.GB))
        self.ok_btn.setVisible(False)

    def _failed(self, msg: str) -> None:
        err = self.worker.error if self.worker else None
        self.worker = None
        self._busy(False)
        if isinstance(err, bonysfile.Cancelled):
            self.status.setText(tr("Abgebrochen – nichts wurde gespeichert."))
            return
        if isinstance(err, vm.NeedsPassword):
            pw, ok = QInputDialog.getText(self, APP_NAME, tr("{msg}\n\nPasswort des Benutzers „{username}“ in der "
                                                             "Vorlage:", msg=msg,
                                                             username=self.t.username), QLineEdit.Password)
            if ok and pw:
                self.password = pw
                self.status.setText(tr("Passwort übernommen – bitte erneut starten."))
            return
        if isinstance(err, bonysfile.NotFreshError) and not err.not_fresh_template:
            self.findings.setVisible(True)
            self.findings.setPlainText(
                (tr("Nach "
                    "dem "
                    "Bereinigen "
                    "noch "
                    "gefunden "
                    "– "
                    "Export "
                    "abgebrochen:\n\n") if err.strict else tr("Gefunden (nur Art und Ort – Inhalte werden nie "
                                                              "angezeigt):\n\n"))
                + bonysfile.format_findings(err.findings, per_category=20))
            if not err.strict:
                self.status.setText(tr("Export blockiert: In der Vorlage sind noch persönliche Daten oder "
                                       "Geheimnisse. „Bereinigen“ entfernt sie nur in der Export-Kopie – die Vorlage "
                                       "bleibt, wie sie ist."))
                self.clean_btn.setVisible(True)
                return
        self.status.setText(tr("Fehler: {msg}", msg=msg))
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _cancel_or_close(self) -> None:
        if self.worker and self.worker.isRunning():
            self.cancel.set()
            self.status.setText(tr("Breche ab und räume auf …"))
            return
        self.accept() if self.result_file else self.reject()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            self.cancel.set()
            return
        super().reject()


class ImportDialog(QDialog):
    """.bonys-Datei ansehen (Manifest, Vorschaubild), Architektur prüfen, importieren – oder das Rezept nutzen."""

    def __init__(self, file: Path, manifest: dict, parent=None):
        super().__init__(parent)
        self.file = Path(file)
        self.m = manifest
        self.worker: FnWorker | None = None
        self.cancel = threading.Event()
        self.result_template: templates.Template | None = None
        self.use_recipe = False
        self.setWindowTitle(tr("Vorlage importieren"))
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("Vorlage „{wert}“ importieren", wert=manifest['name']))
        title.setObjectName("Title")
        root.addWidget(title)
        try:
            data = bonysfile.read_preview(self.file)
        except (OSError, ValueError):
            data = None
        if data:
            pix = QPixmap()
            if pix.loadFromData(data):
                img = QLabel()
                img.setPixmap(pix.scaledToWidth(min(pix.width(), style.px(520)), Qt.SmoothTransformation))
                root.addWidget(img)
        # Texte aus einer fremden Datei: nie als HTML deuten
        text = bonysfile.describe_manifest(manifest, self.file.stat().st_size)
        info = QLabel(html.escape(text).replace("\n", "<br>"))
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)
        from_file = PathLabel(prefix=tr("Datei: "))  # langer Pfad ohne Leerzeichen – in der Mitte gekürzt
        from_file.set_path(self.file)
        root.addWidget(from_file)
        self.arch_ok = bonysfile.arch_matches(manifest)
        if not self.arch_ok:
            warn = QLabel("⚠ " + tr(bonysfile.SLOW_ARCH_WARNING, tpl=manifest["arch"],
                                    host=bonysfile.arch_name(host.detect().arch)))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {style.DANGER}; font-weight: 600;")
            root.addWidget(warn)
        # Rezept im Inhalt (nicht in der festen Knopfzeile – die darf nicht breiter als kleine Bildschirme werden)
        recipe_row = QHBoxLayout()
        self.recipe_btn = QPushButton(tr("Rezept nutzen …"))
        self.recipe_btn.setToolTip(tr("Derselbe Desktop mit denselben Apps, neu eingerichtet mit dem Debian-Image für "
                                      "diesen Rechner – ohne die Festplatte aus der Datei."))
        if not self.arch_ok:
            self.recipe_btn.setObjectName("Primary")
        recipe_row.addWidget(self.recipe_btn)
        recipe_hint = QLabel(tr("hier neu einrichten (passendes Debian-Image)"))
        recipe_hint.setObjectName("Muted")
        recipe_hint.setWordWrap(True)
        recipe_row.addWidget(recipe_hint, 1)
        root.addLayout(recipe_row)
        form = QFormLayout()
        self.name = QLineEdit(self._free_name(manifest["name"]))
        form.addRow(tr("Name"), self.name)
        root.addLayout(form)
        self.create = QCheckBox(tr("Danach gleich einen Agent-PC daraus erstellen"))
        self.create.setChecked(self.arch_ok)
        root.addWidget(self.create)
        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel(tr("Beim Import wird die Prüfsumme (SHA-256) geprüft."))
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.ok_btn = QPushButton(tr("Importieren") if self.arch_ok else tr("Trotzdem importieren"))
        self.ok_btn.setObjectName("Primary" if self.arch_ok else "")
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        root.addLayout(buttons)
        make_scrollable(self, 620)
        self.recipe_btn.clicked.connect(self._recipe)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._import)

    @staticmethod
    def _free_name(name: str) -> str:
        existing = {t.name for t in templates.list_templates()}
        new, n = name, 2
        while new in existing:
            new = f"{name[:36]}-{n}"
            n += 1
        return new

    def _recipe(self) -> None:
        self.use_recipe = True
        self.accept()

    def _import(self) -> None:
        name = self.name.text().strip()
        try:
            templates.check_name(name)
        except ValueError as e:
            self.status.setText(str(e))
            return
        self.cancel.clear()
        file, cancel, library = self.file, self.cancel, storage.preferred_library()
        self.worker = FnWorker(lambda progress: bonysfile.import_bundle(file, location=library, name=name,
                                                                        progress=progress, cancel=cancel))
        self.worker.progress.connect(lambda _p, f, msg: (self.progress.set_percent(f * 100), self.status.setText(msg)))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        for w in (self.name, self.create, self.ok_btn, self.recipe_btn):
            w.setEnabled(False)
        self.progress.setVisible(True)
        self.worker.start()

    def _done(self, t: templates.Template) -> None:
        self.worker = None
        self.result_template = t
        self.accept()

    def _failed(self, msg: str) -> None:
        err = self.worker.error if self.worker else None
        self.worker = None
        for w in (self.name, self.create, self.ok_btn, self.recipe_btn):
            w.setEnabled(True)
        self.progress.setVisible(False)
        if isinstance(err, bonysfile.Cancelled):
            self.status.setText(tr("Abgebrochen – nichts wurde übernommen."))
            return
        self.status.setText(tr("Fehler: {msg}", msg=msg))
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            self.cancel.set()
            self.status.setText(tr("Breche ab …"))
            return
        super().reject()


def open_bonys_file(parent, file: Path) -> str | None:
    """Datei importieren (mit Dialog). Gibt den Namen der neuen Vorlage zurück (oder None)."""
    from .create_dialog import CreateDialog

    file = Path(file)
    if not bonysfile.is_bonys(file):
        return None
    try:
        m = bonysfile.read_manifest(file)
    except (OSError, ValueError) as e:
        QMessageBox.warning(parent, APP_NAME, tr("Datei lässt sich nicht öffnen: {e}", e=e))
        return None
    dlg = ImportDialog(file, m, parent)
    if not dlg.exec():
        return None
    if dlg.use_recipe:
        CreateDialog(host.detect(), parent, recipe=bonysfile.recipe(m)).exec()
        return None
    t = dlg.result_template
    if t is None:
        return None
    if dlg.create.isChecked():
        create = CreateDialog(host.detect(), parent, preset_template=t.name)
        if create.exec() and t.reinstall:
            QMessageBox.information(parent, APP_NAME, tr("Nicht mitgeliefert (Lizenz): {wert}.\n\nSobald der "
                                                         "Agent-PC läuft: „Programme hinzufügen …“ – die Programme "
                                                         "sind dort schon ausgewählt und kommen aus der offiziellen "
                                                         "Quelle.", wert=', '.join(apps.names(t.reinstall))))
    return t.name


class TemplatesDialog(QDialog):
    """Vorlagen verwalten: Liste mit Größe, Datum und verknüpften Agent-PCs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: FnWorker | None = None
        self.setWindowTitle(tr("Vorlagen"))
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("Vorlagen"))
        title.setObjectName("Title")
        root.addWidget(title)
        hint = QLabel(tr("Neue Agent-PCs aus einer Vorlage: „+ Neuer Agent-PC“ → Grundlage. Eine Vorlage entsteht über "
                         "„Als Vorlage speichern …“ bei einem fertig eingerichteten Agent-PC. Weitergeben (z. B. für "
                         "eine Schulung): „Weitergeben …“ speichert eine .bonys-Datei; zum Importieren die Datei "
                         "einfach hierher ziehen."))
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
        self.where = PathLabel(prefix=tr("Ort: "))
        right.addWidget(self.where)
        right.addStretch(1)
        actions = FlowLayout()
        self.rename_btn = QPushButton(tr("Umbenennen …"))
        self.desc_btn = QPushButton(tr("Beschreibung ändern …"))
        self.export_btn = QPushButton(tr("Weitergeben (.bonys) …"))
        self.export_btn.setToolTip(tr("Als eine Datei speichern – mit Frisch-Prüfung, ohne nicht weitergebbare "
                                      "Programme"))
        self.share_btn: QPushButton | None = None   # nur Kursleiter-Version
        if edition.IS_TRAINER:
            self.share_btn = QPushButton(tr("Im Netzwerk freigeben …"))
            self.share_btn.setToolTip(tr("Schulung: Teilnehmer im selben Netz bzw. VPN laden die Vorlage direkt von "
                                         "hier („Schulung beitreten“)"))
        self.delete_btn = QPushButton(tr("Löschen"))
        self.delete_btn.setObjectName("Danger")
        for b in self._actions():
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
        self.import_btn = QPushButton(tr("Importieren …"))
        self.setAcceptDrops(True)
        bottom.addWidget(self.import_btn)
        bottom.addStretch(1)
        self.close_btn = QPushButton(tr("Schließen"))
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)
        make_scrollable(self, 760)

        self.list.currentItemChanged.connect(lambda *_: self._show())
        self.rename_btn.clicked.connect(self._rename)
        self.desc_btn.clicked.connect(self._describe)
        self.export_btn.clicked.connect(self._export)
        if self.share_btn is not None:
            self.share_btn.clicked.connect(self._share)
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
                                 + (tr(" · {n} verknüpft", n=n) if n else ""))
            it.setData(Qt.UserRole, t.name)
            self.list.addItem(it)
            if t.name == current:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._show()

    def _actions(self) -> list[QPushButton]:
        return [b for b in (self.rename_btn, self.desc_btn, self.export_btn, self.share_btn, self.delete_btn) if b]

    def current(self) -> templates.Template | None:
        it = self.list.currentItem()
        return self.items.get(it.data(Qt.UserRole)) if it else None

    def _show(self) -> None:
        t = self.current()
        busy = bool(self.worker and self.worker.isRunning())
        for b in self._actions():
            b.setEnabled(t is not None and not busy)
        self.import_btn.setEnabled(not busy)
        if t is None:
            self.details.setText(tr("Noch keine Vorlagen."))
            self.where.set_path("")
            return
        linked = t.linked_vms()
        rows = [
            f"<b style='font-size:{style.px(15)}px'>{t.name}</b>",
            html.escape(t.description) or "<i>keine Beschreibung</i>",
            "",
            tr("Erstellt: {wert} aus „{wert2}“", wert=html.escape(t.created_local()), wert2=html.escape(t.source)),
            tr("Debian {debian} · {arch} · Festplatte {groesse}", debian=html.escape(t.debian) or "?", arch=t.arch,
               groesse=vm.format_gb(t.disk_gb)),
            tr("Programme: {programme}", programme=", ".join(apps.names(t.apps)) or "–"),
            tr("Größe: {wert:.2f} GB", wert=t.size / storage.GB),
            tr("Persönliche Daten: entfernt") if t.personal_data_removed else
            tr("Persönliche Daten: <b style='color:{farbe}'>enthalten</b>", farbe=style.DANGER),
            tr("Verknüpfte Agent-PCs: {namen}", namen=", ".join(m.name for m in linked)) if linked else
            tr("Verknüpfte Agent-PCs: keine"),
        ]
        if t.creator or t.version:
            rows.insert(4, tr("Importiert: Version {wert} von {wert2}", wert=html.escape(t.version) or '?',
                              wert2=html.escape(t.creator) or 'unbekannt'))
        if t.reinstall:
            rows.insert(6, "Beim Erstellen neu installieren (Lizenz, offizielle Quelle): "
                        + ", ".join(apps.names(t.reinstall)))
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
        self.status.setText(tr("Fehler: {msg}", msg=msg))
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _rename(self) -> None:
        t = self.current()
        if not t:
            return
        new, ok = QInputDialog.getText(self, APP_NAME, tr("Neuer Name der Vorlage:"), text=t.name)
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
        text, ok = QInputDialog.getText(self, APP_NAME, tr("Beschreibung:"), text=t.description)
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
                QMessageBox.information(self, APP_NAME, tr("Löschen gesperrt: Diese Agent-PCs bauen auf „{name}“ "
                                                           "auf: {names}.\n\nZum Unabhängig-Machen bitte erst "
                                                           "herunterfahren: {wert}.", name=t.name, names=names,
                                                           wert=', '.join(running)))
                return
            if QMessageBox.question(
                    self, APP_NAME, tr("Löschen gesperrt: Diese Agent-PCs bauen auf „{name}“ auf: {names}.\n\nSollen "
                                       "sie jetzt zu unabhängigen Kopien werden (übernimmt die Daten der Vorlage, "
                                       "braucht mehr Platz)? Danach kann die Vorlage gelöscht werden.",
                                       name=t.name, names=names)) != QMessageBox.Yes:
                return

            def detach(progress):
                for i, m in enumerate(linked):
                    progress("detach", i / len(linked), tr("Mache „{name}“ unabhängig …", name=m.name))
                    m.make_independent(lambda f, i=i: progress("detach", (i + f) / len(linked),
                                                               tr("Mache „{name}“ unabhängig …", name=linked[i].name)))
                return len(linked)

            self._run(detach, lambda n: tr("{n} Agent-PC(s) sind jetzt unabhängig – die Vorlage kann gelöscht werden.",
                                           n=n))
            return
        if not confirm_delete(self, APP_NAME, tr("Vorlage „{name}“ ({wert:.1f} GB) löschen?", name=t.name,
                                                 wert=t.size / storage.GB),
                              tr("Agent-PCs, die schon daraus erstellt wurden, bleiben erhalten.")):
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
        dlg = ExportDialog(t, self)
        dlg.exec()
        if dlg.result_file:
            self.status.setText(tr("Gespeichert: {result_file}", result_file=dlg.result_file))
        self.reload(t.name)

    def _share(self) -> None:
        from bonys_agents.trainer.gui.share_dialog import ShareDialog

        t = self.current()
        if t:
            ShareDialog(t, self).exec()
            self.reload(t.name)

    def _import(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, tr("Vorlage importieren"), str(Path.home()),
                                              tr("Bony's-Agents-Vorlage ({muster})",
                                                 muster=f"*{bonysfile.SUFFIX} *{templates.FILE_SUFFIX}"))
        if file:
            self.import_file(Path(file))

    def import_file(self, file: Path) -> None:
        if bonysfile.is_bonys(file):
            name = open_bonys_file(self, file)
            if name:
                self.status.setText(tr("Vorlage „{name}“ importiert.", name=name))
                self.reload(name)
            return
        self._import_legacy(file)

    def _import_legacy(self, file: Path) -> None:
        """Altes Format .bonys-template (bis 0.16)."""
        try:
            info = templates.read_export_info(file)
        except (OSError, ValueError, KeyError, tarfile.TarError) as e:
            QMessageBox.warning(self, APP_NAME, tr("Datei lässt sich nicht lesen: {e}", e=e))
            return
        name = info.name
        if name in self.items:
            new, ok = QInputDialog.getText(self, APP_NAME, tr("Eine Vorlage „{name}“ gibt es schon. Name für die "
                                                              "importierte Vorlage:", name=name), text=f"{name}-2")
            if not ok or not new.strip():
                return
            name = new.strip()
        library = storage.preferred_library()
        self._run(lambda progress: templates.import_file(file, location=library, name=name, progress=progress),
                  lambda t: tr("Vorlage „{name}“ importiert nach {path}", name=t.name, path=t.path))

    @staticmethod
    def _dropped_file(event) -> Path | None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix in (bonysfile.SUFFIX, templates.FILE_SUFFIX) and path.is_file():
                return path
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802 – Qt
        if self._dropped_file(event) and not (self.worker and self.worker.isRunning()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 – Qt
        path = self._dropped_file(event)
        if path:
            event.acceptProposedAction()
            self.import_file(path)

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        super().reject()
