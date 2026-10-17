# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleitung über das Bony-Netz (nur Kursleiter-Version): Reiter „Kursleitung“ im Fenster „Kurse“.

- Noch kein Kursleiter (``zentrale.instanz()["ist_kursleiter"]``): nur „Kursleiter-Code einlösen“.
- Sonst Kursliste (Name, Status, Teilnehmer, Code; „Beendete anzeigen“), „Neuer Kurs …“ und die Kursansicht mit Code,
  Starten/Pausieren/Beenden, Teilnehmertabelle und „Kursraum öffnen“ (Fenster ``gui/kursraum_fenster.py``).

Liste und Kursansicht fragen die Zentrale alle 15 Sekunden, solange sie zu sehen sind.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from bony_netz import Konto
from bonys_agents import kurse, netz
from bonys_agents.gui.kurse_dialog import (
    Hintergrund, Seite, auswahl, kursraum_oeffnen, nachfragen, tabelle, zeile,
)
from bonys_agents.gui.netz_dialog import _card, _muted, _section
from bonys_agents.gui.share_dialogs import code_style
from bonys_agents.gui.widgets import make_scrollable
from bonys_agents.gui.workers import TaskWorker

FREISCHALTEN_TEXT = ("Kurse anlegen kann eine Instanz erst mit einem Kursleiter-Code. Den Code bekommst du vom "
                     "Betreiber des Servers – einmal einlösen genügt, auch für Bony's VPN.")


class KursleitungSeite(Seite):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kurse: list[kurse.Kurs] = []
        self.kursleiter = Konto.laden().ist_kursleiter   # bis zur ersten Antwort der Zentrale
        self.geladen = False
        self.status_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # Seite 0: Kursleiter-Code einlösen
        page = QWidget()
        p = QVBoxLayout(page)
        p.setContentsMargins(0, 0, 0, 0)
        p.addWidget(_section("Kursleiter-Code einlösen"))
        card, c = _card()
        c.addWidget(_muted(FREISCHALTEN_TEXT))
        row = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("Kursleiter-Code")
        self.code.setMaxLength(100)
        self.redeem_btn = QPushButton("Einlösen")
        self.redeem_btn.setObjectName("Primary")
        row.addWidget(self.code, 1)
        row.addWidget(self.redeem_btn)
        c.addLayout(row)
        p.addWidget(card)
        p.addStretch(1)
        self.stack.addWidget(page)

        # Seite 1: Kursliste
        page = QWidget()
        p = QVBoxLayout(page)
        p.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.new_btn = QPushButton("+  Neuer Kurs …")
        self.new_btn.setObjectName("Primary")
        self.open_btn = QPushButton("Öffnen")
        self.ended = QCheckBox("Beendete anzeigen")
        row.addWidget(self.new_btn)
        row.addWidget(self.open_btn)
        row.addStretch(1)
        row.addWidget(self.ended)
        p.addLayout(row)
        self.table = tabelle(["Kurs", "Status", "Teilnehmer", "Code"])
        p.addWidget(self.table, 1)
        self.empty = _muted("Noch keine Kurse – mit „Neuer Kurs …“ anlegen.")
        p.addWidget(self.empty)
        self.stack.addWidget(page)

        self.status = _muted()
        lay.addWidget(self.status)
        self.stack.setCurrentIndex(1 if self.kursleiter else 0)

        self.redeem_btn.clicked.connect(self._redeem)
        self.code.returnPressed.connect(self._redeem)
        self.code.textChanged.connect(lambda _t: self._update())
        self.new_btn.clicked.connect(self._new)
        self.open_btn.clicked.connect(self._open)
        self.table.doubleClicked.connect(lambda _i: self._open())
        self.table.itemSelectionChanged.connect(self._update)
        self.ended.toggled.connect(lambda _on: self.tick(sofort=True))
        self._update()

    def _update(self) -> None:
        idle = self.bereit and not self.busy
        self.code.setEnabled(idle)
        self.redeem_btn.setEnabled(idle and bool(self.code.text().strip()))
        self.new_btn.setEnabled(idle)
        self.ended.setEnabled(idle)
        self.open_btn.setEnabled(self.bereit and auswahl(self.table) is not None)
        self.empty.setVisible(self.geladen and not self.kurse)
        self.status.setText("Frage den Server …" if self.busy else self.status_text)

    def laden(self) -> None:
        alle = self.ended.isChecked()

        def run():
            kl = kurse.ist_kursleiter()
            return kl, kurse.geleitete_kurse(alle) if kl else []

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = netz.fehlertext(w.error)
                return
            self.kursleiter, self.kurse = w.result
            self.geladen = True
            self.status_text = ""
            self._zeigen()

        self._run(run, done)

    def _zeigen(self) -> None:
        self.stack.setCurrentIndex(1 if self.kursleiter else 0)
        kurs_id = auswahl(self.table)
        self.table.setRowCount(0)
        for k in self.kurse:
            zeile(self.table, [k.name, k.status_text, str(len(k.teilnehmer)), k.code or "–"], k.kurs_id)
            if k.kurs_id == kurs_id:
                self.table.selectRow(self.table.rowCount() - 1)

    def _redeem(self) -> None:
        if not self.redeem_btn.isEnabled():
            return
        code = self.code.text()

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = f"Nicht freigeschaltet: {netz.fehlertext(w.error)}"
                return
            self.code.clear()
            self.kursleiter = True
            self.status_text = "Freigeschaltet – du kannst jetzt Kurse anlegen."
            self.stack.setCurrentIndex(1)
            self.zuletzt = 0.0
            QTimer.singleShot(0, self.tick)

        self._run(lambda: kurse.kursleiter_freischalten(code), done)

    def _new(self) -> None:
        d = NeuerKursDialog(self)
        if d.exec() == QDialog.Accepted and d.kurs is not None:
            self.status_text = f"Kurs „{d.kurs.name}“ angelegt."
            self.kurse = [d.kurs, *self.kurse]
            self._zeigen()
            self._update()
            self._ansicht(d.kurs)

    def _open(self) -> None:
        kurs_id = auswahl(self.table)
        k = next((x for x in self.kurse if x.kurs_id == kurs_id), None)
        if k is not None:
            self._ansicht(k)

    def _ansicht(self, k: kurse.Kurs) -> None:
        KursAnsicht(k, self).exec()
        self.zuletzt = 0.0
        self.tick()


