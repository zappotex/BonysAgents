# SPDX-License-Identifier: GPL-3.0-or-later
import json
import re
import sys
from pathlib import Path, PurePosixPath

import pycdlib
import pytest

from bonys_agents import apps, cli, cloudinit, host, qemu, screen, vm


# ---------- host ----------
def test_ram_reserve_keeps_host_alive():
    h = host.HostInfo(os="linux", arch="x86_64", cpus=8, ram_mb=16384, accel="kvm")
    assert h.max_vm_ram_mb == 16384 - 4096
    small = host.HostInfo(os="linux", arch="x86_64", cpus=2, ram_mb=4096, accel="tcg")
    assert small.max_vm_ram_mb == 2048
    assert not small.accel_is_fast


def test_detect_returns_sane_values():
    h = host.detect()
    assert h.cpus >= 1 and h.ram_mb > 0
    assert h.arch in ("x86_64", "aarch64")


# ---------- qemu ----------
def _spec(**kw):
    base = dict(
        qemu_bin=PurePosixPath("/usr/bin/qemu-system-x86_64"), arch="x86_64", accel="kvm", name="t",
        cpus=4, ram_mb=4096, disk=PurePosixPath("/tmp/d,isk.qcow2"), qmp_port=4444, ssh_port=2222,
        serial_log=PurePosixPath("/tmp/c.log"), pidfile=PurePosixPath("/tmp/p"),
    )
    base.update(kw)
    return qemu.LaunchSpec(**base)


def test_command_x86_kvm_has_fallback_and_resources():
    cmd = qemu.build_command(_spec())
    joined = " ".join(cmd)
    assert cmd[cmd.index("-accel") + 1] == "kvm"
    assert "tcg,thread=multi" in cmd
    assert cmd[cmd.index("-smp") + 1] == "4"
    assert cmd[cmd.index("-m") + 1] == "4096"
    assert "file=/tmp/d,,isk.qcow2" in joined  # Komma maskiert
    assert "hostfwd=tcp:127.0.0.1:2222-:22" in joined
    assert "-display" not in cmd


def test_command_whpx_and_headless():
    cmd = qemu.build_command(_spec(accel="whpx", headless=True))
    assert "whpx,kernel-irqchip=off" in cmd
    assert cmd[cmd.index("-display") + 1] == "none"


def test_command_aarch64_needs_firmware():
    with pytest.raises(ValueError):
        qemu.build_command(_spec(arch="aarch64", accel="hvf"))
    cmd = qemu.build_command(_spec(arch="aarch64", accel="hvf", firmware=PurePosixPath("/fw.fd")))
    assert "virt" in cmd and "host" in cmd and "/fw.fd" in cmd


# ---------- cloud-init ----------
def _guest():
    return cloudinit.GuestConfig(
        hostname="agent-pc", username="agent", password="geheim'1",
        apps=apps.resolve(["brave", "telegram", "hermes"]),
    )


def test_user_data_is_valid_and_contains_apps():
    ud = cloudinit.user_data(_guest())
    assert ud.startswith("#cloud-config\n")
    doc = json.loads(ud.split("\n", 1)[1])
    assert doc["users"][0]["name"] == "agent"
    script = doc["write_files"][0]["content"]
    assert "brave-browser" in script and "org.telegram.desktop" in script
    assert "hermes-agent.nousresearch.com/install.sh" in script
    assert "BONYS-STEP 5/5" in script
    assert f'echo "{cloudinit.READY_MARKER}"' in script
    assert script.index('touch "$STATE/ready"') < script.index(f'echo "{cloudinit.READY_MARKER}"')


def test_seed_iso_has_cidata_label(tmp_path):
    iso_path = tmp_path / "seed.iso"
    cloudinit.write_seed_iso(iso_path, _guest(), "test-id")
    iso = pycdlib.PyCdlib()
    iso.open(str(iso_path))
    assert iso.pvd.volume_identifier.decode().strip() == "cidata"
    names = {c.file_identifier().decode("utf-16-be") for c in iso.list_children(joliet_path="/")}
    assert {"user-data", "meta-data"} <= names
    iso.close()


def test_unknown_app_rejected():
    with pytest.raises(ValueError):
        apps.resolve(["brave", "gibtsnicht"])


# ---------- vm ----------
def _fake_vm(datadir, name="t1"):
    p = vm.vms_dir() / name
    p.mkdir(parents=True)
    cfg = vm.VMConfig(name=name, arch="x86_64", cpus=2, ram_mb=2048, apps=["brave", "telegram", "hermes"])
    (p / "vm.json").write_text(json.dumps(cfg.__dict__))
    return vm.VM(p)


def test_progress_parsing_and_seed_cleanup(datadir):
    m = _fake_vm(datadir)
    m.seed_iso.write_bytes(b"x")
    m.console_log.write_text("boot...\nBONYS-STEP 1/5 Sprache\nfoo\nBONYS-STEP 3/5 Brave Browser installieren\n")
    p = m.progress()
    assert (p.step, p.total, p.title, p.ready) == (3, 5, "Brave Browser installieren", False)
    m.console_log.write_text(m.console_log.read_text() + "BONYS-AGENTS-READY\r\n")
    assert m.progress().ready
    assert vm.get("t1").config.provisioned
    assert not m.seed_iso.exists()
    assert m.status() == "gestoppt"


def test_create_validates_input(datadir):
    with pytest.raises(ValueError):
        vm.create("bad name!", "pw1234")
    with pytest.raises(ValueError):
        vm.create("ok", "x")


def test_create_builds_vm(datadir, monkeypatch, tmp_path):
    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    steps = []
    m = vm.create("agent1", "pw1234", cpus=999, disk_gb=50, progress=lambda *a: steps.append(a[0]))
    assert m.config.cpus == host.detect().cpus  # auf Host-Kerne begrenzt
    assert m.config.disk_gb == 50
    assert m.seed_iso.exists() and m.disk.exists()
    assert m.config.first_boot_pending
    assert steps[-1] == "done"
    with pytest.raises(FileExistsError):
        vm.create("agent1", "pw1234")
    assert [x.name for x in vm.list_vms()] == ["agent1"]


# ---------- cli ----------
def test_cli_list_and_help(datadir, capsys):
    assert cli.main(["list"]) == 0
    assert "Noch keine Agent-PCs" in capsys.readouterr().out
    assert cli.main(["apps"]) == 0
    assert "hermes" in capsys.readouterr().out
    assert cli.main(["status", "gibtsnicht"]) == 1


# ---------- Debian-Image ----------
def test_debian_image_urls():
    from bonys_agents import images
    a = images.debian_image("x86_64")
    assert a.filename == "debian-13-generic-amd64.qcow2"
    assert a.url.startswith("https://cloud.debian.org/images/cloud/trixie/latest/")
    assert a.sums_url.endswith("/SHA512SUMS") and a.hash_algo == "sha512"
    assert images.debian_image("aarch64").filename == "debian-13-generic-arm64.qcow2"


def test_parse_sums():
    from bonys_agents import images
    text = "aaa  debian-13-genericcloud-amd64.qcow2\nbbb  debian-13-generic-amd64.qcow2\n"
    assert images.parse_sums(text, "debian-13-generic-amd64.qcow2") == "bbb"
    with pytest.raises(RuntimeError):
        images.parse_sums(text, "fehlt.qcow2")


def test_script_sets_up_cinnamon_german():
    script = cloudinit.provision_script(_guest())
    assert "cinnamon-core" in script and "autologin-session=cinnamon" in script
    assert 'DESKTOP_DIR="$AGENT_HOME/Schreibtisch"' in script
    assert "de_DE.UTF-8" in script


def test_git_installed_before_hermes():
    script = cloudinit.provision_script(_guest())
    first_step = script.index("BONYS-STEP 1/"), script.index("BONYS-STEP 2/")
    git = script.index("git build-essential")
    assert first_step[0] < git < first_step[1] < script.index("hermes-agent.nousresearch.com/install.sh")


def test_quiet_boot_messages():
    script = cloudinit.provision_script(_guest())
    assert "ln -sf /dev/null /etc/systemd/system-generators/systemd-ssh-generator" in script
    assert "kernel.printk = 3 4 1 3" in script


def test_wallpaper_in_cloud_init():
    import base64
    doc = json.loads(cloudinit.user_data(_guest()).split("\n", 1)[1])
    wp = next(f for f in doc["write_files"] if f["path"] == cloudinit.WALLPAPER_PATH)
    assert wp["encoding"] == "b64"
    assert base64.b64decode(wp["content"])[:3] == b"\xff\xd8\xff"  # JPEG
    script = doc["write_files"][0]["content"]
    override = script.index(f"cat > {cloudinit.SCHEMA_OVERRIDE}")
    assert script.index("cinnamon-core") < override < script.index("glib-compile-schemas")
    assert f"picture-uri='file://{cloudinit.WALLPAPER_PATH}'" in script
    # skaliert: ganzes Bild sichtbar, Seitenverhältnis bleibt, Rand in der App-Farbe
    assert "picture-options='scaled'" in script
    assert "primary-color='#0b1117'" in script and "color-shading-type='solid'" in script
    # nirgends sonst gestreckt/gezoomt (kein gsettings set, kein dconf, das den Override aushebelt)
    assert "stretched" not in script and "'zoom'" not in script
    assert "gsettings set org.cinnamon.desktop.background" not in script and "dconf write" not in script
    assert not re.search(r"gsettings set \S*background", script)
    # Anmeldebildschirm: eigene Drop-in-Datei, formatgerecht gefüllt statt verzerrt
    greeter = script[script.index(f"cat > {cloudinit.GREETER_DROPIN}"):]
    assert f"background=#zoomed:{cloudinit.WALLPAPER_PATH}" in greeter
    assert "sed -Ei 's|^#? *background" not in script  # früher: zerstörte die Greeter-Konfiguration


