# SPDX-License-Identifier: GPL-3.0-or-later
"""Bibliothek „Kurspakete“ (beide Editionen): Reiter im Fenster „Kurse“.

Liste der Kurspakete (mitgeliefert, aus Datei, aus dem Internet) mit Stufe, Dauer und Fortschritt; Importieren per
Datei oder Drag & Drop, Exportieren, Löschen, Aktualisieren; „Aus dem Internet …“ lädt die Liste aus dem öffentlichen
Repo (Prüfsumme). „Durcharbeiten“ startet den Selbstlern-Modus: eigener Agent-PC aus Rezept bzw. Vorlage, Fortschritt
pro Kurspaket, Anleitung in einem eigenen Fenster (``kurspaket_anleitung``).

Ein Kurspaket ist der *Inhalt*; ein *Kurs* (Reiter „Teilnahme“/„Kursleitung“) ist die Durchführung.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from bonys_agents import apps, desktops, host, kurslauf, kurspaket, vm

from .workers import TaskWorker

INTRO = ("Kurspakete sind fertige Inhalte zum Durcharbeiten – allein zu Hause (Selbstlern-Modus) oder in einem Kurs. "
         "„Durcharbeiten“ richtet dafür einen eigenen Agent-PC nach dem Rezept des Pakets ein, zeigt die Anleitung "
         "neben dem Agent-PC und merkt sich deinen Fortschritt – nur auf diesem Rechner.")
FILTER = f"Kurspakete (*{kurspaket.SUFFIX});;Alle Dateien (*)"
_RUNNING: set[TaskWorker] = set()


def _paket_text(p: kurspaket.Kurspaket) -> str:
    """Beschreibung als Markdown (für ein QLabel mit MarkdownText)."""
    zeilen = [f"**{p.name}**" + ("  *(Entwurf)*" if p.entwurf else ""), "", p.beschreibung, ""]
    angaben = [f"Stufe: {p.stufe_text}", f"Dauer: {p.dauer_text}"]
    if p.teilnehmer_min or p.teilnehmer_max:
        angaben.append(f"Gruppe: {p.teilnehmer_text}")
    angaben.append(f"{len(p.lektionen)} Lektionen" if p.lektionen else "ohne Lektionen (nur Ablaufplan/Handout)")
    zeilen += [" · ".join(angaben), ""]
    if p.lernziele:
        zeilen += ["Lernziele:", ""] + [f"- {z}" for z in p.lernziele] + [""]
    if p.voraussetzungen:
        zeilen += ["Voraussetzungen: " + "; ".join(p.voraussetzungen), ""]
    if p.kosten:
        zeilen += [f"Kosten: {p.kosten}", ""]
    r = p.rezept
    app_namen = ", ".join(apps.names([a for a in r.apps if a in apps.APPS])) or "–"
    zeilen += [f"Agent-PC: {desktops.name(r.desktop)}, Programme: {app_namen}"
               + (f", Vorlage „{r.vorlage}“ (wenn vorhanden)" if r.vorlage else ""), ""]
    autor = f"{p.autor} · " if p.autor else ""
    zeilen.append(f"{autor}Version {p.version} · Lizenz {p.lizenz} · {kurspaket.HERKUNFT_TEXT.get(p.herkunft, '')}")
    return "\n".join(zeilen)


def _vertrauen_text(p: kurspaket.Kurspaket) -> str:
    if kurslauf.geprueft(p):
        return "\n\n✓ **Geprüftes Kurspaket** (von Bony's Agents)"
    n = len(p.skripte())
    if not n:
        return "\n\nNicht geprüft – enthält aber keine Skripte."
    return (f"\n\n⚠ Nicht geprüft – enthält {n} Skript{'e' if n > 1 else ''}, die nur im Agent-PC laufen. "
            "Vor dem ersten Start wirst du gefragt.")


def _md(text: str) -> str:
    """Text aus einem Kurspaket sicher in Markdown einsetzen (keine Links/Bilder/HTML aus fremden Daten)."""
    for z in "\\`*_[]<>!#|":
        text = text.replace(z, "\\" + z)
    return text


def ist_paket(pfad: Path) -> bool:
    return (pfad.is_file() and pfad.suffix.lower() == kurspaket.SUFFIX) or (pfad / kurspaket.PAKET_JSON).is_file()


def importieren(parent: QWidget, quelle: Path, fertig: Callable[[kurspaket.Kurspaket | None], None]) -> None:
    """Import im Hintergrund; bei gleicher ID nachfragen und dann ersetzen."""

    def lauf(ersetzen: bool) -> None:
        w = TaskWorker(lambda: kurspaket.importieren(quelle, ersetzen=ersetzen))
        _RUNNING.add(w)

        def ende() -> None:
            _RUNNING.discard(w)
            if isinstance(w.error, kurspaket.PaketExistiert):
                if QMessageBox.question(parent, "Kurspaket importieren", str(w.error)) == QMessageBox.Yes:
                    lauf(True)
                    return
                fertig(None)
            elif w.error is not None:
                QMessageBox.warning(parent, "Kurspaket importieren",
                                    f"„{quelle.name}“ lässt sich nicht importieren:\n\n{w.error}")
                fertig(None)
            else:
                fertig(w.result)

        w.finished.connect(ende)
        w.start()

    lauf(False)


def skripte_erlauben(parent: QWidget | None, paket: kurspaket.Kurspaket) -> bool:
    """Vor dem ersten Start eines fremden (nicht geprüften) Kurspakets: Hinweis mit der Liste seiner Skripte.

    True, wenn es losgehen darf (keine Skripte, geprüft, schon zugestimmt oder jetzt zugestimmt)."""
    if not kurslauf.zustimmung_noetig(paket):
        return True
    liste = "\n".join(f"• Lektion „{lek.titel}“ – {art}: {pfad}" for lek, art, pfad in paket.skripte())
    box = QMessageBox(QMessageBox.Warning, paket.name, "Dieses Kurspaket führt Skripte im Agent-PC aus.",
                      QMessageBox.NoButton, parent)
    box.setInformativeText(
        "Das Kurspaket ist nicht von Bony's Agents geprüft. Seine Skripte laufen ausschließlich im abgeschotteten "
        "Agent-PC – nie auf deinem Rechner – und können dort Dateien anlegen oder ändern. Öffne das Paket nur, wenn "
        f"du der Quelle vertraust.\n\n{liste}")
    ja = box.addButton("Erlauben und starten", QMessageBox.AcceptRole)
    nein = box.addButton("Abbrechen", QMessageBox.RejectRole)
    box.setDefaultButton(nein)
    box.exec()
    if box.clickedButton() is not ja:
        return False
    kurslauf.zustimmen(paket)
    return True


def agent_pc_einrichten(parent: QWidget, paket: kurspaket.Kurspaket) -> str | None:
    """Selbstlern-Modus: Agent-PC für das Kurspaket wählen oder neu erstellen. Gibt den Namen zurück (oder None)."""
    vorhanden = kurspaket.agent_pc(paket)
    if vorhanden is not None:
        return vorhanden.name
    andere = [m.name for m in vm.list_vms()]
    box = QMessageBox(QMessageBox.Question, paket.name,
                      f"Für „{paket.name}“ brauchst du einen Agent-PC.", QMessageBox.NoButton, parent)
    unbekannt = paket.rezept.unbekannte_apps()
    vorlage = kurspaket.passende_vorlage(paket)
    erklaerung = ("Am besten einen neuen, eigenen Agent-PC nach dem Rezept des Kurspakets – dann kann beim Üben nichts "
                  "an deinen anderen Agent-PCs kaputtgehen.")
    if vorlage:
        erklaerung += f" Er entsteht schnell aus deiner Vorlage „{vorlage}“."
    if unbekannt:
        erklaerung += ("\n\nDiese Programme aus dem Rezept kennt deine Version von Bony's Agents nicht (bitte "
                       f"aktualisieren): {', '.join(unbekannt)}")
    box.setInformativeText(erklaerung)
    neu = box.addButton("Neuen Agent-PC erstellen …", QMessageBox.AcceptRole)
    alt = box.addButton("Vorhandenen verwenden …", QMessageBox.ActionRole) if andere else None
    box.addButton("Abbrechen", QMessageBox.RejectRole)
    box.setDefaultButton(neu)
    box.exec()
    if box.clickedButton() is neu:
        from .create_dialog import CreateDialog

        dlg = CreateDialog(host.detect(), parent, preset_template=vorlage, recipe=paket.rezept.fuer_erstellen(),
                           preset_name=kurspaket.agent_pc_vorschlag(paket))
        dlg.setWindowTitle(f"Neuer Agent-PC für „{paket.name}“")
        if not dlg.exec() or not dlg.created_name:
            return None
        if dlg.hints:
            QMessageBox.warning(parent, paket.name, "\n\n".join(dlg.hints))
        kurspaket.agent_pc_merken(paket, dlg.created_name)
        return dlg.created_name
    if alt is not None and box.clickedButton() is alt:
        name, ok = QInputDialog.getItem(parent, paket.name, "Mit welchem Agent-PC möchtest du das Kurspaket "
                                        "durcharbeiten?", andere, 0, False)
        if ok and name:
            kurspaket.agent_pc_merken(paket, name)
            return name
    return None


class KatalogDialog(QDialog):
    """„Kurspakete aus dem Internet“: Liste aus dem öffentlichen Repo, Laden mit Prüfsumme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kurspakete aus dem Internet")
        self.geladen: list[str] = []
        root = QVBoxLayout(self)
        intro = QLabel(f"Kurspakete aus dem öffentlichen Repository {kurspaket.KATALOG_REPO} auf GitHub. Jede Datei "
                       "wird nach dem Laden mit ihrer Prüfsumme verglichen und vollständig geprüft. Kurspakete "
                       "enthalten nie Zugangsdaten.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Kurspaket", "Stufe", "Dauer", "Version"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        root.addWidget(self.tabelle, 1)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.PlainText)
        root.addWidget(self.text)
        knoepfe = QHBoxLayout()
        self.laden_knopf = QPushButton("Laden")
        self.laden_knopf.setObjectName("Primary")
        self.laden_knopf.setEnabled(False)
        zu = QPushButton("Schließen")
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.laden_knopf)
        knoepfe.addWidget(zu)
        root.addLayout(knoepfe)
        self.resize(640, 420)
        zu.clicked.connect(self.accept)
        self.laden_knopf.clicked.connect(self._laden)
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        self.eintraege: list[kurspaket.KatalogEintrag] = []
        self.text.setText("Lade die Liste …")
        self._lauf(kurspaket.katalog_laden, self._liste)

    def _lauf(self, fn, fertig) -> None:
        w = TaskWorker(fn)
        _RUNNING.add(w)
        w.finished.connect(lambda: (_RUNNING.discard(w), fertig(w)))
        w.start()

    def _liste(self, w: TaskWorker) -> None:
        if w.error is not None:
            self.text.setText(str(w.error))
            return
        lokal = {p.id: p.version for p in kurspaket.liste()}
        self.eintraege = w.result or []
        for e in self.eintraege:
            r = self.tabelle.rowCount()
            self.tabelle.insertRow(r)
            status = ""
            if e.id in lokal:
                status = " (vorhanden)" if kurspaket.version_vergleich(e.version, lokal[e.id]) <= 0 else " (neuer)"
            for i, wert in enumerate([e.name + (" – Entwurf" if e.entwurf else ""), e.stufe_text,
                                      kurspaket.dauer_text(e.dauer_minuten), e.version + status]):
                self.tabelle.setItem(r, i, QTableWidgetItem(wert))
        self.text.setText("Keine Kurspakete gefunden." if not self.eintraege else "")

    def _eintrag(self) -> kurspaket.KatalogEintrag | None:
        rows = self.tabelle.selectionModel().selectedRows()
        return self.eintraege[rows[0].row()] if rows else None

    def _auswahl(self) -> None:
        e = self._eintrag()
        self.laden_knopf.setEnabled(e is not None)
        self.text.setText(e.beschreibung if e else "")

    def _laden(self, ersetzen: bool = False) -> None:
        e = self._eintrag()
        if e is None:
            return
        self.laden_knopf.setEnabled(False)
        self.text.setText(f"Lade „{e.name}“ …")

        def fertig(w: TaskWorker) -> None:
            self.laden_knopf.setEnabled(True)
            if isinstance(w.error, kurspaket.PaketExistiert):
                if QMessageBox.question(self, self.windowTitle(), str(w.error)) == QMessageBox.Yes:
                    self._laden(True)
                else:
                    self.text.setText("")
                return
            if w.error is not None:
                self.text.setText(str(w.error))
                return
            self.geladen.append(w.result.id)
            self.text.setText(f"„{w.result.name}“ ist jetzt in deiner Bibliothek.")

        self._lauf(lambda: kurspaket.herunterladen(e, ersetzen=ersetzen), fertig)


