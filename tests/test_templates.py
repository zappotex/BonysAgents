# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen: Verallgemeinern, Liste der gelöschten Pfade, Backing-File-Kette, Löschschutz, Export/Import."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from bonys_agents import cli, cloudinit, qemu, storage, templates, vm

QEMU_IMG = shutil.which("qemu-img")
needs_qemu_img = pytest.mark.skipif(QEMU_IMG is None, reason="qemu-img nicht installiert")
needs_bash = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="braucht bash")
# Das Skript läuft im Debian-Gast (GNU coreutils, z. B. rm --one-file-system) – ausführen nur unter Linux
needs_gnu = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="braucht GNU coreutils")


# ---------- Verallgemeinern: Befehle und Pfade ----------
def test_generalize_script_contains_system_cleanup():
    s = cloudinit.generalize_script("agent")
    for cmd in ("cloud-init clean --logs --seed --machine-id", "truncate -s 0 /etc/machine-id",
                "rm -f /etc/ssh/ssh_host_*", "apt-get clean", "fstrim -av", "/root/.bash_history",
                '"$H/.bash_history"', "find /var/log -type f", cloudinit.HOSTKEY_SERVICE):
        assert cmd in s, cmd
    # erst die Sitzung beenden, dann löschen, ganz am Ende nullen
    assert s.index("loginctl terminate-user") < s.index("wipe_except \"$H/.hermes\"") < s.index("fstrim")
    assert s.rstrip().endswith('echo "BONYS-GENERALIZED"')


def test_personal_data_list_covers_required_paths():
    paths = cloudinit.personal_data_paths("agent")
    joined = "\n".join(paths)
    for p in ("/home/agent/.var/app/org.telegram.desktop", "/home/agent/.config/BraveSoftware",
              "/home/agent/.hermes", "/home/agent/.openclaw", "/home/agent/.claude", "/home/agent/.claude.json",
              "/home/agent/.ssh", "/home/agent/.git-credentials", "/home/agent/.local/share/keyrings",
              "/home/agent/.config/obsidian", "/home/agent/Agent-Notizen"):
        assert p in joined, p
    # Programme bleiben: Hermes und OpenClaw nur mit Ausnahmen
    hermes = next(i for i in cloudinit.PERSONAL_DATA if ".hermes" in i.paths)
    assert {"hermes-agent", "tools", "installs"} <= set(hermes.keep)
    openclaw = next(i for i in cloudinit.PERSONAL_DATA if ".openclaw" in i.paths)
    assert {"bin", "tools", "lib"} <= set(openclaw.keep)


def test_keep_personal_data_leaves_home_alone():
    s = cloudinit.generalize_script("agent", remove_personal=False)
    assert "org.telegram.desktop" not in s and "BraveSoftware" not in s and ".hermes" not in s
    assert "cloud-init clean" in s  # System wird trotzdem verallgemeinert


