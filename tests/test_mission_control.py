# SPDX-License-Identifier: GPL-3.0-or-later
"""Mission Control und Docker als Apps: Abhängigkeiten, Auswahl, Mindestanforderungen, Nachinstallieren
(vm.json, Wiederaufnahme), Status/Weiterleitung, Vorlagen-Bereinigung – und dass keine Geheimnisse von Mission
Control auf dem Host landen."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bonys_agents import apps, cli, cloudinit, desktops, mission_control, qemu, vm
from bonys_agents import progress as pct

MC = mission_control
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Bash-Skripte nur unter Linux")
SECRET = "geheimes-token-0123456789abcdef"


def bash_syntax_ok(script: str) -> bool:
    """bash -n – nur unter Linux (auf Windows-Runnern gibt es kein brauchbares bash)."""
    if not sys.platform.startswith("linux"):
        return True
    return subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


# ---------------------------------------------------------------- Abhängigkeiten
def test_mission_control_requires_docker_and_brave():
    # Brave: die Verknüpfung öffnet die Oberfläche darin (ohne Browser im Agent-PC passierte nichts)
    assert apps.APPS[MC.APP_ID].requires == ("brave", "docker")
    assert apps.dependencies([MC.APP_ID]) == ["brave", "docker"]
    assert apps.dependencies([MC.APP_ID, "brave"]) == ["docker"]
    assert apps.with_dependencies(["hermes", MC.APP_ID, "brave"]) == ["brave", "docker", MC.APP_ID, "hermes"]
    assert [a.id for a in apps.resolve([MC.APP_ID])] == ["brave", "docker", MC.APP_ID]
    assert apps.required_by("docker", ["brave", MC.APP_ID]) == [MC.APP_ID]
    assert apps.required_by("brave", ["brave", "docker", MC.APP_ID]) == [MC.APP_ID]
    assert apps.dependencies(["brave"]) == [] and apps.with_dependencies(["docker"]) == ["docker"]


def test_dependencies_come_before_their_apps_and_exist():
    order = list(apps.APPS)
    for a in apps.APPS.values():
        for dep in a.requires:
            assert dep in apps.APPS and order.index(dep) < order.index(a.id), (a.id, dep)


def test_docker_is_hidden_building_block():
    assert apps.APPS["docker"].hidden and not apps.APPS["docker"].default
    assert "docker" not in apps.visible_ids() and MC.APP_ID in apps.visible_ids()
    assert not apps.APPS[MC.APP_ID].default  # optional
    with pytest.raises(ValueError, match="Unbekannte"):
        apps.resolve(["mission-kontrolle"])


def test_docker_install_uses_official_repo_with_key_check():
    s = apps.DOCKER.install
    assert "https://download.docker.com/linux/debian/gpg" in s
    assert apps.DOCKER_KEY_FINGERPRINT == "9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
    assert apps.DOCKER_KEY_FINGERPRINT in s and "gpg --batch --show-keys --with-colons" in s
    assert "signed-by=/etc/apt/keyrings/docker.asc" in s and "arch=$ARCH" in s
    for p in ("docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"):
        assert p in s
    assert 'usermod -a -G docker "$AGENT_USER"' in s
    assert "amd64|arm64" in s
    assert "docker.io" not in s.split("apt-get install -y docker-ce")[1]  # nur entfernen, nie installieren
    assert bash_syntax_ok(s)


@linux_only
def test_docker_key_fingerprint_is_checked(tmp_path):
    """Falscher Schlüssel → Abbruch, bevor apt der Quelle vertraut."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    for name, body in {
        "apt-get": f'echo "apt-get $*" >> {log}',
        "dpkg": "echo amd64",
        "dpkg-query": "exit 1",
        "curl": 'while [ $# -gt 0 ]; do [ "$1" = -o ] && echo KEY > "$2"; shift; done',
        "gpg": "echo 'fpr:::::::::0000000000000000000000000000000000000000:'",
        "install": f'echo "install $*" >> {log}',
    }.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", AGENT_USER="agent")
    r = subprocess.run(["bash", "-e"], input=apps.DOCKER.install, text=True, capture_output=True, env=env)
    assert r.returncode != 0 and "Fingerabdruck" in r.stderr
    assert "docker-ce" not in log.read_text() and "keyrings" not in log.read_text()


