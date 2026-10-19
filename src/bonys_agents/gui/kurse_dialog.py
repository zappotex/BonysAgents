# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Kurse“ (Knopf „Kurse“ im Kopf): Kurspakete, Kurse über das Bony-Netz – und der Weg zur Schulung im eigenen
Netz.

- Reiter „Kurspakete“ (beide Editionen): Bibliothek der Kurspakete, Selbstlern-Modus (``kurspaket_bibliothek``).
- Reiter „Teilnahme“ (beide Editionen): Kurs mit Kurscode beitreten, Agent-PC wählen, „Meine Kurse“. Hat ein Kurs
  ein Kurspaket, holt die Seite es automatisch in die Bibliothek; „Anleitung“ öffnet es neben dem Agent-PC des Kurses
  und meldet dem Kursleiter nur Lektion und „geschafft / noch nicht“.
- Reiter „Kursleitung“ (nur Kursleiter-Version, ``bonys_agents.trainer.gui.kurse_leiten``).
- „Schulung im Netzwerk beitreten …“ öffnet wie bisher ``JoinDialog`` (LAN/VPN, ohne Internet und Bony-Netz).

Die Logik steht in ``bonys_agents.kurse``; jeder Aufruf der Zentrale läuft in einem TaskWorker. Ist das Bony-Netz aus
oder keine Instanz angemeldet, fragt das Fenster die Zentrale nicht.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from bonys_agents import edition, kurse, kurspaket, netz, share, vm

from .netz_dialog import _card, _muted, _section
from .widgets import make_scrollable
from .workers import TaskWorker

INTRO = ("Kurse über das Internet laufen über das Bony-Netz: Der Kursleiter gibt dir einen Kurscode, du wählst den "
         "Agent-PC, mit dem du teilnimmst. Nur solange der Kurs läuft, erreicht der Kursleiter genau diesen Agent-PC "
         "– nie deinen Rechner und nie andere Teilnehmer. Für eine Schulung im selben Netz (LAN oder VPN) gibt es "
         "weiter „Schulung im Netzwerk beitreten“.")
AUS_TEXT = ("Das Bony-Netz ist ausgeschaltet oder es ist noch keine Instanz angelegt. Kurse über das Internet "
            "brauchen beides.")
KEIN_GERAET = ("Noch kein Agent-PC im Bony-Netz. Beim Erstellen das Häkchen „Bony-Netz“ setzen oder in der Liste "
               "per Rechtsklick „Mit dem Bony-Netz verbinden“.")

# Laufende Aufrufe auch nach dem Schließen des Fensters festhalten (sonst bräche Qt beim Aufräumen ab)
_RUNNING: set[TaskWorker] = set()


