# SPDX-License-Identifier: GPL-3.0-or-later
"""Hauptfenster: Liste der Agent-PCs links, Details rechts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from bonys_agents import (
    APP_NAME, INTRO_VIDEO_URL, REPO_URL, TAGLINE, YOUTUBE_CHANNEL_URL, __version__, apps, cloudinit, deps, desktops,
    distros, edition, host, kurse, kurspaket, netz, remote,
    screen, storage, updates, vm, vpnlink,
)
from bonys_agents import i18n
from bonys_agents import progress as pct
from bonys_agents.i18n import n_, tr

from . import musik_ui, style
from .about_dialog import AboutDialog
from .create_dialog import CreateDialog
from .desktop_dialog import AddDesktopDialog
from .host_vpn import button_text, linux_vpn, mac_wireguard, vpn_icon, windows_wireguard
from .install_dialog import InstallAppsDialog
from .kurse_dialog import KurseDialog
from .mc_panel import McPanel
from .remote_panel import RemoteDialog, RemotePanel, switch_remote
from .vpn_panel import VpnPanel
from .move_dialog import MoveDialog
from .netz_dialog import NetzDialog
from .resize_dialog import ResizeDialog
from .resources_dialog import ResourcesDialog
from .setup_dialog import SetupDialog
from .template_dialogs import FnWorker, SaveTemplateDialog, TemplatesDialog
from .updates_ui import CheckWorker, UpdateBanner, UpgradeDialog, start_update
from .widgets import (
    ColumnLayout, FlowLayout, PathLabel, PercentBar, ScaledLogo, available_geometry, confirm_delete, fit_to_screen,
    open_url,
)
from .workers import TaskWorker


# Englische Fassungen der Handbücher (docs/handbuch/en/)
HANDBUCH_EN = {"Benutzerhandbuch": "User-Guide", "Kursleiter-Handbuch": "Trainer-Guide"}


def handbuch_url(name: str) -> str:
    """Handbuch als PDF am Release genau dieser Version (docs/handbuch/, die Release-Aktion hängt es an) – in der
    Sprache der Oberfläche."""
    if i18n.sprache() == i18n.ENGLISCH:
        name = HANDBUCH_EN.get(name, name)
    return f"{REPO_URL}/releases/download/v{__version__}/BonysAgents-{name}-{__version__}.pdf"


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


NETZ_COLORS = {netz.IM_NETZ: style.OK, netz.OFFLINE: style.WARN, netz.NICHT_VERBUNDEN: style.MUTED}


def _dot_netz(color: str, netz_color: str | None) -> QIcon:
    """Zustandspunkt und rechts daneben ein kleines Netz-Symbol (drei verbundene Punkte) – oder Platz dafür."""
    pm = QPixmap(30, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    if netz_color:
        pts = (QPointF(22, 3.5), QPointF(17.5, 10.5), QPointF(26.5, 10.5))
        p.setPen(QPen(QColor(netz_color), 1.4))
        for a, b in ((0, 1), (0, 2), (1, 2)):
            p.drawLine(pts[a], pts[b])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(netz_color))
        for pt in pts:
            p.drawEllipse(pt, 2.3, 2.3)
    p.end()
    return QIcon(pm)


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


HINT_SETUP = n_("Der Agent-PC richtet sich im Hintergrund ein. "
                "Das Fenster öffnet sich automatisch, sobald der Desktop bereit ist.")
HINT_ABORTED = n_("Die Einrichtung wurde unterbrochen, bevor der Desktop fertig war. "
                  "Sie kann fortgesetzt werden – erledigte Schritte werden übersprungen.")
HINT_READY = n_("Einrichtung fertig – der Agent-PC startet gleich mit Desktop …")
HINT_TEMPLATE_MISSING = n_("Dieser Agent-PC baut auf einer Vorlage auf, die gerade nicht erreichbar ist (Pfad "
                           "darunter). Steck das Laufwerk mit der Vorlage ein – dann ist der Agent-PC wieder "
                           "verfügbar.")
HINT_TEMPLATE_LOCK = n_("Aus diesem Agent-PC wird gerade eine Vorlage erstellt. Bis das fertig ist, lässt er sich "
                        "nicht starten (das Original bleibt dabei unverändert).")
HINT_STOPPING = n_("Der Agent-PC fährt herunter. Reagiert er nicht, kannst du ihn sofort ausschalten – "
                   "nach {sekunden} Sekunden geschieht das automatisch.")
HINT_SETUP_FAILED = n_("Bei der Einrichtung ist etwas schiefgegangen: {steps}. Fehlende Programme über "
                       "„Programme hinzufügen …“ nachinstallieren – Einzelheiten im Protokoll.")
MISSING_TEXT = n_("Das Laufwerk ist gerade nicht erreichbar. Steck die SSD/Festplatte ein – der Agent-PC taucht dann "
                  "automatisch wieder auf, auch unter einem anderen Laufwerksbuchstaben.")
BROKEN_TEXT = n_("Die Einstellungsdatei vm.json dieses Agent-PCs ist beschädigt oder enthält unzulässige Angaben – die "
                 "Festplatte (disk.qcow2) im Ordner ist davon nicht betroffen. Liegt dort eine vm.json.bak, wird sie "
                 "automatisch genutzt. Sonst den Ordner bitte nicht löschen, sondern Hilfe holen "
                 "(github.com/zappotex/BonysAgents/issues) – die Datei lässt sich meist reparieren.")
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
        self._vpn_check: TaskWorker | None = None
        self._vpn_checked: set[tuple[str, int]] = set()  # (Agent-PC, QMP-Port) – einmal je Start prüfen
        # Bony-Netz: Geräteliste der Instanz (nach Netzname), höchstens alle 30 s und nur bei sichtbarem Fenster
        self._netz_check: TaskWorker | None = None
        self._netz_geraete: dict[str, dict] | None = None
        self._netz_fehler = ""
        self._netz_zuletzt = 0.0
        # Kurse über das Bony-Netz: „Der Kurs X hat begonnen“ (höchstens jede Minute fragen)
        self._kurse_check: TaskWorker | None = None
        self._kurse_zuletzt = 0.0
        self._kurse_aktiv: bool | None = None   # None: noch nicht gefragt; False: keine Teilnahmen
        self._kurse_beobachter = kurse.Beobachter()
        self._ticks = 0
        self._console_big = False
        self.entries: dict[str, vm.VM | vm.MissingVM] = {}
        self.setWindowTitle(edition.NAME)

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
        tagline = QLabel(tr(TAGLINE))
        tagline.setObjectName("Tagline")
        tagline.setWordWrap(True)  # bei schmalem Fenster zweizeilig statt abgeschnitten
        self.about_btn = QPushButton("ⓘ")
        self.about_btn.setObjectName("Quiet")
        self.about_btn.setToolTip(tr("Über {name}, Updates", name=edition.NAME))
        self.about_btn.setMenu(self._build_menu())
        title_row = QHBoxLayout()
        title_row.setSpacing(2)
        title_row.addWidget(title)
        title_row.addWidget(self.about_btn)
        title_row.addStretch(1)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addLayout(title_row)
        if edition.IS_TRAINER:
            # Eigene kleine Zeile statt „Bony's Agents Kursleiter“ im Titel – der lange Titel machte das Fenster
            # bei großer Anzeige zu breit
            ed = QLabel(tr(edition.LABEL))
            ed.setObjectName("Tagline")
            tcol.addWidget(ed)
        tcol.addWidget(tagline)
        tcol.addStretch(1)
        top.addWidget(logo, 0, Qt.AlignTop)
        top.addLayout(tcol, 1)
        # Knöpfe rechts; bei schmalem Fenster brechen sie in eine zweite Zeile um
        top_buttons = FlowLayout(align_right=True)
        top.addLayout(top_buttons)
        self.youtube_btn = QPushButton("▶  YouTube")
        self.youtube_btn.setObjectName("Quiet")
        self.youtube_btn.setToolTip(tr("Anleitungen und Videos auf meinem YouTube-Kanal"))
        self.doctor_btn = QPushButton(tr("System prüfen"))
        self.import_btn = QPushButton(tr("Hinzufügen …"))
        self.import_btn.setToolTip(tr("Vorhandenen Agent-PC von einer SSD oder aus einem Ordner in die Liste "
                                      "aufnehmen"))
        self.templates_btn = QPushButton(tr("Vorlagen"))
        self.templates_btn.setToolTip(tr("Vorlagen verwalten: umbenennen, löschen, weitergeben, im Netzwerk freigeben, "
                                         "importieren"))
        # kurzer Text: der breiteste Knopf bestimmt die Mindestbreite des Fensters (150 % Zoom, 800 px)
        self.join_btn = QPushButton(tr("Kurse"))
        self.join_btn.setToolTip(
            tr("Kurse über das Bony-Netz: beitreten, anlegen und leiten – und Schulung im selben Netz beitreten "
               "(Vorlage vom Rechner des Kursleiters)") if edition.IS_TRAINER else
            tr("Kurse über das Bony-Netz: beitreten – und Schulung im selben Netz beitreten (Vorlage vom Rechner des "
               "Kursleiters)"))
        self.new_btn = QPushButton(tr("+  Neuer Agent-PC"))
        self.new_btn.setObjectName("Primary")
        # Bony's VPN für diesen Rechner – eigenes Programm (nur Linux; Windows/macOS: ⓘ → Extras)
        self.vpn_btn = QPushButton("VPN")
        self.vpn_btn.setIcon(vpn_icon())
        self.vpn_btn.setVisible(sys.platform.startswith("linux"))
        for b in (self.youtube_btn, self.doctor_btn, self.vpn_btn, self.import_btn, self.join_btn, self.templates_btn,
                  self.new_btn):
            top_buttons.addWidget(b)
        outer.addLayout(top)

        # Dezente Leiste, wenn es eine neue Version gibt
        self.update_banner = UpdateBanner()
        self.update_banner.update_requested.connect(lambda info: start_update(self, info))
        outer.addWidget(self.update_banner)
        # Hilfe-Modus (Teilnehmer): gut sichtbar, wenn der Kursleiter zusieht oder steuert
        from .course_ui import HelpBanner, HelpManager, ask_consent

        self.help_banner = HelpBanner()
        outer.addWidget(self.help_banner)
        helpers = HelpManager.get()
        helpers.view_requested.connect(lambda name: ask_consent(self, name, "view"))
        helpers.control_requested.connect(lambda name: ask_consent(self, name, "control"))
        helpers.closed.connect(lambda name, reason: self.statusBar().showMessage(f"{name}: {reason}", 10000))
        if edition.IS_TRAINER:
            from bonys_agents.trainer.gui.helpdesk_dialog import CourseHub

            CourseHub.get().new_request.connect(self._help_request_arrived)
        self._present_dialog = None
        self._helpdesk_dialog = None
        self._update_check: CheckWorker | None = None

        # ---------- Inhalt: Liste | Details, Aufteilung per Ziehen ----------
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.list = QListWidget()
        self.list.setMinimumWidth(150)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # lange Namen enden mit „…“
        self._icon_size = self.list.iconSize()
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.splitter.addWidget(self.list)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_page())
        self.stack.addWidget(self._detail_page())
        self.stack.addWidget(self._missing_page())
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
        self.join_btn.clicked.connect(self.show_courses)
        self.youtube_btn.clicked.connect(lambda: open_url(YOUTUBE_CHANNEL_URL))
        self.vpn_btn.clicked.connect(self.host_vpn)
        self._vpn_button_state()

        sysinfo = QLabel(tr("v{version}  ·  {os} / {arch}  ·  Beschleuniger: {accel}", version=__version__,
                            os=self.info.os, arch=self.info.arch, accel=self.info.accel))
        sysinfo.setObjectName("Muted")
        sysinfo.setWordWrap(True)
        self.statusBar().addPermanentWidget(sysinfo)
        # Musik & Radio: links neben der Versionsangabe (fehlt, wenn Qt Multimedia nicht vorhanden ist)
        self.musik = musik_ui.leiste(self)
        if self.musik:
            self.statusBar().insertPermanentWidget(0, self.musik)

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
        menu.addAction(tr("Über {name}", name=edition.NAME), lambda: AboutDialog(self).exec())
        menu.addAction(tr("Hilfe (Anleitung)"), lambda: open_url(handbuch_url("Benutzerhandbuch")))
        if edition.IS_TRAINER:
            menu.addAction(tr("Kursleiter-Handbuch"), lambda: open_url(handbuch_url("Kursleiter-Handbuch")))
        if not edition.IS_TRAINER:
            menu.addAction(tr("Du möchtest selbst Schulungen geben? → {name}", name=edition.NAMES[edition.KURSLEITER]),
                           lambda: open_url(edition.download_url()))
        menu.addSeparator()
        menu.addAction(tr("Nach Updates suchen"), lambda: self.check_updates(manual=True))
        st = updates.settings()
        auto = QAction(tr("Automatisch nach Updates suchen"), menu, checkable=True, checked=st["auto"])
        auto.toggled.connect(lambda on: updates.set_setting("auto", on))
        pre = QAction(tr("Testversionen anbieten"), menu, checkable=True, checked=st["prereleases"])
        pre.toggled.connect(lambda on: updates.set_setting("prereleases", on))
        menu.addAction(auto)
        menu.addAction(pre)
        menu.addSeparator()
        menu.addAction(tr("Alle Agent-PCs aktualisieren …"), self.upgrade_all)
        if edition.IS_TRAINER:
            menu.addAction(tr("Kursleitung: Hilfe-Anfragen …"), self.show_helpdesk)
            menu.addAction(tr("Kursportal: Moderation …"), self.show_moderation)
        menu.addSeparator()
        menu.addAction(tr("Bony-Netz …"), lambda: NetzDialog(self).exec())
        extras = menu.addMenu(tr("Extras"))
        if sys.platform.startswith("linux"):
            extras.addAction(tr("Bony's VPN für diesen Rechner"), self.host_vpn)
        elif sys.platform == "win32":
            extras.addAction(tr("WireGuard für diesen Rechner installieren …"), lambda: self._keep_worker(
                windows_wireguard(self)))
        elif sys.platform == "darwin":
            extras.addAction(tr("WireGuard für diesen Rechner (App Store) …"), lambda: mac_wireguard(self))
        menu.addSeparator()
        # Beschriftung in beiden Sprachen – man findet den Punkt, egal welche Sprache gerade läuft
        sprache = menu.addMenu("Sprache / Language")
        gruppe = QActionGroup(sprache)
        aktuell = i18n.einstellung()
        for wert, text in ((i18n.AUTO, tr("Automatisch (Sprache des Systems)")), (i18n.DEUTSCH, "Deutsch"),
                           (i18n.ENGLISCH, "English")):
            a = QAction(text, sprache, checkable=True, checked=wert == aktuell)
            a.triggered.connect(lambda _=False, w=wert: self.set_language(w))
            gruppe.addAction(a)
            sprache.addAction(a)
        view = menu.addMenu(tr("Ansicht: Anzeigegröße"))
        self.zoom_group = QActionGroup(view)
        for z in style.ZOOM_STEPS:
            a = QAction(f"{z} %", view, checkable=True, checked=z == style.zoom())
            a.setData(z)
            a.triggered.connect(lambda _=False, z=z: self.set_zoom(z))
            self.zoom_group.addAction(a)
            view.addAction(a)
        view.addSeparator()
        self.zoom_in = view.addAction(tr("Größer"), lambda: self.set_zoom(step=1))
        self.zoom_out = view.addAction(tr("Kleiner"), lambda: self.set_zoom(step=-1))
        self.zoom_reset = view.addAction(tr("Normalgröße (100 %)"), lambda: self.set_zoom(step=0))
        return menu

    def set_language(self, wert: str) -> None:
        """Sprache merken – sie gilt ab dem nächsten Start (alle Fenster werden beim Start aufgebaut)."""
        if wert == i18n.einstellung():
            return
        try:
            i18n.einstellung_setzen(wert)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        # Zweisprachig: Die neue Sprache gilt erst nach dem Neustart
        QMessageBox.information(self, APP_NAME, "Die Sprache wechselt beim nächsten Start von Bony's Agents.\n\n"
                                "The language changes the next time Bony's Agents starts.")

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
        self.statusBar().showMessage(tr("Anzeigegröße: {z} %", z=z), 3000)

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
        from .kursraum_fenster import alle_schliessen

        alle_schliessen()   # offene Kursräume verlassen (sie sind eigene Fenster)
        if self.musik:
            self.musik.abspieler.stop()
        super().closeEvent(event)

    def check_updates(self, manual: bool) -> None:
        if self._update_check and self._update_check.isRunning():
            return
        if not manual and updates.needs_consent():  # einmal fragen, bevor zum ersten Mal still gesucht wird
            yes = QMessageBox.question(self, APP_NAME, tr(updates.CONSENT_QUESTION)) == QMessageBox.Yes
            updates.set_setting("auto", yes)
            self.about_btn.setMenu(self._build_menu())  # Häkchen „Automatisch nach Updates suchen“ anpassen
            if not yes:
                return
        if manual:
            self.statusBar().showMessage(tr("Suche nach Updates …"))
        w = CheckWorker(manual)

        def found(info) -> None:
            if info:
                self.update_banner.show_update(info)
                self.statusBar().clearMessage()
            elif manual:
                self.update_banner.hide()
                self.statusBar().showMessage(tr("Keine Updates gefunden – {name} {version} ist aktuell.",
                                                name=APP_NAME, version=__version__), 8000)

        w.found.connect(found)
        self._update_check = w
        w.start()

    def upgrade_all(self) -> None:
        machines = [m for m in vm.list_vms() if m.is_running() and m.status() == "läuft"]
        if not machines:
            QMessageBox.information(self, APP_NAME, tr("Es läuft gerade kein fertig eingerichteter Agent-PC.\n"
                                                       "Agent-PCs werden aktualisiert, während sie laufen."))
            return
        names = ", ".join(m.name for m in machines)
        if QMessageBox.question(self, APP_NAME, tr("Diese Agent-PCs jetzt aktualisieren?\n\n{namen}",
                                                   namen=names)) == QMessageBox.Yes:
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
        t = QLabel(tr("Noch kein Agent-PC"))
        t.setObjectName("Title")
        t.setAlignment(Qt.AlignCenter)
        m = QLabel(tr("Ein Agent-PC ist ein eigener virtueller Rechner mit Desktop, "
                      "Brave, Telegram und Hermes Agent – sauber getrennt von deinem System."))
        m.setObjectName("Muted")
        m.setAlignment(Qt.AlignCenter)
        m.setWordWrap(True)
        b = QPushButton(tr("+  Ersten Agent-PC erstellen"))
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
        it = QLabel(tr("Neu hier? Auf meinem YouTube-Kanal zeige ich dir, wie Bony's Agents funktioniert."))
        it.setWordWrap(True)
        ib = QPushButton(tr("▶  Zum Vorstellungsvideo"))
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

    def _vpn_button_state(self) -> None:
        self.vpn_btn.setToolTip(tr("{knopf} – WireGuard für diesen ganzen Rechner (eigenes Programm)",
                                   knopf=button_text()))

    def host_vpn(self) -> None:
        """Knopf „VPN“: Bony's VPN öffnen bzw. installieren (nur Linux)."""
        w = linux_vpn(self)
        if w is not None:
            self.statusBar().showMessage(tr("Installiere Bony's VPN …"))
            w.finished.connect(lambda: (self.statusBar().clearMessage(), self._vpn_button_state()))
            self._keep_worker(w)

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
        self.start_btn = QPushButton(tr("Starten"))
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton(tr("Herunterfahren"))
        self.remote_btn = QPushButton(tr("Fernzugriff einschalten"))
        self.remote_btn.setToolTip(tr("RDP aus dem Heimnetz – nur bei Bedarf, wirkt sofort"))
        self.fullscreen_btn = QPushButton(tr("Vollbild"))
        self.fullscreen_btn.setToolTip(tr("Fenster des Agent-PCs auf seinem Monitor als Vollbild – zurück mit "
                                          "Strg+Alt+F"))
        self.ssh_btn = QPushButton(tr("SSH-Befehl kopieren"))
        self.ssh_btn.setToolTip(tr("Befehl zum Anmelden per SSH in die Zwischenablage kopieren"))
        self.delete_btn = QPushButton(tr("Löschen"))
        self.delete_btn.setObjectName("Danger")
        # Verschieben/Vergrößern stehen klein direkt bei „Speicherort“ bzw. „Festplatte“.
        self.move_btn = QPushButton(tr("Verschieben …"))
        self.move_btn.setToolTip(tr("Auf ein anderes Laufwerk oder in einen anderen Ordner verschieben "
                                    "(ausgeschaltet)"))
        self.resize_btn = QPushButton(tr("Festplatte vergrößern …"))
        self.resize_btn.setToolTip(tr("Nur im ausgeschalteten Zustand – vergrößern geht, verkleinern nicht"))
        self.resources_btn = QPushButton(tr("Leistung ändern …"))
        self.resources_btn.setToolTip(tr("CPU-Kerne und Arbeitsspeicher ändern – ein laufender Agent-PC wird dafür neu "
                                         "gestartet"))
        self.upgrade_btn = QPushButton(tr("Agent-PC aktualisieren"))
        self.upgrade_btn.setToolTip(tr("System, Flatpak-Programme und KI-Werkzeuge im laufenden Agent-PC "
                                       "aktualisieren"))
        self.template_btn = QPushButton(tr("Als Vorlage speichern …"))
        self.template_btn.setToolTip(tr("Aus diesem fertig eingerichteten Agent-PC eine Vorlage machen – neue "
                                        "Agent-PCs entstehen daraus in Sekunden. Das Original bleibt unverändert."))
        self.independent_btn = QPushButton(tr("Unabhängig machen …"))
        self.independent_btn.setToolTip(tr("Daten der Vorlage übernehmen – danach braucht der Agent-PC die Vorlage "
                                           "nicht mehr (braucht mehr Platz, nur ausgeschaltet)"))
        self.add_desktop_btn = QPushButton(tr("Desktop hinzufügen …"))
        self.add_desktop_btn.setToolTip(tr("Weiteren Desktop installieren und als Standard wählen – der Agent-PC muss "
                                           "laufen; der bisherige bleibt installiert"))
        self.wallpaper_btn = QPushButton(tr("Hintergrundbild aktualisieren"))
        self.wallpaper_btn.setObjectName("Small")
        self.wallpaper_btn.setToolTip(tr("Neues Standard-Hintergrundbild in den laufenden Agent-PC bringen – nur, wenn "
                                         "noch das alte aktiv ist (ein selbst gewähltes Bild bleibt, sonst Rückfrage)"))
        self.help_btn = QPushButton(tr("Hilfe anfordern …"))
        self.help_btn.setToolTip(tr("Schulung: den Kursleiter um Hilfe bitten – er sieht diesen Agent-PC nur, wenn du "
                                    "zustimmst"))
        self.present_btn: QPushButton | None = None   # nur Kursleiter-Version
        if edition.IS_TRAINER:
            self.present_btn = QPushButton(tr("Vorführen …"))
            self.present_btn.setToolTip(tr("Schulung: diesen Agent-PC live im Browser der Teilnehmer zeigen (nur "
                                           "ansehen)"))
        self.add_apps_btn = QPushButton(tr("Programme hinzufügen …"))
        self.add_apps_btn.setToolTip(tr("Fehlende Programme oder KI-Werkzeuge nachinstallieren – der Agent-PC muss "
                                        "laufen"))
        for b in (self.move_btn, self.resize_btn, self.resources_btn, self.add_apps_btn, self.template_btn,
                  self.independent_btn, self.add_desktop_btn):
            b.setObjectName("Small")
        for b in (self.start_btn, self.stop_btn, self.fullscreen_btn, self.ssh_btn, self.remote_btn, self.present_btn,
                  self.help_btn, self.upgrade_btn, self.template_btn, self.delete_btn):
            if b is not None:
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
        self.peek_btn = QPushButton(tr("Trotzdem anzeigen"))
        self.peek_btn.setObjectName("Small")
        self.peek_btn.setToolTip(tr("Das Fenster lässt sich erst nach der Einrichtung öffnen – "
                                    "hier siehst du stattdessen die Konsole groß."))
        self.resume_btn = QPushButton(tr("Einrichtung fortsetzen"))
        self.resume_btn.setObjectName("Primary")
        self.kill_btn = QPushButton(tr("Sofort ausschalten"))
        self.kill_btn.setObjectName("Danger")
        self.kill_btn.setToolTip(tr("Wie Stecker ziehen – nicht gespeicherte Daten im Agent-PC gehen verloren"))
        hint_buttons = FlowLayout(align_right=True)
        # Pfad separat: lange Pfade werden gekürzt statt das Fenster zu verbreitern
        self.hint_path = PathLabel(prefix=tr("Vorlage: "))
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
        self.terminal_btn = QPushButton(tr("Terminal im Agent-PC öffnen"))
        self.terminal_btn.setToolTip(tr("Terminal dieses Rechners mit SSH-Anmeldung im Agent-PC "
                                        "(Benutzer und Passwort des Agent-PCs)"))
        self.fetch_logs_btn = QPushButton(tr("Einrichtungsprotokoll holen"))
        self.fetch_logs_btn.setToolTip(tr("Kopiert /var/log/bonys-agents.log und /var/log/cloud-init-output.log "
                                          "in den Ordner des Agent-PCs und zeigt sie an"))
        self.screen_btn = QPushButton(tr("Bildschirm anzeigen (SPICE)"))
        self.screen_btn.setToolTip(tr("Den echten Bildschirm des Agent-PCs per SPICE öffnen"))
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
            k = QLabel(tr(title).upper())
            k.setObjectName("Section")
            cl.addWidget(k)
            grid.addWidget(cell)
            return cl

        for key in ("CPU", "RAM", n_("Festplatte"), n_("Desktop"), n_("Benutzer"), n_("Speicherort"), n_("Programme")):
            cl = field(key)
            v = QLabel()
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setWordWrap(True)
            cl.addWidget(v)
            if key == "Speicherort":
                self.d_path = PathLabel()
                cl.addWidget(self.d_path)
            extra = {"RAM": self.resources_btn, "Festplatte": self.resize_btn, "Speicherort": self.move_btn,
                     "Programme": self.add_apps_btn, "Desktop": self.add_desktop_btn}.get(key)
            if extra:
                br = FlowLayout()
                br.addWidget(extra)
                if key == "Festplatte":
                    br.addWidget(self.independent_btn)
                if key == "Desktop":
                    br.addWidget(self.wallpaper_btn)
                cl.addLayout(br)
            cl.addStretch(1)
            self.d_fields[key] = v
        # Bildschirm: Auflösung folgt dem Fenster (Standard), Zoom oder feste Größe
        self.screen_mode = QComboBox()
        for mode, text in screen.MODES.items():
            self.screen_mode.addItem(tr(text), mode)
        self.screen_mode.setToolTip(tr("Wie der Bildschirm des Agent-PCs ins QEMU-Fenster kommt – wirkt ab dem "
                                       "nächsten Start.\nNur wenn die automatische Anpassung nicht klappt, "
                                       "„Bild skalieren“ oder „Feste Auflösung“ wählen."))
        self.screen_size = QComboBox()
        self.screen_size.addItems(screen.SIZES)
        self.screen_size.setToolTip(tr("Auflösung für „Bild skalieren“ und „Feste Auflösung“"))
        self.driver_btn = QPushButton(tr("Anzeige-Treiber aktualisieren"))
        self.driver_btn.setObjectName("Small")
        self.driver_btn.setToolTip(tr("Richtet im laufenden Agent-PC ein, dass die Auflösung dem Fenster folgt (für "
                                      "Agent-PCs von älteren Versionen; passiert auch bei „Agent-PC aktualisieren“)"))
        self.screen_note = QLabel()
        self.screen_note.setObjectName("Muted")
        self.screen_note.setWordWrap(True)
        cl = field(n_("Bildschirm"), span=2)
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
        self.tab_console = QPushButton(tr("Konsole"))
        self.tab_remote = QPushButton(tr("Fernzugriff"))
        self.tab_vpn = QPushButton("VPN")
        self.tab_vpn.setToolTip(tr("Bony's VPN im Agent-PC: Status, verbinden, trennen, Konfiguration importieren"))
        self.tab_mc = QPushButton("Mission Control")
        self.tab_mc.setToolTip(tr("Mission Control im Agent-PC: Status, öffnen, aktualisieren, deinstallieren"))
        for b in (self.tab_console, self.tab_remote, self.tab_vpn, self.tab_mc):
            b.setObjectName("Tab")
            b.setCheckable(True)
            tabs.addWidget(b)
        tabs.addStretch(1)
        self.logs_btn = QPushButton(tr("Protokolle öffnen"))
        self.logs_btn.setObjectName("Small")
        self.logs_btn.setToolTip(tr("Ordner des Agent-PCs mit console.log (auch ältere), qemu.log und "
                                    "geholten Einrichtungsprotokollen im Dateimanager öffnen"))
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
        self.mc_panel = McPanel()
        mc_scroll = QScrollArea()
        mc_scroll.setObjectName("Glass")
        mc_scroll.setWidgetResizable(True)
        mc_scroll.setFrameShape(QFrame.NoFrame)
        mc_scroll.setWidget(self.mc_panel)
        mc_scroll.setMinimumHeight(style.px(200))
        self.lower.addWidget(mc_scroll)
        lay.addWidget(self.lower, 1)
        self.tab_console.clicked.connect(lambda: self._show_tab(0))
        self.tab_remote.clicked.connect(lambda: self._show_tab(1))
        self.tab_vpn.clicked.connect(lambda: self._show_tab(2))
        self.tab_mc.clicked.connect(lambda: self._show_tab(3))
        self.mc_panel.install_requested.connect(lambda: self.add_apps(preselect=["mission-control"]))
        self.mc_panel.changed.connect(self.refresh_detail)
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
        self.wallpaper_btn.clicked.connect(lambda: self._update_wallpaper())
        self.move_btn.clicked.connect(self.move_vm)
        self.resize_btn.clicked.connect(self.resize_vm)
        self.resources_btn.clicked.connect(self.change_resources)
        self.add_apps_btn.clicked.connect(lambda: self.add_apps())
        self.add_desktop_btn.clicked.connect(self.add_desktop)
        self.template_btn.clicked.connect(self.save_template)
        if self.present_btn is not None:
            self.present_btn.clicked.connect(self.present_vm)
        self.help_btn.clicked.connect(self.request_help)
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
        self.tab_mc.setChecked(index == 3)
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
        self.statusBar().showMessage(tr("Anzeige-Treiber in „{name}“ wird eingerichtet …", name=m.name))
        w = TaskWorker(lambda: m.update_display_driver(password=password))

        def failed(msg: str) -> None:
            self.statusBar().clearMessage()
            if isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, tr("{meldung}\n\nPasswort "
                                                                 "von „{name}“:", meldung=msg, name=m.name),
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

    def _update_wallpaper(self, password: str | None = None, force: bool = False) -> None:
        from bonys_agents import wallpaper

        m = self.current()
        if not m:
            return
        self.wallpaper_btn.setEnabled(False)
        self.statusBar().showMessage(tr("Hintergrundbild in „{name}“ wird aktualisiert …", name=m.name))
        w = TaskWorker(lambda: wallpaper.update(m, force=force, password=password))

        def failed(msg: str) -> None:
            self.statusBar().clearMessage()
            if isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, tr("{meldung}\n\nPasswort "
                                                                 "von „{name}“:", meldung=msg, name=m.name),
                                              QLineEdit.Password)
                if ok and pw:
                    self._update_wallpaper(pw, force)
                return
            QMessageBox.warning(self, APP_NAME, msg)

        def done() -> None:
            self.refresh_detail()
            s = w.result
            if w.error is not None or s is None:
                return
            if s.done == "nachfragen":
                self.statusBar().clearMessage()
                ask = QMessageBox.question(
                    self, APP_NAME, tr("{stand}\n\nTrotzdem auf das neue Standard-Hintergrundbild umstellen? Dein Bild "
                                       "wird dann in den Einstellungen ersetzt (die Datei selbst bleibt).",
                                       stand=wallpaper.describe(s)),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ask == QMessageBox.Yes:
                    self._update_wallpaper(password, force=True)
                return
            self.statusBar().showMessage(f"{m.name}: {wallpaper.describe(s)}", 10000)

        w.failed.connect(failed)
        w.finished.connect(done)
        self._keep(w)

    def _open_terminal(self) -> None:
        m = self.current()
        if not m:
            return
        try:
            m.open_terminal()
            self.statusBar().showMessage(tr("Terminal geöffnet – Anmeldung als „{benutzer}“ mit dem Passwort des "
                                            "Agent-PCs.", benutzer=m.config.username), 8000)
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
                pw, ok = QInputDialog.getText(self, APP_NAME, tr("{meldung}\n\nPasswort "
                                                                 "von „{name}“:", meldung=msg, name=m.name),
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
        self.peek_btn.setText(tr("Kleiner anzeigen") if big else tr("Trotzdem anzeigen"))
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
        self.m_status = status = QLabel(tr("●  nicht verfügbar"))
        status.setStyleSheet(f"color: {style.MUTED};")
        self.m_path = PathLabel(prefix=tr("Lag zuletzt in: "))
        self.m_text = QLabel(tr(MISSING_TEXT))
        self.m_text.setWordWrap(True)
        row = QHBoxLayout()
        again = QPushButton(tr("Erneut suchen"))
        again.setObjectName("Primary")
        forget = QPushButton(tr("Aus Liste entfernen"))
        forget.setToolTip(tr("Löscht nichts – der Agent-PC bleibt auf dem Laufwerk und taucht beim Einstecken "
                             "wieder auf."))
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
        with_netz = [e for e in entries if isinstance(e, vm.VM) and e.config.netz_name]
        netz_on = bool(with_netz) and netz.bereit()
        if with_netz:
            self._check_netz(netz_on)
        self._check_kurse()
        self.list.setIconSize(QSize(30, 14) if with_netz else self._icon_size)
        for i, e in enumerate(entries):
            item = self.list.item(i)
            missing = isinstance(e, vm.MissingVM)
            dot = style.STATUS_COLORS.get(e.status(), style.MUTED)
            netz_tip = "" if missing else self._netz_tip(e, netz_on)
            if with_netz:
                state = None if missing or not e.config.netz_name else self._netz_state(e, netz_on)
                item.setIcon(_dot_netz(dot, NETZ_COLORS[state] if state else None))
            else:
                item.setIcon(_dot(dot))
            remote_on = not missing and e.remote_active()
            desk = "" if missing else f"  ·  {desktops.name(e.config.desktop)}"
            item.setText(e.name + desk + (REMOTE_MARK if remote_on else ""))
            item.setForeground(QColor(style.MUTED if missing else style.TEXT))
            tip = (f"{tr(e.status()).capitalize()} – {e.path}" if missing else str(e.path))
            item.setToolTip(tip + ("\n" + tr("Fernzugriff ist an") if remote_on else "") + netz_tip)
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
            self._check_vpn_apps([e for e in entries if isinstance(e, vm.VM)])
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
        self.statusBar().showMessage(tr("„{name}“ ist eingerichtet und startet jetzt mit Desktop.", name=m.name), 8000)

    def refresh_detail(self) -> None:
        entry = self.current_entry()
        if entry is None:
            self.stack.setCurrentIndex(0)
            return
        if isinstance(entry, vm.MissingVM):
            self.stack.setCurrentIndex(2)
            self.m_name.setText(entry.name)
            self.m_path.set_path(entry.path)
            broken = entry.broken()
            self.m_status.setText(f"●  {tr(entry.status())}")
            self.m_status.setStyleSheet(f"color: {style.DANGER if broken else style.MUTED};")
            self.m_text.setText(tr(BROKEN_TEXT if broken else MISSING_TEXT))
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
        elif c.setup_failed and not notice and not (hidden_setup or aborted or about_to_start or stopping):
            notice = tr(HINT_SETUP_FAILED, steps=", ".join(f"„{cloudinit.schritt_titel(t)}“" for t in c.setup_failed))
        self.hint.setVisible(hidden_setup or aborted or about_to_start or stopping or bool(notice))
        self.hint.setProperty("tone", "danger" if aborted or notice and not tpl_lock else "")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        if aborted and not notice:
            cause = m.abort_reason()
            abort_text = tr("{hinweis}\n\nUrsache: {ursache}", hinweis=tr(HINT_ABORTED), ursache=cause.reason) + (
                f"\n{cause.detail}" if cause.detail else "")
        else:
            abort_text = tr(HINT_ABORTED)
        self.hint_text.setText(tr(HINT_STOPPING, sekunden=vm.STOP_TIMEOUT) if stopping else tr(notice) if notice
                               else abort_text if aborted else tr(HINT_READY) if about_to_start else tr(HINT_SETUP))
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
        shown = tr(status)
        if stopping:
            shown = tr("{status} … noch {sekunden} s", status=shown, sekunden=max(0, round(vm.STOP_TIMEOUT - waited)))
            if c.name in self._powering_off:
                shown = tr("wird ausgeschaltet …")
        self.d_status.setText(f"●  {shown}")
        self.d_status.setStyleSheet(f"color: {style.STATUS_COLORS.get(status, style.MUTED)};")
        self.d_fields["CPU"].setText(tr("{n} Kerne", n=c.cpus))
        ram_text = f"{c.ram_mb / 1024:.1f} GB"
        recommended = min(m.recommended_ram_mb(), self.info.max_vm_ram_mb)
        if c.ram_mb < recommended:
            ram_text += "\n" + tr("⚠ empfohlen: {ram}", ram=desktops.format_ram(recommended))
        self.d_fields["RAM"].setText(ram_text)
        linked = m.is_linked()
        disk_text = tr("{groesse} (dynamisch)", groesse=vm.format_gb(c.disk_gb))
        if linked:
            disk_text += "\n" + tr("verknüpft mit Vorlage "
                                   "„{vorlage}“", vorlage=c.template or m.backing_file().parent.name)
        elif c.template:
            disk_text += "\n" + tr("aus Vorlage „{vorlage}“", vorlage=c.template)
        self.d_fields["Festplatte"].setText(disk_text)
        self.d_fields["Benutzer"].setText(c.username)
        others = [desktops.name(d) for d in c.extra_desktops]
        system = f"{distros.name(c.distro)} · " if c.distro != distros.DEFAULT else ""   # Debian: wie bisher
        self.d_fields["Desktop"].setText(system + desktops.name(c.desktop)
                                         + ("\n" + tr("auch: "
                                                      "{desktops}", desktops=", ".join(others)) if others else ""))
        todo = [a for a in c.reinstall if a in apps.APPS and a not in c.apps]
        self.d_fields["Programme"].setText((", ".join(apps.labels(c.apps, c.app_info)) or "–") + (
            "\n" + tr("Noch zu installieren (offizielle Quelle, Lizenz): {programme}",
                      programme=", ".join(apps.names(todo))) if todo else ""))
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
        self.wallpaper_btn.setEnabled(status == "läuft" and not busy and not c.first_boot_pending)
        self.screen_note.setText(tr("gilt ab dem nächsten Start") if m.screen_pending() else
                                 tr("SPICE-Fenster: Remmina/remote-viewer passt die Auflösung an")
                                 if c.display == "spice" else "")
        self.screen_note.setVisible(bool(self.screen_note.text()))
        remote_on = m.remote_active() or (not running and c.remote_permanent)
        self.remote_btn.setText(tr("Fernzugriff ausschalten") if remote_on else tr("Fernzugriff einschalten"))
        self.remote_btn.setVisible("xrdp" in c.apps or remote_on)
        self.remote_btn.setEnabled(not busy and not stopping and (status in ("läuft", "gestoppt") or remote_on))
        self.move_btn.setEnabled(not running and not busy and not blocked)
        self.resize_btn.setEnabled(not running and not busy and not blocked and c.disk_gb < vm.MAX_DISK_GB)
        self.resources_btn.setEnabled(not busy and not blocked and not stopping and not about_to_start
                                      and m.progress().ready and not c.first_boot_pending)
        self.independent_btn.setVisible(linked)
        self.independent_btn.setEnabled(not running and not busy and not blocked)
        finished = m.progress().ready and not c.first_boot_pending
        self.template_btn.setEnabled(finished and not busy and not blocked and not stopping)
        missing = m.missing_apps()
        self.add_apps_btn.setVisible(bool(missing))
        self.add_apps_btn.setEnabled(status == "läuft" and not busy)
        self.add_desktop_btn.setEnabled(status == "läuft" and not busy)
        # Grundsysteme mit nur einem geprüften Desktop (Kali: Xfce) – nichts zum Hinzufügen
        self.add_desktop_btn.setVisible(len(distros.get(c.distro).desktops) != 1)
        self.delete_btn.setEnabled(not busy and not tpl_lock)
        self.upgrade_btn.setEnabled(status == "läuft" and not busy)
        if self.present_btn is not None:
            self.present_btn.setEnabled(status == "läuft" and not c.first_boot_pending and not stopping)
        self.help_btn.setEnabled(status == "läuft" and not c.first_boot_pending and not stopping)

        p = m.progress()
        show = (running and not p.ready) or (c.first_boot_pending and (running or about_to_start))
        self.d_prog.setVisible(show)
        self.d_prog_label.setVisible(show)
        if show:
            self.d_prog.set_percent(p.percent)
            if p.ready:
                what = tr("Einrichtung fertig – startet gleich mit Desktop")
            elif p.resumed:
                what = tr("Schritt {schritt} von {gesamt} – {titel} (wird nach dem Neustart fortgesetzt …)",
                          schritt=p.step, gesamt=p.total, titel=cloudinit.schritt_titel(p.title))
            elif p.total:
                what = tr("Schritt {schritt} von {gesamt} – {titel}", schritt=p.step, gesamt=p.total,
                          titel=cloudinit.schritt_titel(p.title))
                if p.resume_step:
                    what += "  ·  " + tr("fortgesetzt ab Schritt {schritt}", schritt=p.resume_step)
            elif c.template and not c.provisioned:
                what = tr("Erster Start aus der Vorlage – Rechnername, Passwort und Schlüssel werden gesetzt …")
            else:
                what = tr("Agent-PC bootet und bereitet die Einrichtung vor …")
            eta = pct.format_eta(m.eta_seconds(p.percent)) if not p.ready else ""
            self.d_prog_label.setText(tr("Einrichtung: {was}", was=what) + (f"  ·  {eta}" if eta else ""))

        if self.lower.currentIndex() == 1:
            self.remote_panel.update_for(m, status)
        elif self.lower.currentIndex() == 2:
            self.vpn_panel.update_for(m, status)
        elif self.lower.currentIndex() == 3:
            self.mc_panel.update_for(m, status)
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
            text = tr("„{name}“ hat nicht innerhalb von {sekunden} Sekunden reagiert und wurde hart ausgeschaltet.",
                      name=m.name, sekunden=vm.STOP_TIMEOUT)
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
        self.statusBar().showMessage(tr("Fernzugriff für „{name}“ wird eingeschaltet …", name=m.name) if on else
                                     tr("Fernzugriff für „{name}“ wird ausgeschaltet …", name=m.name))
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
            tr("Fernzugriff nach Neustart ausgeschaltet: {namen}", namen=", ".join(w.result)), 10000))
        self._remote_check = w
        w.start()

    def _check_vpn_apps(self, machines: list[vm.VM]) -> None:
        """Im Hintergrund, einmal je Start: Alte, eingebaute Fassung von Bony's VPN (bis 0.14) bzw. zu altes
        Paket im Agent-PC? Dann auf das Paket bonys-vpn umstellen. Nur über den Gast-Agent (ohne Passwort);
        /etc/wireguard und der Kill-Switch bleiben unverändert."""
        if self._vpn_check and self._vpn_check.isRunning():
            return
        todo = []
        for m in machines:
            if vpnlink.APP_ID not in m.config.apps or m.config.first_boot_pending or not m.is_running():
                continue
            rt = m.runtime()
            key = (m.name, int(rt.get("pid") or rt.get("qmp_port") or 0))  # einmal je Start
            if key not in self._vpn_checked and m.progress().ready:
                todo.append((key, m))
        if not todo:
            return

        def run() -> list[tuple[str, str]]:
            out = []
            for key, m in todo:
                if not m.guest_agent_ready():
                    continue  # Gast bootet noch – beim nächsten Durchlauf wieder
                self._vpn_checked.add(key)
                if not vpnlink.needs_update(m):
                    continue
                try:
                    vpnlink.update_app(m)
                    out.append((m.name, ""))
                except Exception as e:  # noqa: BLE001 – Meldung in der Statusleiste, Knopf im Reiter „VPN“
                    out.append((m.name, str(e)))
            return out

        w = TaskWorker(run)

        def done() -> None:
            for name, err in w.result or []:
                self.statusBar().showMessage(
                    tr("Bony's VPN in „{name}“ nicht umgestellt: {fehler}", name=name, fehler=err) if err else
                    tr("Bony's VPN in „{name}“ auf das Paket bonys-vpn umgestellt (Tunnel unverändert).", name=name),
                    20000)
            if w.result:
                self.refresh_detail()

        w.finished.connect(done)
        self._vpn_check = w
        w.start()

    # ---------- Bony-Netz ----------
    def _netz_state(self, m: vm.VM, netz_on: bool) -> str:
        if not netz_on or self._netz_geraete is None:
            return netz.NICHT_VERBUNDEN
        return netz.netz_zustand(m.config.netz_name, self._netz_geraete)

    def _netz_tip(self, m: vm.VM, netz_on: bool) -> str:
        name = m.config.netz_name
        if not name:
            return ""
        if not netz_on:
            return "\n" + tr("Bony-Netz ({name}): ausgeschaltet", name=name)
        if self._netz_geraete is None:
            return "\n" + tr("Bony-Netz ({name}): {zustand}", name=name,
                             zustand=self._netz_fehler or tr("wird abgefragt …"))
        state = netz.netz_zustand(name, self._netz_geraete)
        ip = (self._netz_geraete.get(name) or {}).get("ip")
        return "\n" + tr("Bony-Netz ({name}): {zustand}", name=name, zustand=tr(state)) + (
            f" – {ip}" if ip and state != netz.NICHT_VERBUNDEN else "")

    def _check_netz(self, netz_on: bool) -> None:
        """Geräteliste im Hintergrund – höchstens alle 30 s und nur, wenn das Fenster zu sehen ist."""
        if not netz_on:
            self._netz_geraete, self._netz_fehler = None, ""
            return
        if (not self.isVisible() or self.isMinimized()
                or (self._netz_check and self._netz_check.isRunning())
                or time.monotonic() - self._netz_zuletzt < netz.ABFRAGE_SEKUNDEN):
            return
        self._netz_zuletzt = time.monotonic()
        w = TaskWorker(netz.geraete)

        def done() -> None:
            if w.error is None:
                self._netz_geraete, self._netz_fehler = w.result, ""
            else:
                self._netz_geraete, self._netz_fehler = None, netz.fehlertext(w.error)

        w.finished.connect(done)
        self._netz_check = w
        w.start()

    def show_moderation(self) -> None:
        from .moderation_dialog import ModerationDialog, lokale_ablage
        ModerationDialog(lokale_ablage(), self).exec()

    def _check_kurse(self) -> None:
        """Eigene Teilnahmen im Hintergrund: Meldung, wenn ein Kurs beginnt. Höchstens jede Minute, nur bei sichtbarem
        Fenster und eingeschaltetem Bony-Netz – und nur, solange es Teilnahmen gibt (einmal beim Start nachsehen)."""
        if (self._kurse_aktiv is False or not self.isVisible() or self.isMinimized()
                or (self._kurse_check and self._kurse_check.isRunning())
                or time.monotonic() - self._kurse_zuletzt < kurse.TEILNAHMEN_SEKUNDEN or not netz.bereit()):
            return
        self._kurse_zuletzt = time.monotonic()
        w = TaskWorker(kurse.teilnahmen)

        def done() -> None:
            if w.error is not None:
                return   # ohne Internet: still – die Kurse zeigen den Fehler selbst
            self._kurse_aktiv = bool(w.result)
            neu = self._kurse_beobachter.neu_begonnen(w.result)
            if neu:
                self.statusBar().showMessage(kurse.begonnen_text(neu), 120000)
                QApplication.alert(self, 0)

        w.finished.connect(done)
        self._kurse_check = w
        w.start()

    def _list_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        m = self.entries.get(item.data(Qt.UserRole)) if item else None
        if not isinstance(m, vm.VM) or not netz.bereit():
            return
        if m.config.netz_name and self._netz_geraete is not None \
                and netz.netz_zustand(m.config.netz_name, self._netz_geraete) != netz.NICHT_VERBUNDEN:
            return   # schon im Netz
        ready = m.is_running() and m.progress().ready and not m.config.first_boot_pending
        menu = QMenu(self)
        act = menu.addAction(tr("Mit dem Bony-Netz verbinden") if ready else
                             tr("Mit dem Bony-Netz verbinden (Agent-PC muss laufen und eingerichtet sein)"))
        act.setEnabled(ready)
        act.triggered.connect(lambda: self._netz_verbinden(m))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _netz_verbinden(self, m: vm.VM, password: str | None = None) -> None:
        self.statusBar().showMessage(tr("„{name}“ wird mit dem Bony-Netz verbunden (Tailscale wird installiert) …",
                                        name=m.name))
        w = TaskWorker(lambda: netz.nachtraeglich_verbinden(m, password))

        def failed(msg: str) -> None:
            self.statusBar().clearMessage()
            if isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, tr("{meldung}\n\nPasswort "
                                                                 "von „{name}“:", meldung=msg, name=m.name),
                                              QLineEdit.Password)
                if ok and pw:
                    self._netz_verbinden(m, pw)
                return
            QMessageBox.warning(self, APP_NAME, tr("„{name}“ ließ sich nicht mit dem Bony-Netz verbinden:\n\n{fehler}",
                                                   name=m.name, fehler=netz.fehlertext(w.error) if w.error else msg))

        def done() -> None:
            if w.error is None:
                self.statusBar().showMessage(tr("„{name}“ ist mit dem Bony-Netz verbunden.", name=m.name), 10000)
            self.refresh()

        w.failed.connect(failed)
        w.finished.connect(done)
        self._keep(w)

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
            if dlg.hints:
                QMessageBox.warning(self, APP_NAME, "\n\n".join(dlg.hints))

    def delete_vm(self) -> None:
        m = self.current()
        if not m:
            return
        if confirm_delete(self, APP_NAME, tr("„{name}“ wirklich löschen?", name=m.name),
                          tr("Alle Daten in diesem Agent-PC gehen verloren – das lässt sich nicht rückgängig machen.")):
            def remove() -> str:
                # Erst aus dem Bony-Netz (geht es nicht, trotzdem lokal löschen und Hinweis zeigen)
                hint = netz.loeschen_hinweis(m) if m.template_lock_pid() is None else ""
                m.delete()
                return hint

            w = TaskWorker(remove)
            w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
            w.finished.connect(lambda: (w.result and QMessageBox.warning(self, APP_NAME, w.result), self.refresh()))
            self._keep(w)
            self.refresh_detail()

    def move_vm(self) -> None:
        m = self.current()
        if not m:
            return
        if MoveDialog(m, self).exec():
            self.refresh()
            self.statusBar().showMessage(tr("„{name}“ wurde verschoben.", name=m.name), 5000)

    def add_apps(self, preselect: list[str] | None = None) -> None:
        m = self.current()
        if not m or not m.missing_apps():
            return
        if preselect is None:  # aus einer weitergegebenen Vorlage: nicht mitgelieferte Apps vorschlagen
            preselect = [a for a in m.config.reinstall if a in apps.APPS and a not in m.config.apps]
        InstallAppsDialog(m, self, preselect=preselect).exec()
        self.refresh()

    def save_template(self) -> None:
        m = self.current()
        if not m:
            return
        dlg = SaveTemplateDialog(m, self)
        if dlg.exec() and dlg.result_template:
            t = dlg.result_template
            QMessageBox.information(self, APP_NAME, tr("Vorlage „{name}“ ist fertig "
                                                       "({groesse}).\n\nNeue Agent-PCs daraus: „+ Neuer "
                                                       "Agent-PC“ → Grundlage.", name=t.name,
                                                       groesse=f"{t.size / storage.GB:.1f} GB"))
        self.refresh()

    def show_templates(self) -> None:
        TemplatesDialog(self).exec()
        self.refresh()

    def present_vm(self) -> None:
        """Nicht modal – der Kursleiter arbeitet nebenher weiter (Pause, Hilfe-Anfragen). Nur Kursleiter-Version."""
        from bonys_agents.trainer.gui.present_dialog import PresentDialog

        m = self.current()
        if not m:
            return
        d = self._present_dialog
        if d is not None and d.isVisible():
            d.raise_()
            d.activateWindow()
            return
        d = PresentDialog(m, self, restart=lambda: self._run(lambda x: (x.stop(), x.start())),
                          help_desk=self.show_helpdesk)
        d.setAttribute(Qt.WA_DeleteOnClose)
        d.finished.connect(lambda *_: setattr(self, "_present_dialog", None))
        self._present_dialog = d
        d.show()

    def show_helpdesk(self) -> None:
        from bonys_agents.trainer.gui.helpdesk_dialog import HelpDeskDialog

        d = self._helpdesk_dialog
        if d is None:
            d = self._helpdesk_dialog = HelpDeskDialog(self)
        d.show()
        d.raise_()
        d.activateWindow()

    def _help_request_arrived(self, text: str) -> None:
        self.statusBar().showMessage(text, 30000)
        QApplication.alert(self, 0)
        QApplication.beep()
        self.show_helpdesk()

    def request_help(self) -> None:
        from .course_ui import HelpRequestDialog

        m = self.current()
        if not m:
            return
        HelpRequestDialog(m, self, restart=lambda: self._run(lambda x: (x.stop(), x.start()))).exec()

    def join_training(self) -> None:
        """Schulung im selben Netz (LAN/VPN) – ohne Bony-Netz, wie bisher."""
        from .share_dialogs import JoinDialog

        d = JoinDialog(self)
        d.exec()
        self.refresh()
        paket, info = d.result_paket, d.info
        if paket is not None and info is not None and QMessageBox.question(
                self, APP_NAME, tr("Zur Schulung gehört das Kurspaket „{name}“. Jetzt neben dem Agent-PC "
                                   "durcharbeiten?\n\nDie Kursleitung sieht dabei nur, in welcher Lektion du bist "
                                   "und ob die Prüfaufgabe geschafft ist – solange ihre Freigabe läuft.",
                                   name=paket.name)) == QMessageBox.Yes:
            from bonys_agents import share

            self.kurspaket_durcharbeiten(paket, melden=lambda i, g: share.fortschritt_melden(info, i, g))

    def show_courses(self) -> None:
        KurseDialog(self, join_local=self.join_training, durcharbeiten=self.kurspaket_durcharbeiten,
                    im_kurs=self.kurspaket_im_kurs).exec()
        self._kurse_aktiv = None   # vielleicht beigetreten oder verlassen – bei der nächsten Abfrage nachsehen
        self.refresh()

    def kurspaket_durcharbeiten(self, paket, melden=None) -> None:
        """Selbstlern-Modus: Agent-PC für das Kurspaket wählen/erstellen, dann die Anleitung daneben öffnen.
        ``melden``: in einer Schulung den Fortschritt an den Kursleiter melden."""
        from .kurspaket_anleitung import oeffnen
        from .kurspaket_bibliothek import agent_pc_einrichten, skripte_erlauben

        if not skripte_erlauben(self, paket):
            return
        if not deps.check(self.info).can_run and kurspaket.agent_pc(paket) is None:
            self.show_doctor()
            if not deps.check(self.info).can_run:
                return
        name = agent_pc_einrichten(self, paket)
        if not name:
            return
        self.refresh()
        self._waehlen(name)
        oeffnen(paket, self.kurspaket_agent_pc_zeigen, self, melden=melden)

    def kurspaket_im_kurs(self, paket, kurs_id: str, agent_pc: str) -> None:
        """Kurspaket eines Bony-Netz-Kurses: Anleitung neben dem Agent-PC des Kurses, Fortschritt an den Kursleiter."""
        from bonys_agents import kurse

        from .kurspaket_anleitung import oeffnen
        from .kurspaket_bibliothek import skripte_erlauben

        if not skripte_erlauben(self, paket):
            return
        if agent_pc:
            kurspaket.agent_pc_merken(paket, agent_pc)
            self.refresh()
            self._waehlen(agent_pc)
        elif kurspaket.agent_pc(paket) is None:
            QMessageBox.information(self, APP_NAME, tr("Der Agent-PC, mit dem du am Kurs teilnimmst, liegt nicht "
                                                       "auf diesem Rechner. Die Anleitung öffnet sich trotzdem – "
                                                       "Prüfaufgaben und „Zurücksetzen“ gehen nur mit dem Agent-PC."))
        oeffnen(paket, self.kurspaket_agent_pc_zeigen, self,
                melden=lambda index, geschafft: kurse.fortschritt_melden(kurs_id, index, geschafft))

    def _waehlen(self, name: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == name:
                self.list.setCurrentRow(i)
                return

    def kurspaket_agent_pc_zeigen(self, name: str) -> None:
        """Aus der Anleitung: Agent-PC wählen, starten bzw. sein SPICE-Fenster öffnen, Hauptfenster nach vorn."""
        self.refresh()
        self._waehlen(name)
        m = self.current()
        if m is None or m.name != name:
            QMessageBox.information(self, APP_NAME, tr("Den Agent-PC „{name}“ gibt es nicht (mehr).", name=name))
            return
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if not m.is_running():
            self.start_vm()
        elif m.config.display == "spice" and m.progress().ready:
            self._show_screen()

    def make_independent(self) -> None:
        m = self.current()
        if not m or not m.is_linked():
            return
        if QMessageBox.question(self, APP_NAME, tr("„{name}“ unabhängig machen?\n\nDie Daten der Vorlage werden in "
                                                   "seine Festplatte übernommen – das braucht mehr Platz und kann ein "
                                                   "paar Minuten dauern. Danach braucht er die Vorlage nicht mehr.",
                                                   name=m.name)) != QMessageBox.Yes:
            return
        w = FnWorker(lambda progress: m.make_independent(
            lambda f: progress("detach", f, tr("„{name}“ wird unabhängig … {prozent} %", name=m.name,
                                               prozent=f"{f * 100:.0f}"))))
        w.progress.connect(lambda _p, _f, msg: self.statusBar().showMessage(msg))
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.done.connect(lambda _r: self.statusBar().showMessage(tr("„{name}“ ist jetzt unabhängig.", name=m.name), 8000))
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
                tr("Festplatte von „{name}“ ist jetzt {groesse} groß.", name=m.name,
                   groesse=vm.format_gb(m.config.disk_gb)), 6000)

    def change_resources(self) -> None:
        """CPU/RAM ändern – läuft der Agent-PC, wird er heruntergefahren, geändert und wieder gestartet."""
        m = self.current()
        if not m:
            return
        running = m.is_running()
        dlg = ResourcesDialog(m, self.info, running, self)
        if not dlg.exec():
            return
        cpus, ram_mb = dlg.cpus, dlg.ram_mb
        if not running:
            try:
                m.set_resources(cpus, ram_mb)
            except Exception as e:  # noqa: BLE001 – Fehler gehen an die Oberfläche
                QMessageBox.critical(self, APP_NAME, str(e))
                return
            self.refresh()
            self.statusBar().showMessage(tr("„{name}“: {cpus} Kerne, {ram} RAM – gilt ab dem nächsten Start.",
                                            name=m.name, cpus=cpus, ram=desktops.format_ram(ram_mb)), 8000)
            return
        self._clear_notice()
        m.mark_stopping()

        def restart() -> None:
            m.stop()
            m.set_resources(cpus, ram_mb)
            m.start()

        w = TaskWorker(restart)
        w.failed.connect(lambda msg: QMessageBox.critical(self, APP_NAME, msg))
        w.finished.connect(lambda: (self.refresh(), w.error is None and self.statusBar().showMessage(
            tr("„{name}“ läuft jetzt mit {cpus} Kernen und {ram} RAM.", name=m.name, cpus=cpus,
               ram=desktops.format_ram(ram_mb)), 8000)))
        self._keep(w)
        self.refresh_detail()

    def import_vm(self) -> None:
        start = str(storage.preferred_library().parent)
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Ordner mit Agent-PC(s) wählen (z. B. BonysAgents auf der SSD)"), start
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
        self.statusBar().showMessage(tr("Hinzugefügt: {namen}", namen=names), 6000)

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
        self.statusBar().showMessage(tr("Kopiert: {befehl}", befehl=cmd), 4000)

    def show_doctor(self) -> None:
        SetupDialog(self.info, self).exec()
        self.info = host.detect()


class LogDialog(QDialog):
    """Geholte Einrichtungsprotokolle anzeigen (je Datei ein Reiter)."""

    def __init__(self, machine: vm.VM, files: list[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Einrichtungsprotokoll – {name}", name=machine.name))
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
        where = PathLabel(machine.path, prefix=tr("Gespeichert in "))
        where.setObjectName("Muted")
        lay.addWidget(where)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        folder = buttons.addButton(tr("Ordner öffnen"), QDialogButtonBox.ActionRole)
        folder.clicked.connect(lambda: open_url(str(machine.path)))
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
