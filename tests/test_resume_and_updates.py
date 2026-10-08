# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für 0.8: saubere Umgebung für externe Programme, Wiederaufnahme der Einrichtung, Updates."""

import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path, PurePosixPath

import pytest

from bonys_agents import apps, cloudinit, diagnose, procutil, signing, updates, vm
from bonys_agents import progress as pct

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bonys_agents"


# =========================================================== A) Umgebung für externe Programme
BUNDLE = "/opt/bonys-agents/_internal"


def test_clean_env_restores_ld_library_path_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", BUNDLE, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/bonys-agents/BonysAgents")
    # PyInstaller merkt sich den ursprünglichen Wert in LD_LIBRARY_PATH_ORIG
    monkeypatch.setenv("LD_LIBRARY_PATH", os.pathsep.join([BUNDLE, "/usr/local/lib/eigene"]))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib/eigene")
    monkeypatch.setenv("QT_PLUGIN_PATH", f"{BUNDLE}/PySide6/Qt/plugins")
    monkeypatch.setenv("GTK_PATH", f"{BUNDLE}/gtk")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/eigene.pem")  # gehört dem Nutzer – bleibt
    monkeypatch.setenv("PATH", os.pathsep.join([BUNDLE, "/usr/bin", "/bin"]))
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", BUNDLE)
    env = procutil.clean_env()
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib/eigene"
    assert "LD_LIBRARY_PATH_ORIG" not in env
    assert "QT_PLUGIN_PATH" not in env and "GTK_PATH" not in env
    assert env["SSL_CERT_FILE"] == "/etc/ssl/eigene.pem"
    assert env["PATH"] == os.pathsep.join(["/usr/bin", "/bin"])
    assert not any(k.startswith("_PYI_") for k in env)
    # ohne _ORIG: Variable ganz entfernen (der Normalfall – vorher war sie nicht gesetzt)
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    monkeypatch.setenv("LD_LIBRARY_PATH", BUNDLE)
    assert "LD_LIBRARY_PATH" not in procutil.clean_env()
    assert procutil.clean_env({"X": "1"})["X"] == "1"


def test_clean_env_unchanged_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/irgendwo")
    assert procutil.clean_env()["LD_LIBRARY_PATH"] == "/irgendwo"


_SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}


def _subprocess_calls(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
                and node.func.attr in _SUBPROCESS_FUNCS):
            yield node


def test_every_subprocess_call_uses_clean_env():
    """Quelltext-Check: kein externer Programmaufruf ohne env=clean_env()."""
    files = list(SRC.rglob("*.py"))
    assert len(files) > 20
    checked = 0
    for f in files:
        source = f.read_text("utf-8")
        tree = ast.parse(source)
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for call in _subprocess_calls(tree):
            checked += 1
            where = f"{f.relative_to(ROOT)}:{call.lineno}"
            env = next((k.value for k in call.keywords if k.arg == "env"), None)
            assert env is not None, f"{where}: subprocess-Aufruf ohne env=clean_env()"
            if isinstance(env, ast.Call):
                assert getattr(env.func, "id", getattr(env.func, "attr", "")) == "clean_env", where
            else:  # z. B. env=env – dann muss die Variable aus clean_env() stammen
                outer = [fn for fn in funcs if fn.lineno <= call.lineno <= fn.end_lineno]
                body = ast.get_source_segment(source, outer[-1]) if outer else ""
                assert "clean_env(" in body, f"{where}: env stammt nicht aus clean_env()"
        assert "os.system(" not in source, f.name
        assert "setOpenExternalLinks(True)" not in source, f"{f.name}: Links mit geerbter Umgebung"
        assert "QProcess" not in source, f"{f.name}: QProcess erbt die Umgebung des Programms"
        if "QDesktopServices" in source:
            assert f.name == "widgets.py", f"{f.name}: Links bitte über widgets.open_url öffnen"
    assert checked >= 15


def test_open_url_uses_xdg_open_with_clean_env_when_frozen(monkeypatch):
    from bonys_agents.gui import widgets
    calls = []
    monkeypatch.setattr(procutil, "is_frozen", lambda: True)
    monkeypatch.setattr(widgets.sys, "platform", "linux")
    monkeypatch.setattr(procutil, "open_external", lambda target: calls.append(target))
    widgets.open_url("https://example.org/")
    assert calls == ["https://example.org/"]


