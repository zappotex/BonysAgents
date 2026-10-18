# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Kurspaket-Anleitung“: die Schritte der aktuellen Lektion neben dem Agent-PC (beide Editionen).

Eigenes, schmales Fenster in Bony's Agents (nicht im Agent-PC und nicht im Kursraum – Begründung in
``docs/dev/plan-kurspakete.md``): Es steht standardmäßig über allen Fenstern am rechten Bildschirmrand, damit man
neben dem QEMU-Fenster des Agent-PCs lesen kann. Zurück/Weiter, Lektionswahl („Zu Lektion X springen“),
Fortschritt, Prüfaufgabe („Prüfen“), Quiz und „Lektion zurücksetzen“; in der Kursleiter-Edition zusätzlich die
Notizen für die Kursleitung und der Ablaufplan.

Startzustände (``kurslauf``): Sobald eine Lektion zum ersten Mal betreten wird und der Agent-PC fertig ist, legt das
Fenster im Hintergrund ihren Startzustand an. Prüfungen und Startskripte laufen nur im Agent-PC.

Die Anzeige lädt nur Bilder aus dem Kurspaket selbst (nichts aus dem Internet, keine anderen Dateien des Rechners),
zeigt kein HTML und öffnet Links nur nach Klick und nur mit https im Browser.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QTextDocument
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QTextBrowser, QVBoxLayout, QWidget,
)

from bonys_agents import edition, kurslauf, kurspaket, storage, vm

from . import style
from .widgets import open_url
from .workers import TaskWorker

BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
EINSTELLUNG = "kurspaket_anleitung"      # Position/Größe und „Immer im Vordergrund“
BREITE = 440
_FENSTER: dict[str, AnleitungFenster] = {}
RESET_TEXT = ("Alles, was seit dem Beginn dieser Lektion im Agent-PC geändert wurde – auch eigene Dateien –, geht "
              "verloren. Der Agent-PC wird dafür heruntergefahren und wieder gestartet. Hast du etwas Wichtiges im "
              "Agent-PC, sichere es vorher.")


