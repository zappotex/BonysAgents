# SPDX-License-Identifier: GPL-3.0-or-later
"""Musik & Radio: Leiste unten im Hauptfenster und Fenster zum Auswählen (Daten und Regeln: ``musik.py``).

- Spielt nur, was der Nutzer bewusst startet – nie beim Programmstart, auch nicht die zuletzt gewählte Quelle.
- Läuft im Hauptfenster weiter, während Anleitung, Lektionen und Agent-PCs wechseln.
- Qt Multimedia (mit FFmpeg) wird erst beim ersten Abspielen geladen. Fehlt es (z. B. Linux arm64 ohne
  PySide6-Addons), gibt es die Leiste nicht.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSlider, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, musik
from bonys_agents.i18n import n_, tr

TITEL = n_("Musik & Radio")
EINLADUNG = n_("Lerne auch mit Musik:")   # steht vor dem Player in der Leiste
SCHRIFT_DATEI = "fonts/Pacifico-Regular.ttf"
BUCHSTABENABSTAND = 1.5   # Pixel zwischen den Buchstaben
_SCHRIFT: str | None = None
DATENSCHUTZ = n_("Beim Radiohören sieht der Sender die IP-Adresse dieses Rechners – wie bei jedem Webradio. "
                 "Bony's Agents speichert dazu nichts und spielt nichts von selbst ab.")


def schrift_laden() -> str:
    """Schreibschrift „Pacifico“ (OFL-1.1, resources/fonts) einmal laden – Name der Familie oder "" (dann
    zeigt Qt die normale Schrift)."""
    global _SCHRIFT
    if _SCHRIFT is None:
        from PySide6.QtGui import QFontDatabase

        from .style import resource

        fid = QFontDatabase.addApplicationFont(str(resource(SCHRIFT_DATEI)))
        familien = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _SCHRIFT = familien[0] if familien else ""
    return _SCHRIFT


def verfuegbar() -> bool:
    return importlib.util.find_spec("PySide6.QtMultimedia") is not None


class Abspieler(QObject):
    """Eine Wiedergabe für die ganze App: Radio-Sender oder die eigene Liste."""

    geaendert = Signal()
    fehler = Signal(str)

    def __init__(self, einstellungen: musik.Einstellungen, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.e = einstellungen
        self._player = None      # erst beim ersten Abspielen
        self._ausgabe = None
        self._laeuft = False
        self._fehlversuche = 0   # eigene Liste: nicht abspielbare Dateien hintereinander

    # -------------------------------------------------------------- Qt Multimedia (spät geladen)
    def _neuer_player(self):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        player, ausgabe = QMediaPlayer(self), QAudioOutput(self)
        player.setAudioOutput(ausgabe)
        player.mediaStatusChanged.connect(self._status)
        player.errorOccurred.connect(self._fehler)
        return player, ausgabe

    def _bereit(self):
        if self._player is None:
            self._player, self._ausgabe = self._neuer_player()
            self._lautstaerke_anwenden()
        return self._player

    def _lautstaerke_anwenden(self) -> None:
        if self._ausgabe is not None:
            self._ausgabe.setVolume((self.e.lautstaerke / 100) ** 2)   # hörbar gleichmäßiger als linear

    def _starten(self, url: QUrl) -> None:
        player = self._bereit()
        player.stop()
        player.setSource(url)
        player.play()
        self._laeuft = True
        musik.speichern(self.e)
        self.geaendert.emit()

    def _status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.e.quelle == musik.MUSIK:
            self._fehlversuche = 0
            self.weiter()
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            self._fehlversuche = 0

    def _fehler(self, _code=None, text: str = "") -> None:
        if self.e.quelle == musik.MUSIK and self.e.dateien and self._fehlversuche < min(len(self.e.dateien), 20):
            self._fehlversuche += 1   # Datei fehlt oder ist kaputt → nächste
            self.weiter()
            return
        self._laeuft = False
        if self._player is not None:
            self._player.stop()
        self.geaendert.emit()
        was = tr("Der Sender ist gerade nicht "
                 "erreichbar") if self.e.quelle == musik.RADIO else tr("Die Musik lässt sich " \
                                                                       "nicht abspielen")
        self.fehler.emit(f"{was}.\n\n{text}".strip())

    # -------------------------------------------------------------- Bedienung
    @property
    def laeuft(self) -> bool:
        return self._laeuft

    @property
    def hat_quelle(self) -> bool:
        if self.e.quelle == musik.RADIO:
            return bool(self.e.sender(self.e.sender_url))
        return self.e.quelle == musik.MUSIK and bool(self.e.dateien)

    def radio(self, sender: musik.Sender) -> None:
        self.e.quelle, self.e.sender_url = musik.RADIO, sender.url
        self._starten(QUrl(sender.url))

    def musik(self, index: int | None = None) -> None:
        if not self.e.dateien:
            return
        self.e.quelle = musik.MUSIK
        if index is not None:
            self.e.titel = max(0, min(index, len(self.e.dateien) - 1))
        self.e.titel = min(self.e.titel, len(self.e.dateien) - 1)
        self._starten(QUrl.fromLocalFile(self.e.dateien[self.e.titel]))

    def weiter(self) -> None:
        if not self.e.dateien:
            return
        if self.e.zufall and len(self.e.dateien) > 1:
            index = random.choice([i for i in range(len(self.e.dateien)) if i != self.e.titel])
        else:
            index = (self.e.titel + 1) % len(self.e.dateien)
        self.musik(index)

    def zurueck(self) -> None:
        if self.e.dateien:
            self.musik((self.e.titel - 1) % len(self.e.dateien))

    def umschalten(self) -> None:
        """▶/⏸: Läuft etwas, anhalten (Radio: Verbindung trennen); sonst die gewählte Quelle starten."""
        if self._laeuft and self._player is not None:
            if self.e.quelle == musik.MUSIK:
                self._player.pause()
            else:
                self._player.stop()
            self._laeuft = False
            self.geaendert.emit()
        elif self.e.quelle == musik.MUSIK and self._player is not None and self._player.source().isLocalFile() \
                and Path(self._player.source().toLocalFile()) == Path(self.e.dateien[self.e.titel]):  # Qt: / statt \
            self._player.play()   # an der angehaltenen Stelle weiter
            self._laeuft = True
            self.geaendert.emit()
        elif self.e.quelle == musik.RADIO and (s := self.e.sender(self.e.sender_url)):
            self.radio(s)
        elif self.e.quelle == musik.MUSIK:
            self.musik()

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        self._laeuft = False
        self.geaendert.emit()

    def lautstaerke_setzen(self, prozent: int) -> None:
        self.e.lautstaerke = max(0, min(100, int(prozent)))
        self._lautstaerke_anwenden()

    def text(self) -> str:
        if self.e.quelle == musik.RADIO and (s := self.e.sender(self.e.sender_url)):
            return s.name
        if self.e.quelle == musik.MUSIK and self.e.dateien:
            return Path(self.e.dateien[self.e.titel]).stem
        return tr(TITEL)


class MusikLeiste(QWidget):
    """Unten in der Statusleiste: ♪ (Fenster), ▶/⏸, ⏭ (nur eigene Musik), Name der Quelle, Lautstärke."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.abspieler = Abspieler(musik.laden(), self)
        self._dialog: MusikDialog | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(4)
        schrift_laden()
        self.einladung = QLabel(tr(EINLADUNG))
        self.einladung.setObjectName("MusikEinladung")   # gelb, fett, Schreibschrift (style.py)
        schrift = self.einladung.font()
        schrift.setLetterSpacing(QFont.AbsoluteSpacing, BUCHSTABENABSTAND)   # Schreibschrift sonst schwer lesbar
        self.einladung.setFont(schrift)
        self.menue_knopf = QToolButton(text="♪")
        self.menue_knopf.setToolTip(tr("{titel} – Sender oder eigene Musik wählen", titel=tr(TITEL)))
        self.menue_knopf.clicked.connect(self.dialog_zeigen)
        self.play_knopf = QToolButton()
        self.play_knopf.clicked.connect(self.abspieler.umschalten)
        self.weiter_knopf = QToolButton(text="⏭")
        self.weiter_knopf.setToolTip(tr("Nächster Titel"))
        self.weiter_knopf.clicked.connect(self.abspieler.weiter)
        self.name = QLabel()
        self.name.setObjectName("Muted")
        self.name.setMaximumWidth(220)
        self.lautstaerke = QSlider(Qt.Horizontal)
        self.lautstaerke.setRange(0, 100)
        self.lautstaerke.setFixedWidth(80)
        self.lautstaerke.setValue(self.abspieler.e.lautstaerke)
        self.lautstaerke.setToolTip(tr("Lautstärke"))
        self.lautstaerke.valueChanged.connect(self.abspieler.lautstaerke_setzen)
        self.lautstaerke.sliderReleased.connect(lambda: musik.speichern(self.abspieler.e))
        for w in (self.einladung, self.menue_knopf, self.play_knopf, self.weiter_knopf, self.name, self.lautstaerke):
            row.addWidget(w)
        self.abspieler.geaendert.connect(self.aktualisieren)
        self.abspieler.fehler.connect(lambda text: QMessageBox.warning(self, tr(TITEL), text))
        self.aktualisieren()

    def aktualisieren(self) -> None:
        a = self.abspieler
        self.play_knopf.setText("⏸" if a.laeuft else "▶")
        self.play_knopf.setToolTip(tr("Anhalten") if a.laeuft else tr("Abspielen"))
        self.play_knopf.setEnabled(a.laeuft or a.hat_quelle)
        self.weiter_knopf.setVisible(a.e.quelle == musik.MUSIK and len(a.e.dateien) > 1)
        text = a.text()
        self.name.setText(self.name.fontMetrics().elidedText(text, Qt.ElideRight, self.name.maximumWidth()))
        self.name.setToolTip(text)

    def dialog_zeigen(self) -> None:
        if self._dialog is None:
            self._dialog = MusikDialog(self.abspieler, self.window())
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()


