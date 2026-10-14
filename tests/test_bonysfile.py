# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen weitergeben (.bonys): Manifest, Frisch-Prüfung, Lizenzen, Export/Import, Prüfsummen, Abbruch.

Alle „Geheimnisse“ hier sind Dummy-Werte.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

from bonys_agents import __version__, apps, bonysfile, cli, host, qemu, templates, vm

QEMU_IMG = shutil.which("qemu-img")
needs_qemu_img = pytest.mark.skipif(QEMU_IMG is None, reason="qemu-img nicht installiert")
needs_gnu = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="braucht GNU coreutils/findutils")
DUMMY = "DUMMY-GEHEIMNIS-NUR-TEST-0815"


def _use_real_qemu_img(monkeypatch):
    monkeypatch.setattr(qemu, "find_binary",
                        lambda name, os_: Path(QEMU_IMG) if name == "qemu-img" else Path("/bin/true"))


def _make_template(library: Path, name="kurs", **kw) -> templates.Template:
    d = templates.templates_dir(library) / name
    d.mkdir(parents=True)
    # etwas Inhalt, damit die Prüfsumme nicht die einer leeren Platte ist
    raw = d / "inhalt.raw"
    with raw.open("wb") as f:
        f.write(b"\x42" * 1024 * 1024)
        f.truncate(64 * 1024 * 1024)
    subprocess.run([QEMU_IMG, "convert", "-q", "-O", "qcow2", str(raw), str(d / "disk.qcow2")], check=True)
    raw.unlink()
    defaults = dict(description="Kurs-Vorlage", created="2026-10-06T10:00:00+00:00", arch=host.detect().arch,
                    apps=["brave", "telegram", "obsidian", "hermes", "claude-code"], disk_gb=8,
                    source="agent-pc-1", debian="13.1", personal_data_removed=True)
    defaults.update(kw)
    t = templates.Template(path=d, name=name, size=(d / "disk.qcow2").stat().st_size, **defaults)
    t.save()
    return t


# ---------- Apps: Lizenzen ----------
def test_not_redistributable_apps_have_uninstall():
    assert apps.not_redistributable(list(apps.APPS)) == ["obsidian", "claude-code"]
    for app_id in apps.not_redistributable(list(apps.APPS)):
        assert apps.APPS[app_id].uninstall.strip()
    for a in apps.APPS.values():
        assert a.redistributable or a.uninstall


# ---------- Manifest ----------
def _manifest(**over) -> dict:
    t = templates.Template(path=Path("/x"), name="kurs", description="Kurs", created="2026-10-06T10:00:00+00:00",
                           arch="x86_64", apps=["brave", "claude-code", "mission-control", "docker"], disk_gb=40,
                           desktop="xfce", app_info={"mission-control": {"version": "0.1.0"}})
    m = bonysfile.build_manifest(t, creator="Kursleiter", version="1.2", disk_size=123, disk_sha256="a" * 64,
                                 virtual_size=40 * 2**30, debian="13.1", versions={"brave": "1.80.1"},
                                 removed=["claude-code"])
    m.update(over)
    return m


def test_manifest_contents_and_validation():
    m = bonysfile.validate_manifest(_manifest())
    assert m["format"] == bonysfile.FORMAT_ID and m["arch"] == "amd64" and m["min_version"] == bonysfile.MIN_VERSION
    assert [a["id"] for a in m["apps"]] == ["brave", "mission-control", "docker"]
    assert m["apps"][0]["version"] == "1.80.1" and m["apps"][1]["version"] == "0.1.0"
    assert m["reinstall"] == [{"id": "claude-code", "name": "Claude Code", "note": bonysfile.REINSTALL_NOTE}]
    assert m["recommended"]["disk_gb"] == 40 and m["recommended"]["cpus"] == 2
    assert m["recommended"]["ram_mb"] >= 2048
    assert m["files"]["disk.qcow2"] == {"size": 123, "sha256": "a" * 64}
    assert m["creator"] == "Kursleiter" and m["version"] == "1.2" and m["fresh_check"]["passed"]
    json.dumps(m)  # nur JSON-Typen
    text = bonysfile.describe_manifest(m)
    assert "Kursleiter" in text and "Claude Code" in text and "amd64" in text


