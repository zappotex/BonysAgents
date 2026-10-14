# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen: „Im Netzwerk freigeben“ (Kursleiter) und „Schulung beitreten“ (Teilnehmer)."""

from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from bonys_agents import APP_NAME, bonysfile, host, share, storage, templates

from . import style
from .template_dialogs import ExportDialog, FnWorker, open_bonys_file
from .widgets import PercentBar, make_scrollable


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


class ShareDialog(QDialog):
    """Kursleiter: Vorlage freigeben – Code, Adressen, QR-Code, Fingerabdruck, Teilnehmer mit Fortschritt."""

    def __init__(self, t: templates.Template, parent=None):
        super().__init__(parent)
        self.t = t
        self.share: share.Share | None = None
        self.worker: FnWorker | None = None
        self.setWindowTitle("Im Netzwerk freigeben")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel(f"„{t.name}“ im Netzwerk freigeben")
        title.setObjectName("Title")
        root.addWidget(title)
        intro = QLabel("Teilnehmer im selben Netz (oder im VPN, z. B. Bony's VPN) laden die Vorlage direkt von diesem "
                       "Rechner – mit „Schulung beitreten“. Nur mit Freigabe-Code, verschlüsselt (HTTPS), nur lesend "
                       "und nur solange die Freigabe läuft.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)

        self.settings = QFormLayout()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(share.DEFAULT_PORT)
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 24 * 60)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(share.DEFAULT_TIMEOUT_MIN)
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 32)
        self.parallel.setValue(share.DEFAULT_MAX_DOWNLOADS)
        self.parallel.setToolTip("Mehr gleichzeitige Downloads teilen sich die Bandbreite – der Rest wartet in "
                                 "einer Schlange.")
        self.settings.addRow("Port", self.port)
        self.settings.addRow("Endet nach", self.minutes)
        self.settings.addRow("Gleichzeitige Downloads", self.parallel)
        root.addLayout(self.settings)

        # Während der Freigabe
        self.live = QHBoxLayout()
        left = QVBoxLayout()
        self.code = QLabel()
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        font = QFont(self.code.font())
        font.setPointSizeF(font.pointSizeF() * 2.2)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        self.code.setFont(font)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        left.addWidget(self.code)
        left.addWidget(self.info)
        left.addStretch(1)
        self.live.addLayout(left, 1)
        self.qr = QLabel()
        self.qr.setToolTip("Enthält Adresse, Code und Fingerabdruck – Teilnehmer können den Inhalt („bonys://…“) "
                           "bei „Schulung beitreten“ einfügen.")
        self.live.addWidget(self.qr, 0, Qt.AlignTop)
        root.addLayout(self.live)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Teilnehmer", "Adresse", "Status", "Fortschritt", "Restzeit"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(style.px(110))
        root.addWidget(self.table, 1)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumHeight(style.px(90))
        root.addWidget(self.events)
        self.firewall = QLabel(share.FIREWALL_HINTS.get(host.detect().os, "").format(port=share.DEFAULT_PORT))
        self.firewall.setWordWrap(True)
        self.firewall.setObjectName("Muted")
        root.addWidget(self.firewall)
        for w in (self.code, self.info, self.qr, self.table, self.events):
            w.setVisible(False)

        self.progress = PercentBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        root.addWidget(self.progress)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.start_btn = QPushButton("Freigabe starten")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Freigabe beenden")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setVisible(False)
        for b in (self.close_btn, self.stop_btn, self.start_btn):
            buttons.addWidget(b)
        root.addLayout(buttons)
        make_scrollable(self, 760)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.port.valueChanged.connect(lambda v: self.firewall.setText(
            share.FIREWALL_HINTS.get(host.detect().os, "").format(port=v)))
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.close_btn.clicked.connect(self.reject)

    def _start(self) -> None:
        cached = share.cached_bundle(self.t)
        if cached is None:
            target = share.cache_target(self.t, self.t.version or "1")
            dlg = ExportDialog(self.t, self, target=target)
            dlg.ok_btn.setText("Prüfen und vorbereiten")
            dlg.exec()
            if not dlg.result_file:
                return
            file = dlg.result_file
            self._run(lambda progress: (file, share.remember_cache(
                self.t, file, lambda f: progress("hash", f, f"Berechne Prüfsumme … {f * 100:.0f} %"))))
            return
        self._serve(cached)

    def _run(self, fn) -> None:
        self.worker = FnWorker(fn)
        self.worker.progress.connect(lambda _p, f, msg: (self.progress.set_percent(f * 100), self.status.setText(msg)))
        self.worker.done.connect(self._serve)
        self.worker.failed.connect(self._failed)
        self.progress.setVisible(True)
        self.start_btn.setEnabled(False)
        self.worker.start()

    def _failed(self, msg: str) -> None:
        self.worker = None
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)
        self.status.setText(f"Fehler: {msg}")
        self.status.setStyleSheet(f"color: {style.DANGER};")

    def _serve(self, cached: tuple[Path, str]) -> None:
        self.worker = None
        self.progress.setVisible(False)
        file, sha = cached
        try:
            s = share.Share(file, port=self.port.value(), timeout_min=self.minutes.value(),
                            max_downloads=self.parallel.value(), sha256=sha)
            s.start()
        except (OSError, ValueError, share.ShareError) as e:
            self._failed(str(e))
            return
        self.share = s
        for w in (self.port, self.minutes, self.parallel, self.start_btn):
            w.setEnabled(False)
        self.start_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        for w in (self.code, self.info, self.table, self.events):
            w.setVisible(True)
        self.code.setText(s.code)
        addrs = s.addresses()
        rows = [f"Adresse: <b>{a}:{s.port}</b>" + (f" ({share.address_kind(a)})" if share.address_kind(a) else "")
                for a in addrs]
        rows.append(f"Fingerabdruck: <b>{share.short_fingerprint(s.fingerprint)}</b> – Teilnehmer vergleichen ihn")
        rows.append(f"<span style='font-size:small'>{share.format_fingerprint(s.fingerprint)}</span>")
        rows.append(f"Datei: {file.name} ({s.size / storage.GB:.2f} GB)")
        self.info.setText("<br>".join(rows))
        pix = qr_pixmap(s.link(addrs[0] if addrs else None), style.px(200))
        if pix is not None:
            self.qr.setPixmap(pix)
            self.qr.setVisible(True)
        self.status.setStyleSheet("")
        self.timer.start()
        self._refresh()

    def _refresh(self) -> None:
        s = self.share
        if s is None:
            return
        with s.lock:
            people = list(s.participants.values())
            events = list(s.events)
        self.table.setRowCount(len(people))
        for i, p in enumerate(people):
            status = {"wartet": f"wartet (Platz {p.queue})"}.get(p.status, p.status)
            for col, text in enumerate((p.name, p.address, status, f"{p.percent:.0f} %" if p.total else "",
                                        _eta(p.eta()))):
                self.table.setItem(i, col, QTableWidgetItem(text))
        text = "\n".join(events)
        if text != self.events.toPlainText():
            self.events.setPlainText(text)
            self.events.verticalScrollBar().setValue(self.events.verticalScrollBar().maximum())
        if s.stopped.is_set():
            self.timer.stop()
            self.status.setText(s.stop_reason)
            self.stop_btn.setVisible(False)
            self.code.setStyleSheet("text-decoration: line-through;")
            return
        left = s.remaining()
        done = sum(1 for p in people if p.status == "fertig")
        self.status.setText(f"Freigabe läuft – endet in {int(left // 60)} min {int(left % 60):02d} s · "
                            f"{done} von {len(people)} Teilnehmern fertig")

    def _stop(self) -> None:
        s = self.share
        if s is None:
            return
        busy = [p for p in s.participants.values() if p.status == "lädt"]
        if busy and QMessageBox.question(
                self, APP_NAME, f"{len(busy)} Teilnehmer laden gerade. Trotzdem beenden? (Sie können später "
                "fortsetzen, wenn du wieder freigibst.)") != QMessageBox.Yes:
            return
        s.stop("Freigabe beendet.")
        self._refresh()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self.share and not self.share.stopped.is_set():
            self._stop()
            if not self.share.stopped.is_set():
                return
        self.timer.stop()
        super().reject()


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
        intro = QLabel("Lädt die Vorlage direkt vom Rechner des Kursleiters. Im selben Netz wird die Freigabe meist "
                       "automatisch gefunden. Im VPN (z. B. Bony's VPN) oder wenn nichts erscheint: Adresse und Code "
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
            it = QListWidgetItem(f"{f.txt.get('name', '?')} {f.txt.get('version', '')} – von "
                                 f"{f.txt.get('creator') or '?'} · {f.address}")
            it.setData(Qt.UserRole, (f.address, f.txt.get("fp", "")))
            self.found.addItem(it)
        self.status.setText(f"{len(items)} Freigabe(n) gefunden – auswählen und Code eingeben." if items else
                            "Keine Freigabe gefunden. Im VPN geht die Suche nicht – Adresse und Code eingeben.")
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
        self.worker.failed.connect(lambda msg: self._error(msg))
        self._busy(True)
        self.worker.start()

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