class MusikDialog(QDialog):
    """Sender (mitgeliefert + eigene) und eigene Musik (Ordner, einzelne Dateien) auswählen."""

    def __init__(self, abspieler: Abspieler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.abspieler = abspieler
        self.e = abspieler.e
        self.setWindowTitle(tr(TITEL))
        self.resize(460, 420)
        tabs = QTabWidget()
        tabs.addTab(self._radio_seite(), tr("Radio"))
        tabs.addTab(self._musik_seite(), tr("Eigene Musik"))
        tabs.setCurrentIndex(1 if self.e.quelle == musik.MUSIK else 0)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        self.radio_fuellen()
        self.musik_fuellen()

    # -------------------------------------------------------------- Radio
    def _radio_seite(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.sender_liste = QListWidget()
        self.sender_liste.itemDoubleClicked.connect(lambda _i: self.sender_abspielen())
        self.sender_liste.currentItemChanged.connect(lambda *_: self._radio_knoepfe())
        hinweis = QLabel(tr(DATENSCHUTZ))
        hinweis.setObjectName("Muted")
        hinweis.setWordWrap(True)
        self.sender_play = QPushButton(tr("Abspielen"))
        self.sender_play.clicked.connect(self.sender_abspielen)
        neu = QPushButton(tr("Sender hinzufügen …"))
        neu.clicked.connect(self.sender_hinzufuegen)
        liste = QPushButton(tr("Wiedergabeliste öffnen …"))
        liste.setToolTip(tr("Sender aus einer .m3u- oder .pls-Datei übernehmen (nur https-Adressen)"))
        liste.clicked.connect(self.wiedergabeliste_oeffnen)
        self.sender_weg = QPushButton(tr("Entfernen"))
        self.sender_weg.clicked.connect(self.sender_entfernen)
        knoepfe = QHBoxLayout()
        for b in (self.sender_play, neu, liste, self.sender_weg):
            knoepfe.addWidget(b)
        lay.addWidget(self.sender_liste, 1)
        lay.addLayout(knoepfe)
        lay.addWidget(hinweis)
        return w

    def radio_fuellen(self) -> None:
        self.sender_liste.clear()
        for s in self.e.alle_sender():
            item = QListWidgetItem(tr("{name}  (eigener Sender)", name=s.name) if s.eigen else s.name)
            item.setData(Qt.UserRole, s.url)
            item.setToolTip(s.url)
            self.sender_liste.addItem(item)
            if s.url == self.e.sender_url:
                self.sender_liste.setCurrentItem(item)
        self._radio_knoepfe()

    def _radio_knoepfe(self) -> None:
        s = self._gewaehlter_sender()
        self.sender_play.setEnabled(s is not None)
        self.sender_weg.setEnabled(s is not None and s.eigen)

    def _gewaehlter_sender(self) -> musik.Sender | None:
        item = self.sender_liste.currentItem()
        return self.e.sender(item.data(Qt.UserRole)) if item else None

    def sender_abspielen(self) -> None:
        if s := self._gewaehlter_sender():
            self.abspieler.radio(s)

    def sender_hinzufuegen(self) -> None:
        name, ok = QInputDialog.getText(self, tr(TITEL), tr("Name des Senders:"))
        if not ok:
            return
        url, ok = QInputDialog.getText(self, tr(TITEL), tr("Stream-Adresse (beginnt mit https://):"))
        if not ok:
            return
        try:
            self.e.sender_hinzufuegen(musik.Sender(name, url))
        except musik.MusikFehler as err:
            QMessageBox.warning(self, tr(TITEL), str(err))
            return
        musik.speichern(self.e)
        self.radio_fuellen()
        self.sender_liste.setCurrentRow(self.sender_liste.count() - 1)   # der neue Sender steht unten

    def wiedergabeliste_oeffnen(self) -> None:
        pfad, _ = QFileDialog.getOpenFileName(self, tr("Wiedergabeliste öffnen"), str(Path.home()),
                                              tr("Wiedergabelisten (*.m3u *.m3u8 *.pls)"))
        if not pfad:
            return
        try:
            gefunden = musik.wiedergabeliste_lesen(Path(pfad))
        except musik.MusikFehler as err:
            QMessageBox.warning(self, tr(TITEL), str(err))
            return
        neu = 0
        for s in gefunden:
            try:
                self.e.sender_hinzufuegen(s)
                neu += 1
            except musik.MusikFehler:
                continue   # schon vorhanden oder Höchstzahl erreicht
        musik.speichern(self.e)
        self.radio_fuellen()
        QMessageBox.information(self, tr(TITEL), tr("{neu} "
                                                    "Sender "
                                                    "übernommen.", neu=neu) if neu else tr("Keine neuen Sender "
                                                                                           "gefunden."))

    def sender_entfernen(self) -> None:
        s = self._gewaehlter_sender()
        if not s or not s.eigen:
            return
        if self.abspieler.e.quelle == musik.RADIO and self.e.sender_url == s.url:
            self.abspieler.stop()
        self.e.sender_entfernen(s.url)
        musik.speichern(self.e)
        self.radio_fuellen()
        self.abspieler.geaendert.emit()

    # -------------------------------------------------------------- eigene Musik
    def _musik_seite(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.titel_liste = QListWidget()
        self.titel_liste.itemDoubleClicked.connect(lambda _i: self.musik_abspielen())
        self.titel_play = QPushButton(tr("Abspielen"))
        self.titel_play.clicked.connect(self.musik_abspielen)
        ordner = QPushButton(tr("Ordner hinzufügen …"))
        ordner.clicked.connect(self.ordner_hinzufuegen)
        dateien = QPushButton(tr("Dateien hinzufügen …"))
        dateien.clicked.connect(self.dateien_hinzufuegen)
        self.leeren = QPushButton(tr("Liste leeren"))
        self.leeren.clicked.connect(self.liste_leeren)
        self.zufall = QCheckBox(tr("Zufällige Reihenfolge"))
        self.zufall.setChecked(self.e.zufall)
        self.zufall.toggled.connect(self._zufall)
        knoepfe = QHBoxLayout()
        for b in (self.titel_play, ordner, dateien, self.leeren):
            knoepfe.addWidget(b)
        lay.addWidget(self.titel_liste, 1)
        lay.addLayout(knoepfe)
        lay.addWidget(self.zufall)
        return w

    def musik_fuellen(self) -> None:
        self.titel_liste.clear()
        for p in self.e.dateien:
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            self.titel_liste.addItem(item)
        if self.e.dateien:
            self.titel_liste.setCurrentRow(self.e.titel)
        self.titel_play.setEnabled(bool(self.e.dateien))
        self.leeren.setEnabled(bool(self.e.dateien))

    def _start_ordner(self) -> str:
        return self.e.ordner if self.e.ordner and Path(self.e.ordner).is_dir() else \
            QStandardPaths.writableLocation(QStandardPaths.MusicLocation) or str(Path.home())

    def ordner_hinzufuegen(self) -> None:
        ordner = QFileDialog.getExistingDirectory(self, tr("Musikordner wählen"), self._start_ordner())
        if not ordner:
            return
        try:
            gefunden = musik.titel_im_ordner(Path(ordner))
        except musik.MusikFehler as err:
            QMessageBox.warning(self, tr(TITEL), str(err))
            return
        self.e.ordner = ordner
        self._hinzu(gefunden, tr("Im Ordner „{name}“ ist keine Musik (MP3, OGG, FLAC, M4A, WAV).",
                                 name=Path(ordner).name))

    def dateien_hinzufuegen(self) -> None:
        endungen = " ".join(f"*{x}" for x in sorted(musik.MUSIK_ENDUNGEN))
        pfade, _ = QFileDialog.getOpenFileNames(self, tr("Musik hinzufügen"), self._start_ordner(),
                                                tr("Musik ({endungen})", endungen=endungen))
        if pfade:
            self._hinzu([Path(p) for p in pfade], tr("Keine Musikdatei gewählt."))

    def _hinzu(self, pfade: list[Path], leer: str) -> None:
        if not self.e.dateien_hinzufuegen(pfade) and not pfade:
            QMessageBox.information(self, tr(TITEL), leer)
        musik.speichern(self.e)
        self.musik_fuellen()
        self.abspieler.geaendert.emit()

    def liste_leeren(self) -> None:
        if self.e.quelle == musik.MUSIK:
            self.abspieler.stop()
            self.e.quelle = ""
        self.e.dateien, self.e.titel = [], 0
        musik.speichern(self.e)
        self.musik_fuellen()
        self.abspieler.geaendert.emit()

    def _zufall(self, an: bool) -> None:
        self.e.zufall = an
        musik.speichern(self.e)

    def musik_abspielen(self) -> None:
        if self.e.dateien:
            self.abspieler.musik(max(0, self.titel_liste.currentRow()))


def leiste(parent: QWidget | None = None) -> MusikLeiste | None:
    """Die Leiste – oder ``None``, wenn Qt Multimedia fehlt (dann bleibt die Statusleiste wie bisher)."""
    if not verfuegbar():
        return None
    try:
        return MusikLeiste(parent)
    except Exception as e:  # noqa: BLE001 – Musik darf das Hauptfenster nie verhindern
        print(f"{APP_NAME}: {TITEL} nicht verfügbar: {e}")
        return None