@pytest.mark.parametrize("over, match", [
    ({"format": "etwas-anderes"}, "Keine Vorlagen-Datei"),
    ({"format_version": 99}, "neuer"),
    ({"min_version": "99.0.0"}, "neuer"),
    ({"arch": "riscv64"}, "Architektur"),
    ({"name": "../../boese"}, "Name"),
    ({"username": "Root; rm -rf"}, "Benutzername"),
    ({"desktop": "unbekannt"}, "Desktop"),
    ({"files": {"disk.qcow2": {"size": 1, "sha256": "nicht-hex"}}}, "ungültiger Eintrag"),
    ({"files": {"disk.qcow2": {"size": 1, "sha256": "a" * 64}, "../x": {"size": 1, "sha256": "a" * 64}}},
     "ungültiger Eintrag"),
    ({"apps": [{"id": "$(boese)"}]}, "App-Liste"),
    ({"keyboard": "de'; echo"}, "keyboard"),
])
def test_manifest_rejects_bad_values(over, match):
    with pytest.raises(ValueError, match=match):
        bonysfile.validate_manifest(_manifest(**over))


def test_min_version_is_not_newer_than_this_version():
    assert bonysfile._version_tuple(bonysfile.MIN_VERSION) <= bonysfile._version_tuple(__version__)


def test_recipe_uses_desktop_apps_and_reinstall():
    r = bonysfile.recipe(_manifest())
    assert r["desktop"] == "xfce" and r["disk_gb"] == 40 and r["username"] == "agent"
    # Docker ist nur Baustein (kommt mit Mission Control), Claude Code kommt aus der offiziellen Quelle
    assert r["app_ids"] == ["brave", "mission-control", "claude-code"]


# ---------- Frisch-Prüfung ----------
SECRETS = {
    "home/agent/.hermes/.env": f"OPENAI_API_KEY={DUMMY}",
    "home/agent/.hermes/hermes-agent/run.py": "programm",   # Programm – darf bleiben
    "home/agent/.ssh/id_ed25519": DUMMY,
    "home/agent/.config/BraveSoftware/Brave-Browser/Default/Cookies": DUMMY,
    "home/agent/.var/app/org.telegram.desktop/data/TelegramDesktop/tdata/key_datas": DUMMY,
    "home/agent/.bash_history": f"export TOKEN={DUMMY}",
    "home/agent/.npmrc": f"//registry.npmjs.org/:_authToken={DUMMY}",
    "home/agent/.docker/config.json": json.dumps({"auths": {"x": {"auth": DUMMY}}}),
    "home/agent/.claude/.credentials.json": DUMMY,
    "etc/wireguard/kurs.conf": f"[Interface]\nPrivateKey = {DUMMY}\n",
    "root/.ssh/authorized_keys": DUMMY,
    "root/.bash_history": DUMMY,
    "opt/bonys-mission-control/.env.example": "SESSION_SECRET=__GENERATE__\nPORT=8787\n",
    "opt/bonys-mission-control/.env": f"SESSION_SECRET={DUMMY}\nPORT=8787\n",
    "var/lib/docker/volumes/bonys-mission-control-data/_data/db.sqlite": DUMMY,
}
HARMLESS = {
    "home/agent/.npmrc": "prefix=/home/agent/.local\n",
    "home/agent/.docker/config.json": "{}",
    "home/agent/.bashrc": "bleibt",
    "home/agent/Schreibtisch/brave-browser.desktop": "x",
    "home/agent/.config/obsidian/obsidian.json": "{}",
    "home/agent/.hermes/skills/x/SKILL.md": "x",
    "opt/bonys-mission-control/.env.example": "SESSION_SECRET=__GENERATE__\n",
    "opt/bonys-mission-control/.env": "SESSION_SECRET=__GENERATE__\n",
    "etc/ssh/sshd_config": "x",
}


