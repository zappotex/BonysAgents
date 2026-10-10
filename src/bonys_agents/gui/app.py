# SPDX-License-Identifier: GPL-3.0-or-later
"""Startpunkt der Desktop-App."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from bonys_agents import APP_NAME, procutil

from . import style


def run() -> int:
    procutil.add_homebrew_to_path()
    # Hohe Auflösungen / Windows-Skalierung 125 % oder 150 %: Faktor exakt übernehmen statt runden.
    # Muss vor dem Anlegen der QApplication gesetzt werden.
    if QApplication.instance() is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    style.apply(app)
    app.setWindowIcon(QIcon(str(style.resource("logo.png"))))

    if "--vpn" in sys.argv[1:]:
        # Desktop-Eintrag „Bony's VPN“: nur Bony's VPN für diesen Rechner (läuft im Infobereich weiter)
        from .host_vpn import HostVpnWindow

        app.setApplicationName("Bony's VPN")
        app.setDesktopFileName("bonys-vpn")
        app.setQuitOnLastWindowClosed(False)
        win = HostVpnWindow()
        win.destroyed.connect(app.quit)
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.show()
        return app.exec()

    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
