# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop-Auswahl: Einrichtungsskript je Desktop, Terminal für Verknüpfungen, --desktop, RAM-Warnung."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import apps, cli, cloudinit, desktops, screen, vm
from bonys_agents import progress as pct

needs_bash = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="braucht bash")


def _script(desktop: str, app_ids=("brave", "telegram", "xrdp", "hermes")) -> str:
    guest = cloudinit.GuestConfig(hostname="t", username="agent", password="pw", apps=apps.resolve(list(app_ids)),
                                  desktop=desktop)
    return cloudinit.provision_script(guest)


def _steps(script: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"<<'(BONYS_STEP_\d+)'(.*?)\n\1", script, re.S)}


@pytest.mark.parametrize("desktop", list(desktops.DESKTOPS))
def test_every_desktop_gets_a_complete_setup_step(desktop):
    d = desktops.DESKTOPS[desktop]
    script = _script(desktop)
    step = _steps(script)["BONYS_STEP_2"]
    assert f"BONYS-STEP 2/6 {d.name}-Desktop mit automatischer Anmeldung" in script
    # Pakete: gemeinsame plus die des Desktops
    dm = desktops.DM_PACKAGES[d.display_manager]
    assert f"apt-get install -y {desktops.COMMON_PACKAGES} {dm} {d.packages}" in step
    for pkg in ("spice-vdagent", "qemu-guest-agent", "x11-xserver-utils", "pipewire-pulse"):
        assert pkg in step
    # Anmeldung: automatisch in die X11-Sitzung des Desktops – LightDM, bei GNOME GDM ohne Wayland
    if desktop == "gnome":
        assert "WaylandEnable=false" in step and "AutomaticLogin=$AGENT_USER" in step
        assert "DefaultSession=gnome-xorg.desktop" in step and "XSession=gnome-xorg" in step
        assert "echo /usr/sbin/gdm3 > /etc/X11/default-display-manager" in step and "lightdm" not in dm
    else:
        assert f"autologin-session={d.xsession}" in step and "autologin-user=$AGENT_USER" in step
        assert "echo /usr/sbin/lightdm > /etc/X11/default-display-manager" in step
        assert 'for dm in gdm3 gdm sddm; do systemctl disable' in step
    assert f"test -f /usr/share/xsessions/{d.xsession}.desktop" in step
    # Ausschaltknopf, Hintergrund, Auflösung, Terminal, Anmelde-Skript
    assert "HandlePowerKey=poweroff" in step and "PowerKeyIgnoreInhibited=yes" in step
    assert "picture-options='scaled'" in step and desktops.WALLPAPER_BORDER in step
    assert screen.LIGHTDM_DROPIN in step and screen.UDEV_RULE in step
    assert f"cat > {desktops.TERMINAL_SCRIPT}" in step and f"TERMINAL={d.terminal}" in step
    assert desktops.LOGIN_AUTOSTART in step
    assert f"SESSION_CMD={d.session_cmd}" in step  # für xrdp


def test_desktop_specific_settings():
    xfce = _steps(_script("xfce"))["BONYS_STEP_2"]
    assert "xfce4-desktop.xml" in xfce and '<property name="image-style" type="int" value="4"/>' in xfce
    kde = _steps(_script("kde"))["BONYS_STEP_2"]
    assert "sddm-" in kde and "kwin-x11" in kde and "PowerButtonAction=8" in kde and "plasmax11" in kde
    gnome = _steps(_script("gnome"))["BONYS_STEP_2"]
    assert "gnome-session-xsession" in gnome and 'for dm in lightdm sddm; do systemctl disable' in gnome
    lxqt = _steps(_script("lxqt"))["BONYS_STEP_2"]
    assert "WallpaperMode=fit" in lxqt and "window_manager=" in lxqt
    override = desktops.schema_override()
    for section in ("org.cinnamon.desktop.background", "org.gnome.desktop.background", "org.mate.background",
                    "org.mate.power-manager", "org.cinnamon.settings-daemon.plugins.power"):
        assert f"[{section}]" in override
    # GNOME: keine Ausschaltknopf-Einstellung („nothing“ würde das Herunterfahren in VMs verhindern)
    assert "power-button-action" not in override
    login = desktops.login_script()
    assert "plasma-org" not in login and "org.kde.PlasmaShell.evaluateScript" in login  # KDE: per Skript
    assert "xfconf-query" in login and "favorite-apps" in login


@needs_bash
@pytest.mark.parametrize("desktop", list(desktops.DESKTOPS))
def test_setup_steps_are_valid_bash(desktop):
    for name, body in _steps(_script(desktop)).items():
        r = subprocess.run(["bash", "-n"], input=body, text=True, capture_output=True)
        assert r.returncode == 0, (desktop, name, r.stderr)
    for s in (desktops.login_script(), desktops._TERMINAL,
              cloudinit.desktop_install_script(desktops.KDE, "agent", make_default=False)):
        subprocess.run(["bash", "-n"], input=s, text=True, check=True)


def test_shortcuts_use_desktop_terminal_and_dash():
    for app_id in ("hermes", "openclaw", "claude-code"):
        install = apps.APPS[app_id].install
        assert "gnome-terminal" not in install and "/usr/local/bin/bonys-terminal" in install
        assert apps.APPS[app_id].launcher
    script = _script("gnome", ("brave", "telegram", "hermes", "claude-code"))
    for launcher in ("brave-browser.desktop", "org.telegram.desktop.desktop", "hermes-agent.desktop",
                     "claude-code.desktop"):
        assert f"echo '{launcher}' >> {desktops.FAVORITES}" in script
    # nachträglich installierte Programme bringen den Terminal-Starter selbst mit (ältere Agent-PCs)
    later = cloudinit.app_install_script(apps.APPS["openclaw"], "agent")
    assert f"cat > {desktops.TERMINAL_SCRIPT}" in later and "openclaw.desktop" in later


