# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN als eigenes Paket im Agent-PC: Installation aus dem Release (Signatur, SHA-256), Schema-/
Versionsprüfung, Umstellung alter Agent-PCs, „VPN-App aktualisieren“ (Oberfläche, CLI, beim Start)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bonys_agents import UPDATE_PUBLIC_KEY, apps, cli, cloudinit, qemu, signing, vm, vpnlink

ROOT = Path(__file__).resolve().parent.parent
linux_only = pytest.mark.skipif(sys.platform != "linux", reason="Bash-Skript des Agent-PCs nur unter Linux")
KEY = base64.b64encode(os.urandom(32)).decode()
PEER = base64.b64encode(os.urandom(32)).decode()
CONF = (f"[Interface]\nPrivateKey = {KEY}\nAddress = 10.8.0.2/32\n\n"
        f"[Peer]\nPublicKey = {PEER}\nAllowedIPs = 0.0.0.0/0\nEndpoint = [2001:db8::1]:51820\n")


# ---------------------------------------------------------------- .conf grob prüfen
def test_inspect_conf_accepts_valid_and_finds_hooks():
    info = vpnlink.inspect_conf(CONF.encode("utf-8-sig"))
    assert info.endpoint == "[2001:db8::1]:51820" and info.hooks == ()
    hooked = CONF.replace("[Peer]", "PostUp = echo hi\npredown = x\n[Peer]")
    assert vpnlink.inspect_conf(hooked.encode()).hooks == ("PostUp", "PreDown")


@pytest.mark.parametrize("conf, match", [
    (CONF.replace("[Peer]", "[Kaputt]"), "Abschnitt"),
    (CONF.replace(f"PrivateKey = {KEY}", f"PrivateKey = {KEY[:-2]}"), "PrivateKey"),
    (CONF.replace(f"PublicKey = {PEER}", "PublicKey = xyz"), "PublicKey"),
    (CONF.split("[Peer]")[0], "Peer"),
    (CONF.replace("51820", "0"), "Port"),
    (CONF.replace("Address = ", "Address "), "Name = Wert"),
    ("\xff\xfe".encode("latin-1"), "UTF-8"),
], ids=["abschnitt", "privkey", "pubkey", "ohne-peer", "port", "zeile", "binaer"])
def test_inspect_conf_errors_show_no_values(conf, match):
    data = conf if isinstance(conf, bytes) else conf.encode()
    with pytest.raises(ValueError, match=match) as e:
        vpnlink.inspect_conf(data)
    assert KEY not in str(e.value) and KEY[:-2] not in str(e.value) and PEER not in str(e.value)


def test_check_name():
    assert vpnlink.check_name("fritz_box") == "fritz_box"
    for bad in ("", "a" * 16, "../x", "..", "a b"):
        with pytest.raises(ValueError):
            vpnlink.check_name(bad)
    assert vpnlink.suggest_name("mein vpn (neu)") == "mein_vpn__neu_"


# ---------------------------------------------------------------- Schema und Version
@pytest.mark.parametrize("st, want", [
    ({"schema": 1, "version": "1.0.1"}, ""),
    ({"schema": 1, "version": "1.0.0"}, ""),
    ({"schema": 1, "version": "0.9.9"}, "outdated"),
    ({"schema": 1, "version": "kaputt"}, "outdated"),
    ({"schema": 2, "version": "2.0.0"}, "newer"),
    ({"tunnels": []}, "legacy"),
    ({"legacy": True, "schema": 1}, "legacy"),
    ({"installed": False}, "missing"),
])
def test_compat(st, want):
    assert vpnlink.compat(st) == want
    assert vpnlink.usable(dict(st, compat=want)) == (want not in ("missing", "newer"))


class FakeGA:
    calls: list = []
    reply = (0, "", "")
    fail = False

    def __init__(self, port, timeout=5):
        if FakeGA.fail:
            raise qemu.GuestAgentError("weg")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def exec(self, path, args, stdin=None, timeout=120):
        FakeGA.calls.append((path, args, stdin))
        return FakeGA.reply


@pytest.fixture
def ga(monkeypatch):
    FakeGA.calls, FakeGA.reply, FakeGA.fail = [], (0, "", ""), False
    monkeypatch.setattr(qemu, "GuestAgent", FakeGA)
    return FakeGA


