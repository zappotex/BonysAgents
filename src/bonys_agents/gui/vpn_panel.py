# SPDX-License-Identifier: GPL-3.0-or-later
"""Bereich „VPN“ der Detailansicht: Bony's VPN im laufenden Agent-PC.

Der Status kommt über den Gast-Agent (``bonys-vpn status --json``), notfalls per SSH. Eine
Konfiguration wird hier nur gelesen, geprüft und über die Standardeingabe des Helfers übertragen –
auf diesem Rechner bleibt nichts davon liegen.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from bonys_agents import APP_NAME, vm, vpnlink

from . import style
from .widgets import FlowLayout
from .workers import TaskWorker

POLL_MS = 10_000  # Status bei sichtbarem Bereich alle 10 s


def _small(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Small")
    if tip:
        b.setToolTip(tip)
    return b


def tunnel_details(t: dict) -> str:
    """Nicht geheime Angaben eines Tunnels für die Anzeige."""
    lines = []
    if t.get("addresses"):
        lines.append(f"Adresse: {', '.join(t['addresses'])}")
    eps = [p["endpoint"] for p in t.get("peers") or [] if p.get("endpoint")]
    if eps:
        lines.append(f"Server: {', '.join(eps)}")
    if t.get("active"):
        lines.append(f"Letzter Handshake: {vpnlink.human_age(t.get('handshake'))} · "
                     f"empfangen {vpnlink.human_bytes(t.get('rx'))}, gesendet {vpnlink.human_bytes(t.get('tx'))}")
    if t.get("autostart"):
        lines.append("Verbindet sich bei jedem Start automatisch.")
    return "\n".join(lines)


class VpnPanel(QWidget):
    install_requested = Signal()   # „VPN-App installieren“ – das Hauptfenster öffnet „Programme hinzufügen“

    def __init__(self, parent=None):
        super().__init__(parent)
        self.machine: vm.VM | None = None
        self.state: dict | None = None
        self.error = ""
        self.ip_text = ""
        self.workers: list[TaskWorker] = []
        self._loaded_for = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self.headline = QLabel()
        self.headline.setObjectName("Title")
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.note = QLabel()
        self.note.setObjectName("Muted")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        # Ohne Bony's VPN
        self.install_btn = QPushButton("VPN-App installieren")
        self.install_btn.setObjectName("Primary")
        self.install_btn.setToolTip("Installiert Bony's VPN (WireGuard, Kill-Switch, Tray-Symbol) im laufenden "
                                    "Agent-PC – wie „Programme hinzufügen“")
        lay.addWidget(self.install_btn)

        # Mit Bony's VPN
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        trow = QHBoxLayout()
        self.tunnel_label = QLabel("Tunnel")
        self.tunnel = QComboBox()
        self.tunnel.setMinimumContentsLength(15)
        trow.addWidget(self.tunnel_label)
        trow.addWidget(self.tunnel)
        trow.addStretch(1)
        bl.addLayout(trow)
        self.details = QLabel()
        self.details.setWordWrap(True)
        bl.addWidget(self.details)
        buttons = FlowLayout()
        self.up_btn = QPushButton("Verbinden")
        self.up_btn.setObjectName("Primary")
        self.down_btn = QPushButton("Trennen")
        self.ip_btn = _small("Öffentliche IP prüfen",
                             f"Fragt im Agent-PC {vpnlink.IP_SERVICE_NAME} nach der Adresse, mit der er im Internet "
                             "auftritt")
        self.import_btn = _small("Konfiguration importieren …",
                                 "WireGuard-Konfiguration (.conf) in diesen Agent-PC übertragen – auf diesem Rechner "
                                 "wird nichts gespeichert")
        self.refresh_btn = _small("Aktualisieren")
        for b in (self.up_btn, self.down_btn, self.ip_btn, self.import_btn, self.refresh_btn):
            buttons.addWidget(b)
        bl.addLayout(buttons)
        self.ip_label = QLabel()
        self.ip_label.setWordWrap(True)
        bl.addWidget(self.ip_label)
        self.autostart = QCheckBox("Diesen Tunnel bei jedem Start automatisch verbinden")
        self.killswitch = QCheckBox("Kill-Switch: ohne VPN kein Internet")
        self.killswitch.setToolTip("Sperrt jeden Internetverkehr des Agent-PCs, solange kein Tunnel verbunden ist. "
                                   "Steuerung, Herunterfahren, Fortschritt und Fernzugriff gehen weiter "
                                   "(QEMU-Netz 10.0.2.0/24 ist ausgenommen).")
        bl.addWidget(self.autostart)
        bl.addWidget(self.killswitch)
        lay.addWidget(self.body)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(lambda: self.reload(quiet=True))
        self.install_btn.clicked.connect(self.install_requested.emit)
        self.refresh_btn.clicked.connect(lambda: self.reload())
        self.up_btn.clicked.connect(self._up)
        self.down_btn.clicked.connect(lambda: self._act(lambda m, **kw: vpnlink.down(m, self.tunnel.currentText()
                                                                                     or None, **kw), "Trenne …"))
        self.ip_btn.clicked.connect(self._ip)
        self.import_btn.clicked.connect(self._import)
        self.tunnel.activated.connect(lambda _i: self._show())
        # „clicked“ statt „toggled“: nur echte Klicks lösen etwas aus, nicht das Setzen aus dem Status
        self.autostart.clicked.connect(self._toggle_autostart)
        self.killswitch.clicked.connect(self._toggle_killswitch)

    # ---------- Anzeige ----------
    def busy(self) -> bool:
        return any(w.isRunning() for w in self.workers)

    def usable(self) -> bool:
        m = self.machine
        return bool(m and m.status() == "läuft")

    def update_for(self, m: vm.VM, status: str) -> None:
        """Vom Hauptfenster bei jedem Auffrischen (nur wenn der Bereich sichtbar ist)."""
        if self.machine is None or self.machine.path != m.path:
            self.state, self.error, self.ip_text, self._loaded_for = None, "", "", ""
        self.machine = m
        running = status == "läuft"
        if running and not self.timer.isActive():
            self.timer.start()
        elif not running:
            self.timer.stop()
            self.state, self._loaded_for = None, ""
        if running and vpnlink.APP_ID in m.config.apps and self._loaded_for != m.name and not self.busy():
            self.reload()
        self._show()

    def hideEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self.timer.stop()
        super().hideEvent(event)

    def _show(self) -> None:
        m = self.machine
        if m is None:
            return
        has_app = vpnlink.APP_ID in m.config.apps or bool(self.state and self.state.get("installed"))
        running = self.usable()
        st = self.state if has_app else None
        self.install_btn.setVisible(not has_app)
        self.install_btn.setEnabled(running and not self.busy())
        self.body.setVisible(has_app)
        if not has_app:
            self.headline.setText("Bony's VPN ist nicht installiert")
            self.note.setText("Mit Bony's VPN geht der Internetverkehr des Agent-PCs durch deinen eigenen "
                              "WireGuard-Tunnel, auf Wunsch mit Kill-Switch. "
                              + ("" if running else "Zum Installieren muss der Agent-PC laufen."))
            self.note.setVisible(True)
            return
        if not running:
            self.headline.setText("VPN")
            self.note.setText("Status und Steuerung gibt es, solange der Agent-PC läuft.")
        elif st is None:
            self.headline.setText("VPN")
            self.note.setText(self.error or "Frage den Status im Agent-PC ab …")
        elif not st.get("installed", True):
            self.headline.setText("Bony's VPN fehlt im Agent-PC")
            self.note.setText("Laut Einstellungen installiert, im Agent-PC aber nicht gefunden.")
        else:
            active = st.get("active")
            self.headline.setText(f"●  verbunden – „{active}“" if active else "●  getrennt")
            self.headline.setStyleSheet(f"color: {style.OK if active else style.MUTED};")
            ks = st.get("killswitch") or {}
            notes = []
            if ks.get("enabled") and not active:
                notes.append("Kill-Switch an: Ohne Tunnel hat der Agent-PC kein Internet.")
            if not st.get("tunnels"):
                notes.append("Noch kein Tunnel – „Konfiguration importieren …“ oder im Agent-PC über Bony's VPN.")
            if self.error:
                notes.append(f"⚠ {self.error}")
            self.note.setText("\n".join(notes))
        if st is None or not st.get("installed", True):
            self.headline.setStyleSheet("")
        names = [t["name"] for t in (st or {}).get("tunnels") or []]
        current = self.tunnel.currentText()
        if names != [self.tunnel.itemText(i) for i in range(self.tunnel.count())]:
            self.tunnel.clear()
            self.tunnel.addItems(names)
        want = (st or {}).get("active") or (current if current in names else vpnlink.default_tunnel(st or {}))
        if want in names:
            self.tunnel.setCurrentText(want)
        tunnel = next((t for t in (st or {}).get("tunnels") or [] if t["name"] == self.tunnel.currentText()), None)
        self.tunnel.setVisible(bool(names))
        self.tunnel_label.setVisible(bool(names))
        self.details.setText(tunnel_details(tunnel) if tunnel else "")
        self.details.setVisible(bool(tunnel))
        ok = running and st is not None and st.get("installed", True) and not self.busy()
        self.up_btn.setEnabled(ok and tunnel is not None and not tunnel.get("active"))
        self.down_btn.setEnabled(ok and bool((st or {}).get("active")))
        self.ip_btn.setEnabled(running and not self.busy())
        self.import_btn.setEnabled(ok)
        self.refresh_btn.setEnabled(running and not self.busy())
        self.autostart.setEnabled(ok and tunnel is not None)
        self.autostart.setChecked(bool(tunnel and tunnel.get("autostart")))
        self.killswitch.setEnabled(ok)
        self.killswitch.setChecked(bool(((st or {}).get("killswitch") or {}).get("enabled")))
        self.ip_label.setText(self.ip_text)
        self.ip_label.setVisible(bool(self.ip_text))
        self.note.setVisible(bool(self.note.text()))

    # ---------- Aktionen ----------
    def _start(self, fn, done=None, message: str = "") -> None:
        """``fn(password)`` im Hintergrund. Antwortet der Gast-Agent nicht, wird nach dem Passwort gefragt."""
        m = self.machine
        if m is None:
            return
        w = TaskWorker(lambda: fn(None))
        self.status.setText(message)
        self.status.setStyleSheet("")

        def finished() -> None:
            self.workers = [x for x in self.workers if x.isRunning()]
            if w.error is None:
                self.status.setText("")
                if done:
                    done(w.result)
            elif isinstance(w.error, vm.NeedsPassword):
                pw, ok = QInputDialog.getText(self, APP_NAME, f"{w.error}\n\nPasswort von „{m.name}“:",
                                              QLineEdit.Password)
                if ok and pw:
                    self._start(lambda _pw: fn(pw), done, message)
                    return
                self.status.setText("")
            else:
                self.status.setText(f"Fehler: {w.error}")
                self.status.setStyleSheet(f"color: {style.DANGER};")
            self._show()

        w.finished.connect(finished)
        self.workers.append(w)
        w.start()
        self._show()

    def reload(self, quiet: bool = False) -> None:
        m = self.machine
        if m is None or not self.usable() or self.busy():
            return
        if quiet and vpnlink.APP_ID not in m.config.apps:
            return

        def fetch(pw):
            try:
                return vpnlink.status(m, password=pw)
            except vm.NeedsPassword:
                if quiet:  # regelmäßige Abfrage: nicht jedes Mal nach dem Passwort fragen
                    return {"_error": "Der Gast-Agent antwortet nicht – „Aktualisieren“ fragt nach dem Passwort."}
                raise

        def done(result) -> None:
            self._loaded_for = m.name
            if "_error" in result:
                self.error = result["_error"]
                return
            self.state, self.error = result, ""

        self._start(fetch, done, "" if quiet else "Frage den Status ab …")

    def _act(self, fn, message: str) -> None:
        m = self.machine
        if m is None:
            return

        def run(pw):
            fn(m, password=pw)
            return vpnlink.status(m, password=pw)

        self._start(run, self._set_state, message)

    def _set_state(self, st: dict) -> None:
        self.state, self.error = st, ""

    def _up(self) -> None:
        name = self.tunnel.currentText()
        if name:
            self.ip_text = ""
            self._act(lambda m, **kw: vpnlink.up(m, name, **kw), f"Verbinde „{name}“ …")

    def _toggle_autostart(self, on: bool) -> None:
        name = self.tunnel.currentText()
        if name:
            self._act(lambda m, **kw: vpnlink.set_autostart(m, name, on, **kw),
                      "Schalte automatisches Verbinden " + ("ein …" if on else "aus …"))

    def _toggle_killswitch(self, on: bool) -> None:
        if on and not (self.state or {}).get("active") and QMessageBox.question(
                self, APP_NAME, "Kill-Switch einschalten?\n\nGerade ist kein Tunnel verbunden – der Agent-PC hat dann "
                "sofort kein Internet mehr, bis du verbindest. Die Steuerung durch Bony's Agents geht weiter.") \
                != QMessageBox.Yes:
            self._show()
            return
        self._act(lambda m, **kw: vpnlink.set_killswitch(m, on, **kw),
                  "Schalte den Kill-Switch " + ("ein …" if on else "aus …"))

    def _ip(self) -> None:
        m = self.machine
        if m is None:
            return

        def fetch(pw) -> str | None:
            try:
                return vpnlink.public_ip(m, password=pw)
            except vm.NeedsPassword:
                raise
            except vpnlink.VpnError:
                return None  # kein Internet – kein Fehler, sondern das Ergebnis

        def done(ip: str | None) -> None:
            active = (self.state or {}).get("active")
            if ip is None:
                ks = ((self.state or {}).get("killswitch") or {}).get("enabled")
                self.ip_text = f"Öffentliche IP: keine – der Agent-PC erreicht {vpnlink.IP_SERVICE_NAME} nicht" + (
                    " (Kill-Switch sperrt ohne Tunnel)." if ks and not active else ".")
                return
            self.ip_text = f"Öffentliche IP: {ip}" + (f" (über „{active}“)" if active else " (ohne VPN)") \
                + f" – ermittelt über {vpnlink.IP_SERVICE_NAME}"

        self.ip_text = ""
        self._start(fetch, done, "Frage die öffentliche IP ab …")

    def _import(self) -> None:
        m = self.machine
        if m is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "WireGuard-Konfiguration importieren", str(Path.home()),
                                              "WireGuard-Konfiguration (*.conf);;Alle Dateien (*)")
        if not path:
            return
        try:
            setup = vpnlink.load_conf(path)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        names = [t["name"] for t in (self.state or {}).get("tunnels") or []]
        name, ok = QInputDialog.getText(self, APP_NAME, "Name des Tunnels im Agent-PC (1–15 Zeichen):",
                                        QLineEdit.Normal, setup.name)
        if not ok or not name.strip():
            return
        try:
            setup = vpnlink.VpnSetup(name=vpnlink.wgconf.check_name(name.strip()), data=setup.data,
                                     endpoint=setup.endpoint)
        except ValueError:
            QMessageBox.warning(self, APP_NAME, "Tunnelname: 1–15 Zeichen, nur A–Z, a–z, 0–9 und _ = + . -")
            return
        replace = setup.name in names
        if replace and QMessageBox.question(
                self, APP_NAME, f"Den Tunnel „{setup.name}“ gibt es schon. Ersetzen?") != QMessageBox.Yes:
            return

        def run(pw):
            vpnlink.import_conf(m, setup, replace=replace, password=pw)
            return vpnlink.status(m, password=pw)

        def done(st: dict) -> None:
            self._set_state(st)
            self.tunnel.setCurrentText(setup.name)
            self.status.setText(f"„{setup.name}“ importiert – jetzt „Verbinden“.")

        self._start(run, done, f"Übertrage „{setup.name}“ in den Agent-PC …")
