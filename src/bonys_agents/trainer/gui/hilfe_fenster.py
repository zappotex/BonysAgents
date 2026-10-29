# SPDX-License-Identifier: GPL-3.0-or-later
"""Hilfe-Funktion beim Kursleiter (Aufgabe 06, nur Kursleiter-Version): Zusage prüfen und Agent-PC anzeigen.

``KursleiterHilfe`` gehört zum Kursraum-Fenster (``gui/kursraum_fenster.py``). Kommt eine ``hilfe-zusage``, fragt sie
die Zentrale nach der Adresse des Agent-PCs dieses Teilnehmers (nur solange der Kurs läuft) und verbindet sich nur
dorthin (``hilfe.zusage_pruefen``). Angezeigt wird

- eingebettet: ``HilfeFenster`` – noVNC (``trainer/resources/novnc``) mit der Seite ``trainer/resources/hilfe`` unter
  ``kursraum://app/hilfe/``, Verbindung über ``hilfe_betrachter.Bruecke`` (nur 127.0.0.1, eine Verbindung),
- sonst mit TigerVNC (``hilfe_betrachter.TigerVNC``, Passwort in einer Datei mit Rechten 600).

Geht der Betrachter zu, bekommt der Teilnehmer ``hilfe-ende`` – seine App stoppt x11vnc sofort.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from shiboken6 import isValid

from bonys_agents import hilfe, kursraum, netz
from bonys_agents.gui import kursraum_fenster
from bonys_agents.gui.hilfe_ui import festhalten
from bonys_agents.gui.workers import TaskWorker
from bonys_agents.trainer import present
from bonys_agents.trainer.hilfe_betrachter import BetrachterFehler, Bruecke, TigerVNC
from bonys_agents.i18n import tr

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

SEITE = f"{kursraum.SCHEMA}://{kursraum.HOST}/hilfe/index.html"
PASSWORTDATEI_SEKUNDEN = 20     # so lange darf TigerVNC die Passwortdatei lesen
_RUNNING: set[TaskWorker] = set()


def _laufen(fn, fertig) -> None:
    w = TaskWorker(fn)
    _RUNNING.add(w)

    def ende() -> None:
        _RUNNING.discard(w)
        fertig(w)

    w.finished.connect(ende)
    w.start()


def seiten_ordner():
    return present.resources_dir() / "hilfe"


def _hilfe_datei(pfad: str) -> tuple[bytes, str] | None:
    treffer = kursraum.seiten_datei(pfad, seiten_ordner())
    return (treffer[0].read_bytes(), treffer[1]) if treffer is not None else None


def _novnc_datei(pfad: str) -> tuple[bytes, str] | None:
    ordner = present.novnc_dir()
    datei = present._safe_file(ordner, pfad) if ordner is not None else None
    return (datei.read_bytes(), "text/javascript") if datei is not None else None


# Seiten unter dem Schema des Kursraums anmelden (das Schema selbst meldet gui/app.py vor der QApplication an)
kursraum_fenster.ZUSATZ["hilfe"] = _hilfe_datei
kursraum_fenster.ZUSATZ["novnc"] = _novnc_datei


def eingebettet() -> bool:
    """noVNC im eigenen Fenster möglich? Sonst TigerVNC."""
    return kursraum_fenster.verfuegbar() and present.novnc_dir() is not None \
        and (seiten_ordner() / "index.html").is_file()


class Betrachter(QObject):
    """Objekt ``betrachter`` der Seite (QWebChannel)."""

    verbindung = Signal(str)   # JSON {url, passwort, modus, titel}
    ende = Signal(str)         # Hilfe ist vorbei (Text)
    schliessen = Signal()

    def __init__(self, fenster: HilfeFenster):
        super().__init__(fenster)
        self.fenster = fenster

    @Slot()
    def bereit(self) -> None:
        self.verbindung.emit(json.dumps(self.fenster.fuer_seite()))

    @Slot()
    def verbunden(self) -> None:
        self.fenster.verbunden = True

    @Slot(str)
    def getrennt(self, text: str) -> None:
        self.fenster.getrennt(text)

    @Slot()
    def beenden(self) -> None:
        self.fenster.close()


class HilfeFenster(QWidget):
    """Eigenes Fenster mit noVNC – zeigt genau einen Agent-PC."""

    zu = Signal()

    def __init__(self, freigabe: hilfe.Freigabe, titel: str):
        super().__init__(None)
        self.setAttribute(Qt.WA_DeleteOnClose)
        festhalten(self)
        self.freigabe = freigabe
        self.titel = titel
        self.verbunden = False
        self.gemeldet = False
        self.bruecke = Bruecke((freigabe.ip, freigabe.port))
        self.setWindowTitle(tr("Hilfe – {titel} ({wert})", titel=titel, wert=hilfe.MODUS_TEXT[freigabe.modus]))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.seite = kursraum_fenster._Seite(kursraum_fenster._profil_holen(), self.view)
        self.betrachter = Betrachter(self)
        self.kanal = QWebChannel(self.seite)
        self.kanal.registerObject("betrachter", self.betrachter)
        self.seite.setWebChannel(self.kanal)
        self.view.setPage(self.seite)
        lay.addWidget(self.view)
        self.view.load(QUrl(SEITE))
        bildschirm = QApplication.primaryScreen()
        if bildschirm is not None:
            g = bildschirm.availableGeometry()
            self.resize(min(1400, int(g.width() * 0.9)), min(900, int(g.height() * 0.9)))

    def fuer_seite(self) -> dict:
        return {"url": self.bruecke.url, "passwort": self.freigabe.passwort, "modus": self.freigabe.modus,
                "titel": self.titel}

    def getrennt(self, text: str) -> None:
        if not self.verbunden and self.bruecke.ende == (4010, "Agent-PC nicht erreichbar"):
            text = tr("Der Agent-PC ist von diesem Rechner aus nicht erreichbar.")
            self._netz_pruefen(text)
            return
        self.betrachter.ende.emit(text)

    def _netz_pruefen(self, text: str) -> None:
        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                return
            zusatz = ""
            if w.error is None and not w.result.verbunden:
                zusatz = f"\n\n{w.result.text} {hilfe.verbinden_hinweis()}"
            self.betrachter.ende.emit(text + zusatz)

        _laufen(hilfe.rechner_im_netz, fertig)

    def ende_zeigen(self, text: str) -> None:
        self.betrachter.ende.emit(text)

    def closeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self.betrachter.schliessen.emit()
        self.bruecke.schliessen()
        if not self.gemeldet:
            self.gemeldet = True
            self.zu.emit()
        super().closeEvent(event)


class _TigerVNCSitzung(QObject):
    """TigerVNC als Rückfall: beobachtet den Prozess und löscht die Passwortdatei bald."""

    zu = Signal()

    def __init__(self, freigabe: hilfe.Freigabe, parent=None):
        super().__init__(parent)
        self.vnc = TigerVNC(freigabe)
        QTimer.singleShot(PASSWORTDATEI_SEKUNDEN * 1000, self.vnc.aufraeumen)
        self.uhr = QTimer(self)
        self.uhr.setInterval(1000)
        self.uhr.timeout.connect(self._pruefen)
        self.uhr.start()

    def _pruefen(self) -> None:
        if not self.vnc.laeuft():
            self.uhr.stop()
            self.vnc.aufraeumen()
            self.zu.emit()

    def ende_zeigen(self, _text: str) -> None:
        self.close()

    def close(self) -> None:
        if self.uhr.isActive():
            self.uhr.stop()
            self.vnc.beenden()
            self.zu.emit()


class KursleiterHilfe(QObject):
    """Hilfe-Funktion beim Kursleiter: ein Betrachter je Teilnehmer."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.fenster = fenster                   # KursraumFenster
        self.kurs_id = fenster.karte.kurs_id
        self.offen: dict[str, object] = {}       # instanz_id → HilfeFenster oder _TigerVNCSitzung

    def _seite(self, daten: dict) -> None:
        if isValid(self.fenster):
            self.fenster.an_seite(daten)

    def _ende_senden(self, identitaet: str) -> None:
        self._seite({"aktion": "aktiv", "identity": identitaet, "an": False})
        self._seite({"aktion": "senden", "thema": hilfe.ENDE, "daten": {}, "an": [identitaet]})

    # ---------------------------------------------------------------- von der Seite
    def anfrage(self, _d: dict) -> None:
        """Kommt beim Kursleiter nicht vor."""

    def zusage(self, d: dict) -> None:
        identitaet, name = d["identity"], str(d.get("name") or "?")[:80]
        daten = d.get("daten") if isinstance(d.get("daten"), dict) else {}
        kurs_id = self.kurs_id

        def pruefen() -> hilfe.Freigabe:
            return hilfe.zusage_pruefen(daten, hilfe.teilnehmer_ip(kurs_id, identitaet))

        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                return
            if w.error is not None:
                text = str(w.error) if isinstance(w.error, hilfe.HilfeFehler) else netz.fehlertext(w.error)
                self._seite({"aktion": "hinweis", "text": tr("Hilfe für {name} geht nicht: {inhalt}", name=name,
                                                             inhalt=text)})
                self._ende_senden(identitaet)
                return
            pc = str(daten.get("pc") or "")[:80]
            self._oeffnen(identitaet, w.result, f"{name} · {pc}" if pc else name)

        _laufen(pruefen, fertig)

    def _oeffnen(self, identitaet: str, freigabe: hilfe.Freigabe, titel: str) -> None:
        alt = self.offen.pop(identitaet, None)
        if alt is not None and isValid(alt):
            alt.close()
        try:
            if eingebettet():
                betrachter = HilfeFenster(freigabe, titel)
                betrachter.show()
            else:
                betrachter = _TigerVNCSitzung(freigabe, self)
        except (BetrachterFehler, OSError) as e:
            self._seite({"aktion": "hinweis", "text": str(e)})
            self._ende_senden(identitaet)
            return
        self.offen[identitaet] = betrachter
        betrachter.zu.connect(lambda i=identitaet, b=betrachter: self._zu(i, b))
        self._seite({"aktion": "aktiv", "identity": identitaet, "an": True})

    def _zu(self, identitaet: str, betrachter) -> None:
        if self.offen.get(identitaet) is betrachter:
            del self.offen[identitaet]
            self._ende_senden(identitaet)

    def ende(self, d: dict) -> None:
        """Der Teilnehmer hat beendet (oder x11vnc ist von selbst zu Ende)."""
        identitaet = d["identity"]
        betrachter = self.offen.pop(identitaet, None)
        self._seite({"aktion": "aktiv", "identity": identitaet, "an": False})
        if betrachter is not None and isValid(betrachter):
            betrachter.ende_zeigen(tr("Der Teilnehmer hat die Hilfe beendet."))

    def raum_getrennt(self) -> None:
        """Kursraum verlassen: alle Betrachter schließen – bei den Teilnehmern endet x11vnc damit (``-once``)."""
        for identitaet, betrachter in list(self.offen.items()):
            self.offen.pop(identitaet, None)
            if isValid(betrachter):
                betrachter.close()
