# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Kursraum“ (Aufgabe 05): die mitgelieferte Seite ``resources/kursraum`` in Qt WebEngine.

- Die Seite kommt über das eigene Schema ``kursraum://app/…`` aus den Ressourcen der App, nichts aus dem Internet
  (außer der Verbindung zum LiveKit-Server). ``vorbereiten()`` meldet das Schema an – das muss vor dem Anlegen
  der QApplication geschehen (``gui/app.py``).
- Die Eintrittskarte geht per QWebChannel (Objekt ``bruecke``) an die Seite, nie in die Adresse.
- Kamera, Mikrofon und Bildschirmaufnahme bekommt nur diese Seite (``kursraum.erlaubt``), alle anderen nichts.
  Bildschirm teilen braucht ``ScreenCaptureEnabled`` – nur beim Kursleiter an.
- Stummschalten und Entfernen ruft Python (``kursraum.stummschalten/entfernen``) im Hintergrund auf.
- Beim Schließen verlässt die Seite den Raum (``room.disconnect()``), erst dann geht das Fenster zu.
- Hilfe-Funktion (Aufgabe 06): Die Nachrichten laufen über die Seite, entschieden wird in Python – beim Teilnehmer
  ``gui/hilfe_ui.TeilnehmerHilfe`` (Rückfrage, x11vnc, Hinweis mit „Beenden“), beim Kursleiter
  ``trainer/gui/hilfe_fenster.KursleiterHilfe`` (Zusage prüfen, Betrachter). Weitere Seiten unter demselben Schema
  (Betrachter, noVNC) meldet die Kursleiter-Version über ``ZUSATZ`` an.

Ohne Qt WebEngine (Quelltext-Installation ohne PySide6-WebEngine) zeigt ``oeffnen`` nur einen Hinweis.
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from collections.abc import Callable

from bonys_agents import kursraum, netz

from .workers import TaskWorker

try:
    from PySide6.QtCore import QBuffer, QByteArray, QFile, QIODevice, QUrl
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestJob, QWebEngineUrlScheme,
        QWebEngineUrlSchemeHandler,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:   # PySide6-Essentials ohne WebEngine
    QWebEngineView = None

_FENSTER: dict[str, KursraumFenster] = {}   # kurs_id → offenes Fenster
_RUNNING: set[TaskWorker] = set()
_profil = None
_handler = None
SCHLIESSEN_SEKUNDEN = 3   # so lange wartet das Fenster höchstens auf „Raum verlassen“
DEBUG = bool(os.environ.get("BONYS_KURSRAUM_DEBUG"))
# Weitere Dateien unter kursraum://app/<ordner>/… : ordner → (Pfad darin → (Inhalt, MIME-Typ) oder None)
ZUSATZ: dict[str, Callable[[str], tuple[bytes, str] | None]] = {}


def verfuegbar() -> bool:
    return QWebEngineView is not None


def vorbereiten() -> None:
    """Vor ``QApplication(...)`` aufrufen: Schema ``kursraum`` anmelden (und WebEngine laden, das setzt
    ``AA_ShareOpenGLContexts``). Ohne WebEngine passiert nichts."""
    if not verfuegbar() or QWebEngineUrlScheme.schemeByName(kursraum.SCHEMA.encode()).name():
        return
    if kursraum.sandbox_abschalten():   # Ubuntu 24.04+ ohne AppArmor-Profil – sonst startet WebEngine nicht
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    schema = QWebEngineUrlScheme(kursraum.SCHEMA.encode())
    schema.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    # Sicher (getUserMedia/getDisplayMedia brauchen einen sicheren Kontext), aber nicht „lokal“: Die Seite muss den
    # LiveKit-Server (wss/https) erreichen.
    schema.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(schema)


def _laufen(fn, fertig) -> None:
    w = TaskWorker(fn)
    _RUNNING.add(w)

    def ende() -> None:
        _RUNNING.discard(w)
        fertig(w)

    w.finished.connect(ende)
    w.start()


