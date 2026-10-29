# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Bony-Netz“ (Menü → „Bony-Netz …“): Schalter, Server, Instanz und Zustand.

Die Logik steht in ``bonys_agents.netz``; jeder Aufruf der Zentrale läuft in einem TaskWorker, währenddessen sind
die Knöpfe gesperrt. Ist der Schalter aus, fragt das Fenster die Zentrale nicht.
"""

from __future__ import annotations

import html
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from bony_netz import STANDARD_SERVER, Konto
from bony_netz.konto import server_normalisieren
from bonys_agents import APP_NAME, kurspaket, netz
from bonys_agents.i18n import n_, tr

from .widgets import confirm_delete, make_scrollable, open_url
from .workers import TaskWorker

INTRO = n_("Über das Bony-Netz verbinden sich deine Agent-PCs übers Internet – mit dir und später mit Kursen. "
           "Bony's VPN benutzt dieselbe Anmeldung. Ausgeschaltet bleibt alles wie bisher: Die App nimmt dann keinen "
           "Kontakt zum Server auf.")
DELETE_DETAIL = n_("Auf dem Server werden dabei alle deine Agent-PCs aus dem Bony-Netz entfernt und alle deine Kurse "
                   "und Kursteilnahmen gelöscht – auch für Bony's VPN. Die Agent-PCs selbst bleiben auf diesem "
                   "Rechner. Das lässt sich nicht rückgängig machen.")
DATENSCHUTZ_TEXT = n_("Datenschutz: Der Server sieht bei jeder Anfrage deine IP-Adresse. Gespeichert werden nur die "
                      "Instanz (ohne Namen oder E-Mail), deine Agent-PCs im Netz (Name, Netzadresse, zuletzt online) "
                      "und – in Kursen – dein Anzeigename. Bild, Ton und Chat im Kursraum laufen über den Server, "
                      "werden aber nicht aufgezeichnet.")
DATENSCHUTZ_FREMD = n_("Für einen eigenen Server ist dessen Betreiber verantwortlich – frag ihn nach seiner "
                       "Datenschutzerklärung.")
SWITCH_TEXT = n_("Beim bisherigen Server ist eine Instanz angemeldet. Mit dem Wechsel wird diese Anmeldung hier und "
                 "in Bony's VPN verworfen – die Instanz bleibt auf dem alten Server bestehen, ist von hier aus aber "
                 "nicht mehr erreichbar.\n\nServer trotzdem wechseln?")

# Laufende Aufrufe auch nach dem Schließen des Fensters festhalten (sonst bräche Qt beim Aufräumen ab)
_RUNNING: set[TaskWorker] = set()


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    return frame, lay


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    return label


class NetzDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Bony-Netz"))
        self.konto = Konto.laden()
        self.busy = 0
        self.status_text = ""

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(tr("Bony-Netz"))
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel(tr(INTRO))
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.active = QCheckBox(tr("Bony-Netz verwenden"))
        self.active.setChecked(netz.aktiv(self.konto))
        root.addWidget(self.active)

        root.addWidget(_section(tr("Server")))
        card, lay = _card()
        row = QHBoxLayout()
        self.server = QLineEdit(self.konto.server)
        self.server.setPlaceholderText(STANDARD_SERVER)
        self.check_btn = QPushButton(tr("Prüfen"))
        row.addWidget(self.server, 1)
        row.addWidget(self.check_btn)
        lay.addLayout(row)
        self.server_info = _muted()
        lay.addWidget(self.server_info)
        root.addWidget(card)

        root.addWidget(_section(tr("Instanz")))
        card, lay = _card()
        self.instance = QLabel()
        self.instance.setWordWrap(True)
        self.instance.setTextFormat(Qt.PlainText)
        lay.addWidget(self.instance)
        self.instance_hint = _muted()
        lay.addWidget(self.instance_hint)
        row = QHBoxLayout()
        self.create_btn = QPushButton(tr("Instanz anlegen"))
        self.create_btn.setObjectName("Primary")
        self.delete_btn = QPushButton(tr("Instanz löschen …"))
        self.delete_btn.setObjectName("Danger")
        row.addWidget(self.create_btn)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.datenschutz = _muted()
        self.datenschutz.setTextFormat(Qt.RichText)   # nur feste Texte und die feste Adresse – nichts vom Server
        self.datenschutz.linkActivated.connect(open_url)
        lay.addWidget(self.datenschutz)
        root.addWidget(card)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setStyleSheet("font-weight: 600;")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(tr("Schließen"))
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        make_scrollable(self, 560)

        self.active.toggled.connect(self._toggle)
        self.check_btn.clicked.connect(self._check)
        self.server.returnPressed.connect(self._check)
        self.server.textChanged.connect(lambda _t: self._update())
        self.create_btn.clicked.connect(self._create)
        self.delete_btn.clicked.connect(self._delete)

        self._update()
        if self.active.isChecked():
            self._refresh()

    # ---------------------------------------------------------------- Anzeige
    def _server_changed(self) -> bool:
        return server_normalisieren(self.server.text()) != self.konto.server

    def _datenschutz_text(self) -> str:
        if server_normalisieren(self.server.text().strip() or self.konto.server) == STANDARD_SERVER:
            return (tr("{wert} <a href=\"{DATENSCHUTZ_URL}\">Datenschutzerklärung</a>",
                       wert=html.escape(tr(DATENSCHUTZ_TEXT)), DATENSCHUTZ_URL=kurspaket.DATENSCHUTZ_URL))
        return f"{html.escape(tr(DATENSCHUTZ_TEXT))} {html.escape(tr(DATENSCHUTZ_FREMD))}"

    def _update(self) -> None:
        self.datenschutz.setText(self._datenschutz_text())
        on = self.active.isChecked()
        idle = on and not self.busy
        signed_in = self.konto.angemeldet
        self.server.setEnabled(idle)
        self.check_btn.setEnabled(idle)
        if signed_in:
            self.instance.setText(tr("Instanz-ID: {wert} · Kursleiter: {wert2}",
                                     wert=netz.kurz_id(self.konto.instanz_id),
                                     wert2='ja' if self.konto.ist_kursleiter else 'nein'))
            self.instance_hint.setText("")
        else:
            self.instance.setText(tr("Noch keine Instanz angelegt."))
            self.instance_hint.setText(tr("Erst "
                                          "den "
                                          "neuen "
                                          "Server "
                                          "mit "
                                          "„Prüfen“ "
                                          "übernehmen.") if self._server_changed() else tr("Eine Instanz ist deine "
                                                                                           "Anmeldung beim Server – "
                                                                                           "einmal pro Rechner."))
        self.create_btn.setVisible(not signed_in)
        self.create_btn.setEnabled(idle and not self._server_changed())
        self.delete_btn.setVisible(signed_in)
        self.delete_btn.setEnabled(idle)
        if not on:
            self.status.setText(tr("Bony-Netz ist ausgeschaltet."))
        elif self.busy:
            self.status.setText(tr("Frage den Server …"))
        else:
            self.status.setText(self.status_text)

    def _show(self, z: netz.Zustand) -> None:
        self.konto = z.konto
        self.status_text = z.text
        self.status.setToolTip(z.detail)
        if z.info:
            version = z.info.get("version")
            self.server_info.setText(z.info["server_name"] + (f" · Version {version}" if version else ""))
        else:
            self.server_info.setText(z.detail)

    # ---------------------------------------------------------------- Hintergrund
    def _run(self, fn: Callable[[], object], done: Callable[[TaskWorker], None]) -> None:
        w = TaskWorker(fn)
        _RUNNING.add(w)
        self.busy += 1

        def finished() -> None:
            _RUNNING.discard(w)
            self.busy -= 1
            done(w)
            self._update()

        w.finished.connect(finished)
        self._update()
        w.start()

    def _refresh(self) -> None:
        self._run(netz.zustand, lambda w: self._show(w.result) if w.error is None else self._failed(w.error))

    def _failed(self, error: Exception, title: str = "") -> None:
        text = netz.fehlertext(error)
        self.status_text = text
        if title:
            QMessageBox.warning(self, APP_NAME, f"{title}\n\n{text}")

    # ---------------------------------------------------------------- Aktionen
    def _toggle(self, on: bool) -> None:
        try:
            self.konto = netz.aktiv_setzen(on)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, netz.fehlertext(e))
        self._update()
        if on:
            self._refresh()

    def _check(self) -> None:
        if not self.check_btn.isEnabled():
            return
        address = server_normalisieren(self.server.text())
        self.server.setText(address)
        if address == self.konto.server:
            self._refresh()
            return
        if self.konto.angemeldet:
            box = QMessageBox(QMessageBox.Warning, tr("Server wechseln"), tr(SWITCH_TEXT), QMessageBox.NoButton, self)
            switch = box.addButton(tr("Server wechseln"), QMessageBox.DestructiveRole)
            keep = box.addButton(tr("Abbrechen"), QMessageBox.RejectRole)
            box.setDefaultButton(keep)
            box.setEscapeButton(keep)
            box.exec()
            if box.clickedButton() is not switch:
                self.server.setText(self.konto.server)
                return

        def done(w: TaskWorker) -> None:
            if w.error is None:
                self._show(w.result)
            else:   # der alte Server bleibt
                self.server_info.setText(netz.fehlertext(w.error))
                self.status_text = tr("Der Server wurde nicht übernommen: {wert}", wert=netz.fehlertext(w.error))

        self._run(lambda: netz.server_wechseln(address), done)

    def _create(self) -> None:
        server = self.konto.server

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self._failed(w.error, tr("Die Instanz wurde nicht angelegt."))
                return
            self.konto = w.result
            self._refresh()

        self._run(lambda: netz.instanz_anlegen(server), done)

    def _delete(self) -> None:
        if not confirm_delete(self, tr("Instanz löschen"),
                              tr("Instanz {wert} auf dem Server löschen?", wert=netz.kurz_id(self.konto.instanz_id)),
                              tr(DELETE_DETAIL)):
            return

        def done(w: TaskWorker) -> None:
            if w.error is not None:
                self._failed(w.error, tr("Die Instanz wurde nicht gelöscht."))
                return
            self.konto = w.result
            self.status_text = tr("Instanz gelöscht.")

        self._run(netz.instanz_loeschen, done)