# ---------- Selbst-Installation ----------
def test_linux_root_script_installs_qemu_and_kvm_access():
    from bonys_agents import deps
    info = host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=8192, accel="tcg")
    report = deps.Report([
        deps.Issue("qemu", "fehlt", True, True),
        deps.Issue("kvm-access", "kein Zugriff", True, False),
    ])
    script = deps.linux_root_script(info, report, "bony", "apt-get")
    assert "apt-get install -y qemu-system-x86 qemu-system-gui qemu-utils acl" in script
    assert "usermod -aG kvm 'bony'" in script and "setfacl -m u:'bony':rw /dev/kvm" in script
    arm = deps.linux_root_script(info.__class__(**{**info.__dict__, "arch": "aarch64"}), report, "bony", "dnf")
    assert "edk2-aarch64" in arm and arm.count("dnf install") == 1


def test_linux_root_script_without_package_manager_fails():
    from bonys_agents import deps
    info = host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=8192, accel="tcg")
    with pytest.raises(RuntimeError):
        deps.linux_root_script(info, deps.Report([deps.Issue("qemu", "x", True, True)]), "bony", None)


def test_check_reports_missing_qemu(monkeypatch):
    from bonys_agents import deps

    def missing(name, os_):
        raise qemu.QemuNotFound(name)

    monkeypatch.setattr(deps.qemu, "find_binary", missing)
    info = host.HostInfo(os="windows", arch="x86_64", cpus=4, ram_mb=8192, accel="whpx")
    monkeypatch.setattr(deps.host, "windows_hypervisor_state", lambda: "disabled")
    r = deps.check(info)
    assert {i.key for i in r.issues} == {"qemu", "whpx"}
    assert not r.can_run and len(r.fixable) == 2


def test_install_nothing_to_do():
    from bonys_agents import deps
    info = host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=8192, accel="kvm")
    assert deps.install(info, deps.Report(), log=lambda s: None).success



# ---------- macOS ----------
def _homebrew(monkeypatch, tmp_path, *present):
    """Homebrew-Ordner im Testverzeichnis; ``present``: Architekturen, für die brew installiert ist."""
    from bonys_agents import deps

    prefixes = {"aarch64": tmp_path / "opt-homebrew", "x86_64": tmp_path / "usr-local"}
    for arch in present:
        (prefixes[arch] / "bin").mkdir(parents=True)
        (prefixes[arch] / "bin" / "brew").write_text("#!/bin/sh\n")
    monkeypatch.setattr(deps, "HOMEBREW_PREFIX", prefixes)
    monkeypatch.setattr(deps.shutil, "which", lambda name: None)
    return prefixes


def test_macos_check_offers_homebrew_when_missing(monkeypatch, tmp_path):
    from bonys_agents import deps

    def missing(name, os_):
        raise qemu.QemuNotFound(name)

    monkeypatch.setattr(deps.qemu, "find_binary", missing)
    monkeypatch.setattr(deps.host, "macos_rosetta", lambda: False)
    _homebrew(monkeypatch, tmp_path)
    info = host.HostInfo(os="macos", arch="aarch64", cpus=8, ram_mb=16384, accel="hvf")
    r = deps.check(info)
    assert {i.key for i in r.issues} == {"qemu", "homebrew"} and not r.can_run
    # Ohne Homebrew startet install() nichts selbst – das Terminal öffnen App bzw. Kommandozeile nach Rückfrage
    assert not deps.install(info, r, log=lambda s: None).success


def test_macos_install_uses_homebrew_outside_path(monkeypatch, tmp_path):
    """Aus dem Finder gestartet fehlt /opt/homebrew/bin im PATH – brew wird trotzdem gefunden."""
    from bonys_agents import deps

    prefixes = _homebrew(monkeypatch, tmp_path, "aarch64", "x86_64")
    assert deps.find_brew("aarch64") == prefixes["aarch64"] / "bin" / "brew"  # natives zuerst
    assert deps.find_brew("x86_64") == prefixes["x86_64"] / "bin" / "brew"
    ran = []
    monkeypatch.setattr(deps, "_run", lambda cmd, log, env=None: ran.append((cmd, env)) or 0)
    monkeypatch.setattr(deps, "check", lambda info=None: deps.Report())
    info = host.HostInfo(os="macos", arch="aarch64", cpus=8, ram_mb=16384, accel="hvf")
    res = deps.install(info, deps.Report([deps.Issue("qemu", "fehlt", True, True)]), log=lambda s: None)
    assert res.success and ran[0][0] == [str(prefixes["aarch64"] / "bin" / "brew"), "install", "qemu"]
    assert ran[0][1]["HOMEBREW_NO_ENV_HINTS"] == "1"


def test_homebrew_install_script_uses_official_installer():
    from bonys_agents import deps

    arm, intel = deps.homebrew_install_script("aarch64"), deps.homebrew_install_script("x86_64")
    assert "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh" in arm
    assert 'eval "$(/opt/homebrew/bin/brew shellenv)"' in arm and "brew install qemu" in arm
    assert 'eval "$(/usr/local/bin/brew shellenv)"' in intel
    assert "Intel" in intel and "Intel" not in arm
    assert "sudo" not in arm  # nach dem Passwort fragt der offizielle Installer selbst im Terminal
    assert "Erneut prüfen" in deps.homebrew_explanation() and "Erneut prüfen" not in deps.homebrew_explanation(True)


def test_finder_apps_get_homebrew_in_path():
    from bonys_agents import procutil

    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    procutil.add_homebrew_to_path(env, platform="darwin")
    assert env["PATH"].split(":")[-2:] == ["/opt/homebrew/bin", "/usr/local/bin"]
    procutil.add_homebrew_to_path(env, platform="darwin")  # nicht doppelt
    assert env["PATH"].count("/opt/homebrew/bin") == 1
    linux = {"PATH": "/usr/bin"}
    procutil.add_homebrew_to_path(linux, platform="linux")
    assert linux == {"PATH": "/usr/bin"}


