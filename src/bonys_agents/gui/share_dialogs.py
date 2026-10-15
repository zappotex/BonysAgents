# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: „Schulung beitreten“ (Teilnehmer, beide Editionen) und gemeinsame Bausteine (Code, QR-Code).

„Im Netzwerk freigeben“ gibt es nur in der Kursleiter-Version (``bonys_agents.trainer.gui.share_dialog``).
"""

from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from bonys_agents import bonysfile, share

from . import style
from .template_dialogs import FnWorker, open_bonys_file
from .widgets import PercentBar, make_scrollable, open_url


def code_style() -> str:
    return f"font-size: {style.px(30)}px; font-weight: bold; letter-spacing: 3px;"


def qr_pixmap(text: str, size: int = 220) -> QPixmap | None:
    """QR-Code als Bild (None, wenn das Modul qrcode fehlt)."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    pix = QPixmap(size, size)
    pix.fill(QColor("white"))
    painter = QPainter(pix)
    cell = size / n
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                painter.drawRect(QRectF(x * cell, y * cell, cell + 0.5, cell + 0.5))
    painter.end()
    return pix


def _eta(seconds: float | None) -> str:
    return share._fmt_eta(seconds) if seconds else ""


class JoinDialog(QDialog):
    """Teilnehmer: Freigabe finden (mDNS) oder Adresse/Code eingeben, Fingerabdruck prüfen, laden, importieren."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: FnWorker | None = None
        self.info: share.RemoteInfo | None = None
        self.cancel = threading.Event()
        self.result_template: str | None = None
        self.setWindowTitle("Schulung beitreten")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Schulung beitreten")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Lädt die Vorlage direkt vom Rechner des Kursleiters bzw. öffnet seine Live-Vorführung im "
                       "Browser. Im selben Netz wird beides meist automatisch gefunden. Im VPN (z. B. Bony's VPN) "
                       "oder wenn nichts erscheint: Adresse und Code "
                       "eingeben – oder den Link aus dem QR-Code („bonys://…“) einfügen.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        found_row = QHBoxLayout()
        sec = QLabel("GEFUNDEN IM NETZ")
        sec.setObjectName("Section")
        found_row.addWidget(sec)
        found_row.addStretch(1)
        self.search_btn = QPushButton("Erneut suchen")
        self.search_btn.setObjectName("Small")
        found_row.addWidget(self.search_btn)
        root.addLayout(found_row)
        self.found = QListWidget()
        self.found.setMaximumHeight(style.px(100))
        root.addWidget(self.found)
        form = QFormLayout()
        self.address = QLineEdit()
        self.address.setPlaceholderText("z. B. 192.168.1.5:47110 oder bonys://…")
        self.code = QLineEdit()
        self.code.setPlaceholderText("z. B. 4711-BONY")
        form.addRow("Adresse", self.address)
        form.addRow("Code", self.code)
        root.addLayout(form)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.setVisible(False)
        root.addWidget(self.details)
        self.fp_ok = QCheckBox("Der Fingerabdruck stimmt mit dem auf dem Bildschirm des Kursleiters überein")
        self.fp_ok.setVisible(False)
        root.addWidget(self.fp_ok)
        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Schließen")
        self.connect_btn = QPushButton("Verbinden")
        self.load_btn = QPushButton("Laden und importieren")
        self.load_btn.setObjectName("Primary")
        self.load_btn.setVisible(False)
        for b in (self.cancel_btn, self.connect_btn, self.load_btn):
            buttons.addWidget(b)
        root.addLayout(buttons)
        make_scrollable(self, 640)

        self.search_btn.clicked.connect(self._search)
        self.found.currentItemChanged.connect(self._pick)
        self.address.textChanged.connect(self._reset)
        self.code.textChanged.connect(self._reset)
        self.connect_btn.clicked.connect(self._connect)
        self.load_btn.clicked.connect(self._load)
        self.cancel_btn.clicked.connect(self.reject)
        QTimer.singleShot(0, self._search)

    def _busy(self, busy: bool) -> None:
        for w in (self.search_btn, self.address, self.code, self.connect_btn, self.load_btn, self.found):
            w.setEnabled(not busy)
        self.cancel_btn.setText("Abbrechen" if busy else "Schließen")

    def _search(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.found.clear()
        self.status.setText("Suche Freigaben im Netz …")
        self.worker = FnWorker(lambda progress: share.discover())
        self.worker.done.connect(self._found)
        self.worker.failed.connect(lambda msg: self._error(msg))
        self._busy(True)
        self.worker.start()

    def _found(self, items) -> None:
        self.worker = None
        self._busy(False)
        for f in items:
            if f.txt.get("kind") == "present":
                text = f"▶ Live-Vorführung: {f.txt.get('name', '?')} – von {f.txt.get('creator') or '?'} · {f.address}"
            else:
                text = (f"{f.txt.get('name', '?')} {f.txt.get('version', '')} – von "
                        f"{f.txt.get('creator') or '?'} · {f.address}")
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, (f.address, f.txt.get("fp", "")))
            self.found.addItem(it)
        self.status.setText(f"{len(items)} gefunden – auswählen und Code eingeben." if items else
                            "Nichts gefunden. Im VPN geht die Suche nicht – Adresse und Code eingeben.")
        if len(items) == 1:
            self.found.setCurrentRow(0)

    def _pick(self, item) -> None:
        if item is None:
            return
        addr, fp = item.data(Qt.UserRole)
        # Fingerabdruck aus der Suche mitnehmen – dann prüft das Beitreten ihn selbst
        self.address.setText(f"bonys://{addr}?fp={fp}" if fp else addr)
        self.code.setFocus()

    def _reset(self, *_) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.info = None
        self.details.setVisible(False)
        self.fp_ok.setVisible(False)
        self.load_btn.setVisible(False)
        self.connect_btn.setVisible(True)

    def _target(self) -> share.Target:
        return share.parse_target(self.address.text(), self.code.text())

    def _connect(self) -> None:
        try:
            target = self._target()
        except ValueError as e:
            self._error(str(e))
            return
        if target.code and not self.code.text().strip():
            self.code.setText(target.code)
        self.status.setStyleSheet("")
        self.status.setText(f"Verbinde mit {target.netloc} …")
        self.worker = FnWorker(lambda progress: share.fetch_info(target))
        self.worker.done.connect(self._connected)
        self.worker.failed.connect(self._connect_failed)
        self._busy(True)
        self.worker.start()

    def _connect_failed(self, msg: str) -> None:
        err = self.worker.error if self.worker else None
        if isinstance(err, share.IsPresentation):
            self.worker = None
            self._busy(False)
            self._open_presentation(err)
            return
        self._error(msg)

    def _open_presentation(self, p: share.IsPresentation) -> None:
        """Live-Vorführung im Standardbrowser öffnen – Code (und Name) stehen hinter „#“, gehen also nicht ins Netz."""
        self.status.setStyleSheet("")
        self.status.setText(
            f"„{p.title}“ ist eine Live-Vorführung – sie öffnet sich im Browser. Der Browser warnt vor dem Zertifikat "
            f"(es gilt nur für diese Vorführung): „Erweitert“ → „Weiter“. Fingerabdruck zum Vergleichen: "
            f"{share.short_fingerprint(p.fingerprint)}")
        open_url(p.url(share._client_name()))

    def _connected(self, info: share.RemoteInfo) -> None:
        self.worker = None
        self._busy(False)
        self.info = info
        text = html.escape(bonysfile.describe_manifest(info.manifest, info.size)).replace("\n", "<br>")
        fp = (f"<br><br>Fingerabdruck: <b>{share.short_fingerprint(info.fingerprint)}</b>"
              + (" ✓ (aus dem Link bzw. der Suche)" if info.target.fingerprint else ""))
        if not bonysfile.arch_matches(info.manifest):
            fp += (f"<br><span style='color:{style.DANGER}'>⚠ Andere Architektur ({info.manifest['arch']}) – "
                   "nach dem Laden wird das Rezept angeboten.</span>")
        self.details.setText(text + fp)
        self.details.setVisible(True)
        self.fp_ok.setVisible(not info.target.fingerprint)
        self.fp_ok.setChecked(False)
        self.connect_btn.setVisible(False)
        self.load_btn.setVisible(True)
        self.status.setText("Verbunden. Inhalt prüfen und laden.")

    def _load(self) -> None:
        info = self.info
        if info is None:
            return
        if not info.target.fingerprint and not self.fp_ok.isChecked():
            self.status.setText("Bitte zuerst den Fingerabdruck mit dem Bildschirm des Kursleiters vergleichen.")
            return
        self.cancel.clear()
        cancel = self.cancel
        dest = share.downloads_dir()
        self.worker = FnWorker(lambda progress: share.download(info, dest, progress=progress, cancel=cancel))
        self.worker.progress.connect(lambda _p, f, msg: (self.progress.set_percent(f * 100), self.status.setText(msg)))
        self.worker.done.connect(self._loaded)
        self.worker.failed.connect(self._load_failed)
        self.progress.setVisible(True)
        self._busy(True)
        self.worker.start()

    def _loaded(self, file: Path) -> None:
        self.worker = None
        self._busy(False)
        self.progress.setVisible(False)
        self.status.setText(f"Geladen und geprüft: {file}")
        name = open_bonys_file(self, file)
        if name:
            self.result_template = name
            self.accept()

    def _load_failed(self, msg: str) -> None:
        err = self.worker.error if self.worker else None
        self.worker = None
        self._busy(False)
        if isinstance(err, bonysfile.Cancelled):
            self.status.setText("Abgebrochen – „Laden“ setzt später an derselben Stelle fort.")
            return
        self._error(msg)

    def _error(self, msg: str) -> None:
        self.worker = None
        self._busy(False)
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            self.cancel.set()
            return
        super().reject()
