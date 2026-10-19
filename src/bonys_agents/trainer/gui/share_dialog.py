# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter: „Im Netzwerk freigeben“ – Vorlage im LAN/VPN an die Teilnehmer geben (nur Kursleiter-Version).

Optional mit Kurspaket: Die Teilnehmer bekommen es mit der Vorlage und melden nur Lektion und „geschafft / noch
nicht“ – die Tabelle zeigt das, solange die Freigabe läuft."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from bonys_agents import APP_NAME, host, kurse, kurspaket, share, storage, templates
from bonys_agents.gui import style
from bonys_agents.gui.share_dialogs import _eta, code_style, qr_pixmap
from bonys_agents.gui.template_dialogs import ExportDialog, FnWorker
from bonys_agents.gui.widgets import PercentBar, make_scrollable
from bonys_agents.trainer import share_server


class ShareDialog(QDialog):
    """Kursleiter: Vorlage freigeben – Code, Adressen, QR-Code, Fingerabdruck, Teilnehmer mit Fortschritt."""

    def __init__(self, t: templates.Template, parent=None):
        super().__init__(parent)
        self.t = t
        self.share: share_server.Share | None = None
        self.paket_lokal: kurspaket.Kurspaket | None = None
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
        from bonys_agents.trainer.gui.kurse_leiten import paket_auswahl

        self.paket = paket_auswahl()
        self.settings.addRow("Kurspaket", self.paket)
        root.addLayout(self.settings)

        # Während der Freigabe
        self.live = QHBoxLayout()
        left = QVBoxLayout()
        self.code = QLabel()
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Schrift per Stylesheet – das App-Stylesheet überschreibt setFont() bei QLabel
        self.code.setStyleSheet(code_style())
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
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Teilnehmer", "Adresse", "Status", "Fortschritt", "Restzeit", "Lektion",
                                              "Prüfung"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(style.px(110))
        root.addWidget(self.table, 1)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumHeight(style.px(90))
        root.addWidget(self.events)
        self.firewall = QLabel(share_server.FIREWALL_HINTS.get(host.detect().os, "").format(port=share.DEFAULT_PORT))
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
            share_server.FIREWALL_HINTS.get(host.detect().os, "").format(port=v)))
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.close_btn.clicked.connect(self.reject)

    def _start(self) -> None:
        cached = share_server.cached_bundle(self.t)
        if cached is None:
            target = share_server.cache_target(self.t, self.t.version or "1")
            dlg = ExportDialog(self.t, self, target=target)
            dlg.ok_btn.setText("Prüfen und vorbereiten")
            dlg.exec()
            if not dlg.result_file:
                return
            file = dlg.result_file
            self._run(lambda progress: (file, share_server.remember_cache(
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
        paket = next((p for p in kurspaket.liste() if p.id == self.paket.currentData()), None) \
            if self.paket.currentData() else None
        try:
            mit = (kurse.paket_packen(paket), {"paket_id": paket.id, "name": paket.name, "version": paket.version,
                                               "lektionen": len(paket.lektionen)}) if paket else None
            s = share_server.Share(file, port=self.port.value(), timeout_min=self.minutes.value(),
                                   max_downloads=self.parallel.value(), sha256=sha, kurspaket=mit)
            s.start()
        except (OSError, ValueError, share_server.ShareError, kurspaket.PaketFehler) as e:
            self._failed(str(e))
            return
        self.share = s
        self.paket_lokal = paket
        for spalte in (5, 6):
            self.table.setColumnHidden(spalte, paket is None)
        for w in (self.port, self.minutes, self.parallel, self.paket, self.start_btn):
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
        if paket is not None:
            rows.append(f"Kurspaket: {paket.name} {paket.version} – die Teilnehmer bekommen es mit")
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
            stand = kurse.Stand(p.lektion, p.geschafft) if p.lektion else None
            for col, text in enumerate((p.name, p.address, status, f"{p.percent:.0f} %" if p.total else "",
                                        _eta(p.eta()), stand.lektion_text(self.paket_lokal) if stand else "–",
                                        stand.pruefung_text if stand else "–")):
                self.table.setItem(i, col, QTableWidgetItem(text))
        text = "\n".join(events)
        if text != self.events.toPlainText():
            self.events.setPlainText(text)
            self.events.verticalScrollBar().setValue(self.events.verticalScrollBar().maximum())
        if s.stopped.is_set():
            self.timer.stop()
            self.status.setText(s.stop_reason)
            self.stop_btn.setVisible(False)
            self.code.setStyleSheet(code_style() + " text-decoration: line-through;")
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
