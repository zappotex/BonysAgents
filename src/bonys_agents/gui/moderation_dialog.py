# SPDX-License-Identifier: GPL-3.0-or-later
"""Lokaler Moderationsbildschirm für Kursportal-Einreichungen (Kursleiter-Edition, Menü des Hauptfensters).

Zeigt die Einreichungen einer ``Moderation``-Ablage mit Prüfbericht und Verlauf; Entscheidungen
(freigeben, ablehnen, veröffentlichen, zurückziehen) brauchen Akteur und Begründung. Der Dialog führt nichts aus
und öffnet keine Paketinhalte – er zeigt nur den sanitisierten Bericht.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from pathlib import Path

from bonys_agents import kurspaket, kurspaket_moderation as mod, kurspaket_moderation_client as online, storage

STATUS_TEXT = {
    mod.UPLOADED: "Eingereicht", mod.SCANNING: "Wird geprüft", mod.NEEDS_REVIEW: "Braucht Prüfung",
    mod.APPROVED: "Freigegeben (nicht veröffentlicht)", mod.PUBLISHED: "Veröffentlicht",
    mod.REJECTED: "Abgelehnt", mod.WITHDRAWN: "Zurückgezogen",
}
# Aktion -> (Beschriftung, Zielstatus)
AKTIONEN = {
    "freigeben": ("Freigeben", mod.APPROVED),
    "ablehnen": ("Ablehnen", mod.REJECTED),
    "veroeffentlichen": ("Veröffentlichen", mod.PUBLISHED),
    "zurueckziehen": ("Zurückziehen", mod.WITHDRAWN),
}


def bericht_text(m, sid: str) -> str:
    """Prüfbericht und Verlauf als Klartext – ohne Fundwerte. Paketdaten sind fremder Text und werden nie als
    Markdown oder HTML dargestellt."""
    b = m.bericht(sid) or {}
    zeilen = [f"{b.get('name') or '(ohne Namen)'} · Version {b.get('version') or '–'}",
              f"Paket-ID: {b.get('paket_id') or '–'} · {b.get('groesse', 0)} Bytes",
              f"SHA-256: {b.get('sha256') or '–'}", ""]
    if not getattr(m, "kette_ok", lambda _sid: True)(sid):
        zeilen += ["ACHTUNG: Der Verlauf dieser Einreichung ist verändert worden. Nicht entscheiden.", ""]
    for titel, schluessel in (("Befunde", "findings"), ("Skripte", "skripte"),
                              ("Externe Links", "externe_links"), ("Fundstellen (ohne Werte)", "fundstellen")):
        if b.get(schluessel):
            zeilen += [f"{titel}:"] + [f"  - {x}" for x in b[schluessel]] + [""]
    zeilen += ["Verlauf:"]
    for e in m.verlauf(sid):
        zeilen.append(f"  {e.nr}. {e.zeit} · {STATUS_TEXT.get(e.nach, e.nach)} · {e.akteur}: {e.begruendung}")
    return "\n".join(zeilen)


ART_TEXT = {"text": "Text", "skript": "Skript – wird nie ausgeführt", "bild": "Bild – wird nicht angezeigt",
            "sonstig": "keine Vorschau"}


class InhaltDialog(QDialog):
    """Zeigt die Dateien eines eingereichten Pakets als Klartext. Nichts wird ausgeführt, kein Bild geöffnet,
    kein Markdown/HTML gerendert; das Paket wurde mit allen Schutzgrenzen von ``kurspaket.entpacken`` gelesen."""

    def __init__(self, dateien: list[online.InhaltsDatei], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Kursportal – Paketinhalt (nur Ansicht)")
        self.dateien = dateien
        lay = QVBoxLayout(self)
        hinweis = QLabel("Nur Ansicht: Skripte laufen hier nie, Bilder und Links werden nicht geöffnet.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        zeile = QHBoxLayout()
        self.liste = QListWidget()
        self.liste.addItems([f"{d.pfad}  ({ART_TEXT.get(d.art, '')}, {d.groesse} Bytes)" for d in dateien])
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        zeile.addWidget(self.liste, 1)
        zeile.addWidget(self.text, 2)
        lay.addLayout(zeile, 1)
        self.liste.currentRowChanged.connect(self._zeigen)
        self.resize(900, 560)
        if dateien:
            self.liste.setCurrentRow(0)

    def _zeigen(self, zeile: int) -> None:
        d = self.dateien[zeile] if 0 <= zeile < len(self.dateien) else None
        self.text.setPlainText("" if d is None else d.text or f"({ART_TEXT.get(d.art, '')})")


def lokale_ablage() -> mod.Moderation:
    """Die lokale Ablage dieses Rechners; IDs der mitgelieferten Kurspakete sind für Einreichungen gesperrt."""
    reserviert = {p.id for p in kurspaket.liste() if p.mitgeliefert}
    return mod.Moderation(storage.data_dir() / "kursportal-ablage", reserviert)


class ModerationDialog(QDialog):
    def __init__(self, ablage: mod.Moderation, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Kursportal – Moderation")
        self.lokal = self.ablage = ablage
        self.online: online.OnlineAblage | None = None
        lay = QVBoxLayout(self)
        intro = QLabel("Lokale Moderation auf diesem Rechner: Nichts wird hier veröffentlicht oder hochgeladen und der "
                       "Online-Katalog bleibt unverändert. Jede Entscheidung wird mit Akteur und Begründung "
                       "unveränderlich im Verlauf festgehalten.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        quelle = QHBoxLayout()
        self.quelle = QComboBox()
        self.quelle.addItems(["Lokal (dieser Rechner)", "Online (Kursportal)"])
        self.aktualisieren_knopf = QPushButton("Aktualisieren")
        self.abmelden_knopf = QPushButton("Abmelden")
        quelle.addWidget(self.quelle, 1)
        quelle.addWidget(self.aktualisieren_knopf)
        quelle.addWidget(self.abmelden_knopf)
        lay.addLayout(quelle)
        self.akteur = QLineEdit()
        self.akteur.setPlaceholderText("Dein Name als Moderator")
        lay.addWidget(self.akteur)
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Einreichung", "Paket", "Version", "Status"])
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._auswahl)
        lay.addWidget(self.tabelle, 1)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.details.setOpenLinks(False)
        lay.addWidget(self.details, 2)
        knoepfe = QHBoxLayout()
        self.knoepfe: dict[str, QPushButton] = {}
        for text, ziel in AKTIONEN.values():
            b = QPushButton(text)
            b.setProperty("ziel", ziel)
            b.clicked.connect(self._knopf)      # kein Lambda mit self: sonst wird der Dialog erst beim Beenden frei
            knoepfe.addWidget(b)
            self.knoepfe[ziel] = b
        knoepfe.addStretch(1)
        self.inhalt_knopf = QPushButton("Inhalt ansehen …")
        self.inhalt_knopf.setToolTip("Dateien des Pakets als Klartext lesen – nichts wird ausgeführt")
        self.inhalt_knopf.clicked.connect(self._inhalt_ansehen)
        knoepfe.addWidget(self.inhalt_knopf)
        self.datei_knopf = QPushButton("Paketdatei prüfen …")
        self.datei_knopf.setToolTip("Eine .bonyspaket-Datei als Daten prüfen und in die lokale Ablage aufnehmen – "
                                    "nichts daraus wird ausgeführt")
        self.datei_knopf.clicked.connect(self._datei_waehlen)
        knoepfe.addWidget(self.datei_knopf)
        lay.addLayout(knoepfe)
        self.quelle.currentIndexChanged.connect(self._quelle_gewechselt)
        self.aktualisieren_knopf.clicked.connect(self._aktualisieren)
        self.abmelden_knopf.clicked.connect(self._abmelden)
        self._modus_anzeigen()
        self.neu_laden()

    # --- Quelle: lokal oder online -----------------------------------------

    def _ist_online(self) -> bool:
        return self.quelle.currentIndex() == 1

    def _modus_anzeigen(self) -> None:
        on = self._ist_online()
        self.akteur.setEnabled(not on)
        self.akteur.setPlaceholderText("Der Akteur ist dein Moderator-Zugang" if on else "Dein Name als Moderator")
        self.datei_knopf.setEnabled(not on)
        self.aktualisieren_knopf.setEnabled(on)
        self.abmelden_knopf.setEnabled(on and online.zugang_laden() is not None)

    def _quelle_gewechselt(self) -> None:
        if not self._ist_online():
            self.ablage = self.lokal
        elif not self._online_verbinden():
            self.quelle.blockSignals(True)
            self.quelle.setCurrentIndex(0)
            self.quelle.blockSignals(False)
            self.ablage = self.lokal
        self._modus_anzeigen()
        self.neu_laden()

    def _online_verbinden(self) -> bool:
        """Zugang holen (ohne gespeichertes Token einmal danach fragen), Liste laden, erst dann merken.
        Bei einem Fehler zurück zu „Lokal“; ein abgelehntes Token wird verworfen."""
        zugang = online.zugang_laden()
        neu_eingegeben = zugang is None
        if zugang is None:
            token, ok = QInputDialog.getText(self, "Moderator-Zugang", "Moderator-Token des Kursportals:",
                                             QLineEdit.EchoMode.Password)
            if not ok or not token.strip():
                return False
            zugang = online.Zugang(online.portal_url(), token.strip())
        try:
            neu = online.OnlineAblage(zugang)
            neu.aktualisieren()
            if neu_eingegeben:
                online.zugang_speichern(zugang.token, zugang.url)
        except online.OnlineFehler as exc:
            if exc.code in (401, 403):
                online.zugang_loeschen()
            QMessageBox.warning(self, "Kursportal", str(exc))
            return False
        self.online = self.ablage = neu
        return True

    def _aktualisieren(self) -> None:
        if self.online is None:
            return
        try:
            self.online.aktualisieren()
        except online.OnlineFehler as exc:
            QMessageBox.warning(self, "Kursportal", str(exc))
        self.neu_laden()

    def _abmelden(self) -> None:
        online.zugang_loeschen()
        self.online = None
        self.quelle.setCurrentIndex(0)          # löst _quelle_gewechselt aus

    def _inhalt_ansehen(self) -> None:
        sid = self.aktuelle_id()
        if not sid:
            return
        try:
            with self.ablage.original_bereit(sid) as datei:
                dateien = online.inhalt_lesen(datei)
        except mod.ModerationsFehler as exc:             # auch OnlineFehler
            QMessageBox.warning(self, "Inhalt nicht ansehbar", str(exc))
            return
        InhaltDialog(dateien, self).exec()

    def _knopf(self) -> None:
        self.entscheiden(self.sender().property("ziel"))

    def _datei_waehlen(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Paketdatei prüfen", str(Path.home()),
                                               f"Kurspakete (*{kurspaket.SUFFIX});;Alle Dateien (*)")
        if datei:
            self.einreichen(Path(datei))

    def einreichen(self, datei: Path) -> bool:
        try:
            self.ablage.einreichen(datei, "lokal")
        except (mod.ModerationsFehler, kurspaket.PaketFehler, OSError) as exc:
            QMessageBox.warning(self, "Prüfung nicht möglich", str(exc))
            return False
        self.neu_laden()
        return True

    def aktuelle_id(self) -> str:
        zeile = self.tabelle.currentRow()
        item = self.tabelle.item(zeile, 0) if zeile >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def neu_laden(self) -> None:
        auswahl = self.aktuelle_id()
        self.tabelle.setRowCount(0)
        for sid in self.ablage.ids():
            b = self.ablage.bericht(sid) or {}
            zeile = self.tabelle.rowCount()
            self.tabelle.insertRow(zeile)
            for spalte, text in enumerate((sid[:8], b.get("name") or b.get("paket_id") or "–",
                                           b.get("version") or "–", STATUS_TEXT.get(self.ablage.status(sid), "?"))):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, sid)
                self.tabelle.setItem(zeile, spalte, item)
            if sid == auswahl:
                self.tabelle.selectRow(zeile)
        self._auswahl()

    def _auswahl(self) -> None:
        sid = self.aktuelle_id()
        if sid and self._ist_online() and self.online is not None:
            try:
                self.online.detail_laden(sid)
            except online.OnlineFehler as exc:
                self.details.setPlainText(str(exc))
                for knopf in self.knoepfe.values():
                    knopf.setEnabled(False)
                return
        status = self.ablage.status(sid) if sid else ""
        self.inhalt_knopf.setEnabled(bool(sid))
        self.details.setPlainText(bericht_text(self.ablage, sid) if sid else "Keine Einreichung ausgewählt.")
        for ziel, knopf in self.knoepfe.items():
            knopf.setEnabled(ziel in mod.ERLAUBT_MENSCH.get(status, set()))

    def entscheiden(self, ziel: str, begruendung: str | None = None) -> bool:
        sid = self.aktuelle_id()
        if not sid:
            return False
        if begruendung is None:
            begruendung, ok = QInputDialog.getMultiLineText(self, "Begründung", "Warum diese Entscheidung?")
            if not ok:
                return False
        try:
            self.ablage.entscheiden(sid, ziel, self.akteur.text(), begruendung)
        except mod.ModerationsFehler as exc:         # auch OnlineFehler
            QMessageBox.warning(self, "Entscheidung nicht möglich", str(exc))
            return False
        self.neu_laden()
        return True