def test_intel_app_under_rosetta_uses_apple_chip(monkeypatch):
    monkeypatch.setattr(host.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(host, "detect_os", lambda: "macos")
    monkeypatch.setattr(host, "_sysctl", lambda name: {"hw.optional.arm64": "1", "sysctl.proc_translated": "1"}[name])
    assert host.detect_arch() == "aarch64" and host.macos_rosetta()
    monkeypatch.setattr(host, "_sysctl", lambda name: "")  # echter Intel-Mac
    assert host.detect_arch() == "x86_64" and not host.macos_rosetta()
    assert host.macos_chip_name("aarch64") == "Apple-Chip (arm64)"


def test_aarch64_firmware_from_homebrew_cellar(tmp_path):
    """Homebrew: /opt/homebrew/bin/qemu-system-aarch64 ist ein Link in den Cellar, die Firmware liegt in share/qemu."""
    cellar = tmp_path / "Cellar" / "qemu" / "11.1.1"
    (cellar / "bin").mkdir(parents=True)
    (cellar / "share" / "qemu").mkdir(parents=True)
    real = cellar / "bin" / "qemu-system-aarch64"
    real.write_text("")
    fw = cellar / "share" / "qemu" / "edk2-aarch64-code.fd"
    fw.write_text("")
    (tmp_path / "bin").mkdir()
    link = tmp_path / "bin" / "qemu-system-aarch64"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("keine symbolischen Links")
    assert qemu.find_aarch64_firmware(link).resolve() == fw.resolve()

# ---------- Speicherorte ----------
def _fake_create(monkeypatch, tmp_path):
    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk" * 1000))


def test_create_on_other_drive_and_find_again(datadir, monkeypatch, tmp_path):
    from bonys_agents import storage
    _fake_create(monkeypatch, tmp_path)
    ssd = tmp_path / "ssd" / "BonysAgents"
    m = vm.create("auf-ssd", "pw1234", location=ssd)
    assert m.path == ssd / "auf-ssd" and m.disk.exists()
    assert str(ssd) in storage.load_settings()["locations"]
    assert vm.get("auf-ssd").path == ssd / "auf-ssd"
    # gleicher Name an anderem Ort ist nicht erlaubt
    with pytest.raises(FileExistsError):
        vm.create("auf-ssd", "pw1234")


def test_drive_unplugged_then_found_via_autodiscovery(datadir, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from bonys_agents import storage
    _fake_create(monkeypatch, tmp_path)
    ssd_mount = tmp_path / "E"
    vm.create("mobil", "pw1234", location=ssd_mount / "BonysAgents")
    # Laufwerk „abziehen“: Ordner weg, Einstellungen vergessen den Ort
    moved = tmp_path / "F"
    (ssd_mount).rename(moved)
    s = storage.load_settings()
    s["locations"] = []
    storage.save_settings(s)
    storage.invalidate_cache()
    entries = vm.list_all()
    assert [type(e).__name__ for e in entries] == ["MissingVM"]
    assert entries[0].status() == "nicht verfügbar"
    with pytest.raises(KeyError, match="nicht verfügbar"):
        vm.get("mobil")
    # Laufwerk taucht mit neuem Buchstaben wieder auf → automatisch gefunden
    monkeypatch.setattr(storage, "_partitions", lambda: [SimpleNamespace(mountpoint=str(moved))])
    storage.invalidate_cache()
    assert vm.get("mobil").path == moved / "BonysAgents" / "mobil"
    assert storage.load_settings()["known"]["mobil"] == str(moved / "BonysAgents" / "mobil")


def test_move_between_locations(datadir, monkeypatch, tmp_path):
    _fake_create(monkeypatch, tmp_path)
    m = vm.create("wanderer", "pw1234")
    size = m.disk.stat().st_size
    target = tmp_path / "ziel"
    steps = []
    monkeypatch.setattr(vm, "_same_device", lambda a, b: False)  # Kopierweg wie bei echtem Laufwerkswechsel
    moved = vm.move("wanderer", target, progress=lambda *a: steps.append(a[0]))
    assert moved.path == target / "wanderer" and moved.disk.stat().st_size == size
    assert not m.path.exists() and "move" in steps and steps[-1] == "done"
    assert vm.get("wanderer").path == target / "wanderer"
    # gleiches Laufwerk: schnelles Umbenennen
    monkeypatch.setattr(vm, "_same_device", lambda a, b: True)
    back = vm.move("wanderer", tmp_path / "zurueck")
    assert back.path == tmp_path / "zurueck" / "wanderer" and back.disk.stat().st_size == size


def test_import_existing_folder(datadir, tmp_path):
    lib = tmp_path / "usb" / "BonysAgents"
    (lib / "alt").mkdir(parents=True)
    cfg = vm.VMConfig(name="alt", arch="x86_64", cpus=1, ram_mb=2048)
    (lib / "alt" / "vm.json").write_text(json.dumps(cfg.__dict__))
    added = vm.import_path(lib / "alt")
    assert [m.name for m in added] == ["alt"]
    assert vm.get("alt").location == lib
    with pytest.raises(ValueError):
        vm.import_path(tmp_path)


def test_location_check_rejects_fat32(monkeypatch, tmp_path):
    from bonys_agents import storage
    fat = storage.Drive(tmp_path, "STICK", "vfat", 64 * storage.GB, 60 * storage.GB, True, False)
    monkeypatch.setattr(storage, "drive_for", lambda p: fat)
    chk = storage.check_location(tmp_path / "BonysAgents", 50)
    assert not chk.ok and "4 GB" in chk.errors[0]
    exfat = storage.Drive(tmp_path, "SSD", "exfat", 1000 * storage.GB, 900 * storage.GB, True, False)
    monkeypatch.setattr(storage, "drive_for", lambda p: exfat)
    chk = storage.check_location(tmp_path / "BonysAgents", 50, create=True)
    assert chk.ok and any("Abziehen" in w for w in chk.warnings)
    assert (tmp_path / "BonysAgents").is_dir()


def test_drives_lists_real_partitions():
    from bonys_agents import storage
    ds = storage.drives()
    assert ds and ds[0].system  # Hauptsystem steht oben
    assert all(d.free <= d.total for d in ds)


def test_doctor_warns_about_old_user_install(datadir, capsys):
    from bonys_agents import storage
    assert storage.old_user_install() is None
    (datadir / "app" / "bin").mkdir(parents=True)
    (datadir / "app" / "bin" / "bonys-agents").touch()
    assert storage.old_user_install() == datadir / "app"
    cli.main(["doctor"])
    assert "Ältere Installation gefunden" in capsys.readouterr().out


# ---------- Ersteinrichtung ohne Fenster ----------
@pytest.fixture
def first_boot(datadir, monkeypatch):
    """Frisch angelegter Agent-PC; QEMU-Start und -Zustand werden nachgebildet."""
    m = _fake_vm(datadir)
    m.config.first_boot_pending = True
    m.save()
    m.seed_iso.write_bytes(b"seed")
    state = {"running": False, "launches": []}
    monkeypatch.setattr(vm.VM, "is_running", lambda self: state["running"])

    def launch(self, headless):
        state["launches"].append(headless)
        state["running"] = True
        self.console_log.write_text("boot …\n")  # QEMU legt die Konsole beim Start neu an

    monkeypatch.setattr(vm.VM, "_launch", launch)
    return m, state


def test_first_boot_hidden_then_window_after_ready(first_boot):
    m, state = first_boot
    m.start()
    assert state["launches"] == [True]  # Ersteinrichtung ohne Fenster
    m.console_log.write_text("BONYS-STEP 2/5 Cinnamon\n")
    assert m.status() == "wird eingerichtet" and not m.needs_window_start()
    m.console_log.write_text(m.console_log.read_text() + "BONYS-AGENTS-READY\n")
    assert m.status() == "wird eingerichtet"  # fährt gerade herunter
    state["running"] = False  # Gast hat sich ausgeschaltet
    assert m.status() == vm.STATUS_READY_FOR_DESKTOP and m.needs_window_start()
    assert m.finish_first_boot()
    assert state["launches"] == [True, False]  # jetzt mit Fenster
    again = vm.get(m.name)
    assert not again.config.first_boot_pending and again.config.provisioned
    assert not again.seed_iso.exists()
    assert again.status() == "läuft" and not again.finish_first_boot()


def test_first_boot_aborted_without_ready(first_boot):
    m, state = first_boot
    assert m.status() == "gestoppt"  # noch nie gestartet: kein Abbruch
    m.start()
    m.console_log.write_text("BONYS-STEP 3/5 Brave Browser installieren\n")
    state["running"] = False  # beendet ohne READY
    assert m.status() == vm.STATUS_ABORTED
    assert not m.needs_window_start() and not m.finish_first_boot()
    m.start()  # „Einrichtung fortsetzen“
    assert state["launches"] == [True, True]
    assert m.config.first_boot_pending


def test_start_after_app_was_closed_opens_window(first_boot):
    m, state = first_boot
    m.console_log.write_text("BONYS-AGENTS-READY\n")  # Einrichtung endete, während die App zu war
    vm.get(m.name).start()
    assert state["launches"] == [False]
    assert not vm.get(m.name).config.first_boot_pending


def test_wait_ready_restarts_with_window(first_boot, capsys):
    m, state = first_boot
    m.start()
    m.console_log.write_text("BONYS-AGENTS-READY\n")
    state["running"] = False
    assert cli._wait_ready(m, poll=0) == 0
    assert state["launches"] == [True, False]
    assert "mit Desktop" in capsys.readouterr().out


def test_wait_ready_reports_abort(first_boot, capsys):
    m, state = first_boot
    m.start()
    state["running"] = False
    assert cli._wait_ready(m, poll=0) == 1
    assert state["launches"] == [True]
    assert vm.STATUS_ABORTED in capsys.readouterr().out


def test_guest_powers_off_after_setup():
    doc = json.loads(cloudinit.user_data(_guest()).split("\n", 1)[1])
    assert "power_state" not in doc  # cloud-init würde sonst mitten in die Einrichtung (Dienst) hinein ausschalten
    script = cloudinit.provision_script(_guest())
    tail = script[script.index(f'echo "{cloudinit.READY_MARKER}"'):]
    assert "systemctl --no-block poweroff" in tail and "cidata" in tail  # nur mit eingelegtem Seed-ISO


# ---------- Fortschritt in Prozent ----------
def test_step_ranges_follow_weights_and_redistribute():
    from bonys_agents import progress as pct
    full = pct.step_ranges(["brave", "telegram", "hermes"])
    assert [round(x) for x, _ in full] == [22, 27, 65, 75, 85]  # wie vorgegeben
    assert full[-1][1] == pytest.approx(97)
    only_hermes = pct.step_ranges(["hermes"])
    assert len(only_hermes) == 3 and only_hermes[-1][1] == pytest.approx(97)
    assert only_hermes[1][1] - only_hermes[1][0] > full[1][1] - full[1][0]  # Cinnamon bekommt mehr Anteil


def test_creation_percent_phases():
    from bonys_agents import progress as pct
    assert pct.creation_percent("download", 0) == 0
    assert pct.creation_percent("download", 0.5) == pytest.approx(7.5)
    assert pct.creation_percent("download", 1) == 15
    assert pct.creation_percent("disk", 0) == 15
    assert pct.creation_percent("seed", 0) == 18


def test_setup_percent_moves_within_step():
    from bonys_agents import progress as pct
    ids = ["brave", "telegram", "hermes"]
    boot = pct.setup_percent("[    0.1] Linux version …\n" * 50, ids, ready=False)
    assert 18 < boot < 22
    head = "BONYS-STEP 2/5 Cinnamon-Desktop\n0 upgraded, 100 newly installed, 0 to remove and 0 not upgraded.\n"
    start = pct.setup_percent(head, ids, ready=False)
    half = pct.setup_percent(head + "Get:1 x\n" * 100 + "Unpacking foo\n" * 50, ids, ready=False)
    assert start == pytest.approx(27, abs=0.1)
    assert half == pytest.approx(27 + 38 * 0.5, abs=0.1)
    german = "BONYS-STEP 2/5 Cinnamon\n0 aktualisiert, 10 neu installiert, 0 zu entfernen\n" \
             + "Holen:1 x\n" * 10 + "Entpacken von foo …\n" * 10 + "foo (1.0) wird eingerichtet …\n" * 10
    assert pct.setup_percent(german, ids, ready=False) == pytest.approx(27 + 38 * 0.98, abs=0.1)
    # ohne apt-Zusammenfassung (z. B. flatpak, Hermes-Installer): wandert trotzdem weiter
    a = pct.setup_percent("BONYS-STEP 4/5 Telegram\n" + "x\n" * 10, ids, ready=False)
    b = pct.setup_percent("BONYS-STEP 4/5 Telegram\n" + "x\n" * 300, ids, ready=False)
    assert 75 < a < b < 85


def test_setup_percent_finish():
    from bonys_agents import progress as pct
    assert pct.setup_percent("", [], ready=True, pending=True, running=True) == 97
    assert pct.setup_percent("", [], ready=True, pending=True, running=False) == 99
    assert pct.setup_percent("", [], ready=True, pending=False) == 100


def test_eta():
    from bonys_agents import progress as pct
    assert pct.eta_seconds(0, 18, 30, 30) is None          # zu früh
    assert pct.eta_seconds(0, 18, 600, 19) is None         # zu wenig Fortschritt
    assert pct.eta_seconds(0, 18, 600, 58) == pytest.approx(42 * 600 / 40)
    assert pct.format_eta(12 * 60 - 5) == "noch ca. 12 Min."
    assert pct.format_eta(30) == "noch knapp 1 Min."
    assert pct.format_eta(90 * 60) == "noch ca. 1 Std. 30 Min."
    assert pct.format_eta(None) == ""


def test_vm_progress_has_percent(first_boot):
    m, state = first_boot
    m.start()
    m.console_log.write_text("BONYS-STEP 3/5 Brave Browser installieren\n")
    assert m.progress().percent == pytest.approx(65, abs=0.5)


def test_cli_status_shows_percent(first_boot, capsys):
    m, state = first_boot
    m.start()
    m.console_log.write_text("BONYS-STEP 3/5 Brave Browser installieren\n")
    assert cli.main(["status", m.name]) == 0
    assert "Einrichtung: 65 % · Schritt 3/5 Brave Browser installieren" in capsys.readouterr().out


# ---------- Festplatte ----------
def test_disk_size_limits(datadir):
    assert vm.format_gb(64) == "64 GB" and vm.format_gb(1024) == "1 TB"
    assert vm.DEFAULT_DISK_GB == 64
    with pytest.raises(ValueError, match="32 bis 1024"):
        vm.create("ok", "pw1234", disk_gb=16)
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["create", "x", "--disk", "2048"])
    assert cli.build_parser().parse_args(["create", "x", "--disk", "100"]).disk == 100


def test_resize_only_grows(datadir, monkeypatch):
    m = _fake_vm(datadir)  # 64 GB
    calls = []
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "resize_disk", lambda qi, disk, gb: calls.append(gb))
    with pytest.raises(ValueError, match="Nur vergrößern"):
        m.resize(48)
    with pytest.raises(ValueError):
        m.resize(2048)
    assert cli.main(["resize", m.name, "128"]) == 0
    assert calls == [128] and vm.get(m.name).config.disk_gb == 128
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    with pytest.raises(RuntimeError, match="herunterfahren"):
        m.resize(256)


