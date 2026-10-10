# SPDX-License-Identifier: GPL-3.0-or-later
"""WireGuard auf dem eigenen Rechner: Paket-Layout, polkit, hostvpn, Qt-Bereich, Windows/macOS."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bonys_agents import hostvpn
from bonys_agents.vpn import cli as vpncli
from bonys_agents.vpn import install as vpninstall

ROOT = Path(__file__).resolve().parent.parent
KEY = base64.b64encode(bytes(range(1, 33))).decode()
PEER = base64.b64encode(bytes(range(33, 65))).decode()
# Helfer (fcntl, pwd), Dateirechte und wg/nft gibt es nur unter Linux
linux_only = pytest.mark.skipif(sys.platform != "linux", reason="nur unter Linux")
CONF = (f"[Interface]\nPrivateKey = {KEY}\nAddress = 10.8.0.2/32\nDNS = 10.8.0.1\n\n"
        f"[Peer]\nPublicKey = {PEER}\nAllowedIPs = 0.0.0.0/0\nEndpoint = vpn.example.net:51820\n")
STATUS = {
    "tunnels": [
        {"name": "heim", "active": True, "autostart": True, "managed": True, "addresses": ["10.8.0.2/32"],
         "dns": ["10.8.0.1"], "peers": [{"endpoint": "vpn.example.net:51820"}], "handshake": 1, "rx": 2048,
         "tx": 1024},
        {"name": "fremd", "active": False, "autostart": False, "managed": False, "addresses": ["10.9.0.2/32"],
         "peers": []},
    ],
    "active": "heim",
    "killswitch": {"enabled": False, "active": False, "exceptions": []},
}


# ---------------------------------------------------------------- Paket und polkit
@linux_only
def test_system_layout_for_deb(tmp_path):
    written = vpninstall.install("host", root=tmp_path, as_root=False, layout="system")
    rel = {str(p.relative_to(tmp_path)) for p in written}
    assert "usr/sbin/bonys-vpn-helper" in rel and "usr/bin/bonys-vpn" in rel
    assert "usr/lib/bonys-agents/vpn/bonys_vpn/helper.py" in rel
    assert "usr/lib/systemd/system/bonys-vpn-killswitch.service" in rel
    assert "usr/share/polkit-1/rules.d/50-bonys-vpn.rules" in rel
    assert not any(r.startswith("etc/") or "usr/local" in r or r.endswith("gui.py") for r in rel)
    assert not (tmp_path / "etc").exists()  # keine Conffiles, der Helfer legt /etc/bonys-vpn selbst an
    helper = (tmp_path / "usr/sbin/bonys-vpn-helper")
    assert helper.read_text().startswith("#!/usr/bin/python3 -I")
    assert '"/usr/lib/bonys-agents/vpn"' in helper.read_text() and os.access(helper, os.X_OK)
    policy = (tmp_path / vpninstall.POLICY).read_text()
    assert policy.count("<annotate key=\"org.freedesktop.policykit.exec.path\">/usr/sbin/bonys-vpn-helper<") == 1
    rules = (tmp_path / "usr/share/polkit-1/rules.d/50-bonys-vpn.rules").read_text()
    assert "AUTH_ADMIN_KEEP" in rules and "@" not in rules.replace("@HELPER@", "")
    # ohne Passwort nur genau „status“ ohne weitere Argumente
    assert 'action.lookup("command_line") == "/usr/sbin/bonys-vpn-helper status"' in rules
    assert rules.count("Result.YES") == 1
    with pytest.raises(ValueError):
        vpninstall.install("agent", root=tmp_path, as_root=False, layout="system")
    assert vpninstall.main(["--layout", "system"]) == 1  # nie direkt ins System


def test_policy_and_host_rules():
    """pkexec nimmt die erste Aktion mit passendem Pfad – eine zweite Aktion mit exec.argv1 griffe nie.
    Status ohne Passwort geht deshalb über die Regel (command_line), die Aktion bleibt eine."""
    import xml.dom.minidom

    doc = xml.dom.minidom.parse(str(ROOT / "src/bonys_agents/vpn/data/io.github.bonys-agents.vpn.policy"))
    actions = doc.getElementsByTagName("action")
    assert [a.getAttribute("id") for a in actions] == ["io.github.bonys-agents.vpn"]
    d = actions[0].getElementsByTagName("defaults")[0]
    assert d.getElementsByTagName("allow_active")[0].firstChild.data == "auth_admin_keep"
    rules = (ROOT / "src/bonys_agents/vpn/data/host.rules").read_text()
    assert "subject.local && subject.active && action.lookup(\"command_line\") == \"@HELPER@ status\"" in rules
    agent = (ROOT / "src/bonys_agents/vpn/data/agent.rules").read_text()
    assert "command_line" not in agent


def test_build_deb_contains_vpn_parts():
    s = (ROOT / "packaging/linux/build-deb.sh").read_text()
    assert "--variant host --layout system" in s and "bonys-vpn.desktop" in s
    recommends = next(line for line in s.splitlines() if line.startswith("Recommends:"))
    assert "wireguard-tools" in recommends and "nftables" in recommends
    depends = next(line for line in s.splitlines() if line.startswith("Depends:"))
    assert "wireguard" not in depends and "python3" in depends
    assert "killswitch off" in s  # prerm: beim Entfernen nicht offline zurücklassen
    desktop = (ROOT / "packaging/linux/bonys-vpn.desktop").read_text()
    assert "Name=Bony's VPN" in desktop and "Exec=/opt/bonys-agents/BonysAgents --vpn" in desktop


def test_helper_path_prefers_installed(tmp_path, monkeypatch):
    local, deb = tmp_path / "local", tmp_path / "deb"
    monkeypatch.delenv("BONYS_VPN_HELPER", raising=False)
    monkeypatch.setattr(vpncli, "HELPER", str(local))
    monkeypatch.setattr(vpncli, "DEB_HELPER", str(deb))
    assert vpncli.helper_path() == str(local)  # nichts installiert → Standard (Meldung nennt ihn)
    deb.touch()
    assert vpncli.helper_path() == str(deb)
    local.touch()
    assert vpncli.helper_path() == str(local)
    monkeypatch.setenv("BONYS_VPN_HELPER", "/x/y")
    assert vpncli.helper_path() == "/x/y"


@linux_only
def test_helper_can_clear_exceptions():
    from bonys_agents.vpn import helper as vpnhelper

    got = []
    fake = SimpleNamespace(killswitch_on=got.append, status=lambda: {"killswitch": {}})
    out = SimpleNamespace(write=lambda s: None)
    assert vpnhelper.main(["killswitch", "on", "--no-exceptions"], helper=fake, stdout=out) == 0
    assert vpnhelper.main(["killswitch", "on"], helper=fake, stdout=out) == 0
    assert vpnhelper.main(["killswitch", "on", "--exception", "192.168.178.0/24"], helper=fake, stdout=out) == 0
    assert got == [[], None, ["192.168.178.0/24"]]


# ---------------------------------------------------------------- hostvpn (Linux)
@linux_only
def test_missing_tools_and_install_command(tmp_path):
    assert hostvpn.missing_tools(str(tmp_path)) == ["wireguard-tools", "nftables"]
    for tool in ("wg", "wg-quick", "nft"):
        f = tmp_path / tool
        f.write_text("#!/bin/sh\n")
        f.chmod(0o755)
    assert hostvpn.missing_tools(str(tmp_path)) == []
    cmd = hostvpn.install_tools_command(["nftables", "evil; rm -rf /"])
    assert cmd[:3] == ["pkexec", "sh", "-c"]
    assert "apt-get install -y -q --no-install-recommends nftables\n" in cmd[3] and "evil" not in cmd[3]


def test_install_tools_reports_cancel(monkeypatch):
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: "/usr/bin/" + name)
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return SimpleNamespace(returncode=126)

    monkeypatch.setattr(hostvpn.subprocess, "run", run)
    with pytest.raises(hostvpn.HostVpnError, match="abgebrochen"):
        hostvpn.install_tools()
    assert "env" in calls[0][1]


def test_calls_go_through_helper(monkeypatch):
    calls = []
    monkeypatch.setattr(hostvpn, "helper", lambda: "/usr/sbin/bonys-vpn-helper")

    def call(args, data=None):
        calls.append((args, data))
        return '{"enabled": true, "exceptions": []}' if args[0] in ("killswitch", "import", "status") else ""

    monkeypatch.setattr(vpncli, "call", call)
    hostvpn.up("heim")
    hostvpn.down()
    hostvpn.set_autostart("heim", False)
    hostvpn.set_killswitch(True)
    hostvpn.set_killswitch(True, [])
    hostvpn.set_killswitch(True, ["192.168.178.0/24"])
    hostvpn.set_killswitch(False, ["10.0.0.0/8"])
    hostvpn.import_conf("heim", CONF.encode(), allow_hooks=True, replace=True)
    assert [c[0] for c in calls] == [
        ["up", "heim"], ["down"], ["autostart", "heim", "off"], ["killswitch", "on"],
        ["killswitch", "on", "--no-exceptions"], ["killswitch", "on", "--exception", "192.168.178.0/24"],
        ["killswitch", "off"], ["import", "heim", "--allow-hooks", "--replace"]]
    assert calls[-1][1] == CONF.encode()  # über stdin, nie als Pfad
    with pytest.raises(ValueError):
        hostvpn.up("../etc/shadow")


def test_errors_without_helper(monkeypatch):
    monkeypatch.setattr(hostvpn, "helper", lambda: None)
    with pytest.raises(hostvpn.HostVpnError, match=".deb"):
        hostvpn.status()

    def fail(args, data=None):
        raise vpncli.CliError("Keine Berechtigung")

    monkeypatch.setattr(hostvpn, "helper", lambda: "/x")
    monkeypatch.setattr(vpncli, "call", fail)
    with pytest.raises(hostvpn.HostVpnError, match="Keine Berechtigung"):
        hostvpn.down("heim")


def test_parse_exceptions_and_policy_check(tmp_path):
    assert hostvpn.parse_exceptions("192.168.178.0/24, 10.0.0.5;fd00::/8\n") == [
        "192.168.178.0/24", "10.0.0.5/32", "fd00::/8"]
    assert hostvpn.parse_exceptions("  ") == []
    with pytest.raises(ValueError, match="fritz.box"):
        hostvpn.parse_exceptions("fritz.box")
    p = tmp_path / "50-bonys-vpn.rules"
    assert hostvpn.status_needs_password((p,))
    p.write_text((ROOT / "src/bonys_agents/vpn/data/agent.rules").read_text())
    assert hostvpn.status_needs_password((p,))
    p.write_text((ROOT / "src/bonys_agents/vpn/data/host.rules").read_text())
    assert not hostvpn.status_needs_password((tmp_path / "fehlt", p))


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


@pytest.fixture
def fake_host(monkeypatch):
    """hostvpn ohne echten Helfer: Aufrufe werden protokolliert, Aktionen laufen sofort."""
    from bonys_agents.gui import host_vpn

    calls = []
    state = {"status": STATUS}
    monkeypatch.setattr(hostvpn, "helper", lambda: "/usr/sbin/bonys-vpn-helper")
    monkeypatch.setattr(hostvpn, "missing_tools", lambda path=None: [])
    monkeypatch.setattr(hostvpn, "status_needs_password", lambda rules=None: False)
    monkeypatch.setattr(hostvpn, "status", lambda: state["status"])
    monkeypatch.setattr(hostvpn, "nm_wireguard", lambda run=None: state.get("nm", set()))
    for fn in ("up", "down", "set_autostart", "set_killswitch", "import_conf", "delete", "rename"):
        monkeypatch.setattr(hostvpn, fn, lambda *a, _fn=fn, **kw: calls.append((_fn, a, kw)))
    monkeypatch.setattr(host_vpn.model, "read_live", lambda: {"heim": (4096, 2048)})

    class SyncWorker:
        def __init__(self, fn):
            self.fn, self.result, self.error, self._done = fn, None, None, []
            self.finished = SimpleNamespace(connect=self._done.append)

        def start(self):
            try:
                self.result = self.fn()
            except Exception as e:  # noqa: BLE001
                self.error = e
            for f in self._done:
                f()

        def isRunning(self):  # noqa: N802
            return False

    monkeypatch.setattr(host_vpn, "TaskWorker", SyncWorker)
    return SimpleNamespace(calls=calls, state=state, module=host_vpn)


def test_panel_without_helper(qapp, monkeypatch):
    from bonys_agents.gui.host_vpn import HostVpnPanel

    monkeypatch.setattr(hostvpn, "helper", lambda: None)
    panel = HostVpnPanel()
    assert not panel.setup.isHidden() and panel.body.isHidden() and panel.setup_btn.isHidden()
    assert ".deb" in panel.setup_text.text()
    monkeypatch.setattr(hostvpn, "helper", lambda: "/usr/sbin/bonys-vpn-helper")
    monkeypatch.setattr(hostvpn, "missing_tools", lambda path=None: ["wireguard-tools"])
    monkeypatch.setattr(hostvpn, "has_apt", lambda: True)
    panel._show()
    assert "wireguard-tools" in panel.setup_text.text() and not panel.setup_btn.isHidden()


def test_panel_status_and_actions(qapp, fake_host, monkeypatch, datadir):
    host_vpn = fake_host.module
    panel = host_vpn.HostVpnPanel()
    panel.start()
    panel.live_timer.stop()
    panel.status_timer.stop()
    assert panel.list.count() == 2 and "Verbunden mit heim" in panel.headline.text()
    assert panel.toggle_btn.text() == "Trennen" and panel.autostart.isChecked()
    assert "4,0 KiB" in " ".join(panel.form.itemAt(i).widget().text() for i in range(panel.form.count())
                                 if panel.form.itemAt(i).widget())
    panel.toggle_btn.click()
    assert fake_host.calls[-1][:2] == ("down", ("heim",))
    # fremder Tunnel: nur verbinden/ansehen
    panel.list.setCurrentRow(1)
    assert not panel.rename_btn.isEnabled() and not panel.delete_btn.isEnabled()
    assert panel.edit_btn.text() == "Ansehen …" and panel.toggle_btn.text() == "Verbinden"
    # Hinweis „ganzer Rechner“ vor dem Verbinden – abgebrochen: nichts passiert
    monkeypatch.setattr(host_vpn.QMessageBox, "exec", lambda self: host_vpn.QMessageBox.Cancel)
    n = len(fake_host.calls)
    panel.toggle_btn.click()
    assert len(fake_host.calls) == n
    monkeypatch.setattr(host_vpn, "confirm_whole_computer", lambda parent: True)
    panel.toggle_btn.click()
    assert fake_host.calls[-1][:2] == ("up", ("fremd",))
    # Kill-Switch: ohne Bestätigung der Warnung kein Aufruf
    n = len(fake_host.calls)
    panel.killswitch.click()
    assert len(fake_host.calls) == n and not panel.killswitch.isChecked()


def test_nm_wireguard_parses_nmcli(monkeypatch):
    out = "Kabelgebundene Verbindung 1:802-3-ethernet\nheim:wireguard\nmit\\:doppelpunkt:wireguard\nlo:loopback\n"
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: "/usr/bin/nmcli")
    assert hostvpn.nm_wireguard(lambda *a, **k: SimpleNamespace(stdout=out)) == {"heim", "mit:doppelpunkt"}
    monkeypatch.setattr(hostvpn.shutil, "which", lambda name, **kw: None)
    assert hostvpn.nm_wireguard() == set()


def test_networkmanager_tunnels(qapp, fake_host, monkeypatch, datadir):
    host_vpn = fake_host.module
    fake_host.state["nm"] = {"heim"}
    panel = host_vpn.HostVpnPanel()
    panel.start()
    panel.live_timer.stop()
    panel.status_timer.stop()
    assert not panel.toggle_btn.isEnabled() and "NetworkManager" in panel.tunnel_note.text()
    panel.list.setCurrentRow(1)
    infos = []
    monkeypatch.setattr(host_vpn.QMessageBox, "information", lambda *a: infos.append(a[2]))
    n = len(fake_host.calls)
    panel.toggle_btn.click()
    assert len(fake_host.calls) == n and "zuerst" in infos[0]


def test_intro_hint_remembered(qapp, monkeypatch, datadir):
    from bonys_agents import storage
    from bonys_agents.gui import host_vpn

    shown = []

    def exec_(box):
        shown.append(box.text())
        box.checkBox().setChecked(True)
        return host_vpn.QMessageBox.Ok

    monkeypatch.setattr(host_vpn.QMessageBox, "exec", exec_)
    assert host_vpn.confirm_whole_computer(None)
    assert host_vpn.confirm_whole_computer(None)
    assert len(shown) == 1 and hostvpn.WHOLE_COMPUTER in shown[0]
    assert storage.load_settings()[host_vpn.INTRO_SETTING] is True


def test_import_files_names_hooks_and_no_secret(qapp, fake_host, monkeypatch, tmp_path, datadir):
    host_vpn = fake_host.module
    monkeypatch.setattr(host_vpn, "confirm_whole_computer", lambda parent: True)
    panel = host_vpn.HostVpnPanel()
    panel.start()
    panel.live_timer.stop()
    a = tmp_path / "Mein VPN.conf"
    a.write_bytes(CONF.encode())
    hooks = tmp_path / "hooks.conf"
    hooks.write_bytes(CONF.replace("DNS = 10.8.0.1\n", "DNS = 10.8.0.1\nPostUp = echo hi\n").encode())
    bad = tmp_path / "bad.conf"
    bad.write_text("[Interface]\n")
    warnings = []
    monkeypatch.setattr(host_vpn.QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    monkeypatch.setattr(host_vpn, "confirm_hooks", lambda parent, name, h: False)
    panel.import_files([a, hooks, bad])
    imports = [c for c in fake_host.calls if c[0] == "import_conf"]
    assert [(c[1][0], c[2]) for c in imports] == [("Mein_VPN", {"allow_hooks": False, "replace": False})]
    assert imports[0][1][1] == CONF.encode()
    assert warnings and "bad" in warnings[0] and KEY not in warnings[0]
    # vorhandener Name → „Ersetzen“
    monkeypatch.setattr(host_vpn, "confirm_hooks", lambda parent, name, h: True)
    heim = tmp_path / "heim.conf"
    heim.write_bytes(CONF.encode())

    def choose(box):
        box._clicked = next(b for b in box.buttons() if b.text() == "Ersetzen")
        return 0

    monkeypatch.setattr(host_vpn.QMessageBox, "exec", choose)
    monkeypatch.setattr(host_vpn.QMessageBox, "clickedButton", lambda box: box._clicked)
    panel.import_files([heim, hooks])
    imports = [c for c in fake_host.calls if c[0] == "import_conf"][1:]
    assert [(c[1][0], c[2]) for c in imports] == [("heim", {"allow_hooks": False, "replace": True}),
                                                  ("hooks", {"allow_hooks": True, "replace": False})]
    assert KEY not in panel.message.text() + panel.note.text() + panel.headline.text()


def test_editor_masks_and_validates(qapp, fake_host):
    from bonys_agents.vpn import conf as wgconf

    host_vpn = fake_host.module
    masked = wgconf.mask(CONF)
    assert KEY not in masked
    dlg = host_vpn.EditorDialog("heim", {"managed": True, "conf": masked})
    save = dlg.buttons.button(host_vpn.QDialogButtonBox.Save)
    assert save.isEnabled() and KEY not in dlg.text()
    dlg.edit.setPlainText(masked.replace("Address = 10.8.0.2/32\n", ""))
    assert not save.isEnabled() and "Address" in dlg.check.text()
    dlg.edit.setPlainText(masked + "\n")
    dlg.edit.setPlainText(masked.replace("[Peer]", "PostUp = echo x\n\n[Peer]"))
    assert dlg.hooks == ["PostUp"] and save.isEnabled()
    view = host_vpn.EditorDialog("fremd", {"managed": False, "conf": masked})
    assert view.edit.isReadOnly() and view.reveal_btn.isHidden()


def test_main_window_vpn_area(qapp, fake_host, datadir, monkeypatch):
    from bonys_agents import deps
    from bonys_agents.gui import main_window

    monkeypatch.setattr(deps, "check", lambda info: SimpleNamespace(ok=True))
    monkeypatch.setattr(main_window.updates, "auto_check_due", lambda: False)
    win = main_window.MainWindow()
    try:
        win.timer.stop()
        win.host_vpn.live_timer.stop()
        assert win.vpn_btn.isHidden() == (not sys.platform.startswith("linux"))
        extras = next(a.menu() for a in win.about_btn.menu().actions() if a.menu() and a.text() == "Extras")
        expected = {"win32": ["WireGuard für diesen Rechner installieren …"],
                    "darwin": ["WireGuard für diesen Rechner (App Store) …"]}.get(
            sys.platform, ["Bony's VPN für diesen Rechner"])
        assert [a.text() for a in extras.actions()] == expected
        if not sys.platform.startswith("linux"):
            return
        win.vpn_btn.click()
        win.host_vpn.status_timer.stop()
        assert win.vpn_mode and win.stack.currentIndex() == 3 and win.host_vpn.list.count() == 2
        win.show_vpn(False)
        assert not win.vpn_mode and win.stack.currentIndex() != 3 and not win.vpn_btn.isChecked()
    finally:
        win.timer.stop()
        win.close()


def test_host_vpn_window_offscreen(qapp, fake_host, datadir):
    win = fake_host.module.HostVpnWindow()
    try:
        win.panel.live_timer.stop()
        win.panel.status_timer.stop()
        assert win.windowTitle() == "Bony's VPN" and win.panel.list.count() == 2
        win._fill_menu() if win.tray else None
    finally:
        win.quitting = True
        win.close()


def test_hostvpn_uses_clean_env_everywhere():
    src = (ROOT / "src/bonys_agents/hostvpn.py").read_text()
    for call in ("subprocess.run(", "subprocess.Popen("):
        for chunk in src.split(call)[1:]:
            assert "env=clean_env()" in chunk.split("\n\n")[0][:300], chunk[:120]
    assert subprocess  # (Import für die Prüfung oben)
