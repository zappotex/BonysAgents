# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN für den eigenen Rechner: Bereich „VPN“ im Hauptfenster und eigenes Fenster
(Desktop-Eintrag „Bony's VPN“, ``BonysAgents --vpn``).

Gleiche Funktionen wie die GTK-Oberfläche im Agent-PC, im Stil von Bony's Agents: Tunnelliste mit
Status, Ein-Klick verbinden/trennen, Live-Werte, öffentliche IP, Import (Dateiauswahl, Drag&Drop,
mehrere Dateien, ZIP), Umbenennen, Löschen, Export, Editor mit verborgenen Schlüsseln,
Autostart, Kill-Switch mit Ausnahmen, Meldung bei Abbruch. Alles, was root braucht, geht über
``bonys-vpn-helper`` (pkexec, Administrator-Passwort, einige Minuten gemerkt).

Außerdem: „Extras → WireGuard für diesen Rechner …“ unter Windows (winget) und macOS (App Store).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, REPO_URL, hostvpn, storage
from bonys_agents.vpn import cli as vpncli
from bonys_agents.vpn import conf as wgconf
from bonys_agents.vpn import model

from . import style
from .widgets import FlowLayout, open_url
from .workers import TaskWorker

model.set_language("de")  # Bony's Agents ist deutsch

LIVE_MS = 2_000      # Live-Werte aus /sys (ohne root)
STATUS_MS = 10_000   # Helfer-Status (Handshake) bei sichtbarem Bereich – nur ohne Passwortabfrage
ICON_DIR = Path(model.__file__).resolve().parent / "data" / "icons"
STATE_COLORS = {"connected": style.OK, "warning": style.WARN, "blocked": style.DANGER,
                "disconnected": style.MUTED}
INTRO_SETTING = "host_vpn_intro_seen"
HELP_URL = f"{REPO_URL}#vpn-bonys-vpn"


def state_icon(state: str) -> QIcon:
    return QIcon(str(ICON_DIR / f"bonys-vpn-{state}.svg"))


def _small(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Small")
    if tip:
        b.setToolTip(tip)
    return b


def confirm_whole_computer(parent: QWidget) -> bool:
    """Hinweis „gilt für den ganzen Rechner“ – bis „Nicht mehr anzeigen“ angehakt wurde."""
    s = storage.load_settings()
    if s.get(INTRO_SETTING):
        return True
    box = QMessageBox(QMessageBox.Information, "Bony's VPN auf diesem Rechner", hostvpn.INTRO,
                      QMessageBox.Ok | QMessageBox.Cancel, parent)
    box.button(QMessageBox.Ok).setText("Verstanden")
    again = QCheckBox("Nicht mehr anzeigen")
    box.setCheckBox(again)
    if box.exec() != QMessageBox.Ok:
        return False
    if again.isChecked():
        s[INTRO_SETTING] = True
        storage.save_settings(s)
    return True


class EditorDialog(QDialog):
    """Konfiguration ansehen und bearbeiten. Schlüssel stehen als „(verborgen)“ da – unverändert
    gelassen setzt der Helfer die gespeicherten wieder ein."""

    def __init__(self, name: str, shown: dict, parent=None):
        super().__init__(parent)
        self.name = name
        self.managed = bool(shown.get("managed"))
        self.setWindowTitle(f"„{name}“ bearbeiten" if self.managed else f"„{name}“ ansehen")
        self.resize(style.px(620), style.px(480))
        lay = QVBoxLayout(self)
        hint = QLabel(model.tr("Private Schlüssel sind verborgen. Unverändert gelassenes „(verborgen)“ behält den "
                               "gespeicherten Schlüssel.") if self.managed else
                      model.tr("Nur ansehen – der Tunnel wurde nicht mit Bony's VPN angelegt."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.edit = QPlainTextEdit(shown.get("conf", ""))
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.edit.setFont(mono)
        self.edit.setReadOnly(not self.managed)
        lay.addWidget(self.edit, 1)
        self.check = QLabel()
        self.check.setWordWrap(True)
        lay.addWidget(self.check)
        row = QHBoxLayout()
        self.reveal_btn = _small("Schlüssel anzeigen", "Holt die gespeicherten Schlüssel (Administrator-Passwort)")
        self.reveal_btn.setVisible(self.managed)
        row.addWidget(self.reveal_btn)
        row.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel if self.managed
                                        else QDialogButtonBox.Close)
        row.addWidget(self.buttons)
        lay.addLayout(row)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.reveal_btn.clicked.connect(self._reveal)
        self.edit.textChanged.connect(self._validate)
        self.hooks: list[str] = []
        self._validate()

    def text(self) -> str:
        return self.edit.toPlainText()

    def _validate(self) -> None:
        save = self.buttons.button(QDialogButtonBox.Save)
        try:
            parsed = model.check_text(self.text())
        except wgconf.ConfError as e:
            self.hooks = []
            self.check.setText(f"⚠ {e}")
            self.check.setStyleSheet(f"color: {style.DANGER};")
            if save:
                save.setEnabled(False)
            return
        self.hooks = list(parsed.hooks)
        self.check.setText(model.tr("Die Konfiguration ist in Ordnung.")
                           + (" " + model.tr("Achtung: führt beim Verbinden Befehle als root aus ({hooks}).",
                                             hooks=", ".join(self.hooks)) if self.hooks else ""))
        self.check.setStyleSheet(f"color: {style.WARN if self.hooks else style.OK};")
        if save:
            save.setEnabled(True)

    def _reveal(self) -> None:
        try:
            full = hostvpn.export(self.name)
        except hostvpn.HostVpnError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.edit.setPlainText(model.reveal(self.text(), full))
        self.reveal_btn.setEnabled(False)


def confirm_hooks(parent: QWidget, name: str, hooks: list[str]) -> bool:
    box = QMessageBox(QMessageBox.Warning, model.tr("Befehle in der Konfiguration"),
                      model.tr("„{name}“ enthält {hooks}. Diese Zeilen sind Shell-Befehle, die beim Verbinden und "
                               "Trennen als root laufen. Eine fremde Datei kann damit den ganzen Rechner "
                               "übernehmen.\n\nNur übernehmen, wenn du der Datei vertraust.",
                               name=name, hooks=", ".join(hooks)),
                      QMessageBox.Cancel, parent)
    ok = box.addButton(model.tr("Trotzdem übernehmen"), QMessageBox.DestructiveRole)
    box.setDefaultButton(QMessageBox.Cancel)
    box.exec()
    return box.clickedButton() is ok


class HostVpnPanel(QWidget):
    """Bony's VPN für diesen Rechner – im Hauptfenster und im eigenen Fenster."""

    state_changed = Signal(str)        # connected / warning / blocked / disconnected
    notify = Signal(str, str)          # Titel, Text – Abbruch und Wiederkehr

    def __init__(self, parent=None, show_title: bool = True):
        super().__init__(parent)
        self.status: model.Status | None = None
        self.error = ""
        self.ip_text = ""
        self.worker: TaskWorker | None = None
        self.watch = model.Watch()
        self.activity = model.Activity()
        self._last_state = ""
        self._selected = ""
        self.nm_active: set[str] = set()   # WireGuard-Verbindungen des NetworkManager
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        if show_title:
            title = QLabel("Bony's VPN – dieser Rechner")
            title.setObjectName("Section")
            lay.addWidget(title)
        self.headline = QLabel()
        self.headline.setObjectName("Title")
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.note = QLabel()
        self.note.setObjectName("Muted")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        # Helfer oder Werkzeuge fehlen
        self.setup = QFrame()
        self.setup.setObjectName("Hint")
        sl = QHBoxLayout(self.setup)
        sl.setContentsMargins(14, 10, 14, 10)
        self.setup_text = QLabel()
        self.setup_text.setWordWrap(True)
        self.setup_btn = QPushButton("WireGuard-Werkzeuge installieren …")
        self.setup_btn.setObjectName("Primary")
        sl.addWidget(self.setup_text, 1)
        sl.addWidget(self.setup_btn)
        lay.addWidget(self.setup)

        # Tunnel | Details
        self.body = QWidget()
        bl = QHBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(14)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(style.px(170))
        self.list.setMaximumWidth(style.px(260))
        left.addWidget(self.list, 1)
        drop = QLabel("Konfigurationen (.conf, .zip) lassen sich hierher ziehen.")
        drop.setObjectName("Muted")
        drop.setWordWrap(True)
        left.addWidget(drop)
        bl.addLayout(left)
        right = QVBoxLayout()
        right.setSpacing(8)
        self.tunnel_title = QLabel()
        self.tunnel_title.setObjectName("Section")
        right.addWidget(self.tunnel_title)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(14)
        right.addLayout(self.form)
        self.tunnel_note = QLabel()
        self.tunnel_note.setWordWrap(True)
        right.addWidget(self.tunnel_note)
        main_buttons = FlowLayout()
        self.toggle_btn = QPushButton("Verbinden")
        self.toggle_btn.setObjectName("Primary")
        self.ip_btn = _small("Öffentliche IP prüfen", f"Fragt {model.IP_SERVICE_NAME} nach der Adresse, mit der "
                             "dieser Rechner im Internet auftritt")
        main_buttons.addWidget(self.toggle_btn)
        main_buttons.addWidget(self.ip_btn)
        right.addLayout(main_buttons)
        self.ip_label = QLabel()
        self.ip_label.setWordWrap(True)
        right.addWidget(self.ip_label)
        more = FlowLayout()
        self.import_btn = _small("Importieren …", "WireGuard-Konfigurationen (.conf oder .zip, auch mehrere)")
        self.edit_btn = _small("Bearbeiten …")
        self.rename_btn = _small("Umbenennen …")
        self.export_btn = _small("Exportieren …", "Mit privatem Schlüssel, nur für dich lesbar")
        self.delete_btn = _small("Löschen …")
        self.delete_btn.setStyleSheet(f"color: {style.DANGER};")  # bleibt klein wie die anderen
        self.refresh_btn = _small("Aktualisieren")
        self.help_btn = _small("Hilfe", "Anleitung zu Bony's VPN (README, Abschnitt „VPN“)")
        for b in (self.import_btn, self.edit_btn, self.rename_btn, self.export_btn, self.delete_btn,
                  self.refresh_btn, self.help_btn):
            more.addWidget(b)
        right.addLayout(more)
        self.autostart = QCheckBox("Diesen Tunnel beim Hochfahren automatisch verbinden")
        self.autostart.setToolTip(model.tr("Verbindet diesen Tunnel beim Hochfahren des Rechners "
                                           "(immer nur ein Tunnel)."))
        right.addWidget(self.autostart)
        ks_row = QHBoxLayout()
        self.killswitch = QCheckBox("Kill-Switch: ohne VPN kein Internet für diesen Rechner")
        self.exceptions_btn = _small("Ausnahmen …", "Netze, die ohne Tunnel erreichbar bleiben (z. B. das Heimnetz "
                                     "für Drucker und NAS)")
        ks_row.addWidget(self.killswitch)
        ks_row.addWidget(self.exceptions_btn)
        ks_row.addStretch(1)
        right.addLayout(ks_row)
        self.ks_note = QLabel()
        self.ks_note.setObjectName("Muted")
        self.ks_note.setWordWrap(True)
        right.addWidget(self.ks_note)
        right.addStretch(1)
        bl.addLayout(right, 1)
        lay.addWidget(self.body, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        lay.addWidget(self.message)
        self.filler = QWidget()  # hält alles oben, solange die Tunnelansicht fehlt
        lay.addWidget(self.filler, 1)

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(LIVE_MS)
        self.live_timer.timeout.connect(self._live)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(lambda: self.reload(quiet=True))

        self.setup_btn.clicked.connect(self._install_tools)
        self.list.currentItemChanged.connect(lambda *_: self._select())
        self.toggle_btn.clicked.connect(self._toggle)
        self.ip_btn.clicked.connect(self._ip)
        self.import_btn.clicked.connect(self._import_dialog)
        self.edit_btn.clicked.connect(self._edit)
        self.rename_btn.clicked.connect(self._rename)
        self.export_btn.clicked.connect(self._export)
        self.delete_btn.clicked.connect(self._delete)
        self.refresh_btn.clicked.connect(lambda: self.reload())
        self.help_btn.clicked.connect(lambda: open_url(HELP_URL))
        # „clicked“ statt „toggled“: nur echte Klicks lösen etwas aus, nicht das Setzen aus dem Status
        self.autostart.clicked.connect(self._toggle_autostart)
        self.killswitch.clicked.connect(self._toggle_killswitch)
        self.exceptions_btn.clicked.connect(self._exceptions)
        self._show()

    # ---------- Sichtbarkeit und Abfragen ----------
    def start(self) -> None:
        """Bereich wird gezeigt: Status holen, Live-Werte und (ohne Passwort) regelmäßige Abfrage."""
        self.live_timer.start()
        if not hostvpn.status_needs_password():
            self.status_timer.start()
        if self.ready() and not self.busy():
            if self.status is None and hostvpn.status_needs_password():
                self._show()  # „Aktualisieren“ fragt nach dem Passwort – nicht ungefragt beim Öffnen
            else:
                self.reload(quiet=True)
        self._show()

    def pause(self) -> None:
        """Bereich ist verdeckt: nur noch die Live-Werte (für Abbruch-Meldungen und Tray)."""
        self.status_timer.stop()

    def ready(self) -> bool:
        return hostvpn.helper() is not None and not hostvpn.missing_tools()

    def busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def current(self) -> model.Tunnel | None:
        item = self.list.currentItem()
        return self.status.get(item.data(Qt.UserRole)) if item and self.status else None

    def state(self) -> str:
        return self.status.state() if self.status else "disconnected"

    def _live(self) -> None:
        if self.status is None:
            return
        live = model.read_live()
        self.activity.update(live)
        changed = self.status.apply_live(live)
        self.activity.apply(self.status)
        if changed and not self.busy():
            if hostvpn.status_needs_password():
                for t in self.status.tunnels:
                    t.active = t.name in live
                self._events()
            else:
                self.reload(quiet=True)
        self._show()

    def _events(self) -> None:
        if self.status is None:
            return
        for ev in self.watch.observe(self.status):
            self.notify.emit(ev.title(), ev.body())
        st = self.status.state()
        if st != self._last_state:
            self._last_state = st
            self.state_changed.emit(st)

    def reload(self, quiet: bool = False) -> None:
        if not self.ready() or self.busy():
            self._show()
            return

        def done(data: dict) -> None:
            self._set_status(data)

        self._run(hostvpn.status, done, "" if quiet else "Frage den Status ab …", quiet=quiet)

    def _set_status(self, data: dict) -> None:
        self.nm_active = hostvpn.nm_wireguard()
        self.status = model.Status.from_helper(data)
        live = model.read_live()
        self.activity.update(live)
        self.status.apply_live(live)
        self.activity.apply(self.status)
        self.error = ""
        self._events()

    def _run(self, fn, done=None, message: str = "", quiet: bool = False, expect: bool = False) -> None:
        if self.busy():
            return
        if expect:
            self.watch.expect()
        w = TaskWorker(fn)
        self.worker = w
        self.message.setText(message)
        self.message.setStyleSheet("")

        def finished() -> None:
            if w.error is None:
                self.message.setText("")
                if done:
                    done(w.result)
            elif quiet:
                self.error = str(w.error)
                self.message.setText("")
            else:
                self.message.setText(f"Fehler: {w.error}")
                self.message.setStyleSheet(f"color: {style.DANGER};")
            self._show()

        w.finished.connect(finished)
        w.start()
        self._show()

    def _act(self, fn, message: str, after=None) -> None:
        """Aktion, danach den neuen Status holen (beides im Hintergrund)."""
        def run():
            fn()
            return hostvpn.status()

        def done(data) -> None:
            self._set_status(data)
            if after:
                after()

        self._run(run, done, message, expect=True)

    # ---------- Anzeige ----------
    def _show(self) -> None:
        helper = hostvpn.helper()
        missing = hostvpn.missing_tools()
        self.setup.setVisible(helper is None or bool(missing))
        if helper is None:
            self.setup_text.setText("Der Helfer von Bony's VPN fehlt. Er kommt mit dem .deb-Paket von Bony's Agents "
                                    "(auch über die Aktualisierungsverwaltung). Ohne ihn lässt sich WireGuard auf "
                                    "diesem Rechner hier nicht steuern.")
            self.setup_btn.setVisible(False)
        elif missing:
            self.setup_text.setText(f"Für Bony's VPN fehlen noch die Debian-Pakete {', '.join(missing)}. "
                                    "Bony's Agents installiert sie nach deiner Zustimmung über apt "
                                    "(Administrator-Passwort).")
            self.setup_btn.setVisible(hostvpn.has_apt())
            self.setup_btn.setEnabled(not self.busy())
        ready = helper is not None and not missing
        self.body.setVisible(ready)
        self.filler.setVisible(not ready)
        st = self.status
        if not ready:
            self.headline.setText("WireGuard für diesen Rechner")
            self.headline.setStyleSheet("")
            self.note.setText(hostvpn.WHOLE_COMPUTER)
            self.note.setVisible(True)
            return
        if st is None:
            self.headline.setText("Bony's VPN")
            self.headline.setStyleSheet("")
            self.note.setText(self.error or ("„Aktualisieren“ fragt nach dem Administrator-Passwort und zeigt "
                                             "dann die Tunnel." if hostvpn.status_needs_password()
                                             else "Frage den Status ab …"))
        else:
            state = st.state()
            self.headline.setText(f"●  {st.summary()}")
            self.headline.setStyleSheet(f"color: {STATE_COLORS[state]};")
            notes = [hostvpn.WHOLE_COMPUTER]
            if not st.tunnels:
                notes.append(model.tr("WireGuard-Konfiguration (.conf oder .zip) hierher ziehen oder "
                                      "„Importieren …“ wählen."))
            if self.error:
                notes.append(f"⚠ {self.error}")
            self.note.setText("\n".join(notes))
        self.note.setVisible(bool(self.note.text()))

        # Liste
        names = st.names() if st else []
        selected = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else self._selected
        if names != [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]:
            self.list.blockSignals(True)
            self.list.clear()
            for n in names:
                it = QListWidgetItem(n)
                it.setData(Qt.UserRole, n)
                self.list.addItem(it)
            self.list.blockSignals(False)
        if self.list.currentItem() is None and names:
            want = selected if selected in names else (st.active.name if st and st.active else names[0])
            self.list.blockSignals(True)
            self.list.setCurrentRow(names.index(want))
            self.list.blockSignals(False)
        for i in range(self.list.count()):
            item = self.list.item(i)
            t = st.get(item.data(Qt.UserRole)) if st else None
            if t is None:
                continue
            item.setIcon(state_icon(("warning" if t.stale() else "connected") if t.active else "disconnected"))
            item.setText(t.name + ("  · verbunden" if t.active else "") + ("" if t.managed else "  (fremd)"))
            item.setToolTip("" if t.managed else model.tr("nicht von Bony's VPN angelegt – nur verbinden und trennen"))

        t = self.current()
        while self.form.rowCount():
            self.form.removeRow(0)
        if t:
            self.tunnel_title.setText(f"TUNNEL „{t.name}“".upper())
            for label, value in t.detail_rows():
                v = QLabel(value)
                v.setTextInteractionFlags(Qt.TextSelectableByMouse)
                v.setWordWrap(True)
                self.form.addRow(label, v)
            extra = []
            if t.error:
                extra.append(model.tr("Fehler in der Konfiguration: {error}", error=t.error))
            if t.hooks:
                extra.append(model.tr("Achtung: führt beim Verbinden Befehle als root aus ({hooks}).",
                                      hooks=", ".join(t.hooks)))
            if t.name in self.nm_active:
                extra.append("Wird vom NetworkManager verwaltet – trennen über das Netzwerk-Symbol der Leiste.")
            elif not t.managed:
                extra.append("Nicht mit Bony's VPN angelegt: verbinden, trennen und ansehen geht, ändern nicht.")
            self.tunnel_note.setText("\n".join(extra))
            self.tunnel_note.setStyleSheet(f"color: {style.WARN};" if t.hooks or t.error else "")
        else:
            self.tunnel_title.setText("")
            self.tunnel_note.setText("")
        self.tunnel_note.setVisible(bool(self.tunnel_note.text()))
        idle = st is not None and not self.busy()
        self.toggle_btn.setText("Trennen" if t and t.active else "Verbinden")
        self.toggle_btn.setObjectName("" if t and t.active else "Primary")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)
        self.toggle_btn.setEnabled(idle and t is not None and not t.error and t.name not in self.nm_active)
        self.ip_btn.setEnabled(not self.busy())
        self.import_btn.setEnabled(not self.busy() and (st is not None or not hostvpn.status_needs_password()))
        self.edit_btn.setEnabled(idle and t is not None)
        self.edit_btn.setText("Bearbeiten …" if t is None or t.managed else "Ansehen …")
        for b in (self.rename_btn, self.export_btn, self.delete_btn):
            b.setEnabled(idle and t is not None and t.managed)
        self.refresh_btn.setEnabled(not self.busy())
        self.autostart.setEnabled(idle and t is not None)
        self.autostart.setChecked(bool(t and t.autostart))
        self.killswitch.setEnabled(idle)
        self.killswitch.setChecked(bool(st and st.killswitch_enabled))
        self.exceptions_btn.setEnabled(idle)
        ks = []
        if st and st.killswitch_enabled:
            ks.append("Kill-Switch an: Ohne Tunnel hat dieser Rechner kein Internet. Agent-PCs laufen weiter, "
                      "ihr Internet geht nur über den Tunnel.")
        if st and st.exceptions:
            ks.append(model.tr("Immer erreichbar: {nets}", nets=", ".join(st.exceptions)))
        self.ks_note.setText("\n".join(ks))
        self.ks_note.setVisible(bool(ks))
        self.ip_label.setText(self.ip_text)
        self.ip_label.setVisible(bool(self.ip_text))

    def _select(self) -> None:
        item = self.list.currentItem()
        if item:
            self._selected = item.data(Qt.UserRole)
        self._show()

    # ---------- Aktionen ----------
    def _install_tools(self) -> None:
        missing = hostvpn.missing_tools()
        if QMessageBox.question(
                self, APP_NAME, f"Jetzt {', '.join(missing)} aus den Paketquellen deines Systems installieren?\n\n"
                "Dafür fragt dein Rechner einmal nach dem Administrator-Passwort.") != QMessageBox.Yes:
            return
        self._run(lambda: hostvpn.install_tools(missing), lambda _r: self.reload(), "Installiere WireGuard …")

    def _toggle(self) -> None:
        t = self.current()
        if t is None:
            return
        if t.active:
            self._act(lambda: hostvpn.down(t.name), f"Trenne „{t.name}“ …")
            return
        if not self._nm_free() or not confirm_whole_computer(self):
            return
        self.ip_text = ""
        self._act(lambda: hostvpn.up(t.name), f"Verbinde „{t.name}“ …")

    def _nm_free(self) -> bool:
        """Läuft ein WireGuard-Tunnel des NetworkManager, bissen sich beide (gleiche Routing-Tabelle)."""
        self.nm_active = hostvpn.nm_wireguard()
        if self.nm_active:
            QMessageBox.information(
                self, APP_NAME, f"Gerade ist „{', '.join(sorted(self.nm_active))}“ über den NetworkManager verbunden. "
                "Bitte diesen Tunnel zuerst über das Netzwerk-Symbol der Leiste trennen – zwei WireGuard-Tunnel für "
                "den ganzen Rechner gleichzeitig kommen sich in die Quere.")
            return False
        return True

    def _toggle_autostart(self, on: bool) -> None:
        t = self.current()
        if t is None:
            return
        self._act(lambda: hostvpn.set_autostart(t.name, on),
                  "Schalte automatisches Verbinden " + ("ein …" if on else "aus …"))

    def _toggle_killswitch(self, on: bool) -> None:
        if on:
            box = QMessageBox(QMessageBox.Warning, "Kill-Switch", hostvpn.KILLSWITCH_WARNING,
                              QMessageBox.Cancel, self)
            yes = box.addButton("Kill-Switch einschalten", QMessageBox.AcceptRole)
            box.setDefaultButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is not yes:
                self._show()
                return
        self._act(lambda: hostvpn.set_killswitch(on), "Schalte den Kill-Switch " + ("ein …" if on else "aus …"))

    def _exceptions(self) -> None:
        current = ", ".join(self.status.exceptions) if self.status else ""
        text, ok = QInputDialog.getText(
            self, "Kill-Switch – Ausnahmen",
            "Netze, die auch ohne Tunnel erreichbar bleiben, durch Komma getrennt\n"
            "(z. B. 192.168.178.0/24 für das Heimnetz einer Fritzbox). Leer = keine Ausnahmen.\n"
            "Gilt beim nächsten Einschalten bzw. sofort, wenn der Kill-Switch an ist.",
            QLineEdit.Normal, current)
        if not ok:
            return
        try:
            nets = hostvpn.parse_exceptions(text)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        enabled = bool(self.status and self.status.killswitch_enabled)

        def run() -> None:
            hostvpn.set_killswitch(True, nets)
            if not enabled:
                hostvpn.set_killswitch(False)

        self._act(run, "Speichere die Ausnahmen …")

    def _ip(self) -> None:
        def done(ip) -> None:
            st = self.status
            active = st.active.name if st and st.active else None
            if not ip:
                ks = st and st.killswitch_enabled and not active
                self.ip_text = (f"Öffentliche IP: keine – {model.IP_SERVICE_NAME} ist nicht erreichbar"
                                + (" (Kill-Switch sperrt ohne Tunnel)." if ks else "."))
            else:
                self.ip_text = (f"Öffentliche IP: {ip}" + (f" (über „{active}“)" if active else " (ohne VPN)")
                                + f" – ermittelt über {model.IP_SERVICE_NAME}")

        def fetch():
            try:
                return model.public_ip()
            except (OSError, ValueError):
                return None

        self.ip_text = ""
        self._run(fetch, done, "Frage die öffentliche IP ab …")

    # Import
    def dragEnterEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        if event.mimeData().hasUrls() and self.body.isVisible():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.import_files(paths)

    def _import_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, model.tr("Konfigurationen importieren"), str(Path.home()),
                                                "WireGuard-Konfigurationen (*.conf *.zip);;Alle Dateien (*)")
        if files:
            self.import_files([Path(f) for f in files])

    def import_files(self, paths: list[Path]) -> None:
        """Dateien lesen (als Benutzer), Namen klären, Hook-Zeilen bestätigen lassen, dann importieren."""
        if self.busy() or not confirm_whole_computer(self):
            return
        items: list[tuple[str, bytes]] = []
        problems: list[str] = []
        for p in paths:
            try:
                items += vpncli.confs_from(p)
            except vpncli.CliError as e:
                problems.append(str(e))
        existing = set(self.status.names() if self.status else [])
        jobs: list[tuple[str, bytes, bool, bool]] = []   # Name, Inhalt, Hooks erlauben, ersetzen
        for stem, data in items:
            try:
                parsed = wgconf.parse(wgconf.decode(data))
            except wgconf.ConfError as e:
                problems.append(f"{stem}: {e}")
                continue
            name = model.suggest_name(stem)
            replace = False
            while name in existing:
                box = QMessageBox(QMessageBox.Question, APP_NAME, model.tr("Den Tunnel „{name}“ gibt es schon.",
                                                                             name=name), QMessageBox.NoButton, self)
                rep = box.addButton(model.tr("Ersetzen"), QMessageBox.DestructiveRole)
                other = box.addButton(model.tr("Anderer Name"), QMessageBox.ActionRole)
                box.addButton(model.tr("Überspringen"), QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is rep:
                    replace = True
                    break
                if box.clickedButton() is not other:
                    name = ""
                    break
                new, ok = QInputDialog.getText(self, APP_NAME, model.tr("Name des Tunnels") + " ("
                                               + model.tr("1–15 Zeichen: A–Z, a–z, 0–9 und _ = + . -") + "):",
                                               QLineEdit.Normal, model.suggest_name(name, existing))
                if not ok:
                    name = ""
                    break
                if model.name_error(new.strip()):
                    QMessageBox.warning(self, APP_NAME, model.name_error(new.strip()))
                    continue
                name = new.strip()
            if not name:
                continue
            if replace and self.status and self.status.get(name) and not self.status.get(name).managed:
                problems.append(f"„{name}“ wurde nicht mit Bony's VPN angelegt und lässt sich nicht ersetzen.")
                continue
            if parsed.hooks and not confirm_hooks(self, name, list(parsed.hooks)):
                continue
            jobs.append((name, data, bool(parsed.hooks), replace))
            existing.add(name)
        if not jobs:
            if problems:
                QMessageBox.warning(self, APP_NAME, "\n".join(problems))
            return

        def run():
            done, failed = [], list(problems)
            for name, data, hooks, replace in jobs:
                try:
                    hostvpn.import_conf(name, data, allow_hooks=hooks, replace=replace)
                    done.append(name)
                except hostvpn.HostVpnError as e:
                    failed.append(f"{name}: {e}")
            return done, failed, hostvpn.status()

        def finished(result) -> None:
            done, failed, data = result
            self._set_status(data)
            if done:
                self._selected = done[-1]
                self.list.setCurrentItem(None)
                self.message.setText(("Importiert: " + ", ".join(f"„{n}“" for n in done))
                                     + (" – jetzt „Verbinden“." if len(done) == 1 else ""))
            if failed:
                QMessageBox.warning(self, APP_NAME, "\n".join(failed))

        self._run(run, finished, f"Importiere {len(jobs)} Konfiguration(en) …", expect=True)

    def _edit(self) -> None:
        t = self.current()
        if t is None:
            return
        try:
            shown = hostvpn.show(t.name)
        except hostvpn.HostVpnError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        dlg = EditorDialog(t.name, shown, self)
        while dlg.exec() == QDialog.Accepted and dlg.managed:
            if dlg.hooks and not confirm_hooks(self, t.name, dlg.hooks):
                continue
            text, hooks = dlg.text(), bool(dlg.hooks)
            self._act(lambda text=text, hooks=hooks: hostvpn.import_conf(t.name, text.encode("utf-8"),
                                                                         allow_hooks=hooks, replace=True),
                      "Speichere …", after=lambda: self.message.setText(
                          model.tr("Gespeichert.") + (" Neu verbinden, damit es gilt." if t.active else "")))
            break

    def _rename(self) -> None:
        t = self.current()
        if t is None:
            return
        if t.active:
            QMessageBox.information(self, APP_NAME, model.tr("Bitte zuerst trennen."))
            return
        new, ok = QInputDialog.getText(self, model.tr("„{name}“ umbenennen", name=t.name),
                                       model.tr("1–15 Zeichen: A–Z, a–z, 0–9 und _ = + . -"), QLineEdit.Normal, t.name)
        new = new.strip()
        if not ok or not new or new == t.name:
            return
        if model.name_error(new):
            QMessageBox.warning(self, APP_NAME, model.name_error(new))
            return
        self._selected = new
        self.list.setCurrentItem(None)
        self._act(lambda: hostvpn.rename(t.name, new), f"Benenne „{t.name}“ um …")

    def _export(self) -> None:
        t = self.current()
        if t is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, model.tr("„{name}“ exportieren", name=t.name),
                                              str(Path.home() / f"{t.name}.conf"),
                                              "WireGuard-Konfiguration (*.conf)")
        if not path:
            return
        try:
            model.write_private(Path(path), hostvpn.export(t.name))
        except (hostvpn.HostVpnError, OSError) as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.message.setText(model.tr("Exportiert nach {path} (nur für dich lesbar – enthält den privaten "
                                      "Schlüssel).", path=path))
        self.message.setStyleSheet("")

    def _delete(self) -> None:
        t = self.current()
        if t is None:
            return
        box = QMessageBox(QMessageBox.Warning, model.tr("„{name}“ löschen?", name=t.name),
                          model.tr("Die Konfiguration mit dem privaten Schlüssel wird gelöscht. Das lässt sich nicht "
                                   "rückgängig machen."), QMessageBox.Cancel, self)
        yes = box.addButton(model.tr("Löschen"), QMessageBox.DestructiveRole)
        box.setDefaultButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is yes:
            self._selected = ""
            self._act(lambda: hostvpn.delete(t.name), f"Lösche „{t.name}“ …")


class HostVpnWindow(QMainWindow):
    """Eigenes Fenster „Bony's VPN“ (Desktop-Eintrag) mit Tray-Symbol."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bony's VPN")
        self.setWindowIcon(state_icon("disconnected"))
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        self.panel = HostVpnPanel(show_title=False)
        cl.addWidget(self.panel)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(14, 14, 14, 14)
        wl.addWidget(card)
        self.setCentralWidget(wrap)
        self.resize(style.px(820), style.px(560))
        self.quitting = False
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(state_icon("disconnected"), self)
            self.tray.setToolTip("Bony's VPN")
            self.menu = QMenu()
            self.menu.aboutToShow.connect(self._fill_menu)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(lambda reason: self._raise() if reason == QSystemTrayIcon.Trigger else None)
            self.tray.show()
        self.panel.state_changed.connect(self._state)
        self.panel.notify.connect(self._notify)
        self.panel.start()

    def _state(self, state: str) -> None:
        icon = state_icon(state)
        self.setWindowIcon(icon)
        if self.tray:
            self.tray.setIcon(icon)
            self.tray.setToolTip(f"Bony's VPN – {self.panel.status.summary() if self.panel.status else ''}")

    def _notify(self, title: str, body: str) -> None:
        if self.tray:
            self.tray.showMessage(title, body, QSystemTrayIcon.Warning, 10_000)
        self.statusBar().showMessage(f"{title}: {body}", 15_000)

    def _raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.panel.start()

    def _fill_menu(self) -> None:
        self.menu.clear()
        self.menu.addAction(model.tr("Fenster öffnen"), self._raise)
        st = self.panel.status
        if st and st.tunnels:
            self.menu.addSeparator()
            for t in st.tunnels:
                a = self.menu.addAction(("●  " if t.active else "○  ") + t.name)
                a.setEnabled(not self.panel.busy() and not t.error)
                a.triggered.connect(lambda _=False, t=t: self._tray_toggle(t))
        self.menu.addSeparator()
        self.menu.addAction(model.tr("Beenden"), self._quit)

    def _tray_toggle(self, t: model.Tunnel) -> None:
        if t.active:
            self.panel._act(lambda: hostvpn.down(t.name), f"Trenne „{t.name}“ …")
        elif self.panel._nm_free() and confirm_whole_computer(self):
            self.panel._act(lambda: hostvpn.up(t.name), f"Verbinde „{t.name}“ …")

    def _quit(self) -> None:
        self.quitting = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        if self.tray and not self.quitting:
            event.ignore()
            self.hide()
            self.panel.pause()
            if not storage.load_settings().get("host_vpn_tray_hint"):
                self.tray.showMessage("Bony's VPN", "Läuft im Infobereich weiter und meldet Abbrüche. "
                                      "Beenden über das Symbol.", QSystemTrayIcon.Information, 8000)
                s = storage.load_settings()
                s["host_vpn_tray_hint"] = True
                storage.save_settings(s)
            return
        if self.tray:
            self.tray.hide()
        super().closeEvent(event)


# ---------------------------------------------------------------- Windows / macOS
def windows_wireguard(parent: QWidget) -> TaskWorker | None:
    """„Extras → WireGuard für diesen Rechner installieren“: offizielle App per winget, sonst öffnen."""
    exe = hostvpn.windows_app()
    if exe is not None:
        if QMessageBox.question(parent, APP_NAME, "Die WireGuard-App ist schon installiert. Jetzt öffnen?\n\n"
                                + hostvpn.WHOLE_COMPUTER) == QMessageBox.Yes:
            try:
                hostvpn.windows_open(exe)
            except (hostvpn.HostVpnError, OSError) as e:
                QMessageBox.warning(parent, APP_NAME, str(e))
        return None
    box = QMessageBox(QMessageBox.Information, "WireGuard für diesen Rechner", hostvpn.WINDOWS_INTRO,
                      QMessageBox.Cancel, parent)
    go = box.addButton("Installieren", QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is not go:
        return None
    w = TaskWorker(hostvpn.windows_install)

    def done() -> None:
        if w.error is not None:
            QMessageBox.warning(parent, APP_NAME, str(w.error))
            return
        if QMessageBox.question(parent, APP_NAME, "WireGuard ist installiert. App jetzt öffnen?") == QMessageBox.Yes:
            try:
                hostvpn.windows_open()
            except (hostvpn.HostVpnError, OSError) as e:
                QMessageBox.warning(parent, APP_NAME, str(e))

    w.finished.connect(done)
    w.start()
    return w


def mac_wireguard(parent: QWidget) -> None:
    """„Extras → WireGuard für diesen Rechner …“: App öffnen oder App-Store-Seite zeigen."""
    if hostvpn.mac_app() is not None:
        if QMessageBox.question(parent, APP_NAME, "Die WireGuard-App ist schon installiert. Jetzt öffnen?\n\n"
                                + hostvpn.WHOLE_COMPUTER) == QMessageBox.Yes:
            hostvpn.mac_open_app()
        return
    box = QMessageBox(QMessageBox.Information, "WireGuard für diesen Rechner", hostvpn.MAC_INTRO,
                      QMessageBox.Cancel, parent)
    go = box.addButton("App Store öffnen", QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is go:
        hostvpn.mac_open_store()