class MarkdownAnsicht(QTextBrowser):
    """Markdown ohne HTML; Bilder nur aus ``basis`` (dem Kurspaket), Links nur https im Browser."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.basis: Path | None = None
        self.ordner: Path | None = None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._link)

    def zeigen(self, text: str, ordner: Path, basis: Path) -> None:
        self.ordner, self.basis = ordner, basis
        self.document().setBaseUrl(QUrl.fromLocalFile(str(ordner) + "/"))
        features = QTextDocument.MarkdownFeature(QTextDocument.MarkdownDialectGitHub.value
                                                 | QTextDocument.MarkdownNoHTML.value)
        self.document().setMarkdown(kurspaket.markdown_fuer_anzeige(text), features)
        self.verticalScrollBar().setValue(0)

    def loadResource(self, art: int, url: QUrl):  # noqa: N802
        """Nur Bilder, nur aus dem Kurspaket – alles andere bleibt leer (kein Netz, keine fremden Dateien)."""
        if art != QTextDocument.ImageResource or self.basis is None or self.ordner is None:
            return None
        if url.scheme() not in ("", "file"):
            return None
        pfad = Path(url.toLocalFile()) if url.isLocalFile() else self.ordner / url.path()
        try:
            pfad = pfad.resolve()
            pfad.relative_to(self.basis.resolve())
        except (OSError, ValueError):
            return None
        if pfad.suffix.lower() not in BILD_ENDUNGEN or not pfad.is_file() or pfad.stat().st_size > 10 * 1024 ** 2:
            return None
        return super().loadResource(art, QUrl.fromLocalFile(str(pfad)))

    def _link(self, url: QUrl) -> None:
        if url.scheme() == "https":
            open_url(url.toString())
        elif not url.scheme() and url.fragment():
            self.scrollToAnchor(url.fragment())


class QuizDialog(QDialog):
    """Quiz am Ende einer Lektion: eine Frage nach der anderen, sofort mit Auflösung. Ergebnis bleibt lokal."""

    def __init__(self, titel: str, fragen: list[kurspaket.Frage], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Quiz – {titel}")
        self.fragen = fragen
        self.nr = 0
        self.richtig = 0
        self.beantwortet = False
        root = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setObjectName("Muted")
        root.addWidget(self.kopf)
        self.frage = QLabel()
        self.frage.setWordWrap(True)
        self.frage.setTextFormat(Qt.PlainText)
        f = self.frage.font()
        f.setBold(True)
        self.frage.setFont(f)
        root.addWidget(self.frage)
        self.gruppe = QButtonGroup(self)
        self.antworten_box = QVBoxLayout()
        root.addLayout(self.antworten_box)
        self.rueckmeldung = QLabel()
        self.rueckmeldung.setWordWrap(True)
        self.rueckmeldung.setTextFormat(Qt.PlainText)
        root.addWidget(self.rueckmeldung)
        root.addStretch(1)
        knoepfe = QHBoxLayout()
        self.spaeter = QPushButton("Später")
        self.knopf = QPushButton("Antworten")
        self.knopf.setObjectName("Primary")
        knoepfe.addWidget(self.spaeter)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.knopf)
        root.addLayout(knoepfe)
        self.spaeter.clicked.connect(self.reject)
        self.knopf.clicked.connect(self._weiter)
        self.resize(480, 340)
        self._zeigen()

    @property
    def ergebnis(self) -> list[int]:
        return [self.richtig, len(self.fragen)]

    def _zeigen(self) -> None:
        f = self.fragen[self.nr]
        self.kopf.setText(f"Frage {self.nr + 1} von {len(self.fragen)}")
        self.frage.setText(f.frage)
        for b in self.gruppe.buttons():
            self.gruppe.removeButton(b)
            b.deleteLater()
        for i, a in enumerate(f.antworten):
            rb = QRadioButton(a)
            self.gruppe.addButton(rb, i)
            self.antworten_box.addWidget(rb)
        self.rueckmeldung.setText("")
        self.rueckmeldung.setStyleSheet("")
        self.knopf.setText("Antworten")
        self.beantwortet = False

    def _weiter(self) -> None:
        if not self.beantwortet:
            wahl = self.gruppe.checkedId()
            if wahl < 0:
                self.rueckmeldung.setText("Bitte eine Antwort wählen.")
                return
            f = self.fragen[self.nr]
            ok = wahl == f.richtig
            self.richtig += ok
            text = "Richtig!" if ok else f"Leider nicht. Richtig ist: {f.antworten[f.richtig]}"
            self.rueckmeldung.setText(text + (f"\n{f.erklaerung}" if f.erklaerung else ""))
            self.rueckmeldung.setStyleSheet(f"color: {style.OK if ok else style.WARN};")
            for b in self.gruppe.buttons():
                b.setEnabled(False)
            self.beantwortet = True
            self.knopf.setText("Fertig" if self.nr == len(self.fragen) - 1 else "Nächste Frage")
            return
        if self.nr == len(self.fragen) - 1:
            self.accept()
            return
        self.nr += 1
        self._zeigen()


def oeffnen(paket: kurspaket.Kurspaket, agent_pc_zeigen: Callable[[str], None] | None = None,
            parent: QWidget | None = None) -> AnleitungFenster:
    """Fenster für dieses Kurspaket öffnen (oder nach vorn holen, wenn es schon offen ist)."""
    f = _FENSTER.get(paket.id)
    if f is None:
        f = AnleitungFenster(paket, agent_pc_zeigen, parent)
        _FENSTER[paket.id] = f
    f.show()
    f.raise_()
    f.activateWindow()
    return f


class AnleitungFenster(QWidget):
    def __init__(self, paket: kurspaket.Kurspaket, agent_pc_zeigen: Callable[[str], None] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.paket = paket
        self.agent_pc_zeigen = agent_pc_zeigen
        self.fortschritt = kurspaket.Fortschritt.laden(paket.id)
        self.setWindowTitle(f"{paket.name} – Anleitung")
        self.zusatz = ""                      # "handout" / "ablaufplan": statt der Lektion anzeigen
        self.arbeit: TaskWorker | None = None  # Prüfung, Zurücksetzen oder Startzustand im Hintergrund
        self.arbeit_text = ""
        self.startzustaende: set[str] | None = None   # None = noch nicht gelesen
        self.vorbereiten_fehler = ""
        self.ergebnis: dict[str, kurslauf.Ergebnis] = {}
        self._angezeigt: tuple[str, str] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        self.titel = QLabel(paket.name)
        self.titel.setObjectName("Title")
        self.titel.setWordWrap(True)
        root.addWidget(self.titel)

        kopf = QHBoxLayout()
        self.auswahl = QComboBox()
        for i, lek in enumerate(paket.lektionen, 1):
            self.auswahl.addItem(f"{i}. {lek.titel}", i - 1)
        self.auswahl.setToolTip("Zu Lektion springen")
        kopf.addWidget(self.auswahl, 1)
        self.mehr = QPushButton("⋯")
        self.mehr.setObjectName("Quiet")
        self.mehr.setToolTip("Handout, Ablaufplan, Startzustände, Fortschritt zurücksetzen")
        self.mehr.setMenu(self._menue())
        kopf.addWidget(self.mehr)
        root.addLayout(kopf)

        self.balken = QProgressBar()
        self.balken.setRange(0, max(1, len(paket.lektionen)))
        self.balken.setTextVisible(False)
        self.balken.setMaximumHeight(8)
        root.addWidget(self.balken)

        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        self.ansicht = MarkdownAnsicht()
        self.ansicht.setMinimumHeight(200)
        root.addWidget(self.ansicht, 1)

        # Prüfaufgabe, Quiz, Zurücksetzen
        self.aufgabe = QFrame()
        self.aufgabe.setObjectName("Hint")
        al = QVBoxLayout(self.aufgabe)
        al.setContentsMargins(10, 8, 10, 8)
        self.aufgabe_text = QLabel()
        self.aufgabe_text.setWordWrap(True)
        self.aufgabe_text.setTextFormat(Qt.PlainText)
        al.addWidget(self.aufgabe_text)
        self.ergebnis_text = QLabel()
        self.ergebnis_text.setWordWrap(True)
        self.ergebnis_text.setTextFormat(Qt.PlainText)
        al.addWidget(self.ergebnis_text)
        zeile = QHBoxLayout()
        self.pruefen_knopf = QPushButton("Prüfen")
        self.pruefen_knopf.setToolTip("Prüft im Agent-PC, ob die Aufgabe geschafft ist")
        self.quiz_knopf = QPushButton("Quiz")
        self.reset_knopf = QPushButton("↺  Zurücksetzen")
        self.reset_knopf.setToolTip("Lektion zurücksetzen: Agent-PC auf den Stand vom Beginn dieser Lektion")
        zeile.addWidget(self.pruefen_knopf)
        zeile.addWidget(self.quiz_knopf)
        zeile.addStretch(1)
        zeile.addWidget(self.reset_knopf)
        al.addLayout(zeile)
        root.addWidget(self.aufgabe)

        # Kursleiter-Edition: Notizen zur Lektion (aufklappbar)
        self.notiz_knopf = QPushButton("Notizen für die Kursleitung ▸")
        self.notiz_knopf.setObjectName("Quiet")
        self.notiz_knopf.setCheckable(True)
        self.notiz = MarkdownAnsicht()
        self.notiz.setMaximumHeight(180)
        self.notiz.setVisible(False)
        self.notiz_knopf.toggled.connect(self._notiz_umschalten)
        root.addWidget(self.notiz_knopf)
        root.addWidget(self.notiz)

        pc = QHBoxLayout()
        self.pc_text = QLabel()
        self.pc_text.setObjectName("Muted")
        self.pc_text.setWordWrap(True)
        self.pc_knopf = QPushButton("Agent-PC zeigen")
        self.pc_knopf.setToolTip("Den Agent-PC dieses Kurspakets im Hauptfenster wählen und starten bzw. zeigen")
        pc.addWidget(self.pc_text, 1)
        pc.addWidget(self.pc_knopf)
        root.addLayout(pc)

        unten = QHBoxLayout()
        self.zurueck = QPushButton("◀  Zurück")
        self.weiter = QPushButton("Weiter  ▶")
        self.weiter.setObjectName("Primary")
        self.oben = QCheckBox("Immer im Vordergrund")
        self.oben.setToolTip("Das Fenster bleibt über dem Agent-PC sichtbar")
        unten.addWidget(self.zurueck)
        unten.addWidget(self.oben, 1, Qt.AlignCenter)
        unten.addWidget(self.weiter)
        root.addLayout(unten)

        self.zurueck.clicked.connect(self._zurueck)
        self.weiter.clicked.connect(self._weiter)
        self.auswahl.activated.connect(lambda i: self._springen(self.auswahl.itemData(i)))
        self.pc_knopf.clicked.connect(self._agent_pc)
        self.oben.toggled.connect(self._vordergrund)
        self.pruefen_knopf.clicked.connect(self._pruefen)
        self.quiz_knopf.clicked.connect(lambda: self._quiz())
        self.reset_knopf.clicked.connect(lambda: self._zuruecksetzen_fragen(self._index()))

        einst = storage.load_settings().get(EINSTELLUNG) or {}
        self._platzieren(einst.get("geometrie"))
        self.oben.setChecked(einst.get("vordergrund", True) is not False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._takt)
        self.timer.start(3000)
        self._zeigen()
        QTimer.singleShot(0, self._takt)

    # ---------------------------------------------------------------- Aufbau
    def _menue(self) -> QMenu:
        m = QMenu(self)
        if self.paket.lektionen:
            m.addAction("Lektion anzeigen", lambda: self._zusatz(""))
        if self.paket.handout_datei.is_file():
            m.addAction("Handout anzeigen", lambda: self._zusatz("handout"))
        if edition.IS_TRAINER:
            m.addAction("Ablaufplan (Kursleitung) anzeigen", lambda: self._zusatz("ablaufplan"))
        m.addSeparator()
        m.addAction("Startzustände löschen …", self._startzustaende_loeschen)
        m.addAction("Fortschritt zurücksetzen …", self._fortschritt_zuruecksetzen)
        return m

    def _platzieren(self, geometrie) -> None:
        bildschirm = (self.parentWidget().screen() if self.parentWidget() else None) or QGuiApplication.primaryScreen()
        frei = bildschirm.availableGeometry()
        if isinstance(geometrie, list) and len(geometrie) == 4 and all(isinstance(x, int) for x in geometrie):
            x, y, w, h = geometrie
            if any(s.availableGeometry().intersects(QRect(x, y, w, h)) for s in QGuiApplication.screens()):
                self.setGeometry(x, y, max(320, w), max(400, h))
                return
        w = min(BREITE, frei.width() // 3)
        self.setGeometry(frei.right() - w - 8, frei.top() + 40, w, max(400, frei.height() - 80))

    def _vordergrund(self, an: bool) -> None:
        sichtbar = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, an)
        if sichtbar:
            self.show()
        self._einstellung_merken()

    def _einstellung_merken(self) -> None:
        g = self.geometry()
        s = storage.load_settings()
        s[EINSTELLUNG] = {"geometrie": [g.x(), g.y(), g.width(), g.height()], "vordergrund": self.oben.isChecked()}
        try:
            storage.save_settings(s)
        except OSError:
            pass

    # ---------------------------------------------------------------- Zustand
    def _index(self) -> int:
        return max(0, min(self.fortschritt.lektion, len(self.paket.lektionen) - 1))

    def maschine(self) -> vm.VM | None:
        name = self.fortschritt.agent_pc
        if not name:
            return None
        try:
            return vm.get(name)
        except (KeyError, OSError, ValueError, RuntimeError):
            return None

    def beschaeftigt(self) -> bool:
        """Bis das Ergebnis der Arbeit im Hintergrund ausgewertet ist (nicht nur, solange der Thread läuft)."""
        return self.arbeit is not None

    def _im_hintergrund(self, text: str, fn, fertig: Callable[[TaskWorker], None]) -> None:
        w = TaskWorker(fn)
        self.arbeit = w
        self.arbeit_text = text

        def ende() -> None:
            if self.arbeit is w:
                self.arbeit = None
            fertig(w)
            self._zeigen()

        w.finished.connect(ende)
        w.start()
        self._zeigen()

    # ---------------------------------------------------------------- Anzeige
    def _zeigen(self) -> None:
        p, f = self.paket, self.fortschritt
        n = len(p.lektionen)
        self.balken.setValue(f.fertig(p))
        self._pc_status()
        beschaeftigt = self.beschaeftigt()
        hat_lektionen = n > 0 and not self.zusatz
        for w in (self.zurueck, self.weiter, self.auswahl):
            w.setEnabled(hat_lektionen and not beschaeftigt)
        if not hat_lektionen:
            self.aufgabe.setVisible(False)
            self.notiz_knopf.setVisible(False)
            self.notiz.setVisible(False)
            if self._angezeigt != ("", self.zusatz):
                if self.zusatz == "ablaufplan":
                    self.ansicht.zeigen(p.ablaufplan(), p.pfad, p.pfad)
                else:
                    self.ansicht.zeigen(p.handout() or p.beschreibung, p.pfad, p.pfad)
                self._angezeigt = ("", self.zusatz)
            self.info.setText({"ablaufplan": "Ablaufplan für die Kursleitung"}.get(
                self.zusatz, "Handout" if p.handout_datei.is_file() else ""))
            if self.zusatz:
                self.zurueck.setEnabled(bool(n))
                self.zurueck.setText("◀  Zur Lektion")
            return
        self.zurueck.setText("◀  Zurück")
        i = self._index()
        lek = p.lektionen[i]
        if self.auswahl.currentIndex() != i:
            self.auswahl.setCurrentIndex(i)
        teile = [f"Lektion {i + 1} von {n}", f"{f.fertig(p)} erledigt"]
        if lek.dauer_minuten:
            teile.append(f"{lek.dauer_minuten} min")
        if lek.art:
            teile.append(lek.art)
        zeilen = [" · ".join(teile) + ("  ✓" if lek.ordner in f.erledigt else "")]
        if lek.ziel:
            zeilen.append(f"Ziel: {lek.ziel}")
        zeilen.append(self._startzustand_text(lek))
        self.info.setText("\n".join(z for z in zeilen if z))
        if self._angezeigt != (lek.ordner, "anleitung"):
            try:
                self.ansicht.zeigen(lek.anleitung(), lek.pfad, p.pfad)
            except kurspaket.PaketFehler as e:
                self.ansicht.setPlainText(str(e))
            self._angezeigt = (lek.ordner, "anleitung")

        pr = lek.pruefung
        hat_start = self.startzustaende is not None and lek.ordner in self.startzustaende
        self.aufgabe.setVisible(pr is not None or lek.hat_quiz or hat_start or beschaeftigt)
        self.aufgabe_text.setVisible(pr is not None)
        self.pruefen_knopf.setVisible(pr is not None)
        if pr is not None:
            was = pr.aufgabe or kurspaket.EINGEBAUTE_PRUEFUNGEN.get(pr.typ, "")
            self.aufgabe_text.setText(f"Prüfaufgabe: {was}" if was else "Prüfaufgabe zu dieser Lektion")
        e = self.ergebnis.get(lek.ordner)
        if beschaeftigt:
            text, farbe = self.arbeit_text or "Bitte warten …", style.MUTED
        elif e is not None:
            text, farbe = ("✓ " if e.geschafft else "✗ ") + e.text, style.OK if e.geschafft else style.WARN
        elif pr is not None and lek.ordner in f.pruefungen:
            ok = f.pruefungen[lek.ordner]
            text, farbe = ("✓ Schon geschafft." if ok else "Beim letzten Prüfen noch nicht geschafft."), \
                (style.OK if ok else style.MUTED)
        else:
            text, farbe = "", style.MUTED
        self.ergebnis_text.setText(text)
        self.ergebnis_text.setStyleSheet(f"color: {farbe};")
        self.ergebnis_text.setVisible(bool(text))
        self.quiz_knopf.setVisible(lek.hat_quiz)
        q = f.quiz.get(lek.ordner)
        self.quiz_knopf.setText(f"Quiz ({q[0]}/{q[1]})" if q else "Quiz")
        self.reset_knopf.setVisible(hat_start)
        for b in (self.reset_knopf, self.pruefen_knopf, self.quiz_knopf):
            b.setEnabled(not beschaeftigt)

        notiz = lek.kursleitung() if edition.IS_TRAINER else ""
        self.notiz_knopf.setVisible(bool(notiz))
        if notiz and self._notiz_ordner != lek.ordner:
            self.notiz.zeigen(notiz, lek.pfad, p.pfad)
            self._notiz_ordner = lek.ordner
        self.notiz.setVisible(bool(notiz) and self.notiz_knopf.isChecked())
        self.zurueck.setEnabled(i > 0 and not beschaeftigt)
        self.weiter.setText("Abschließen  ✓" if i == n - 1 else "Weiter  ▶")

    _notiz_ordner = ""

    def _startzustand_text(self, lek: kurspaket.Lektion) -> str:
        if self.maschine() is None or self.startzustaende is None:
            return ""
        if lek.ordner in self.startzustaende:
            return "Startzustand gesichert – die Lektion lässt sich zurücksetzen."
        if self.vorbereiten_fehler:
            return f"Startzustand: {self.vorbereiten_fehler}"
        return "Der Startzustand wird gesichert, sobald der Agent-PC fertig ist."

    def _notiz_umschalten(self, an: bool) -> None:
        self.notiz_knopf.setText("Notizen für die Kursleitung " + ("▾" if an else "▸"))
        self.notiz.setVisible(an)

    def _zusatz(self, was: str) -> None:
        self.zusatz = was
        self._zeigen()

    def _pc_status(self) -> None:
        name = self.fortschritt.agent_pc
        if not name:
            self.pc_text.setText("Noch kein Agent-PC für dieses Kurspaket.")
            self.pc_knopf.setEnabled(False)
            return
        m = self.maschine()
        if m is None:
            self.pc_text.setText(f"Agent-PC „{name}“ ist nicht verfügbar.")
            self.pc_text.setStyleSheet("")
            self.pc_knopf.setEnabled(False)
            return
        status = m.status()
        self.pc_text.setText(f"Agent-PC „{name}“: {status}")
        self.pc_text.setStyleSheet(f"color: {style.STATUS_COLORS.get(status, style.MUTED)};")
        self.pc_knopf.setEnabled(self.agent_pc_zeigen is not None)

    # ---------------------------------------------------------------- Startzustände im Hintergrund
    def _takt(self) -> None:
        """Alle paar Sekunden: Startzustände lesen; fehlt der der aktuellen Lektion, ihn sichern, sobald es geht."""
        if self.beschaeftigt() or not self.paket.lektionen:
            self._pc_status()
            return
        m = self.maschine()
        if m is None:
            self._zeigen()
            return
        self.startzustaende = kurslauf.startzustaende(m, self.paket)
        index = self._index()
        lek = self.paket.lektionen[index]
        if lek.ordner in self.startzustaende:
            self._zeigen()
            return
        # Erst wenn der Agent-PC fertig eingerichtet ist – sonst sicherte man den halb installierten Zustand
        try:
            fertig = m.progress().ready and not m.config.first_boot_pending
        except (OSError, ValueError):
            fertig = False
        skript_noetig = lek.start is not None or any(
            x.start and x.ordner not in self.startzustaende for x in self.paket.lektionen[:index])
        if not fertig or ((skript_noetig or m.is_running()) and not kurslauf.bereit(m)):
            self._zeigen()
            return

        def fertig_cb(w: TaskWorker) -> None:
            self.vorbereiten_fehler = str(w.error) if w.error is not None else ""
            self.startzustaende = kurslauf.startzustaende(m, self.paket)

        self._im_hintergrund("Startzustand der Lektion wird gesichert …",
                             lambda: kurslauf.lektion_vorbereiten(m, self.paket, index), fertig_cb)

    # ---------------------------------------------------------------- Bedienung
    def _gehe(self, index) -> None:
        self.zusatz = ""
        if isinstance(index, int) and self.paket.lektionen:
            self.fortschritt.gehe_zu(self.paket, index)
        self.vorbereiten_fehler = ""
        self._zeigen()
        QTimer.singleShot(0, self._takt)

    def _zurueck(self) -> None:
        self._gehe(self._index() if self.zusatz else self._index() - 1)

    def _weiter(self) -> None:
        p, f = self.paket, self.fortschritt
        i = self._index()
        lek = p.lektionen[i]
        if lek.hat_quiz and lek.ordner not in f.quiz:
            if QMessageBox.question(self, p.name, "Zu dieser Lektion gibt es ein kurzes Quiz. Jetzt machen?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                self._quiz()
        f.erledigen(lek)
        if i == len(p.lektionen) - 1:
            f.speichern()
            self._zeigen()
            QMessageBox.information(self, p.name, f"Geschafft! Du hast „{p.name}“ durchgearbeitet.\n\n"
                                    f"{f.fertig(p)} von {len(p.lektionen)} Lektionen erledigt.")
            return
        self._gehe(i + 1)

    def _springen(self, ziel) -> None:
        """„Zu Lektion X springen“: gibt es ihren Startzustand, wahlweise nur ansehen oder zurücksetzen."""
        if not isinstance(ziel, int) or ziel == self._index():
            self._zeigen()
            return
        lek = self.paket.lektionen[ziel]
        if self.startzustaende and lek.ordner in self.startzustaende and self.maschine() is not None:
            box = QMessageBox(QMessageBox.Question, self.paket.name, f"Zu Lektion {ziel + 1} „{lek.titel}“",
                              QMessageBox.NoButton, self)
            box.setInformativeText("Nur die Anleitung ansehen – oder auch den Agent-PC auf den Stand vom Beginn "
                                   "dieser Lektion zurücksetzen?\n\n" + RESET_TEXT)
            ansehen = box.addButton("Nur ansehen", QMessageBox.AcceptRole)
            reset = box.addButton("Zurücksetzen", QMessageBox.DestructiveRole)
            box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.setDefaultButton(ansehen)
            box.exec()
            if box.clickedButton() is reset:
                self._gehe(ziel)
                self._zuruecksetzen(ziel)
            elif box.clickedButton() is ansehen:
                self._gehe(ziel)
            else:
                self._zeigen()
            return
        self._gehe(ziel)

    def _zuruecksetzen_fragen(self, index: int) -> None:
        lek = self.paket.lektionen[index]
        box = QMessageBox(QMessageBox.Warning, self.paket.name, f"Lektion {index + 1} „{lek.titel}“ zurücksetzen?",
                          QMessageBox.NoButton, self)
        box.setInformativeText(RESET_TEXT)
        ja = box.addButton("Zurücksetzen", QMessageBox.DestructiveRole)
        nein = box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.setDefaultButton(nein)
        box.exec()
        if box.clickedButton() is ja:
            self._zuruecksetzen(index)

    def _zuruecksetzen(self, index: int) -> None:
        m = self.maschine()
        if m is None:
            return

        def fertig(w: TaskWorker) -> None:
            self.startzustaende = kurslauf.startzustaende(m, self.paket)
            if w.error is not None:
                QMessageBox.warning(self, self.paket.name, f"Zurücksetzen nicht möglich:\n\n{w.error}")
                return
            for spaeter in self.paket.lektionen[index:]:
                self.ergebnis.pop(spaeter.ordner, None)
                if spaeter.ordner in self.fortschritt.erledigt:
                    self.fortschritt.erledigt.remove(spaeter.ordner)
                self.fortschritt.pruefungen.pop(spaeter.ordner, None)
            self.fortschritt.gehe_zu(self.paket, index)

        self._im_hintergrund("Agent-PC wird zurückgesetzt und neu gestartet …",
                             lambda: kurslauf.lektion_zuruecksetzen(m, self.paket, index), fertig)

    def _pruefen(self) -> None:
        lek = self.paket.lektionen[self._index()]
        m = self.maschine()

        def fertig(w: TaskWorker) -> None:
            if isinstance(w.error, kurslauf.NichtBereit):
                self.ergebnis[lek.ordner] = kurslauf.Ergebnis(False, str(w.error))
                return
            if w.error is not None:
                self.ergebnis[lek.ordner] = kurslauf.Ergebnis(False, f"Prüfen ging nicht: {w.error}")
                return
            e: kurslauf.Ergebnis = w.result
            self.ergebnis[lek.ordner] = e
            self.fortschritt.pruefungen[lek.ordner] = e.geschafft
            self.fortschritt.speichern()

        self._im_hintergrund("Wird im Agent-PC geprüft …", lambda: kurslauf.pruefen(m, self.paket, lek), fertig)

    def _quiz(self) -> None:
        lek = self.paket.lektionen[self._index()]
        try:
            fragen = lek.quiz()
        except kurspaket.PaketFehler as e:
            QMessageBox.warning(self, self.paket.name, str(e))
            return
        if not fragen:
            return
        dlg = QuizDialog(lek.titel, fragen, self)
        if dlg.exec():
            self.fortschritt.quiz[lek.ordner] = dlg.ergebnis
            self.fortschritt.speichern()
            self._zeigen()

    def _startzustaende_loeschen(self) -> None:
        m = self.maschine()
        if m is None or self.beschaeftigt():
            return
        if QMessageBox.question(self, self.paket.name, "Alle gesicherten Startzustände dieses Kurspakets löschen?\n\n"
                                "Das gibt Speicherplatz frei. Zurücksetzen geht danach erst wieder für Lektionen, "
                                "die neu betreten werden. Der Agent-PC selbst bleibt unverändert.") \
                != QMessageBox.Yes:
            return

        def fertig(w: TaskWorker) -> None:
            self.startzustaende = kurslauf.startzustaende(m, self.paket)
            if w.error is not None:
                QMessageBox.warning(self, self.paket.name, str(w.error))

        self._im_hintergrund("Startzustände werden gelöscht …", lambda: kurslauf.alle_loeschen(m, self.paket),
                             fertig)

    def _fortschritt_zuruecksetzen(self) -> None:
        if QMessageBox.question(self, self.paket.name, "Fortschritt in diesem Kurspaket zurücksetzen?\n\nDer Agent-PC "
                                "und seine Dateien bleiben unverändert – nur die Häkchen, Prüf- und Quiz-Ergebnisse "
                                "und die aktuelle Lektion werden gelöscht.") != QMessageBox.Yes:
            return
        alt = self.fortschritt
        self.fortschritt = kurspaket.Fortschritt(self.paket.id, agent_pc=alt.agent_pc,
                                                 skripte_erlaubt=alt.skripte_erlaubt)
        self.fortschritt.speichern()
        self.ergebnis.clear()
        self._gehe(0)

    def _agent_pc(self) -> None:
        if self.agent_pc_zeigen and self.fortschritt.agent_pc:
            self.agent_pc_zeigen(self.fortschritt.agent_pc)

    # ---------------------------------------------------------------- Fenster
    def moveEvent(self, e) -> None:  # noqa: N802
        super().moveEvent(e)
        if hasattr(self, "oben"):
            self._einstellung_merken_spaeter()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "oben"):
            self._einstellung_merken_spaeter()

    def _einstellung_merken_spaeter(self) -> None:
        if not hasattr(self, "_merk_timer"):
            self._merk_timer = QTimer(self)
            self._merk_timer.setSingleShot(True)
            self._merk_timer.timeout.connect(self._einstellung_merken)
        self._merk_timer.start(800)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.beschaeftigt():
            QMessageBox.information(self, self.paket.name, "Bitte warten, bis der Agent-PC fertig ist.")
            e.ignore()
            return
        self.timer.stop()
        self._einstellung_merken()
        _FENSTER.pop(self.paket.id, None)
        super().closeEvent(e)