def test_spawn_detached_passes_clean_env(monkeypatch):
    seen = {}

    class FakePopen:
        def __init__(self, cmd, env=None, **kw):
            seen.update(cmd=cmd, env=env, kw=kw)

    monkeypatch.setattr(procutil.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(procutil, "clean_env", lambda extra=None: {"SAUBER": "1"})
    procutil.spawn_detached(["xdg-open", "x"])
    assert seen["env"] == {"SAUBER": "1"} and seen["cmd"] == ["xdg-open", "x"]


def test_terminal_command():
    which = {"gnome-terminal": "/usr/bin/gnome-terminal"}.get
    assert procutil.terminal_command(["ssh", "-p", "2222", "agent@127.0.0.1"], "linux", which) == \
        ["gnome-terminal", "--", "ssh", "-p", "2222", "agent@127.0.0.1"]
    only_xterm = {"xterm": "/usr/bin/xterm"}.get
    assert procutil.terminal_command(["ssh", "x"], "linux", only_xterm)[:2] == ["xterm", "-e"]
    with pytest.raises(RuntimeError):
        procutil.terminal_command(["ssh"], "linux", lambda name: None)
    assert procutil.terminal_command(["ssh", "a b"], "windows")[:3] == ["cmd.exe", "/c", "start"]


def test_spec_does_not_bundle_system_libraries():
    spec = (ROOT / "packaging" / "bonys-agents.spec").read_text("utf-8")
    for lib in ("libmount", "libblkid", "libselinux", "libpcre2", "libudev", "libsystemd", "libdbus",
                "libz.so", "libstdc++", "libgcc_s", "libffi"):
        assert f'"{lib}' in spec, lib
    deb = (ROOT / "packaging" / "linux" / "build-deb.sh").read_text("utf-8")
    for pkg in ("libmount1", "libblkid1", "libselinux1", "libpcre2-8-0", "libudev1", "libsystemd0",
                "libdbus-1-3", "zlib1g", "libstdc++6", "libgcc-s1", "libffi8"):
        assert pkg in deb, pkg


def test_selftest_command(monkeypatch, capsys):
    from bonys_agents import cli, selftest
    monkeypatch.setattr(selftest, "run", lambda log=None, include_qt=True, boot=False: [
        log(c) or c for c in (selftest.Check("qemu-system-x86_64 --version", True, "QEMU 9"),
                              selftest.Check("qemu-system-x86_64 öffnet das Seed-ISO", False, "libmount"))])
    assert cli.main(["selftest"]) == 1
    out = capsys.readouterr().out
    assert "OK" in out and "FEHLER" in out and "Ergebnis: FEHLER" in out


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="echtes QEMU nur unter Linux im Test")
def test_selftest_real_qemu_if_installed():
    from bonys_agents import qemu, selftest
    try:
        qemu.find_binary("qemu-system-x86_64", "linux")
    except qemu.QemuNotFound:
        pytest.skip("QEMU nicht installiert")
    results = selftest.run(include_qt=False, boot=True)
    assert selftest.passed(results), [(c.name, c.detail) for c in results if not c.ok]
    assert any(c.name.startswith("Agent-PC starten") for c in results)  # Startbefehl der App, bis QEMU läuft