@needs_bash
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Gast-Skript (Linux)")
@pytest.mark.parametrize("terminal,expect", [
    ("xfce4-terminal", "--title=Hermes Agent -x"), ("konsole", "-p tabtitle=Hermes Agent -e"),
    ("gnome-terminal", "--title=Hermes Agent --"), ("mate-terminal", "--title=Hermes Agent -x"),
    ("qterminal", "-e"),
])
def test_terminal_wrapper_starts_desktop_terminal(tmp_path, terminal, expect):
    env = tmp_path / "desktop.env"
    env.write_text(f"TERMINAL={terminal}\n")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for t in ("gnome-terminal", "konsole", "xfce4-terminal", "mate-terminal", "qterminal"):
        # Stub: Aufruf merken und das übergebene Skript (letztes Argument) ausführen
        (stubs / t).write_text(f'#!/bin/bash\necho "{t} $*" > {tmp_path}/aufruf\n"${{@: -1}}"\n')
        (stubs / t).chmod(0o755)
    wrapper = tmp_path / "bonys-terminal"
    wrapper.write_text(desktops._TERMINAL.replace(desktops.DESKTOP_ENV, str(env)))
    wrapper.chmod(0o755)
    out = tmp_path / "lief"
    subprocess.run([str(wrapper), "Hermes Agent", "bash", "-c", f"echo 'mit Leerzeichen' > {out}"],
                   env={**os.environ, "PATH": f"{stubs}:/usr/bin:/bin"}, check=True)
    call = (tmp_path / "aufruf").read_text()
    assert call.startswith(f"{terminal} {expect}")
    assert out.read_text() == "mit Leerzeichen\n"  # Anführungszeichen überleben


def test_ram_warning():
    assert desktops.ram_warning("xfce", 2048) == ""
    assert "4 GB" in desktops.ram_warning("kde", 3072) and "3 GB" in desktops.ram_warning("kde", 3072)
    assert "1,5 GB" in desktops.ram_warning("lxqt", 1024)
    with pytest.raises(ValueError):
        desktops.ram_warning("windows", 4096)


def test_progress_weight_follows_desktop():
    ids = ["brave", "telegram", "hermes"]
    kde = pct.step_ranges(ids, "kde")
    xfce = pct.step_ranges(ids, "xfce")
    # KDE lädt rund 900 MB, Xfce gut 100 MB – der Desktop-Schritt nimmt entsprechend mehr vom Balken ein
    assert (kde[1][1] - kde[1][0]) > (xfce[1][1] - xfce[1][0]) + 20
    assert pct.step_ranges(ids) == pct.step_ranges(ids, "cinnamon")
    assert pct.step_ranges(ids, "unbekannt") == pct.step_ranges(ids)  # neuere Version → wie Cinnamon


def test_cli_desktop_option(datadir, monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_create(name, password, **kw):
        seen.update(kw)
        raise RuntimeError("Abbruch nach dem Prüfen")

    monkeypatch.setattr(vm, "create", fake_create)
    monkeypatch.setattr(cli, "_ensure_ready", lambda yes: True)
    monkeypatch.setattr(cli.host, "detect", lambda: vm.host.HostInfo("linux", "x86_64", 4, 16384, "kvm"))
    rc = cli.main(["create", "neu", "--desktop", "kde", "--password", "pw1234", "--ram", "3072", "--no-start"])
    assert rc == 1 and seen["desktop"] == "kde"
    assert "KDE Plasma braucht mindestens" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["create", "neu", "--desktop", "windows"])
    assert cli.main(["create", "neu", "--template", "x", "--desktop", "xfce"]) == 2


def test_desktop_saved_in_vm_json_and_templates(datadir, monkeypatch, tmp_path):
    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    m = vm.create("plasma", "pw1234", desktop="kde")
    assert json.loads((m.path / "vm.json").read_text())["desktop"] == "kde"
    assert vm.get("plasma").config.desktop == "kde"
    with pytest.raises(ValueError):
        vm.create("falsch", "pw1234", desktop="windows")
    # ältere vm.json ohne Desktop → Cinnamon
    data = json.loads((m.path / "vm.json").read_text())
    del data["desktop"]
    (m.path / "vm.json").write_text(json.dumps(data))
    assert vm.get("plasma").config.desktop == "cinnamon"
    from bonys_agents import templates
    t = templates.Template(path=tmp_path, name="x", desktop="xfce", extra_desktops=["lxqt"])
    assert t.to_json()["desktop"] == "xfce" and "Xfce" in templates.describe(t)


def test_install_desktop_later(datadir, monkeypatch):
    p = vm.vms_dir() / "laeuft"
    p.mkdir(parents=True)
    (p / "vm.json").write_text(json.dumps(vm.VMConfig(name="laeuft", arch="x86_64", cpus=1, ram_mb=4096,
                                                      provisioned=True).__dict__))
    m = vm.VM(p)
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    sent = {}
    monkeypatch.setattr(vm.VM, "_ssh", lambda self, cmd, script, pw=None, log=None: sent.update(s=script) or 0)
    m.install_desktop("xfce", make_default=False, password="pw")
    assert m.config.desktop == "cinnamon" and m.config.extra_desktops == ["xfce"]
    assert "autologin-session" not in sent["s"] and "xfce4-terminal" in sent["s"]
    m.install_desktop("xfce", make_default=True, password="pw")  # schon da → nur Standard umstellen
    assert m.config.desktop == "xfce" and m.config.extra_desktops == ["cinnamon"]
    assert "autologin-session=xfce" in sent["s"]
    with pytest.raises(ValueError):
        m.install_desktop("xfce", password="pw")
