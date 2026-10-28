# SPDX-License-Identifier: GPL-3.0-or-later
"""Lokaler Moderationsbildschirm für Kursportal-Einreichungen (Kursleiter-Edition, Menü des Hauptfensters).

Zeigt die Einreichungen einer ``Moderation``-Ablage mit Prüfbericht und Verlauf; Entscheidungen
(freigeben, ablehnen, veröffentlichen, zurückziehen) brauchen Akteur und Begründung. Der Dialog führt nichts aus
und öffnet keine Paketinhalte – er zeigt nur den sanitisierten Bericht.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from pathlib import Path

from bonys_agents import kurspaket, kurspaket_moderation as mod, storage

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


def bericht_text(m: mod.Moderation, sid: str) -> str:
    """Prüfbericht und Verlauf als Markdown – ohne Fundwerte."""
    b = m.bericht(sid) or {}
    zeilen = [f"**{b.get('name') or '(ohne Namen)'}** · Version {b.get('version') or '–'}",
              f"Paket-ID: {b.get('paket_id') or '–'} · {b.get('groesse', 0)} Bytes",
              f"SHA-256: `{b.get('sha256') or '–'}`", ""]
    for titel, schluessel in (("Befunde", "findings"), ("Skripte", "skripte"),
                              ("Externe Links", "externe_links"), ("Fundstellen (ohne Werte)", "fundstellen")):
        if b.get(schluessel):
            zeilen += [f"{titel}:", ""] + [f"- {x}" for x in b[schluessel]] + [""]
    zeilen += ["Verlauf:", ""]
    for e in m.verlauf(sid):
        zeilen.append(f"- {e.nr}. {e.zeit} · {STATUS_TEXT.get(e.nach, e.nach)} · {e.akteur}: {e.begruendung}")
    return "\n".join(zeilen)


def lokale_ablage() -> mod.Moderation:
    """Die lokale Ablage dieses Rechners; IDs der mitgelieferten Kurspakete sind für Einreichungen gesperrt."""
    reserviert = {p.id for p in kurspaket.liste() if p.mitgeliefert}
    return mod.Moderation(storage.data_dir() / "kursportal-ablage", reserviert)


class ModerationDialog(QDialog):
    def __init__(self, ablage: mod.Moderation, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Kursportal – Moderation")
        self.ablage = ablage
        lay = QVBoxLayout(self)
        intro = QLabel("Lokale Moderation auf diesem Rechner: Nichts wird hier veröffentlicht oder hochgeladen und der "
                       "Online-Katalog bleibt unverändert. Jede Entscheidung wird mit Akteur und Begründung "
                       "unveränderlich im Verlauf festgehalten.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
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
        self.datei_knopf = QPushButton("Paketdatei prüfen …")
        self.datei_knopf.setToolTip("Eine .bonyspaket-Datei als Daten prüfen und in die lokale Ablage aufnehmen – "
                                    "nichts daraus wird ausgeführt")
        self.datei_knopf.clicked.connect(self._datei_waehlen)
        knoepfe.addWidget(self.datei_knopf)
        lay.addLayout(knoepfe)
        self.neu_laden()

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
        status = self.ablage.status(sid) if sid else ""
        self.details.setMarkdown(bericht_text(self.ablage, sid) if sid else "Keine Einreichung ausgewählt.")
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
        except mod.ModerationsFehler as exc:
            QMessageBox.warning(self, "Entscheidung nicht möglich", str(exc))
            return False
        self.neu_laden()
        return True