# =========================================================== B) Wiederaufnahme der Einrichtung
def _sandbox_script(tmp_path, steps):
    """Einrichtungsskript, das ohne root in einem Testordner läuft (Systembefehle als Attrappen)."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in {"systemctl": "echo systemctl \"$@\" >> \"$CALLS\"", "dpkg": "exit 0",
                       "python3": "exit 1", "blkid": "exit 0", "chown": "exit 0"}.items():
        f = bindir / name
        f.write_text(f"#!/bin/sh\n{body}\n")
        f.chmod(0o755)
    script = cloudinit.render_provision(
        steps, "agent", state_dir=str(tmp_path / "state"), log_file=str(tmp_path / "bonys-agents.log"),
        home_base=str(tmp_path / "home"), apt_lock_conf=str(tmp_path / "apt-lock.conf"),
        console=str(tmp_path / "ttyS0"),
    )
    path = tmp_path / "provision.sh"
    path.write_text(script)
    (tmp_path / "ttyS0").write_text("")
    return path, {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "CALLS": str(tmp_path / "calls")}


def _run(path, env):
    return subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=60).stdout


@pytest.mark.skipif(os.name != "posix", reason="Bash-Skript")
def test_resume_after_abort_in_step_3_skips_steps_1_and_2(tmp_path):
    ran = tmp_path / "ran"
    steps = [(f"Schritt {i}", f"\necho {i} >> {ran}\n") for i in (1, 2)]
    # Schritt 3 bricht beim ersten Mal hart ab (wie ein beendetes QEMU) – beim zweiten Mal läuft er durch
    steps.append(("Schritt 3", f"\necho 3 >> {ran}\nif [ ! -f {tmp_path}/2.lauf ]; then kill -9 $PPID; fi\n"))
    steps.append(("Schritt 4", f"\necho 4 >> {ran}\n"))
    script, env = _sandbox_script(tmp_path, steps)

    first = _run(script, env)
    assert "BONYS-STEP 3/4 Schritt 3" in first and "BONYS-STEP 4/4" not in first
    assert cloudinit.READY_MARKER not in first
    state = tmp_path / "state"
    assert (state / "step-1.done").exists() and (state / "step-2.done").exists()
    assert not (state / "step-3.done").exists() and not (state / "ready").exists()

    (tmp_path / "2.lauf").write_text("")  # Neustart des Agent-PCs: der Dienst läuft erneut
    second = _run(script, env)
    assert "BONYS-RESUME Schritt 3" in second
    assert "BONYS-STEP 1/" not in second and "BONYS-STEP 2/" not in second
    assert "Schritt 1/4 bereits erledigt" in second
    assert "BONYS-STEP 3/4 Schritt 3" in second and "BONYS-STEP 4/4 Schritt 4" in second
    assert f'{cloudinit.READY_MARKER}' in second
    assert ran.read_text().split() == ["1", "2", "3", "3", "4"]  # 1 und 2 nur einmal
    assert (state / "ready").exists()
    calls = (tmp_path / "calls").read_text()
    assert f"disable {cloudinit.PROVISION_SERVICE}" in calls and "--no-block poweroff" in calls
    # Ausgabe landet auch auf der „seriellen Konsole“ und im Protokoll
    assert "BONYS-RESUME Schritt 3" in (tmp_path / "ttyS0").read_text()
    assert "BONYS-STEP 4/4" in (tmp_path / "bonys-agents.log").read_text()


@pytest.mark.skipif(os.name != "posix", reason="Bash-Skript")
def test_failed_step_is_retried_after_restart_and_setup_continues(tmp_path):
    steps = [("A", "\nfalse\n"), ("B", "\ntrue\n")]
    script, env = _sandbox_script(tmp_path, steps)
    out = _run(script, env)
    assert "WARNUNG: Schritt 'A' fehlgeschlagen" in out and cloudinit.READY_MARKER in out
    assert not (tmp_path / "state" / "step-1.done").exists()
    assert (tmp_path / "state" / "step-2.done").exists()


def test_provision_service_definition():
    doc = json.loads(cloudinit.user_data(_guest()).split("\n", 1)[1])
    files = {f["path"]: f for f in doc["write_files"]}
    unit = files[f"/etc/systemd/system/{cloudinit.PROVISION_SERVICE}"]["content"]
    assert "Type=oneshot" in unit and f"ExecStart={cloudinit.PROVISION_SCRIPT}" in unit
    assert "network-online.target cloud-init.target" in unit.split("After=")[1].splitlines()[0]
    assert "Wants=network-online.target" in unit
    # Ohne DefaultDependencies=no: multi-user.target → nach Dienst → nach cloud-init.target → nach
    # multi-user.target = Zyklus, systemd verwirft den Dienst ab dem zweiten Start (genau Fehler B)
    assert "DefaultDependencies=no" in unit and "Conflicts=shutdown.target" in unit
    assert f"ConditionPathExists=!{cloudinit.STATE_DIR}/ready" in unit  # läuft bei jedem Start bis READY
    assert "WantedBy=multi-user.target" in unit and "TimeoutStartSec=0" in unit
    assert files[cloudinit.PROVISION_SCRIPT]["permissions"] == "0755"
    # runcmd startet die Einrichtung nicht mehr selbst, sondern schaltet nur den Dienst ein
    assert doc["runcmd"] == [["systemctl", "daemon-reload"], ["systemctl", "enable", cloudinit.PROVISION_SERVICE],
                             ["systemctl", "start", "--no-block", cloudinit.PROVISION_SERVICE]]
    script = files[cloudinit.PROVISION_SCRIPT]["content"]
    assert f"systemctl disable {cloudinit.PROVISION_SERVICE}" in script  # deaktiviert sich selbst
    # erst alles auf die Platte, dann „erledigt“ – sonst bleiben nach einem harten Abbruch leere Dateien
    assert 'then sync; touch "$STATE/step-1.done"; sync;' in script and "dpkg --configure -a" in script
    assert 'DPkg::Lock::Timeout' in script and "apt-daily" in script
    assert "--or-update flathub org.telegram.desktop" in script  # Flatpak gefahrlos wiederholbar
    # Ausgabe über /dev/console (= ttyS0): offene Dateien auf /dev/ttyS0 macht agetty per vhangup() tot
    assert "OUT='/dev/console'" in script and "/dev/ttyS0" not in script
    assert "tee -a /var/log/bonys-agents-upgrade.log /dev/console" in apps.upgrade_script(["brave"], "agent")


def _guest():
    return cloudinit.GuestConfig(hostname="agent-pc", username="agent", password="geheim'1",
                                 apps=apps.resolve(["brave", "telegram", "hermes"]))


def test_strip_ansi_escape_sequences():
    raw = ("\x1b[0;32m  OK  \x1b[0m] Started Cloud-init\r\n\x1b[?7h\x1b[6n\x1b[?25lDebian login: "
           "\x1b]0;Titel\x07fertig\nLade 10 %\rLade 50 %\r\n\x1bc\x1b(B\x1b7Ende\x1b8\n")
    clean = pct.strip_ansi(raw)
    assert "\x1b" not in clean and "\r" not in clean
    assert clean.splitlines() == ["  OK  ] Started Cloud-init", "Debian login: fertig", "Lade 50 %", "Ende"]


def _fake_vm(name="t1"):
    p = vm.vms_dir() / name
    p.mkdir(parents=True)
    cfg = vm.VMConfig(name=name, arch="x86_64", cpus=2, ram_mb=2048, apps=["brave", "telegram", "hermes"],
                      first_boot_pending=True)
    (p / "vm.json").write_text(json.dumps(cfg.__dict__))
    return vm.VM(p)


def test_console_shown_without_escape_sequences(datadir):
    m = _fake_vm()
    m.console_log.write_bytes(b"\x1b[0;32mBONYS-STEP 2/5 Cinnamon\x1b[0m\r\n\x1b[6n")
    assert m.console_tail() == "BONYS-STEP 2/5 Cinnamon"
    p = m.progress()
    assert (p.step, p.title) == (2, "Cinnamon")


def test_app_progress_continues_after_restart(datadir, monkeypatch):
    m = _fake_vm()
    running = {"on": True}
    monkeypatch.setattr(vm.VM, "is_running", lambda self: running["on"])
    m.console_log.write_text("boot\nBONYS-STEP 1/5 Sprache\nBONYS-STEP 2/5 Cinnamon\nBONYS-STEP 3/5 Brave\nHolen: 1\n")
    before = m.progress()
    assert before.step == 3 and vm.get(m.name).config.setup_step == 3
    # QEMU hart beendet, neu gestartet: Konsole wird rotiert, Gast bootet erst
    running["on"] = False
    assert vm.get(m.name).status() == vm.STATUS_ABORTED
    assert vm.rotate_log(m.console_log) is not None
    running["on"] = True
    m.console_log.write_text("Linux version 6.12\nCloud-init v. 25 finished\n")
    booting = vm.get(m.name).progress()
    assert booting.resumed and booting.step == 3 and booting.title == "Brave"
    assert booting.percent == pytest.approx(pct.step_ranges(m.config.apps)[2][0])  # nicht zurück auf 18 %
    m.console_log.write_text(m.console_log.read_text() + "BONYS-RESUME Schritt 3\nBONYS-STEP 3/5 Brave\n")
    resumed = vm.get(m.name).progress()
    assert not resumed.resumed and resumed.resume_step == 3 and resumed.step == 3
    assert resumed.percent >= booting.percent


def test_seed_iso_kept_until_ready(datadir, monkeypatch):
    m = _fake_vm()
    m.seed_iso.write_bytes(b"seed")
    monkeypatch.setattr(vm.VM, "is_running", lambda self: False)
    m.console_log.write_text("BONYS-STEP 4/5 Telegram\n")
    m.progress()
    assert m.seed_iso.exists()  # Abbruch: Seed (mit Passwort) wird für die Fortsetzung gebraucht
    m.console_log.write_text("BONYS-RESUME Schritt 4\nBONYS-STEP 5/5 Hermes\nBONYS-AGENTS-READY\n")
    assert m.progress().ready and not m.seed_iso.exists()


def test_console_log_rotation(tmp_path):
    log = tmp_path / "console.log"
    assert vm.rotate_log(log) is None  # noch keine Konsole
    for i in range(8):
        log.write_text(f"Lauf {i}\n")
        rotated = vm.rotate_log(log, keep=5)
        assert rotated and rotated.read_text() == f"Lauf {i}\n" and not log.exists()
        os.utime(rotated, (time.time() + i, time.time() + i))
    old = sorted(tmp_path.glob("console-*.log"))
    assert len(old) == 5
    assert {f.read_text() for f in old} == {f"Lauf {i}\n" for i in range(3, 8)}  # die neuesten bleiben
    log.write_text("")
    assert vm.rotate_log(log) is None  # leere Konsole nicht aufbewahren


@pytest.mark.skipif(os.name != "posix", reason="nutzt eine Kopie von sleep als QEMU-Attrappe")
def test_launch_rotates_console_and_records_pid(datadir, monkeypatch, tmp_path):
    from test_core import _LINUX_HOST, _copy_as_qemu
    m = _fake_vm()
    m.console_log.write_text("alter Lauf\n")
    exe = _copy_as_qemu(tmp_path)
    monkeypatch.setattr(vm.host, "detect", lambda: _LINUX_HOST)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path(exe))
    monkeypatch.setattr(vm.qemu, "capabilities", lambda qb, cf=None: {"spice": False, "audio": [], "displays": []})
    monkeypatch.setattr(vm.qemu, "build_command", lambda spec: [exe, "5"])
    monkeypatch.setattr(vm.time, "sleep", lambda s: m.pidfile.write_text(str(vm._children and max(vm._children))))
    m._launch(headless=True)
    try:
        assert [f.read_text() for f in m.path.glob("console-*.log")] == ["alter Lauf\n"]
        assert m.runtime()["pid"] in vm._children
    finally:
        for proc in vm._children.values():
            proc.kill()
            proc.wait()
        vm._children.clear()


def test_abort_reasons():
    oom = "Out of memory: Killed process 4242 (qemu-system-x86) total-vm:9000000kB, anon-rss:7000000kB"
    info = diagnose.explain_abort(kernel_log=oom, pid=4242, started=100, boot_time=50)
    assert info.reason == "QEMU wurde beendet – vermutlich zu wenig Arbeitsspeicher."
    oom2 = "oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),task=qemu-system-x86,pid=99,uid=1000"
    assert "Arbeitsspeicher" in diagnose.explain_abort(kernel_log=oom2).reason
    oomd = "systemd-oomd: Killed /user.slice/app.scope due to memory pressure for /user.slice being 80% > 50%"
    assert "Arbeitsspeicher" in diagnose.explain_abort(kernel_log=oomd).reason
    other = "Out of memory: Killed process 77 (firefox)"
    assert "Arbeitsspeicher" not in diagnose.explain_abort(kernel_log=other, pid=4242).reason
    assert "neu gestartet" in diagnose.explain_abort(started=100, boot_time=200).reason
    assert "hart ausgeschaltet" in diagnose.explain_abort(powered_off=True, kernel_log=oom).reason
    sig = "qemu-system-x86_64: terminating on signal 15 from pid 1234 (/usr/bin/pkill)"
    assert diagnose.explain_abort(qemu_log=sig).reason == "QEMU wurde von außen beendet (SIGTERM von „/usr/bin/pkill“)."
    err = diagnose.explain_abort(qemu_log="qemu-system-x86_64: -drive …: Could not open 'disk.qcow2'")
    assert "Fehlermeldung" in err.reason and "Could not open" in err.detail
    assert "unbekannt" not in diagnose.explain_abort(console="reboot: Power down").reason
    assert "nicht bekannt" in diagnose.explain_abort().reason


def test_abort_reason_shown_and_cached(datadir, monkeypatch):
    m = _fake_vm()
    monkeypatch.setattr(vm.VM, "is_running", lambda self: False)
    m.console_log.write_text("BONYS-STEP 2/5 Cinnamon\n")
    m.runtime_file.write_text(json.dumps({"started": time.time(), "pid": 4242}))
    calls = []
    monkeypatch.setattr(vm.diagnose, "kernel_log", lambda since: calls.append(since) or
                        "Out of memory: Killed process 4242 (qemu-system-x86)")
    assert m.status() == vm.STATUS_ABORTED
    assert "Arbeitsspeicher" in m.abort_reason().reason
    assert "Arbeitsspeicher" in vm.get(m.name).abort_reason().reason
    assert len(calls) == 1  # einmal je Start ermittelt, danach aus runtime.json


def test_ram_suggestion_leaves_host_3_gb():
    from bonys_agents import host
    for ram in (6144, 8192, 12288):
        h = host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=ram, accel="tcg")
        assert h.ram_mb - h.default_vm_ram_mb >= 3072


def test_create_dialog_warns_without_acceleration():
    from PySide6.QtWidgets import QApplication, QLabel

    from bonys_agents import host
    from bonys_agents.gui.create_dialog import CreateDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dlg = CreateDialog(host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=8192, accel="tcg"))
    texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "mehrere Stunden" in texts and "verschachtelte Virtualisierung" in texts
    assert dlg.ram.maximum() * 512 <= 8192 - 3072


# =========================================================== D) Updates
def test_version_comparison_semver():
    v = updates.Version.parse
    assert v("v1.2.3") == v("1.2.3") and str(v("v1.2.3-rc.1")) == "1.2.3-rc.1"
    ordered = ["0.7.1", "0.8.0-alpha", "0.8.0-alpha.1", "0.8.0-alpha.beta", "0.8.0-beta", "0.8.0-beta.2",
               "0.8.0-beta.11", "0.8.0-rc.1", "0.8.0", "0.8.1", "0.10.0", "1.0.0"]
    for a, b in zip(ordered, ordered[1:], strict=False):
        assert v(a) < v(b), (a, b)
        assert updates.is_newer(b, a) and not updates.is_newer(a, b)
    assert not updates.is_newer("0.8.0+build.5", "0.8.0")  # Build-Metadaten zählen nicht
    assert v("kaputt") is None and not updates.is_newer("kaputt", "0.1.0")
    assert v("0.9.0-rc.1").prerelease and not v("0.9.0").prerelease


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
        assert timeout, "ohne Zeitlimit"
        if url not in routes:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        value = routes[url]
        if isinstance(value, Exception):
            raise value
        return _Resp(value if isinstance(value, bytes) else json.dumps(value).encode(), url)
    return opener


REPO = "bony/bonys-agents"
DL = f"https://github.com/{REPO}/releases/download"


def _release(tag="v0.9.0", prerelease=False, assets=()):
    return {"tag_name": tag, "name": f"Bony's Agents {tag}", "body": "- Neu: Updates", "prerelease": prerelease,
            "draft": False, "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
            "assets": [{"name": n, "browser_download_url": u, "size": 1} for n, u in assets]}


def test_update_check_finds_newer_version():
    latest = f"https://api.github.com/repos/{REPO}/releases/latest"
    info = updates.check("0.8.0", REPO, opener=_opener({latest: _release("v0.9.0")}))
    assert info.version == "0.9.0" and info.notes == "- Neu: Updates" and info.html_url.endswith("v0.9.0")
    assert updates.check("0.9.0", REPO, opener=_opener({latest: _release("v0.9.0")})) is None
    assert updates.check("0.8.0", REPO, skip_version="0.9.0", opener=_opener({latest: _release("v0.9.0")})) is None
    # Vorversionen nur mit „Testversionen anbieten“
    listing = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
    rels = [_release("v0.9.0"), _release("v1.0.0-rc.1", prerelease=True)]
    assert updates.check("0.8.0", REPO, prereleases=True, opener=_opener({listing: rels})).version == "1.0.0-rc.1"
    assert updates.check("0.8.0", REPO, opener=_opener({latest: _release("v1.0.0-rc.1", True)})) is None


@pytest.mark.parametrize("routes", [
    {},                                                                    # Repository gibt es nicht (404)
    {"https://api.github.com/repos/bony/bonys-agents/releases/latest": urllib.error.URLError("offline")},
    {"https://api.github.com/repos/bony/bonys-agents/releases/latest": TimeoutError("Zeitlimit")},
    {"https://api.github.com/repos/bony/bonys-agents/releases/latest": b"<html>kein JSON"},
    {"https://api.github.com/repos/bony/bonys-agents/releases/latest": {"message": "Not Found"}},
])
def test_no_updates_when_repository_unreachable(routes):
    assert updates.check("0.1.0", REPO, opener=_opener(routes)) is None


def test_placeholder_repository_gives_no_updates_without_crash():
    def offline(req, timeout=None):
        raise urllib.error.URLError("kein Netz im Test")
    assert updates.check("0.0.1", "DEIN-GITHUB-NAME/bonys-agents", opener=offline) is None
    assert updates.check("0.0.1", "kein gültiger name", opener=offline) is None


def test_auto_check_at_most_once_per_day(datadir):
    assert updates.auto_check_due(now=1_000_000)
    updates.set_setting("last", 1_000_000)
    assert not updates.auto_check_due(now=1_000_000 + 3600)
    assert updates.auto_check_due(now=1_000_000 + 25 * 3600)
    updates.set_setting("auto", False)
    assert not updates.auto_check_due(now=1_000_000 + 25 * 3600)


@pytest.fixture
def signed_release(tmp_path):
    """Release mit .deb, SHA256SUMS und minisign-Signatur – wie aus der Pipeline."""
    secret, key_id = b"\x11" * 32, b"BONYS-01"
    public = signing.PublicKey(key_id, signing.ed25519_public_key(secret)).text()
    deb = b"echtes Paket" * 1000
    name = "bonys-agents_0.9.0_amd64.deb"
    sums = f"{hashlib.sha256(deb).hexdigest()}  {name}\n{'0' * 64}  BonysAgents-Setup-0.9.0.exe\n".encode()
    sig = signing.sign(sums, secret, key_id, "Bony's Agents v0.9.0").encode()
    routes = {f"{DL}/v0.9.0/{name}": deb, f"{DL}/v0.9.0/SHA256SUMS": sums, f"{DL}/v0.9.0/SHA256SUMS.minisig": sig}
    info = updates._release(_release("v0.9.0", assets=[(n.rsplit("/", 1)[1], n) for n in routes]))
    return info, routes, public, name, (secret, key_id)


def test_download_verified_accepts_signed_file(signed_release, tmp_path):
    info, routes, public, name, _ = signed_release
    path = updates.download_verified(info, name, tmp_path / "dl", repo=REPO, public_key=public, opener=_opener(routes))
    assert path.read_bytes() == routes[f"{DL}/v0.9.0/{name}"]


def test_download_aborts_on_wrong_checksum(signed_release, tmp_path):
    info, routes, public, name, _ = signed_release
    routes[f"{DL}/v0.9.0/{name}"] = b"manipuliert"
    with pytest.raises(updates.UpdateError, match="Prüfsumme"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key=public, opener=_opener(routes))
    assert not list(tmp_path.glob("*.deb*"))  # nichts liegen lassen


def test_download_aborts_on_wrong_signature(signed_release, tmp_path):
    info, routes, public, name, (secret, key_id) = signed_release
    sums_url = f"{DL}/v0.9.0/SHA256SUMS"
    bad = dict(routes)
    bad[sums_url] = routes[sums_url] + f"{'1' * 64}  untergeschoben.deb\n".encode()  # Liste verändert
    with pytest.raises(updates.UpdateError, match="Signatur"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key=public, opener=_opener(bad))
    # Signatur von einem fremden Schlüssel
    other = signing.PublicKey(key_id, signing.ed25519_public_key(b"\x22" * 32)).text()
    with pytest.raises(updates.UpdateError, match="Signatur"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key=other, opener=_opener(routes))
    # echte Signatur, aber für eine andere Version (alte Datei untergeschoben)
    old = dict(routes)
    old[f"{DL}/v0.9.0/SHA256SUMS.minisig"] = signing.sign(routes[sums_url], secret, key_id,
                                                          "Bony's Agents v0.8.0").encode()
    with pytest.raises(updates.UpdateError, match="anderen Version"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key=public, opener=_opener(old))
    # ohne Signatur bzw. ohne eingebauten Schlüssel wird nie installiert
    unsigned = updates.UpdateInfo(info.version, info.tag, assets={k: v for k, v in info.assets.items()
                                                                  if k != "SHA256SUMS.minisig"})
    with pytest.raises(updates.UpdateError, match="nicht signiert"):
        updates.download_verified(unsigned, name, tmp_path, repo=REPO, public_key=public, opener=_opener(routes))
    with pytest.raises(updates.UpdateError, match="kein Signaturschlüssel"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key="", opener=_opener(routes))


def test_download_only_from_official_release_over_https(signed_release, tmp_path):
    info, routes, public, name, _ = signed_release
    foreign = updates.UpdateInfo(info.version, info.tag, assets={
        **info.assets, name: updates.Asset(name, f"https://evil.example/{name}")})
    with pytest.raises(updates.UpdateError, match="offiziellen Release"):
        updates.download_verified(foreign, name, tmp_path, repo=REPO, public_key=public, opener=_opener(routes))

    def http_redirect(req, timeout=None):
        return _Resp(b"", "http://objects.example/datei")
    with pytest.raises(updates.UpdateError, match="HTTPS"):
        updates.download_verified(info, name, tmp_path, repo=REPO, public_key=public, opener=http_redirect)


def test_minisign_signature_roundtrip_and_rfc8032_vector():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert signing.ed25519_public_key(sk).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert signing.ed25519_sign(sk, b"").hex().startswith("e5564300c360ac729086e2cc806e828a")
    # Signatur, wie sie minisign 0.11 erzeugt (Schlüssel und Datei aus einem echten Lauf)
    pub = "RWSoYo6zKqmQ53xGMQoD0Ol66IObO/Cb/AS5qeUo+jM0Jpu7kenP8fp3"
    sig = ("untrusted comment: signature from minisign secret key\n"
           "RUSoYo6zKqmQ52vzO7dY32j6FV4ZYNqu/6EjkNBksYmJGjZCqW7RTHVVwdMtCILpgD5ZBV6EI/OFwUIgqHM3MhkwrjUp/CEdCwU=\n"
           "trusted comment: Bony's Agents v9.9.9\n"
           "sb4aOrS0UpJ/bsnv4rAugfXH2ISFz0QwKRoRIWsQSPNLcGTvCYMho5d8Nlt3fVIiZ3h+XFOD7rMKL5yeD9tYCw==\n")
    data = (Path(__file__).parent / "data" / "SHA256SUMS").read_bytes()
    assert signing.verify(data, sig, pub) == "Bony's Agents v9.9.9"


def test_deb822_source_file():
    text = updates.apt_sources_text("Bony/bonys-agents")
    fields = dict(line.split(": ", 1) for line in text.splitlines() if line and not line.startswith("#"))
    assert fields == {"Types": "deb", "URIs": "https://bony.github.io/bonys-agents/apt/", "Suites": "stable",
                      "Components": "main", "Signed-By": "/usr/share/keyrings/bonys-agents.gpg"}
    assert text.endswith("\n") and "\n\n" not in text  # ein einziger Absatz (deb822)


def test_apt_source_detection(tmp_path):
    f = tmp_path / "bonys-agents.sources"
    assert not updates.apt_source_configured(f)
    f.write_text(updates.apt_sources_text(REPO), "utf-8")
    assert updates.apt_source_configured(f)
    f.write_text(updates.apt_sources_text(REPO) + "Enabled: no\n", "utf-8")
    assert not updates.apt_source_configured(f)


def test_deb_package_sets_up_and_removes_source():
    deb = (ROOT / "packaging" / "linux" / "build-deb.sh").read_text("utf-8")
    assert "/etc/apt/sources.list.d/bonys-agents.sources" in deb
    assert "remove|purge) rm -f /etc/apt/sources.list.d/bonys-agents.sources" in deb
    assert '/usr/share/keyrings/$PKG.gpg' in deb and "apt_sources_text" in deb


def test_install_scripts():
    assert "apt-get install -y --only-upgrade bonys-agents" in updates.apt_upgrade_script()
    assert "apt-get install -y '/tmp/x y/bonys-agents_0.9.0_amd64.deb'" in \
        updates.deb_install_script(PurePosixPath("/tmp/x y/bonys-agents_0.9.0_amd64.deb"))
    assert updates.asset_for("0.9.0", "linux", "x86_64") == "bonys-agents_0.9.0_amd64.deb"
    assert updates.asset_for("0.9.0", "linux", "aarch64") == "bonys-agents_0.9.0_arm64.deb"
    assert updates.asset_for("0.9.0", "windows", "x86_64") == "BonysAgents-Setup-0.9.0.exe"
    assert updates.asset_for("0.9.0", "macos", "aarch64") == "BonysAgents-0.9.0-macos-applesilicon.dmg"
    assert updates.asset_for("0.9.0", "macos", "x86_64") == "BonysAgents-0.9.0-macos-intel.dmg"


def test_macos_update_loads_dmg_for_this_chip(signed_release, tmp_path, monkeypatch):
    """macOS: die .dmg zum Chip laden – nur mit gültiger Signatur und Prüfsumme – und im Finder öffnen."""
    info, routes, public, _deb, (secret, key_id) = signed_release
    dmg = b"neue App" * 500
    name = "BonysAgents-0.9.0-macos-applesilicon.dmg"
    sums = f"{hashlib.sha256(dmg).hexdigest()}  {name}\n".encode()
    routes = {f"{DL}/v0.9.0/{name}": dmg, f"{DL}/v0.9.0/SHA256SUMS": sums,
              f"{DL}/v0.9.0/SHA256SUMS.minisig": signing.sign(sums, secret, key_id, "Bony's Agents v0.9.0").encode()}
    info = updates._release(_release("v0.9.0", assets=[(n.rsplit("/", 1)[1], n) for n in routes]))
    real = updates.download_verified
    monkeypatch.setattr(updates, "download_verified",
                        lambda i, n, d, opener=None: real(i, n, d, repo=REPO, public_key=public, opener=opener))
    opened = []
    monkeypatch.setattr(updates.subprocess, "Popen", lambda cmd, **kw: opened.append(cmd))
    path = updates.install_macos(info, "aarch64", log=lambda s: None, opener=_opener(routes), dest_dir=tmp_path)
    assert path == tmp_path / name and path.read_bytes() == dmg and opened == [["open", str(path)]]
    with pytest.raises(updates.UpdateError, match="keine Datei BonysAgents-0.9.0-macos-intel.dmg"):
        updates.install_macos(info, "x86_64", log=lambda s: None, opener=_opener(routes), dest_dir=tmp_path)


def test_cli_update_on_macos_opens_dmg(datadir, monkeypatch, capsys):
    from bonys_agents import cli
    info = updates.UpdateInfo("9.9.9", "v9.9.9", html_url="https://example/rel")
    monkeypatch.setattr(updates, "check", lambda **kw: info)
    monkeypatch.setattr(updates, "can_self_update", lambda host_os: True)
    monkeypatch.setattr(cli.host, "detect", lambda: vm.host.HostInfo("macos", "x86_64", 4, 8192, "hvf"))
    calls = []
    monkeypatch.setattr(updates, "install_macos", lambda i, arch, log: calls.append(arch) or "/x/a.dmg")
    monkeypatch.setattr("builtins.input", lambda q: "nein")
    assert cli.main(["update"]) == 1 and not calls  # erst fragen
    assert cli.main(["update", "-y"]) == 0 and calls == ["x86_64"]
    assert "Programme" in capsys.readouterr().out


def test_guest_upgrade_only_for_installed_tools():
    script = apps.upgrade_script(["brave", "telegram", "hermes"], "agent")
    assert "full-upgrade" in script and "flatpak update -y" in script
    assert "hermes update" in script
    assert "claude update" not in script and "openclaw update" not in script
    everything = apps.upgrade_script(list(apps.APPS), "agent")
    assert "claude update" in everything and "openclaw update" in everything
    # auch im Gast nur, wenn das Werkzeug wirklich da ist (Prüfbefehl vor dem Update)
    hermes = everything[everything.index("== Hermes Agent =="):]
    assert everything.index(apps.HERMES.check.replace("'", "'\"'\"'")) < everything.index("hermes update")
    assert "nicht installiert – übersprungen" in hermes
    assert "/var/run/reboot-required" in script and apps.REBOOT_MARKER in script
    assert "\nhermes update" not in script  # nie als root, immer als Agent-Benutzer
    assert all(not a.update or "su - \"$AGENT_USER\" -c" in everything for a in apps.APPS.values())


def test_vm_upgrade_reports_reboot(datadir, monkeypatch):
    m = _fake_vm()
    m.config.first_boot_pending, m.config.provisioned = False, True
    m.save()
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    m.runtime_file.write_text(json.dumps({"qga_port": 1}))
    seen = {}

    class GA:
        def __init__(self, port, timeout=5):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def execute(self, cmd, **kw):
            if cmd == "guest-exec":
                seen["script"] = kw["arg"][1]
                m.console_log.write_text("== Systempakete (apt) ==\n\x1b[0mfertig\n")
                return {"pid": 7}
            import base64
            out = base64.b64encode(f"{apps.REBOOT_MARKER}\n{apps.UPGRADE_DONE} 0\n".encode()).decode()
            return {"exited": True, "exitcode": 0, "out-data": out}

    monkeypatch.setattr(vm.qemu, "GuestAgent", GA)
    lines = []
    result = vm.get(m.name).upgrade(log=lines.append)
    assert result.ok and result.reboot_required
    assert "Neustart" in result.message(m.name)
    assert "== Systempakete (apt) ==" in lines and "fertig" in lines  # live aus der Konsole, ohne Steuerzeichen
    assert "hermes update" in seen["script"] and "claude update" not in seen["script"]


def test_upgrade_needs_password_without_guest_agent(datadir, monkeypatch):
    m = _fake_vm()
    m.config.first_boot_pending, m.config.provisioned = False, True
    m.save()
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)

    def no_agent(port, timeout=5):
        raise vm.qemu.GuestAgentError("nicht erreichbar")
    monkeypatch.setattr(vm.qemu, "GuestAgent", no_agent)
    with pytest.raises(vm.NeedsPassword):
        vm.get(m.name).upgrade()


def test_cli_update_check_without_repository(datadir, monkeypatch, capsys):
    from bonys_agents import cli
    monkeypatch.setattr(updates, "check", lambda **kw: None)
    assert cli.main(["update", "--check"]) == 0
    assert "Keine Updates gefunden" in capsys.readouterr().out


def test_cli_update_asks_before_installing(datadir, monkeypatch, capsys):
    from bonys_agents import cli
    info = updates.UpdateInfo("9.9.9", "v9.9.9", html_url="https://example/rel")
    monkeypatch.setattr(updates, "check", lambda **kw: info)
    monkeypatch.setattr(updates, "can_self_update", lambda host_os: True)
    monkeypatch.setattr(cli.host, "detect", lambda: vm.host.HostInfo("linux", "x86_64", 4, 8192, "kvm"))
    installed = []
    monkeypatch.setattr(updates, "install_linux", lambda *a, **kw: installed.append(a))
    monkeypatch.setattr("builtins.input", lambda q: "nein")
    assert cli.main(["update"]) == 1 and not installed  # ohne Zustimmung nichts installieren
    assert "nichts installiert" in capsys.readouterr().out
    assert cli.main(["update", "--check"]) == 0 and not installed
    assert cli.main(["update", "-y"]) == 0 and installed


def test_update_banner_and_menu():
    from PySide6.QtWidgets import QApplication

    from bonys_agents.gui.updates_ui import UpdateBanner
    app = QApplication.instance() or QApplication([])  # noqa: F841
    banner = UpdateBanner()
    assert banner.isHidden()
    banner.show_update(updates.UpdateInfo("9.9.9", "v9.9.9", notes="Neu"))
    assert not banner.isHidden() and "Version 9.9.9 ist verfügbar" in banner.text.text()
    texts = {b.text() for b in (banner.notes_btn, banner.install_btn, banner.later_btn)}
    assert texts == {"Was ist neu?", "Jetzt aktualisieren", "Später"}
    banner.later_btn.click()
    assert banner.isHidden()


@pytest.mark.skipif(os.name != "posix" or not __import__("shutil").which("tail"), reason="POSIX-Prozesse")
def test_qemu_counts_as_running_until_process_is_gone(datadir, tmp_path):
    """QEMU löscht die pidfile vor dem Ende – ein sofortiger Neustart mit Fenster scheiterte am SPICE-Port."""
    import shutil
    exe = tmp_path / "qemu-fake"
    shutil.copy(shutil.which("tail"), exe)
    m = _fake_vm()
    m.disk.write_bytes(b"")
    proc = subprocess.Popen([str(exe), "-f", str(m.disk)])
    try:
        m.runtime_file.write_text(json.dumps({"pid": proc.pid, "started": time.time()}))
        assert not m.pidfile.exists() and m.is_running()
        other = _fake_vm("t2")  # gleiche PID, aber nicht seine Festplatte: gehört nicht zu ihm
        other.runtime_file.write_text(json.dumps({"pid": proc.pid, "started": time.time()}))
        assert not other.is_running()
    finally:
        proc.kill()
        proc.wait()
    assert not m.is_running()


def test_launch_waits_for_fixed_ports(monkeypatch):
    busy = {"n": 3}

    def port_free(port):
        busy["n"] -= 1
        return busy["n"] <= 0
    monkeypatch.setattr(vm.remote, "port_free", port_free)
    monkeypatch.setattr(vm.time, "sleep", lambda s: None)
    assert vm._wait_port_free(5901) and busy["n"] == 0


# =========================================================== Start nur von der Systemplatte (kein PXE)
@pytest.mark.parametrize("arch,accel", [("x86_64", "kvm"), ("x86_64", "tcg"), ("aarch64", "hvf")])
def test_boot_only_from_system_disk_without_network_rom(arch, accel):
    from bonys_agents import qemu
    spec = qemu.LaunchSpec(
        qemu_bin=Path("/usr/bin/qemu"), arch=arch, accel=accel, name="t", cpus=2, ram_mb=2048,
        disk=Path("/vms/t/disk.qcow2"), qmp_port=1, ssh_port=2, serial_log=Path("/vms/t/console.log"),
        pidfile=Path("/vms/t/qemu.pid"), seed_iso=Path("/vms/t/seed.iso"),
        firmware=Path("/usr/share/AAVMF/AAVMF_CODE.fd") if arch == "aarch64" else None,
    )
    cmd = qemu.build_command(spec)
    args = " ".join(cmd)
    devices = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-device"]
    drives = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-drive"]
    # Systemplatte: erstes und einziges Startgerät
    assert f"if=none,id=disk0,file={Path('/vms/t/disk.qcow2')},format=qcow2,discard=unmap" in drives
    assert "virtio-blk-pci,drive=disk0,bootindex=0" in devices
    assert cmd[cmd.index("-boot") + 1] == "strict=on,menu=off"
    # Netzwerkkarte ohne Boot-ROM (kein iPXE/PXE)
    assert f"virtio-net-pci,netdev={qemu.NETDEV},romfile=" in devices
    # Seed-ISO nie als Startgerät, kein Laufwerk mehr über if=virtio (dort fehlte die Reihenfolge)
    assert "virtio-blk-pci,drive=seed0" in devices
    assert args.count("bootindex=") == 1 and "if=virtio" not in args
    assert ("-bios" in cmd) == (arch == "aarch64")  # x86: SeaBIOS (Standard), ARM64: UEFI ist Pflicht
