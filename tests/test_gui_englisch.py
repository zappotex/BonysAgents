# SPDX-License-Identifier: GPL-3.0-or-later
"""Englische Oberfläche (offscreen): Hauptfenster und „Neuer Agent-PC“ zeigen keine deutschen Texte mehr.

Findet Texte, die nicht in ``tr()`` stehen oder deren Quelle nicht mit ``n_()`` markiert ist – der Katalog-Test in
test_i18n.py sieht nur, was schon in ``tr()`` steht."""

import json
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton, QApplication, QComboBox, QLabel, QListWidget, QMenu, QPushButton, QWidget,
)

from bonys_agents import i18n, updates, vm  # noqa: E402

# Umlaute, deutsche Anführungszeichen und häufige deutsche Wörter
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(der|die|das|und|nicht|mit|für|ist|wird|eine?|von|auf|oder|noch|bei|Kerne)\b")


@pytest.fixture
def app(datadir, monkeypatch):
    from bonys_agents.gui import style

    a = QApplication.instance() or QApplication([])
    monkeypatch.setattr(updates, "auto_check_due", lambda: False)
    style.apply(a)
    i18n.setzen(i18n.ENGLISCH)
    yield a
    i18n.setzen(i18n.DEUTSCH)   # andere Tests prüfen deutsche Texte
    for w in a.topLevelWidgets():
        w.close()
        w.deleteLater()
    a.processEvents()


def _fake_vm(name="agent1"):
    p = vm.vms_dir() / name
    p.mkdir(parents=True)
    cfg = vm.VMConfig(name=name, arch="x86_64", cpus=4, ram_mb=8192, apps=["brave", "telegram", "hermes", "xrdp"])
    (p / "vm.json").write_text(json.dumps(cfg.__dict__))
    return vm.VM(p)


def _menu_texts(menu: QMenu) -> list[str]:
    out = []
    for a in menu.actions():
        out.append(a.text())
        if a.menu():
            out += _menu_texts(a.menu())
    return out


def _texte(top: QWidget) -> list[str]:
    """Alle Texte, die man sehen kann – auch in Tooltips, Auswahllisten und Menüs."""
    out = [top.windowTitle()]
    for w in [top, *top.findChildren(QWidget)]:
        out.append(w.toolTip())
        if isinstance(w, (QLabel, QAbstractButton)):
            out.append(w.text())
        if isinstance(w, QPushButton) and w.menu():
            out += _menu_texts(w.menu())
        if isinstance(w, QComboBox):
            out += [w.itemText(i) for i in range(w.count())]
        if isinstance(w, QListWidget):
            out += [w.item(i).text() + " " + w.item(i).toolTip() for i in range(w.count())]
    return [t for t in out if t]


def _deutsch(texte: list[str]) -> list[str]:
    return sorted({t for t in texte if DEUTSCH.search(t)})


def test_hauptfenster_ist_englisch(app, monkeypatch):
    from bonys_agents.gui import main_window

    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    _fake_vm()
    w = main_window.MainWindow()
    w.timer.stop()
    w.show()
    w.list.setCurrentRow(0)
    app.processEvents()
    texte = _texte(w)
    assert "Start" in texte and "Shut down" in texte   # Detailseite des Agent-PCs
    assert any(t.startswith("●  stopped") for t in texte)   # Zustand aus vm.py, übersetzt beim Anzeigen
    assert _deutsch(texte) == []


def test_leere_liste_ist_englisch(app, monkeypatch):
    from bonys_agents.gui import main_window

    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    w = main_window.MainWindow()
    w.timer.stop()
    w.show()
    app.processEvents()
    assert "No Agent PC yet" in _texte(w)
    assert _deutsch(_texte(w)) == []


def test_neuer_agent_pc_ist_englisch(app):
    from bonys_agents import host
    from bonys_agents.gui.create_dialog import CreateDialog

    d = CreateDialog(host.detect())
    d.show()
    app.processEvents()
    texte = _texte(d)
    assert "Create and start" in texte and "German" in texte
    assert _deutsch(texte) == []
    d.done(0)


def test_deutsch_bleibt_deutsch(app, monkeypatch):
    from bonys_agents.gui import main_window

    i18n.setzen(i18n.DEUTSCH)
    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    _fake_vm()
    w = main_window.MainWindow()
    w.timer.stop()
    w.list.setCurrentRow(0)
    app.processEvents()
    texte = _texte(w)
    assert "Starten" in texte and any(t.startswith("●  gestoppt") for t in texte)


# Testdaten aus test_gui_layout (Kursnamen, Teilnehmer, Nachrichten) – kein Text der Oberfläche
TESTDATEN = re.compile(r"Teilnehmer(in)? \d+ mit langem Namen|Einführung in Hermes|Hermes antwortet nicht mehr|"
                       r"^Neu(\nNeu)*\n?$|sehr-langer-ordnername|Kurs mit langer Beschreibung")


def _kursinhalt() -> set[str]:
    """Namen der mitgelieferten Kurspakete – Inhalt, kein Text der Oberfläche (englische Kurspakete: Phase 5)."""
    from bonys_agents import kurspaket

    return {p.name for p in kurspaket.liste()}


def test_alle_dialoge_sind_englisch(app, monkeypatch):
    """Jeder Dialog aus der Layout-Prüfung, auf Englisch geöffnet: keine deutschen Texte (außer Testdaten)."""
    import test_gui_layout

    from bonys_agents.gui import main_window

    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    _fake_vm()
    w = main_window.MainWindow()
    w.timer.stop()
    w.list.setCurrentRow(0)
    inhalt = _kursinhalt()
    reste = {}
    for name, make in test_gui_layout._dialogs(w, monkeypatch).items():
        d = make()
        d.show()
        app.processEvents()
        deutsch = [t for t in _deutsch(_texte(d)) if not TESTDATEN.search(t) and not any(k in t for k in inhalt)]
        if deutsch:
            reste[name] = deutsch
        d.done(0)
        d.deleteLater()
    assert reste == {}
