# SPDX-License-Identifier: GPL-3.0-or-later
"""Zwei Editionen aus einem Quellcode: Anwender-Version ohne ``bonys_agents.trainer``, Kursleiter-Version mit.

Läuft in beiden Test-Runden (``pytest --edition anwender|kursleiter``) und prüft jeweils, was die Edition können muss.
"""

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import __version__, cli, edition

SRC = Path(__file__).resolve().parent.parent / "src" / "bonys_agents"


def test_edition_matches_test_run(request):
    wanted = request.config.getoption("--edition")
    assert edition.EDITION == wanted
    assert edition.IS_TRAINER == (wanted == "kursleiter")
    assert edition.NAME == ("Bony's Agents Kursleiter" if edition.IS_TRAINER else "Bony's Agents")
    assert edition.PACKAGE == ("bonys-agents-kursleiter" if edition.IS_TRAINER else "bonys-agents")
    if not edition.IS_TRAINER:
        assert not edition.trainer_available()
        with pytest.raises(ImportError):
            import bonys_agents.trainer  # noqa: F401


def test_version_shows_edition(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"bonys-agents {__version__} ({edition.LABEL})"


def test_trainer_commands_only_in_trainer_edition(capsys):
    if edition.IS_TRAINER:
        a = cli.build_parser().parse_args(["present", "pc", "--quality", "high"])
        assert a.quality == "high"
        return
    for argv in (["share", "kurs", "--port", "1"], ["present", "pc"]):
        assert cli.main(argv) == 2
        err = capsys.readouterr().err
        assert "nur in „Bony's Agents Kursleiter“" in err and "join" in err and "releases" in err


def test_doctor_names_edition(capsys, monkeypatch):
    from types import SimpleNamespace

    from bonys_agents import host

    monkeypatch.setattr(host, "detect", lambda: SimpleNamespace())   # nach der ersten Zeile abbrechen
    with pytest.raises(AttributeError):
        cli.cmd_doctor(SimpleNamespace())
    assert capsys.readouterr().out.splitlines()[0] == f"{edition.NAME} {__version__} (Edition: {edition.LABEL})"


def _top_level_imports(tree: ast.Module) -> list[str]:
    names = []
    for node in tree.body:   # nur Modul-Ebene – Importe in Funktionen laufen erst bei Bedarf
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module + "." + ",".join(a.name for a in node.names))
    return names


def test_main_package_never_imports_trainer_at_module_level():
    bad = []
    for f in SRC.rglob("*.py"):
        if "trainer" in f.relative_to(SRC).parts:
            continue
        for name in _top_level_imports(ast.parse(f.read_text("utf-8"))):
            if "trainer" in name.split("."):
                bad.append(f"{f.relative_to(SRC)}: {name}")
    assert bad == []


def test_trainer_package_contains_server_and_novnc_paths():
    """Alles, was nur der Kursleiter braucht, liegt unter trainer/ – das Bauen lässt den Ordner einfach weg."""
    for rel in ("trainer/share_server.py", "trainer/present.py", "trainer/helpdesk.py", "trainer/announce.py",
                "trainer/cli.py", "trainer/gui/present_dialog.py", "trainer/resources/present/view.html"):
        assert (SRC / rel).is_file(), rel
    assert not (SRC / "resources" / "novnc").exists() and not (SRC / "resources" / "present").exists()
    for f in SRC.rglob("*.py"):
        if "trainer" in f.relative_to(SRC).parts:
            continue
        text = f.read_text("utf-8")
        assert "ThreadingHTTPServer" not in text and not re.search(r"[\"']novnc[\"']", text), f


def test_main_package_works_without_trainer_folder(tmp_path):
    """Kopie des Pakets OHNE trainer/ (wie in der gebauten Anwender-Version): alle Module importierbar, CLI läuft,
    Hauptfenster entsteht ohne Kursleiter-Knöpfe."""
    pkg = tmp_path / "src" / "bonys_agents"
    shutil.copytree(SRC, pkg, ignore=shutil.ignore_patterns("trainer", "__pycache__", "_edition.py"))
    shutil.copytree(SRC.parent / "bony_netz", pkg.parent / "bony_netz", ignore=shutil.ignore_patterns("__pycache__"))
    home = tmp_path / "home"
    script = r'''
import importlib, io, pkgutil, sys, contextlib
import bonys_agents
from bonys_agents import edition
assert edition.EDITION == "anwender" and not edition.IS_TRAINER, edition.EDITION
mods = [m.name for m in pkgutil.walk_packages(bonys_agents.__path__, "bonys_agents.")]
assert not [m for m in mods if ".trainer" in m], mods
for m in mods:
    if m.endswith("__main__"):
        continue
    importlib.import_module(m)
from bonys_agents import cli
err = io.StringIO()
with contextlib.redirect_stderr(err):
    assert cli.main(["present", "pc"]) == 2
assert "Kursleiter" in err.getvalue()
from bonys_agents import storage
storage.data_dir = lambda: __import__("pathlib").Path(sys.argv[1])
storage._partitions = lambda: []
from PySide6.QtWidgets import QApplication, QPushButton
app = QApplication([])
from bonys_agents.gui import main_window, template_dialogs, about_dialog
w = main_window.MainWindow()
texts = [b.text() for b in w.findChildren(QPushButton)]
assert "Vorführen …" not in texts and w.present_btn is None, texts
menu = [a.text() for a in w.about_btn.menu().actions()]
assert not [t for t in menu if "Kursleitung" in t], menu
assert not [t for t in menu if "Moderation" in t], menu
assert [t for t in menu if "Schulungen geben" in t], menu
assert "Hilfe anfordern …" in texts and "Kurse" in texts
from bonys_agents.gui import kurse_dialog
k = kurse_dialog.KurseDialog(w)
tabs = [k.tabs.tabText(i) for i in range(k.tabs.count())]
assert tabs == ["Kurspakete", "Teilnahme"], "Kursleitung in der Anwender-Version"
d = template_dialogs.TemplatesDialog(w)
assert d.share_btn is None and "Im Netzwerk freigeben …" not in [b.text() for b in d.findChildren(QPushButton)]
a = about_dialog.AboutDialog(w)
print("OK", len(mods))
'''
    env = {k: v for k, v in os.environ.items() if k not in ("BONYS_AGENTS_EDITION", "PYTHONPATH")}
    env.update(PYTHONPATH=str(pkg.parent), QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", script, str(home)], capture_output=True, text=True, env=env,
                       cwd=tmp_path, timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().startswith("OK")


def test_trainer_controls_match_edition(datadir, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from bonys_agents import vm
    from bonys_agents.gui import main_window, template_dialogs

    monkeypatch.setattr(vm, "list_vms", lambda: [])
    app = QApplication.instance() or QApplication([])
    w = main_window.MainWindow()
    menu = [a.text() for a in w.about_btn.menu().actions()]
    d = template_dialogs.TemplatesDialog(w)
    try:
        assert (w.present_btn is not None) == edition.IS_TRAINER
        assert (d.share_btn is not None) == edition.IS_TRAINER
        assert any("Kursleitung" in t for t in menu) == edition.IS_TRAINER
        assert any("Moderation" in t for t in menu) == edition.IS_TRAINER
        assert any("Schulungen geben" in t for t in menu) == (not edition.IS_TRAINER)
        assert w.windowTitle() == edition.NAME
    finally:
        d.close()
        w.close()
        app.processEvents()