def _fake_root(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "wurzel"
    for rel, content in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    return root


def _run_check(root: Path, strict=False, boot: float | None = None, removed=()) -> str:
    env = {**os.environ, "BONYS_ROOT": str(root), "BONYS_BOOT": str(int(boot if boot is not None else
                                                                            time.time() + 3600))}
    script = bonysfile.check_script("agent", strict=strict, removed_apps=removed)
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=True).stdout


@needs_gnu
def test_fresh_check_finds_dummy_secrets_without_printing_them(tmp_path):
    root = _fake_root(tmp_path, SECRETS)
    out = _run_check(root)
    assert DUMMY not in out  # nie Inhalte
    assert out.rstrip().endswith(bonysfile.CHECK_DONE)
    found = bonysfile.parse_findings(out)
    paths = {f.path.replace(str(root), "") for f in found}
    cats = {f.category for f in found}
    for p in ("/home/agent/.hermes/.env", "/home/agent/.ssh", "/home/agent/.config/BraveSoftware",
              "/home/agent/.var/app/org.telegram.desktop", "/home/agent/.bash_history", "/home/agent/.npmrc",
              "/home/agent/.docker/config.json", "/home/agent/.claude", "/etc/wireguard/kurs.conf",
              "/root/.ssh/authorized_keys", "/root/.bash_history",
              "/opt/bonys-mission-control/.env (SESSION_SECRET)",
              "/var/lib/docker/volumes/bonys-mission-control-data/_data"):
        assert p in paths, p
    assert {"wireguard", "rootssh", "history", "tokens", "mc-secrets", "mc-data"} <= cats
    assert "/home/agent/.hermes/hermes-agent" not in paths  # das Programm bleibt
    text = bonysfile.format_findings(found)
    assert "WireGuard" in text and "Hermes" in text and DUMMY not in text


@needs_gnu
def test_fresh_check_clean_image_has_no_findings(tmp_path):
    root = _fake_root(tmp_path, HARMLESS)
    assert bonysfile.parse_findings(_run_check(root)) == []
    # streng: Hostschlüssel, Maschinen-ID, Passwort-Hash und nicht entfernte Apps zählen jetzt auch
    (root / "etc/ssh/ssh_host_ed25519_key").write_text(DUMMY)
    (root / "etc/machine-id").write_text("0123456789abcdef\n")
    (root / "etc/shadow").write_text(f"root:!:19000::::::\nagent:$6${DUMMY}:19000::::::\nnobody:*:1::::::\n")
    assert bonysfile.parse_findings(_run_check(root)) == []
    out = _run_check(root, strict=True)
    assert DUMMY not in out
    cats = {(f.category, f.path.replace(str(root), "")) for f in bonysfile.parse_findings(out)}
    assert ("hostkeys", "/etc/ssh/ssh_host_ed25519_key") in cats and ("machine-id", "/etc/machine-id") in cats
    assert ("password", "/etc/shadow (agent)") in cats
    assert not any(p.endswith("(root)") or p.endswith("(nobody)") for _c, p in cats)


@needs_gnu
def test_fresh_check_ignores_what_the_check_boot_created(tmp_path):
    """Vor dem Bereinigen: Was erst beim Start der Prüfkopie entstand (neuer Schlüsselbund …), ist kein Fund."""
    root = _fake_root(tmp_path, {"home/agent/.local/share/keyrings/login.keyring": "neu",
                                 "home/agent/.hermes/.env": DUMMY})
    boot = time.time() - 600
    old = boot - 3600
    os.utime(root / "home/agent/.hermes/.env", (old, old))
    paths = {f.path.replace(str(root), "") for f in bonysfile.parse_findings(_run_check(root, boot=boot))}
    assert paths == {"/home/agent/.hermes/.env"}
    # streng (nach dem Verallgemeinern) zählt alles
    paths = {f.path.replace(str(root), "") for f in bonysfile.parse_findings(_run_check(root, strict=True,
                                                                                        boot=boot))}
    assert "/home/agent/.local/share/keyrings" in paths


