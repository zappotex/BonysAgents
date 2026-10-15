# SPDX-License-Identifier: GPL-3.0-or-later
"""Oberfläche ohne Bildschirm (offscreen): Hauptfenster und Dialoge passen auf 800 × 550,
nichts wird abgeschnitten, Fensterzustand und Anzeigegröße werden gemerkt."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton, QApplication, QDialog, QLabel, QScrollArea, QWidget,
)

from bonys_agents import storage, updates, vm  # noqa: E402

SMALL = (800, 550)


@pytest.fixture
def app(datadir, monkeypatch):
    from bonys_agents.gui import style

    a = QApplication.instance() or QApplication([])
    monkeypatch.setattr(updates, "auto_check_due", lambda: False)
    # Lange Pfade ohne Leerzeichen (wie unter Windows) dürfen das Fenster nicht verbreitern
    deep = datadir.parent / ("sehr-langer-ordnername-ohne-leerzeichen-" * 3) / "noch-ein-ordner" / "home"
    monkeypatch.setattr(storage, "data_dir", lambda: deep)
    style.apply(a)
    yield a
    style.set_zoom(a, style.DEFAULT_ZOOM, save=False)
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


@pytest.fixture
def window(app, monkeypatch):
    from bonys_agents.gui import main_window

    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    _fake_vm()
    w = main_window.MainWindow()
    w.timer.stop()
    w.show()
    w.list.setCurrentRow(0)
    app.processEvents()
    return w


def _settle(app, widget, size):
    widget.resize(*size)
    for _ in range(3):
        app.processEvents()


def _widest(top: QWidget, n: int = 8) -> str:
    """Die breitesten sichtbaren Elemente – zeigt im Fehlerfall, was das Fenster aufspreizt."""
    rows = []
    for w in top.findChildren(QWidget):
        if w.isVisible():
            text = w.text()[:50] if isinstance(w, (QAbstractButton, QLabel)) else ""
            rows.append((w.minimumSizeHint().width(), w.minimumWidth(), type(w).__name__, w.objectName(), text))
    return "\n".join(map(str, sorted(rows, reverse=True)[:n]))


def _container(w: QWidget) -> QWidget:
    """Fläche, in der das Element vollständig liegen muss: Inhalt eines Bildlaufbereichs oder das Fenster."""
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QScrollArea):
            return p.widget()
        if p.isWindow():
            return p
        p = p.parentWidget()
    return w.window()


def _assert_nothing_cut(top: QWidget) -> None:
    """Jeder sichtbare Knopf und jedes Textfeld ist mindestens so groß wie nötig und liegt ganz in seiner Fläche."""
    for w in top.findChildren(QWidget):
        if not isinstance(w, (QAbstractButton, QLabel)) or not w.isVisibleTo(top) or not w.isVisible():
            continue
        if isinstance(w, QLabel) and not w.text():
            continue
        hint = w.minimumSizeHint()
        name = f"{type(w).__name__} „{getattr(w, 'text', lambda: '')()[:40]}“"
        assert w.width() >= hint.width(), f"{name} zu schmal: {w.width()} < {hint.width()}"
        if not (isinstance(w, QLabel) and w.wordWrap()):
            assert w.height() >= hint.height(), f"{name} zu niedrig: {w.height()} < {hint.height()}"
        box = _container(w)
        rect = QRect(w.mapTo(box, w.rect().topLeft()), w.size())
        assert box.rect().contains(rect), f"{name} ragt heraus: {rect} nicht in {box.rect()}"


# ---------------------------------------------------------------- Hauptfenster
def test_main_window_fits_800x550(app, window):
    hint = window.minimumSizeHint()
    assert hint.width() <= SMALL[0] and hint.height() <= SMALL[1], f"{hint}\n{_widest(window)}"
    assert window.minimumWidth() <= SMALL[0] and window.minimumHeight() <= SMALL[1]
    _settle(app, window, SMALL)
    assert (window.width(), window.height()) == SMALL
    _assert_nothing_cut(window)


@pytest.mark.parametrize("zoom", [80, 125, 150])
def test_main_window_fits_with_zoom(app, window, zoom):
    from bonys_agents.gui import style

    style.set_zoom(app, zoom, save=False)
    _settle(app, window, SMALL)
    hint = window.minimumSizeHint()
    assert hint.width() <= SMALL[0] and hint.height() <= SMALL[1], f"{hint}\n{_widest(window)}"
    _assert_nothing_cut(window)


def test_main_window_is_resizable_and_grabs(app, window, tmp_path):
    assert window.maximumWidth() > 4000 and window.maximumHeight() > 4000  # kein festes Maß, Maximieren geht
    for size in (SMALL, (1280, 800), (1920, 1080)):
        _settle(app, window, size)
        assert (window.width(), window.height()) == size
        _assert_nothing_cut(window)
        img = window.grab()
        assert not img.isNull() and img.width() >= size[0]


def test_start_size_is_80_percent_and_centered(app, window):
    from bonys_agents.gui.widgets import available_geometry

    avail = available_geometry()
    w = max(window.minimumWidth(), min(1400, int(avail.width() * 0.8)))
    h = max(window.minimumHeight(), min(900, int(avail.height() * 0.8)))
    assert (window.width(), window.height()) == (w, h)
    assert abs(window.geometry().center().x() - avail.center().x()) <= 4  # Fensterrahmen


def test_window_state_is_saved_and_restored(app, window):
    from bonys_agents.gui import main_window

    window.setGeometry(QRect(20, 30, 800, 560))
    window.splitter.setSizes([200, 600])
    app.processEvents()
    window.close()
    saved = storage.load_settings()["window"]
    assert (saved["w"], saved["h"]) == (800, 560) and saved["splitter"]

    again = main_window.MainWindow()
    again.timer.stop()
    assert (again.geometry().x(), again.geometry().y(), again.width(), again.height()) == (20, 30, 800, 560)
    assert again.splitter.sizes()[0] == window.splitter.sizes()[0]


def test_window_outside_all_screens_returns_to_primary(app, window):
    from bonys_agents.gui import main_window
    from bonys_agents.gui.widgets import available_geometry

    s = storage.load_settings()
    s["window"] = {"x": 9000, "y": 9000, "w": 900, "h": 600}  # zweiter Monitor abgesteckt
    storage.save_settings(s)
    w = main_window.MainWindow()
    w.timer.stop()
    assert available_geometry().contains(w.geometry())


# ---------------------------------------------------------------- Dialoge
def _fake_bundle(info):
    """Vorlage (nur im Speicher) und eine kleine .bonys-Datei für die Dialoge „Weitergeben“/„Importieren“."""
    import hashlib

    from bonys_agents import bonysfile, templates

    base = vm.vms_dir().parent / "bonys-test"
    base.mkdir(parents=True, exist_ok=True)
    tpl = templates.Template(path=base, name="kurs-vorlage", description="Kurs mit langer Beschreibung " * 4,
                             arch=info.arch, apps=["brave", "telegram", "obsidian", "hermes", "claude-code"],
                             personal_data_removed=False)
    disk = base / "disk.qcow2"
    disk.write_bytes(b"QFI\xfb" + b"\0" * 1020)
    m = bonysfile.build_manifest(tpl, creator="Kursleiterin mit einem langen Namen", version="1.0",
                                 disk_size=disk.stat().st_size,
                                 disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(),
                                 virtual_size=2**30, debian="13.1", versions={}, removed=["obsidian", "claude-code"])
    file = base / "kurs-vorlage-1.0.bonys"
    file.unlink(missing_ok=True)
    bonysfile.write_bundle(file, m, disk)
    return tpl, file, m


def _live_present(window, m, monkeypatch):
    """„Vorführen“ mit laufender Vorführung und Zuschauern (ohne echten Agent-PC, nur 127.0.0.1)."""
    from bonys_agents.trainer import present
    from bonys_agents.trainer.gui import present_dialog

    nov = vm.vms_dir().parent / "bonys-test" / "novnc"
    (nov / "core").mkdir(parents=True, exist_ok=True)
    (nov / "core" / "rfb.js").write_text("")
    monkeypatch.setattr(present, "novnc_dir", lambda: nov)
    monkeypatch.setattr(type(m), "is_running", lambda self: True)
    monkeypatch.setattr(type(m), "vnc_available", lambda self: True)
    monkeypatch.setattr(present, "for_vm", lambda machine, port=0, **kw: present.Presentation(
        machine.name, lambda: None, port=0, bind="127.0.0.1", advertise=False, novnc=nov, **kw))
    monkeypatch.setattr(present_dialog.QMessageBox, "exec", lambda self: present_dialog.QMessageBox.Ok)
    monkeypatch.setattr(present_dialog.QMessageBox, "question", lambda *a, **k: present_dialog.QMessageBox.Yes)
    d = present_dialog.PresentDialog(m, window)
    d._start()
    p = d.pres
    for i in range(6):
        p.viewers[str(i)] = present.Viewer(id=str(i), token_hash=str(i), name=f"Teilnehmerin Nummer {i}",
                                           address=f"192.168.178.{100 + i}", dropped_input=i)
    p.set_paused(True)
    d._refresh()
    d.finished.connect(lambda *_: p.stop())
    return d


def _live_helpdesk(window, m, monkeypatch):
    """„Hilfe-Anfragen“ mit laufendem Hilfe-Schalter und wartenden Teilnehmern (nur 127.0.0.1)."""
    import time

    from bonys_agents.trainer import helpdesk, present
    from bonys_agents.trainer.gui import helpdesk_dialog

    nov = vm.vms_dir().parent / "bonys-test" / "novnc"
    (nov / "core").mkdir(parents=True, exist_ok=True)
    (nov / "core" / "rfb.js").write_text("")
    hub = helpdesk_dialog.CourseHub.get()
    srv = present.Presentation(port=0, bind="127.0.0.1", advertise=False, novnc=nov)
    srv.start()
    hub.adopt(srv)
    for i in range(5):
        srv.helpdesk.sessions[str(i)] = helpdesk.HelpSession(
            id=str(i), name=f"Teilnehmer mit langem Namen {i}", vm=f"agent-pc-{i}", address=f"192.168.1.{i}",
            state=helpdesk.WAITING, message="Hermes antwortet nicht mehr seit dem Update " * 2,
            requested_at=time.time())
    d = helpdesk_dialog.HelpDeskDialog(window)
    d.finished.connect(lambda *_: srv.stop())
    return d


def _dialogs(window, monkeypatch):
    from bonys_agents import host
    from bonys_agents.gui import (
        about_dialog, create_dialog, desktop_dialog, install_dialog, main_window, move_dialog, remote_panel,
        resize_dialog, setup_dialog, template_dialogs, updates_ui,
    )

    # Nie wirklich installieren oder aktualisieren
    monkeypatch.setattr(updates_ui.InstallWorker, "start", lambda self: None)
    monkeypatch.setattr(updates_ui.UpgradeWorker, "start", lambda self: None)
    m = window.current()
    info = host.detect()
    up = updates.UpdateInfo(version="9.9.9", tag="v9.9.9", notes="Neu\n" * 40)
    tpl, bundle, manifest = _fake_bundle(info)
    from bonys_agents import edition, share
    from bonys_agents.gui import course_ui, share_dialogs

    monkeypatch.setattr(share, "discover", lambda timeout=2.5: [])  # keine echte Suche im Netz
    trainer = {}
    if edition.IS_TRAINER:
        from bonys_agents.trainer.gui import helpdesk_dialog, present_dialog, share_dialog

        trainer = {
            "Im Netzwerk freigeben": lambda: share_dialog.ShareDialog(tpl, window),
            "Vorführen": lambda: present_dialog.PresentDialog(m, window),
            "Vorführen (läuft)": lambda: _live_present(window, m, monkeypatch),
            "Hilfe-Anfragen": lambda: helpdesk_dialog.HelpDeskDialog(window),
            "Hilfe-Anfragen (läuft)": lambda: _live_helpdesk(window, m, monkeypatch),
        }
    return {
        **trainer,
        "Neuer Agent-PC": lambda: create_dialog.CreateDialog(info, window),
        "Einrichtung": lambda: setup_dialog.SetupDialog(info, window),
        "Verschieben": lambda: move_dialog.MoveDialog(m, window),
        "Festplatte": lambda: resize_dialog.ResizeDialog(m, window),
        "Als Vorlage speichern": lambda: template_dialogs.SaveTemplateDialog(m, window),
        "Vorlagen": lambda: template_dialogs.TemplatesDialog(window),
        "Weitergeben": lambda: template_dialogs.ExportDialog(tpl, window),
        "Importieren": lambda: template_dialogs.ImportDialog(bundle, manifest, window),
        "Schulung beitreten": lambda: share_dialogs.JoinDialog(window),
        "Hilfe anfordern": lambda: course_ui.HelpRequestDialog(m, window),
        "Importieren (andere Architektur)": lambda: template_dialogs.ImportDialog(
            bundle, {**manifest, "arch": "arm64" if info.arch == "x86_64" else "amd64"}, window),
        "Programme": lambda: install_dialog.InstallAppsDialog(m, window),
        "Desktop": lambda: desktop_dialog.AddDesktopDialog(m, window),
        "Über": lambda: about_dialog.AboutDialog(window),
        "Fernzugriff": lambda: remote_panel.RemoteDialog(m, False, window),
        "Was ist neu": lambda: updates_ui.ReleaseNotesDialog(up, window),
        "Update installieren": lambda: updates_ui.InstallDialog(up, [], window),
        "Agent-PC aktualisieren": lambda: updates_ui.UpgradeDialog([m], window),
        "Protokoll": lambda: main_window.LogDialog(m, [], window),
    }


def test_all_dialogs_fit_800x550(app, window, monkeypatch):
    from bonys_agents.gui.widgets import available_geometry

    avail = available_geometry()
    for name, make in _dialogs(window, monkeypatch).items():
        d: QDialog = make()
        d.show()
        app.processEvents()
        assert d.height() <= avail.height() and d.width() <= avail.width(), \
            f"{name}: {d.size()} größer als der Bildschirm {avail.size()}\n{_widest(d)}"
        hint = d.minimumSizeHint()
        assert hint.width() <= SMALL[0] and hint.height() <= SMALL[1], f"{name}: {hint}\n{_widest(d)}"
        assert d.maximumWidth() > 4000, f"{name}: Breite fest"
        _settle(app, d, SMALL)
        assert (d.width(), d.height()) == SMALL, name
        _assert_nothing_cut(d)
        d.reject() if not hasattr(d, "worker") else d.done(0)
        d.deleteLater()


def test_dialog_buttons_stay_outside_scroll_area(app, window, monkeypatch):
    """Inhalt scrollt, OK/Abbrechen bleiben immer sichtbar – auch im kleinsten Dialog."""
    for name, make in _dialogs(window, monkeypatch).items():
        d = make()
        scroll = d.findChild(QScrollArea)
        if scroll is None or scroll.parentWidget() is not d:
            d.deleteLater()
            continue
        d.show()
        _settle(app, d, (d.minimumSizeHint().width(), d.minimumSizeHint().height()))
        buttons = [b for b in d.findChildren(QAbstractButton) if b.isVisible() and not scroll.isAncestorOf(b)]
        assert buttons, f"{name}: keine Knöpfe außerhalb des Bildlaufbereichs"
        for b in buttons:
            r = QRect(b.mapTo(d, b.rect().topLeft()), b.size())
            assert d.rect().contains(r), f"{name}: {b.text()} nicht sichtbar"
        d.done(0)
        d.deleteLater()


# ---------------------------------------------------------------- Anzeigegröße
def test_zoom_scales_stylesheet_and_is_saved(app):
    from bonys_agents.gui import style

    assert style.saved_zoom() == 100
    assert "font-size: 14px" in style.stylesheet()
    style.set_zoom(app, 150)
    css = style.stylesheet()
    assert "font-size: 21px" in css and "border: 1px solid" in css  # Schrift wächst, dünne Linien bleiben
    assert app.styleSheet() == css
    assert storage.load_settings()["zoom"] == 150 and style.saved_zoom() == 150
    assert style.step_zoom(app, 1) == 150  # größer geht nicht
    assert style.step_zoom(app, -1) == 125
    assert style.step_zoom(app, 0) == 100
    assert style.set_zoom(app, 120) == 125  # nächstgelegene Stufe


def test_zoom_shortcuts(app, window):
    from PySide6.QtGui import QKeySequence

    assert QKeySequence("Ctrl+0") in window.zoom_reset.shortcuts()
    assert QKeySequence(QKeySequence.ZoomIn) in window.zoom_in.shortcuts()
    window.zoom_in.trigger()
    assert storage.load_settings()["zoom"] == 110
    assert [a.data() for a in window.zoom_group.actions() if a.isChecked()] == [110]
    window.zoom_out.trigger()
    window.zoom_out.trigger()
    assert storage.load_settings()["zoom"] == 90


# ---------------------------------------------------------------- Bausteine
def test_flow_layout_wraps(app):
    from PySide6.QtWidgets import QPushButton

    from bonys_agents.gui.widgets import FlowLayout

    host = QWidget()
    flow = FlowLayout(host)
    buttons = [QPushButton(f"Knopf Nummer {i}") for i in range(6)]
    for b in buttons:
        flow.addWidget(b)
    one_row = flow.heightForWidth(5000)
    narrow = flow.minimumSize().width()
    assert narrow == max(b.minimumSizeHint().width() for b in buttons) or narrow >= buttons[0].sizeHint().width()
    assert flow.heightForWidth(narrow) > one_row * 3


def test_column_layout_reduces_columns(app):
    from bonys_agents.gui.widgets import ColumnLayout

    host = QWidget()
    grid = ColumnLayout(host, columns=3, min_width=200)
    labels = [QLabel(f"Feld {i}") for i in range(6)]
    for lab in labels:
        grid.addWidget(lab)
    host.show()
    host.resize(900, grid.heightForWidth(900))
    app.processEvents()
    assert len({lab.y() for lab in labels}) == 2  # drei Spalten
    host.resize(300, grid.heightForWidth(300))
    app.processEvents()
    assert len({lab.y() for lab in labels}) == 6  # eine Spalte
    assert grid.minimumSize().width() < 200


def test_path_label_shortens_in_the_middle(app):
    from bonys_agents.gui.widgets import PathLabel

    path = "/media/nutzer/" + "x" * 200 + "/agent-pc-1"
    lab = PathLabel(path, prefix="Ort: ")
    assert lab.minimumSizeHint().width() < 120 < lab.sizeHint().width()
    lab.resize(260, 30)
    lab.show()
    app.processEvents()
    text = lab.text()  # Anfang und Ende bleiben, die Mitte wird „…“ – wie viel passt, hängt von der Schrift ab
    assert text.startswith("Ort: /") and text.endswith("1") and "…" in text and len(text) < len(path)
    assert lab.fontMetrics().horizontalAdvance(text) <= lab.width()
    assert lab.path() == path and lab.toolTip() == path
    lab.actions()[0].trigger()
    assert QApplication.clipboard().text() == path


def test_logo_does_not_force_size(app):
    from bonys_agents.gui.widgets import ScaledLogo

    logo = ScaledLogo(160)
    assert logo.minimumSizeHint().width() <= 1
    logo.resize(40, 40)
    logo.show()
    app.processEvents()
    assert not logo.grab().isNull()


@pytest.mark.parametrize("folder", ["Bony's Agents.app/Contents/Resources", 'Ordner "mit" Anführungszeichen'])
def test_stylesheet_survives_quotes_in_path(app, monkeypatch, tmp_path, folder):
    """macOS: alles liegt in „Bony's Agents.app“ – ein Apostroph im Pfad darf das Stylesheet nicht brechen."""
    from PySide6.QtCore import qInstallMessageHandler
    from PySide6.QtWidgets import QCheckBox

    from bonys_agents.gui import style

    monkeypatch.setattr(style, "resource", lambda name: tmp_path / folder / name)
    assert 'url("' in style.STYLESHEET  # das echte Stylesheet nutzt dieselbe Schreibweise
    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _ctx, msg: messages.append(msg))
    try:
        app.setStyleSheet(f"QCheckBox::indicator:checked {{ image: url({style._url('check.svg')}); }}")
        box = QCheckBox("Test")
        box.show()
        app.processEvents()
    finally:
        qInstallMessageHandler(previous)
        style.apply(app)
    assert not [m for m in messages if "parse" in m.lower()], messages