def test_guest_grows_root_partition_on_every_boot():
    script = cloudinit.provision_script(_guest())
    assert "cloud-guest-utils" in script
    assert 'growpart "$DISK" "$NUM"' in script and "resize2fs" in script
    assert "systemctl enable bonys-growroot.service" in script


# ---------- KI-Werkzeuge: OpenClaw und Claude Code ----------
def _outside_heredocs(snippet: str) -> list[str]:
    """Zeilen, die das Snippet selbst ausführt (ohne Inhalt von <<'EOF'-Blöcken)."""
    lines, inside = [], False
    for line in snippet.splitlines():
        if inside:
            inside = line.strip() != "EOF"
            continue
        if "<<'EOF'" in line:
            inside = True
        lines.append(line)
    return lines


def test_ai_tool_specs():
    for app_id, name in (("openclaw", "OpenClaw"), ("claude-code", "Claude Code"), ("hermes", "Hermes Agent")):
        spec = apps.APPS[app_id]
        assert spec.name == name and spec.category == apps.AGENT
    assert apps.ids_in_category(apps.PROGRAM) == ["brave", "telegram", "xrdp"]
    assert apps.default_app_ids() == ["brave", "telegram", "xrdp", "hermes"]  # KI-Werkzeuge außer Hermes nur auf Wunsch


@pytest.mark.parametrize("app_id,installer", [
    ("openclaw", "https://openclaw.ai/install-cli.sh"),
    ("claude-code", "https://claude.ai/install.sh"),
    ("hermes", "https://hermes-agent.nousresearch.com/install.sh"),
])
def test_ai_tools_install_as_agent_user_not_root(app_id, installer):
    run = _outside_heredocs(apps.APPS[app_id].install)
    curl_lines = [line for line in run if installer in line]
    assert curl_lines, "Installer wird nicht aufgerufen"
    assert all(line.startswith('su - "$AGENT_USER" -c ') for line in curl_lines)


def test_claude_code_unchanged_installer_path_and_shortcut():
    snippet = apps.APPS["claude-code"].install
    assert "su - \"$AGENT_USER\" -c 'curl -fsSL https://claude.ai/install.sh | bash'" in snippet
    assert "ensure_path .local/bin" in snippet and '"$AGENT_HOME/Projekte"' in snippet
    assert "Icon=utilities-terminal" in snippet and 'cd "$HOME/Projekte"' in snippet


def test_openclaw_no_daemon_and_first_run_marker():
    snippet = apps.APPS["openclaw"].install
    assert "--no-onboard" in snippet and "ensure_path .openclaw/bin" in snippet
    assert "openclaw onboard --no-install-daemon" in snippet
    assert '$HOME/.openclaw/.bonys-eingerichtet' in snippet
    run = "\n".join(_outside_heredocs(snippet))
    assert "gateway" not in run and "systemctl" not in run  # kein Dienst beim Einrichten


def test_step_order_and_git_first():
    guest = cloudinit.GuestConfig(hostname="t", username="agent", password="pw",
                                  apps=apps.resolve(["claude-code", "openclaw", "brave", "hermes"]))
    script = cloudinit.provision_script(guest)
    titles = re.findall(r"BONYS-STEP \d+/(\d+) ([^\"]+)", script)
    assert [t for _, t in titles] == [
        "Sprache, Tastatur und Zeitzone", "Cinnamon-Desktop mit automatischer Anmeldung",
        "Brave Browser installieren", "Hermes Agent installieren",
        "OpenClaw installieren", "Claude Code installieren",
    ]
    assert script.index("git build-essential") < script.index("BONYS-STEP 2/")


def test_no_credentials_in_cloud_init():
    guest = cloudinit.GuestConfig(hostname="t", username="agent", password="geheim123",
                                  apps=apps.resolve(list(apps.APPS)))
    doc = json.loads(cloudinit.user_data(guest).split("\n", 1)[1])
    script = doc["write_files"][0]["content"].lower()
    for word in ("anthropic_api_key", "api_key", "apikey", "sk-ant", "token", "openai", "credentials"):
        assert word not in script, word
    assert "geheim123" not in script  # das Passwort steht nur im Benutzereintrag von cloud-init


def test_agents_option():
    assert cli.app_selection(None, None) is None
    assert cli.app_selection(None, "openclaw,claude-code") == ["brave", "telegram", "xrdp", "openclaw", "claude-code"]
    assert cli.app_selection("brave", "none") == ["brave"]
    assert cli.app_selection("brave,hermes", None) == ["brave", "hermes"]
    with pytest.raises(ValueError, match="nur für KI-Werkzeuge"):
        cli.app_selection(None, "telegram")
    with pytest.raises(ValueError, match="Unbekannte"):
        cli.app_selection(None, "gibtsnicht")
    args = cli.build_parser().parse_args(["create", "x", "--agents", "hermes,claude-code"])
    assert args.agents == "hermes,claude-code"


def test_progress_includes_new_tools():
    from bonys_agents import progress as pct
    r = pct.step_ranges(["brave", "telegram", "hermes", "openclaw", "claude-code"])
    assert len(r) == 7 and r[-1][1] == pytest.approx(97)
    hermes, openclaw = r[4], r[5]
    assert openclaw[1] - openclaw[0] == pytest.approx(hermes[1] - hermes[0])


@pytest.fixture
def running_vm(datadir, monkeypatch):
    m = _fake_vm(datadir)
    m.config.apps = ["brave", "hermes"]
    m.config.provisioned = True
    m.save()
    m.runtime_file.write_text(json.dumps({"ssh_port": 2222}))
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/ssh")
    return vm.get(m.name)


