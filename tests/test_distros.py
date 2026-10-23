# SPDX-License-Identifier: GPL-3.0-or-later
"""Grundsysteme: Kali Linux neben Debian 13 (Abbild, Apps, Einrichtung, Vorlagen und Kurspakete)."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import lzma
import tarfile
from pathlib import Path

import pytest

from bonys_agents import apps, bonysfile, cloudinit, distros, host, images, kurspaket, vm

SUMS = ("aaa  kali-linux-2026.2-cloud-genericcloud-amd64.tar.xz\n"
        "bbb  kali-linux-2026.10-cloud-genericcloud-amd64.tar.xz\n"
        "ccc  kali-linux-2026.10-cloud-genericcloud-arm64.tar.xz\n"
        "ddd  kali-linux-2026.3-installer-amd64.iso\n")


def test_kali_image_takes_newest_version():
    img = images.kali_image("x86_64", SUMS)
    assert img.filename == "kali-linux-2026.10-cloud-genericcloud-amd64.tar.xz"   # 2026.10 nach 2026.2
    assert img.url == f"{images.KALI_BASE}/{img.filename}"
    assert img.hash_algo == "sha256" and img.member == "disk.raw"
    assert img.cache_name == "kali-linux-2026.10-cloud-genericcloud-amd64.qcow2"
    assert images.kali_image("aarch64", SUMS).filename.endswith("-arm64.tar.xz")
    with pytest.raises(RuntimeError):
        images.kali_image("x86_64", "ddd  kali-linux-2026.3-installer-amd64.iso\n")
    assert images.debian_image("x86_64").cache_name == "debian-13-generic-amd64.qcow2"


def _tar_xz(path: Path, members: dict[str, bytes]) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    path.write_bytes(lzma.compress(buf.getvalue()))


def test_extract_member_keeps_zeros_sparse(tmp_path):
    data = b"A" * 100 + bytes(3 * 1024 * 1024) + b"B" * 10
    archive = tmp_path / "a.tar.xz"
    _tar_xz(archive, {"README": b"x", "disk.raw": data})
    out = tmp_path / "disk.raw"
    images.extract_member(archive, "disk.raw", out)
    assert out.read_bytes() == data
    with pytest.raises(RuntimeError, match="fehlt"):
        images.extract_member(archive, "anders.raw", tmp_path / "x")


def _fake_qemu_img(tmp_path: Path) -> Path:
    """„qemu-img convert -f raw -O qcow2 QUELLE ZIEL“ – kopiert nur."""
    script = tmp_path / "qemu-img"
    script.write_text('#!/bin/sh\ncp "$6" "$7"\n')
    script.chmod(0o755)
    return script


@pytest.mark.skipif(not Path("/bin/sh").exists(), reason="braucht /bin/sh")
def test_ensure_image_unpacks_and_reuses_archive(tmp_path, monkeypatch):
    archive = tmp_path / "src.tar.xz"
    _tar_xz(archive, {"disk.raw": b"RAW" * 1000})
    want = hashlib.sha256(archive.read_bytes()).hexdigest()
    img = images.BaseImage(name="Kali", url="https://x/k.tar.xz", sums_url="https://x/SHA256SUMS",
                           filename="k.tar.xz", hash_algo="sha256", member="disk.raw")
    monkeypatch.setattr(images, "expected_hash", lambda image: want)
    loads = []

    class Resp(io.BytesIO):
        headers: dict = {}

    monkeypatch.setattr(images, "_open", lambda url: (loads.append(url), Resp(archive.read_bytes()))[1])
    cache = tmp_path / "cache"
    out = images.ensure_image(img, cache, qemu_img=_fake_qemu_img(tmp_path))
    assert out == cache / "k.qcow2" and out.read_bytes() == b"RAW" * 1000
    assert sorted(p.name for p in cache.iterdir()) == ["k.qcow2", "k.qcow2.sha256"]   # Archiv und Rohdatei weg
    assert images.ensure_image(img, cache) == out and len(loads) == 1                   # aus dem Cache
    # anderer Speicherort: kopiert statt neu geladen
    other = images.ensure_image(img, tmp_path / "cache2", reuse_from=[cache])
    assert other.read_bytes() == out.read_bytes() and len(loads) == 1
    # beschädigtes qcow2 im Cache → neu laden
    out.write_bytes(b"kaputt")
    images.ensure_image(img, cache, qemu_img=_fake_qemu_img(tmp_path))
    assert len(loads) == 2 and out.read_bytes() == b"RAW" * 1000


def test_ensure_image_archive_rejects_bad_download(tmp_path, monkeypatch):
    img = images.BaseImage(name="Kali", url="u", sums_url="s", filename="k.tar.xz", hash_algo="sha256",
                           member="disk.raw")
    monkeypatch.setattr(images, "expected_hash", lambda image: "0" * 64)

    class Resp(io.BytesIO):
        headers: dict = {}

    monkeypatch.setattr(images, "_open", lambda url: Resp(b"falsch"))
    with pytest.raises(RuntimeError, match="Prüfsumme"):
        images.ensure_image(img, tmp_path, qemu_img=Path("/bin/false"))
    assert list(tmp_path.iterdir()) == []


def test_apps_per_distro():
    assert "kali-tools" in apps.default_app_ids(distros.KALI)
    assert "kali-tools" not in apps.default_app_ids()
    assert apps.default_app_ids() == apps.default_app_ids(distros.DEBIAN)
    with pytest.raises(ValueError, match="Debian 13: Kali-Werkzeuge"):
        apps.check_arch(["brave", "kali-tools"], "x86_64")
    apps.check_arch(["brave", "kali-tools"], "x86_64", distros.KALI)
    with pytest.raises(ValueError, match="aarch64: Tor Browser"):
        apps.check_arch(["tor-browser"], "aarch64", distros.KALI)


def test_distro_check():
    distros.check(distros.KALI, "x86_64", "xfce")
    distros.check(distros.DEBIAN, "aarch64", "kde")
    with pytest.raises(ValueError, match="nur auf x86_64"):
        distros.check(distros.KALI, "aarch64", "xfce")
    with pytest.raises(ValueError, match="nur mit Xfce"):
        distros.check(distros.KALI, "x86_64", "cinnamon")
    with pytest.raises(ValueError, match="Unbekanntes Grundsystem"):
        distros.get("tails")


def _guest(distro: str) -> cloudinit.GuestConfig:
    return cloudinit.GuestConfig(hostname="k", username="agent", password="pw1234", desktop="xfce", distro=distro,
                                 apps=apps.resolve(["brave", "kali-tools"] if distro == distros.KALI else ["brave"]))


def test_provision_script_kali_steps():
    script = cloudinit.provision_script(_guest(distros.KALI))
    titles = [ln.strip().split(" ", 3)[3].rstrip('"') for ln in script.splitlines()
              if ln.strip().startswith(f'echo "{cloudinit.STEP_MARKER}')]
    assert titles[1].startswith("Kali: Kernel mit Grafik")
    assert titles[-1] == "Kali: auf den normalen Kernel umstellen"       # erst nach allen Apps
    assert "Kali-Werkzeuge installieren" in titles
    debian = cloudinit.provision_script(_guest(distros.DEBIAN))
    assert "Kali" not in debian and "linux-image-" not in debian
    # Alle Teile des Cloud-Kernels raus (sonst Kernel-Panic) und GRUB danach geprüft
    assert "'linux-*cloud*'" in cloudinit.KALI_KERNEL_SWITCH and "update-grub" in cloudinit.KALI_KERNEL_SWITCH
    assert "autologin.conf" in cloudinit.KALI_PREPARE
    assert "fonts-noto-cjk" in cloudinit.KALI_PREPARE and "fonts-noto-cjk" not in debian


@pytest.fixture
def x86(monkeypatch):
    real = host.detect()
    monkeypatch.setattr(vm.host, "detect", lambda: dataclasses.replace(real, arch="x86_64"))


def test_create_kali_vm(datadir, monkeypatch, tmp_path, x86):
    base = tmp_path / "kali.qcow2"
    base.write_bytes(b"img")
    used = []
    monkeypatch.setattr(vm.images, "base_image", lambda distro, arch: used.append(distro) or images.debian_image(arch))
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None, qemu_img=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    m = vm.create("kali1", "pw1234", desktop="xfce", distro=distros.KALI)
    assert used == [distros.KALI]
    assert m.config.distro == distros.KALI and "kali-tools" in m.config.apps
    assert vm.get("kali1").config.distro == distros.KALI                  # in vm.json gespeichert
    assert "kali-tools" not in [a.id for a in m.missing_apps()]
    with pytest.raises(ValueError, match="nur mit Xfce"):
        vm.create("kali2", "pw1234", desktop="cinnamon", distro=distros.KALI)
    with pytest.raises(ValueError, match="Kali-Werkzeuge"):
        vm.create("deb1", "pw1234", app_ids=["kali-tools"])


def test_old_vm_json_is_debian(datadir, monkeypatch, tmp_path):
    base = tmp_path / "b.qcow2"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None, qemu_img=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    m = vm.create("alt", "pw1234")
    data = vm.storage.read_json(m.path / "vm.json")
    data.pop("distro")
    vm.write_json(m.path / "vm.json", data)
    assert vm.get("alt").config.distro == distros.DEBIAN
    data["distro"] = "tails"
    vm.write_json(m.path / "vm.json", data)
    with pytest.raises(ValueError, match="distro"):
        vm.VM(m.path)


def test_recipe_and_course_package_carry_distro():
    m = {"username": "agent", "desktop": "xfce", "distro": "kali", "apps": [{"id": "kali-tools"}]}
    r = bonysfile.recipe(m)
    assert r["distro"] == "kali" and r["app_ids"] == ["kali-tools"]
    assert bonysfile.recipe({"username": "agent"})["distro"] == distros.DEBIAN
    rez = kurspaket._rezept({"distro": "kali", "apps": ["kali-tools"]})
    assert rez.distro == "kali" and rez.desktop == "xfce"                 # Standard-Desktop von Kali
    assert rez.fuer_erstellen()["distro"] == "kali"
    assert kurspaket._rezept({}).distro == distros.DEBIAN
    with pytest.raises(kurspaket.PaketFehler, match="Grundsystem"):
        kurspaket._rezept({"distro": "tails"})


# ---------------------------------------------------------------- Oberfläche
@pytest.fixture
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _dialog(monkeypatch, arch: str, captured: dict):
    from types import SimpleNamespace

    from bonys_agents.gui import create_dialog

    class Worker:
        def __init__(self, params):
            captured.update(params)
            self.progress = self.hint = self.finished_ok = self.failed = SimpleNamespace(connect=lambda f: None)

        def start(self):
            pass

        def isRunning(self):  # noqa: N802
            return True

    monkeypatch.setattr(create_dialog, "CreateWorker", Worker)
    return create_dialog.CreateDialog(host.HostInfo(os="linux", arch=arch, cpus=4, ram_mb=16384, accel="kvm"))


def test_create_dialog_kali(qapp, datadir, monkeypatch):
    captured: dict = {}
    dlg = _dialog(monkeypatch, "x86_64", captured)
    tools = dlg.app_boxes["kali-tools"]
    assert dlg.distro().id == distros.DEBIAN and tools.isHidden() and not tools.isChecked()
    assert dlg.desktop.isEnabled()
    dlg.base.setCurrentIndex(dlg.base.findData(":kali"))
    assert dlg.distro().id == distros.KALI
    assert not tools.isHidden() and tools.isChecked()
    assert dlg.desktop.currentData() == "xfce" and not dlg.desktop.isEnabled()
    assert "Sicherheitstests" in dlg.base_info.text()
    dlg.pw1.setText("pw1234")
    dlg.pw2.setText("pw1234")
    dlg._create()
    assert captured["distro"] == distros.KALI and captured["desktop"] == "xfce"
    assert "kali-tools" in captured["app_ids"]
    # zurück zu Debian: Kali-Werkzeuge wieder aus
    dlg.base.setCurrentIndex(dlg.base.findData(":debian"))
    assert tools.isHidden() and not tools.isChecked() and dlg.desktop.isEnabled()


def test_create_dialog_no_kali_on_arm(qapp, datadir, monkeypatch):
    dlg = _dialog(monkeypatch, "aarch64", {})
    assert dlg.base.findData(":kali") < 0 and dlg.base.findData(":debian") >= 0


def test_tor_desktop_file_both_names():
    """Debian 13: torbrowser.desktop, neuere torbrowser-launcher (Kali): org.torproject.torbrowser-launcher.desktop."""
    install = apps.APPS["tor-browser"].install
    assert "torbrowser.desktop org.torproject.torbrowser-launcher.desktop" in install


def test_docker_uses_debian_branch_on_kali():
    assert '= kali ] && CODENAME=trixie' in apps.APPS["docker"].install
