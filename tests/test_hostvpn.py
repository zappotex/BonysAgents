# SPDX-License-Identifier: GPL-3.0-or-later
"""VPN auf dem eigenen Rechner: Bony's VPN öffnen/installieren (Linux), WireGuard unter Windows/macOS, .deb."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from bonys_agents import hostvpn, signing, updates, vpnlink

ROOT = Path(__file__).resolve().parent.parent
DL = f"https://github.com/{vpnlink.VPN_REPO}/releases/download"
LATEST = f"https://api.github.com/repos/{vpnlink.VPN_REPO}/releases/latest"


# ---------------------------------------------------------------- .deb von Bony's Agents
def test_build_deb_has_no_vpn_files_only_suggests():
    script = (ROOT / "packaging/linux/build-deb.sh").read_text()
    assert "Suggests: bonys-vpn," in script
    assert "vpn/install.py" not in script and "bonys-vpn.desktop" not in script
    assert "wireguard-tools" not in script and "rm -rf /etc/bonys-vpn" not in script
    # Update von 0.14 ohne Paket bonys-vpn: Kill-Switch vorher abschalten
    preinst = script.split('DEBIAN/preinst" <<\'EOF\'', 1)[1].split("\nEOF\n", 1)[0]
    assert "lt 0.15" in preinst and "killswitch off" in preinst and "bonys-vpn" in preinst
    assert "rm -rf /usr/lib/bonys-agents/vpn" in script
    assert not (ROOT / "src/bonys_agents/vpn").exists()
    assert "bonys_agents.vpn" not in (ROOT / "packaging/bonys-agents.spec").read_text()


# ---------------------------------------------------------------- Linux: Bony's VPN
def test_gui_command_and_installed_version(monkeypatch, tmp_path):
    monkeypatch.setattr(hostvpn, "GUI_PATH", tmp_path / "bonys-vpn-gui")
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: None)
    assert hostvpn.gui_command() is None and hostvpn.installed_version() is None
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: f"/usr/bin/{name}")
    assert hostvpn.gui_command() == "/usr/bin/bonys-vpn-gui"
    runs = []

    def run(cmd, **kw):
        runs.append(cmd)
        assert kw["env"] is not None
        return SimpleNamespace(returncode=0, stdout="installed 1.0.1")

    monkeypatch.setattr(hostvpn.subprocess, "run", run)
    assert hostvpn.installed_version() == "1.0.1"
    assert runs[0][:2] == ["dpkg-query", "-W"] and runs[0][-1] == "bonys-vpn"
    monkeypatch.setattr(hostvpn.subprocess, "run", lambda cmd, **kw: SimpleNamespace(returncode=0,
                                                                                     stdout="config-files 1.0.1"))
    assert hostvpn.installed_version() is None  # entfernt, nur Einstellungen übrig


def test_old_leftovers(monkeypatch, tmp_path):
    monkeypatch.setattr(hostvpn, "OLD_STATE", tmp_path / "killswitch.json")
    monkeypatch.setattr(hostvpn, "gui_command", lambda: None)
    assert not hostvpn.old_leftovers()
    (tmp_path / "killswitch.json").write_text("{}")
    assert hostvpn.old_leftovers()
    monkeypatch.setattr(hostvpn, "gui_command", lambda: "/usr/bin/bonys-vpn-gui")
    assert not hostvpn.old_leftovers()


def test_install_from_apt_source(monkeypatch):
    scripts = []
    monkeypatch.setattr(hostvpn, "apt_configured", lambda: True)
    monkeypatch.setattr(hostvpn, "installed_version", lambda: "1.0.1")
    v = hostvpn.install(print, runner=lambda s: scripts.append(s) or 0,
                        opener=lambda *a, **k: pytest.fail("ohne GitHub"))
    assert v == "1.0.1" and "apt-get install -y bonys-vpn" in scripts[0]
    monkeypatch.setattr(hostvpn, "installed_version", lambda: None)
    with pytest.raises(hostvpn.HostVpnError, match="abgebrochen"):
        hostvpn.install(print, runner=lambda s: 126)


class _Resp(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url
        self.headers = {"Content-Length": str(len(data))}

    def geturl(self):
        return self.url


def _opener(routes: dict):
    def opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if url not in routes:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        v = routes[url]
        return _Resp(v if isinstance(v, bytes) else json.dumps(v).encode(), url)
    return opener


@pytest.fixture
def vpn_release(monkeypatch):
    """Release von bonys-vpn mit SHA256SUMS + minisign-Signatur (Testschlüssel)."""
    secret, key_id = b"\x33" * 32, b"VPNTEST1"
    public = signing.PublicKey(key_id, signing.ed25519_public_key(secret)).text()
    monkeypatch.setattr(updates, "UPDATE_PUBLIC_KEY", public)
    real = updates.download_verified
    monkeypatch.setattr(updates, "download_verified",
                        lambda *a, **kw: real(*a, **{**kw, "public_key": public}))
    debs = {"bonys-vpn_1.0.1_all.deb": b"vpn" * 500, "bonys-vpn-agentpc_1.0.1_all.deb": b"agentpc" * 50}
    sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in debs.items()).encode()
    routes = {f"{DL}/v1.0.1/{n}": d for n, d in debs.items()}
    routes[f"{DL}/v1.0.1/SHA256SUMS"] = sums
    routes[f"{DL}/v1.0.1/SHA256SUMS.minisig"] = signing.sign(sums, secret, key_id, "Bony's VPN v1.0.1").encode()
    routes[LATEST] = {"tag_name": "v1.0.1", "draft": False, "prerelease": False,
                      "assets": [{"name": u.rsplit("/", 1)[1], "browser_download_url": u, "size": 1}
                                 for u in list(routes)]}
    return routes, (secret, key_id)


def test_install_from_signed_release(monkeypatch, vpn_release):
    routes, _ = vpn_release
    monkeypatch.setattr(hostvpn, "apt_configured", lambda: False)
    monkeypatch.setattr(hostvpn, "deb_arch", lambda: "amd64")
    monkeypatch.setattr(hostvpn, "installed_version", lambda: None)
    seen = []

    def runner(script):
        deb = Path(script.split("apt-get install -y ", 1)[1].strip().strip("'"))
        seen.append((deb.name, deb.read_bytes()))
        return 0

    assert hostvpn.install(print, opener=_opener(routes), runner=runner) == "1.0.1"
    assert seen == [("bonys-vpn_1.0.1_all.deb", b"vpn" * 500)]  # nur das Paket für den eigenen Rechner


def test_install_aborts_on_bad_checksum_or_signature(monkeypatch, vpn_release):
    routes, (secret, key_id) = vpn_release
    monkeypatch.setattr(hostvpn, "apt_configured", lambda: False)
    monkeypatch.setattr(hostvpn, "deb_arch", lambda: "arm64")
    never = lambda s: pytest.fail("darf nicht installieren")  # noqa: E731
    bad = dict(routes)
    bad[f"{DL}/v1.0.1/bonys-vpn_1.0.1_all.deb"] = b"manipuliert"
    with pytest.raises(hostvpn.HostVpnError, match="Prüfsumme"):
        hostvpn.install(print, opener=_opener(bad), runner=never)
    old = dict(routes)
    old[f"{DL}/v1.0.1/SHA256SUMS.minisig"] = signing.sign(routes[f"{DL}/v1.0.1/SHA256SUMS"], secret, key_id,
                                                           "Bony's VPN v1.0.0").encode()
    with pytest.raises(hostvpn.HostVpnError, match="anderen Version"):
        hostvpn.install(print, opener=_opener(old), runner=never)
    with pytest.raises(hostvpn.HostVpnError, match="GitHub ist nicht erreichbar|kein Release"):
        hostvpn.install(print, opener=_opener({}), runner=never)


def test_open_app(monkeypatch):
    monkeypatch.setattr(hostvpn, "gui_command", lambda: None)
    with pytest.raises(hostvpn.HostVpnError, match="nicht installiert"):
        hostvpn.open_app()
    started = []
    monkeypatch.setattr(hostvpn, "gui_command", lambda: "/usr/bin/bonys-vpn-gui")
    monkeypatch.setattr(hostvpn.subprocess, "Popen", lambda cmd, **kw: started.append((cmd, kw)))
    hostvpn.open_app()
    assert started[0][0] == ["/usr/bin/bonys-vpn-gui"] and started[0][1]["start_new_session"]


# ---------------------------------------------------------------- Windows / macOS
def test_windows_app_and_winget(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    for var in ("ProgramW6432", "ProgramFiles(x86)"):
        monkeypatch.delenv(var, raising=False)
    assert hostvpn.windows_app() is None
    calls = []
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: None)
    with pytest.raises(hostvpn.HostVpnError, match="winget fehlt"):
        hostvpn.windows_install()
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: "C:/winget.exe")

    def run(cmd, **kw):
        calls.append(cmd)
        exe = tmp_path / "WireGuard" / "wireguard.exe"
        exe.parent.mkdir(exist_ok=True)
        exe.write_text("")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hostvpn.subprocess, "run", run)
    hostvpn.windows_install()
    assert calls == [hostvpn.WINGET_INSTALL]
    assert calls[0][:5] == ["winget", "install", "--id", "WireGuard.WireGuard", "-e"]
    assert hostvpn.windows_app() == tmp_path / "WireGuard" / "wireguard.exe"


def test_mac_opens_app_store(monkeypatch):
    calls = []
    monkeypatch.setattr(hostvpn.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=1 if len(calls) == 1 else 0))
    hostvpn.mac_open_store()
    assert calls == [["open", "macappstore://apps.apple.com/app/id1451685025"],
                     ["open", "https://apps.apple.com/app/wireguard/id1451685025"]]
    assert "nur im App Store" in hostvpn.MAC_INTRO and hostvpn.WHOLE_COMPUTER in hostvpn.MAC_INTRO
    assert hostvpn.WHOLE_COMPUTER in hostvpn.WINDOWS_INTRO


# ---------------------------------------------------------------- Oberfläche
@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class FakeBox:
    """QMessageBox ohne Fenster: „Installieren“ bzw. „Ja“ wird gewählt."""

    Information = Warning = Cancel = AcceptRole = Yes = No = 0
    shown: list[str] = []

    def __init__(self, _icon, title, text, *_a):
        FakeBox.shown.append(text)
        self.go = object()

    def setTextFormat(self, _f):  # noqa: N802
        pass

    def addButton(self, *_a):  # noqa: N802
        return self.go

    def button(self, _which):
        return SimpleNamespace(setText=lambda _t: None)

    def exec(self):
        pass

    def clickedButton(self):  # noqa: N802
        return self.go

    @staticmethod
    def question(*_a):
        return FakeBox.Yes

    @staticmethod
    def warning(_p, _t, text):
        FakeBox.shown.append(text)

    information = warning


def test_linux_button_opens_or_installs(qapp, monkeypatch):
    from bonys_agents.gui import host_vpn

    FakeBox.shown = []
    monkeypatch.setattr(host_vpn, "QMessageBox", FakeBox)
    opened = []
    monkeypatch.setattr(hostvpn, "open_app", lambda: opened.append(1))
    monkeypatch.setattr(hostvpn, "gui_command", lambda: "/usr/bin/bonys-vpn-gui")
    assert host_vpn.linux_vpn(None) is None and opened == [1]
    assert host_vpn.button_text() == "Bony's VPN öffnen"
    # nicht installiert: Rückfrage, dann Installation im Hintergrund
    monkeypatch.setattr(hostvpn, "gui_command", lambda: None)
    monkeypatch.setattr(hostvpn, "can_install", lambda: True)
    monkeypatch.setattr(hostvpn, "old_leftovers", lambda: True)
    monkeypatch.setattr(hostvpn, "install", lambda log: "1.0.1")
    assert host_vpn.button_text() == "Bony's VPN installieren"
    w = host_vpn.linux_vpn(None)
    w.wait(5000)
    assert w.result == "1.0.1"
    assert hostvpn.LINUX_INTRO in FakeBox.shown[0] and hostvpn.OLD_INSTALL_HINT in FakeBox.shown[0]


def test_main_window_vpn_button(qapp, datadir, monkeypatch):
    from bonys_agents import deps
    from bonys_agents.gui import main_window

    monkeypatch.setattr(deps, "check", lambda info: SimpleNamespace(ok=True))
    monkeypatch.setattr(main_window.updates, "auto_check_due", lambda: False)
    monkeypatch.setattr(hostvpn, "gui_command", lambda: None)
    win = main_window.MainWindow()
    try:
        win.timer.stop()
        assert win.vpn_btn.isHidden() == (not sys.platform.startswith("linux"))
        assert not win.vpn_btn.isCheckable() and "installieren" in win.vpn_btn.toolTip()
        extras = next(a.menu() for a in win.about_btn.menu().actions() if a.menu() and a.text() == "Extras")
        expected = {"win32": ["WireGuard für diesen Rechner installieren …"],
                    "darwin": ["WireGuard für diesen Rechner (App Store) …"]}.get(
            sys.platform, ["Bony's VPN für diesen Rechner"])
        assert [a.text() for a in extras.actions()] == expected
        called = []
        monkeypatch.setattr(main_window, "linux_vpn", lambda parent: called.append(parent))
        win.vpn_btn.click()
        assert called == [win]
        assert not hasattr(win, "vpn_mode")  # kein eigener VPN-Bereich mehr im Fenster
    finally:
        win.timer.stop()
        win.close()


def test_hostvpn_uses_clean_env_everywhere():
    src = (ROOT / "src/bonys_agents/hostvpn.py").read_text()
    for call in ("subprocess.run(", "subprocess.Popen("):
        for chunk in src.split(call)[1:]:
            assert "env=clean_env()" in chunk.split("\n\n")[0][:300], chunk[:120]
    assert subprocess  # (Import für die Prüfung oben)