def fake_machine(**over):
    m = SimpleNamespace(name="pc", is_running=lambda: True, runtime=lambda: {"qga_port": 1},
                        progress=lambda: SimpleNamespace(ready=True), save=lambda: None,
                        config=SimpleNamespace(username="agent", apps=["vpn"], first_boot_pending=False))
    for k, v in over.items():
        setattr(m, k, v)
    return m


NEW = {"schema": 1, "version": "1.0.1", "active": None, "tunnels": [{"name": "fritz", "autostart": True}],
       "killswitch": {"enabled": True, "active": True, "exceptions": ["10.0.2.0/24"]}}
OLD = {"active": "fritz", "tunnels": [{"name": "fritz", "active": True}], "killswitch": {"enabled": False}}


def test_status_new_package_and_legacy(ga):
    ga.reply = (0, json.dumps(NEW) + "\n", "")
    st = vpnlink.status(fake_machine())
    script = ga.calls[0][1][1]
    assert f"{vpnlink.GUEST_CLI} status --json" in script and vpnlink.LEGACY_CLI in script
    assert st["compat"] == "" and st["installed"] and "Bony's VPN 1.0.1" in vpnlink.summary(st)
    # alte, eingebaute Fassung: Status kommt trotzdem, mit Hinweis
    ga.reply = (0, '{"legacy": true}\n' + json.dumps(OLD) + "\n", "")
    st = vpnlink.status(fake_machine())
    assert st["compat"] == "legacy" and st["active"] == "fritz" and vpnlink.usable(st)
    assert "VPN-App aktualisieren" in vpnlink.COMPAT_TEXT["legacy"]
    ga.reply = (0, '{"installed": false}\n', "")
    assert vpnlink.status(fake_machine())["compat"] == "missing"
    # Fehler aus „bonys-vpn … --json“ kommt als JSON auf stdout
    ga.reply = (1, json.dumps({"schema": 1, "error": f"Tunnel kaputt {KEY}"}), "")
    with pytest.raises(vpnlink.VpnError) as e:
        vpnlink.up(fake_machine(), "fritz")
    assert "Tunnel kaputt" in str(e.value) and KEY not in str(e.value)


def test_actions_use_the_cli_with_legacy_fallback(ga):
    vpnlink.up(fake_machine(), "fritz")
    vpnlink.set_killswitch(fake_machine(), False)
    path, args, _ = ga.calls[0]
    assert path == "/bin/sh" and args[2:] == ["bonys-vpn", "up", "fritz"]
    assert vpnlink.GUEST_CLI in args[1] and vpnlink.LEGACY_CLI in args[1]
    assert ga.calls[1][1][3:] == ["killswitch", "aus"]
    # Skript wirklich ausführen: neue CLI vor der alten, Argumente unverändert
    if sys.platform == "linux":
        out = subprocess.run(["/bin/sh", "-c", args[1].replace(vpnlink.GUEST_CLI, "/bin/echo"), "x", "up", "a b"],
                             capture_output=True, text=True)
        assert out.stdout.strip() == "up a b"


def test_needs_update(ga, monkeypatch):
    ga.reply = (0, '{"legacy": true}\n' + json.dumps(OLD), "")
    assert vpnlink.needs_update(fake_machine())
    ga.reply = (0, json.dumps(NEW), "")
    assert not vpnlink.needs_update(fake_machine())
    ga.reply = (0, json.dumps(dict(NEW, version="0.5.0")), "")
    assert vpnlink.needs_update(fake_machine())
    ga.fail = True  # ohne Gast-Agent nie nach dem Passwort fragen
    assert not vpnlink.needs_update(fake_machine())