def _fehlertext(e: BaseException) -> str:
    return str(e) if isinstance(e, kursraum.KursraumFehler) else netz.fehlertext(e)


def oeffnen(kurs_id: str, kursname: str, parent: QWidget | None = None, fertig=None) -> None:
    """Kursraum eines Kurses öffnen – ist er schon offen, nach vorn holen.

    Holt erst die Eintrittskarte (Hintergrund). ``fertig(fehlertext_oder_None)`` meldet das Ergebnis, z. B. für die
    Statuszeile des aufrufenden Fensters; ohne ``fertig`` erscheint ein Fehler als Meldungsfenster.
    """
    def melden(text: str | None) -> None:
        if fertig is not None:
            fertig(text)
        elif text:
            QMessageBox.warning(parent if parent is not None and isValid(parent) else None, "Kursraum", text)

    offen = _FENSTER.get(kurs_id)
    if offen is not None and isValid(offen):
        offen.showNormal()
        offen.raise_()
        offen.activateWindow()
        melden(None)
        return
    if not verfuegbar():
        melden(kursraum.kein_webengine_text())
        return
    if not kursraum.livekit_da():
        melden(kursraum.KEINE_SEITE)
        return

    def da(w: TaskWorker) -> None:
        if w.error is not None:
            melden(_fehlertext(w.error))
            return
        if kurs_id in _FENSTER and isValid(_FENSTER[kurs_id]):   # inzwischen doppelt geklickt
            _FENSTER[kurs_id].raise_()
        else:
            f = KursraumFenster(w.result, kursname)
            _FENSTER[kurs_id] = f
            f.show()
        melden(None)

    _laufen(lambda: _eintreten(kurs_id), da)


def _eintreten(kurs_id: str) -> kursraum.Karte:
    """Eintrittskarte holen (Hintergrund); beim Kursleiter auch die eigene Adresse im Bony-Netz – nur von ihr aus
    nimmt der Agent-PC eines Teilnehmers dann die Hilfe-Verbindung an."""
    karte = kursraum.eintreten(kurs_id)
    if karte.kursleiter:
        from bonys_agents import hilfe

        karte.von = hilfe.eigene_ip()
    return karte


def alle_schliessen() -> None:
    for f in list(_FENSTER.values()):
        if isValid(f):
            f.close()


def offen(kurs_id: str) -> bool:
    f = _FENSTER.get(kurs_id)
    return f is not None and isValid(f)