def tabelle(spalten: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setWordWrap(False)
    head = t.horizontalHeader()
    head.setSectionResizeMode(QHeaderView.ResizeToContents)
    head.setSectionResizeMode(0, QHeaderView.Stretch)
    t.setMinimumHeight(120)
    return t


def zeile(t: QTableWidget, werte: list[str], daten=None) -> None:
    r = t.rowCount()
    t.insertRow(r)
    for i, w in enumerate(werte):
        item = QTableWidgetItem(w)
        if i == 0 and daten is not None:
            item.setData(Qt.UserRole, daten)
        t.setItem(r, i, item)


def auswahl(t: QTableWidget):
    rows = t.selectionModel().selectedRows() if t.selectionModel() else []
    if not rows:
        return None
    item = t.item(rows[0].row(), 0)
    return item.data(Qt.UserRole) if item else None


def nachfragen(parent, titel: str, text: str, detail: str, ja: str, nein: str = "Abbrechen") -> bool:
    """Rückfrage – „nein“ ist voreingestellt, Enter und Esc ändern also nichts."""
    box = QMessageBox(QMessageBox.Warning, titel, text, QMessageBox.NoButton, parent)
    if detail:
        box.setInformativeText(detail)
    ok = box.addButton(ja, QMessageBox.DestructiveRole)
    keep = box.addButton(nein, QMessageBox.RejectRole)
    box.setDefaultButton(keep)
    box.setEscapeButton(keep)
    box.exec()
    return box.clickedButton() is ok


def kursraum_oeffnen(seite, kurs_id: str, name: str) -> None:
    """Kursraum öffnen (eigenes Fenster); ``seite`` hat ``busy``, ``status_text`` und ``_update`` (Hintergrund)."""
    from .kursraum_fenster import oeffnen

    seite.busy += 1
    seite.status_text = ""
    seite._update()
    seite.status.setText("Hole die Eintrittskarte …")

    def fertig(fehler: str | None) -> None:
        if not isValid(seite):
            return
        seite.busy -= 1
        seite.status_text = f"Kursraum: {fehler}" if fehler else ""
        seite._update()

    oeffnen(kurs_id, name, seite, fertig)


class Hintergrund:
    """Zähler ``busy`` und Aufrufe der Zentrale im TaskWorker; nach jedem Ende ``_update()``."""

    busy = 0

    def _run(self, fn: Callable[[], object], done: Callable[[TaskWorker], None]) -> None:
        w = TaskWorker(fn)
        _RUNNING.add(w)
        self.busy += 1

        def finished() -> None:
            _RUNNING.discard(w)
            if not isValid(self):   # Fenster inzwischen geschlossen
                return
            self.busy -= 1
            try:
                done(w)
            finally:
                self._update()

        w.finished.connect(finished)
        self._update()
        w.start()

    def _update(self) -> None:
        raise NotImplementedError


class Seite(QWidget, Hintergrund):
    """Reiter im Fenster „Kurse“: lädt beim Zeigen und danach höchstens alle ``intervall`` Sekunden."""

    intervall = kurse.KURSANSICHT_SEKUNDEN

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zuletzt = 0.0
        self.bereit = False

    def tick(self, sofort: bool = False) -> None:
        if not self.bereit or self.busy or not self.isVisible():
            return
        if sofort or time.monotonic() - self.zuletzt >= self.intervall:
            self.zuletzt = time.monotonic()
            self.laden()

    def laden(self) -> None:
        raise NotImplementedError


def _lokale_namen() -> dict[str, str]:
    """Netzname → Name des Agent-PCs auf diesem Rechner."""
    namen = {}
    for m in vm.list_vms():
        cfg = getattr(m, "config", None)
        if cfg is not None and getattr(cfg, "netz_name", ""):
            namen[cfg.netz_name] = m.name
    return namen


def geraet_text(g: dict, lokal: dict[str, str]) -> str:
    name = str(g.get("name") or "?")
    eigen = lokal.get(name)
    text = name + (f" („{eigen}“)" if eigen and eigen != name else "")
    return text + (" · online" if g.get("online") else " · offline")


class TeilnahmeSeite(Seite):
    """Teilnehmer: Kurs beitreten und „Meine Kurse“."""

    intervall = kurse.TEILNAHMEN_SEKUNDEN

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kurse: list[kurse.Kurs] = []
        self.geraete: list[dict] = []
        self.lokal: dict[str, str] = {}
        self.status_text = ""
        self.geladen = False
        self.paket_fehler: dict[str, str] = {}      # kurs_id → warum das Kurspaket nicht geholt werden konnte
        # (Kurspaket, kurs_id, Name des Agent-PCs hier oder "") – setzt das Fenster „Kurse“
        self.anleitung_oeffnen: Callable[[kurspaket.Kurspaket, str, str], None] | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(_section("Kurs beitreten"))
        card, c = _card()
        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("z. B. K7QX-M3PA")
        self.code.setMaxLength(20)
        self.geraet = QComboBox()
        self.geraet.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.geraet.setMinimumContentsLength(16)
        self.name = QLineEdit(kurse.gemerkt(kurse.ANZEIGENAME) or share._client_name())
        self.name.setMaxLength(kurse.NAME_MAX)
        self.name.setPlaceholderText("So sieht dich der Kursleiter")
        form.addRow("Kurscode", self.code)
        form.addRow("Agent-PC", self.geraet)
        form.addRow("Dein Name", self.name)
        c.addLayout(form)
        self.geraet_hint = _muted()
        c.addWidget(self.geraet_hint)
        row = QHBoxLayout()
        row.addStretch(1)
        self.join_btn = QPushButton("Beitreten")
        self.join_btn.setObjectName("Primary")
        row.addWidget(self.join_btn)
        c.addLayout(row)
        lay.addWidget(card)

        lay.addWidget(_section("Meine Kurse"))
        self.table = tabelle(["Kurs", "Kursleiter", "Status", "Agent-PC", "Kurspaket"])
        lay.addWidget(self.table)
        self.empty = _muted("Du nimmst an keinem Kurs teil.")
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        self.room_btn = QPushButton("Kursraum betreten")
        self.room_btn.setToolTip("Nur, solange der Kurs läuft")
        self.anleitung_btn = QPushButton("Anleitung")
        self.anleitung_btn.setToolTip("Das Kurspaket des Kurses neben deinem Agent-PC öffnen – der Kursleiter sieht "
                                      "nur deine Lektion und ob die Prüfaufgabe geschafft ist")
        self.leave_btn = QPushButton("Kurs verlassen …")
        self.leave_btn.setObjectName("Danger")
        row.addWidget(self.room_btn)
        row.addWidget(self.anleitung_btn)
        row.addWidget(self.leave_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = _muted()
        lay.addWidget(self.status)

        self.join_btn.clicked.connect(self._join)
        self.code.returnPressed.connect(self._join)
        self.room_btn.clicked.connect(self._room)
        self.anleitung_btn.clicked.connect(self._anleitung)
        self.leave_btn.clicked.connect(self._leave)
        self.table.itemSelectionChanged.connect(self._update)
        self.code.textChanged.connect(lambda _t: self._update())
        self._update()

    def _kurs(self) -> kurse.Kurs | None:
        kurs_id = auswahl(self.table)
        return next((k for k in self.kurse if k.kurs_id == kurs_id), None)

    def _update(self) -> None:
        idle = self.bereit and not self.busy
        for w in (self.code, self.geraet, self.name):
            w.setEnabled(idle)
        self.join_btn.setEnabled(idle and bool(self.code.text().strip()) and self.geraet.currentData() is not None)
        k = self._kurs()
        self.room_btn.setEnabled(idle and k is not None and k.laeuft)
        self.anleitung_btn.setEnabled(idle and k is not None and k.kurspaket is not None)
        self.leave_btn.setEnabled(idle and k is not None)
        self.empty.setVisible(self.geladen and not self.kurse)
        self.status.setText("Frage den Server …" if self.busy else self.status_text)

    def laden(self) -> None:
        def run():
            geraete, teilnahmen = kurse.eigene_geraete(), kurse.teilnahmen()
            fehler = {}
            for k in teilnahmen:   # Kurspakete automatisch in die Bibliothek holen
                if k.kurspaket is not None:
                    try:
                        kurse.kurspaket_fuer_kurs(k)
                    except Exception as e:  # noqa: BLE001 – nur anzeigen, die Liste soll trotzdem kommen
                        fehler[k.kurs_id] = netz.fehlertext(e)
            return geraete, teilnahmen, _lokale_namen(), fehler

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = netz.fehlertext(w.error)
                return
            self.geraete, self.kurse, self.lokal, self.paket_fehler = w.result
            self.geladen = True
            self.status_text = next((f"Kurspaket von „{k.name}“ nicht geholt: {self.paket_fehler[k.kurs_id]}"
                                     for k in self.kurse if k.kurs_id in self.paket_fehler), "")
            self._zeigen()

        self._run(run, done)

    def _zeigen(self) -> None:
        gewaehlt = self.geraet.currentData()
        self.geraet.clear()
        for g in self.geraete:
            self.geraet.addItem(geraet_text(g, self.lokal), str(g["geraet_id"]))
        i = self.geraet.findData(gewaehlt) if gewaehlt is not None else -1
        self.geraet.setCurrentIndex(max(i, 0) if self.geraete else -1)
        self.geraet_hint.setText("" if self.geraete else KEIN_GERAET)
        self.geraet_hint.setVisible(not self.geraete)

        namen = {str(g["geraet_id"]): str(g.get("name") or "") for g in self.geraete}
        kurs_id = auswahl(self.table)
        self.table.setRowCount(0)
        for k in self.kurse:
            netzname = namen.get(k.mein_geraet_id, "")
            pc = self.lokal.get(netzname) or netzname or "–"
            zeile(self.table, [k.name, k.kursleiter_name or "–", k.status_text, pc,
                               k.kurspaket.name if k.kurspaket else "–"], k.kurs_id)
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == kurs_id:
                self.table.selectRow(r)

    def _join(self) -> None:
        if not self.join_btn.isEnabled():
            return
        code, geraet_id, name = self.code.text(), self.geraet.currentData(), self.name.text()

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = f"Nicht beigetreten: {netz.fehlertext(w.error)}"
                return
            self.code.clear()
            self.status_text = f"Beigetreten: „{w.result.name}“." if w.result.kurs_id else "Beigetreten."
            self.zuletzt = 0.0
            QTimer.singleShot(0, self.tick)

        self._run(lambda: kurse.kurs_beitreten(code, geraet_id, name), done)

    def _room(self) -> None:
        k = self._kurs()
        if k is not None and k.laeuft:
            kursraum_oeffnen(self, k.kurs_id, k.name)

    def _agent_pc_hier(self, k: kurse.Kurs) -> str:
        """Name des Agent-PCs, mit dem du am Kurs teilnimmst – wenn er auf diesem Rechner liegt, sonst ""."""
        netzname = next((str(g.get("name") or "") for g in self.geraete if str(g["geraet_id"]) == k.mein_geraet_id),
                        "")
        return self.lokal.get(netzname, "") if netzname else ""

    def _anleitung(self) -> None:
        k = self._kurs()
        if k is None or k.kurspaket is None:
            return
        pc = self._agent_pc_hier(k)

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = f"Kurspaket nicht geholt: {netz.fehlertext(w.error)}"
                return
            self.status_text = ""
            if self.anleitung_oeffnen is not None:
                self.anleitung_oeffnen(w.result, k.kurs_id, pc)

        self.status_text = ""
        self._run(lambda: kurse.kurspaket_fuer_kurs(k), done)
        self.status.setText("Hole das Kurspaket …")

    def _leave(self) -> None:
        k = self._kurs()
        if k is None or not nachfragen(
                self, "Kurs verlassen", f"Kurs „{k.name}“ verlassen?",
                "Der Kursleiter erreicht deinen Agent-PC danach nicht mehr über diesen Kurs.", "Verlassen"):
            return

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = f"Nicht verlassen: {netz.fehlertext(w.error)}"
                return
            self.status_text = f"„{k.name}“ verlassen."
            self.kurse = [x for x in self.kurse if x.kurs_id != k.kurs_id]
            self._zeigen()

        self._run(lambda: kurse.kurs_verlassen(k.kurs_id), done)


class KurseDialog(QDialog):
    def __init__(self, parent=None, join_local: Callable[[], None] | None = None,
                 durcharbeiten: Callable[[kurspaket.Kurspaket], None] | None = None,
                 im_kurs: Callable[[kurspaket.Kurspaket, str, str], None] | None = None):
        super().__init__(parent)
        self.durcharbeiten = durcharbeiten
        self.im_kurs = im_kurs
        self.setWindowModality(Qt.WindowModal)   # sperrt nur das Hauptfenster, nicht den Kursraum
        self.setWindowTitle("Kurse")
        self.join_local = join_local
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Kurse")
        title.setObjectName("Title")
        root.addWidget(title)
        self.intro = _muted(INTRO)
        root.addWidget(self.intro)

        self.off = QFrame()
        self.off.setObjectName("Hint")
        row = QHBoxLayout(self.off)
        text = QLabel(AUS_TEXT)
        text.setWordWrap(True)
        self.netz_btn = QPushButton("Bony-Netz …")
        row.addWidget(text, 1)
        row.addWidget(self.netz_btn)
        root.addWidget(self.off)

        self.tabs = QTabWidget()
        self.seiten: list[Seite] = []
        from .kurspaket_bibliothek import BibliothekSeite

        self.pakete = BibliothekSeite(self, durcharbeiten=self._durcharbeiten if durcharbeiten else None)
        self.tabs.addTab(self.pakete, "Kurspakete")
        if edition.IS_TRAINER:
            from bonys_agents.trainer.gui.kurse_leiten import KursleitungSeite

            self.leitung = KursleitungSeite(self)
            self.tabs.addTab(self.leitung, "Kursleitung")
            self.seiten.append(self.leitung)
        self.teilnahme = TeilnahmeSeite(self)
        self.teilnahme.anleitung_oeffnen = self._im_kurs
        self.tabs.addTab(self.teilnahme, "Teilnahme")
        self.seiten.append(self.teilnahme)
        root.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.local_btn = QPushButton("Schulung im Netzwerk beitreten …")
        self.local_btn.setToolTip("Vorlage vom Rechner des Kursleiters laden bzw. seine Vorführung öffnen – im "
                                  "selben Netz oder per VPN, ohne Bony-Netz")
        buttons.addWidget(self.local_btn)
        buttons.addStretch(1)
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        make_scrollable(self, 660)

        # Wie bisher auf den Kursen über das Bony-Netz öffnen – ohne Bony-Netz auf den Kurspaketen
        if netz.bereit() and self.seiten:
            self.tabs.setCurrentWidget(self.seiten[0])
        self.netz_btn.clicked.connect(self._netz)
        self.local_btn.clicked.connect(self._local)
        self.tabs.currentChanged.connect(lambda _i: (self._hinweise(), self._tick()))
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self._bereit()

    def _durcharbeiten(self, paket: kurspaket.Kurspaket) -> None:
        """Selbstlern-Modus: Fenster schließen (es sperrt das Hauptfenster), dann übernimmt das Hauptfenster."""
        self.accept()
        QTimer.singleShot(0, lambda: self.durcharbeiten(paket))

    def _im_kurs(self, paket: kurspaket.Kurspaket, kurs_id: str, agent_pc: str) -> None:
        """Anleitung im Kurs: wie „Durcharbeiten“ erst dieses Fenster schließen, dann übernimmt das Hauptfenster."""
        if self.im_kurs is None:
            from .kurspaket_anleitung import oeffnen

            oeffnen(paket, melden=lambda i, g: kurse.fortschritt_melden(kurs_id, i, g))
            return
        self.accept()
        QTimer.singleShot(0, lambda: self.im_kurs(paket, kurs_id, agent_pc))

    def _hinweise(self) -> None:
        """Erklärung und „Bony-Netz aus“ gehören nur zu den Reitern der Kurse über das Bony-Netz."""
        netz_reiter = isinstance(self.tabs.currentWidget(), Seite)
        self.intro.setVisible(netz_reiter)
        self.off.setVisible(netz_reiter and not netz.bereit())

    def _bereit(self) -> None:
        on = netz.bereit()
        self._hinweise()
        for s in self.seiten:
            s.bereit = on
            s._update()
        if on:
            self.timer.start()
            QTimer.singleShot(0, self._tick)
        else:
            self.timer.stop()

    def _tick(self) -> None:
        s = self.tabs.currentWidget()
        if isinstance(s, Seite) and self.isVisible():
            s.tick()

    def _netz(self) -> None:
        from .netz_dialog import NetzDialog

        NetzDialog(self).exec()
        for s in self.seiten:
            s.zuletzt = 0.0
        self._bereit()

    def _local(self) -> None:
        if self.join_local:
            self.join_local()
        else:
            from .share_dialogs import JoinDialog

            JoinDialog(self).exec()

    def done(self, r: int) -> None:
        self.timer.stop()
        super().done(r)
