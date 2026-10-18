# SPDX-License-Identifier: GPL-3.0-or-later
"""Gemeinsame Test-Hilfen – und die Wahl der Edition.

``pytest --edition anwender`` testet die Anwender-Version: ``bonys_agents.trainer`` lässt sich dann gar nicht
importieren (wie im gebauten Paket, in dem es fehlt), Tests mit ``@pytest.mark.kursleiter`` werden übersprungen.
Ohne Angabe (bzw. ``--edition kursleiter``) läuft alles.
"""

import importlib.abc
import os
import sys

import pytest

EDITION_ENV = "BONYS_AGENTS_EDITION"
# Diese Test-Dateien prüfen nur Kursleiter-Server (Vorführung, Hilfe-Schalter) – in der Anwender-Runde weglassen
TRAINER_ONLY_FILES = {"test_present.py", "test_helpmode.py", "test_share_server.py"}


def pytest_addoption(parser):
    parser.addoption("--edition", choices=["kursleiter", "anwender"], default=os.environ.get(EDITION_ENV) or
                     "kursleiter", help="Welche Edition getestet wird (Standard: kursleiter = alles)")


class _NoTrainer(importlib.abc.MetaPathFinder):
    """Tut so, als fehle ``bonys_agents.trainer`` – wie in der gebauten Anwender-Version."""

    def find_spec(self, name, path=None, target=None):
        if name == "bonys_agents.trainer" or name.startswith("bonys_agents.trainer."):
            raise ModuleNotFoundError(f"No module named {name!r} (Anwender-Version)", name=name)
        return None


def pytest_configure(config):
    config.addinivalue_line("markers", "kursleiter: nur in der Kursleiter-Version (braucht bonys_agents.trainer)")
    edition = config.getoption("--edition")
    os.environ[EDITION_ENV] = edition
    if edition == "anwender":
        if any(m == "bonys_agents.edition" or m.startswith("bonys_agents.trainer") for m in sys.modules):
            raise pytest.UsageError("bonys_agents.edition wurde vor der Wahl der Edition importiert.")
        sys.meta_path.insert(0, _NoTrainer())


def pytest_ignore_collect(collection_path, config):
    if config.getoption("--edition") == "anwender" and collection_path.name in TRAINER_ONLY_FILES:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    if config.getoption("--edition") != "anwender":
        return
    skip = pytest.mark.skip(reason="nur Kursleiter-Version")
    for item in items:
        if "kursleiter" in item.keywords:
            item.add_marker(skip)


def pytest_report_header(config):
    return f"Edition: {config.getoption('--edition')}"


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    from bonys_agents import storage, vm

    home = tmp_path / "home"
    monkeypatch.setattr(storage, "data_dir", lambda: home)
    monkeypatch.setattr(storage, "_partitions", lambda: [])  # echte Laufwerke ignorieren
    storage.invalidate_cache()
    # Nie echte Remmina-Profile im Home-Ordner anfassen, keinen echten QEMU-Probelauf starten
    from bonys_agents import remote
    monkeypatch.setattr(remote, "remmina_dirs", lambda native=None, flatpak=None: [])
    monkeypatch.setattr(vm.VM, "capabilities", lambda self: {"spice": True, "audio": ["pipewire", "spice"]})
    monkeypatch.setattr(remote, "port_free", lambda port: True)
    return home


@pytest.fixture(autouse=True)
def _no_update_consent_question(monkeypatch):
    """Keine Rückfrage „nach Updates suchen?“ mitten in einem Test (ein Hauptfenster sucht nach 3 s automatisch).
    Der Test der Rückfrage selbst nutzt ``REAL_NEEDS_CONSENT``."""
    from bonys_agents import updates

    global REAL_NEEDS_CONSENT
    REAL_NEEDS_CONSENT = REAL_NEEDS_CONSENT or updates.needs_consent
    monkeypatch.setattr(updates, "needs_consent", lambda: False)


REAL_NEEDS_CONSENT = None


@pytest.fixture(autouse=True)
def _kein_einrichtungsassistent(monkeypatch):
    """Fehlt QEMU (z. B. auf dem Windows-Runner), öffnet ein Hauptfenster nach 300 ms den Einrichtungs-Assistenten
    modal (``exec``) – ein Test, der danach Ereignisse abarbeitet, hinge dort bis zum Zeitlimit."""
    try:
        from bonys_agents.gui import main_window
    except ImportError:   # ohne Qt
        return
    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)


@pytest.fixture(autouse=True)
def _no_network_for_mission_control(monkeypatch):
    """Mindestwerte von Mission Control nie wirklich aus dem Internet laden (Dialoge tun das im Hintergrund)."""
    from bonys_agents import mission_control

    def offline(url, timeout):
        raise OSError("kein Netz im Test")

    monkeypatch.setattr(mission_control, "_download", offline)
    monkeypatch.setattr(mission_control, "_cache", None)


@pytest.fixture(autouse=True)
def _own_bony_netz_folder(tmp_path, monkeypatch):
    """Nie die echte Bony-Netz-Anmeldung (~/.config/bonys-netz/konto.json) lesen oder überschreiben."""
    monkeypatch.setenv("BONY_NETZ_ORDNER", str(tmp_path / "bony-netz"))


@pytest.fixture(autouse=True)
def _kein_echtes_tailscale(monkeypatch):
    """Hilfe-Funktion: Tests fragen nie Tailscale auf diesem Rechner (der Kursstart hinge sonst an dessen Zustand).
    ``None`` = nicht installiert; Tests mit eigenem Zustand übergeben ihn direkt."""
    monkeypatch.setattr("bonys_agents.hilfe.tailscale_status", lambda run=None: None)
