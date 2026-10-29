# SPDX-License-Identifier: GPL-3.0-or-later
"""VPN für den eigenen Rechner.

- Linux: Knopf „VPN“ oben im Fenster → „Bony's VPN öffnen“ bzw. „Bony's VPN installieren“. Bony's VPN ist ein
  eigenes Programm (https://github.com/zappotex/bonys-vpn) – installiert wird nach Rückfrage aus der
  offiziellen Quelle (siehe ``hostvpn.install``), mit pkexec.
- Windows (winget) und macOS (App Store): „Extras → WireGuard für diesen Rechner …“.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMessageBox, QWidget

from bonys_agents import APP_NAME, hostvpn
from bonys_agents.i18n import tr

from .workers import TaskWorker

# Symbol aus dem Paket bonys-vpn (fehlt es, bleibt der Knopf ohne Symbol)
ICON = Path("/usr/share/icons/hicolor/96x96/apps/bonys-vpn.png")


def vpn_icon() -> QIcon:
    return QIcon(str(ICON)) if ICON.exists() else QIcon()


def button_text() -> str:
    return tr("Bony's VPN öffnen") if hostvpn.gui_command() else tr("Bony's VPN installieren")


def linux_vpn(parent: QWidget, log=None) -> TaskWorker | None:
    """Knopf „VPN“ (Linux): Bony's VPN öffnen – oder nach Rückfrage installieren und dann öffnen."""
    if hostvpn.gui_command():
        try:
            hostvpn.open_app()
        except (hostvpn.HostVpnError, OSError) as e:
            QMessageBox.warning(parent, APP_NAME, str(e))
        return None
    if not hostvpn.can_install():
        QMessageBox.information(parent, tr("Bony's "
                                           "VPN"), tr("Bony's VPN gibt es als Paket für Debian, Ubuntu und Linux "
                                                      "Mint. Auf diesem System bitte von {VPN_REPO_URL} installieren.",
                                                      VPN_REPO_URL=hostvpn.VPN_REPO_URL))
        return None
    text = hostvpn.intro(hostvpn.LINUX_INTRO)
    if hostvpn.old_leftovers():
        text += "\n\n" + tr(hostvpn.OLD_INSTALL_HINT)
    box = QMessageBox(QMessageBox.Information, tr("Bony's VPN installieren"), text, QMessageBox.Cancel, parent)
    box.setTextFormat(Qt.PlainText)
    box.button(QMessageBox.Cancel).setText(tr("Abbrechen"))
    go = box.addButton(tr("Installieren"), QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is not go:
        return None
    emit = log or (lambda _line: None)
    w = TaskWorker(lambda: hostvpn.install(emit))

    def done() -> None:
        if w.error is not None:
            QMessageBox.warning(parent, APP_NAME, tr("Bony's VPN wurde nicht installiert:\n\n{error}", error=w.error))
            return
        if QMessageBox.question(parent, APP_NAME, tr("Bony's VPN {result} ist installiert. Jetzt öffnen?",
                                                     result=w.result)) \
                == QMessageBox.Yes:
            try:
                hostvpn.open_app()
            except (hostvpn.HostVpnError, OSError) as e:
                QMessageBox.warning(parent, APP_NAME, str(e))

    w.finished.connect(done)
    w.start()
    return w


# ---------------------------------------------------------------- Windows / macOS
def windows_wireguard(parent: QWidget) -> TaskWorker | None:
    """„Extras → WireGuard für diesen Rechner installieren“: offizielle App per winget, sonst öffnen."""
    exe = hostvpn.windows_app()
    if exe is not None:
        if QMessageBox.question(parent, APP_NAME, tr("Die WireGuard-App ist schon installiert. Jetzt "
                                                     "öffnen?\n\n{WHOLE_COMPUTER}",
                                                     WHOLE_COMPUTER=tr(hostvpn.WHOLE_COMPUTER))) == QMessageBox.Yes:
            try:
                hostvpn.windows_open(exe)
            except (hostvpn.HostVpnError, OSError) as e:
                QMessageBox.warning(parent, APP_NAME, str(e))
        return None
    box = QMessageBox(QMessageBox.Information, tr("WireGuard für diesen Rechner"), hostvpn.intro(hostvpn.WINDOWS_INTRO),
                      QMessageBox.Cancel, parent)
    go = box.addButton(tr("Installieren"), QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is not go:
        return None
    w = TaskWorker(hostvpn.windows_install)

    def done() -> None:
        if w.error is not None:
            QMessageBox.warning(parent, APP_NAME, str(w.error))
            return
        if QMessageBox.question(parent, APP_NAME, tr("WireGuard ist installiert. App jetzt "
                                                     "öffnen?")) == QMessageBox.Yes:
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
        if QMessageBox.question(parent, APP_NAME, tr("Die WireGuard-App ist schon installiert. Jetzt "
                                                     "öffnen?\n\n{WHOLE_COMPUTER}",
                                                     WHOLE_COMPUTER=tr(hostvpn.WHOLE_COMPUTER))) == QMessageBox.Yes:
            hostvpn.mac_open_app()
        return
    box = QMessageBox(QMessageBox.Information, tr("WireGuard für diesen Rechner"), hostvpn.intro(hostvpn.MAC_INTRO),
                      QMessageBox.Cancel, parent)
    go = box.addButton(tr("App Store öffnen"), QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is go:
        hostvpn.mac_open_store()