class _FakePopen:
    calls: list = []
    rc = 0

    def __init__(self, cmd, stdin=None, stdout=None, stderr=None, env=None, **kw):
        import io

        fake = self

        class _Stdin(io.StringIO):
            def close(self):
                fake.script = self.getvalue()
                super().close()

        self.cmd, self.env, self.script = cmd, env, ""
        self.stdin = _Stdin()
        self.stdout = io.StringIO("Claude Code ist installiert.\n")
        self.askpass = Path(env["SSH_ASKPASS"]).read_text() if env and "SSH_ASKPASS" in env else None
        _FakePopen.calls.append(self)

    def wait(self):
        return _FakePopen.rc


def test_install_app_over_ssh(running_vm, monkeypatch):
    _FakePopen.calls, _FakePopen.rc = [], 0
    monkeypatch.setattr(vm.subprocess, "Popen", _FakePopen)
    lines = []
    running_vm.install_app("claude-code", password="geheim123", log=lines.append)
    call = _FakePopen.calls[0]
    assert "geheim123" not in " ".join(call.cmd)                  # nicht auf der Kommandozeile
    assert "geheim123" not in (call.askpass or "")                # nicht in einer Datei
    assert call.env["BONYS_SSH_PASSWORD"] == "geheim123" and call.env["SSH_ASKPASS_REQUIRE"] == "force"
    assert "agent@127.0.0.1" in call.cmd and "2222" in call.cmd
    assert "https://claude.ai/install.sh" in call.script and 'test -x "$HOME/.local/bin/claude"' in call.script
    assert lines == ["Claude Code ist installiert."]
    assert vm.get(running_vm.name).config.apps == ["brave", "hermes", "claude-code"]
    assert not any("geheim123" in f.read_text(errors="ignore") for f in running_vm.path.iterdir() if f.is_file())
    with pytest.raises(ValueError, match="bereits installiert"):
        vm.get(running_vm.name).install_app("claude-code")


def test_install_app_reports_ssh_failure(running_vm, monkeypatch):
    _FakePopen.calls, _FakePopen.rc = [], 255
    monkeypatch.setattr(vm.subprocess, "Popen", _FakePopen)
    with pytest.raises(RuntimeError, match="Passwort"):
        running_vm.install_app("openclaw", password="falsch")
    assert "openclaw" not in vm.get(running_vm.name).config.apps


# ---------- Fernzugriff: RDP und SPICE ----------
# Fester Host für Starttests: host.detect() ruft unter macOS/Windows selbst Programme auf.
_LINUX_HOST = host.HostInfo(os="linux", arch="x86_64", cpus=8, ram_mb=16384, accel="kvm")


def _rspec(**kw):
    base = dict(qemu_bin=PurePosixPath("/usr/bin/qemu-system-x86_64"), arch="x86_64", accel="kvm", name="t",
                cpus=2, ram_mb=2048, disk=PurePosixPath("/tmp/d.qcow2"), qmp_port=4444, ssh_port=2222,
                serial_log=PurePosixPath("/tmp/c.log"), pidfile=PurePosixPath("/tmp/q.pid"))
    base.update(kw)
    return qemu.LaunchSpec(**base)


def test_remote_ports_unique(datadir, monkeypatch):
    from bonys_agents import remote
    a, b = _fake_vm(datadir, "a"), _fake_vm(datadir, "b")
    monkeypatch.setattr(remote, "port_free", lambda port: port != 3391)  # 3391 belegt ein anderes Programm
    a.ensure_remote_ports()
    b.ensure_remote_ports()
    assert (a.config.rdp_port, a.config.spice_port) == (3390, 5901)
    assert (b.config.rdp_port, b.config.spice_port) == (3392, 5902)
    assert json.loads((b.path / "vm.json").read_text())["rdp_port"] == 3392  # fest gespeichert
    b.ensure_remote_ports()
    assert b.config.rdp_port == 3392  # bleibt


def test_remote_off_by_default_and_ports_at_start():
    off = qemu.build_command(_rspec(rdp_port=3390, spice_port=5901))
    net = off[off.index("-netdev") + 1]
    assert net == "user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22"  # nur SSH, lokal – kein RDP-Port
    assert "port=5901,addr=127.0.0.1,disable-ticketing=on" in off      # SPICE nur an diesem Rechner
    assert "com.redhat.spice.0" in " ".join(off)
    lan = qemu.build_command(_rspec(rdp_addr="0.0.0.0", rdp_port=3390, spice_port=5901, spice_addr="0.0.0.0",
                                   spice_password_file=PurePosixPath("/vm/spice-password")))
    net = lan[lan.index("-netdev") + 1]
    assert "hostfwd=tcp:127.0.0.1:2222-:22" in net        # SSH bleibt immer lokal
    assert "hostfwd=tcp:0.0.0.0:3390-:3389" in net
    assert "port=5901,addr=0.0.0.0,password-secret=spicepw" in lan
    assert "secret,id=spicepw,file=/vm/spice-password" in lan
    assert not any("disable-ticketing" in x for x in lan)
    plain = qemu.build_command(_rspec())
    assert "-spice" not in plain and "ich9-intel-hda" not in plain


def test_screen_follows_window_and_guest_agent_channel():
    cmd = qemu.build_command(_rspec(qga_port=4555, spice_port=5901))
    assert "virtio-vga,edid=on,xres=800,yres=600" in cmd  # EDID: neue Fenstergröße geht an den Gast
    assert cmd[cmd.index("-fw_cfg") + 1] == "name=opt/bonys-agents/screen,string=auto"
    assert "socket,id=qga0,host=127.0.0.1,port=4555,server=on,wait=off" in cmd
    assert "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0" in cmd
    assert cmd.count("virtio-serial-pci") == 1  # ein Bus für Gast-Agent und SPICE
    arm = qemu.build_command(_rspec(arch="aarch64", firmware=PurePosixPath("/fw.fd")))
    assert "virtio-gpu-pci,edid=on,xres=800,yres=600" in arm
    fixed = qemu.build_command(_rspec(screen=(1280, 800), screen_setting="fixed:1280x800"))
    assert "virtio-vga,edid=on,xres=1280,yres=800" in fixed
    assert "name=opt/bonys-agents/screen,string=fixed:1280x800" in fixed
    # Mit -spice öffnet QEMU von sich aus KEIN Fenster – deshalb steht die Anzeige ausdrücklich da.
    win = qemu.build_command(_rspec(spice_port=5901, display="gtk"))
    assert win[-2:] == ["-display", "gtk"]
    assert qemu.build_command(_rspec(display="gtk", headless=True))[-2:] == ["-display", "none"]
    # zoom-to-fit=off ließe das Fenster nicht kleiner als den Gast werden – nur bei fester Auflösung
    assert qemu.window_display("linux", ["none", "gtk", "sdl"]) == "gtk,zoom-to-fit=on,show-menubar=on"
    assert qemu.window_display("linux", ["gtk"], "scale") == "gtk,zoom-to-fit=on,show-menubar=on"
    assert qemu.window_display("windows", ["gtk"], "fixed") == "gtk,zoom-to-fit=off,show-menubar=on"
    assert qemu.window_display("macos", ["cocoa", "sdl"]) == "cocoa"
    assert qemu.window_display("macos", ["cocoa"], "scale") == "cocoa,zoom-to-fit=on"
    assert qemu.window_display("windows", ["sdl"]) == "sdl"
    assert qemu.window_display("linux", []) is None


def test_screen_settings_and_sizes():
    assert screen.parse_size("1920X1080") == (1920, 1080) and screen.parse_size("1280×800") == (1280, 800)
    for bad in ("1280", "abcxdef", "320x200", "99999x1"):
        with pytest.raises(ValueError):
            screen.parse_size(bad)
    with pytest.raises(ValueError):
        screen.check_mode("stretch")
    assert screen.start_size("auto", "1920x1080") == (800, 600)   # Startgröße, danach folgt der Gast dem Fenster
    assert screen.start_size("fixed", "1920x1080") == (1920, 1080)
    assert screen.guest_setting("auto", "1024x768") == "auto"
    assert screen.guest_setting("scale", "1024X768") == "scale:1024x768"
    assert screen.label("fixed", "1024x768") == "Feste Auflösung (1024x768)"


def test_vm_screen_setting_saved_and_validated(datadir, monkeypatch, tmp_path):
    _fake_create(monkeypatch, tmp_path)
    m = vm.create("bild", "pw1234", cpus=1, ram_mb=2048, location=tmp_path / "lib")
    assert m.screen_settings() == ("auto", screen.DEFAULT_SIZE)
    m.set_screen("fixed", "1366x768")
    assert vm.VM(m.path).screen_settings() == ("fixed", "1366x768")
    with pytest.raises(ValueError):
        m.set_screen("fixed", "riesig")
    with pytest.raises(ValueError):
        m.set_screen("wackeln")
    data = json.loads((m.path / "vm.json").read_text("utf-8"))
    data.update(screen_mode="quatsch", screen_size="0x0")  # von Hand verbogen → Standard
    (m.path / "vm.json").write_text(json.dumps(data), "utf-8")
    assert vm.VM(m.path).screen_settings() == ("auto", screen.DEFAULT_SIZE)


