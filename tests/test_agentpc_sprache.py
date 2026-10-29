# SPDX-License-Identifier: GPL-3.0-or-later
"""Sprache im Agent-PC (Plan Englisch, Phase 3): Locale, Tastatur, Ordner, Starter und Hermes-Stimme je Sprache."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import apps, cli, cloudinit, desktops, i18n, kurspaket, vm


def _guest(locale: str, keyboard: str = "de", app_ids=("hermes", "claude-code", "obsidian")):
    return cloudinit.GuestConfig(hostname="pc", username="agent", password="pw1234", apps=apps.resolve(list(app_ids)),
                                 locale=locale, keyboard=keyboard)


# Die Skripte laufen im Agent-PC (Linux); unter Windows gibt es kein bash zum Prüfen
nur_mit_bash = pytest.mark.skipif(sys.platform.startswith("win"), reason="braucht bash")


def _bash(script: str, env: dict | None = None) -> str:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True,
                          env=env or {"PATH": "/usr/bin:/bin"}).stdout.strip()


@nur_mit_bash
@pytest.mark.parametrize(("locale", "lang", "ordner"), [("de_DE.UTF-8", "de", "Schreibtisch"),
                                                         ("en_US.UTF-8", "en", "Desktop")])
def test_provisioning_follows_locale(locale, lang, ordner):
    script = cloudinit.provision_script(_guest(locale, "us" if lang == "en" else "de"))
    assert f"update-locale LANG={locale}" in script
    assert f'DESKTOP_DIR="$AGENT_HOME/{ordner}"' in script
    assert f"AGENT_LANG={lang}" in script and "export AGENT_USER AGENT_HOME DESKTOP_DIR AGENT_LANG" in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


@nur_mit_bash
@pytest.mark.parametrize(("inhalt", "erwartet"), [("LANG=de_DE.UTF-8\n", "de /h/Schreibtisch"),
                                                  ("LANG=en_US.UTF-8\n", "en /h/Desktop"),
                                                  ("", "de /h/Schreibtisch")])   # alte Agent-PCs: deutsch
def test_guest_language_read_from_locale_file(tmp_path, inhalt, erwartet):
    f = tmp_path / "locale"
    f.write_text(inhalt)
    script = "AGENT_HOME=/h\n" + cloudinit.GUEST_LANG.replace("/etc/default/locale", str(f)) + \
        '\necho "$AGENT_LANG $DESKTOP_DIR"'
    # Das LANG der aufrufenden Sitzung zählt nicht, nur die Einstellung des Agent-PCs
    assert _bash(script, {"PATH": "/usr/bin:/bin", "LANG": "fr_FR.UTF-8"}) == erwartet


def test_later_installs_detect_language_in_guest():
    for script in (cloudinit.app_install_script(apps.APPS["hermes"], "agent"),
                   cloudinit.desktop_install_script(desktops.get("xfce"), "agent", make_default=False)):
        assert cloudinit.GUEST_LANG in script
        assert "Schreibtisch" not in script.split(cloudinit.GUEST_LANG)[0]
    xdg = desktops.install_script(desktops.get("xfce"))
    assert "/etc/default/locale" in xdg and "xdg-user-dirs-update" in xdg


@nur_mit_bash
def test_hermes_voice_matches_language():
    install = apps.APPS["hermes"].install
    assert "HL=de; HP=de_DE-thorsten-medium; HE=de-DE-KatjaNeural" in install
    assert "HL=en; HP=en_US-lessac-medium; HE=en-US-AriaNeural" in install
    assert "stt.language $HL" in install and "bonys-hermes-sprachmodell $HP" in install
    assert subprocess.run(["bash", "-n"], input=install, text=True).returncode == 0


@nur_mit_bash
@pytest.mark.parametrize("app_id", ["hermes", "openclaw", "claude-code", "mission-control", "n8n"])
def test_launchers_are_bilingual(app_id):
    install = apps.APPS[app_id].install
    for block in install.split("[Desktop Entry]")[1:]:
        entry = block.split("EOF")[0]
        if "Comment=" in entry:
            assert "Comment[de]=" in entry, entry
    assert subprocess.run(["bash", "-n"], input=install, text=True).returncode == 0


def test_agent_apps_launcher_bilingual():
    text = (Path(__file__).parents[1] / "agent-apps" / "agenten-apps.desktop").read_text("utf-8")
    assert "Name=Agent Apps" in text and "Name[de]=Agenten-Apps" in text and "Comment[de]=" in text


def test_folders_named_by_language():
    obsidian, claude = apps.APPS["obsidian"].install, apps.APPS["claude-code"].install
    assert '"$AGENT_HOME/Agent Notes"' in obsidian
    assert "P=Projects" in claude and '"$HOME/Projects"' in claude
    namen = [p for item in cloudinit.PERSONAL_DATA for p in item.paths]
    assert "Agent Notes" in namen and "Projects" in namen


def test_create_uses_app_language_by_default(datadir, monkeypatch, tmp_path):
    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None, qemu_img=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    gesehen = []
    monkeypatch.setattr(vm.cloudinit, "write_seed_iso", lambda path, guest, instance_id: gesehen.append(guest))
    monkeypatch.setattr(i18n, "_aktiv", "en")
    m = vm.create("englisch", "pw1234")
    assert (gesehen[-1].locale, gesehen[-1].keyboard) == ("en_US.UTF-8", "us")
    assert m.config.keyboard == "us"
    vm.create("deutsch", "pw1234", sprache="de")
    assert (gesehen[-1].locale, gesehen[-1].keyboard) == ("de_DE.UTF-8", "de")
    vm.create("gemischt", "pw1234", sprache="en", keyboard="ch")
    assert (gesehen[-1].locale, gesehen[-1].keyboard) == ("en_US.UTF-8", "ch")
    with pytest.raises(ValueError):
        vm.create("klingonisch", "pw1234", sprache="tlh")


def test_cli_language_option():
    args = cli.build_parser().parse_args(["create", "pc", "--sprache", "en"])
    assert args.sprache == "en" and args.keyboard is None
    assert cli.build_parser().parse_args(["create", "pc", "--language", "de"]).sprache == "de"


@pytest.mark.parametrize(("sprache", "agent", "tastatur"), [("de", "de", "de"), ("en", "en", "us"),
                                                            ("fr", "en", "us")])
def test_course_package_sets_agent_pc_language(sprache, agent, tastatur):
    args = kurspaket._rezept({"apps": ["brave"]}, sprache).fuer_erstellen()
    assert (args["sprache"], args["keyboard"]) == (agent, tastatur)
    # Eine ausdrücklich gewählte Tastatur bleibt
    assert kurspaket._rezept({"keyboard": "ch"}, "en").keyboard == "ch"


# ---------------------------------------------------------------- Anlegen-Dialog
@pytest.fixture
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qtw = pytest.importorskip("PySide6.QtWidgets")
    return qtw.QApplication.instance() or qtw.QApplication([])


def _dialog(monkeypatch, captured: dict):
    from types import SimpleNamespace

    from bonys_agents import host
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
    return create_dialog.CreateDialog(host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=16384, accel="kvm"))


def test_create_dialog_language(qapp, datadir, monkeypatch):
    monkeypatch.setattr(i18n, "_aktiv", "en")
    captured: dict = {}
    dlg = _dialog(monkeypatch, captured)
    assert (dlg.sprache.currentData(), dlg.keyboard.currentData()) == ("en", "us")
    dlg.sprache.setCurrentIndex(dlg.sprache.findData("de"))
    assert dlg.keyboard.currentData() == "de"            # Vorgabe zieht mit
    dlg.keyboard.setCurrentIndex(dlg.keyboard.findData("ch"))
    dlg.sprache.setCurrentIndex(dlg.sprache.findData("en"))
    assert dlg.keyboard.currentData() == "ch"            # eigene Wahl bleibt
    dlg.name.setText("pc1")
    dlg.pw1.setText("pw1234")
    dlg.pw2.setText("pw1234")
    dlg._create()
    assert (captured["sprache"], captured["keyboard"]) == ("en", "ch")


def test_create_dialog_takes_language_from_course_recipe(qapp, datadir, monkeypatch):
    from bonys_agents import host
    from bonys_agents.gui import create_dialog

    monkeypatch.setattr(i18n, "_aktiv", "de")
    rezept = kurspaket._rezept({"apps": ["brave"]}, "en").fuer_erstellen()
    dlg = create_dialog.CreateDialog(host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=16384, accel="kvm"),
                                     recipe=rezept)
    assert (dlg.sprache.currentData(), dlg.keyboard.currentData()) == ("en", "us")
