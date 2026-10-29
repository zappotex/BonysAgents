# SPDX-License-Identifier: GPL-3.0-or-later
"""Startpunkt der Desktop-App."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from bonys_agents import APP_NAME, crashlog, edition, i18n, procutil
from bonys_agents.i18n import tr

from . import style


def install_german(app: QApplication) -> bool:
    """Qt-eigene Texte deutsch: „Ja/Nein“, „Abbrechen“, Kontextmenüs („Kopieren“, „Einfügen“), Dateidialoge."""
    qt_de = QTranslator(app)   # Elternobjekt: lebt so lange wie die App
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_de.load(QLocale(QLocale.German, QLocale.Germany), "qtbase", "_", folder):
        app.installTranslator(qt_de)
        return True
    return False


def _show_error(text: str) -> None:
    QMessageBox.critical(QApplication.activeWindow(), tr("Unerwarteter Fehler"), text)


def run() -> int:
    crashlog.install(show=_show_error)
    procutil.add_homebrew_to_path()
    # Hohe Auflösungen / Windows-Skalierung 125 % oder 150 %: Faktor exakt übernehmen statt runden.
    # Muss vor dem Anlegen der QApplication gesetzt werden.
    if QApplication.instance() is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        # Kursraum (Qt WebEngine): eigenes Schema kursraum:// – geht nur vor dem Anlegen der QApplication
        from .kursraum_fenster import vorbereiten

        vorbereiten()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)   # gleich in beiden Editionen (Einstellungen bleiben beim Wechsel)
    app.setApplicationDisplayName(edition.NAME)
    # Sprache vor allen Fenstern festlegen; Englisch braucht keine Qt-Übersetzung (Qt ist englisch)
    if i18n.starten(QLocale.system().name()) == i18n.DEUTSCH:
        install_german(app)
    style.apply(app)
    app.setWindowIcon(QIcon(str(style.resource("logo.png"))))

    if "--vpn" in sys.argv[1:]:
        # Früher: eigenes Fenster „Bony's VPN“. Heute ist Bony's VPN ein eigenes Programm.
        from bonys_agents import hostvpn

        if hostvpn.gui_command():
            hostvpn.open_app()
            return 0

    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


def main() -> None:
    try:
        code = run()
    except Exception as e:  # noqa: BLE001 – App startet nicht: protokollieren und, wenn möglich, melden
        path = crashlog.write(type(e), e, e.__traceback__, where="Start")
        try:
            QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, tr("Bony's Agents startet nicht"),
                                 tr("{fehler}\n\nEinzelheiten: {pfad}", fehler=crashlog.short(e), pfad=path))
        except Exception:  # noqa: BLE001
            pass
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