@needs_gnu
@pytest.mark.parametrize("dry", [False, True])
def test_generalize_personal_part_runs(tmp_path, dry):
    """Persönlichen Teil wirklich ausführen – in einem Spiel-Home, mit harmlosen Ersatzbefehlen."""
    home = tmp_path / "home"
    files = {
        ".var/app/org.telegram.desktop/data/TelegramDesktop/tdata/key": "x",
        ".config/BraveSoftware/Brave-Browser/Default/Login Data": "x",
        ".hermes/.env": "OPENAI_API_KEY=geheim", ".hermes/config.yaml": "x", ".hermes/memories/m.md": "x",
        ".hermes/hermes-agent/hermes": "programm", ".hermes/tools/node/bin/node": "programm",
        ".hermes/installs/a/b": "programm", ".hermes/skills/x/SKILL.md": "x",
        ".openclaw/openclaw.json": "x", ".openclaw/credentials/c.json": "x", ".openclaw/.bonys-eingerichtet": "",
        ".openclaw/bin/openclaw": "programm", ".openclaw/tools/node/lib/x": "programm",
        ".claude/.credentials.json": "x", ".claude.json": "x", ".ssh/id_ed25519": "x",
        ".git-credentials": "x", ".gitconfig": "x", "Downloads/rechnung.pdf": "x", "Schreibtisch/brave.desktop": "x",
        ".bashrc": "bleibt", ".config/obsidian/obsidian.json": "tresore", ".config/obsidian/Local Storage/x": "x",
        "Agent-Notizen/Geheim.md": "x", "Agent-Notizen/.obsidian/app.json": "x",
    }
    for rel, content in files.items():
        f = home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    script = cloudinit.generalize_script("niemand-hier", dry_run=dry)
    script = script.replace("H='/home/niemand-hier'", f"H='{home}'")
    script = script.split('echo "== System =="')[0]  # nur der persönliche Teil
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for cmd in ("systemctl", "loginctl", "pkill", "sleep"):
        (stubs / cmd).write_text("#!/bin/sh\nexit 0\n")
        (stubs / cmd).chmod(0o755)
    env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=True).stdout
    gone = [".var/app/org.telegram.desktop", ".config/BraveSoftware", ".hermes/.env", ".hermes/config.yaml",
            ".hermes/memories", ".openclaw/openclaw.json", ".openclaw/credentials", ".openclaw/.bonys-eingerichtet",
            ".claude", ".claude.json", ".ssh", ".git-credentials", ".gitconfig", "Downloads/rechnung.pdf",
            ".config/obsidian/Local Storage", "Agent-Notizen/Geheim.md", "Agent-Notizen/.obsidian"]
    kept = [".hermes/hermes-agent/hermes", ".hermes/tools/node/bin/node", ".hermes/installs/a/b",
            ".hermes/skills/x/SKILL.md", ".openclaw/bin/openclaw", ".openclaw/tools/node/lib/x",
            "Schreibtisch/brave.desktop", ".bashrc", "Downloads", ".config/obsidian/obsidian.json", "Agent-Notizen"]
    for rel in kept:
        assert (home / rel).exists(), rel
    for rel in gone:
        assert (home / rel).exists() == dry, rel
    if dry:
        assert f"WÜRDE LÖSCHEN: {home}/.hermes/.env" in out and f"BLEIBT: {home}/.hermes/tools" in out
        assert "gelöscht:" not in out
    else:
        assert f"gelöscht: {home}/.ssh" in out


@needs_bash
def test_generalize_scripts_are_valid_bash():
    for remove in (True, False):
        for dry in (True, False):
            subprocess.run(["bash", "-n"], input=cloudinit.generalize_script("agent", remove, dry), text=True,
                           check=True)
    subprocess.run(["sh", "-n"], input=cloudinit.clone_firstboot_script(), text=True, check=True)


def test_clone_user_data_only_sets_identity():
    ud = cloudinit.clone_user_data("klon-1", "agent", "pw'1")
    doc = json.loads(ud.split("\n", 1)[1])
    assert doc["hostname"] == "klon-1" and doc["users"] == []  # kein neuer Benutzer, keine Einrichtung
    assert doc["chpasswd"]["users"] == [{"name": "agent", "password": "pw'1", "type": "text"}]
    assert doc["growpart"]["mode"] == "auto" and doc["runcmd"] == [[cloudinit.CLONE_SCRIPT]]
    assert cloudinit.PROVISION_SCRIPT not in ud
    # Fertig-Marke erscheint auf der Konsole ohne Anführungszeichen – nur das zählt als „fertig“
    script = cloudinit.clone_firstboot_script()
    assert "ssh-keygen -A" in script and cloudinit.GROWROOT_SCRIPT in script
    printed = re.search(r'echo "(.*?)" >', script).group(1)
    assert re.search(rf'(?<!"){cloudinit.READY_MARKER}(?!")', printed)