def test_screen_cli(datadir, monkeypatch, tmp_path, capsys):
    _fake_create(monkeypatch, tmp_path)
    vm.create("cli-bild", "pw1234", cpus=1, ram_mb=2048, location=tmp_path / "lib")
    assert cli.main(["screen", "cli-bild", "scale", "--size", "1600x900"]) == 0
    assert vm.get("cli-bild").screen_settings() == ("scale", "1600x900")
    assert cli.main(["screen", "cli-bild"]) == 0
    assert "Bild skalieren (Zoom to Fit) (1600x900)" in capsys.readouterr().out


def test_fullscreen_needs_window(datadir, monkeypatch, tmp_path):
    _fake_create(monkeypatch, tmp_path)
    m = vm.create("voll", "pw1234", cpus=1, ram_mb=2048, location=tmp_path / "lib")
    with pytest.raises(RuntimeError, match="läuft nicht"):
        m.fullscreen()
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    m._update_runtime(command=["qemu", "-display", "none"])
    with pytest.raises(RuntimeError, match="Strg\\+Alt\\+F"):
        m.fullscreen()  # SPICE-Fenster bzw. ohne Fenster: nur der Hinweis
    m._update_runtime(command=["qemu", "-display", "gtk,zoom-to-fit=on"])
    monkeypatch.setattr(vm, "window_tools_available", lambda: True)
    monkeypatch.setattr(vm, "_find_qemu_window", lambda name: "4711")
    calls = []
    monkeypatch.setattr(vm.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    assert "Vollbild" in m.fullscreen()
    assert calls == [["xdotool", "windowactivate", "--sync", "4711", "key", "--clearmodifiers", "ctrl+alt+f"]]
    assert vm.window_title_pattern("voll") == "\\(Bony's Agents – voll\\)"


def test_audio_devices_and_host_driver(monkeypatch, tmp_path):
    cmd = qemu.build_command(_rspec(audio="pipewire"))
    assert "pipewire,id=snd0" in cmd and "hda-duplex,audiodev=snd0" in cmd
    (tmp_path / "pipewire-0").touch()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert qemu.host_audio_driver("linux", ["pa", "pipewire"]) == "pipewire"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "leer"))
    assert qemu.host_audio_driver("linux", ["pa", "pipewire"]) == "pa"
    assert qemu.host_audio_driver("windows", ["dsound"]) == "dsound"
    assert qemu.host_audio_driver("macos", ["coreaudio"]) == "coreaudio"
    assert qemu.host_audio_driver("windows", []) is None


def test_remote_settings_when_stopped(datadir):
    m = _fake_vm(datadir)
    m.config.apps.append("xrdp")
    m.save()
    info = m.remote_info()
    assert not info["active"] and not info["permanent"] and info["spice_password"] == ""
    with pytest.raises(RuntimeError, match="läuft nicht"):
        m.set_remote(True)  # „nur bis zum Herunterfahren“ geht nur bei laufendem Agent-PC
    assert "nächsten Start" in m.set_remote(True, permanent=True)
    again = vm.get(m.name)
    assert again.config.remote_permanent and len(again.config.spice_password) >= 10
    assert again.remote_info()["spice_lan"]  # beim nächsten Start auch SPICE im Heimnetz
    again.set_remote(False)
    assert not vm.get(m.name).config.remote_permanent


def test_remote_needs_xrdp(datadir):
    m = _fake_vm(datadir)  # ohne „xrdp“
    with pytest.raises(RuntimeError, match="Fernzugriff \\(RDP\\)"):
        m.set_remote(True, permanent=True)


def test_old_remote_lan_setting_migrates(datadir):
    m = _fake_vm(datadir)
    data = json.loads((m.path / "vm.json").read_text())
    data.pop("remote_permanent")
    data["remote_lan"] = True
    (m.path / "vm.json").write_text(json.dumps(data))
    assert vm.get(m.name).config.remote_permanent


def test_spice_detection_switches_off(datadir, monkeypatch, tmp_path):
    quits = tmp_path / "qemu-ohne-spice"
    quits.write_text("#!/bin/sh\necho 'There is no option group spice' >&2\nexit 1\n")
    quits.chmod(0o755)
    runs = tmp_path / "qemu-mit-spice"
    runs.write_text("#!/bin/sh\nsleep 5\n")
    runs.chmod(0o755)
    if sys.platform != "win32":  # Shell-Skripte als Ersatz-QEMU laufen nur unter POSIX
        assert qemu._probe_spice(quits) is False
        assert qemu._probe_spice(runs) is True
    m = _fake_vm(datadir)
    m.ensure_remote_ports()
    monkeypatch.setattr(vm.VM, "capabilities", lambda self: {"spice": False, "audio": []})
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    info = m.remote_info()
    assert info["spice_port"] is None and not info["spice_supported"]
    with pytest.raises(RuntimeError, match="kein SPICE"):
        m.connect("SPICE")


def test_spice_window_start(datadir, monkeypatch):
    """SPICE-Fenster: QEMU ohne eigenes Fenster, Ton über SPICE, Viewer wird geöffnet."""
    from bonys_agents import remote
    m = _fake_vm(datadir)
    m.config.provisioned = True
    m.set_display("spice")
    started, opened = [], []

    class FakeProc:
        pid = 1

        def __init__(self, cmd, **kw):
            started.append(cmd)
            m.pidfile.write_text("1")

        def poll(self):
            return None

    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/usr/bin/qemu-system-x86_64"))
    monkeypatch.setattr(vm.qemu, "capabilities", lambda qb, cache=None: {"spice": True, "audio": ["pipewire", "spice"]})
    monkeypatch.setattr(vm.subprocess, "Popen", FakeProc)  # ersetzt Popen überall – darum fester Host:
    monkeypatch.setattr(vm.host, "detect", lambda: _LINUX_HOST)
    monkeypatch.setattr(remote, "spice_viewer_available", lambda: True)
    monkeypatch.setattr(vm, "_wait_for_port", lambda port, timeout=8.0: None)
    monkeypatch.setattr(vm.VM, "connect", lambda self, proto: opened.append(proto))
    m.start()
    cmd = started[0]
    assert cmd[-2:] == ["-display", "none"] and "spice,id=snd0" in cmd
    assert opened == ["SPICE"]
    rt = m.runtime()
    assert rt["rdp_port"] == 3390 and rt["spice_port"] == 5901 and rt["remote_on"] is False
    assert rt["qga_port"] and "hostfwd=tcp:0.0.0.0" not in " ".join(cmd)
    vm._children.clear()


def test_remmina_profiles_created_and_removed(datadir, monkeypatch, tmp_path):
    from bonys_agents import remote
    native, flat = tmp_path / "remmina", tmp_path / "flatpak-remmina"
    monkeypatch.setattr(remote, "remmina_dirs", lambda native_=None, flatpak=None, **kw: [native, flat])
    monkeypatch.setattr(vm.sys, "platform", "linux")
    m = _fake_vm(datadir, "agent-pc-1")
    m.ensure_remote_ports()
    m.sync_remmina()
    for d in (native, flat):
        rdp = (d / "bonys-agents-agent-pc-1-rdp.remmina").read_text()
        spice = (d / "bonys-agents-agent-pc-1-spice.remmina").read_text()
        assert "group=Bony's Agents" in rdp and "protocol=RDP" in rdp
        assert "server=127.0.0.1:3390" in rdp and "username=agent" in rdp
        assert "protocol=SPICE" in spice and "server=127.0.0.1:5901" in spice
        assert "password" not in (rdp + spice).lower()
    m.delete()
    assert not list(native.iterdir()) and not list(flat.iterdir())


def test_export_profiles_for_other_pc(tmp_path):
    from bonys_agents import remote
    files = remote.export_profiles(tmp_path, "agent-pc-1", "agent", 3390, 5901, "192.168.178.105")
    names = sorted(f.name for f in files)
    assert names == ["agent-pc-1 (RDP).remmina", "agent-pc-1 (SPICE).remmina", "agent-pc-1.rdp"]
    rdp = (tmp_path / "agent-pc-1.rdp").read_text()
    assert "full address:s:192.168.178.105:3390" in rdp and "username:s:agent" in rdp
    assert "server=192.168.178.105:5901" in (tmp_path / "agent-pc-1 (SPICE).remmina").read_text()
    assert "password" not in "".join(f.read_text().lower() for f in files)


def test_xrdp_step_in_cloud_init():
    guest = cloudinit.GuestConfig(hostname="t", username="agent", password="pw",
                                  apps=apps.resolve(apps.default_app_ids()))
    script = cloudinit.provision_script(guest)
    assert "apt-get install -y xrdp pipewire-module-xrdp" in script
    assert "adduser xrdp ssl-cert" in script
    # startet den Desktop aus /etc/bonys-agents/desktop.env, ohne die Datei Cinnamon
    assert "exec dbus-run-session -- $SESSION_CMD" in script and "SESSION_CMD=cinnamon-session" in script
    # installiert, aber aus – eingeschaltet wird nur bei Bedarf
    assert "systemctl disable --now xrdp xrdp-sesman" in script
    assert "systemctl enable xrdp" not in script and "systemctl start xrdp" not in script
    assert apps.APPS["xrdp"].check == "test -x /usr/sbin/xrdp"
    assert script.index("Telegram Desktop installieren") < script.index("Fernzugriff (RDP) installieren") \
        < script.index("Hermes Agent installieren")
    assert apps.APPS["xrdp"].default and apps.APPS["xrdp"].category == apps.PROGRAM