def test_prepare_script_removes_only_not_redistributable_apps():
    s = bonysfile.prepare_script("agent", ["brave", "obsidian", "claude-code", "hermes"], ["obsidian", "claude-code"])
    assert "apt-get purge -y obsidian" in s and ".local/share/claude" in s
    assert "brave-browser-stable" not in s  # Brave bleibt
    assert s.index("Versionen") < s.index("Obsidian (Notizen) entfernen") < s.index("Passwörter sperren")
    assert "usermod -p '!'" in s and s.rstrip().endswith(f'echo "{bonysfile.PREP_DONE}"')
    if shutil.which("bash"):
        subprocess.run(["bash", "-n"], input=s, text=True, check=True)
        for strict in (False, True):
            subprocess.run(["bash", "-n"], input=bonysfile.check_script("agent", strict, ["claude-code"]),
                           text=True, check=True)


def test_parse_versions_and_findings():
    out = ("x\nBONYS-APPVERSION\tbrave\t1.80.1\nBONYS-APPVERSION\thermes\t\nBONYS-FUND\thistory\t/root/.x\n"
           "BONYS-APPVERSION\topenclaw\tHermes Agent v0.22.0+2200.geb75627 (2026.9.24) · stable\n"
           "BONYS-APPVERSION\tdocker\t5:29.9.1-1~debian.13~trixie\nBONYS-APPVERSION\txrdp\t0.10.1-3.1+deb13u2\n"
           "BONYS-APPVERSION\ttelegram\t7.3\nBONYS-APPVERSION\tvpn\tunbekannt\n")
    assert bonysfile.parse_versions(out) == {"brave": "1.80.1", "openclaw": "0.22.0", "docker": "29.9.1",
                                             "xrdp": "0.10.1", "telegram": "7.3", "vpn": "unbekannt"}
    assert bonysfile.parse_findings(out) == [bonysfile.Finding("history", "/root/.x")]


# ---------- Export/Import mit echtem qemu-img, ohne echten Gast ----------
class _FakeCopy:
    def __init__(self, work: Path):
        self.path = work
        self.stopped = False

    def stop(self, timeout=0):
        self.stopped = True

    def power_off(self):
        pass


def _fake_guest(monkeypatch, findings_first="", findings_after="", seen=None):
    seen = seen if seen is not None else {}

    def start(t, work, qemu_img):
        work.mkdir(parents=True, exist_ok=True)
        qemu.create_overlay(qemu_img, t.disk, work / "disk.qcow2")
        seen["copy"] = _FakeCopy(work)
        return seen["copy"]

    def run(copy, script, password, has_agent, timeout, what="", poll=None):
        seen.setdefault("scripts", []).append((what, script))
        if poll:
            poll()
        if what == "Frisch-Prüfung":
            strict = "STRICT=1" in script
            return (findings_after if strict else findings_first) + bonysfile.CHECK_DONE + "\n"
        if what == "Vorbereiten":
            return f"{bonysfile.VERSION_MARKER}\tbrave\t1.80.1\nentfernt: Claude Code\n{bonysfile.PREP_DONE}\n"
        return "BONYS-DEBIAN 13.2\nBONYS-GENERALIZED\n"

    monkeypatch.setattr(bonysfile, "_start_export_copy", start)
    monkeypatch.setattr(templates, "_wait_guest_agent", lambda copy, progress: True)
    monkeypatch.setattr(templates, "_run_in_copy", run)
    return seen