class NeuerKursDialog(QDialog, Hintergrund):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neuer Kurs")
        self.kurs: kurse.Kurs | None = None
        self.fehler = ""
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Neuer Kurs")
        title.setObjectName("Title")
        root.addWidget(title)
        root.addWidget(_muted("Der Kurs bekommt einen Code, mit dem Teilnehmer beitreten. Er startet erst, wenn du "
                              "„Kurs starten“ drückst – vorher erreichst du keine Agent-PCs der Teilnehmer."))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(kurse.NAME_MAX)
        self.name.setPlaceholderText("z. B. Einführung Hermes")
        self.leader = QLineEdit(kurse.gemerkt(kurse.KURSLEITER_NAME))
        self.leader.setMaxLength(kurse.NAME_MAX)
        self.leader.setPlaceholderText("So sehen dich die Teilnehmer")
        self.days = QSpinBox()
        self.days.setRange(kurse.TAGE_MIN, kurse.TAGE_MAX)
        self.days.setValue(kurse.TAGE_STANDARD)
        self.days.setSuffix(" Tage")
        form.addRow("Kursname", self.name)
        form.addRow("Dein Anzeigename", self.leader)
        form.addRow("Code gültig für", self.days)
        root.addLayout(form)
        self.status = _muted()
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.ok_btn = QPushButton("Kurs anlegen")
        self.ok_btn.setObjectName("Primary")
        self.ok_btn.setDefault(True)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.ok_btn)
        root.addLayout(buttons)
        make_scrollable(self, 480)

        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._go)
        self.name.textChanged.connect(lambda _t: self._update())
        self.leader.textChanged.connect(lambda _t: self._update())
        self._update()

    def _update(self) -> None:
        idle = not self.busy
        for w in (self.name, self.leader, self.days, self.cancel_btn):
            w.setEnabled(idle)
        self.ok_btn.setEnabled(idle and bool(self.name.text().strip()) and bool(self.leader.text().strip()))
        self.status.setText("Lege den Kurs an …" if self.busy else self.fehler)

    def _go(self) -> None:
        if not self.ok_btn.isEnabled():
            return
        name, leader, days = self.name.text(), self.leader.text(), self.days.value()

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.fehler = f"Der Kurs wurde nicht angelegt: {netz.fehlertext(w.error)}"
                return
            self.kurs = w.result
            self.accept()

        self._run(lambda: kurse.kurs_anlegen(name, leader, days), done)

    def reject(self) -> None:
        if not self.busy:
            super().reject()