def test_cli_remote_on_shows_data(datadir, monkeypatch, capsys):
    from bonys_agents import remote
    m = _fake_vm(datadir)
    m.config.apps.append("xrdp")
    m.save()
    monkeypatch.setattr(remote, "firewall_needed", lambda host_os=None: False)
    monkeypatch.setattr(remote, "lan_addresses", lambda: [remote.LanAddress("192.168.1.20", "192.168.1.0/24")])
    assert cli.main(["remote", m.name, "on"]) == 1  # läuft nicht → nur dauerhaft möglich
    assert "dauerhaft" in capsys.readouterr().err
    assert cli.main(["remote", m.name, "on", "--permanent"]) == 0
    out = capsys.readouterr().out
    assert "nächsten Start" in out and "SPICE spice://127.0.0.1:5901 – aus dem Heimnetz" in out
    assert cli.main(["remote", m.name, "off"]) == 0
    assert "Fernzugriff: aus" in capsys.readouterr().out


class _FakeQMP:
    """Nimmt QMP-Befehle entgegen, ohne dass QEMU läuft."""
    log: list = []
    rules: set = set()

    def __init__(self, port, timeout=5.0):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def execute(self, command, **kw):
        _FakeQMP.log.append(command)
        return {}

    def hostfwd_add(self, rule):
        _FakeQMP.log.append(f"add {rule}")
        _FakeQMP.rules.add(rule)

    def hostfwd_remove(self, rule):
        _FakeQMP.log.append(f"remove {rule}")
        _FakeQMP.rules.discard(rule)


class _FakeGA:
    """Gast-Agent: merkt sich die Befehle, liefert eine boot_id."""
    scripts: list = []
    boot_id = "boot-1"
    down = False

    def __init__(self, port, timeout=5.0):
        if _FakeGA.down:
            raise qemu.GuestAgentError("weg")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def run(self, script, timeout=120):
        _FakeGA.scripts.append(script)
        return 0, (_FakeGA.boot_id + "\n") if "boot_id" in script else ""

    def shutdown(self):
        _FakeQMP.log.append("guest-shutdown")


@pytest.fixture
def live_vm(datadir, monkeypatch):
    """Eingerichteter, „laufender“ Agent-PC mit nachgebildetem QMP und Gast-Agent."""
    m = _fake_vm(datadir)
    m.config.apps.append("xrdp")
    m.config.provisioned = True
    m.save()
    m.ensure_remote_ports()
    m.runtime_file.write_text(json.dumps({"qmp_port": 1, "qga_port": 2, "ssh_port": 2222,
                                          "remote_on": False, "spice_lan": False}))
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    _FakeQMP.log, _FakeQMP.rules = [], set()
    _FakeGA.scripts, _FakeGA.boot_id, _FakeGA.down = [], "boot-1", False
    monkeypatch.setattr(vm.qemu, "QMP", _FakeQMP)
    monkeypatch.setattr(vm.qemu, "GuestAgent", _FakeGA)
    return vm.get(m.name)


def test_remote_on_until_shutdown_at_runtime(live_vm):
    m = live_vm
    msg = m.set_remote(True)
    assert "bis zum Herunterfahren" in msg
    assert _FakeQMP.rules == {"tcp:0.0.0.0:3390-:3389"}       # Weiterleitung ohne Neustart
    start = next(x for x in _FakeGA.scripts if "xrdp" in x)
    assert "systemctl start xrdp" in start and "enable" not in start.replace("disable", "")
    assert m.remote_active() and not vm.get(m.name).config.remote_permanent
    assert m.remote_info()["temporary"]
    # Neustart im Gast: neue boot_id → Fernzugriff wird zurückgesetzt
    assert not m.check_remote_reset()
    _FakeGA.boot_id = "boot-2"
    assert m.check_remote_reset()
    assert _FakeQMP.rules == set() and not m.remote_active()


def test_remote_on_permanent_and_off(live_vm):
    m = live_vm
    msg = m.set_remote(True, permanent=True)
    assert "SPICE aus dem Heimnetz ab dem nächsten Start" in msg   # SPICE-Adresse steht beim Start fest
    assert "systemctl enable --now xrdp" in _FakeGA.scripts
    assert vm.get(m.name).config.remote_permanent and m.remote_info()["needs_restart"]
    _FakeGA.boot_id = "boot-2"
    assert not m.check_remote_reset()  # dauerhaft: bleibt auch nach Neustart im Gast an
    assert "aus" in m.set_remote(False)
    assert _FakeQMP.rules == set() and not m.remote_active()
    assert _FakeGA.scripts[-1] == "systemctl disable --now xrdp xrdp-sesman"
    assert not vm.get(m.name).config.remote_permanent
    assert "expire_password" not in _FakeQMP.log  # SPICE lief nur lokal
    # Lief SPICE seit dem Start im Heimnetz: beim Ausschalten das Passwort sofort verfallen lassen
    m.set_remote(True, permanent=True)
    m._update_runtime(spice_lan=True)
    m.set_remote(False)
    assert _FakeQMP.log[-1] == "expire_password"


def test_remote_without_guest_agent_needs_password(live_vm, monkeypatch):
    m = live_vm
    _FakeGA.down = True
    with pytest.raises(vm.NeedsPassword):
        m.set_remote(True)
    assert _FakeQMP.rules == set()  # nichts halb eingeschaltet
    sent = []
    monkeypatch.setattr(vm.VM, "_ssh", lambda self, cmd, script, password=None, log=None:
                        sent.append((script, password)) or 0)
    m.set_remote(True, password="geheim")
    assert sent == [("systemctl disable xrdp xrdp-sesman >/dev/null 2>&1; systemctl start xrdp", "geheim")]
    assert _FakeQMP.rules == {"tcp:0.0.0.0:3390-:3389"}


def test_permanent_remote_opens_ports_at_start(datadir, monkeypatch):
    m = _fake_vm(datadir)
    m.config.apps.append("xrdp")
    m.config.provisioned = True
    m.save()
    m.set_remote(True, permanent=True)
    started = []

    class FakeProc:
        pid = 1

        def __init__(self, cmd, **kw):
            started.append(cmd)
            m.pidfile.write_text("1")

        def poll(self):
            return None

    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/usr/bin/qemu-system-x86_64"))
    monkeypatch.setattr(vm.qemu, "capabilities", lambda qb, cache=None: {"spice": True, "audio": []})
    monkeypatch.setattr(vm.subprocess, "Popen", FakeProc)  # ersetzt Popen überall – darum fester Host:
    monkeypatch.setattr(vm.host, "detect", lambda: _LINUX_HOST)
    vm.get(m.name).start()
    cmd = " ".join(started[0])
    assert "hostfwd=tcp:0.0.0.0:3390-:3389" in cmd and "addr=0.0.0.0,password-secret=spicepw" in cmd
    assert (m.path / "spice-password").read_text() == vm.get(m.name).config.spice_password
    assert m.runtime()["remote_on"] and m.runtime()["spice_lan"]
    vm._children.clear()


# ---------- Herunterfahren ----------
def _copy_as_qemu(tmp_path) -> str:
    """Ein Programm, dessen Prozessname „qemu“ enthält (pid() prüft das)."""
    import shutil
    exe = tmp_path / "qemu-fake"
    shutil.copy(shutil.which("sleep"), exe)
    return str(exe)


@pytest.mark.skipif(not hasattr(__import__("os"), "waitpid") or __import__("os").name != "posix",
                    reason="Zombies gibt es nur unter POSIX")
def test_exited_qemu_child_is_not_running(datadir, tmp_path):
    """Herunterfahren aus der Desktop-App: QEMU ist Kind der App und bleibt sonst als Zombie „laufend“."""
    import subprocess
    import time

    import psutil
    m = _fake_vm(datadir)
    exe = _copy_as_qemu(tmp_path)
    # a) über das aufbewahrte Popen-Objekt (so startet die App QEMU)
    proc = subprocess.Popen([exe, "0.2"], start_new_session=True)
    vm._children[proc.pid] = proc
    m.pidfile.write_text(str(proc.pid))
    assert m.is_running()
    time.sleep(0.6)
    assert m.pid() is None and not m.is_running()
    assert proc.returncode == 0 and proc.pid not in vm._children
    # b) ohne Popen-Objekt: Zombie erkennen und per waitpid einsammeln
    import os
    pid = os.spawnv(os.P_NOWAIT, exe, [exe, "0.2"])
    m.pidfile.write_text(str(pid))
    time.sleep(0.6)
    assert psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    assert not m.is_running()
    assert not psutil.pid_exists(pid)  # eingesammelt


def test_stop_request_returns_immediately_with_countdown(live_vm, monkeypatch):
    m = live_vm
    assert m.status() == "läuft"
    assert m.request_stop()  # kehrt sofort zurück
    assert _FakeQMP.log == ["guest-shutdown"]  # über den Gast-Agent – kein Desktop kann das abfangen
    assert m.status() == vm.STATUS_STOPPING
    assert 0 <= m.stopping_for() < 2
    since = m.runtime()["stopping_since"]
    m.request_stop()  # nochmal drücken: Countdown läuft weiter, beginnt nicht neu
    assert m.runtime()["stopping_since"] == since