class BibliothekSeite(QWidget):
    """Reiter „Kurspakete“. ``durcharbeiten(paket)`` übernimmt das Hauptfenster (Agent-PC, Anleitung)."""

    def __init__(self, parent=None, durcharbeiten: Callable[[kurspaket.Kurspaket], None] | None = None):
        super().__init__(parent)
        self.durcharbeiten = durcharbeiten
        self.setAcceptDrops(True)
        root = QVBoxLayout(self)
        root.setSpacing(8)
        intro = QLabel(INTRO)
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.fehler = QFrame()
        self.fehler.setObjectName("Hint")
        self.fehler.setProperty("tone", "danger")
        fl = QVBoxLayout(self.fehler)
        self.fehler_text = QLabel()
        self.fehler_text.setWordWrap(True)
        self.fehler_text.setTextFormat(Qt.PlainText)
        fl.addWidget(self.fehler_text)
        root.addWidget(self.fehler)

        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Kurspaket", "Stufe", "Dauer", "Fortschritt"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setWordWrap(False)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabelle.setMinimumHeight(140)
        root.addWidget(self.tabelle, 1)

        self.details = QLabel()
        self.details.setTextFormat(Qt.MarkdownText)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.details)

        knoepfe = QHBoxLayout()
        self.start_knopf = QPushButton("Durcharbeiten")
        self.start_knopf.setObjectName("Primary")
        self.start_knopf.setToolTip("Selbstlern-Modus: eigener Agent-PC, Anleitung daneben, Fortschritt wird gemerkt")
        self.import_knopf = QPushButton("Importieren …")
        self.import_knopf.setToolTip(f"Kurspaket aus einer {kurspaket.SUFFIX}-Datei übernehmen – oder die Datei "
                                     "einfach hierher ziehen")
        self.internet_knopf = QPushButton("Aus dem Internet …")
        self.export_knopf = QPushButton("Exportieren …")
        self.export_knopf.setToolTip(f"Kurspaket als {kurspaket.SUFFIX}-Datei speichern, z. B. zum Weitergeben")
        self.loeschen_knopf = QPushButton("Löschen …")
        for b in (self.import_knopf, self.internet_knopf, self.export_knopf, self.loeschen_knopf):
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.start_knopf)
        root.addLayout(knoepfe)

        self.start_knopf.clicked.connect(self._durcharbeiten)
        self.tabelle.doubleClicked.connect(lambda _i: self._durcharbeiten())
        self.import_knopf.clicked.connect(self._importieren)
        self.internet_knopf.clicked.connect(self._internet)
        self.export_knopf.clicked.connect(self._exportieren)
        self.loeschen_knopf.clicked.connect(self._loeschen)
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        self.pakete: list[kurspaket.Kurspaket] = []
        self.laden()

    # ---------------------------------------------------------------- Liste
    def laden(self, waehlen: str | None = None) -> None:
        vorher = waehlen or (self.paket().id if self.paket() else None)
        bestand = kurspaket.bestand()
        self.pakete = bestand.pakete
        self.fehler.setVisible(bool(bestand.fehler))
        self.fehler_text.setText("Diese Kurspakete in der Bibliothek sind fehlerhaft:\n"
                                 + "\n".join(f"• {o}: {m}" for o, m in bestand.fehler))
        self.tabelle.setRowCount(0)
        for p in self.pakete:
            r = self.tabelle.rowCount()
            self.tabelle.insertRow(r)
            f = kurspaket.Fortschritt.laden(p.id)
            werte = [p.name + ("  (Entwurf)" if p.entwurf else ""), p.stufe_text, p.dauer_text,
                     f.text(p) if p.lektionen else "–"]
            for i, w in enumerate(werte):
                self.tabelle.setItem(r, i, QTableWidgetItem(w))
            if p.id == vorher:
                self.tabelle.selectRow(r)
        if self.pakete and not self.paket():
            self.tabelle.selectRow(0)
        self._auswahl()

    def paket(self) -> kurspaket.Kurspaket | None:
        rows = self.tabelle.selectionModel().selectedRows() if self.tabelle.selectionModel() else []
        return self.pakete[rows[0].row()] if rows and rows[0].row() < len(self.pakete) else None

    def _auswahl(self) -> None:
        p = self.paket()
        self.details.setText(_md_ganz(p) + _vertrauen_text(p) if p else ("Noch keine Kurspakete. Importiere eine "
                                                     f"{kurspaket.SUFFIX}-Datei oder lade eines aus dem Internet."))
        self.start_knopf.setEnabled(p is not None and bool(p.lektionen))
        self.export_knopf.setEnabled(p is not None)
        self.loeschen_knopf.setEnabled(p is not None and not p.mitgeliefert)
        self.loeschen_knopf.setToolTip("Mitgelieferte Kurspakete gehören zum Programm" if p and p.mitgeliefert
                                       else "Kurspaket aus der Bibliothek entfernen")
        if p is not None:
            begonnen = kurspaket.Fortschritt.laden(p.id).begonnen
            self.start_knopf.setText("Fortsetzen" if begonnen else "Durcharbeiten")
            if not p.lektionen:
                self.start_knopf.setToolTip("Dieses Kurspaket hat keine Lektionen zum Durcharbeiten "
                                            "(nur Ablaufplan und Handout)")

    # ---------------------------------------------------------------- Aktionen
    def _durcharbeiten(self) -> None:
        p = self.paket()
        if p is not None and p.lektionen and self.durcharbeiten:
            self.durcharbeiten(p)

    def _importieren(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Kurspaket importieren", str(Path.home()), FILTER)
        if datei:
            self.importieren(Path(datei))

    def importieren(self, quelle: Path) -> None:
        self.import_knopf.setEnabled(False)

        def fertig(paket) -> None:
            self.import_knopf.setEnabled(True)
            self.laden(paket.id if paket else None)

        importieren(self, quelle, fertig)

    def _internet(self) -> None:
        dlg = KatalogDialog(self)
        dlg.exec()
        self.laden(dlg.geladen[-1] if dlg.geladen else None)

    def _exportieren(self) -> None:
        p = self.paket()
        if p is None:
            return
        ziel, _ = QFileDialog.getSaveFileName(self, "Kurspaket exportieren",
                                              str(Path.home() / kurspaket.dateiname(p)), FILTER)
        if not ziel:
            return
        if not ziel.lower().endswith(kurspaket.SUFFIX):
            ziel += kurspaket.SUFFIX
        try:
            kurspaket.packen(p.pfad, Path(ziel))
        except (kurspaket.PaketFehler, OSError) as e:
            QMessageBox.warning(self, "Kurspaket exportieren", str(e))
            return
        QMessageBox.information(self, "Kurspaket exportieren", f"Gespeichert: {ziel}")

    def _loeschen(self) -> None:
        p = self.paket()
        if p is None or p.mitgeliefert:
            return
        box = QMessageBox(QMessageBox.Warning, "Kurspaket löschen", f"„{p.name}“ aus der Bibliothek löschen?",
                          QMessageBox.NoButton, self)
        box.setInformativeText("Der Fortschritt in diesem Kurspaket wird ebenfalls gelöscht. Agent-PCs bleiben "
                               "unverändert.")
        ja = box.addButton("Löschen", QMessageBox.DestructiveRole)
        nein = box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.setDefaultButton(nein)
        box.exec()
        if box.clickedButton() is not ja:
            return
        try:
            kurspaket.loeschen(p.id)
        except (kurspaket.PaketFehler, OSError) as e:
            QMessageBox.warning(self, "Kurspaket löschen", str(e))
        self.laden()

    # ---------------------------------------------------------------- Drag & Drop
    @staticmethod
    def _pfade(e) -> list[Path]:
        md = e.mimeData()
        if not md.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile() and ist_paket(Path(u.toLocalFile()))]

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self._pfade(e):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if self._pfade(e):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        pfade = self._pfade(e)
        if pfade:
            e.acceptProposedAction()
            self.importieren(pfade[0])


def _md_ganz(p: kurspaket.Kurspaket) -> str:
    """Wie ``_paket_text``, aber alle Texte aus dem (fremden) Kurspaket maskiert."""
    sicher = kurspaket.Kurspaket(
        id=p.id, name=_md(p.name), beschreibung=_md(p.beschreibung), stufe=p.stufe, version=p.version,
        autor=_md(p.autor), lizenz=_md(p.lizenz), dauer_minuten=p.dauer_minuten, teilnehmer_min=p.teilnehmer_min,
        teilnehmer_max=p.teilnehmer_max, voraussetzungen=[_md(x) for x in p.voraussetzungen], kosten=_md(p.kosten),
        lernziele=[_md(x) for x in p.lernziele], entwurf=p.entwurf, rezept=p.rezept, lektionen=p.lektionen,
        herkunft=p.herkunft)
    return _paket_text(sicher)
