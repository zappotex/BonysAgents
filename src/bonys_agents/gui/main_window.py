# SPDX-License-Identifier: GPL-3.0-or-later
"""Hauptfenster: Liste der Agent-PCs links, Details rechts."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QIcon, QKeySequence, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from bonys_agents import (
    APP_NAME, INTRO_VIDEO_URL, REPO_URL, TAGLINE, YOUTUBE_CHANNEL_URL, __version__, apps, deps, desktops, host, remote,
    screen, storage, updates, vm,
)
from bonys_agents import progress as pct

from . import style
from .about_dialog import AboutDialog
from .create_dialog import CreateDialog
from .desktop_dialog import AddDesktopDialog
from .host_vpn import HostVpnPanel, mac_wireguard, state_icon, windows_wireguard
from .install_dialog import InstallAppsDialog
from .remote_panel import RemoteDialog, RemotePanel, switch_remote
from .vpn_panel import VpnPanel
from .move_dialog import MoveDialog
from .resize_dialog import ResizeDialog
from .setup_dialog import SetupDialog
from .template_dialogs import FnWorker, SaveTemplateDialog, TemplatesDialog
from .updates_ui import CheckWorker, UpdateBanner, UpgradeDialog, start_update
from .widgets import (
    ColumnLayout, FlowLayout, PathLabel, PercentBar, ScaledLogo, available_geometry, fit_to_screen, open_url,
)
from .workers import TaskWorker


def _dot(color: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    p.end()
    return QIcon(pm)


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


HINT_SETUP = ("Der Agent-PC richtet sich im Hintergrund ein. "
              "Das Fenster öffnet sich automatisch, sobald der Desktop bereit ist.")
HINT_ABORTED = ("Die Einrichtung wurde unterbrochen, bevor der Desktop fertig war. "
                "Sie kann fortgesetzt werden – erledigte Schritte werden übersprungen.")
HINT_READY = "Einrichtung fertig – der Agent-PC startet gleich mit Desktop …"
HINT_TEMPLATE_MISSING = ("Dieser Agent-PC baut auf einer Vorlage auf, die gerade nicht erreichbar ist (Pfad darunter). "
                         "Steck das Laufwerk mit der Vorlage ein – dann ist der Agent-PC wieder verfügbar.")
HINT_TEMPLATE_LOCK = ("Aus diesem Agent-PC wird gerade eine Vorlage erstellt. Bis das fertig ist, lässt er sich nicht "
                      "starten (das Original bleibt dabei unverändert).")
HINT_STOPPING = ("Der Agent-PC fährt herunter. Reagiert er nicht, kannst du ihn sofort ausschalten – "
                 f"nach {vm.STOP_TIMEOUT} Sekunden geschieht das automatisch.")
REMOTE_MARK = "  ⇄"  # hinter dem Namen in der Liste: Fernzugriff ist an


class Backdrop(QWidget):
    """Hintergrundbild, formatfüllend ohne Verzerrung („cover“) und stark abgedunkelt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QPixmap(str(style.resource("background.jpg")))
        self._scaled: QPixmap | None = None

    def resizeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self._scaled = None
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(style.BG))
        if not self._image.isNull():
            if self._scaled is None:
                self._scaled = self._image.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (self.width() - self._scaled.width()) // 2
            y = (self.height() - self._scaled.height()) // 2
            p.drawPixmap(x, y, self._scaled)
        p.fillRect(self.rect(), QColor(*style.BACKDROP_DIM))
        p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.info = host.detect()
        self.workers: list[TaskWorker] = []
        self._autostarting: set[str] = set()
        self._powering_off: set[str] = set()      # „Sofort ausschalten“ läuft gerade
        self._notices: dict[str, str] = {}        # z. B. „wurde hart ausgeschaltet“ – bis zum nächsten Start
        self._remote_check: TaskWorker | None = None
        self._ticks = 0
        self._console_big = False
        self.vpn_mode = False                     # Bereich „VPN“ (dieser Rechner) statt der Details
        self.entries: dict[str, vm.VM | vm.MissingVM] = {}
        self.setWindowTitle(APP_NAME)

        central = Backdrop()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(16)

        # ---------- Kopfzeile ----------
        top = QHBoxLayout()
        top.setSpacing(8)
        logo = ScaledLogo(48)
        logo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # klein genug – lieber bricht der Untertitel um
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        title.setWordWrap(True)  # bei sehr großer Anzeige lieber zweizeilig als zu breit
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("Tagline")
        tagline.setWordWrap(True)  # bei schmalem Fenster zweizeilig statt abgeschnitten
        self.about_btn = QPushButton("ⓘ")
        self.about_btn.setObjectName("Quiet")
        self.about_btn.setToolTip(f"Über {APP_NAME}, Updates")
        self.about_btn.setMenu(self._build_menu())
        title_row = QHBoxLayout()
        title_row.setSpacing(2)
        title_row.addWidget(title)
        title_row.addWidget(self.about_btn)
        title_row.addStretch(1)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addLayout(title_row)
        tcol.addWidget(tagline)
        tcol.addStretch(1)
        top.addWidget(logo, 0, Qt.AlignTop)
        top.addLayout(tcol, 1)
        # Knöpfe rechts; bei schmalem Fenster brechen sie in eine zweite Zeile um
        top_buttons = FlowLayout(align_right=True)
        top.addLayout(top_buttons)
        self.youtube_btn = QPushButton("▶  YouTube")
        self.youtube_btn.setObjectName("Quiet")
        self.youtube_btn.setToolTip("Anleitungen und Videos auf meinem YouTube-Kanal")
        self.doctor_btn = QPushButton("System prüfen")
        self.import_btn = QPushButton("Hinzufügen …")
        self.import_btn.setToolTip("Vorhandenen Agent-PC von einer SSD oder aus einem Ordner in die Liste aufnehmen")
        self.templates_btn = QPushButton("Vorlagen")
        self.templates_btn.setToolTip("Vorlagen verwalten: umbenennen, löschen, exportieren, importieren")
        self.new_btn = QPushButton("+  Neuer Agent-PC")
        self.new_btn.setObjectName("Primary")
        # Bony's VPN für diesen Rechner (nur Linux; Windows/macOS: ⓘ → Extras)
        self.vpn_btn = QPushButton("VPN")
        self.vpn_btn.setCheckable(True)
        self.vpn_btn.setIcon(state_icon("disconnected"))
        self.vpn_btn.setToolTip("Bony's VPN – WireGuard für diesen ganzen Rechner")
        self.vpn_btn.setVisible(sys.platform.startswith("linux"))
        for b in (self.youtube_btn, self.doctor_btn, self.vpn_btn, self.import_btn, self.templates_btn,
                  self.new_btn):
            top_buttons.addWidget(b)
        outer.addLayout(top)

        # Dezente Leiste, wenn es eine neue Version gibt
        self.update_banner = UpdateBanner()
        self.update_banner.update_requested.connect(lambda info: start_update(self, info))
        outer.addWidget(self.update_banner)
        self._update_check: CheckWorker | None = None

        # ---------- Inhalt: Liste | Details, Aufteilung per Ziehen ----------
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.list = QListWidget()
        self.list.setMinimumWidth(150)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # lange Namen enden mit „…“
        self.splitter.addWidget(self.list)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_page())
        self.stack.addWidget(self._detail_page())
        self.stack.addWidget(self._missing_page())
        self.stack.addWidget(self._vpn_page())
        # Bei kleinem Fenster wird gescrollt statt abgeschnitten
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setWidget(self.stack)
        self.detail_scroll.viewport().setAutoFillBackground(False)
        self.splitter.addWidget(self.detail_scroll)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 900])
        outer.addWidget(self.splitter, 1)

        self.new_btn.clicked.connect(self.create_vm)
        self.doctor_btn.clicked.connect(self.show_doctor)
        self.import_btn.clicked.connect(self.import_vm)
        self.templates_btn.clicked.connect(self.show_templates)
        self.youtube_btn.clicked.connect(lambda: open_url(YOUTUBE_CHANNEL_URL))
        self.list.currentItemChanged.connect(lambda *_: self.show_vpn(False))
        self.list.itemPressed.connect(lambda *_: self.show_vpn(False))
        self.vpn_btn.clicked.connect(self.show_vpn)

        sysinfo = QLabel(f"v{__version__}  ·  {self.info.os} / {self.info.arch}  ·  Beschleuniger: {self.info.accel}")
        sysinfo.setObjectName("Muted")
        sysinfo.setWordWrap(True)
        self.statusBar().addPermanentWidget(sysinfo)

        self._zoom_actions()
        self._restore_window()

        # Remmina-Profile aller Agent-PCs einmal beim Start aktualisieren
        for machine in vm.list_vms():
            try:
                machine.sync_remmina()
            except Exception:  # noqa: BLE001 – Profile sind nur eine Bequemlichkeit
                pass

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()
        # Beim Start prüfen, ob QEMU & Co. fehlen – dann gleich den Assistenten zeigen.
        if not deps.check(self.info).ok:
            QTimer.singleShot(300, self.show_doctor)
        # Höchstens einmal am Tag still nach Updates suchen (abschaltbar)
        if updates.auto_check_due():
            QTimer.singleShot(3000, lambda: self.check_updates(manual=False))

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(f"Über {APP_NAME}", lambda: AboutDialog(self).exec())
        menu.addAction("Hilfe (Anleitung)", lambda: open_url(f"{REPO_URL}#readme"))
        menu.addSeparator()
        menu.addAction("Nach Updates suchen", lambda: self.check_updates(manual=True))
        st = updates.settings()
        auto = QAction("Automatisch nach Updates suchen", menu, checkable=True, checked=st["auto"])
        auto.toggled.connect(lambda on: updates.set_setting("auto", on))
        pre = QAction("Testversionen anbieten", menu, checkable=True, checked=st["prereleases"])
        pre.toggled.connect(lambda on: updates.set_setting("prereleases", on))
        menu.addAction(auto)
        menu.addAction(pre)
        menu.addSeparator()
        menu.addAction("Alle Agent-PCs aktualisieren …", self.upgrade_all)
        menu.addSeparator()
        extras = menu.addMenu("Extras")
        if sys.platform.startswith("linux"):
            extras.addAction("Bony's VPN für diesen Rechner", lambda: self.show_vpn(True))
        elif sys.platform == "win32":
            extras.addAction("WireGuard für diesen Rechner installieren …", lambda: self._keep_worker(
                windows_wireguard(self)))
        elif sys.platform == "darwin":
            extras.addAction("WireGuard für diesen Rechner (App Store) …", lambda: mac_wireguard(self))
        menu.addSeparator()
        view = menu.addMenu("Ansicht: Anzeigegröße")
        self.zoom_group = QActionGroup(view)
        for z in style.ZOOM_STEPS:
            a = QAction(f"{z} %", view, checkable=True, checked=z == style.zoom())
            a.setData(z)
            a.triggered.connect(lambda _=False, z=z: self.set_zoom(z))
            self.zoom_group.addAction(a)
            view.addAction(a)
        view.addSeparator()
        self.zoom_in = view.addAction("Größer", lambda: self.set_zoom(step=1))
        self.zoom_out = view.addAction("Kleiner", lambda: self.set_zoom(step=-1))
        self.zoom_reset = view.addAction("Normalgröße (100 %)", lambda: self.set_zoom(step=0))
        return menu

    # ---------- Anzeigegröße und Fensterzustand ----------
    def _zoom_actions(self) -> None:
        """Strg + Plus / Strg + Minus / Strg + 0 – im ganzen Fenster, auch ohne geöffnetes Menü."""
        self.zoom_in.setShortcuts([QKeySequence(QKeySequence.ZoomIn), QKeySequence("Ctrl+="),
                                   QKeySequence("Ctrl++")])
        self.zoom_out.setShortcuts([QKeySequence(QKeySequence.ZoomOut), QKeySequence("Ctrl+-")])
        self.zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        for a in (self.zoom_in, self.zoom_out, self.zoom_reset):
            a.setShortcutContext(Qt.WindowShortcut)
            self.addAction(a)

    def set_zoom(self, percent: int | None = None, step: int | None = None) -> None:
        app = QApplication.instance()
        z = style.step_zoom(app, step) if step is not None else style.set_zoom(app, percent)
        for a in self.zoom_group.actions():
            a.setChecked(a.data() == z)
        self.statusBar().showMessage(f"Anzeigegröße: {z} %", 3000)

    def _restore_window(self) -> None:
        """Größe und Position vom letzten Mal – liegt sie auf keinem Bildschirm mehr (z. B. zweiter Monitor
        abgesteckt), auf den Hauptbildschirm zurück. Sonst etwa 80 % des Bildschirms, mittig."""
        avail = available_geometry()
        self.setMinimumSize(min(800, avail.width()), min(550, avail.height()))
        saved = storage.load_settings().get("window") or {}
        try:
            rect = QRect(int(saved["x"]), int(saved["y"]), int(saved["w"]), int(saved["h"]))
        except (KeyError, TypeError, ValueError):
            rect = None
        scr = QGuiApplication.screenAt(rect.center()) if rect is not None and rect.isValid() else None
        if scr is not None:
            area = scr.availableGeometry()
            rect.setWidth(min(rect.width(), area.width()))
            rect.setHeight(min(rect.height(), area.height()))
            self.setGeometry(rect)
        else:
            w = min(1400, int(avail.width() * 0.8)) if rect is None else rect.width()
            h = min(900, int(avail.height() * 0.8)) if rect is None else rect.height()
            w, h = max(self.minimumWidth(), min(w, avail.width())), max(self.minimumHeight(), min(h, avail.height()))
            self.setGeometry(QRect(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2, w, h))
        if saved.get("splitter"):
            self.splitter.restoreState(QByteArray.fromBase64(saved["splitter"].encode()))
        if saved.get("maximized"):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _save_window(self) -> None:
        g = self.normalGeometry() if self.isMaximized() or self.isFullScreen() else self.geometry()
        s = storage.load_settings()
        s["window"] = {
            "x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(),
            "maximized": self.isMaximized(),
            "splitter": bytes(self.splitter.saveState().toBase64()).decode(),
        }
        try:
            storage.save_settings(s)
        except OSError:
            pass  # nur eine Bequemlichkeit

    def closeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self._save_window()
        super().closeEvent(event)

    def check_updates(self, manual: bool) -> None:
        if self._update_check and self._update_check.isRunning():
            return
        if manual:
            self.statusBar().showMessage("Suche nach Updates …")
        w = CheckWorker(manual)

        def found(info) -> None:
            if info:
                self.update_banner.show_update(info)
                self.statusBar().clearMessage()
            elif manual:
                self.update_banner.hide()
                self.statusBar().showMessage(f"Keine Updates gefunden – {APP_NAME} {__version__} ist aktuell.", 8000)

        w.found.connect(found)
        self._update_check = w
        w.start()

    def upgrade_all(self) -> None:
        machines = [m for m in vm.list_vms() if m.is_running() and m.status() == "läuft"]
        if not machines:
            QMessageBox.information(self, APP_NAME, "Es läuft gerade kein fertig eingerichteter Agent-PC.\n"
                                    "Agent-PCs werden aktualisiert, während sie laufen.")
            return
        names = ", ".join(m.name for m in machines)
        if QMessageBox.question(self, APP_NAME, f"Diese Agent-PCs jetzt aktualisieren?\n\n{names}") == QMessageBox.Yes:
            UpgradeDialog(machines, self).exec()
            self.refresh()

    def upgrade_vm(self) -> None:
        m = self.current()
        if m:
            self._show_tab(0)  # Ausgabe erscheint auch in der Konsole
            UpgradeDialog([m], self).exec()
            self.refresh()

    # ---------- Seiten ----------
    def _empty_page(self) -> QWidget:
        w = _card()
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        t = QLabel("Noch kein Agent-PC")
        t.setObjectName("Title")
        t.setAlignment(Qt.AlignCenter)
        m = QLabel("Ein Agent-PC ist ein eigener virtueller Rechner mit Desktop, "
                   "Brave, Telegram und Hermes Agent – sauber getrennt von deinem System.")
        m.setObjectName("Muted")
        m.setAlignment(Qt.AlignCenter)
        m.setWordWrap(True)
        b = QPushButton("+  Ersten Agent-PC erstellen")
        b.setObjectName("Primary")
        b.clicked.connect(self.create_vm)
        lay.addWidget(t)
        lay.addWidget(m)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(b)
        row.addStretch(1)
        lay.addSpacing(12)
        lay.addLayout(row)

        # Hinweis aufs Vorstellungsvideo
        intro = QFrame()
        intro.setObjectName("Hint")
        intro.setMaximumWidth(style.px(560))
        il = QHBoxLayout(intro)
        il.setContentsMargins(14, 10, 14, 10)
        il.setSpacing(12)
        it = QLabel("Neu hier? Auf meinem YouTube-Kanal zeige ich dir, wie Bony's Agents funktioniert.")
        it.setWordWrap(True)
        ib = QPushButton("▶  Zum Vorstellungsvideo")
        ib.setObjectName("Small")
        ib.clicked.connect(lambda: open_url(INTRO_VIDEO_URL))
        il.addWidget(it, 1)
        il.addWidget(ib)
        irow = QHBoxLayout()
        irow.addStretch(1)
        irow.addWidget(intro)
        irow.addStretch(1)
        lay.addSpacing(28)
        lay.addLayout(irow)
        lay.addStretch(1)
        return w

    def _vpn_page(self) -> QWidget:
        w = _card()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.host_vpn = HostVpnPanel()
        self.host_vpn.state_changed.connect(lambda st: self.vpn_btn.setIcon(state_icon(st)))
        self.host_vpn.notify.connect(lambda title, body: self.statusBar().showMessage(f"{title}: {body}", 15000))
        lay.addWidget(self.host_vpn)
        return w

    def show_vpn(self, on: bool = True) -> None:
        """Bereich „VPN“ (dieser Rechner) zeigen – oder zurück zu den Details des Agent-PCs."""
        on = bool(on) and sys.platform.startswith("linux")
        if on != self.vpn_mode:
            self.vpn_mode = on
            if on:
                self.host_vpn.start()
            else:
                self.host_vpn.pause()
        self.vpn_btn.setChecked(on)
        self.refresh_detail()

    def _keep_worker(self, w) -> None:
        if w is not None:
            self.workers = [x for x in self.workers if x.isRunning()] + [w]

    def _detail_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        head = _card()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(20, 18, 20, 18)
        row = QHBoxLayout()
        self.d_name = QLabel()
        self.d_name.setObjectName("Title")
        self.d_status = QLabel()
        row.addWidget(self.d_name)
        row.addSpacing(12)
        row.addWidget(self.d_status)
        row.addStretch(1)
        hl.addLayout(row)
        row = FlowLayout()
        self.start_btn = QPushButton("Starten")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Herunterfahren")
        self.remote_btn = QPushButton("Fernzugriff einschalten")
        self.remote_btn.setToolTip("RDP aus dem Heimnetz – nur bei Bedarf, wirkt sofort")
        self.fullscreen_btn = QPushButton("Vollbild")
        self.fullscreen_btn.setToolTip("Fenster des Agent-PCs auf seinem Monitor als Vollbild – zurück mit Strg+Alt+F")
        self.ssh_btn = QPushButton("SSH-Befehl kopieren")
        self.ssh_btn.setToolTip("Befehl zum Anmelden per SSH in die Zwischenablage kopieren")
        self.delete_btn = QPushButton("Löschen")
        self.delete_btn.setObjectName("Danger")
        # Verschieben/Vergrößern stehen klein direkt bei „Speicherort“ bzw. „Festplatte“.
        self.move_btn = QPushButton("Verschieben …")
        self.move_btn.setToolTip("Auf ein anderes Laufwerk oder in einen anderen Ordner verschieben (ausgeschaltet)")
        self.resize_btn = QPushButton("Festplatte vergrößern …")
        self.resize_btn.setToolTip("Nur im ausgeschalteten Zustand – vergrößern geht, verkleinern nicht")
        self.upgrade_btn = QPushButton("Agent-PC aktualisieren")
        self.upgrade_btn.setToolTip("System, Flatpak-Programme und KI-Werkzeuge im laufenden Agent-PC aktualisieren")
        self.template_btn = QPushButton("Als Vorlage speichern …")
        self.template_btn.setToolTip("Aus diesem fertig eingerichteten Agent-PC eine Vorlage machen – neue Agent-PCs "
                                     "entstehen daraus in Sekunden. Das Original bleibt unverändert.")
        self.independent_btn = QPushButton("Unabhängig machen …")
        self.independent_btn.setToolTip("Daten der Vorlage übernehmen – danach braucht der Agent-PC die Vorlage nicht "
                                        "mehr (braucht mehr Platz, nur ausgeschaltet)")
        self.add_desktop_btn = QPushButton("Desktop hinzufügen …")
        self.add_desktop_btn.setToolTip("Weiteren Desktop installieren und als Standard wählen – der Agent-PC muss "
                                        "laufen; der bisherige bleibt installiert")
        self.add_apps_btn = QPushButton("Programme hinzufügen …")
        self.add_apps_btn.setToolTip("Fehlende Programme oder KI-Werkzeuge nachinstallieren – der Agent-PC muss laufen")
        for b in (self.move_btn, self.resize_btn, self.add_apps_btn, self.template_btn, self.independent_btn,
                  self.add_desktop_btn):
            b.setObjectName("Small")
        for b in (self.start_btn, self.stop_btn, self.fullscreen_btn, self.ssh_btn, self.remote_btn, self.upgrade_btn,
                  self.template_btn, self.delete_btn):
            row.addWidget(b)
        hl.addSpacing(6)
        hl.addLayout(row)

        # Hinweis während der unsichtbaren Ersteinrichtung bzw. nach einem Abbruch
        self.hint = QFrame()
        self.hint.setObjectName("Hint")
        hint_row = QHBoxLayout(self.hint)
        hint_row.setContentsMargins(12, 10, 12, 10)
        hint_row.setSpacing(12)
        self.hint_text = QLabel()
        self.hint_text.setWordWrap(True)
        self.peek_btn = QPushButton("Trotzdem anzeigen")
        self.peek_btn.setObjectName("Small")
        self.peek_btn.setToolTip("Das Fenster lässt sich erst nach der Einrichtung öffnen – "
                                 "hier siehst du stattdessen die Konsole groß.")
        self.resume_btn = QPushButton("Einrichtung fortsetzen")
        self.resume_btn.setObjectName("Primary")
        self.kill_btn = QPushButton("Sofort ausschalten")
        self.kill_btn.setObjectName("Danger")
        self.kill_btn.setToolTip("Wie Stecker ziehen – nicht gespeicherte Daten im Agent-PC gehen verloren")
        hint_buttons = FlowLayout(align_right=True)
        # Pfad separat: lange Pfade werden gekürzt statt das Fenster zu verbreitern
        self.hint_path = PathLabel(prefix="Vorlage: ")
        hint_col = QVBoxLayout()
        hint_col.setSpacing(4)
        hint_col.addWidget(self.hint_text)
        hint_col.addWidget(self.hint_path)
        hint_row.addLayout(hint_col, 3)
        hint_row.addLayout(hint_buttons, 1)
        hint_buttons.addWidget(self.peek_btn)
        hint_buttons.addWidget(self.resume_btn)
        hint_buttons.addWidget(self.kill_btn)
        hl.addSpacing(10)
        hl.addWidget(self.hint)

        # „Trotzdem anzeigen“: Zugang zum Agent-PC, während er sich unsichtbar einrichtet
        self.peek_tools = QWidget()
        pt = FlowLayout(self.peek_tools)
        pt.setContentsMargins(0, 6, 0, 0)
        self.terminal_btn = QPushButton("Terminal im Agent-PC öffnen")
        self.terminal_btn.setToolTip("Terminal dieses Rechners mit SSH-Anmeldung im Agent-PC "
                                     "(Benutzer und Passwort des Agent-PCs)")
        self.fetch_logs_btn = QPushButton("Einrichtungsprotokoll holen")
        self.fetch_logs_btn.setToolTip("Kopiert /var/log/bonys-agents.log und /var/log/cloud-init-output.log "
                                       "in den Ordner des Agent-PCs und zeigt sie an")
        self.screen_btn = QPushButton("Bildschirm anzeigen (SPICE)")
        self.screen_btn.setToolTip("Den echten Bildschirm des Agent-PCs per SPICE öffnen")
        for b in (self.terminal_btn, self.fetch_logs_btn, self.screen_btn):
            b.setObjectName("Small")
            pt.addWidget(b)
        self.peek_tools.setVisible(False)
        hl.addWidget(self.peek_tools)

        # Angaben in bis zu drei Spalten – bei schmalem Fenster rutschen sie untereinander
        self.d_info = QWidget()
        grid = ColumnLayout(self.d_info, columns=3, min_width=190)
        self.d_fields: dict[str, QLabel] = {}

        def field(title: str, span: int = 1) -> QVBoxLayout:
            cell = QWidget()
            cell.setProperty("span", span)  # Spalten, die das Feld belegt
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(6)
            k = QLabel(title.upper())
            k.setObjectName("Section")
            cl.addWidget(k)
            grid.addWidget(cell)
            return cl

        for key in ("CPU", "RAM", "Festplatte", "Desktop", "Benutzer", "Speicherort", "Programme"):
            cl = field(key)
            v = QLabel()
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setWordWrap(True)
            cl.addWidget(v)
            if key == "Speicherort":
                self.d_path = PathLabel()
                cl.addWidget(self.d_path)
            extra = {"Festplatte": self.resize_btn, "Speicherort": self.move_btn,
                     "Programme": self.add_apps_btn, "Desktop": self.add_desktop_btn}.get(key)
            if extra:
                br = FlowLayout()
                br.addWidget(extra)
                if key == "Festplatte":
                    br.addWidget(self.independent_btn)
                cl.addLayout(br)
            cl.addStretch(1)
            self.d_fields[key] = v
        # Bildschirm: Auflösung folgt dem Fenster (Standard), Zoom oder feste Größe
        self.screen_mode = QComboBox()
        for mode, text in screen.MODES.items():
            self.screen_mode.addItem(text, mode)
        self.screen_mode.setToolTip("Wie der Bildschirm des Agent-PCs ins QEMU-Fenster kommt – wirkt ab dem "
                                    "nächsten Start.\nNur wenn die automatische Anpassung nicht klappt, "
                                    "„Bild skalieren“ oder „Feste Auflösung“ wählen.")
        self.screen_size = QComboBox()
        self.screen_size.addItems(screen.SIZES)
        self.screen_size.setToolTip("Auflösung für „Bild skalieren“ und „Feste Auflösung“")
        self.driver_btn = QPushButton("Anzeige-Treiber aktualisieren")
        self.driver_btn.setObjectName("Small")
        self.driver_btn.setToolTip("Richtet im laufenden Agent-PC ein, dass die Auflösung dem Fenster folgt "
                                   "(für Agent-PCs von älteren Versionen; passiert auch bei „Agent-PC aktualisieren“)")
        self.screen_note = QLabel()
        self.screen_note.setObjectName("Muted")
        self.screen_note.setWordWrap(True)
        cl = field("Bildschirm", span=2)
        sr = FlowLayout()
        sr.addWidget(self.screen_mode)
        sr.addWidget(self.screen_size)
        sr.addWidget(self.driver_btn)
        cl.addLayout(sr)
        cl.addWidget(self.screen_note)
        cl.addStretch(1)
        hl.addSpacing(10)
        hl.addWidget(self.d_info)

        self.d_prog_label = QLabel()
        self.d_prog_label.setObjectName("Muted")
        self.d_prog_label.setWordWrap(True)
        self.d_prog = PercentBar()
        hl.addSpacing(8)
        hl.addWidget(self.d_prog_label)
        hl.addWidget(self.d_prog)
        lay.addWidget(head)

        # Unten umschaltbar: Konsole oder Fernzugriff
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tab_console = QPushButton("Konsole")
        self.tab_remote = QPushButton("Fernzugriff")
        self.tab_vpn = QPushButton("VPN")
        self.tab_vpn.setToolTip("Bony's VPN im Agent-PC: Status, verbinden, trennen, Konfiguration importieren")
        for b in (self.tab_console, self.tab_remote, self.tab_vpn):
            b.setObjectName("Tab")
            b.setCheckable(True)
            tabs.addWidget(b)
        tabs.addStretch(1)
        self.logs_btn = QPushButton("Protokolle öffnen")
        self.logs_btn.setObjectName("Small")
        self.logs_btn.setToolTip("Ordner des Agent-PCs mit console.log (auch ältere), qemu.log und "
                                 "geholten Einrichtungsprotokollen im Dateimanager öffnen")
        tabs.addWidget(self.logs_btn)
        self.tab_console.setChecked(True)
        lay.addLayout(tabs)
        self.lower = QStackedWidget()
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        self.console.setMinimumHeight(style.px(140))  # bleibt lesbar; reicht der Platz nicht, wird gescrollt
        self.remote_panel = RemotePanel()
        remote_scroll = QScrollArea()
        remote_scroll.setObjectName("Glass")
        remote_scroll.setWidgetResizable(True)
        remote_scroll.setFrameShape(QFrame.NoFrame)
        remote_scroll.setWidget(self.remote_panel)
        remote_scroll.setMinimumHeight(style.px(200))
        self.vpn_panel = VpnPanel()
        vpn_scroll = QScrollArea()
        vpn_scroll.setObjectName("Glass")
        vpn_scroll.setWidgetResizable(True)
        vpn_scroll.setFrameShape(QFrame.NoFrame)
        vpn_scroll.setWidget(self.vpn_panel)
        vpn_scroll.setMinimumHeight(style.px(200))
        self.lower.addWidget(self.console)
        self.lower.addWidget(remote_scroll)
        self.lower.addWidget(vpn_scroll)
        lay.addWidget(self.lower, 1)
        self.tab_console.clicked.connect(lambda: self._show_tab(0))
        self.tab_remote.clicked.connect(lambda: self._show_tab(1))
        self.tab_vpn.clicked.connect(lambda: self._show_tab(2))
        self.remote_panel.changed.connect(self.refresh_detail)
        self.vpn_panel.install_requested.connect(lambda: self.add_apps(preselect=["vpn"]))

        self.start_btn.clicked.connect(self.start_vm)
        self.stop_btn.clicked.connect(self.stop_vm)
        self.kill_btn.clicked.connect(lambda: self.current() and self._power_off(self.current()))
        self.remote_btn.clicked.connect(self.toggle_remote)
        self.delete_btn.clicked.connect(self.delete_vm)
        self.ssh_btn.clicked.connect(self.copy_ssh)
        self.fullscreen_btn.clicked.connect(self._fullscreen)
        self.screen_mode.activated.connect(self._set_screen)
        self.screen_size.activated.connect(self._set_screen)
        self.driver_btn.clicked.connect(lambda: self._update_driver())
        self.move_btn.clicked.connect(self.move_vm)
        self.resize_btn.clicked.connect(self.resize_vm)
        self.add_apps_btn.clicked.connect(lambda: self.add_apps())
        self.add_desktop_btn.clicked.connect(self.add_desktop)
        self.template_btn.clicked.connect(self.save_template)
        self.independent_btn.clicked.connect(self.make_independent)
        self.upgrade_btn.clicked.connect(self.upgrade_vm)
        self.resume_btn.clicked.connect(lambda: self._clear_notice() or self._run(lambda m: m.start(headless=True)))
        self.peek_btn.clicked.connect(self._peek)
        self.logs_btn.clicked.connect(lambda: self.current() and open_url(str(self.current().path)))
        self.terminal_btn.clicked.connect(self._open_terminal)
        self.fetch_logs_btn.clicked.connect(lambda: self._fetch_logs())
        self.screen_btn.clicked.connect(self._show_screen)
        return w

    def _show_tab(self, index: int) -> None:
        self.lower.setCurrentIndex(index)
        # Fernzugriff braucht Platz: Detailangaben solange einklappen
        self.d_info.setVisible(index == 0 and not self._console_big)
        self.tab_console.setChecked(index == 0)
        self.tab_remote.setChecked(index == 1)
        self.tab_vpn.setChecked(index == 2)
        self.refresh_detail()

    def _peek(self) -> None:
        """„Trotzdem anzeigen“: Konsole groß, dazu Terminal, Protokolle und – wenn möglich – der Bildschirm."""
        self._set_console_big(not self._console_big)

    def _show_screen(self) -> None:
        m = self.current()
        if not m:
            return
        try:
            m.connect("SPICE")
        except RuntimeError as e:
            QMessageBox.information(self, APP_NAME, str(e))

    def _fullscreen(self) -> None:
        m = self.current()
        if not m:
            return
        try:
            self.statusBar().showMessage(f"{m.name}: {m.fullscreen()}", 8000)
        except RuntimeError as e:
            QMessageBox.information(self, APP_NAME, str(e))

    def _set_screen(self) -> None:
        m = self.current()
        if not m:
            return
        try:
            m.set_screen(self.screen_mode.currentData(), self.screen_size.currentText())
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
        self.refresh_detail()

    def _update_driver(self, password: str | None = None) -> None:
        m = self.current()
        if not m:
            return
        self.driver_btn.setEnabled(False)
        self.statusBar().showMessage(f"Anzeige-Treiber in „{m.name}“ wird eingerichtet …")
        w = TaskWorker(lambda: m.update_display_driver(password=password))

        def failed(msg: str) -> None:
            self.statusBar().clearMessage()
            if isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, f"{msg}\n\nPasswort von „{m.name}“:",
                                              QLineEdit.Password)
                if ok and pw:
                    self._update_driver(pw)
                return
            QMessageBox.warning(self, APP_NAME, msg)

        def done() -> None:
            if w.error is None and w.result:
                self.statusBar().showMessage(f"{m.name}: {w.result}", 10000)
            self.refresh_detail()

        w.failed.connect(failed)
        w.finished.connect(done)
        self._keep(w)

    def _open_terminal(self) -> None:
        m = self.current()
        if not m:
            return
        try:
            m.open_terminal()
            self.statusBar().showMessage(f"Terminal geöffnet – Anmeldung als „{m.config.username}“ mit dem "
                                         "Passwort des Agent-PCs.", 8000)
        except (RuntimeError, OSError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))

    def _fetch_logs(self, password: str | None = None) -> None:
        m = self.current()
        if not m:
            return
        self.fetch_logs_btn.setEnabled(False)
        w = TaskWorker(lambda: m.fetch_setup_logs(password=password))

        def failed(msg: str) -> None:
            self.fetch_logs_btn.setEnabled(True)
            if isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, f"{msg}\n\nPasswort von „{m.name}“:",
                                              QLineEdit.Password)
                if ok and pw:
                    self._fetch_logs(pw)
                return
            QMessageBox.warning(self, APP_NAME, msg)

        def done() -> None:
            self.fetch_logs_btn.setEnabled(True)
            if w.error is None and w.result:
                LogDialog(m, w.result, self).show()

        w.failed.connect(failed)
        w.finished.connect(done)
        self._keep(w)

    def _set_console_big(self, big: bool) -> None:
        """„Trotzdem anzeigen“: Konsole groß und ans Ende – ein unsichtbar gestartetes QEMU hat kein Fenster."""
        self._console_big = big
        self.d_info.setVisible(not big and self.lower.currentIndex() == 0)
        self.peek_btn.setText("Kleiner anzeigen" if big else "Trotzdem anzeigen")
        self.peek_tools.setVisible(big)
        m = self.current()
        try:
            spice = bool(big and m and m.remote_info()["spice_supported"] and remote.spice_viewer_available())
        except RuntimeError:
            spice = False
        self.screen_btn.setVisible(spice)
        if big:
            self._show_tab(0)
            bar = self.console.verticalScrollBar()
            bar.setValue(bar.maximum())
            self.console.setFocus()

    def _missing_page(self) -> QWidget:
        w = _card()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 22, 24, 22)
        self.m_name = QLabel()
        self.m_name.setObjectName("Title")
        status = QLabel("●  nicht verfügbar")
        status.setStyleSheet(f"color: {style.MUTED};")
        self.m_path = PathLabel(prefix="Lag zuletzt in: ")
        self.m_text = QLabel("Das Laufwerk ist gerade nicht erreichbar. Steck die SSD/Festplatte ein – der Agent-PC "
                             "taucht dann automatisch wieder auf, auch unter einem anderen Laufwerksbuchstaben.")
        self.m_text.setWordWrap(True)
        row = QHBoxLayout()
        again = QPushButton("Erneut suchen")
        again.setObjectName("Primary")
        forget = QPushButton("Aus Liste entfernen")
        forget.setToolTip("Löscht nichts – der Agent-PC bleibt auf dem Laufwerk und taucht beim Einstecken wieder auf.")
        row.addWidget(again)
        row.addWidget(forget)
        row.addStretch(1)
        for x in (self.m_name, status):
            lay.addWidget(x)
        lay.addSpacing(10)
        lay.addWidget(self.m_path)
        lay.addSpacing(8)
        lay.addWidget(self.m_text)
        lay.addSpacing(12)
        lay.addLayout(row)
        lay.addStretch(1)
        again.clicked.connect(self._rescan)
        forget.clicked.connect(self._forget_missing)
        return w

    # ---------- Aktualisieren ----------
    def current_entry(self) -> vm.VM | vm.MissingVM | None:
        item = self.list.currentItem()
        return self.entries.get(item.data(Qt.UserRole)) if item else None

    def current(self) -> vm.VM | None:
        e = self.current_entry()
        return e if isinstance(e, vm.VM) else None

    def refresh(self) -> None:
        vm.reap_children()  # beendete QEMU-Prozesse einsammeln (sonst Zombies, die als „läuft“ gelten)
        entries = vm.list_all()
        self.entries = {e.name: e for e in entries}
        selected = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        names = [e.name for e in entries]
        if names != [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]:
            self.list.blockSignals(True)
            self.list.clear()
            for e in entries:
                it = QListWidgetItem(e.name)
                it.setData(Qt.UserRole, e.name)
                self.list.addItem(it)
            self.list.blockSignals(False)
            if selected in names:
                self.list.setCurrentRow(names.index(selected))
            elif names:
                self.list.setCurrentRow(0)
        stopping = False
        for i, e in enumerate(entries):
            item = self.list.item(i)
            item.setIcon(_dot(style.STATUS_COLORS.get(e.status(), style.MUTED)))
            missing = isinstance(e, vm.MissingVM)
            remote_on = not missing and e.remote_active()
            desk = "" if missing else f"  ·  {desktops.name(e.config.desktop)}"
            item.setText(e.name + desk + (REMOTE_MARK if remote_on else ""))
            item.setForeground(QColor(style.MUTED if missing else style.TEXT))
            tip = f"Nicht verfügbar – liegt auf {e.path}" if missing else str(e.path)
            item.setToolTip(tip + ("\nFernzugriff ist an" if remote_on else ""))
            # Herunterfahren überwachen: nach STOP_TIMEOUT Sekunden hart ausschalten
            waited = None if missing else e.stopping_for()
            if waited is not None:
                stopping = True
                if waited >= vm.STOP_TIMEOUT and e.name not in self._powering_off:
                    self._power_off(e, automatic=True)
        # Countdown sekundengenau, sonst reicht alle 2 Sekunden
        self.timer.setInterval(1000 if stopping else 2000)
        # „Fernzugriff nur bis zum Herunterfahren“: Neustart im Gast erkennen (etwa alle 15 s)
        self._ticks += 1
        if self._ticks % 8 == 0:
            self._check_remote_resets([e for e in entries if isinstance(e, vm.VM)])
        # Ersteinrichtung fertig und Gast ausgeschaltet → jetzt mit Fenster starten
        # (greift auch, wenn die App beim Ende der Einrichtung geschlossen war).
        for e in entries:
            if isinstance(e, vm.VM) and e.name not in self._autostarting and e.needs_window_start():
                self._start_with_window(e)
        self.refresh_detail()

    def _start_with_window(self, m: vm.VM) -> None:
        self._autostarting.add(m.name)
        w = TaskWorker(m.finish_first_boot)
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.finished.connect(lambda: (self._autostarting.discard(m.name), self.refresh()))
        self.workers = [x for x in self.workers if x.isRunning()] + [w]
        w.start()
        self.statusBar().showMessage(f"„{m.name}“ ist eingerichtet und startet jetzt mit Desktop.", 8000)

    def refresh_detail(self) -> None:
        if self.vpn_mode:
            self.stack.setCurrentIndex(3)
            return
        entry = self.current_entry()
        if entry is None:
            self.stack.setCurrentIndex(0)
            return
        if isinstance(entry, vm.MissingVM):
            self.stack.setCurrentIndex(2)
            self.m_name.setText(entry.name)
            self.m_path.set_path(entry.path)
            return
        m = entry
        self.stack.setCurrentIndex(1)
        c = m.config
        status = m.status()
        running = m.is_running()
        waited = m.stopping_for() if status == vm.STATUS_STOPPING else None
        stopping = waited is not None
        hidden_setup = running and c.first_boot_pending and not stopping
        aborted = status == vm.STATUS_ABORTED
        about_to_start = status == vm.STATUS_READY_FOR_DESKTOP
        notice = self._notices.get(c.name) if not running else None
        tpl_missing = status == vm.STATUS_TEMPLATE_MISSING
        tpl_lock = m.template_lock_pid() is not None
        if tpl_missing and not notice:
            notice = HINT_TEMPLATE_MISSING
        elif tpl_lock and not notice:
            notice = HINT_TEMPLATE_LOCK
        self.hint.setVisible(hidden_setup or aborted or about_to_start or stopping or bool(notice))
        self.hint.setProperty("tone", "danger" if aborted or notice and not tpl_lock else "")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        if aborted and not notice:
            cause = m.abort_reason()
            abort_text = f"{HINT_ABORTED}\n\nUrsache: {cause.reason}" + (f"\n{cause.detail}" if cause.detail else "")
        else:
            abort_text = HINT_ABORTED
        self.hint_text.setText(HINT_STOPPING if stopping else notice if notice else abort_text if aborted
                               else HINT_READY if about_to_start else HINT_SETUP)
        self.hint_path.set_path(m.backing_file() if notice == HINT_TEMPLATE_MISSING else "")
        self.hint_path.setVisible(notice == HINT_TEMPLATE_MISSING)
        self.peek_btn.setVisible(hidden_setup)
        self.resume_btn.setVisible(aborted and not notice)
        self.kill_btn.setVisible(stopping and waited >= vm.STOP_OFFER_KILL_AFTER)
        self.kill_btn.setEnabled(c.name not in self._powering_off)
        self.start_btn.setVisible(not aborted)
        if self._console_big and not hidden_setup:
            self._set_console_big(False)
        self.d_name.setText(c.name)
        shown = status
        if stopping:
            shown = f"{status} … noch {max(0, round(vm.STOP_TIMEOUT - waited))} s"
            if c.name in self._powering_off:
                shown = "wird ausgeschaltet …"
        self.d_status.setText(f"●  {shown}")
        self.d_status.setStyleSheet(f"color: {style.STATUS_COLORS.get(status, style.MUTED)};")
        self.d_fields["CPU"].setText(f"{c.cpus} Kerne")
        self.d_fields["RAM"].setText(f"{c.ram_mb / 1024:.1f} GB")
        linked = m.is_linked()
        disk_text = f"{vm.format_gb(c.disk_gb)} (dynamisch)"
        if linked:
            disk_text += f"\nverknüpft mit Vorlage „{c.template or m.backing_file().parent.name}“"
        elif c.template:
            disk_text += f"\naus Vorlage „{c.template}“"
        self.d_fields["Festplatte"].setText(disk_text)
        self.d_fields["Benutzer"].setText(c.username)
        others = [desktops.name(d) for d in c.extra_desktops]
        self.d_fields["Desktop"].setText(desktops.name(c.desktop) + (f"\nauch: {', '.join(others)}" if others else ""))
        self.d_fields["Programme"].setText(", ".join(apps.names(c.apps)) or "–")
        drive = storage.drive_for(m.path)
        where = drive.label if drive else ""
        self.d_fields["Speicherort"].setText(where)
        self.d_fields["Speicherort"].setVisible(bool(where))
        self.d_path.set_path(m.path)

        busy = any(w.isRunning() for w in self.workers)
        blocked = tpl_missing or tpl_lock
        self.start_btn.setEnabled(not running and not busy and not about_to_start and not blocked)
        self.resume_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(running and not busy and not stopping)
        self.ssh_btn.setEnabled(running)
        window = running and not c.first_boot_pending and c.display != "spice"
        self.fullscreen_btn.setVisible(window or not running)
        self.fullscreen_btn.setEnabled(window and not stopping)
        mode, size = m.screen_settings()
        self.screen_mode.setCurrentIndex(max(0, self.screen_mode.findData(mode)))
        if self.screen_size.findText(size) < 0:
            self.screen_size.addItem(size)
        self.screen_size.setCurrentText(size)
        self.screen_size.setVisible(mode != screen.AUTO)
        self.driver_btn.setEnabled(status == "läuft" and not busy)
        self.screen_note.setText("gilt ab dem nächsten Start" if m.screen_pending() else
                                 "SPICE-Fenster: Remmina/remote-viewer passt die Auflösung an"
                                 if c.display == "spice" else "")
        self.screen_note.setVisible(bool(self.screen_note.text()))
        remote_on = m.remote_active() or (not running and c.remote_permanent)
        self.remote_btn.setText("Fernzugriff ausschalten" if remote_on else "Fernzugriff einschalten")
        self.remote_btn.setVisible("xrdp" in c.apps or remote_on)
        self.remote_btn.setEnabled(not busy and not stopping and (status in ("läuft", "gestoppt") or remote_on))
        self.move_btn.setEnabled(not running and not busy and not blocked)
        self.resize_btn.setEnabled(not running and not busy and not blocked and c.disk_gb < vm.MAX_DISK_GB)
        self.independent_btn.setVisible(linked)
        self.independent_btn.setEnabled(not running and not busy and not blocked)
        finished = m.progress().ready and not c.first_boot_pending
        self.template_btn.setEnabled(finished and not busy and not blocked and not stopping)
        missing = m.missing_apps()
        self.add_apps_btn.setVisible(bool(missing))
        self.add_apps_btn.setEnabled(status == "läuft" and not busy)
        self.add_desktop_btn.setEnabled(status == "läuft" and not busy)
        self.delete_btn.setEnabled(not busy and not tpl_lock)
        self.upgrade_btn.setEnabled(status == "läuft" and not busy)

        p = m.progress()
        show = (running and not p.ready) or (c.first_boot_pending and (running or about_to_start))
        self.d_prog.setVisible(show)
        self.d_prog_label.setVisible(show)
        if show:
            self.d_prog.set_percent(p.percent)
            if p.ready:
                what = "Einrichtung fertig – startet gleich mit Desktop"
            elif p.resumed:
                what = f"Schritt {p.step} von {p.total} – {p.title} (wird nach dem Neustart fortgesetzt …)"
            elif p.total:
                what = f"Schritt {p.step} von {p.total} – {p.title}"
                if p.resume_step:
                    what += f"  ·  fortgesetzt ab Schritt {p.resume_step}"
            elif c.template and not c.provisioned:
                what = "Erster Start aus der Vorlage – Rechnername, Passwort und Schlüssel werden gesetzt …"
            else:
                what = "Agent-PC bootet und bereitet die Einrichtung vor …"
            eta = pct.format_eta(m.eta_seconds(p.percent)) if not p.ready else ""
            self.d_prog_label.setText(f"Einrichtung: {what}" + (f"  ·  {eta}" if eta else ""))

        if self.lower.currentIndex() == 1:
            self.remote_panel.update_for(m, status)
        elif self.lower.currentIndex() == 2:
            self.vpn_panel.update_for(m, status)
        text = m.console_tail(400)
        if text != self.console.toPlainText():
            bar = self.console.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 4
            self.console.setPlainText(text)
            if at_bottom:
                bar.setValue(bar.maximum())

    # ---------- Aktionen ----------
    def _clear_notice(self) -> None:
        m = self.current()
        if m:
            self._notices.pop(m.name, None)

    def start_vm(self) -> None:
        self._clear_notice()
        self._run(lambda m: m.start())

    def stop_vm(self) -> None:
        """Herunterfahren: Status sofort umschalten, der Rest läuft im Hintergrund – nie blockierend."""
        m = self.current()
        if not m:
            return
        self._notices.pop(m.name, None)
        m.mark_stopping()

        def press() -> None:
            if not m.request_stop():
                m.power_off()  # QEMU nicht erreichbar – dann eben hart

        w = TaskWorker(press)
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.finished.connect(self.refresh)
        self._keep(w)
        self.refresh_detail()

    def _power_off(self, m: vm.VM, automatic: bool = False) -> None:
        """„Sofort ausschalten“ (QMP quit bzw. kill) – auch automatisch nach Ablauf der Wartezeit."""
        self._powering_off.add(m.name)
        if automatic:
            text = (f"„{m.name}“ hat nicht innerhalb von {vm.STOP_TIMEOUT} Sekunden reagiert "
                    "und wurde hart ausgeschaltet.")
            self._notices[m.name] = text
            self.statusBar().showMessage(text, 15000)
        w = TaskWorker(m.power_off)
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.finished.connect(lambda: (self._powering_off.discard(m.name), self.refresh()))
        self._keep(w)
        self.refresh_detail()

    def toggle_remote(self) -> None:
        m = self.current()
        if not m:
            return
        running = m.is_running()
        if m.remote_active() or (not running and m.config.remote_permanent):
            on, permanent = False, False
        else:
            dlg = RemoteDialog(m, running, self)
            if not dlg.exec():
                return
            on, permanent = True, dlg.permanent.isChecked()

        def done(message) -> None:
            if message:
                self.statusBar().showMessage(f"{m.name}: {message}", 10000)
                if on and remote.firewall_needed():
                    self.remote_panel._firewall(ask=True, machine=m)
            self.refresh()

        self.remote_btn.setEnabled(False)
        self.statusBar().showMessage(f"Fernzugriff für „{m.name}“ wird {'ein' if on else 'aus'}geschaltet …")
        switch_remote(self, m, on, permanent, done)

    def _check_remote_resets(self, machines: list[vm.VM]) -> None:
        """Im Hintergrund: Wurde ein Agent-PC mit „nur bis zum Herunterfahren“ neu gestartet?"""
        if self._remote_check and self._remote_check.isRunning():
            return
        candidates = [m for m in machines if m.remote_active() and not m.config.remote_permanent]
        if not candidates:
            return

        def check() -> list[str]:
            return [m.name for m in candidates if m.check_remote_reset()]

        w = TaskWorker(check)
        w.finished.connect(lambda: w.result and self.statusBar().showMessage(
            "Fernzugriff nach Neustart ausgeschaltet: " + ", ".join(w.result), 10000))
        self._remote_check = w
        w.start()

    def _keep(self, w: TaskWorker) -> None:
        self.workers = [x for x in self.workers if x.isRunning()] + [w]
        w.start()

    def _run(self, fn) -> None:
        m = self.current()
        if not m:
            return
        w = TaskWorker(lambda: fn(m))
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.finished.connect(self.refresh)
        self.workers = [x for x in self.workers if x.isRunning()] + [w]
        w.start()
        self.refresh_detail()

    def create_vm(self) -> None:
        if not deps.check(self.info).can_run:
            self.show_doctor()
            if not deps.check(self.info).can_run:
                return
        dlg = CreateDialog(self.info, self)
        if dlg.exec() and dlg.created_name:
            self.refresh()
            for i in range(self.list.count()):  # Text enthält auch den Desktop – über den Namen suchen
                if self.list.item(i).data(Qt.UserRole) == dlg.created_name:
                    self.list.setCurrentRow(i)
                    break

    def delete_vm(self) -> None:
        m = self.current()
        if not m:
            return
        answer = QMessageBox.question(
            self, APP_NAME,
            f"„{m.name}“ wirklich löschen?\nAlle Daten in diesem Agent-PC gehen verloren.",
        )
        if answer == QMessageBox.Yes:
            self._run(lambda mm: mm.delete())

    def move_vm(self) -> None:
        m = self.current()
        if not m:
            return
        if MoveDialog(m, self).exec():
            self.refresh()
            self.statusBar().showMessage(f"„{m.name}“ wurde verschoben.", 5000)

    def add_apps(self, preselect: list[str] | None = None) -> None:
        m = self.current()
        if not m or not m.missing_apps():
            return
        InstallAppsDialog(m, self, preselect=preselect or []).exec()
        self.refresh()

    def save_template(self) -> None:
        m = self.current()
        if not m:
            return
        dlg = SaveTemplateDialog(m, self)
        if dlg.exec() and dlg.result_template:
            t = dlg.result_template
            QMessageBox.information(self, APP_NAME, f"Vorlage „{t.name}“ ist fertig ({t.size / storage.GB:.1f} GB).\n\n"
                                    "Neue Agent-PCs daraus: „+ Neuer Agent-PC“ → Grundlage.")
        self.refresh()

    def show_templates(self) -> None:
        TemplatesDialog(self).exec()
        self.refresh()

    def make_independent(self) -> None:
        m = self.current()
        if not m or not m.is_linked():
            return
        if QMessageBox.question(self, APP_NAME, f"„{m.name}“ unabhängig machen?\n\nDie Daten der Vorlage werden in "
                                "seine Festplatte übernommen – das braucht mehr Platz und kann ein paar Minuten "
                                "dauern. Danach braucht er die Vorlage nicht mehr.") != QMessageBox.Yes:
            return
        w = FnWorker(lambda progress: m.make_independent(
            lambda f: progress("detach", f, f"„{m.name}“ wird unabhängig … {f * 100:.0f} %")))
        w.progress.connect(lambda _p, _f, msg: self.statusBar().showMessage(msg))
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.done.connect(lambda _r: self.statusBar().showMessage(f"„{m.name}“ ist jetzt unabhängig.", 8000))
        w.finished.connect(self.refresh)
        self.workers = [x for x in self.workers if x.isRunning()] + [w]
        w.start()
        self.refresh_detail()

    def add_desktop(self) -> None:
        m = self.current()
        if not m:
            return
        AddDesktopDialog(m, self).exec()
        self.refresh()

    def resize_vm(self) -> None:
        m = self.current()
        if not m or m.config.disk_gb >= vm.MAX_DISK_GB:
            return
        if ResizeDialog(m, self).exec():
            self.refresh()
            self.statusBar().showMessage(
                f"Festplatte von „{m.name}“ ist jetzt {vm.format_gb(m.config.disk_gb)} groß.", 6000)

    def import_vm(self) -> None:
        start = str(storage.preferred_library().parent)
        chosen = QFileDialog.getExistingDirectory(
            self, "Ordner mit Agent-PC(s) wählen (z. B. BonysAgents auf der SSD)", start
        )
        if not chosen:
            return
        try:
            added = vm.import_path(Path(chosen))
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.refresh()
        names = ", ".join(m.name for m in added)
        self.statusBar().showMessage(f"Hinzugefügt: {names}", 6000)

    def _rescan(self) -> None:
        storage.invalidate_cache()
        self.refresh()

    def _forget_missing(self) -> None:
        e = self.current_entry()
        if isinstance(e, vm.MissingVM):
            vm.forget_missing(e.name)
            self.refresh()

    def copy_ssh(self) -> None:
        m = self.current()
        if not m:
            return
        cmd = f"ssh -p {m.runtime().get('ssh_port')} {m.config.username}@127.0.0.1"
        QGuiApplication.clipboard().setText(cmd)
        self.statusBar().showMessage(f"Kopiert: {cmd}", 4000)

    def show_doctor(self) -> None:
        SetupDialog(self.info, self).exec()
        self.info = host.detect()


class LogDialog(QDialog):
    """Geholte Einrichtungsprotokolle anzeigen (je Datei ein Reiter)."""

    def __init__(self, machine: vm.VM, files: list[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Einrichtungsprotokoll – {machine.name}")
        fit_to_screen(self, 900, 600)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        for f in files:
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setPlainText(f.read_text("utf-8", errors="replace"))
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
            tabs.addTab(view, f.name)
        lay.addWidget(tabs, 1)
        where = PathLabel(machine.path, prefix="Gespeichert in ")
        where.setObjectName("Muted")
        lay.addWidget(where)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        folder = buttons.addButton("Ordner öffnen", QDialogButtonBox.ActionRole)
        folder.clicked.connect(lambda: open_url(str(machine.path)))
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