# ---------------------------------------------------------------- Installation von Mission Control
def test_install_script_uses_fixed_release_and_checksums():
    s = apps.APPS[MC.APP_ID].install
    assert f"MC_VERSION='{MC.VERSION}'" in s and f"MC_SHA256='{MC.INSTALL_SHA256}'" in s
    assert f"{MC.REPO_URL}/releases/download/v{MC.VERSION}" in s
    assert "sha256sum -c --strict" in s and "SHA256SUMS" in s
    assert "--no-desktop" in s and "--install-deps" not in s.replace("ohne --install-deps", "")
    assert '--user "$AGENT_USER"' in s
    assert "/releases/latest" not in s  # neue Agent-PCs bekommen immer genau dieses Release
    assert bash_syntax_ok(s)


def test_launcher_opens_brave():
    s = MC.launcher_script()
    assert f"Exec={MC.OPENER}" in s and "brave-browser" in s and MC.URL in s
    assert '"$DESKTOP_DIR/' in s and apps.APPS[MC.APP_ID].launcher == MC.LAUNCHER
    assert "xdg-open" in s  # ohne Brave: Standard-Browser


@linux_only
@pytest.mark.parametrize("tampered", [False, True])
def test_install_script_refuses_tampered_installer(tmp_path, tampered):
    release = tmp_path / "release"
    release.mkdir()
    good = b"#!/bin/bash\necho \"INSTALLER $*\"\n"
    (release / "install.sh").write_bytes(good + (b"echo boese\n" if tampered else b""))
    (release / "SHA256SUMS").write_text(f"{hashlib.sha256(good).hexdigest()}  install.sh\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "apt-get": "true",
        "curl": f'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; https://*) url="$1";; esac; shift; done\n'
                f'cp "{release}/${{url##*/}}" "$out"',
    }.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    script = MC.install_script(sha256=hashlib.sha256(good).hexdigest()).split("\ncat > /usr/local/bin")[0]
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", AGENT_USER="agent")
    r = subprocess.run(["bash", "-e"], input=script, text=True, capture_output=True, env=env)
    if tampered:
        assert r.returncode != 0 and "INSTALLER" not in r.stdout and "Prüfsumme" in r.stderr
    else:
        assert r.returncode == 0, r.stderr
        assert f"INSTALLER --version {MC.VERSION} --user agent --no-desktop" in r.stdout


def test_progress_follows_install_sh_steps():
    assert pct.step_fraction("") < 0.1
    early = pct.step_fraction("[mission-control] (1/10) System prüfen\n")
    late = pct.step_fraction("[mission-control] (1/10) a\n[mission-control] (9/10) Dienste starten\n")
    assert 0 < early < late < 1
    plan = ["docker", MC.APP_ID]
    assert pct.install_percent(plan, 0, "") == 0
    mid = pct.install_percent(plan, 1, "[mission-control] (5/10) x\n")
    assert pct.install_percent(plan, 1, "") < mid < 100
    assert pct.install_percent(plan, 2, "") == 100


# ---------------------------------------------------------------- Mindestanforderungen
def test_parse_requirements_and_fallback():
    r = MC.parse_requirements({"version": "0.1.0", "min_ram_mb": 768, "min_free_disk_gb": 3})
    assert (r.min_ram_mb, r.min_free_disk_gb, r.fetched) == (768, 3, True)
    bad = MC.parse_requirements({"min_ram_mb": "viel", "min_free_disk_gb": -1})
    assert bad.min_ram_mb == MC.DEFAULT_REQUIREMENTS.min_ram_mb and not bad.fetched
    assert MC.parse_requirements(["kein", "dict"]) == MC.DEFAULT_REQUIREMENTS