# ---------------------------------------------------------------- WebEngine-Teile (nur wenn verfügbar)
if verfuegbar():

    class _Schema(QWebEngineUrlSchemeHandler):
        """Liefert ``resources/kursraum`` (und ``qwebchannel.js`` aus Qt) – sonst 404."""

        def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802 – Qt-Name
            url = job.requestUrl()
            if url.host() != kursraum.HOST or job.requestMethod() != b"GET":
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            if url.path() == "/qwebchannel.js":
                datei = QFile(":/qtwebchannel/qwebchannel.js")
                if not datei.open(QIODevice.ReadOnly):
                    job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                    return
                inhalt, mime = bytes(datei.readAll()), "text/javascript"
            else:
                ordner, _, rest = url.path().lstrip("/").partition("/")
                if ordner in ZUSATZ:
                    treffer = ZUSATZ[ordner](rest)
                else:
                    datei = kursraum.seiten_datei(url.path())
                    treffer = (datei[0].read_bytes(), datei[1]) if datei is not None else None
                if treffer is None:
                    job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                    return
                inhalt, mime = treffer
            puffer = QBuffer(job)
            puffer.setData(QByteArray(inhalt))
            puffer.open(QIODevice.ReadOnly)
            job.reply(mime.encode(), puffer)

    def _profil_holen() -> QWebEngineProfile:
        """Ein Profil ohne Speicher auf der Platte (Chat und Einstellungen gehen mit dem Fenster)."""
        global _profil, _handler
        if _profil is None:
            _profil = QWebEngineProfile(QApplication.instance())   # ohne Namen: nichts auf der Platte
            _handler = _Schema(_profil)
            _profil.installUrlSchemeHandler(kursraum.SCHEMA.encode(), _handler)
            _profil.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        return _profil

    class _Seite(QWebEnginePage):
        def __init__(self, profil, parent=None):
            super().__init__(profil, parent)
            if hasattr(self, "permissionRequested"):          # Qt 6.8+
                self.permissionRequested.connect(self._berechtigung)
            else:                                              # Qt 6.6/6.7
                self.featurePermissionRequested.connect(self._berechtigung_alt)
            if hasattr(self, "desktopMediaRequested"):        # Qt 6.7+: Bildschirm oder Fenster wählen
                self.desktopMediaRequested.connect(self._bildschirm_waehlen)

        def _berechtigung(self, anfrage) -> None:
            herkunft = anfrage.origin()
            art = anfrage.permissionType().name
            if kursraum.erlaubt(herkunft.scheme(), herkunft.host(), art):
                anfrage.grant()
            else:
                anfrage.deny()

        def _berechtigung_alt(self, herkunft, merkmal) -> None:
            ok = kursraum.erlaubt(herkunft.scheme(), herkunft.host(), merkmal.name)
            self.setFeaturePermission(herkunft, merkmal, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                                      if ok else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)

        def _bildschirm_waehlen(self, anfrage) -> None:
            if not kursraum.erlaubt(self.url().scheme(), self.url().host(), "DesktopVideoCapture"):
                anfrage.cancel()
                return
            dlg = _BildschirmWahl(anfrage, self.parent())   # Elternobjekt ist die QWebEngineView
            if dlg.exec() != QDialog.Accepted or not dlg.auswahl(anfrage):
                anfrage.cancel()

        def acceptNavigationRequest(self, url, art, hauptrahmen) -> bool:  # noqa: N802 – Qt-Name
            # Nur die eigene Seite – Links und Weiterleitungen nach außen gibt es im Kursraum nicht
            return url.scheme() == kursraum.SCHEMA and url.host() == kursraum.HOST

        def createWindow(self, art):  # noqa: N802 – keine Popups
            return None

        def javaScriptConsoleMessage(self, stufe, text, zeile, quelle) -> None:  # noqa: N802
            if DEBUG:   # nur zur Fehlersuche – die Seite gibt nie die Eintrittskarte aus
                print(f"[kursraum] {quelle}:{zeile} {text}", flush=True)

    class _BildschirmWahl(QDialog):
        """Was geteilt wird: ein Bildschirm oder ein einzelnes Fenster."""

        def __init__(self, anfrage, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Bildschirm teilen")
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Was sollen die Teilnehmer sehen?"))
            self.liste = QListWidget()
            for art, modell, wort in (("bildschirm", anfrage.screensModel(), "Bildschirm"),
                                      ("fenster", anfrage.windowsModel(), "Fenster")):
                for zeile in range(modell.rowCount()):
                    name = modell.data(modell.index(zeile, 0)) or ""
                    text = f"{wort} {zeile + 1}" if art == "bildschirm" else f"Fenster: {name or '?'}"
                    if art == "bildschirm" and name:
                        text += f" ({name})"
                    item = QListWidgetItem(text)
                    item.setData(Qt.UserRole, (art, zeile))
                    self.liste.addItem(item)
            self.liste.setCurrentRow(0)
            self.liste.itemDoubleClicked.connect(lambda _i: self.accept())
            lay.addWidget(self.liste)
            knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            knoepfe.button(QDialogButtonBox.Ok).setText("Teilen")
            knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            knoepfe.accepted.connect(self.accept)
            knoepfe.rejected.connect(self.reject)
            lay.addWidget(knoepfe)
            self.resize(460, 360)

        def auswahl(self, anfrage) -> bool:
            item = self.liste.currentItem()
            if item is None:
                return False
            art, zeile = item.data(Qt.UserRole)
            if art == "bildschirm":
                anfrage.selectScreen(anfrage.screensModel().index(zeile, 0))
            else:
                anfrage.selectWindow(anfrage.windowsModel().index(zeile, 0))
            return True


class Bruecke(QObject):
    """Objekt ``bruecke`` der Seite (QWebChannel)."""

    karte = Signal(str)       # JSON: Karte für die Seite oder {"fehler": …}
    antwort = Signal(str)     # JSON: {id, ok, text}
    schliessen = Signal()
    hilfe = Signal(str)       # JSON: Hilfe-Funktion → Seite ({aktion: senden|helfen|aktiv|hinweis|banner, …})

    def __init__(self, fenster: KursraumFenster):
        super().__init__(fenster)
        self.fenster = fenster

    @Slot()
    def bereit(self) -> None:
        self.karte.emit(json.dumps(self.fenster.fuer_seite()))
        self.fenster.seite_bereit()

    # Hilfe-Funktion: was die Seite empfängt, entscheidet Python
    @Slot(str)
    def hilfeAnfrage(self, daten: str) -> None:  # noqa: N802 – Name auf der Seite
        self._hilfe("anfrage", daten)

    @Slot(str)
    def hilfeZusage(self, daten: str) -> None:  # noqa: N802
        self._hilfe("zusage", daten)

    @Slot(str)
    def hilfeEnde(self, daten: str) -> None:  # noqa: N802
        self._hilfe("ende", daten)

    @Slot()
    def raumGetrennt(self) -> None:  # noqa: N802
        if self.fenster.hilfe is not None:
            self.fenster.hilfe.raum_getrennt()

    def _hilfe(self, art: str, daten: str) -> None:
        steuerung = self.fenster.hilfe
        if steuerung is None:
            return
        try:
            d = json.loads(daten)
        except ValueError:
            return
        if isinstance(d, dict) and isinstance(d.get("identity"), str):
            getattr(steuerung, art)(d)

    @Slot(str, str, str)
    def stumm(self, anfrage_id: str, identitaet: str, track_sid: str) -> None:
        karte = self.fenster.karte
        self._im_hintergrund(anfrage_id, lambda: kursraum.stummschalten(karte, identitaet, track_sid))

    @Slot(str, str)
    def entfernen(self, anfrage_id: str, identitaet: str) -> None:
        karte = self.fenster.karte
        self._im_hintergrund(anfrage_id, lambda: kursraum.entfernen(karte, identitaet))

    @Slot()
    def erneut(self) -> None:
        self.fenster.erneut_eintreten()

    @Slot()
    def verlassen(self) -> None:
        self.fenster.raum_verlassen()

    def _im_hintergrund(self, anfrage_id: str, fn) -> None:
        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                return
            fehler = None if w.error is None else _fehlertext(w.error)
            self.antwort.emit(json.dumps({"id": anfrage_id, "ok": fehler is None, "text": fehler or ""}))

        _laufen(fn, fertig)


class KursraumFenster(QWidget):
    """Eigenständiges Fenster (ohne Elternfenster), damit es neben „Kurse“ und der Kursansicht bedienbar bleibt."""

    def __init__(self, karte: kursraum.Karte, kursname: str):
        super().__init__(None)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.karte = karte
        self.kursname = kursname
        self.fertig = False          # Seite hat den Raum verlassen – jetzt darf das Fenster zu
        self.teilen, self.teilen_hinweis = kursraum.bildschirm_teilen()
        self.setWindowTitle(f"Kursraum – {kursname}" if kursname else "Kursraum")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.seite = _Seite(_profil_holen(), self.view)
        einst = self.seite.settings()
        einst.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, karte.kursleiter and self.teilen)
        einst.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        einst.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        einst.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        self.bruecke = Bruecke(self)
        self.kanal = QWebChannel(self.seite)
        self.kanal.registerObject("bruecke", self.bruecke)
        self.seite.setWebChannel(self.kanal)
        self.view.setPage(self.seite)
        lay.addWidget(self.view)
        self.view.load(QUrl(kursraum.STARTSEITE))
        bildschirm = QApplication.primaryScreen()
        if bildschirm is not None:
            g = bildschirm.availableGeometry()
            self.resize(min(1280, int(g.width() * 0.9)), min(820, int(g.height() * 0.9)))
        self._uhr = QTimer(self)
        self._uhr.setSingleShot(True)
        self._uhr.timeout.connect(self.raum_verlassen)
        self.destroyed.connect(lambda *_: _FENSTER.pop(karte.kurs_id, None))
        self._bereit = False
        self._hilfe_wartet: list[str] = []
        self.hilfe = _hilfe_steuerung(self)

    def seite_bereit(self) -> None:
        self._bereit = True
        for identitaet in self._hilfe_wartet:
            self.an_seite({"aktion": "helfen", "identity": identitaet})
        self._hilfe_wartet.clear()

    def an_seite(self, daten: dict) -> None:
        """Nachricht der Hilfe-Funktion an die Seite (``bruecke.hilfe``)."""
        self.bruecke.hilfe.emit(json.dumps(daten))

    def helfen(self, instanz_id: str) -> None:
        """Kursleiter: „Helfen“ für einen Teilnehmer (auch aus der Kursansicht) – fragt ihn über die Seite."""
        if self._bereit:
            self.an_seite({"aktion": "helfen", "identity": instanz_id})
        else:
            self._hilfe_wartet.append(instanz_id)

    def fuer_seite(self) -> dict:
        return self.karte.fuer_seite(kursname=self.kursname, teilen=self.teilen, teilen_hinweis=self.teilen_hinweis)

    def erneut_eintreten(self) -> None:
        kurs_id = self.karte.kurs_id

        def fertig(w: TaskWorker) -> None:
            if not isValid(self):
                return
            if w.error is not None:
                self.bruecke.karte.emit(json.dumps({"fehler": _fehlertext(w.error)}))
                return
            self.karte = w.result
            self.seite.settings().setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
                                               self.karte.kursleiter and self.teilen)
            self.bruecke.karte.emit(json.dumps(self.fuer_seite()))

        _laufen(lambda: _eintreten(kurs_id), fertig)

    def raum_verlassen(self) -> None:
        self.fertig = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        if self.fertig:
            self._uhr.stop()
            if self.hilfe is not None:
                self.hilfe.raum_getrennt()   # eine laufende Hilfe endet mit dem Kursraum
            super().closeEvent(event)   # Seite und Ansicht gehen mit dem Fenster, das Profil gehört der App
            return
        event.ignore()
        if not self._uhr.isActive():
            self.bruecke.schliessen.emit()   # Seite ruft room.disconnect() und dann bruecke.verlassen()
            self._uhr.start(SCHLIESSEN_SEKUNDEN * 1000)


def _hilfe_steuerung(fenster: KursraumFenster):
    """Teilnehmer: Rückfrage und x11vnc. Kursleiter: Betrachter – nur in der Kursleiter-Version (sonst None)."""
    if fenster.karte.kursleiter:
        try:
            from bonys_agents.trainer.gui.hilfe_fenster import KursleiterHilfe
        except ImportError:   # Anwender-Version: kein Betrachter
            return None
        return KursleiterHilfe(fenster)
    from .hilfe_ui import TeilnehmerHilfe

    return TeilnehmerHilfe(fenster)


def helfen(kurs_id: str, kursname: str, instanz_id: str, parent: QWidget | None = None, fertig=None) -> None:
    """Kursansicht → „Helfen“: Kursraum öffnen (falls nötig) und den Teilnehmer um Zustimmung bitten."""
    def offen_dann(text: str | None) -> None:
        f = _FENSTER.get(kurs_id)
        if text is None and f is not None and isValid(f):
            f.helfen(instanz_id)
        if fertig is not None:
            fertig(text)

    oeffnen(kurs_id, kursname, parent, offen_dann)
