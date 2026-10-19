# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Kurspaket bearbeiten“ (nur Kursleiter-Edition) und die Knöpfe dafür in der Bibliothek.

Links die Gliederung (Steckbrief, Rezept, Ablaufplan, Handout, Lektionen – hinzufügen, löschen, umsortieren), rechts
die Seite dazu. Markdown mit Vorschau (dieselbe Anzeige wie im Anleitungs-Fenster), Bilder aus einer Datei oder als
Bildschirmfoto des Agent-PCs, Kursleitungs-Notizen, Zeiten, Quiz, Prüfaufgabe mit Skript-Vorlagen, Startzustand
(auch aus einem Ordner im Agent-PC übernommen). Gespeichert wird nur ein vollständig gültiges Kurspaket ohne
Geheimnisse (``trainer.kurspaket_editor.speichern``) – sonst bleibt der Ordner, wie er war.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from bonys_agents import apps, desktops, kurslauf, kurspaket, qemu, templates, vm
from bonys_agents.gui.kurspaket_anleitung import MarkdownAnsicht
from bonys_agents.gui.kurspaket_bibliothek import FILTER, skripte_erlauben
from bonys_agents.gui.widgets import fit_to_screen
from bonys_agents.gui.workers import TaskWorker
from bonys_agents.trainer import kurspaket_editor as ed

_FENSTER: dict[str, EditorFenster] = {}
_RUNNING: set[TaskWorker] = set()
ARTEN = ["Erklärung", "Mitmachen", "Übung", "Erklärung + Quiz", "Diskussion", "Pause"]
PRUEF_TYPEN = [("", "Keine Prüfaufgabe"), (kurspaket.SKRIPT, "Skript im Agent-PC"),
               ("agent-pc-laeuft", "Eingebaut: Agent-PC läuft"), ("vorlage-vorhanden", "Eingebaut: Vorlage vorhanden")]
SPRACHEN = [(".sh", "Bash"), (".py", "Python 3")]


def _lauf(fn, fertig: Callable[[TaskWorker], None]) -> None:
    w = TaskWorker(fn)
    _RUNNING.add(w)
    w.finished.connect(lambda: (_RUNNING.discard(w), fertig(w)))
    w.start()


def _mono(edit: QPlainTextEdit) -> QPlainTextEdit:
    edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    edit.setLineWrapMode(QPlainTextEdit.NoWrap)
    return edit


def _laufende_agent_pcs() -> list[vm.VM]:
    try:
        return [m for m in vm.list_vms() if m.is_running()]
    except (OSError, ValueError):
        return []


def agent_pc_waehlen(parent: QWidget, zweck: str) -> vm.VM | None:
    """Einen laufenden Agent-PC wählen (bei nur einem: diesen)."""
    laufend = _laufende_agent_pcs()
    if not laufend:
        QMessageBox.information(parent, "Agent-PC", f"Für {zweck} muss ein Agent-PC laufen – starte ihn im "
                                "Hauptfenster und versuche es dann noch einmal.")
        return None
    if len(laufend) == 1:
        return laufend[0]
    name, ok = QInputDialog.getItem(parent, "Agent-PC", f"Welcher Agent-PC – für {zweck}?",
                                    [m.name for m in laufend], 0, False)
    return next((m for m in laufend if m.name == name), None) if ok else None


# ---------------------------------------------------------------- Markdown mit Vorschau
class MarkdownEditor(QWidget):
    """Text links, Vorschau rechts. ``ordner()`` liefert den Ordner, in den Bilder kommen (relativ: ``bilder/…``)."""

    def __init__(self, ordner: Callable[[], Path | None], basis: Callable[[], Path], parent=None,
                 bildschirmfoto: Callable[[Path], Path | None] | None = None):
        super().__init__(parent)
        self.ordner, self.basis, self.foto = ordner, basis, bildschirmfoto
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        leiste = QHBoxLayout()
        self.bild_knopf = QPushButton("Bild einfügen …")
        self.foto_knopf = QPushButton("Bildschirmfoto des Agent-PCs")
        self.foto_knopf.setToolTip("Nimmt den Bildschirm eines laufenden Agent-PCs auf und fügt ihn hier ein")
        self.kasten_knopf = QPushButton("Kasten ▾")
        menue = QMenu(self.kasten_knopf)
        for art, text in (("tipp", "Tipp"), ("hinweis", "Hinweis"), ("warnung", "Achtung"),
                          ("datenschutz", "Datenschutz")):
            menue.addAction(text, lambda a=art: self._einfuegen(f"\n::: {a}\nText\n:::\n"))
        self.kasten_knopf.setMenu(menue)
        self.vorschau_box = QCheckBox("Vorschau")
        self.vorschau_box.setChecked(True)
        for w in (self.bild_knopf, self.foto_knopf, self.kasten_knopf):
            leiste.addWidget(w)
        leiste.addStretch(1)
        leiste.addWidget(self.vorschau_box)
        root.addLayout(leiste)
        self.split = QSplitter(Qt.Horizontal)
        self.text = QPlainTextEdit()
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.vorschau = MarkdownAnsicht()
        self.split.addWidget(self.text)
        self.split.addWidget(self.vorschau)
        root.addWidget(self.split, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._vorschau)
        self.text.textChanged.connect(self.timer.start)
        self.vorschau_box.toggled.connect(lambda an: (self.vorschau.setVisible(an), self._vorschau()))
        self.bild_knopf.clicked.connect(self._bild)
        self.foto_knopf.clicked.connect(self._foto)
        self.foto_knopf.setVisible(bildschirmfoto is not None)

    def setzen(self, text: str) -> None:
        self.text.blockSignals(True)
        self.text.setPlainText(text)
        self.text.blockSignals(False)
        self._vorschau()

    def wert(self) -> str:
        return self.text.toPlainText()

    def _vorschau(self) -> None:
        if not self.vorschau.isVisible() and not self.vorschau_box.isChecked():
            return
        ordner = self.ordner() or self.basis()
        self.vorschau.zeigen(self.wert(), ordner, self.basis())

    def _einfuegen(self, text: str) -> None:
        self.text.textCursor().insertText(text)
        self.text.setFocus()

    def _ziel_ordner(self) -> Path | None:
        ordner = self.ordner()
        if ordner is None:
            QMessageBox.information(self, "Bild", "Bitte das Kurspaket zuerst speichern.")
        return ordner

    def _bild(self) -> None:
        ordner = self._ziel_ordner()
        if ordner is None:
            return
        datei, _ = QFileDialog.getOpenFileName(self, "Bild einfügen", str(Path.home()), ed.BILD_DATEIEN)
        if not datei:
            return
        quelle = Path(datei)
        endung = quelle.suffix.lower()
        if endung not in {".png", ".jpg", ".jpeg", ".gif", ".webp"} or quelle.stat().st_size > 10 * 1024 ** 2:
            QMessageBox.warning(self, "Bild", "Erlaubt sind PNG, JPG, GIF und WebP bis 10 MB.")
            return
        ziel = ed.bild_name(ordner, quelle.stem, endung)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(quelle, ziel)
        ziel.chmod(0o644)
        self._einfuegen(f"![{quelle.stem}](bilder/{ziel.name})")

    def _foto(self) -> None:
        ordner = self._ziel_ordner()
        if ordner is None or self.foto is None:
            return
        ziel = self.foto(ordner)
        if ziel is not None:
            self._einfuegen(f"![Bildschirm](bilder/{ziel.name})")