def test_requirements_from_release_cached_and_offline(datadir, monkeypatch):
    assert MC.requirements() == MC.DEFAULT_REQUIREMENTS  # kein Netz → Standardwerte
    calls = []

    def download(url, timeout):
        calls.append(url)
        return json.dumps({"version": MC.VERSION, "min_ram_mb": 1024, "min_free_disk_gb": 5}).encode()

    monkeypatch.setattr(MC, "_download", download)
    r = MC.requirements()
    assert (r.min_ram_mb, r.min_free_disk_gb) == (1024, 5) and calls == [MC.release_url("agentpc.json")]
    monkeypatch.setattr(MC, "_cache", None)
    assert MC.requirements(fetch=False).min_ram_mb == 1024 and len(calls) == 1  # aus der Datei
    assert "5 GB" in MC.requirement_note(r) and "Docker" in MC.requirement_note(r)


def test_resource_warnings():
    req = MC.Requirements(min_ram_mb=512, min_free_disk_gb=2, fetched=True)
    cin = desktops.get("cinnamon").min_ram_mb
    assert MC.resource_warnings(["brave"], 1024, 32, cin, req) == []           # ohne Mission Control nie
    assert MC.resource_warnings([MC.APP_ID], cin + 512, 32, cin, req) == []
    low = MC.resource_warnings([MC.APP_ID], cin, 32, cin, req)
    assert len(low) == 1 and "RAM" in low[0] and "erhöhen" in low[0]
    big = MC.Requirements(min_ram_mb=512, min_free_disk_gb=40, fetched=True)
    disk = MC.resource_warnings([MC.APP_ID], 8192, 32, cin, big)
    assert len(disk) == 1 and "Festplatte" in disk[0]
    assert "frei" in MC.resource_warnings([MC.APP_ID], 8192, 64, cin, req, free_disk_gb=1.0)[0]