@needs_qemu_img
def test_export_import_roundtrip(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    t = _make_template(vm.vms_dir())
    before = hashlib.sha256(t.disk.read_bytes()).hexdigest()
    seen = _fake_guest(monkeypatch)
    preview = tmp_path / "bild.png"
    preview.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    steps = []
    out = bonysfile.export("kurs", tmp_path, creator="Kursleiter", version="1.0", preview=preview,
                           progress=lambda *a: steps.append(a[1]))
    assert out == tmp_path / "kurs-1.0.bonys" and steps[-1] == 1.0 and steps == sorted(steps)
    whats = [w for w, _s in seen["scripts"]]
    assert whats == ["Frisch-Prüfung", "Vorbereiten", "Verallgemeinern", "Frisch-Prüfung"]
    prep = seen["scripts"][1][1]
    assert "Claude Code entfernen" in prep and "Obsidian (Notizen) entfernen" in prep
    assert "cloud-init clean" in seen["scripts"][2][1]
    assert seen["copy"].stopped
    assert hashlib.sha256(t.disk.read_bytes()).hexdigest() == before  # Vorlage unverändert
    assert not (templates.templates_dir(vm.vms_dir()) / ".kurs.export").exists()  # aufgeräumt

    with tarfile.open(out) as tar:
        assert tar.getnames() == ["manifest.json", "preview.png", "disk.qcow2"]
    m = bonysfile.read_manifest(out)
    assert [a["id"] for a in m["apps"]] == ["brave", "telegram", "hermes"]
    assert {a["id"] for a in m["reinstall"]} == {"obsidian", "claude-code"}
    assert m["apps"][0]["version"] == "1.80.1" and m["debian"] == "13.2" and m["creator"] == "Kursleiter"
    assert bonysfile.read_preview(out).startswith(b"\x89PNG")

    lib2 = tmp_path / "anderer-rechner" / "BonysAgents"
    imported = bonysfile.import_bundle(out, location=lib2, name="kurs-2")
    assert imported.path == lib2 / "_templates" / "kurs-2" and qemu.backing_file(imported.disk) is None
    assert imported.apps == ["brave", "telegram", "hermes"] and imported.reinstall == ["obsidian", "claude-code"]
    assert imported.creator == "Kursleiter" and imported.version == "1.0" and imported.personal_data_removed
    assert imported.preview == "preview.png" and (imported.path / "preview.png").exists()
    assert hashlib.sha256(imported.disk.read_bytes()).hexdigest() == m["files"]["disk.qcow2"]["sha256"]
    loaded = templates.Template.load(imported.path)
    assert loaded.reinstall == ["obsidian", "claude-code"]
    with pytest.raises(FileExistsError):
        bonysfile.import_bundle(out, location=lib2, name="kurs-2")
    with pytest.raises(FileExistsError):
        bonysfile.export("kurs", out)  # gibt es schon


@needs_qemu_img
def test_export_blocked_by_findings_until_cleaned(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    _make_template(vm.vms_dir())
    fund = f"{bonysfile.FUND_MARKER}\twireguard\t/etc/wireguard/kurs.conf\n"
    seen = _fake_guest(monkeypatch, findings_first=fund)
    with pytest.raises(bonysfile.NotFreshError) as e:
        bonysfile.export("kurs", tmp_path)
    assert not e.value.strict and e.value.findings == [bonysfile.Finding("wireguard", "/etc/wireguard/kurs.conf")]
    assert "WireGuard" in str(e.value) and [w for w, _s in seen["scripts"]] == ["Frisch-Prüfung"]
    assert list(tmp_path.glob("*.bonys*")) == []
    # bereinigen (nur in der Kopie) → Export geht durch
    out = bonysfile.export("kurs", tmp_path, clean=True)
    assert out.exists()
    # bleibt nach dem Bereinigen etwas übrig, bricht der Export ab
    _fake_guest(monkeypatch, findings_after=f"{bonysfile.FUND_MARKER}\thostkeys\t/etc/ssh/ssh_host_rsa_key\n")
    with pytest.raises(bonysfile.NotFreshError) as e:
        bonysfile.export("kurs", tmp_path / "zwei.bonys", clean=True)
    assert e.value.strict and not (tmp_path / "zwei.bonys").exists()


@needs_qemu_img
def test_clone_template_needs_clean(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    _make_template(vm.vms_dir(), personal_data_removed=False)
    seen = _fake_guest(monkeypatch)
    with pytest.raises(bonysfile.NotFreshError) as e:
        bonysfile.export("kurs", tmp_path)
    assert e.value.not_fresh_template and "scripts" not in seen  # gar nicht erst gestartet
    assert bonysfile.export("kurs", tmp_path, clean=True).exists()


@needs_qemu_img
def test_export_cancel_cleans_up(datadir, monkeypatch, tmp_path):
    _use_real_qemu_img(monkeypatch)
    _make_template(vm.vms_dir())
    _fake_guest(monkeypatch)
    cancel = threading.Event()

    def progress(phase, frac, msg):
        if phase == "convert":
            cancel.set()

    target = tmp_path / "ziel"
    target.mkdir()
    with pytest.raises(bonysfile.Cancelled):
        bonysfile.export("kurs", target, progress=progress, cancel=cancel)
    assert list(target.iterdir()) == []
    assert not (templates.templates_dir(vm.vms_dir()) / ".kurs.export").exists()


def _bundle(tmp_path: Path, disk: bytes = b"QFI\xfb" + b"\0" * 1020, **over) -> Path:
    sha = hashlib.sha256(disk).hexdigest()
    m = _manifest(files={"disk.qcow2": {"size": len(disk), "sha256": sha}}, arch=bonysfile.arch_name(
        host.detect().arch), **over)
    d = tmp_path / "disk.qcow2"
    d.write_bytes(disk)
    return bonysfile.write_bundle(tmp_path / "kurs.bonys", m, d)


def test_import_rejects_tampered_disk(datadir, tmp_path):
    f = _bundle(tmp_path)
    data = bytearray(f.read_bytes())
    pos = data.rfind(b"QFI\xfb")
    data[pos + 10] ^= 0xFF  # ein Byte in der Festplatte verändern
    f.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="Prüfsumme"):
        bonysfile.import_bundle(f, location=tmp_path / "lib")
    assert not any((tmp_path / "lib" / "_templates").iterdir())


def test_import_rejects_truncated_and_foreign_files(datadir, tmp_path):
    f = _bundle(tmp_path)
    f.write_bytes(f.read_bytes()[:3000])
    with pytest.raises((ValueError, tarfile.TarError, EOFError)):
        bonysfile.import_bundle(f, location=tmp_path / "lib")
    bad = tmp_path / "boese.bonys"
    payload = tmp_path / "x"
    payload.write_text(json.dumps(_manifest()))
    with tarfile.open(bad, "w") as tar:
        tar.add(payload, arcname="manifest.json")
        tar.add(payload, arcname="../../etc/passwd")
    with pytest.raises(ValueError, match="Unerwarteter Eintrag"):
        bonysfile.import_bundle(bad, location=tmp_path / "lib")
    with tarfile.open(bad, "w") as tar:
        tar.add(payload, arcname="disk.qcow2")
    assert not bonysfile.is_bonys(bad)
    with pytest.raises(ValueError, match="manifest.json"):
        bonysfile.read_manifest(bad)


def test_cli_parses_export_import():
    p = cli.build_parser()
    a = p.parse_args(["template", "export", "kurs", "/tmp/x.bonys", "--creator", "K", "--version", "2",
                      "--clean"])
    assert (a.name, a.file, a.creator, a.version, a.clean) == ("kurs", "/tmp/x.bonys", "K", "2", True)
    a = p.parse_args(["template", "export", "kurs"])
    assert a.file is None
    a = p.parse_args(["template", "import", "x.bonys", "--create", "pc-1", "--ram", "4096"])
    assert (a.create, a.ram, a.recipe) == ("pc-1", 4096, None)
    a = p.parse_args(["template", "import", "x.bonys", "--recipe", "pc-2"])
    assert a.recipe == "pc-2"


def test_foreign_arch_uses_tcg(datadir, monkeypatch):
    other = "aarch64" if host.detect().arch == "x86_64" else "x86_64"
    p = vm.vms_dir() / "fremd"
    p.mkdir(parents=True)
    (p / "vm.json").write_text(json.dumps(vm.VMConfig(name="fremd", arch=other, cpus=1, ram_mb=2048,
                                                      provisioned=True).__dict__))
    captured = {}
    monkeypatch.setattr(qemu, "build_command", lambda spec: captured.update(spec=spec) or ["true"])
    monkeypatch.setattr(qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(qemu, "find_aarch64_firmware", lambda b: Path("/x.fd"))
    monkeypatch.setattr(qemu, "capabilities", lambda b, cache: {"spice": False, "audio": [], "displays": []})
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gestartet")))
    with pytest.raises(RuntimeError, match="gestartet"):
        vm.VM(p)._launch(headless=True)
    assert captured["spec"].accel == "tcg" and captured["spec"].arch == other