# ---------------------------------------------------------------- Seiten
class SteckbriefSeite(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.id = QLabel()
        self.id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.name = QLineEdit()
        self.beschreibung = QPlainTextEdit()
        self.beschreibung.setMaximumHeight(90)
        self.stufe = QComboBox()
        for k, v in kurspaket.STUFEN.items():
            self.stufe.addItem(v, k)
        versionen = QHBoxLayout()
        self.version = QLineEdit()
        self.version.setMaximumWidth(110)
        self.erhoehen = QPushButton("Version erhöhen ▾")
        menue = QMenu(self.erhoehen)
        for teil, text in (("patch", "Korrektur (1.0.0 → 1.0.1)"), ("minor", "Neue Inhalte (1.0.0 → 1.1.0)"),
                           ("major", "Grundlegend neu (1.0.0 → 2.0.0)")):
            menue.addAction(text, lambda t=teil: self.version.setText(ed.version_erhoehen(self.version.text(), t)))
        self.erhoehen.setMenu(menue)
        versionen.addWidget(self.version)
        versionen.addWidget(self.erhoehen)
        versionen.addStretch(1)
        self.entwurf = QCheckBox("Entwurf (noch nicht ausgearbeitet)")
        self.autor = QLineEdit()
        self.lizenz = QLineEdit()
        self.sprache = QLineEdit()
        self.sprache.setMaximumWidth(80)
        self.dauer = QSpinBox()
        self.dauer.setRange(0, 6000)
        self.dauer.setSuffix(" min")
        self.dauer.setSpecialValueText("Summe der Lektionen")
        self.pause = QSpinBox()
        self.pause.setRange(0, 1440)
        self.pause.setSuffix(" min")
        gruppe = QHBoxLayout()
        self.t_min, self.t_max = QSpinBox(), QSpinBox()
        for s in (self.t_min, self.t_max):
            s.setRange(0, 1000)
            s.setSpecialValueText("–")
        gruppe.addWidget(QLabel("von"))
        gruppe.addWidget(self.t_min)
        gruppe.addWidget(QLabel("bis"))
        gruppe.addWidget(self.t_max)
        gruppe.addStretch(1)
        self.zielgruppe = QLineEdit()
        self.kosten = QLineEdit()
        self.voraussetzungen = QPlainTextEdit()
        self.lernziele = QPlainTextEdit()
        self.quellen = QPlainTextEdit()
        self.quellen.setPlaceholderText("Titel | https://…")
        for e in (self.voraussetzungen, self.lernziele, self.quellen):
            e.setMaximumHeight(80)
        form.addRow("Kennung:", self.id)
        form.addRow("Name:", self.name)
        form.addRow("Beschreibung:", self.beschreibung)
        form.addRow("Stufe:", self.stufe)
        form.addRow("Version:", versionen)
        form.addRow("", self.entwurf)
        form.addRow("Autor:", self.autor)
        form.addRow("Lizenz:", self.lizenz)
        form.addRow("Sprache:", self.sprache)
        form.addRow("Dauer:", self.dauer)
        form.addRow("Pausen:", self.pause)
        form.addRow("Teilnehmer:", gruppe)
        form.addRow("Zielgruppe:", self.zielgruppe)
        form.addRow("Kosten:", self.kosten)
        form.addRow("Voraussetzungen\n(je Zeile eine):", self.voraussetzungen)
        form.addRow("Lernziele\n(je Zeile eines):", self.lernziele)
        form.addRow("Quellen\n(Titel | Adresse):", self.quellen)

    def setzen(self, p: kurspaket.Kurspaket) -> None:
        self.id.setText(p.id)
        self.name.setText(p.name)
        self.beschreibung.setPlainText(p.beschreibung)
        self.stufe.setCurrentIndex(max(0, self.stufe.findData(p.stufe)))
        self.version.setText(p.version)
        self.entwurf.setChecked(p.entwurf)
        self.autor.setText(p.autor)
        self.lizenz.setText(p.lizenz)
        self.sprache.setText(p.sprache)
        summe = sum(lek.dauer_minuten for lek in p.lektionen)
        self.dauer.setValue(0 if p.dauer_minuten == summe else p.dauer_minuten)
        self.pause.setValue(p.pause_minuten)
        self.t_min.setValue(p.teilnehmer_min)
        self.t_max.setValue(p.teilnehmer_max)
        self.zielgruppe.setText(p.zielgruppe)
        self.kosten.setText(p.kosten)
        self.voraussetzungen.setPlainText("\n".join(p.voraussetzungen))
        self.lernziele.setPlainText("\n".join(p.lernziele))
        self.quellen.setPlainText("\n".join(f"{q['titel']} | {q['url']}" for q in p.quellen))

    def uebernehmen(self, p: kurspaket.Kurspaket) -> None:
        def zeilen(e: QPlainTextEdit) -> list[str]:
            return [z.strip() for z in e.toPlainText().splitlines() if z.strip()]

        p.name = self.name.text().strip()
        p.beschreibung = self.beschreibung.toPlainText().strip()
        p.stufe = self.stufe.currentData()
        p.version = self.version.text().strip()
        p.entwurf = self.entwurf.isChecked()
        p.autor = self.autor.text().strip()
        p.lizenz = self.lizenz.text().strip() or kurspaket.LIZENZ_STANDARD
        p.sprache = self.sprache.text().strip() or "de"
        p.dauer_minuten = self.dauer.value()
        p.pause_minuten = self.pause.value()
        p.teilnehmer_min, p.teilnehmer_max = self.t_min.value(), self.t_max.value()
        p.zielgruppe = self.zielgruppe.text().strip()
        p.kosten = self.kosten.text().strip()
        p.voraussetzungen = zeilen(self.voraussetzungen)
        p.lernziele = zeilen(self.lernziele)
        quellen = []
        for z in zeilen(self.quellen):
            titel, _, url = z.rpartition("|") if "|" in z else ("", "", z)
            quellen.append({"titel": titel.strip() or url.strip(), "url": url.strip()})
        p.quellen = quellen


class RezeptSeite(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        intro = QLabel("So wird der Agent-PC eingerichtet, wenn jemand das Kurspaket durcharbeitet – ein Kurspaket "
                       "enthält kein Festplatten-Abbild. Gibt es die genannte Vorlage auf dem Rechner, entsteht der "
                       "Agent-PC schnell daraus.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("agent-kurs")
        self.desktop = QComboBox()
        for d in desktops.DESKTOPS:
            self.desktop.addItem(desktops.name(d), d)
        self.apps = QListWidget()
        self.apps.setMaximumHeight(170)
        for a in apps.APPS.values():
            if a.hidden:
                continue
            item = QListWidgetItem(a.name)
            item.setData(Qt.UserRole, a.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.apps.addItem(item)
        self.ram, self.cpus, self.disk = QSpinBox(), QSpinBox(), QSpinBox()
        self.ram.setRange(0, 262144)
        self.ram.setSingleStep(1024)
        self.ram.setSuffix(" MB")
        self.cpus.setRange(0, 64)
        self.disk.setRange(0, vm.MAX_DISK_GB)
        self.disk.setSuffix(" GB")
        for s in (self.ram, self.cpus, self.disk):
            s.setSpecialValueText("Standard")
        self.username, self.keyboard, self.timezone = QLineEdit(), QLineEdit(), QLineEdit()
        self.vorlage = QComboBox()
        self.vorlage.setEditable(True)
        self.vorlage.addItem("")
        try:
            self.vorlage.addItems([t.name for t in templates.list_templates()])
        except (OSError, ValueError, RuntimeError):
            pass
        self.sha = QLineEdit()
        self.sha.setPlaceholderText("optional: SHA-256 der .bonys-Datei")
        form.addRow("Name des Agent-PCs:", self.name)
        form.addRow("Desktop:", self.desktop)
        form.addRow("Programme:", self.apps)
        form.addRow("Arbeitsspeicher:", self.ram)
        form.addRow("Prozessorkerne:", self.cpus)
        form.addRow("Festplatte:", self.disk)
        form.addRow("Benutzer:", self.username)
        form.addRow("Tastatur:", self.keyboard)
        form.addRow("Zeitzone:", self.timezone)
        form.addRow("Vorlage:", self.vorlage)
        form.addRow("Prüfsumme:", self.sha)
        root.addLayout(form)
        self.uebernehmen_knopf = QPushButton("Aus einem Agent-PC übernehmen …")
        self.uebernehmen_knopf.setToolTip("Desktop, Programme, RAM, CPUs, Festplatte, Benutzer, Tastatur, Zeitzone "
                                          "und Vorlage eines eingerichteten Agent-PCs übernehmen")
        self.uebernehmen_knopf.clicked.connect(self._aus_agent_pc)
        zeile = QHBoxLayout()
        zeile.addWidget(self.uebernehmen_knopf)
        zeile.addStretch(1)
        root.addLayout(zeile)
        root.addStretch(1)

    def setzen(self, r: kurspaket.Rezept) -> None:
        self.name.setText(r.name)
        self.desktop.setCurrentIndex(max(0, self.desktop.findData(r.desktop)))
        for i in range(self.apps.count()):
            item = self.apps.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in r.apps else Qt.Unchecked)
        self.unbekannt = [a for a in r.apps if a not in apps.APPS or apps.APPS[a].hidden]
        self.ram.setValue(r.ram_mb or 0)
        self.cpus.setValue(r.cpus or 0)
        self.disk.setValue(r.disk_gb or 0)
        self.username.setText(r.username)
        self.keyboard.setText(r.keyboard)
        self.timezone.setText(r.timezone)
        self.vorlage.setCurrentText(r.vorlage)
        self.sha.setText(r.vorlage_sha256)

    def wert(self) -> kurspaket.Rezept:
        gewaehlt = [self.apps.item(i).data(Qt.UserRole) for i in range(self.apps.count())
                    if self.apps.item(i).checkState() == Qt.Checked]
        disk = self.disk.value()
        return kurspaket.Rezept(
            name=self.name.text().strip(), desktop=self.desktop.currentData(),
            apps=gewaehlt + [a for a in getattr(self, "unbekannt", []) if a not in gewaehlt],
            ram_mb=self.ram.value() or None, cpus=self.cpus.value() or None,
            disk_gb=max(disk, vm.MIN_DISK_GB) if disk else None, username=self.username.text().strip() or "agent",
            keyboard=self.keyboard.text().strip() or "de", timezone=self.timezone.text().strip() or "Europe/Berlin",
            vorlage=self.vorlage.currentText().strip(), vorlage_sha256=self.sha.text().strip().lower())

    def _aus_agent_pc(self) -> None:
        try:
            maschinen = vm.list_vms()
        except (OSError, ValueError):
            maschinen = []
        if not maschinen:
            QMessageBox.information(self, "Rezept", "Es gibt noch keinen Agent-PC.")
            return
        name, ok = QInputDialog.getItem(self, "Rezept übernehmen", "Von welchem Agent-PC?",
                                        [m.name for m in maschinen], 0, False)
        if ok:
            m = next(m for m in maschinen if m.name == name)
            self.setzen(ed.rezept_aus_agent_pc(m, self.wert()))


class SkriptFeld(QWidget):
    """Skript-Editor mit Sprache (Bash/Python)."""

    def __init__(self, platzhalter: str, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        self.sprache = QComboBox()
        for endung, text in SPRACHEN:
            self.sprache.addItem(text, endung)
        kopf.addWidget(QLabel("Sprache:"))
        kopf.addWidget(self.sprache)
        self.kopf = kopf
        kopf.addStretch(1)
        root.addLayout(kopf)
        self.text = _mono(QPlainTextEdit())
        self.text.setPlaceholderText(platzhalter)
        root.addWidget(self.text, 1)

    def setzen(self, inhalt: str, pfad: str) -> None:
        self.text.setPlainText(inhalt)
        self.pfad = pfad
        endung = Path(pfad).suffix.lower() if pfad else (".py" if inhalt.startswith("#!/usr/bin/env python")
                                                          else ".sh")
        self.sprache.setCurrentIndex(max(0, self.sprache.findData(endung)))

    def skript_pfad(self, ordner: str, standard: str) -> str:
        """Pfad im Lektionsordner – mit der gewählten Endung."""
        basis = self.pfad if getattr(self, "pfad", "") else f"{ordner}/{standard}"
        return PurePosixPath(basis).with_suffix(self.sprache.currentData()).as_posix()   # auch unter Windows mit „/“

    def setzen_vorlage(self, inhalt: str) -> None:
        if self.text.toPlainText().strip() and QMessageBox.question(
                self, "Vorlage", "Das vorhandene Skript ersetzen?") != QMessageBox.Yes:
            return
        self.text.setPlainText(inhalt)
        self.sprache.setCurrentIndex(self.sprache.findData(".py" if inhalt.startswith("#!/usr/bin/env python")
                                                           else ".sh"))


class QuizSeite(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fragen: list[kurspaket.Frage] = []
        root = QHBoxLayout(self)
        links = QVBoxLayout()
        self.liste = QListWidget()
        links.addWidget(self.liste, 1)
        knoepfe = QHBoxLayout()
        self.neu = QPushButton("+ Frage")
        self.weg = QPushButton("Löschen")
        knoepfe.addWidget(self.neu)
        knoepfe.addWidget(self.weg)
        links.addLayout(knoepfe)
        root.addLayout(links, 1)
        form = QFormLayout()
        self.frage = QLineEdit()
        self.antworten = QPlainTextEdit()
        self.antworten.setPlaceholderText("Je Zeile eine Antwort (2 bis 6)")
        self.richtig = QSpinBox()
        self.richtig.setRange(1, 6)
        self.erklaerung = QPlainTextEdit()
        self.erklaerung.setMaximumHeight(80)
        form.addRow("Frage:", self.frage)
        form.addRow("Antworten:", self.antworten)
        form.addRow("Richtig ist Nr.:", self.richtig)
        form.addRow("Erklärung:", self.erklaerung)
        rechts = QWidget()
        rechts.setLayout(form)
        root.addWidget(rechts, 2)
        self.aktuell = -1
        self.liste.currentRowChanged.connect(self._wechsel)
        self.neu.clicked.connect(self._neu)
        self.weg.clicked.connect(self._weg)

    def setzen(self, fragen: list[kurspaket.Frage]) -> None:
        self.fragen = [replace(f, antworten=list(f.antworten)) for f in fragen]
        self.aktuell = -1
        self._liste()
        if self.fragen:
            self.liste.setCurrentRow(0)
        else:
            self._felder(None)

    def wert(self) -> list[kurspaket.Frage]:
        self._sichern()
        return [f for f in self.fragen if f.frage.strip()]

    def _liste(self) -> None:
        self.liste.blockSignals(True)
        self.liste.clear()
        for i, f in enumerate(self.fragen, 1):
            self.liste.addItem(f"{i}. {f.frage or '(neue Frage)'}")
        self.liste.blockSignals(False)

    def _felder(self, f: kurspaket.Frage | None) -> None:
        for w in (self.frage, self.antworten, self.richtig, self.erklaerung):
            w.setEnabled(f is not None)
        self.frage.setText(f.frage if f else "")
        self.antworten.setPlainText("\n".join(f.antworten) if f else "")
        self.richtig.setValue(f.richtig + 1 if f else 1)
        self.erklaerung.setPlainText(f.erklaerung if f else "")

    def _sichern(self) -> None:
        if 0 <= self.aktuell < len(self.fragen):
            antworten = [z.strip() for z in self.antworten.toPlainText().splitlines() if z.strip()]
            self.fragen[self.aktuell] = kurspaket.Frage(self.frage.text().strip(), antworten,
                                                        self.richtig.value() - 1, self.erklaerung.toPlainText().strip())

    def _wechsel(self, zeile: int) -> None:
        self._sichern()
        self.aktuell = zeile
        self._felder(self.fragen[zeile] if 0 <= zeile < len(self.fragen) else None)

    def _neu(self) -> None:
        self._sichern()
        self.fragen.append(kurspaket.Frage("", ["", ""], 0))
        self.aktuell = -1
        self._liste()
        self.liste.setCurrentRow(len(self.fragen) - 1)
        self.frage.setFocus()

    def _weg(self) -> None:
        zeile = self.liste.currentRow()
        if 0 <= zeile < len(self.fragen):
            self.fragen.pop(zeile)
            self.aktuell = -1
            self._liste()
            self.liste.setCurrentRow(min(zeile, len(self.fragen) - 1))
            if not self.fragen:
                self._felder(None)


class LektionSeite(QWidget):
    """Eine Lektion mit Reitern: Allgemein, Anleitung, Kursleitung, Prüfung, Startzustand, Quiz."""

    def __init__(self, editor: EditorFenster):
        super().__init__(editor)
        self.editor = editor
        self.le: ed.LektionEntwurf | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        allgemein = QWidget()
        form = QFormLayout(allgemein)
        self.titel = QLineEdit()
        self.ordner = QLabel()
        self.ordner.setObjectName("Muted")
        self.dauer = QSpinBox()
        self.dauer.setRange(0, 1440)
        self.dauer.setSuffix(" min")
        self.art = QComboBox()
        self.art.setEditable(True)
        self.art.addItems([""] + ARTEN)
        self.ziel = QPlainTextEdit()
        self.ziel.setMaximumHeight(90)
        form.addRow("Titel:", self.titel)
        form.addRow("Ordner:", self.ordner)
        form.addRow("Dauer:", self.dauer)
        form.addRow("Art:", self.art)
        form.addRow("Ziel:", self.ziel)
        self.tabs.addTab(allgemein, "Allgemein")

        self.anleitung = MarkdownEditor(self._bildordner, self.editor.basis, bildschirmfoto=self.editor.foto)
        self.tabs.addTab(self.anleitung, "Anleitung")
        self.kursleitung = MarkdownEditor(self._bildordner, self.editor.basis, bildschirmfoto=self.editor.foto)
        self.tabs.addTab(self.kursleitung, "Kursleitung")

        pruefung = QWidget()
        pl = QVBoxLayout(pruefung)
        pf = QFormLayout()
        self.typ = QComboBox()
        for k, v in PRUEF_TYPEN:
            self.typ.addItem(v, k)
        self.aufgabe = QLineEdit()
        self.aufgabe.setPlaceholderText("Was geprüft wird – sehen die Teilnehmer, z. B. „~/Kurs/einkaufsliste.txt "
                                        "mit Käse“")
        self.geschafft = QLineEdit()
        self.noch_nicht = QLineEdit()
        self.p_zeit = QSpinBox()
        self.p_zeit.setRange(1, kurspaket.PRUEF_ZEIT_MAX)
        self.p_zeit.setSuffix(" s")
        self.p_als = QComboBox()
        self.p_als.addItem("Benutzer des Agent-PCs", "benutzer")
        self.p_als.addItem("root", "root")
        pf.addRow("Prüfung:", self.typ)
        pf.addRow("Aufgabe:", self.aufgabe)
        pf.addRow("Text „geschafft“:", self.geschafft)
        pf.addRow("Text „noch nicht“:", self.noch_nicht)
        pf.addRow("Zeitlimit:", self.p_zeit)
        pf.addRow("Läuft als:", self.p_als)
        pl.addLayout(pf)
        self.skript_bereich = QTabWidget()
        self.pruef_skript = SkriptFeld("Exit-Code 0 = geschafft, sonst noch nicht. Läuft nur im Agent-PC, die Ausgabe "
                                       "wird verworfen.")
        self.vorlage_knopf = QPushButton("Vorlage einfügen ▾")
        menue = QMenu(self.vorlage_knopf)
        menue.addAction("Datei existiert …", self._vorlage_datei)
        menue.addAction("Dienst läuft …", self._vorlage_dienst)
        menue.addAction("Hermes eingerichtet",
                        lambda: self.pruef_skript.setzen_vorlage(ed.vorlage_hermes_eingerichtet()))
        self.vorlage_knopf.setMenu(menue)
        self.pruef_skript.kopf.addWidget(self.vorlage_knopf)
        self.loesung_skript = SkriptFeld("Optional: löst die Aufgabe – nur für „Kurspaket prüfen“ (Test-Agent-PC), "
                                         "Teilnehmer bekommen es nie ausgeführt.")
        self.skript_bereich.addTab(self.pruef_skript, "Prüfskript")
        self.skript_bereich.addTab(self.loesung_skript, "Lösung (optional)")
        pl.addWidget(self.skript_bereich, 1)
        self.tabs.addTab(pruefung, "Prüfung")

        start = QWidget()
        sl = QVBoxLayout(start)
        hinweis = QLabel("Startzustand: Beim ersten Betreten der Lektion läuft dieses Skript im Agent-PC, danach "
                         "sichert Bony's Agents den Zustand – „Lektion zurücksetzen“ kehrt dorthin zurück. Ohne Skript "
                         "wird nur gesichert.")
        hinweis.setObjectName("Muted")
        hinweis.setWordWrap(True)
        sl.addWidget(hinweis)
        sf = QFormLayout()
        self.start_an = QCheckBox("Startskript verwenden")
        self.s_zeit = QSpinBox()
        self.s_zeit.setRange(1, kurspaket.START_ZEIT_MAX)
        self.s_zeit.setSuffix(" s")
        self.s_als = QComboBox()
        self.s_als.addItem("root", "root")
        self.s_als.addItem("Benutzer des Agent-PCs", "benutzer")
        sf.addRow("", self.start_an)
        sf.addRow("Zeitlimit:", self.s_zeit)
        sf.addRow("Läuft als:", self.s_als)
        sl.addLayout(sf)
        self.start_skript = SkriptFeld("Richtet den Agent-PC für diese Lektion ein, z. B. Übungsdateien anlegen.")
        self.aus_pc = QPushButton("Aus Ordner im Agent-PC übernehmen …")
        self.aus_pc.setToolTip("Einen Ordner (z. B. ~/Kurs) aus einem laufenden Agent-PC lesen und ein Skript "
                               "erzeugen, das ihn bei Teilnehmern genauso anlegt")
        self.aus_pc.clicked.connect(self._aus_agent_pc)
        self.start_skript.kopf.addWidget(self.aus_pc)
        sl.addWidget(self.start_skript, 1)
        self.tabs.addTab(start, "Startzustand")

        self.quiz = QuizSeite()
        self.tabs.addTab(self.quiz, "Quiz")

        self.typ.currentIndexChanged.connect(self._sichtbar)
        self.start_an.toggled.connect(self._sichtbar)
        self.titel.textEdited.connect(lambda t: self.editor.lektion_umbenannt(t))

    def _bildordner(self) -> Path | None:
        return self.editor.lektion_ordner(self.le) if self.le is not None else None

    def _sichtbar(self) -> None:
        typ = self.typ.currentData()
        for w in (self.aufgabe, self.geschafft, self.noch_nicht):
            w.setEnabled(bool(typ))
        for w in (self.p_zeit, self.p_als, self.skript_bereich):
            w.setEnabled(typ == kurspaket.SKRIPT)
        for w in (self.s_zeit, self.s_als, self.start_skript):
            w.setEnabled(self.start_an.isChecked())

    def setzen(self, le: ed.LektionEntwurf) -> None:
        self.le = le
        lek = le.lektion
        self.titel.setText(lek.titel)
        self.ordner.setText(f"{kurspaket.LEKTIONEN}/{le.quelle.name}" if le.quelle is not None
                            and not le.quelle.name.startswith(".") else "(neu – entsteht beim Speichern)")
        self.dauer.setValue(lek.dauer_minuten)
        self.art.setCurrentText(lek.art)
        self.ziel.setPlainText(lek.ziel)
        self.anleitung.setzen(le.anleitung)
        self.kursleitung.setzen(le.kursleitung)
        p = lek.pruefung
        self.typ.setCurrentIndex(max(0, self.typ.findData(p.typ if p else "")))
        self.aufgabe.setText(p.aufgabe if p else "")
        self.geschafft.setText(p.geschafft if p else "Geschafft!")
        self.noch_nicht.setText(p.noch_nicht if p else "Noch nicht geschafft.")
        self.p_zeit.setValue(p.zeitlimit if p else kurspaket.PRUEF_ZEIT_STANDARD)
        self.p_als.setCurrentIndex(max(0, self.p_als.findData(p.als if p else "benutzer")))
        self.pruef_skript.setzen(le.pruef_skript, p.skript if p else "")
        self.loesung_skript.setzen(le.loesung_skript, p.loesung if p else "")
        s = lek.start
        self.start_an.setChecked(s is not None)
        self.s_zeit.setValue(s.zeitlimit if s else kurspaket.START_ZEIT_STANDARD)
        self.s_als.setCurrentIndex(max(0, self.s_als.findData(s.als if s else "root")))
        self.start_skript.setzen(le.start_skript, s.skript if s else "")
        self.quiz.setzen(le.quiz)
        self._sichtbar()

    def uebernehmen(self) -> None:
        le = self.le
        if le is None:
            return
        lek = le.lektion
        lek.titel = self.titel.text().strip()
        lek.dauer_minuten = self.dauer.value()
        lek.art = self.art.currentText().strip()
        lek.ziel = self.ziel.toPlainText().strip()
        le.anleitung = self.anleitung.wert()
        le.kursleitung = self.kursleitung.wert()
        typ = self.typ.currentData()
        if not typ:
            lek.pruefung = None
        else:
            skript = self.pruef_skript.skript_pfad("pruefung", "pruefen.sh") if typ == kurspaket.SKRIPT else ""
            loesung = self.loesung_skript.skript_pfad("pruefung", "loesung.sh") \
                if typ == kurspaket.SKRIPT and self.loesung_skript.text.toPlainText().strip() else ""
            if loesung == skript:
                loesung = PurePosixPath(loesung).with_name("loesung" + PurePosixPath(loesung).suffix).as_posix()
            lek.pruefung = kurspaket.Pruefung(
                typ=typ, skript=skript, loesung=loesung, aufgabe=self.aufgabe.text().strip(),
                geschafft=self.geschafft.text().strip(), noch_nicht=self.noch_nicht.text().strip(),
                zeitlimit=self.p_zeit.value(), als=self.p_als.currentData())
        le.pruef_skript = self.pruef_skript.text.toPlainText() if typ == kurspaket.SKRIPT else ""
        le.loesung_skript = self.loesung_skript.text.toPlainText() if typ == kurspaket.SKRIPT else ""
        if self.start_an.isChecked():
            lek.start = kurspaket.Start(skript=self.start_skript.skript_pfad("start", "start.sh"),
                                        zeitlimit=self.s_zeit.value(), als=self.s_als.currentData())
            le.start_skript = self.start_skript.text.toPlainText()
        else:
            lek.start, le.start_skript = None, ""
        le.quiz = self.quiz.wert()

    def _vorlage_datei(self) -> None:
        pfad, ok = QInputDialog.getText(self, "Datei existiert", "Datei im Agent-PC:", text="~/Kurs/datei.txt")
        if not ok:
            return
        enthaelt, ok = QInputDialog.getText(self, "Datei existiert", "Muss diesen Text enthalten (leer = egal):")
        if not ok:
            return
        try:
            self.pruef_skript.setzen_vorlage(ed.vorlage_datei_existiert(pfad, enthaelt))
        except ValueError as e:
            QMessageBox.warning(self, "Vorlage", str(e))

    def _vorlage_dienst(self) -> None:
        dienst, ok = QInputDialog.getText(self, "Dienst läuft", "Name des Dienstes (systemd):", text="docker")
        if not ok:
            return
        benutzer = QMessageBox.question(self, "Dienst läuft", "Ist es ein Benutzerdienst (systemctl --user)?") \
            == QMessageBox.Yes
        try:
            self.pruef_skript.setzen_vorlage(ed.vorlage_dienst_laeuft(dienst, benutzer))
        except ValueError as e:
            QMessageBox.warning(self, "Vorlage", str(e))
            return
        if benutzer:
            self.p_als.setCurrentIndex(self.p_als.findData("benutzer"))

    def _aus_agent_pc(self) -> None:
        machine = agent_pc_waehlen(self, "den Startzustand")
        if machine is None:
            return
        ordner, ok = QInputDialog.getText(self, "Startzustand übernehmen", "Ordner im Agent-PC:", text="~/Kurs")
        if not ok:
            return
        self.aus_pc.setEnabled(False)

        def fertig(w: TaskWorker) -> None:
            self.aus_pc.setEnabled(True)
            if w.error is not None:
                QMessageBox.warning(self, "Startzustand übernehmen", str(w.error))
                return
            self.start_an.setChecked(True)
            self.s_als.setCurrentIndex(self.s_als.findData("benutzer"))
            self.start_skript.setzen_vorlage(w.result)

        _lauf(lambda: ed.startskript_aus_agent_pc(machine, ordner), fertig)


# ---------------------------------------------------------------- „Kurspaket prüfen“
class PruefenDialog(QDialog):
    def __init__(self, paket: kurspaket.Kurspaket, parent=None):
        super().__init__(parent)
        self.paket = paket
        self.setWindowTitle(f"Kurspaket prüfen – {paket.name}")
        self._abbruch = False
        root = QVBoxLayout(self)
        intro = QLabel("Prüft Format, Bilder, Links und Geheimnisse. Mit einem Test-Agent-PC spielt es außerdem die "
                       "Lektionen durch: Startskripte, Syntax der Skripte, Prüfaufgaben vor und nach dem "
                       "Lösungsskript. Die Skripte laufen nur im Test-Agent-PC – am besten ein frischer nach dem "
                       "Rezept, der dabei verändert werden darf.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        self.agent_pc = QComboBox()
        self.agent_pc.addItem("– ohne Test-Agent-PC –", "")
        for m in _laufende_agent_pcs():
            self.agent_pc.addItem(m.name, m.name)
        self.zurueck = QCheckBox("Test-Agent-PC danach zurücksetzen (Neustart)")
        self.zurueck.setChecked(True)
        self.links = QCheckBox("Links im Internet prüfen")
        form.addRow("Test-Agent-PC:", self.agent_pc)
        form.addRow("", self.zurueck)
        form.addRow("", self.links)
        root.addLayout(form)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        root.addWidget(self.status)
        self.ergebnis = QPlainTextEdit()
        self.ergebnis.setReadOnly(True)
        root.addWidget(self.ergebnis, 1)
        knoepfe = QDialogButtonBox()
        self.start = knoepfe.addButton("Prüfen", QDialogButtonBox.AcceptRole)
        self.start.setObjectName("Primary")
        self.zu = knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        root.addWidget(knoepfe)
        self.start.clicked.connect(self._pruefen)
        self.zu.clicked.connect(self._schliessen)
        self.resize(680, 520)
        self.lauf: TaskWorker | None = None

    def _schliessen(self) -> None:
        if self.lauf is not None:
            self._abbruch = True
            self.status.setText("Breche nach der aktuellen Lektion ab …")
            return
        self.reject()

    def _pruefen(self) -> None:
        name = self.agent_pc.currentData()
        machine = None
        if name:
            try:
                machine = vm.get(name)
            except (KeyError, OSError, ValueError) as e:
                QMessageBox.warning(self, self.windowTitle(), str(e))
                return
            if not skripte_erlauben(self, self.paket):
                return
            if QMessageBox.question(self, self.windowTitle(),
                                    f"Die Skripte des Kurspakets verändern „{name}“. Fortfahren?") != QMessageBox.Yes:
                return
        self.start.setEnabled(False)
        self.ergebnis.clear()
        self._abbruch = False
        links, zurueck = self.links.isChecked(), self.zurueck.isChecked()

        def arbeit() -> list[ed.Meldung]:
            m = ed.pruefen_statisch(self.paket.pfad)
            if links:
                m += ed.links_pruefen(self.paket)
            if machine is not None and not any(x.stufe == ed.FEHLER and not x.wo for x in m):
                m += ed.durchspielen(machine, self.paket, progress=lambda _f, t: setattr(self, "_status", t),
                                     abbrechen=lambda: self._abbruch, zuruecksetzen=zurueck)
            return m

        self._status = "Prüfe …"
        timer = QTimer(self)
        timer.timeout.connect(lambda: self.status.setText(self._status))
        timer.start(300)

        def fertig(w: TaskWorker) -> None:
            timer.stop()
            self.lauf = None
            self.start.setEnabled(True)
            if w.error is not None:
                self.status.setText("")
                self.ergebnis.setPlainText(f"✗ {w.error}")
                return
            meldungen: list[ed.Meldung] = w.result
            fehler = sum(1 for x in meldungen if x.stufe == ed.FEHLER)
            warn = sum(1 for x in meldungen if x.stufe == ed.WARNUNG)
            self.status.setText("Alles in Ordnung." if not fehler and not warn else
                                f"{fehler} Fehler, {warn} Warnungen.")
            self.ergebnis.setPlainText("\n".join(str(x) for x in meldungen))

        self.lauf = TaskWorker(arbeit)
        _RUNNING.add(self.lauf)
        w = self.lauf
        w.finished.connect(lambda: (_RUNNING.discard(w), fertig(w)))
        w.start()


# ---------------------------------------------------------------- Editor-Fenster
class EditorFenster(QWidget):
    """Eigenes Fenster (nicht modal) zum Bearbeiten eines Paket-Ordners."""

    def __init__(self, ordner: Path, gespeichert: Callable[[kurspaket.Kurspaket], None] | None = None):
        super().__init__(None, Qt.Window)
        self.ordner = Path(ordner)
        self.gespeichert_cb = gespeichert
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._neu_nr = 0
        root = QVBoxLayout(self)
        self.split = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.gliederung = QListWidget()
        ll.addWidget(self.gliederung, 1)
        reihe = QHBoxLayout()
        self.plus = QPushButton("+ Lektion")
        self.minus = QPushButton("Löschen")
        self.hoch = QPushButton("↑")
        self.runter = QPushButton("↓")
        self.hoch.setToolTip("Lektion nach vorn")
        self.runter.setToolTip("Lektion nach hinten")
        for b in (self.plus, self.minus, self.hoch, self.runter):
            reihe.addWidget(b)
        ll.addLayout(reihe)
        self.split.addWidget(links)
        self.seiten = QStackedWidget()
        self.steckbrief = SteckbriefSeite()
        self.rezept = RezeptSeite()
        self.ablaufplan = MarkdownEditor(lambda: self.ordner, self.basis, bildschirmfoto=self.foto)
        self.handout = MarkdownEditor(lambda: self.ordner, self.basis, bildschirmfoto=self.foto)
        self.lektion_seite = LektionSeite(self)
        for s in (self.steckbrief, self.rezept, self.ablaufplan, self.handout, self.lektion_seite):
            self.seiten.addWidget(s)
        self.split.addWidget(self.seiten)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([240, 760])
        root.addWidget(self.split, 1)

        unten = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        unten.addWidget(self.status, 1)
        self.pruefen_knopf = QPushButton("Kurspaket prüfen …")
        self.pdf_knopf = QPushButton("PDF ▾")
        menue = QMenu(self.pdf_knopf)
        menue.addAction("Ablaufplan als PDF …", lambda: self._pdf("ablaufplan"))
        menue.addAction("Handout als PDF …", lambda: self._pdf("handout"))
        self.pdf_knopf.setMenu(menue)
        self.export_knopf = QPushButton("Exportieren …")
        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.setObjectName("Primary")
        self.speichern_knopf.setShortcut("Ctrl+S")
        zu = QPushButton("Schließen")
        for b in (self.pruefen_knopf, self.pdf_knopf, self.export_knopf, self.speichern_knopf, zu):
            unten.addWidget(b)
        root.addLayout(unten)

        self.gliederung.currentRowChanged.connect(self._wechsel)
        self.plus.clicked.connect(self._lektion_neu)
        self.minus.clicked.connect(self._lektion_weg)
        self.hoch.clicked.connect(lambda: self._verschieben(-1))
        self.runter.clicked.connect(lambda: self._verschieben(1))
        self.speichern_knopf.clicked.connect(self.speichern)
        self.pruefen_knopf.clicked.connect(self._pruefen)
        self.export_knopf.clicked.connect(self._exportieren)
        zu.clicked.connect(self.close)
        self._laden()
        fit_to_screen(self, 1100, 760)

    # ---------- Laden, Gliederung
    def basis(self) -> Path:
        return self.ordner

    def _laden(self, zeile: int = 0) -> None:
        self.entwurf = ed.Entwurf.laden(self.ordner)
        self.aktuell = -1
        self.steckbrief.setzen(self.entwurf.paket)
        self.rezept.setzen(self.entwurf.paket.rezept)
        self.ablaufplan.setzen(self.entwurf.ablaufplan)
        self.handout.setzen(self.entwurf.handout)
        self._gliederung(zeile)
        self._stand = self._zustand()
        self.setWindowTitle(f"Kurspaket bearbeiten – {self.entwurf.paket.name}")
        self.status.setText(f"Ordner: {self.ordner}")

    def _gliederung(self, zeile: int) -> None:
        self.gliederung.blockSignals(True)
        self.gliederung.clear()
        for text in ("Steckbrief", "Rezept (Agent-PC)", "Ablaufplan (Kursleitung)", "Handout (Teilnehmer)"):
            self.gliederung.addItem(text)
        for i, le in enumerate(self.entwurf.lektionen, 1):
            self.gliederung.addItem(f"  {i}. {le.lektion.titel or '(ohne Titel)'}")
        self.gliederung.blockSignals(False)
        self.gliederung.setCurrentRow(min(zeile, self.gliederung.count() - 1))
        self._wechsel(self.gliederung.currentRow())

    def _lektion_index(self, zeile: int | None = None) -> int:
        zeile = self.gliederung.currentRow() if zeile is None else zeile
        return zeile - 4 if zeile >= 4 else -1

    def _sichern(self) -> None:
        """Werte der aktuell sichtbaren Seite in den Entwurf übernehmen."""
        if self.aktuell == 0:
            self.steckbrief.uebernehmen(self.entwurf.paket)
        elif self.aktuell == 1:
            self.entwurf.paket.rezept = self.rezept.wert()
        elif self.aktuell == 2:
            self.entwurf.ablaufplan = self.ablaufplan.wert()
        elif self.aktuell == 3:
            self.entwurf.handout = self.handout.wert()
        elif self.aktuell >= 4:
            self.lektion_seite.uebernehmen()

    def _wechsel(self, zeile: int) -> None:
        if zeile < 0:
            return
        self._sichern()
        self.aktuell = zeile
        i = self._lektion_index(zeile)
        if i >= 0:
            self.lektion_seite.setzen(self.entwurf.lektionen[i])
            self.seiten.setCurrentWidget(self.lektion_seite)
        else:
            self.seiten.setCurrentIndex(zeile)
        self.minus.setEnabled(i >= 0)
        self.hoch.setEnabled(i > 0)
        self.runter.setEnabled(0 <= i < len(self.entwurf.lektionen) - 1)

    def lektion_umbenannt(self, titel: str) -> None:
        i = self._lektion_index()
        if i >= 0:
            self.gliederung.item(i + 4).setText(f"  {i + 1}. {titel or '(ohne Titel)'}")

    def lektion_ordner(self, le: ed.LektionEntwurf) -> Path:
        """Ordner für Bilder einer Lektion – neue Lektionen bekommen einen versteckten Ordner bis zum Speichern."""
        if le.quelle is None:
            self._neu_nr += 1
            le.quelle = self.ordner / kurspaket.LEKTIONEN / f".neu-{self._neu_nr}"
            le.quelle.mkdir(parents=True, exist_ok=True)
        return le.quelle

    def _lektion_neu(self) -> None:
        self._sichern()
        i = self._lektion_index()
        pos = i + 1 if i >= 0 else len(self.entwurf.lektionen)
        titel = f"Lektion {pos + 1}"
        self.entwurf.lektionen.insert(pos, ed.LektionEntwurf(
            kurspaket.Lektion(ordner="", titel=titel), anleitung=ed.ANLEITUNG_VORLAGE.format(titel=titel)))
        self.aktuell = -1
        self._gliederung(pos + 4)
        self.lektion_seite.titel.setFocus()
        self.lektion_seite.titel.selectAll()

    def _lektion_weg(self) -> None:
        i = self._lektion_index()
        if i < 0:
            return
        le = self.entwurf.lektionen[i]
        if QMessageBox.question(self, "Lektion löschen", f"Lektion „{le.lektion.titel}“ mit Anleitung, Quiz und "
                                "Skripten löschen? (Erst beim Speichern endgültig.)") != QMessageBox.Yes:
            return
        self.entwurf.lektionen.pop(i)
        self.aktuell = -1
        self._gliederung(min(i + 4, 3 + len(self.entwurf.lektionen)))

    def _verschieben(self, schritt: int) -> None:
        i = self._lektion_index()
        j = i + schritt
        if i < 0 or not 0 <= j < len(self.entwurf.lektionen):
            return
        self._sichern()
        ls = self.entwurf.lektionen
        ls[i], ls[j] = ls[j], ls[i]
        self.aktuell = -1
        self._gliederung(j + 4)

    # ---------- Speichern
    def _zustand(self) -> str:
        self._sichern()
        e = self.entwurf
        teile = [kurspaket.json_text(kurspaket.paket_json(replace(e.paket, lektionen=[le.lektion
                                                                                        for le in e.lektionen]))),
                 e.ablaufplan, e.handout]
        for le in e.lektionen:
            teile += [le.anleitung, le.kursleitung, le.pruef_skript, le.loesung_skript, le.start_skript,
                      repr(le.quiz), str(le.quelle)]
        return "\0".join(teile)

    def geaendert(self) -> bool:
        return self._zustand() != self._stand

    def speichern(self) -> bool:
        self._sichern()
        zeile = self.gliederung.currentRow()
        try:
            paket = ed.speichern(self.entwurf, self.ordner)
        except kurspaket.GeheimnisGefunden as e:
            QMessageBox.warning(self, "Nicht gespeichert – Geheimnis-Prüfung", str(e))
            return False
        except (kurspaket.PaketFehler, OSError, ValueError) as e:
            QMessageBox.warning(self, "Nicht gespeichert", f"Das Kurspaket ist so noch nicht gültig:\n\n{e}")
            return False
        for d in (self.ordner / kurspaket.LEKTIONEN).glob(".neu-*"):
            shutil.rmtree(d, ignore_errors=True)
        self._laden(zeile)
        self.status.setText(f"Gespeichert: {paket.name} {paket.version} – {self.ordner}")
        if self.gespeichert_cb:
            self.gespeichert_cb(paket)
        return True

    def _gespeichert_oder_fragen(self, was: str) -> bool:
        if not self.geaendert():
            return True
        if QMessageBox.question(self, was, f"Für „{was}“ muss das Kurspaket gespeichert sein. Jetzt speichern?") \
                != QMessageBox.Yes:
            return False
        return self.speichern()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.geaendert():
            box = QMessageBox(QMessageBox.Question, "Kurspaket bearbeiten", "Änderungen speichern?",
                              QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
            antwort = box.exec()
            if antwort == QMessageBox.Cancel or (antwort == QMessageBox.Save and not self.speichern()):
                e.ignore()
                return
        for d in (self.ordner / kurspaket.LEKTIONEN).glob(".neu-*"):
            shutil.rmtree(d, ignore_errors=True)
        _FENSTER.pop(str(self.ordner.resolve()), None)
        super().closeEvent(e)

    # ---------- Aktionen
    def foto(self, ordner: Path) -> Path | None:
        machine = agent_pc_waehlen(self, "das Bildschirmfoto")
        if machine is None:
            return None
        try:
            return ed.bildschirmfoto(machine, ed.bild_name(ordner, "bildschirm"))
        except (RuntimeError, OSError, kurslauf.NichtBereit, qemu.GuestAgentError) as e:
            QMessageBox.warning(self, "Bildschirmfoto", str(e))
            return None

    def _pruefen(self) -> None:
        if not self._gespeichert_oder_fragen("Kurspaket prüfen"):
            return
        PruefenDialog(kurspaket.laden(self.ordner), self).exec()

    def _pdf(self, welches: str) -> None:
        if not self._gespeichert_oder_fragen("PDF"):
            return
        paket = kurspaket.laden(self.ordner)
        name = f"{paket.id}-{'ablaufplan' if welches == 'ablaufplan' else 'handout'}-{paket.version}.pdf"
        ziel, _ = QFileDialog.getSaveFileName(self, "PDF speichern", str(Path.home() / name), "PDF (*.pdf)")
        if not ziel:
            return
        self.pdf_knopf.setEnabled(False)
        self.status.setText("Erzeuge das PDF …")

        def fertig(w: TaskWorker) -> None:
            self.pdf_knopf.setEnabled(True)
            if w.error is not None:
                self.status.setText("")
                QMessageBox.warning(self, "PDF", str(w.error))
                return
            self.status.setText(f"PDF gespeichert: {w.result}")

        _lauf(lambda: ed.pdf_bauen(paket, welches, Path(ziel)), fertig)

    def _exportieren(self) -> None:
        if not self._gespeichert_oder_fragen("Exportieren"):
            return
        paket = kurspaket.laden(self.ordner)
        ziel, _ = QFileDialog.getSaveFileName(self, "Kurspaket exportieren",
                                              str(Path.home() / kurspaket.dateiname(paket)), FILTER)
        if not ziel:
            return
        if not ziel.lower().endswith(kurspaket.SUFFIX):
            ziel += kurspaket.SUFFIX
        try:
            kurspaket.packen(self.ordner, Path(ziel))
        except (kurspaket.PaketFehler, OSError) as e:
            QMessageBox.warning(self, "Kurspaket exportieren", str(e))
            return
        self.status.setText(f"Exportiert: {ziel}")


def oeffnen(ordner: Path, gespeichert: Callable[[kurspaket.Kurspaket], None] | None = None) -> EditorFenster:
    """Editor für ``ordner`` öffnen – ist er schon offen, nach vorn holen."""
    key = str(Path(ordner).resolve())
    fenster = _FENSTER.get(key)
    if fenster is None:
        fenster = EditorFenster(Path(ordner), gespeichert)
        _FENSTER[key] = fenster
    fenster.show()
    fenster.raise_()
    fenster.activateWindow()
    return fenster


# ---------------------------------------------------------------- Knöpfe in der Bibliothek
def bibliothek_knoepfe(seite, leiste: QHBoxLayout) -> None:
    """„Neu …“, „Bearbeiten …“, „Duplizieren …“ und „Ordner öffnen …“ für den Reiter „Kurspakete“."""
    neu = QPushButton("Neu …")
    neu.setToolTip("Neues Kurspaket anlegen und bearbeiten")
    bearbeiten = QPushButton("Bearbeiten …")
    duplizieren_knopf = QPushButton("Duplizieren …")
    ordner_knopf = QPushButton("Ordner öffnen …")
    ordner_knopf.setToolTip("Kurspaket-Ordner bearbeiten, der nicht in der Bibliothek liegt (z. B. in einem "
                            "Git-Repository)")
    for i, b in enumerate((neu, bearbeiten, duplizieren_knopf, ordner_knopf)):
        leiste.insertWidget(i, b)

    def neu_geladen(paket: kurspaket.Kurspaket) -> None:
        seite.laden(paket.id)

    def auswahl() -> None:
        p = seite.paket()
        bearbeiten.setEnabled(p is not None)
        duplizieren_knopf.setEnabled(p is not None)

    def anlegen() -> None:
        dlg = NeuDialog(seite)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            paket = ed.neu_anlegen(dlg.name.text(), dlg.stufe.currentData(), dlg.kennung.text().strip(),
                                   dlg.autor.text())
        except (kurspaket.PaketFehler, OSError) as e:
            QMessageBox.warning(seite, "Neues Kurspaket", str(e))
            return
        seite.laden(paket.id)
        oeffnen(paket.pfad, neu_geladen)

    def kopieren(p: kurspaket.Kurspaket, gleiche_id: bool = False) -> kurspaket.Kurspaket | None:
        if gleiche_id:
            neue_id, name = p.id, p.name
        else:
            name, ok = QInputDialog.getText(seite, "Duplizieren", "Name der Kopie:", text=f"{p.name} (Kopie)")
            if not ok or not name.strip():
                return None
            neue_id, ok = QInputDialog.getText(seite, "Duplizieren", "Kennung der Kopie:", text=ed.slug(name, 60))
            if not ok:
                return None
        try:
            kopie = ed.duplizieren(p, neue_id.strip(), name)
        except (kurspaket.PaketFehler, OSError) as e:
            QMessageBox.warning(seite, "Duplizieren", str(e))
            return None
        seite.laden(kopie.id)
        return kopie

    def bearbeiten_klick() -> None:
        p = seite.paket()
        if p is None:
            return
        if not ed.bearbeitbar(p):
            box = QMessageBox(QMessageBox.Question, "Kurspaket bearbeiten",
                              f"„{p.name}“ gehört zum Programm und lässt sich nicht direkt ändern.",
                              QMessageBox.NoButton, seite)
            box.setInformativeText("„Eigene Fassung“ legt eine Kopie mit derselben Kennung in deiner Bibliothek an – "
                                   "sie ersetzt das mitgelieferte Kurspaket, der Fortschritt bleibt. „Duplizieren“ "
                                   "macht daraus ein neues Kurspaket.")
            eigen = box.addButton("Eigene Fassung", QMessageBox.AcceptRole)
            kopie = box.addButton("Duplizieren …", QMessageBox.ActionRole)
            box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is eigen:
                p = kopieren(p, gleiche_id=True)
            elif box.clickedButton() is kopie:
                p = kopieren(p)
            else:
                return
            if p is None:
                return
        oeffnen(p.pfad, neu_geladen)

    def duplizieren_klick() -> None:
        p = seite.paket()
        if p is not None and (kopie := kopieren(p)) is not None:
            oeffnen(kopie.pfad, neu_geladen)

    def ordner_klick() -> None:
        d = QFileDialog.getExistingDirectory(seite, "Kurspaket-Ordner öffnen", str(Path.home()))
        if not d:
            return
        try:
            kurspaket.laden(Path(d))
        except kurspaket.PaketFehler as e:
            QMessageBox.warning(seite, "Kurspaket-Ordner öffnen", str(e))
            return
        oeffnen(Path(d), neu_geladen)

    neu.clicked.connect(anlegen)
    bearbeiten.clicked.connect(bearbeiten_klick)
    duplizieren_knopf.clicked.connect(duplizieren_klick)
    ordner_knopf.clicked.connect(ordner_klick)
    seite.tabelle.itemSelectionChanged.connect(auswahl)
    auswahl()
    seite.editor_knoepfe = (neu, bearbeiten, duplizieren_knopf, ordner_knopf)


class NeuDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Kurspaket")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Einführung in Hermes Agent")
        self.kennung = QLineEdit()
        self.kennung.setPlaceholderText("wird aus dem Namen gebildet")
        self.stufe = QComboBox()
        for k, v in kurspaket.STUFEN.items():
            self.stufe.addItem(v, k)
        self.autor = QLineEdit()
        form.addRow("Name:", self.name)
        form.addRow("Kennung:", self.kennung)
        form.addRow("Stufe:", self.stufe)
        form.addRow("Autor:", self.autor)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Anlegen")
        form.addRow(knoepfe)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        self.name.textEdited.connect(lambda t: self.kennung.setPlaceholderText(ed.slug(t, 60) or
                                                                               "wird aus dem Namen gebildet"))
        self.resize(460, 0)

    def _ok(self) -> None:
        if len(self.name.text().strip()) < 3:
            QMessageBox.information(self, self.windowTitle(), "Bitte einen Namen eingeben (mindestens 3 Zeichen).")
            return
        self.accept()