# ---------- qcow2: Backing-File lesen ----------
def test_backing_file_parser_without_qemu_img(tmp_path):
    name = b"../_templates/basis/disk.qcow2"
    head = b"QFI\xfb" + (3).to_bytes(4, "big") + (104).to_bytes(8, "big") + len(name).to_bytes(4, "big")
    disk = tmp_path / "vm" / "disk.qcow2"
    disk.parent.mkdir()
    disk.write_bytes(head.ljust(104, b"\0") + name)
    assert qemu.backing_file(disk) == disk.parent / name.decode()
    disk.write_bytes(b"QFI\xfb" + b"\0" * 100)
    assert qemu.backing_file(disk) is None
    assert qemu.backing_file(tmp_path / "fehlt.qcow2") is None


# ---------- echte Abbilder mit qemu-img ----------
def _use_real_qemu_img(monkeypatch):
    monkeypatch.setattr(qemu, "find_binary",
                        lambda name, os_: Path(QEMU_IMG) if name == "qemu-img" else Path("/bin/true"))


def _make_template(library: Path, name="basis", size_gb=32, **kw) -> templates.Template:
    d = templates.templates_dir(library) / name
    d.mkdir(parents=True)
    subprocess.run([QEMU_IMG, "create", "-q", "-f", "qcow2", str(d / "disk.qcow2"), f"{size_gb}G"], check=True)
    t = templates.Template(path=d, name=name, description="Test", created="2026-10-06T10:00:00+00:00",
                           arch=vm.host.detect().arch, apps=["brave", "telegram"], disk_gb=size_gb,
                           size=(d / "disk.qcow2").stat().st_size, source="agent-pc-1", **kw)
    t.save()
    return t


