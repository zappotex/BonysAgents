# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from bonys_agents import vm


@pytest.fixture
def datadir(tmp_path, monkeypatch):
    from bonys_agents import storage
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