class KursAnsicht(QDialog, Hintergrund):
    """Ein Kurs: Code, Starten/Pausieren/Beenden, Teilnehmer. Alle 15 Sekunden frisch, solange sichtbar."""

    def __init__(self, kurs: kurse.Kurs, parent=None):
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModal)   # der Kursraum (eigenes Fenster) bleibt daneben bedienbar
        self.kurs = kurs
        self.weg = False
        self.status_text = ""
        self.zuletzt = time.monotonic()
        self.setWindowTitle(f"Kurs – {kurs.name}")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        self.title = QLabel()
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        root.addWidget(self.title)
        self.info = _muted()
        root.addWidget(self.info)

        root.addWidget(_section("Kurscode"))
        card, c = _card()
        row = QHBoxLayout()
        self.code = QLabel()
        self.code.setStyleSheet(code_style())
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.copy_btn = QPushButton("Kopieren")
        row.addWidget(self.code, 1)
        row.addWidget(self.copy_btn)
        c.addLayout(row)
        self.valid = _muted()
        c.addWidget(self.valid)
        root.addWidget(card)

        row = QHBoxLayout()
        self.start_btn = QPushButton("Kurs starten")
        self.start_btn.setObjectName("Primary")
        self.pause_btn = QPushButton("Pausieren")
        self.end_btn = QPushButton("Beenden …")
        self.end_btn.setObjectName("Danger")
        self.room_btn = QPushButton("Kursraum öffnen")
        for b in (self.start_btn, self.pause_btn, self.end_btn, self.room_btn):
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)

        root.addWidget(_section("Teilnehmer"))
        self.table = tabelle(["Anzeigename", "Agent-PC", "Netzadresse", "Beigetreten"])
        root.addWidget(self.table, 1)
        self.empty = _muted("Noch niemand beigetreten.")
        root.addWidget(self.empty)
        row = QHBoxLayout()
        self.remove_btn = QPushButton("Entfernen …")
        self.remove_btn.setObjectName("Danger")
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        root.addLayout(row)
        root.addWidget(_muted(kurse.NETZ_HINWEIS))
        self.status = _muted()
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        make_scrollable(self, 640)

        self.copy_btn.clicked.connect(self._copy)
        self.start_btn.clicked.connect(lambda: self._status(kurse.LAEUFT))
        self.pause_btn.clicked.connect(lambda: self._status(kurse.PAUSIERT))
        self.end_btn.clicked.connect(self._end)
        self.room_btn.clicked.connect(lambda: kursraum_oeffnen(self, self.kurs.kurs_id, self.kurs.name))
        self.remove_btn.clicked.connect(self._remove)
        self.table.itemSelectionChanged.connect(self._update)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._zeigen()

    # ---------------------------------------------------------------- Anzeige
    def _zeigen(self) -> None:
        k = self.kurs
        self.title.setText(k.name)
        teil = len(k.teilnehmer)
        self.info.setText(f"Status: {k.status_text} · {teil} Teilnehmer" +
                          (f" · Kursleiter: {k.kursleiter_name}" if k.kursleiter_name else ""))
        self.code.setText(k.code or "–")
        if k.beendet:
            self.valid.setText("Der Kurs ist beendet – mit dem Code tritt niemand mehr bei.")
        else:
            self.valid.setText(f"gültig bis {kurse.datum(k.code_gueltig_bis)}" if k.code_gueltig_bis else "")
        auswahl_id = auswahl(self.table)
        self.table.setRowCount(0)
        for t in k.teilnehmer:
            zeile(self.table, [t.anzeigename, t.geraet_name or "–", t.geraet_ip or "–", kurse.datum(t.beigetreten)],
                  t.instanz_id)
            if t.instanz_id == auswahl_id:
                self.table.selectRow(self.table.rowCount() - 1)
        self.empty.setVisible(not k.teilnehmer)
        self._update()

    def _update(self) -> None:
        k, idle = self.kurs, not self.busy and not self.weg
        self.start_btn.setVisible(k.status in (kurse.OFFEN, kurse.PAUSIERT))
        self.pause_btn.setVisible(k.laeuft)
        self.end_btn.setVisible(not k.beendet)
        self.room_btn.setVisible(k.laeuft)
        for b in (self.start_btn, self.pause_btn, self.end_btn, self.room_btn):
            b.setEnabled(idle)
        self.copy_btn.setEnabled(bool(k.code) and not k.beendet)
        self.remove_btn.setEnabled(idle and not k.beendet and auswahl(self.table) is not None)
        self.status.setText("Frage den Server …" if self.busy else self.status_text)

    # ---------------------------------------------------------------- Hintergrund
    def _tick(self) -> None:
        if self.busy or self.weg or not self.isVisible() \
                or time.monotonic() - self.zuletzt < kurse.KURSANSICHT_SEKUNDEN:
            return
        self.laden()

    def laden(self) -> None:
        self.zuletzt = time.monotonic()
        kurs_id = self.kurs.kurs_id

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = netz.fehlertext(w.error)
                return
            if w.result is None:
                self.weg = True
                self.status_text = "Den Kurs gibt es auf dem Server nicht mehr."
                return
            self.kurs = w.result
            self.status_text = ""
            self._zeigen()

        self._run(lambda: kurse.geleiteter_kurs(kurs_id), done)

    # ---------------------------------------------------------------- Aktionen
    def _copy(self) -> None:
        QApplication.clipboard().setText(self.kurs.code)
        self.status_text = "Kurscode kopiert."
        self._update()

    def _status(self, status: str) -> None:
        kurs_id = self.kurs.kurs_id

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = netz.fehlertext(w.error)
                return
            neu = w.result
            if neu.name == "?":   # Antwort ohne Kurs und frisch holen ging nicht – nur den Status übernehmen
                self.kurs.status = neu.status
            else:
                self.kurs = neu
            self.status_text = {kurse.LAEUFT: "Der Kurs läuft.", kurse.PAUSIERT: "Der Kurs ist pausiert.",
                                kurse.BEENDET: "Der Kurs ist beendet."}[status]
            self._zeigen()
            self.zuletzt = 0.0   # gleich frisch holen (Netzadressen der Teilnehmer)

        self._run(lambda: kurse.status_setzen(kurs_id, status), done)

    def _end(self) -> None:
        if nachfragen(self, "Kurs beenden", f"Kurs „{self.kurs.name}“ beenden?",
                      f"{kurse.BEENDEN_HINWEIS} Der Kurscode gilt danach nicht mehr, und das lässt sich nicht "
                      "rückgängig machen.", "Beenden"):
            self._status(kurse.BEENDET)

    def _remove(self) -> None:
        instanz_id = auswahl(self.table)
        t = next((x for x in self.kurs.teilnehmer if x.instanz_id == instanz_id), None)
        if t is None or not nachfragen(self, "Teilnehmer entfernen", f"„{t.anzeigename}“ aus dem Kurs entfernen?",
                                       "Sein Agent-PC ist danach über diesen Kurs nicht mehr erreichbar.",
                                       "Entfernen"):
            return
        kurs_id = self.kurs.kurs_id

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self.status_text = netz.fehlertext(w.error)
                return
            self.kurs.teilnehmer = [x for x in self.kurs.teilnehmer if x.instanz_id != instanz_id]
            self.status_text = f"„{t.anzeigename}“ entfernt."
            self._zeigen()

        self._run(lambda: kurse.teilnehmer_entfernen(kurs_id, instanz_id), done)

    def done(self, r: int) -> None:
        self.timer.stop()
        super().done(r)