@needs_qemu_img
def test_clone_linked_and_full(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    lib = vm.vms_dir()
    t = _make_template(lib)
    assert [x.name for x in templates.list_templates()] == ["basis"]

    linked = vm.create("schnell", "pw1234", template="basis")  # gleiches Laufwerk → verknüpft
    assert linked.is_linked() and linked.backing_file().resolve() == t.disk.resolve()
    assert linked.config.template == "basis" and linked.config.apps == ["brave", "telegram"]
    assert not linked.config.first_boot_pending and not linked.config.provisioned  # startet gleich mit Fenster
    assert linked.seed_iso.exists()
    # relativer Verweis: übersteht einen anderen Einhängepunkt
    info = json.loads(qemu._run_img([QEMU_IMG, "info", "--output=json", str(linked.disk)]))
    assert info["backing-filename"] == "../_templates/basis/disk.qcow2"
    assert [m.name for m in t.linked_vms()] == ["schnell"]

    full = vm.create("kopie", "pw1234", template="basis", linked=False, disk_gb=48)
    assert not full.is_linked() and full.config.disk_gb == 48
    assert qemu.virtual_size(Path(QEMU_IMG), full.disk) == 48 * storage.GB
    gross = _make_template(lib, "gross", 64)
    with pytest.raises(ValueError, match="mindestens"):
        vm.create("zu-klein", "pw1234", template=gross.name, disk_gb=48)

    # Fertig-Marke vom ersten Start → Seed (mit Passwort) wird gelöscht
    linked.console_log.write_text(f"...\n{cloudinit.READY_MARKER}\n")
    assert linked.progress().ready and linked.config.provisioned and not linked.seed_iso.exists()


@needs_qemu_img
def test_linked_vm_without_template_is_unavailable(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    usb = tmp_path / "usb" / "BonysAgents"
    t = _make_template(usb)
    storage.add_location(usb)
    m = vm.create("abhaengig", "pw1234", template="basis", location=usb)
    assert m.status() == "gestoppt"
    shutil.rmtree(t.path)  # wie: Laufwerk mit der Vorlage abgezogen
    assert m.template_missing() and m.status() == vm.STATUS_TEMPLATE_MISSING
    with pytest.raises(RuntimeError, match="Vorlage"):
        m.start()
    with pytest.raises(RuntimeError, match="Vorlage"):
        vm.move("abhaengig", tmp_path / "anderswo")


@needs_qemu_img
def test_delete_blocked_while_linked_then_make_independent(datadir, monkeypatch):
    _use_real_qemu_img(monkeypatch)
    _make_template(vm.vms_dir())
    m = vm.create("klon", "pw1234", template="basis")
    with pytest.raises(templates.LinkedVMsError) as err:
        templates.delete("basis")
    assert [x.name for x in err.value.machines] == ["klon"]
    m.make_independent()
    assert not m.is_linked()
    templates.delete("basis")
    assert templates.list_templates() == []
    assert vm.get("klon").status() == "gestoppt"  # funktioniert ohne Vorlage weiter


@needs_qemu_img
def test_move_linked_vm(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    lib = vm.vms_dir()
    t = _make_template(lib)
    vm.create("wanderer", "pw1234", template="basis")
    # gleiches Laufwerk, anderer Ordner: Verweis wird angepasst, bleibt verknüpft
    moved = vm.move("wanderer", tmp_path / "anderer-ordner")
    assert moved.is_linked() and moved.backing_file().resolve() == t.disk.resolve()
    # anderes Laufwerk: wird automatisch unabhängig
    assert vm.move_makes_independent(moved, tmp_path / "ssd") is False  # hier gleiches Gerät
    monkeypatch.setattr(vm, "_same_device", lambda a, b: False)
    notes = []
    far = vm.move("wanderer", tmp_path / "ssd", progress=lambda ph, f, msg: notes.append(msg))
    assert not far.is_linked() and "unabhängige Kopie" in notes[-1]
    subprocess.run([QEMU_IMG, "check", "-q", str(far.disk)], check=True)


@needs_qemu_img
def test_rename_keeps_linked_vms_working(datadir, monkeypatch):
    _use_real_qemu_img(monkeypatch)
    _make_template(vm.vms_dir())
    m = vm.create("klon", "pw1234", template="basis")
    templates.rename("basis", "neu")
    m = vm.get("klon")
    assert not m.template_missing() and m.backing_file().resolve() == templates.get("neu").disk.resolve()
    assert m.config.template == "neu"


@needs_qemu_img
def test_export_import_roundtrip(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    t = _make_template(vm.vms_dir(), personal_data_removed=True)
    steps = []
    out = templates.export("basis", tmp_path / "weitergabe", progress=lambda *a: steps.append(a[1]))
    assert out.name == "weitergabe.bonys-template" and steps and steps[-1] == 1.0
    with tarfile.open(out) as tar:
        assert sorted(tar.getnames()) == ["disk.qcow2", "template.json"]
    info = templates.read_export_info(out)
    assert info.name == "basis" and info.source == "agent-pc-1"
    with pytest.raises(FileExistsError):
        templates.import_file(out)
    other = tmp_path / "anderer-pc" / "BonysAgents"
    imported = templates.import_file(out, location=other, name="basis-2")
    assert imported.path == other / "_templates" / "basis-2"
    assert imported.disk.read_bytes() == t.disk.read_bytes()
    assert {x.name for x in templates.list_templates()} == {"basis", "basis-2"}


def test_import_rejects_foreign_tar(datadir, tmp_path):
    bad = tmp_path / "boese.bonys-template"
    payload = tmp_path / "x"
    payload.write_text("x")
    with tarfile.open(bad, "w") as tar:
        tar.add(payload, arcname="template.json")
        tar.add(payload, arcname="../../etc/disk.qcow2")
    with pytest.raises(ValueError, match="gültige"):
        templates.import_file(bad)


@needs_qemu_img
def test_create_template_from_overlay_leaves_original_untouched(datadir, monkeypatch):
    """Ablauf ohne echtes QEMU: Überlagerung, „Verallgemeinern“, Komprimieren, Prüfen, Aufräumen."""
    _use_real_qemu_img(monkeypatch)
    src = vm.vms_dir() / "agent-pc-1"
    src.mkdir(parents=True)
    subprocess.run([QEMU_IMG, "create", "-q", "-f", "qcow2", str(src / "disk.qcow2"), "32G"], check=True)
    cfg = vm.VMConfig(name="agent-pc-1", arch="x86_64", cpus=2, ram_mb=2048, disk_gb=32, provisioned=True,
                      apps=["brave", "hermes"])
    (src / "vm.json").write_text(json.dumps(cfg.__dict__))
    before = hashlib.sha256((src / "disk.qcow2").read_bytes()).hexdigest()
    seen = {}

    class FakeCopy:
        def __init__(self, path):
            self.path = path

        def stop(self, timeout=0):
            seen["stopped"] = True

        def power_off(self):
            seen["power_off"] = True

    def start(machine, work):
        seen["locked"] = (machine.path / vm.TEMPLATE_LOCK).exists()
        with pytest.raises(RuntimeError, match="Vorlage"):
            vm.get("agent-pc-1").start()  # Original gesperrt, solange die Kopie darauf aufbaut
        work.mkdir(parents=True)
        qemu.create_overlay(Path(QEMU_IMG), machine.disk, work / "disk.qcow2")
        return FakeCopy(work)

    def run(copy, script, password, has_agent, timeout):
        seen["script"] = script
        # Gast schreibt in die Kopie – das Original darf das nicht merken
        subprocess.run([QEMU_IMG, "resize", "-q", str(copy.path / "disk.qcow2"), "33G"], check=True)
        return "BONYS-DEBIAN 13.1\ngelöscht: /home/agent/.ssh\nBONYS-GENERALIZED\n"

    monkeypatch.setattr(templates, "_start_work_copy", start)
    monkeypatch.setattr(templates, "_wait_guest_agent", lambda copy, progress: True)
    monkeypatch.setattr(templates, "_run_in_copy", run)
    log = []
    t = templates.create("agent-pc-1", "frisch", "Brave und Hermes", log=log.append)
    assert seen["locked"] and seen["stopped"] and "cloud-init clean" in seen["script"]
    assert t.path == vm.vms_dir() / "_templates" / "frisch" and t.disk.exists()
    assert (t.debian, t.source, t.apps, t.disk_gb) == ("13.1", "agent-pc-1", ["brave", "hermes"], 32)
    assert json.loads((t.path / "template.json").read_text())["description"] == "Brave und Hermes"
    assert qemu.backing_file(t.disk) is None  # eigenständig
    assert "gelöscht: /home/agent/.ssh" in log
    assert hashlib.sha256((src / "disk.qcow2").read_bytes()).hexdigest() == before
    assert not (src / vm.TEMPLATE_LOCK).exists()
    assert sorted(p.name for p in t.path.parent.iterdir()) == ["frisch"]  # Arbeitskopie weg
    assert vm.get("agent-pc-1").template_lock_pid() is None
    with pytest.raises(FileExistsError):
        templates.create("agent-pc-1", "frisch")


def test_create_template_needs_finished_and_stopped_vm(datadir, monkeypatch):
    p = vm.vms_dir() / "halb"
    p.mkdir(parents=True)
    (p / "vm.json").write_text(json.dumps(vm.VMConfig(name="halb", arch="x86_64", cpus=1, ram_mb=2048,
                                                      first_boot_pending=True).__dict__))
    with pytest.raises(RuntimeError, match="fertig eingerichtet"):
        templates.create("halb", "v")
    with pytest.raises(ValueError):
        templates.create("halb", "ungültig name")


def test_cli_parses_template_commands():
    p = cli.build_parser()
    a = p.parse_args(["template", "create", "agent-pc-1", "basis", "--keep-personal-data"])
    assert (a.vm, a.name, a.keep_personal_data, a.func) == ("agent-pc-1", "basis", True, cli.cmd_template_create)
    a = p.parse_args(["template", "export", "basis", "/tmp/x.bonys-template"])
    assert a.func == cli.cmd_template_export
    a = p.parse_args(["create", "neu", "--template", "basis", "--full"])
    assert a.template == "basis" and a.full and not a.linked and a.disk is None
    with pytest.raises(SystemExit):
        p.parse_args(["create", "neu", "--template", "basis", "--full", "--linked"])
    assert cli.main(["create", "neu", "--linked"]) == 2  # nur mit --template
