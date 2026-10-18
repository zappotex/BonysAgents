# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Kurspaket-Anleitung“: die Schritte der aktuellen Lektion neben dem Agent-PC (beide Editionen).

Eigenes, schmales Fenster in Bony's Agents (nicht im Agent-PC und nicht im Kursraum – Begründung in
``docs/dev/plan-kurspakete.md``): Es steht standardmäßig über allen Fenstern am rechten Bildschirmrand, damit man
neben dem QEMU-Fenster des Agent-PCs lesen kann. Zurück/Weiter, Lektionswahl, Fortschritt; in der
Kursleiter-Edition zusätzlich die Notizen für die Kursleitung und der Ablaufplan.

Die Anzeige lädt nur Bilder aus dem Kurspaket selbst (nichts aus dem Internet, keine anderen Dateien des Rechners),
zeigt kein HTML und öffnet Links nur nach Klick und nur mit https im Browser.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)

from bonys_agents import edition, kurspaket, storage, vm

from . import style
from .widgets import open_url

BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
EINSTELLUNG = "kurspaket_anleitung"      # Position/Größe und „Immer im Vordergrund“
BREITE = 440
_FENSTER: dict[str, AnleitungFenster] = {}


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

    def loadResource(self, art: int, url: QUrl):
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
        self.zusatz = ""      # "handout" / "ablaufplan": statt der Lektion anzeigen

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
        self.auswahl.setToolTip("Lektion wählen")
        kopf.addWidget(self.auswahl, 1)
        self.mehr = QPushButton("⋯")
        self.mehr.setObjectName("Quiet")
        self.mehr.setToolTip("Handout, Ablaufplan, Fortschritt zurücksetzen")
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

        self.aufgabe = QFrame()
        self.aufgabe.setObjectName("Hint")
        al = QVBoxLayout(self.aufgabe)
        al.setContentsMargins(10, 8, 10, 8)
        self.aufgabe_text = QLabel()
        self.aufgabe_text.setWordWrap(True)
        self.aufgabe_text.setTextFormat(Qt.PlainText)
        al.addWidget(self.aufgabe_text)
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

        self.zurueck.clicked.connect(lambda: self._gehe(self.fortschritt.lektion - 1))
        self.weiter.clicked.connect(self._weiter)
        self.auswahl.activated.connect(lambda i: self._gehe(self.auswahl.itemData(i)))
        self.pc_knopf.clicked.connect(self._agent_pc)
        self.oben.toggled.connect(self._vordergrund)

        einst = storage.load_settings().get(EINSTELLUNG) or {}
        self._platzieren(einst.get("geometrie"))
        self.oben.setChecked(einst.get("vordergrund", True) is not False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pc_status)
        self.timer.start(3000)
        self._zeigen()

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
        m.addAction("Fortschritt zurücksetzen …", self._zuruecksetzen)
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

    # ---------------------------------------------------------------- Anzeige
    def _zeigen(self) -> None:
        p, f = self.paket, self.fortschritt
        n = len(p.lektionen)
        self.balken.setValue(f.fertig(p))
        self.balken.setFormat(f"{f.fertig(p)} von {n} Lektionen erledigt" if n else "Keine Lektionen")
        self._pc_status()
        hat_lektionen = n > 0 and not self.zusatz
        for w in (self.zurueck, self.weiter, self.auswahl):
            w.setEnabled(hat_lektionen)
        if not hat_lektionen:
            self.aufgabe.setVisible(False)
            self.notiz_knopf.setVisible(False)
            self.notiz.setVisible(False)
            if self.zusatz == "ablaufplan":
                self.info.setText("Ablaufplan für die Kursleitung")
                self.ansicht.zeigen(p.ablaufplan(), p.pfad, p.pfad)
            else:
                self.info.setText("Handout" if p.handout_datei.is_file() else "")
                self.ansicht.zeigen(p.handout() or p.beschreibung, p.pfad, p.pfad)
            if self.zusatz:
                self.zurueck.setEnabled(bool(n))
                self.zurueck.setText("◀  Zur Lektion")
            return
        self.zurueck.setText("◀  Zurück")
        i = max(0, min(f.lektion, n - 1))
        lek = p.lektionen[i]
        self.auswahl.setCurrentIndex(i)
        erledigt = "  ✓ erledigt" if lek.ordner in f.erledigt else ""
        teile = [f"Lektion {i + 1} von {n}", f"{f.fertig(p)} erledigt"]
        if lek.dauer_minuten:
            teile.append(f"{lek.dauer_minuten} min")
        if lek.art:
            teile.append(lek.art)
        self.info.setText(" · ".join(teile) + erledigt + (f"\nZiel: {lek.ziel}" if lek.ziel else ""))
        try:
            self.ansicht.zeigen(lek.anleitung(), lek.pfad, p.pfad)
        except kurspaket.PaketFehler as e:
            self.ansicht.setPlainText(str(e))
        pr = lek.pruefung
        self.aufgabe.setVisible(pr is not None)
        if pr is not None:
            self.aufgabe_text.setText(f"Prüfaufgabe: {pr.aufgabe or kurspaket.EINGEBAUTE_PRUEFUNGEN.get(pr.typ, '')}")
        notiz = lek.kursleitung() if edition.IS_TRAINER else ""
        self.notiz_knopf.setVisible(bool(notiz))
        if notiz:
            self.notiz.zeigen(notiz, lek.pfad, p.pfad)
        self.notiz.setVisible(bool(notiz) and self.notiz_knopf.isChecked())
        self.zurueck.setEnabled(i > 0)
        letzte = i == n - 1
        self.weiter.setText("Abschließen  ✓" if letzte else "Weiter  ▶")

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
        try:
            m = vm.get(name)
        except (KeyError, OSError, ValueError, RuntimeError):
            self.pc_text.setText(f"Agent-PC „{name}“ ist nicht verfügbar.")
            self.pc_knopf.setEnabled(False)
            return
        status = m.status()
        self.pc_text.setText(f"Agent-PC „{name}“: {status}")
        self.pc_text.setStyleSheet(f"color: {style.STATUS_COLORS.get(status, style.MUTED)};")
        self.pc_knopf.setEnabled(self.agent_pc_zeigen is not None)

    # ---------------------------------------------------------------- Bedienung
    def _gehe(self, index) -> None:
        if self.zusatz:
            self.zusatz = ""
        if isinstance(index, int) and self.paket.lektionen:
            self.fortschritt.gehe_zu(self.paket, index)
        self._zeigen()

    def _weiter(self) -> None:
        p, f = self.paket, self.fortschritt
        i = max(0, min(f.lektion, len(p.lektionen) - 1))
        f.erledigen(p.lektionen[i])
        if i == len(p.lektionen) - 1:
            f.speichern()
            self._zeigen()
            QMessageBox.information(self, p.name, f"Geschafft! Du hast „{p.name}“ durchgearbeitet.\n\n"
                                    f"{f.fertig(p)} von {len(p.lektionen)} Lektionen erledigt.")
            return
        f.gehe_zu(p, i + 1)
        self._zeigen()

    def _zuruecksetzen(self) -> None:
        if QMessageBox.question(self, self.paket.name, "Fortschritt in diesem Kurspaket zurücksetzen?\n\nDer Agent-PC "
                                "und seine Dateien bleiben unverändert – nur die Häkchen und die aktuelle Lektion "
                                "werden gelöscht.") != QMessageBox.Yes:
            return
        agent = self.fortschritt.agent_pc
        self.fortschritt = kurspaket.Fortschritt(self.paket.id, agent_pc=agent)
        self.fortschritt.speichern()
        self.zusatz = ""
        self._zeigen()

    def _agent_pc(self) -> None:
        if self.agent_pc_zeigen and self.fortschritt.agent_pc:
            self.agent_pc_zeigen(self.fortschritt.agent_pc)

    def moveEvent(self, e) -> None:  # noqa: N802
        super().moveEvent(e)
        if hasattr(self, "oben"):
            self._einstellung_merken_spaeter()

    def _einstellung_merken_spaeter(self) -> None:
        if not hasattr(self, "_merk_timer"):
            self._merk_timer = QTimer(self)
            self._merk_timer.setSingleShot(True)
            self._merk_timer.timeout.connect(self._einstellung_merken)
        self._merk_timer.start(800)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "oben"):
            self._einstellung_merken_spaeter()

    def closeEvent(self, e) -> None:  # noqa: N802
        self.timer.stop()
        self._einstellung_merken()
        _FENSTER.pop(self.paket.id, None)
        super().closeEvent(e)