# ---------------------------------------------------------------- VPN-App aktualisieren / umstellen
def test_update_app_runs_the_install_step(monkeypatch):
    runs, saved = [], []
    machine = fake_machine(config=SimpleNamespace(username="agent", apps=["brave"], first_boot_pending=False),
                           save=lambda: saved.append(1))

    def run_logged(script, **kw):
        runs.append((script, kw))
        return 0, "Bony's VPN ist installiert."

    machine.run_logged = run_logged
    vpnlink.update_app(machine)
    script, kw = runs[0]
    assert apps.VPN.install in script and "tee -a /var/log/bonys-agents-vpn.log /dev/console" in script
    assert kw["timeout"] >= 600 and machine.config.apps == ["brave", "vpn"] and saved
    machine.run_logged = lambda script, **kw: (1, apps.VPN_BLOCKED_HINT)
    with pytest.raises(vpnlink.VpnError, match="Kill-Switch"):
        vpnlink.update_app(machine)
    machine.run_logged = lambda script, **kw: (3, "FEHLER")
    with pytest.raises(vpnlink.VpnError, match="Code 3"):
        vpnlink.update_app(machine)
    machine.progress = lambda: SimpleNamespace(ready=False)
    with pytest.raises(vpnlink.VpnError, match="fertig eingerichtet"):
        vpnlink.update_app(machine)


def test_vpn_app_spec():
    spec = apps.APPS["vpn"]
    assert spec.launcher == "bonys-vpn.desktop" and "/usr/sbin/bonys-vpn-helper" in spec.check
    assert "bonys-vpn" in spec.check  # Gruppe
    assert "releases/latest/download" in spec.install and UPDATE_PUBLIC_KEY in spec.install
    assert "/usr/local/lib" not in spec.install.replace("/usr/local/[l]ib", "")  # kein eigener Code mehr
    assert "BONYS_VPN_PAYLOAD" not in spec.install and len(spec.install) < 8000
    # Übernahme der .conf beim Erstellen: Helfer aus dem Paket
    assert vpnlink.GUEST_HELPER == "/usr/sbin/bonys-vpn-helper"


# ---------------------------------------------------------------- Installationsskript mit Attrappen
FAKES = {
    "curl": r'''#!/bin/sh
out=""; url=""; prev=""
for a in "$@"; do
  [ "$prev" = -o ] && out="$a"
  case "$a" in https://*) url="$a" ;; esac
  prev="$a"
done
echo "curl $url" >> "$LOG"
case "$url" in https://github.com/zappotex/bonys-vpn/releases/latest/download/*) ;; *) exit 22 ;; esac
f="$RELEASE/$(basename "$url")"; [ -f "$f" ] || exit 22; /bin/cp "$f" "$out"
''',
    "minisign": r'''#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.environ["SRC"])
from bonys_agents import signing
a = sys.argv[1:]
arg = lambda f: a[a.index(f) + 1]
assert "-V" in a
try:
    c = signing.verify(open(arg("-m"), "rb").read(), open(arg("-x")).read(), arg("-P"))
except signing.SignatureError:
    sys.exit("Signature verification failed")
print(c if "-Q" in a else "Signature and comment signature verified\nTrusted comment: " + c)
''',
    "dpkg": '#!/bin/sh\n[ "$1" = --print-architecture ] && { echo amd64; exit 0; }\nexec /usr/bin/dpkg "$@"\n',
    "apt-get": '#!/bin/sh\necho "apt-get $*" >> "$LOG"\n',
    "usermod": '#!/bin/sh\necho "usermod $*" >> "$LOG"\n',
    "cp": '#!/bin/sh\necho "cp $*" >> "$LOG"\n',
    "nft": '#!/bin/sh\nexit "${NFT_RC:-1}"\n',
    "wg": "#!/bin/sh\nexit 0\n",
    "pgrep": '#!/bin/sh\necho "pgrep $*" >> "$LOG"\n',
}


@pytest.fixture
def guest(tmp_path):
    """Release-Ordner mit signierten Prüfsummen (Testschlüssel) und Attrappen für curl, minisign, apt …"""
    secret, key_id = b"\x44" * 32, b"VPNGUEST"
    public = signing.PublicKey(key_id, signing.ed25519_public_key(secret)).text()
    rel = tmp_path / "release"
    rel.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, text in FAKES.items():
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    desk = tmp_path / "Schreibtisch"
    desk.mkdir()
    (desk / "io.github.bonys_agents.vpn.desktop").write_text("alt")

    def publish(version="1.0.1", comment=None, tamper=None, packages=("bonys-vpn", "bonys-vpn-agentpc")):
        for f in rel.iterdir():
            f.unlink()
        debs = {f"{p}_{version}_all.deb": p.encode() for p in packages}
        for n, d in debs.items():
            (rel / n).write_bytes(d)
        sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in debs.items()).encode()
        (rel / "SHA256SUMS").write_bytes(sums)
        sig = signing.sign(sums, secret, key_id, comment or f"Bony's VPN v{version}")
        (rel / "SHA256SUMS.minisig").write_text(sig)
        if tamper:
            tamper(rel)

    def run(**env):
        script = apps.VPN.install.replace(UPDATE_PUBLIC_KEY, public)
        step = tmp_path / "step.sh"
        step.write_text(script)
        log = tmp_path / "log"
        log.write_text("")
        e = {"PATH": f"{bin_}:/usr/bin:/bin", "LOG": str(log), "RELEASE": str(rel), "SRC": str(ROOT / "src"),
             "AGENT_USER": "agent", "DESKTOP_DIR": str(desk), "HOME": str(tmp_path), **env}
        p = subprocess.run(["bash", "-e", str(step)], capture_output=True, text=True, env=e, timeout=60)
        return p.returncode, p.stdout + p.stderr, log.read_text()

    return SimpleNamespace(publish=publish, run=run, desk=desk)


