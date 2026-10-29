# SPDX-License-Identifier: GPL-3.0-or-later
"""Hilfe-Funktion beim Teilnehmer (Aufgabe 06, beide Editionen): Rückfrage, Bildschirmfreigabe, Hinweis mit „Beenden“.

``TeilnehmerHilfe`` gehört zum Kursraum-Fenster (``gui/kursraum_fenster.py``): Die Seite reicht ``hilfe-anfrage``
und ``hilfe-ende`` des Kursleiters herein, alles Weitere entscheidet diese Klasse – die Logik ohne Qt steht in
``bonys_agents.hilfe``.

- Jede Anfrage fragt neu (``Zustimmung``): „Nur ansehen“, „Ansehen und bedienen“, „Ablehnen“; nach 60 s ohne
  Antwort gilt „Ablehnen“. Läuft schon eine Hilfe, wird eine weitere Anfrage abgelehnt.
- Solange x11vnc läuft, steht ``Hinweis`` über allen Fenstern: „<Kursleiter> sieht gerade deinen Agenten-PC …“
  mit „Beenden“ (stoppt x11vnc sofort). Dasselbe passiert, wenn der Kurs nicht mehr läuft (alle 15 s gefragt), der
  Kursraum verlassen wird oder x11vnc von selbst endet (Kursleiter hat getrennt, 2 min ohne Verbindung, 30 min um).
- Im Protokoll beim Teilnehmer steht, wann wer zugesehen hat (``helpmode.log_file``, ohne Bildinhalte).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from bonys_agents import helpmode, hilfe, netz
from bonys_agents.i18n import tr

from . import style
from .workers import TaskWorker

PRUEFEN_SEKUNDEN = 3        # läuft x11vnc noch?
KURS_SEKUNDEN = 15          # läuft der Kurs noch?
_RUNNING: set[TaskWorker] = set()
# Fenster ohne Elternfenster bis zum Löschen durch Qt festhalten: Fiele die letzte Python-Referenz weg, während noch
# ihr eigener Timer oder closeEvent läuft, würde Python sie mitten darin löschen (Absturz).
_OFFEN: set[QWidget] = set()


def festhalten(fenster: QWidget) -> None:
    _OFFEN.add(fenster)
    fenster.destroyed.connect(lambda *_: _OFFEN.discard(fenster))


def passend_hoch(fenster: QWidget, breite: int) -> None:
    """Feste Breite, Höhe passend zum umgebrochenen Text – ``sizeHint`` rechnet mit der breiteren Wunschbreite,
    bei ``breite`` wären die Texte dann unten abgeschnitten."""
    fenster.ensurePolished()
    fenster.resize(breite, max(fenster.sizeHint().height(), fenster.heightForWidth(breite)))


def _laufen(fn, fertig=None) -> None:
    """Im Hintergrund – unabhängig vom Fenster (Beenden muss auch nach dem Schließen des Kursraums durchlaufen)."""
    w = TaskWorker(fn)
    _RUNNING.add(w)

    def ende() -> None:
        _RUNNING.discard(w)
        if fertig is not None:
            fertig(w)

    w.finished.connect(ende)
    w.start()


def _fehlertext(e: BaseException) -> str:
    return str(e) if isinstance(e, hilfe.HilfeFehler) else netz.fehlertext(e)


class Zustimmung(QDialog):
    """Deutliche Rückfrage – jedes Mal neu. ``antwort`` liefert ANSEHEN, BEDIENEN oder "" (abgelehnt)."""

    antwort = Signal(str)

    def __init__(self, kursleiter: str, pc: str, sekunden: int = hilfe.ANTWORT_SEKUNDEN):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(tr("Hilfe-Anfrage des Kursleiters"))
        self.setAttribute(Qt.WA_DeleteOnClose)
        festhalten(self)
        self.rest = sekunden
        self.gemeldet = False
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        frage = QLabel(tr("{kursleiter} möchte deinen Agenten-PC „{pc}“ sehen und "
                          "bedienen. Erlauben?", kursleiter=kursleiter, pc=pc))
        frage.setObjectName("Title")
        frage.setWordWrap(True)
        lay.addWidget(frage)
        info = QLabel(tr("„Nur ansehen“: Der Kursleiter sieht den "
                         "Bildschirm dieses Agent-PCs, kann aber "
                         "nichts eingeben.\n„Ansehen und bedienen“: Er "
                         "kann auch Maus und Tastatur benutzen.\n\nEr "
                         "sieht nur diesen Agent-PC – nie deinen "
                         "übrigen Bildschirm. Du kannst jederzeit "
                         "beenden, nach spätestens "
                         "{HOECHSTENS_MINUTEN} Minuten endet die Hilfe "
                         "von selbst.", HOECHSTENS_MINUTEN=hilfe.HOECHSTENS_MINUTEN))
        info.setWordWrap(True)
        lay.addWidget(info)
        self.uhr_text = QLabel()
        self.uhr_text.setStyleSheet(f"color: {style.MUTED};")
        lay.addWidget(self.uhr_text)
        row = QHBoxLayout()
        self.nein = QPushButton(tr("Ablehnen"))
        self.ansehen = QPushButton(tr("Nur ansehen"))
        self.bedienen = QPushButton(tr("Ansehen und bedienen"))
        self.bedienen.setObjectName("Danger")
        for b in (self.ansehen, self.bedienen):
            b.setAutoDefault(False)
        self.nein.setDefault(True)   # Enter und Esc erlauben nie etwas
        row.addWidget(self.nein)
        row.addStretch(1)
        row.addWidget(self.ansehen)
        row.addWidget(self.bedienen)
        lay.addLayout(row)
        self.nein.clicked.connect(lambda: self._fertig(""))
        self.ansehen.clicked.connect(lambda: self._fertig(hilfe.ANSEHEN))
        self.bedienen.clicked.connect(lambda: self._fertig(hilfe.BEDIENEN))
        self.uhr = QTimer(self)
        self.uhr.setInterval(1000)
        self.uhr.timeout.connect(self._ticken)
        self.uhr.start()
        self._zeigen()
        passend_hoch(self, 520)

    def _zeigen(self) -> None:
        self.uhr_text.setText(tr("Ohne Antwort wird die Anfrage in {rest} Sekunden abgelehnt.", rest=self.rest))

    def _ticken(self) -> None:
        self.rest -= 1
        if self.rest <= 0:
            self._fertig("")
        else:
            self._zeigen()

    def _fertig(self, modus: str) -> None:
        if not self.gemeldet:
            self.gemeldet = True
            self.uhr.stop()
            self.antwort.emit(modus)
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 – Schließen = Ablehnen
        if not self.gemeldet:
            self.gemeldet = True
            self.uhr.stop()
            self.antwort.emit("")
        super().closeEvent(event)

    def reject(self) -> None:
        self._fertig("")


class Hinweis(QWidget):
    """Auffälliger Hinweis über allen Fenstern, solange der Kursleiter zusehen kann – mit „Beenden“."""

    beenden = Signal()

    def __init__(self, kursleiter: str, pc: str, modus: str):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(tr("Hilfe läuft"))
        self.setAttribute(Qt.WA_DeleteOnClose)
        festhalten(self)
        self.ende = time.monotonic() + hilfe.HOECHSTENS_MINUTEN * 60
        self.zu = False
        farbe = style.DANGER if modus == hilfe.BEDIENEN else style.WARN
        rahmen = QFrame(self)
        rahmen.setObjectName("HilfeHinweis")
        rahmen.setStyleSheet(f"QFrame#HilfeHinweis {{ background: {farbe}; border-radius: 8px; }} "
                             "QFrame#HilfeHinweis QLabel { color: #111; }")
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(rahmen)
        lay = QHBoxLayout(rahmen)
        lay.setContentsMargins(16, 12, 16, 12)
        texte = QVBoxLayout()
        self.text = QLabel(self.text_fuer(kursleiter, pc, modus))
        self.text.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.text.setWordWrap(True)
        texte.addWidget(self.text)
        self.zeit = QLabel()
        texte.addWidget(self.zeit)
        lay.addLayout(texte, 1)
        self.knopf = QPushButton(tr("Beenden"))
        self.knopf.setMinimumWidth(110)
        self.knopf.setStyleSheet("QPushButton { background: #111; color: #fff; font-weight: bold; padding: 8px 16px; "
                                 "border-radius: 6px; } QPushButton:hover { background: #333; }")
        lay.addWidget(self.knopf)
        self.knopf.clicked.connect(self._beenden)
        self.uhr = QTimer(self)
        self.uhr.setInterval(1000)
        self.uhr.timeout.connect(self._zeit)
        self.uhr.start()
        self._zeit()
        passend_hoch(self, 560)
        bildschirm = QApplication.primaryScreen()
        if bildschirm is not None:
            g = bildschirm.availableGeometry()
            self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 24)

    @staticmethod
    def text_fuer(kursleiter: str, pc: str, modus: str) -> str:
        if modus == hilfe.BEDIENEN:
            return tr("{kursleiter} sieht gerade deinen Agenten-PC „{pc}“ und kann ihn bedienen.",
                      kursleiter=kursleiter, pc=pc)
        return tr("{kursleiter} sieht gerade deinen Agenten-PC „{pc}“.", kursleiter=kursleiter, pc=pc)

    def _zeit(self) -> None:
        rest = max(0, int(self.ende - time.monotonic()))
        self.zeit.setText(tr("Endet spätestens in {wert}:{wert2:02d} min – "
                             "„Beenden“ trennt sofort.", wert=rest // 60, wert2=rest % 60))

    def _beenden(self) -> None:
        self.knopf.setEnabled(False)
        self.knopf.setText(tr("Beende …"))
        self.beenden.emit()

    def schliessen(self) -> None:
        self.zu = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 – Fenster zu = Beenden
        if not self.zu:
            self.zu = True
            self.beenden.emit()
        super().closeEvent(event)


FRAGE, STARTET, AKTIV = "frage", "startet", "aktiv"


class TeilnehmerHilfe(QObject):
    """Hilfe-Funktion beim Teilnehmer – eine Hilfe zur Zeit."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.fenster = fenster                   # KursraumFenster
        self.kurs_id = fenster.karte.kurs_id
        self.kursname = fenster.kursname
        self.zustand: str | None = None
        self.abbrechen = False                   # während des Starts beendet (Kursraum zu, Kurs pausiert …)
        self.machine = None
        self.anfrage_id = ""
        self.leiter_id = ""
        self.leiter_name = ""
        self.von = ""                            # Adresse des Kursleiter-Rechners – nur sie darf sich verbinden
        self.modus = ""
        self.dialog: Zustimmung | None = None
        self.hinweis: Hinweis | None = None
        self.pruefen_laeuft = False
        self.kurs_zuletzt = 0.0
        self.uhr = QTimer(self)
        self.uhr.setInterval(PRUEFEN_SEKUNDEN * 1000)
        self.uhr.timeout.connect(self._pruefen)

    # ---------------------------------------------------------------- an die Seite
    def _senden(self, thema: str, daten: dict) -> None:
        if isValid(self.fenster) and self.leiter_id:
            self.fenster.an_seite({"aktion": "senden", "thema": thema, "daten": daten, "an": [self.leiter_id]})

    def _seite(self, daten: dict) -> None:
        if isValid(self.fenster):
            self.fenster.an_seite(daten)

    def _absage(self, anfrage_id: str, leiter_id: str, grund: str = "") -> None:
        if isValid(self.fenster):
            daten = {"id": anfrage_id, **({"grund": grund} if grund else {})}
            self.fenster.an_seite({"aktion": "senden", "thema": hilfe.ABSAGE, "daten": daten, "an": [leiter_id]})

    def _melden(self, text: str) -> None:
        parent = self.fenster if isValid(self.fenster) else None
        box = QMessageBox(QMessageBox.Warning, tr("Hilfe"), text, QMessageBox.Ok, parent)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.setWindowModality(Qt.NonModal)
        box.show()

    # ---------------------------------------------------------------- von der Seite
    def anfrage(self, d: dict) -> None:
        anfrage_id, leiter_id = str(d.get("id") or "")[:64], d["identity"]
        # Nur der Kursleiter laut Zentrale (Identität in seiner Karte) darf fragen – nie jemand, der sich nur so nennt
        leiter = getattr(self.fenster.karte, "leiter", "")
        if not anfrage_id or not leiter or leiter_id != leiter:
            return
        von = d.get("von")
        self.von = von if isinstance(von, str) and hilfe.im_netz(von) else ""
        if self.zustand is not None:
            self._absage(anfrage_id, leiter_id, tr("Gerade läuft schon eine Hilfe-Anfrage."))
            return
        self.zustand, self.abbrechen = FRAGE, False
        self.anfrage_id, self.leiter_id = anfrage_id, leiter_id
        self.leiter_name = str(d.get("name") or "Der Kursleiter")[:80]
        kurs_id = self.kurs_id

        def finden():
            m = hilfe.agent_pc(kurs_id)
            hilfe._bereit(m)
            return m

        def gefunden(w: TaskWorker) -> None:
            if not isValid(self):
                return
            if self.zustand != FRAGE or self.abbrechen:   # inzwischen Kursraum verlassen
                if self.zustand == FRAGE:
                    self._absage(anfrage_id, leiter_id, "Der Kursraum wurde inzwischen verlassen.")
                    self.zustand = None
                return
            if w.error is not None:
                text = _fehlertext(w.error)
                self._absage(anfrage_id, leiter_id, tr("Hilfe geht gerade nicht: {inhalt}", inhalt=text))
                self.zustand = None
                self._melden(tr("{leiter_name} wollte deinen Agent-PC sehen – das geht gerade nicht:\n\n{inhalt}",
                                leiter_name=self.leiter_name, inhalt=text))
                return
            self.machine = w.result
            QApplication.alert(self.fenster, 0)
            self.dialog = Zustimmung(self.leiter_name, self.machine.name)
            self.dialog.antwort.connect(self._antwort)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()

        _laufen(finden, gefunden)

    def _antwort(self, modus: str) -> None:
        self.dialog = None
        if self.zustand != FRAGE:
            return
        if not modus or self.abbrechen:
            grund = "" if not modus else "Der Kursraum wurde inzwischen verlassen."
            if not modus and not self.abbrechen:
                helpmode.log_event(self.kursname, self.machine.name, tr("Hilfe-Anfrage von {leiter_name} abgelehnt",
                                                                        leiter_name=self.leiter_name))
            self._absage(self.anfrage_id, self.leiter_id, grund)
            self.zustand = None
            return
        self.zustand, self.modus = STARTET, modus
        machine = self.machine

        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                if w.error is None:
                    _laufen(lambda: hilfe.beenden(machine))
                return
            if w.error is not None:
                text = _fehlertext(w.error)
                self._absage(self.anfrage_id, self.leiter_id, tr("Hilfe geht gerade nicht: {inhalt}", inhalt=text))
                self.zustand = None
                self._melden(tr("Die Bildschirmfreigabe ließ sich nicht starten:\n\n{inhalt}", inhalt=text))
                return
            if self.abbrechen:   # inzwischen Kursraum verlassen oder Kurs pausiert
                _laufen(lambda: hilfe.beenden(machine))
                self._absage(self.anfrage_id, self.leiter_id, "Die Hilfe wurde inzwischen beendet.")
                self.zustand = None
                return
            self._aktiv(w.result)

        von = self.von
        _laufen(lambda: hilfe.starten(machine, modus, von=von), fertig)

    def _aktiv(self, freigabe: hilfe.Freigabe) -> None:
        self.zustand = AKTIV
        self._senden(hilfe.ZUSAGE, freigabe.nachricht(self.anfrage_id, self.machine.name))
        helpmode.log_event(self.kursname, self.machine.name,
                           f"{self.leiter_name}: {hilfe.MODUS_TEXT[self.modus]} erlaubt (Bony-Netz)")
        self.hinweis = Hinweis(self.leiter_name, self.machine.name, self.modus)
        self.hinweis.beenden.connect(lambda: self.beenden("Du hast die Hilfe beendet."))
        self.hinweis.show()
        self._seite({"aktion": "banner", "text": Hinweis.text_fuer(self.leiter_name, self.machine.name, self.modus)})
        self.kurs_zuletzt = time.monotonic()
        self.uhr.start()

    def ende(self, d: dict) -> None:
        """Der Kursleiter hat den Betrachter geschlossen."""
        if d.get("identity") == self.leiter_id:
            self.beenden(tr("Der Kursleiter hat die Hilfe beendet."), melden=False)

    def raum_getrennt(self) -> None:
        self.beenden("Der Kursraum wurde verlassen.", melden=False)

    # ---------------------------------------------------------------- Beenden
    def beenden(self, grund: str, melden: bool = True) -> None:
        if self.zustand is None:
            return
        if self.zustand == FRAGE:
            self.abbrechen = True
            if self.dialog is not None and isValid(self.dialog):
                self.dialog.close()   # → _antwort("") → Absage
            return
        if self.zustand == STARTET:
            self.abbrechen = True     # fertig() stoppt gleich wieder
            return
        self.zustand = None
        self.uhr.stop()
        machine = self.machine
        _laufen(lambda: hilfe.beenden(machine))
        if self.hinweis is not None and isValid(self.hinweis):
            self.hinweis.schliessen()
        self.hinweis = None
        self._seite({"aktion": "banner", "text": ""})
        self._senden(hilfe.ENDE, {"id": self.anfrage_id})
        helpmode.log_event(self.kursname, machine.name, f"Hilfe beendet: {grund}")
        if melden and grund != "Du hast die Hilfe beendet.":
            self._seite({"aktion": "hinweis", "text": grund})

    def _pruefen(self) -> None:
        if self.zustand != AKTIV or self.pruefen_laeuft:
            return
        self.pruefen_laeuft = True
        machine, kurs_id = self.machine, self.kurs_id
        kurs_auch = time.monotonic() - self.kurs_zuletzt >= KURS_SEKUNDEN
        if kurs_auch:
            self.kurs_zuletzt = time.monotonic()

        def run():
            laeuft = hilfe.aktiv(machine)
            kurs = None
            if kurs_auch and laeuft is not False:
                try:
                    kurs = hilfe.kurs_laeuft(kurs_id)
                except Exception:  # noqa: BLE001 – Zentrale gerade nicht erreichbar: weiter, x11vnc endet ohnehin
                    kurs = None
            return laeuft, kurs

        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                return
            self.pruefen_laeuft = False
            if self.zustand != AKTIV or w.error is not None:
                return
            laeuft, kurs = w.result
            if laeuft is False:
                self.beenden(tr("Die Bildschirmfreigabe ist zu Ende (getrennt oder Zeit abgelaufen)."))
            elif kurs is False:
                self.beenden(tr("Der Kurs ist pausiert oder beendet – die Hilfe ist vorbei."))

        _laufen(run, fertig)