# ---------------------------------------------------------------- Kommandozeile
def test_cli_create_with_mission_control_warns_and_adds_docker(datadir, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli, "_ensure_ready", lambda yes: True)
    monkeypatch.setattr(vm, "create", lambda *a, **kw: seen.update(kw) or (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        cli.main(["create", "pc", "--apps", "brave,mission-control", "--ram", "2048", "--password", "x",
                  "--desktop", "cinnamon"])
    out = capsys.readouterr().out
    assert seen["app_ids"] == ["brave", MC.APP_ID]
    assert "Wird mitinstalliert: Docker" in out and "RAM" in out and "--ram" in out


def _machine(datadir, apps_=("brave", "hermes"), running=True, **cfg):
    p = vm.vms_dir() / "pc"
    p.mkdir(parents=True, exist_ok=True)
    c = vm.VMConfig(name="pc", arch="x86_64", cpus=2, ram_mb=8192, apps=list(apps_), provisioned=True, **cfg)
    (p / "vm.json").write_text(json.dumps(c.__dict__))
    m = vm.VM(p)
    m.is_running = lambda: running
    return m


def test_cli_apps_lists_installed_and_available(datadir, monkeypatch, capsys):
    m = _machine(datadir, apps_=("brave", "docker", MC.APP_ID), app_info={MC.APP_ID: {"version": "0.1.0"}})
    monkeypatch.setattr(vm, "get", lambda name: m)
    assert cli.main(["apps", "pc"]) == 0
    out = capsys.readouterr().out
    installed, available = out.split("Verfügbar")
    assert "Mission Control  Version 0.1.0" in installed and "docker" in installed
    assert "telegram" in available and "docker" not in available and MC.APP_ID not in available
    assert cli.main(["apps"]) == 0
    out = capsys.readouterr().out
    assert "mission-control" in out and "(bringt Brave Browser, Docker mit)" in out and "  docker " not in out


def test_cli_install_several_apps(datadir, monkeypatch, capsys):
    m = _machine(datadir)
    monkeypatch.setattr(vm, "get", lambda name: m)
    calls = []
    monkeypatch.setattr(vm.VM, "install_apps", lambda self, ids, **kw: calls.append((ids, kw)) or ids)
    assert cli.main(["install", "pc", "mission-control", "telegram"]) == 0
    out = capsys.readouterr().out
    assert "Docker wird mitinstalliert" in out
    ids, kw = calls[0]
    assert ids == ["mission-control", "telegram"] and kw["ssh_prompt"] and kw["log"] is print


# ---------------------------------------------------------------- Nachinstallieren: vm.json, Wiederaufnahme
def test_install_apps_records_each_app_and_resumes(datadir):
    m = _machine(datadir)
    m.progress = lambda: SimpleNamespace(ready=True)
    runs = []
    fail_on = {MC.APP_ID}

    def run_logged(script, **kw):
        app = next(a for a in apps.APPS.values() if f"installiert {a.name} nachträglich" in script)
        runs.append(app.id)
        return (1, "FEHLER") if app.id in fail_on else (0, "ok")

    m.run_logged = run_logged
    steps = []
    with pytest.raises(RuntimeError, match="Erneut starten setzt hier fort"):
        m.install_apps([MC.APP_ID], step=lambda n, total, a: steps.append((n, total, a)))
    assert runs == ["docker", MC.APP_ID] and steps[0] == (1, 2, "docker")
    saved = json.loads((m.path / "vm.json").read_text())
    assert "docker" in saved["apps"] and MC.APP_ID not in saved["apps"]   # Docker ist fertig und gemerkt
    # zweiter Versuch: nur noch Mission Control
    fail_on.clear()
    runs.clear()
    m2 = vm.VM(m.path)
    m2.is_running, m2.progress, m2.run_logged = (lambda: True), (lambda: SimpleNamespace(ready=True)), run_logged
    assert m2.install_plan([MC.APP_ID]) == [MC.APP_ID]
    assert m2.install_apps([MC.APP_ID]) == [MC.APP_ID] and runs == [MC.APP_ID]
    saved = json.loads((m.path / "vm.json").read_text())
    assert saved["apps"] == ["brave", "docker", MC.APP_ID, "hermes"]
    assert saved["app_info"][MC.APP_ID]["version"] == MC.VERSION and "installed" in saved["app_info"]["docker"]
    with pytest.raises(ValueError, match="bereits installiert"):
        m2.install_apps([MC.APP_ID])


def test_missing_apps_hides_building_blocks(datadir):
    m = _machine(datadir)
    ids = [a.id for a in m.missing_apps()]
    assert MC.APP_ID in ids and "docker" not in ids


def test_vmconfig_defaults_and_old_vm_json(datadir):
    cfg = vm.VMConfig(name="x", arch="x86_64", cpus=1, ram_mb=4096)
    assert cfg.app_info == {} and not cfg.mc_forward and cfg.mc_forward_port == 0  # Weiterleitung aus
    p = vm.vms_dir() / "alt"
    p.mkdir(parents=True)
    (p / "vm.json").write_text(json.dumps({"name": "alt", "arch": "x86_64", "cpus": 1, "ram_mb": 4096,
                                           "apps": ["brave"]}))
    assert vm.VM(p).config.app_info == {}  # vm.json älterer Versionen


@linux_only
def test_app_install_script_is_resumable(tmp_path):
    """Markierung + grüne Prüfung → überspringen; Sperre gegen einen noch laufenden Versuch."""
    app = apps.AppSpec(id="demo", name="Demo", description="", install="\necho INSTALLIERT\n", check="true")
    kw = dict(console=str(tmp_path / "console"), state_dir=str(tmp_path / "state"),
              lock_file=str(tmp_path / "lock"), log_file=str(tmp_path / "log"))
    script = cloudinit.app_install_script(app, os.environ.get("USER", "root"), **kw)
    script = script.replace('su - "$AGENT_USER" -c', "bash -c").replace("apt-get update -y || true", "true")
    script = script.replace("dpkg --configure -a || true", "true")
    script = script.replace("\nbonys_apt_wait\n", "\ntrue\n")  # echte dpkg-Sperren gehören root
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "chown").write_text("#!/bin/sh\ntrue\n")
    (bin_dir / "chown").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    script = script.replace('AGENT_HOME="/home/$AGENT_USER"', f'AGENT_HOME="{tmp_path}/home"')
    r1 = subprocess.run(["bash"], input=script, text=True, capture_output=True, env=env)
    assert r1.returncode == 0 and "INSTALLIERT" in r1.stdout, r1.stdout + r1.stderr
    assert (tmp_path / "state" / "demo.done").exists()
    r2 = subprocess.run(["bash"], input=script, text=True, capture_output=True, env=env)
    assert r2.returncode == 0 and "bereits installiert" in r2.stdout and "INSTALLIERT" not in r2.stdout
    forced = cloudinit.app_install_script(app, "x", force=True, **kw)
    assert "[ 0 = 1 ]" in forced


# ---------------------------------------------------------------- Status, Öffnen, Update, Deinstallieren
def test_parse_status_keeps_only_known_fields():
    line = MC.STATUS_MARKER + " " + json.dumps({"installed": True, "version": "0.1.0", "active": True,
                                                  "healthy": True, "health_version": "0.1.0", "docker": True,
                                                  "port": 8787, "MISSION_CONTROL_API_TOKEN": SECRET,
                                                  "env": {"x": SECRET}})
    st = MC.parse_status("Rauschen\n" + line + "\n")
    assert SECRET not in json.dumps(st) and set(st) <= set(MC._STATUS_KEYS)
    assert MC.status_text(st) == "läuft (Version 0.1.0)"
    assert MC.parse_status(MC.STATUS_MARKER + ' {"installed": true, "port": "8787; rm -rf /"}')["port"] == MC.PORT
    with pytest.raises(RuntimeError):
        MC.parse_status("nichts")


@linux_only
def test_status_script_never_prints_secrets(tmp_path):
    d = tmp_path / "mc"
    d.mkdir()
    (d / "VERSION").write_text("0.1.0\n")
    (d / ".env").write_text(f"MISSION_CONTROL_PORT=8799\nMISSION_CONTROL_API_TOKEN={SECRET}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text("#!/bin/sh\necho inactive\n")
    (bin_dir / "systemctl").chmod(0o755)
    script = MC.status_script().replace(MC.INSTALL_DIR, str(d))
    r = subprocess.run(["bash"], input=script, text=True, capture_output=True,
                       env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}"))
    assert r.returncode == 0, r.stderr
    assert SECRET not in r.stdout + r.stderr
    st = MC.parse_status(r.stdout)
    assert st["installed"] and st["port"] == 8799 and not st["healthy"] and st["version"] == "0.1.0"
    for s in (MC.status_script(), MC.update_script(), MC.uninstall_script(True), MC.open_script("agent"),
              MC.fresh_template_script(), MC.install_script()):
        assert "cat " + MC.INSTALL_DIR + "/.env" not in s and "MISSION_CONTROL_API_TOKEN" not in s


def test_status_update_uninstall_keep_secrets_off_host(datadir):
    m = _machine(datadir, apps_=("brave", "docker", MC.APP_ID), app_info={MC.APP_ID: {"version": "0.1.0"}})
    m.progress = lambda: SimpleNamespace(ready=True)
    scripts = []

    def run_logged(script, **kw):
        scripts.append(script)
        if MC.STATUS_MARKER in script:
            return 0, MC.STATUS_MARKER + " " + json.dumps({"installed": True, "version": "0.2.0", "active": True,
                                                            "healthy": True, "health_version": "0.2.0",
                                                            "docker": True, "port": 8787, "token": SECRET})
        return 0, "[mission-control] (6/10) .env angelegt\n"

    m.run_logged = run_logged
    assert "0.2.0" in MC.update(m, version="0.2.0")
    assert "--version '0.2.0'" in scripts[0] and "update.sh" in scripts[0]
    with pytest.raises(ValueError):
        MC.update_script("0.2; rm -rf /")
    saved = (m.path / "vm.json").read_text()
    assert json.loads(saved)["app_info"][MC.APP_ID]["version"] == "0.2.0" and SECRET not in saved
    assert "entfernt" in MC.uninstall(m)
    assert "uninstall.sh\n" in scripts[-1] and "--purge" not in scripts[-1]
    saved = json.loads((m.path / "vm.json").read_text())
    assert saved["apps"] == ["brave", "docker"] and MC.APP_ID not in saved["app_info"]  # Docker bleibt
    assert "--purge" in MC.uninstall_script(purge=True)
    for f in m.path.iterdir():
        assert SECRET not in f.read_text(errors="ignore")


def test_open_reports_missing_desktop(datadir):
    m = _machine(datadir, apps_=(MC.APP_ID,))
    m.progress = lambda: SimpleNamespace(ready=True)
    m.run_logged = lambda script, **kw: (4, "")
    with pytest.raises(RuntimeError, match="kein Desktop"):
        MC.open_in_guest(m)
    m.run_logged = lambda script, **kw: (0, "")
    assert "Brave" in MC.open_in_guest(m)
    assert "runuser -u" in MC.open_script("agent") and MC.OPENER in MC.open_script("agent")


# ---------------------------------------------------------------- Weiterleitung (nur 127.0.0.1, standardmäßig aus)
class _FakeQMP:
    log: list = []

    def __init__(self, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def hostfwd_add(self, rule):
        _FakeQMP.log.append(("add", rule))

    def hostfwd_remove(self, rule):
        _FakeQMP.log.append(("remove", rule))


def test_forward_only_localhost_and_off_by_default(datadir, monkeypatch):
    monkeypatch.setattr(qemu, "QMP", _FakeQMP)
    _FakeQMP.log = []
    m = _machine(datadir, apps_=(MC.APP_ID,))
    m.runtime = lambda: {"qmp_port": 1}
    m.progress = lambda: SimpleNamespace(ready=True)
    scripts = []
    m.run_logged = lambda script, **kw: scripts.append(script) or (0, "")
    assert MC.launch_forwards(m) == ()
    msg = MC.set_forward(m, True)
    port = m.config.mc_forward_port
    rule = f"tcp:127.0.0.1:{port}-:{MC.GUEST_FORWARD_PORT}"
    assert port >= MC.FIRST_FORWARD_PORT and f"http://127.0.0.1:{port}/" in msg
    assert ("add", rule) in _FakeQMP.log and MC.launch_forwards(m) == (rule,)
    assert all("0.0.0.0" not in r for _, r in _FakeQMP.log)
    # Proxy im Agent-PC: nur an der Adresse im QEMU-Netz, Ziel 127.0.0.1 im Agent-PC
    assert f"ListenStream={MC.GUEST_NET_ADDR}:{MC.GUEST_FORWARD_PORT}" in scripts[0]
    assert f"127.0.0.1:{MC.PORT}" in scripts[0] and "systemctl enable bonys-mc-forward.socket" in scripts[0]
    assert bash_syntax_ok(scripts[0])
    MC.set_forward(m, False)
    assert not vm.VM(m.path).config.mc_forward and ("remove", rule) in _FakeQMP.log
    assert "disable --now bonys-mc-forward.socket" in scripts[-1]
    assert "bonys-mc-forward" in MC.uninstall_script()
    spec = SimpleNamespace(ssh_port=2222, restrict_net=False, rdp_port=None, rdp_addr=None,
                           extra_forwards=(MC.forward_rule(18787),))
    assert f"hostfwd=tcp:127.0.0.1:18787-:{MC.GUEST_FORWARD_PORT}" in qemu._netdev(spec)


def test_forward_needs_mission_control(datadir):
    m = _machine(datadir)
    with pytest.raises(RuntimeError, match="nicht installiert"):
        MC.set_forward(m, True)


# ---------------------------------------------------------------- Vorlagen
def test_fresh_template_resets_mission_control_clone_keeps_it():
    fresh = cloudinit.generalize_script("agent", remove_personal=True)
    clone = cloudinit.generalize_script("agent", remove_personal=False)
    assert "reset-secrets.sh" in fresh and "== Mission Control ==" in fresh
    assert "reset-secrets.sh" not in clone
    dry = cloudinit.generalize_script("agent", remove_personal=True, dry_run=True)
    assert "WÜRDE AUSFÜHREN: $MC/scripts/reset-secrets.sh" in dry
    assert "docker image" not in MC.fresh_template_script() and "--purge" not in MC.fresh_template_script()


def _run_fresh(tmp_path, reset_body: str, volume_left: bool = False):
    d = tmp_path / "mc"
    (d / "scripts").mkdir(parents=True)
    (d / ".env.example").write_text("MISSION_CONTROL_PORT=8787\nMISSION_CONTROL_API_TOKEN=__GENERATE__\n")
    (d / ".env").write_text(f"MISSION_CONTROL_PORT=8787\nMISSION_CONTROL_API_TOKEN={SECRET}\n")
    (d / "scripts" / "reset-secrets.sh").write_text(f"#!/bin/bash\n{reset_body}\n")
    (d / "scripts" / "reset-secrets.sh").chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in {"systemctl": "true",
                       "docker": "exit 0" if volume_left else '[ "$2" = inspect ] && exit 1; exit 0'}.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    script = "DRY=0\n" + MC.fresh_template_script().replace(MC.INSTALL_DIR, str(d))
    r = subprocess.run(["bash"], input=script, text=True, capture_output=True,
                       env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MCDIR=str(d)))
    return r, d


@linux_only
def test_fresh_template_verifies_reset(tmp_path):
    good = "sed -i 's/^MISSION_CONTROL_API_TOKEN=.*/MISSION_CONTROL_API_TOKEN=__GENERATE__/' \"$MCDIR/.env\""
    r, d = _run_fresh(tmp_path, good)
    assert r.returncode == 0, r.stdout + r.stderr
    assert SECRET not in (d / ".env").read_text() and SECRET not in r.stdout + r.stderr
    r, _ = _run_fresh(tmp_path / "2", "true")  # Skript „vergisst“ das Geheimnis
    assert r.returncode == 1 and "nicht zurückgesetzt" in r.stdout and SECRET not in r.stdout
    r, _ = _run_fresh(tmp_path / "3", good, volume_left=True)
    assert r.returncode == 1 and "Docker-Volume" in r.stdout


def test_template_keeps_app_info(datadir):
    from bonys_agents import templates

    t = templates.Template(path=Path("/x"), name="t", app_info={MC.APP_ID: {"version": "0.1.0"}})
    assert t.to_json()["app_info"] == {MC.APP_ID: {"version": "0.1.0"}}


def test_deletion_text_mentions_mission_control():
    pytest.importorskip("PySide6.QtWidgets")
    from bonys_agents.gui.template_dialogs import deletion_text

    assert MC.FRESH_CLEANUP in deletion_text("agent", True, mission=True)
    assert MC.FRESH_CLEANUP not in deletion_text("agent", True, mission=False)
    assert MC.CLONE_NOTE in deletion_text("agent", False, mission=True)


# ---------------------------------------------------------------- Oberfläche
@pytest.fixture
def qapp(datadir):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_create_dialog_selects_docker_and_warns(qapp):
    from bonys_agents import host
    from bonys_agents.gui.create_dialog import CreateDialog

    dlg = CreateDialog(host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=16384, accel="kvm"))
    assert "docker" not in dlg.app_boxes and MC.APP_ID in dlg.app_boxes
    assert not dlg.mc_box.isChecked()
    dlg.desktop.setCurrentIndex(dlg.desktop.findData("cinnamon"))
    dlg.ram.setValue(desktops.get("cinnamon").min_ram_mb // 512)
    dlg.mc_box.setChecked(True)
    dlg.app_boxes["brave"].setChecked(True)
    assert "Wird mitinstalliert: Docker" in dlg.mc_desc.text()
    dlg.app_boxes["brave"].setChecked(False)  # ohne Brave-Häkchen kommt Brave trotzdem mit – und steht da
    assert "Wird mitinstalliert: Brave Browser, Docker" in dlg.mc_desc.text()
    assert not dlg.mc_warn.isHidden() and "RAM" in dlg.mc_warn.text()
    dlg._fix_mc()
    assert dlg.ram.value() * 512 >= desktops.get("cinnamon").min_ram_mb + MC.DEFAULT_REQUIREMENTS.min_ram_mb
    assert dlg.mc_warn.isHidden()
    dlg._req_timer.stop()
    dlg.close()


def test_install_dialog_shows_dependency(qapp, datadir):
    from bonys_agents.gui.install_dialog import InstallAppsDialog

    m = _machine(datadir)
    dlg = InstallAppsDialog(m, preselect=[MC.APP_ID])
    assert "docker" not in dlg.boxes
    assert "Docker" in dlg.plan_label.text() and not dlg.plan_label.isHidden()
    assert not dlg.pw.isHidden()  # kein Gast-Agent → Passwort für SSH
    dlg.close()


def test_mc_panel_states(qapp, datadir):
    from bonys_agents.gui.mc_panel import McPanel

    p = McPanel()
    m = _machine(datadir, running=False)
    m.status = lambda: "gestoppt"
    p.update_for(m, "gestoppt")
    assert not p.install_btn.isHidden() and p.body.isHidden() and "nicht installiert" in p.headline.text()
    m2 = _machine(datadir, apps_=("docker", MC.APP_ID), running=False, app_info={MC.APP_ID: {"version": "0.1.0"}})
    m2.status = lambda: "gestoppt"
    p.machine = None
    p.update_for(m2, "gestoppt")
    assert p.install_btn.isHidden() and not p.body.isHidden() and "0.1.0" in p.headline.text()
    assert not p.forward.isChecked() and not p.open_btn.isEnabled()


# ---------------------------------------------------------------- Brave ohne Schlüsselbund (--password-store=basic)
BRAVE_DESKTOP = """[Desktop Entry]
Name=Brave Web Browser
Exec=/usr/bin/brave-browser-stable %U
[Desktop Action new-window]
Exec=/usr/bin/brave-browser-stable
[Desktop Action new-private-window]
Exec=/usr/bin/brave-browser-stable --incognito
"""


@linux_only
def test_brave_uses_basic_password_store(tmp_path):
    """Alle Exec-Zeilen bekommen den Schalter; Eintrag in /usr/local (bleibt bei Updates), Markierung gesetzt."""
    share, local, conf, desk = (tmp_path / d for d in ("share", "local", "conf", "desk"))
    share.mkdir()
    desk.mkdir()
    (share / "brave-browser.desktop").write_text(BRAVE_DESKTOP)
    part = apps.BRAVE.install.split("apt-get install -y brave-browser\n", 1)[1]
    part = (part.replace("/usr/share/applications", str(share)).replace("/usr/local/share/applications", str(local))
            .replace(desktops.CONF_DIR, str(conf)))
    r = subprocess.run(["bash", "-e"], input=part, text=True, capture_output=True,
                       env=dict(os.environ, DESKTOP_DIR=str(desk)))
    assert r.returncode == 0, r.stderr
    out = (local / "brave-browser.desktop").read_text()
    assert out.count("--password-store=basic") == 3 and "--incognito" in out
    assert (desk / "brave-browser.desktop").read_text() == out
    assert (conf / "brave-password-store-basic").exists()
    assert (share / "brave-browser.desktop").read_text() == BRAVE_DESKTOP  # Paketdatei unverändert


@linux_only
@pytest.mark.parametrize("marker", [True, False])
def test_mc_opener_follows_brave_setting(tmp_path, marker):
    opener = MC.launcher_script().split("<<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0]
    if marker:
        (tmp_path / "marker").touch()
    opener = opener.replace(desktops.BRAVE_BASIC_MARKER, str(tmp_path / "marker"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "brave-browser").write_text('#!/bin/sh\necho "BRAVE $*"\n')
    (bin_dir / "brave-browser").chmod(0o755)
    r = subprocess.run(["sh"], input=opener, text=True, capture_output=True,
                       env=dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin"))
    assert r.stdout.startswith("BRAVE ") and MC.URL in r.stdout
    assert ("--password-store=basic" in r.stdout) == marker