@linux_only
def test_install_script_verifies_and_installs(guest):
    guest.publish()
    rc, out, log = guest.run()
    assert rc == 0, out
    assert "Signatur und Prüfsummen in Ordnung" in out
    install = [line for line in log.splitlines() if line.startswith("apt-get install") and ".deb" in line]
    assert len(install) == 1 and "bonys-vpn_1.0.1_all.deb" in install[0] and "bonys-vpn-agentpc_1.0.1_all.deb" \
        in install[0]
    assert "usermod -a -G bonys-vpn agent" in log
    assert f"cp /usr/share/applications/bonys-vpn.desktop {guest.desk}/" in log
    assert not (guest.desk / "io.github.bonys_agents.vpn.desktop").exists()  # alte Verknüpfung weg
    assert all(u.startswith("curl https://github.com/zappotex/bonys-vpn/releases/latest/download/")
               for u in log.splitlines() if u.startswith("curl"))


@linux_only
@pytest.mark.parametrize("case, match", [
    ("pruefsumme", "Prüfsumme von bonys-vpn-agentpc"),
    ("signatur", "Signatur der Prüfsummen"),
    ("version", "anderen Version"),
    ("zu-alt", "älter als"),
    ("fehlt", "fehlt im Release"),
])
def test_install_script_refuses_bad_releases(guest, case, match):
    if case == "pruefsumme":
        guest.publish(tamper=lambda r: (r / "bonys-vpn-agentpc_1.0.1_all.deb").write_bytes(b"manipuliert"))
    elif case == "signatur":
        guest.publish(tamper=lambda r: (r / "SHA256SUMS").write_bytes(
            (r / "SHA256SUMS").read_bytes() + b"0" * 64 + b"  untergeschoben.deb\n"))
    elif case == "version":
        guest.publish(comment="Bony's VPN v1.0.0")  # echte, aber alte Signatur
    elif case == "zu-alt":
        guest.publish(version="0.9.0")
    else:
        guest.publish(packages=("bonys-vpn",))
    rc, out, log = guest.run()
    assert rc != 0 and match in out, out
    assert not any(".deb" in line and line.startswith("apt-get") for line in log.splitlines())
    assert "usermod" not in log


@linux_only
def test_install_script_stops_when_killswitch_blocks(guest):
    guest.publish()
    rc, out, log = guest.run(NFT_RC="0")  # Tabelle bonys_vpn geladen, kein Tunnel
    assert rc == 1 and apps.VPN_BLOCKED_HINT in out and "curl" not in log


@linux_only
def test_install_step_inside_app_install_script(guest):
    """Der Schritt läuft wie bei „Programme hinzufügen“ – Heredoc und Prüfung danach bleiben intakt."""
    script = cloudinit.app_install_script(apps.VPN, "agent")
    assert "BONYS_APP" in script and apps.VPN.check in script
    body = script.split("<<'BONYS_APP'", 1)[1].split("BONYS_APP\n", 1)[0]
    assert body == apps.VPN.install
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