def test_stop_falls_back_to_power_off(live_vm, monkeypatch):
    m = live_vm
    state = {"running": True}
    monkeypatch.setattr(vm.VM, "pid", lambda self: 4242 if state["running"] else None)
    monkeypatch.setattr(vm.VM, "is_running", lambda self: state["running"])

    class QuitQMP(_FakeQMP):
        def execute(self, command, **kw):
            _FakeQMP.log.append(command)
            if command == "quit":
                state["running"] = False
            return {}

    monkeypatch.setattr(vm.qemu, "QMP", QuitQMP)
    _FakeGA.down = True  # ohne Gast-Agent: ACPI-Ausschaltknopf
    assert m.stop(timeout=0.3) is True  # Gast reagiert nicht → nach Ablauf hart aus
    assert _FakeQMP.log == ["system_powerdown", "quit"]
    state["running"] = True
    _FakeQMP.log = []
    assert m.stop(force=True) is True and _FakeQMP.log == ["quit"]


def test_guest_power_button_shuts_down_immediately():
    script = cloudinit.provision_script(_guest())
    dropin = script[script.index(f"cat > {cloudinit.LOGIND_DROPIN}"):]
    assert "HandlePowerKey=poweroff" in dropin and "PowerKeyIgnoreInhibited=yes" in dropin
    override = script[script.index(f"cat > {cloudinit.SCHEMA_OVERRIDE}"):script.index("glib-compile-schemas")]
    assert "[org.cinnamon.settings-daemon.plugins.power]\nbutton-power='shutdown'" in override


def test_guest_screen_follows_window():
    script = cloudinit.provision_script(_guest())
    setup = screen.guest_setup_script()
    assert setup in script
    assert f"display-setup-script={screen.SCREEN_SCRIPT}" in setup             # LightDM (Anmeldebildschirm)
    assert "Exec=" + screen.SCREEN_SCRIPT in setup                              # Cinnamon (Autostart)
    assert 'ACTION=="change", SUBSYSTEM=="drm"' in setup                       # udev: DRM-Hotplug
    assert f'RUN+="{screen.EVENT_SCRIPT}"' in setup
    assert "xrandr --output \"$out\" --auto" in setup and "XRDP_SESSION" in setup
    assert "sleep 0.5" in setup                                                 # entprellt
    assert "--mode 800x600" not in script                                       # nicht mehr fest
    # Hintergrundbild als RGBA-PNG (24-Bit-JPG lässt Cinnamon/llvmpipe bei Größenwechseln abstürzen),
    # erst NACH der Schema-Datei, damit die angepasst werden kann
    assert script.index(f"cat > {cloudinit.SCHEMA_OVERRIDE}") < script.index(setup)
    assert f"sed -i 's|{screen.WALLPAPER_JPG}|{screen.WALLPAPER_PNG}|' {screen.SCHEMA_OVERRIDE}" in setup
    assert "add_alpha" in setup and f"systemctl restart --no-block {screen.GUARD_SERVICE}" in setup
    # Wächter: startet Cinnamon im selben Launcher neu (cinnamon-session gäbe nach zwei Neustarts in 60 s auf),
    # Zombies zählen nicht als „läuft“, Launcher beenden nur als letzter Ausweg
    guard = screen._fill(screen._GUARD)
    assert "gsettings set $KEY $NEW; gsettings set $KEY $OLD" in guard
    assert 'KEY="org.cinnamon.launcher memory-limit-enabled"' in guard
    assert "$1 !~ /^Z/" in guard and 'alive "$1" || kill "$1"' in guard
    assert f"+ {screen.GUARD_SECONDS} ))" in guard
    # auch beim Aktualisieren bestehender Agent-PCs
    assert setup in apps.upgrade_script(["brave"], "agent")


def test_guest_screen_scripts_are_valid_shell(tmp_path):
    import shutil
    import subprocess
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash fehlt")
    setup = tmp_path / "setup.sh"
    setup.write_text(screen.guest_setup_script(), "utf-8")
    assert subprocess.run([bash, "-n", str(setup)], capture_output=True).returncode == 0
    for name in ("_APPLY", "_SYNC", "_EVENT", "_GUARD"):
        f = tmp_path / f"{name}.sh"
        f.write_text(screen._fill(getattr(screen, name)), "utf-8")
        assert "@" not in f.read_text("utf-8").replace("@cinnamon", ""), name  # alle Platzhalter ersetzt
        assert subprocess.run(["sh", "-n", str(f)], capture_output=True).returncode == 0, name


@pytest.mark.skipif(sys.platform == "win32", reason="Shell-Skript des Gasts")
@pytest.mark.parametrize("setting, expected", [
    ("auto", ["--output Virtual-1 --auto"]),
    ("fixed:1024x768", ["--output Virtual-1 --mode 1024x768"]),
    # Größe fehlt in der Liste: eigener Modusname, weil „BxH“ schon im X-Server stecken kann
    ("scale:1280x800", ["--output Virtual-1 --mode 1280x800", "--newmode bonys-1280x800 83.50",
                        "--addmode Virtual-1 bonys-1280x800", "--output Virtual-1 --mode bonys-1280x800"]),
])
def test_guest_apply_script_calls_xrandr(tmp_path, setting, expected):
    import subprocess
    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "xrandr.log"
    (fake / "xrandr").write_text(f"""#!/bin/sh
echo "$*" >> {log}
case "$*" in
  --query) printf 'Screen 0: current 800 x 600\nVirtual-1 connected primary 800x600+0+0\n'
           printf '   800x600 60.00*+\n   1024x768 60.00\nrdp0 connected\n' ;;
  "--output Virtual-1 --mode 1280x800") exit 1 ;;
esac
exit 0
""")
    modeline = '"1280x800_60.00"  83.50  1280 1352 1480 1680  800 803 809 831 -hsync +vsync'
    (fake / "cvt").write_text(f"#!/bin/sh\necho 'Modeline {modeline}'\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    cfg = tmp_path / "raw"
    cfg.write_text(setting)
    script = tmp_path / "apply.sh"
    script.write_text(screen._fill(screen._APPLY)
                      .replace(f"/sys/firmware/qemu_fw_cfg/by_name/{screen.FW_CFG_NAME}/raw", str(cfg))
                      .replace("/run/bonys-screen.mode", str(tmp_path / "cache")))
    env = {"PATH": f"{fake}:/usr/bin:/bin"}
    assert subprocess.run(["sh", str(script)], env=env).returncode == 0
    calls = [line for line in log.read_text().splitlines() if line != "--query"]
    assert [c for c in calls if not c.startswith("--newmode")] == [e for e in expected if not e.startswith("--newmode")]
    for e in expected:
        assert any(c.startswith(e) for c in calls), e
    assert not any("rdp0" in c for c in calls)  # RDP-Ausgänge bleiben unberührt
    # In einer RDP-Sitzung passiert gar nichts
    log.unlink()
    subprocess.run(["sh", str(script)], env={**env, "XRDP_SESSION": "1"})
    assert not log.exists()


def test_console_keyboard_applied_immediately():
    script = cloudinit.provision_script(_guest())
    assert script.index('XKBLAYOUT="de"') < script.index("setupcon --force --keyboard-only") \
        < script.index("BONYS-STEP 2/")


# ---------- Lizenz ----------
ROOT = Path(__file__).resolve().parent.parent


def test_license_is_gpl3_unchanged():
    import hashlib
    text = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    assert text.startswith(b"                    GNU GENERAL PUBLIC LICENSE\n                       Version 3")
    assert hashlib.md5(text).hexdigest() == "1ebbd3e34237af26da5dc08a4e440464"  # offizieller Text von gnu.org
    meta = (ROOT / "pyproject.toml").read_text("utf-8")
    assert 'license = "GPL-3.0-or-later"' in meta and "MIT" not in meta


def test_every_python_file_has_spdx_line():
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("packaging/*.py")]
    assert len(files) > 25
    for f in files:
        head = f.read_text("utf-8").lstrip("﻿").splitlines()[:2]
        assert "# SPDX-License-Identifier: GPL-3.0-or-later" in head, f


def test_third_party_licenses_and_about_links():
    import bonys_agents
    third = (ROOT / "THIRD-PARTY-LICENSES").read_text("utf-8")
    for name in ("PySide6", "Qt 6", "psutil", "platformdirs", "pycdlib", "Python", "PyInstaller-Bootloader",
                 "GNU LESSER GENERAL PUBLIC LICENSE", "NICHT mitgeliefert", "QEMU", "Brave"):
        assert name in third, name
    assert bonys_agents.license_location("LICENSE").endswith("LICENSE")
    assert Path(bonys_agents.license_location("THIRD-PARTY-LICENSES")).is_file()
    assert bonys_agents.license_location("GIBTSNICHT").startswith("https://github.com/zappotex/BonysAgents/")


def test_about_dialog_shows_gpl():
    from PySide6.QtWidgets import QApplication, QLabel

    from bonys_agents.gui.about_dialog import AboutDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dlg = AboutDialog()  # festhalten, sonst räumt Python die Labels vorher ab
    texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "Lizenz: <b>GPL-3.0-or-later</b>" in texts and "MIT" not in texts
    assert "LICENSE" in texts and "THIRD-PARTY-LICENSES" in texts