# ---------------------------------------------------------------- Kommandozeile und Oberfläche
def test_cli_vpn_update_and_status_hint(monkeypatch, capsys):
    machine = fake_machine()
    monkeypatch.setattr(vm, "get", lambda name: machine)
    calls = []
    monkeypatch.setattr(vpnlink, "update_app", lambda m, **kw: calls.append(kw))
    monkeypatch.setattr(vpnlink, "status", lambda m, **kw: dict(NEW, compat="", installed=True))
    assert cli.main(["vpn", "pc", "update"]) == 0
    assert calls[0]["ssh_prompt"] and calls[0]["log"] is print
    assert "Bony's VPN 1.0.1 ist installiert" in capsys.readouterr().out
    monkeypatch.setattr(vpnlink, "status", lambda m, **kw: dict(OLD, compat="legacy", installed=True, legacy=True))
    assert cli.main(["vpn", "pc", "status"]) == 0
    out = capsys.readouterr().out
    assert "alte, eingebaute Fassung" in out and "bonys-agents vpn pc update" in out
    assert cli.main(["vpn", "pc", "update", "x"]) == 1


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_panel_offers_update_for_old_versions(qapp, monkeypatch):
    from bonys_agents.gui.vpn_panel import VpnPanel

    machine = fake_machine(status=lambda: "läuft", path=Path("/x/pc"))
    panel = VpnPanel()
    monkeypatch.setattr(panel, "reload", lambda quiet=False: None)
    panel.update_for(machine, "läuft")
    panel.state = dict(OLD, installed=True, legacy=True, compat="legacy")
    panel._show()
    assert not panel.update_btn.isHidden() and panel.update_btn.isEnabled()
    assert "alte, eingebaute Fassung" in panel.note.text() and panel.down_btn.isEnabled()  # bedienbar
    panel.state = dict(NEW, installed=True, compat="")
    panel._show()
    assert panel.update_btn.isHidden()
    panel.state = dict(NEW, schema=2, installed=True, compat="newer")
    panel._show()
    assert panel.update_btn.isHidden() and not panel.import_btn.isEnabled() and "neuer" in panel.note.text()
    # Knopf: Rückfrage, dann update_app und neuer Status
    from bonys_agents.gui import vpn_panel

    monkeypatch.setattr(vpn_panel.QMessageBox, "question", lambda *a: vpn_panel.QMessageBox.Yes)
    done = []
    monkeypatch.setattr(vpnlink, "update_app", lambda m, password=None: done.append(m))
    monkeypatch.setattr(vpnlink, "status", lambda m, password=None: dict(NEW, installed=True, compat=""))
    panel.state = dict(OLD, installed=True, legacy=True, compat="legacy")
    panel._update_app()
    for w in panel.workers:
        w.wait(5000)
    qapp.processEvents()
    assert done == [machine] and panel.state["compat"] == "" and "1.0.1 ist installiert" in panel.status.text()


def test_main_window_switches_old_agent_pcs_once_per_start(qapp, datadir, monkeypatch):
    from bonys_agents import deps
    from bonys_agents.gui import main_window

    monkeypatch.setattr(deps, "check", lambda info: SimpleNamespace(ok=True))
    monkeypatch.setattr(main_window.updates, "auto_check_due", lambda: False)
    win = main_window.MainWindow()
    try:
        win.timer.stop()
        old = fake_machine(name="alt", guest_agent_ready=lambda: True, runtime=lambda: {"qmp_port": 7})
        new = fake_machine(name="neu", guest_agent_ready=lambda: True, runtime=lambda: {"qmp_port": 8})
        boot = fake_machine(name="bootet", guest_agent_ready=lambda: False, runtime=lambda: {"qmp_port": 9})
        noapp = fake_machine(name="ohne", config=SimpleNamespace(username="a", apps=[], first_boot_pending=False))
        updated = []
        monkeypatch.setattr(vpnlink, "needs_update", lambda m: m.name == "alt")
        monkeypatch.setattr(vpnlink, "update_app", lambda m: updated.append(m.name))
        for _ in range(2):  # zweiter Durchlauf: schon geprüft → nichts mehr
            win._check_vpn_apps([old, new, boot, noapp])
            if win._vpn_check:
                win._vpn_check.wait(5000)
            qapp.processEvents()
        assert updated == ["alt"]
        assert ("alt", 7) in win._vpn_checked and ("neu", 8) in win._vpn_checked
        assert ("bootet", 9) not in win._vpn_checked  # wird später geprüft
        assert "umgestellt" in win.statusBar().currentMessage()
    finally:
        win.timer.stop()
        win.close()
