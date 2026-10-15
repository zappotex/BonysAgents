# SPDX-License-Identifier: GPL-3.0-or-later
"""Hintergrundbild der Agent-PCs: neues Standardbild, Randfarbe, Umstellen nur bei altem Bild (eigene bleiben)."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import cli, cloudinit, desktops, screen, wallpaper

RES = Path(wallpaper.__file__).resolve().parent / "resources"
OLD = next(iter(wallpaper.OLD_SHA256))
# Die Gast-Skripte laufen im Agent-PC (Debian: GNU sed, bash) – ausführen lassen sie sich nur auf Linux
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("bash"),
                                reason="Gast-Skript braucht GNU-Werkzeuge wie im Agent-PC")


def test_new_default_image_is_compact_and_old_one_is_gone():
    from PySide6.QtGui import QImage

    data = wallpaper.data()
    assert data[:3] == b"\xff\xd8\xff" and len(data) <= 300 * 1024          # JPEG, kompakt
    img = QImage.fromData(data)
    assert not img.isNull() and img.width() <= 3840 and abs(img.width() / img.height() - 1.5) < 0.01
    assert wallpaper.sha256() not in wallpaper.OLD_SHA256
    for f in RES.rglob("*"):   # das alte Agent-PC-Bild steckt nirgends mehr im Paket
        if f.is_file():
            assert hashlib.sha256(f.read_bytes()).hexdigest() != OLD, f


def test_border_color_comes_from_the_image():
    from PySide6.QtGui import QImage

    img = QImage.fromData(wallpaper.data())
    w, h, frame = img.width(), img.height(), 4
    px = [img.pixelColor(x, y) for x in range(w) for y in (*range(frame), *range(h - frame, h))]
    px += [img.pixelColor(x, y) for y in range(frame, h - frame) for x in (*range(frame), *range(w - frame, w))]
    avg = [sum(getattr(c, k)() for c in px) / len(px) for k in ("red", "green", "blue")]
    want = [int(desktops.WALLPAPER_BORDER[i:i + 2], 16) for i in (1, 3, 5)]
    assert all(abs(a - b) <= 2 for a, b in zip(avg, want, strict=True)), (avg, want)
    # Alle Desktops nutzen sie: gsettings, Xfce, KDE, LXQt
    assert f"primary-color='{desktops.WALLPAPER_BORDER}'" in desktops.schema_override()
    assert f"'Color','{desktops.WALLPAPER_BORDER}'" in desktops.login_script()
    assert f"BgColor={desktops.WALLPAPER_BORDER}" in desktops.LXQT.extra
    assert "picture-options='scaled'" in desktops.schema_override() and "WallpaperMode=fit" in desktops.LXQT.extra


# ---------------------------------------------------------------- Gast-Skript in einem Test-Wurzelordner
@pytest.fixture
def guest(tmp_path):
    if not sys.platform.startswith("linux") or not shutil.which("bash"):
        pytest.skip("Gast-Skript braucht GNU-Werkzeuge wie im Agent-PC (Debian)")
    root = tmp_path / "root"
    home = root / "home" / "agent"
    (root / Path(screen.WALLPAPER_JPG).parent.relative_to("/")).mkdir(parents=True)
    (root / "usr/share/glib-2.0/schemas").mkdir(parents=True)
    (root / Path(desktops.LOGIN_SCRIPT).parent.relative_to("/")).mkdir(parents=True)
    (root / desktops.LOGIN_SCRIPT.lstrip("/")).write_text("alt\n")
    (home / ".config/bonys-agents").mkdir(parents=True)
    for m in ("hintergrund-xfce", "hintergrund-kde"):
        (home / ".config/bonys-agents" / m).touch()
    lq = home / ".config/pcmanfm-qt/lxqt"
    lq.mkdir(parents=True)
    (lq / "settings.conf").write_text(f"[Desktop]\nWallpaper={screen.WALLPAPER_JPG}\nWallpaperMode=fit\n"
                                      "BgColor=#0b1117\n")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gsettings").write_text('#!/bin/sh\n[ "$1" = get ] && [ -f "$HOME/gs/$2.$3" ] && exec cat "$HOME/gs/$2.$3"'
                                    "\nexit 1\n")
    (stub / "gsettings").chmod(0o755)

    def jpg() -> Path:
        return root / screen.WALLPAPER_JPG.lstrip("/")

    def run(mode: str):
        script = wallpaper.staged_script("agent", mode) if mode != "check" else \
            "#!/bin/bash\n" + wallpaper.guest_script("agent", "check")
        env = {**os.environ, "BONYS_WP_ROOT": str(root), "PATH": f"{stub}:{os.environ['PATH']}"}
        r = subprocess.run(["bash", "-s"], input=script, capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
        return wallpaper.parse(r.stdout)

    return type("G", (), {"root": root, "home": home, "jpg": staticmethod(jpg), "run": staticmethod(run)})


def _old_image() -> bytes:
    return b"altes Standardbild"   # Prüfsumme wird im Test passend gemacht


def test_old_default_is_replaced_without_asking(guest, monkeypatch):
    guest.jpg().write_bytes(_old_image())
    monkeypatch.setattr(wallpaper, "OLD_SHA256", {hashlib.sha256(_old_image()).hexdigest(): "Test"})
    s = guest.run("check")
    assert (s.state, s.custom, s.needs_consent) == (wallpaper.OLD, [], False)
    s = guest.run("auto")
    assert s.done == "umgestellt"
    assert guest.jpg().read_bytes() == wallpaper.data()
    schema = (guest.root / screen.SCHEMA_OVERRIDE.lstrip("/")).read_text()
    assert f"primary-color='{desktops.WALLPAPER_BORDER}'" in schema
    assert "BgColor=" + desktops.WALLPAPER_BORDER in (guest.home / ".config/pcmanfm-qt/lxqt/settings.conf").read_text()
    assert (guest.root / desktops.LOGIN_SCRIPT.lstrip("/")).read_text() == desktops.login_script()
    # Xfce/KDE übernehmen es beim nächsten Anmelden
    assert not (guest.home / ".config/bonys-agents/hintergrund-xfce").exists()
    assert guest.run("auto").done == "aktuell"
    assert guest.run("check").state == wallpaper.CURRENT


def test_own_image_is_kept_unless_forced(guest, monkeypatch):
    guest.jpg().write_bytes(_old_image())
    monkeypatch.setattr(wallpaper, "OLD_SHA256", {hashlib.sha256(_old_image()).hexdigest(): "Test"})
    xf = guest.home / ".config/xfce4/xfconf/xfce-perchannel-xml"
    xf.mkdir(parents=True)
    (xf / "xfce4-desktop.xml").write_text('<property name="last-image" type="string" value="/home/agent/Bilder/'
                                          'Mein Urlaub.jpg"/>')
    (guest.home / "gs").mkdir()
    (guest.home / "gs/org.cinnamon.desktop.background.picture-uri").write_text(
        f"'file://{screen.WALLPAPER_PNG}'\n")   # unser Bild – zählt nicht als eigenes
    s = guest.run("auto")
    assert s.done == "nachfragen" and s.custom == ["xfce: /home/agent/Bilder/Mein Urlaub.jpg"]
    assert guest.jpg().read_bytes() == _old_image()                       # nichts geändert
    assert (guest.home / ".config/bonys-agents/hintergrund-xfce").exists()
    assert "Mein Urlaub" in wallpaper.describe(s)
    s = guest.run("force")
    assert s.done == "umgestellt" and guest.jpg().read_bytes() == wallpaper.data()
    assert not (guest.home / ".config/bonys-agents/hintergrund-xfce").exists()   # Xfce bekommt es wieder
    (xf / "xfce4-desktop.xml").write_text('<property name="last-image" type="string" value="/home/agent/a.png"/>')
    s = guest.run("auto")
    assert s.done == "aktuell" and "eigenes Bild gewählt – das bleibt" in wallpaper.describe(s)


def test_cinnamon_own_image_and_foreign_file_need_consent(guest):
    (guest.home / "gs").mkdir()
    (guest.home / "gs/org.cinnamon.desktop.background.picture-uri").write_text("'file:///home/agent/hund.png'\n")
    guest.jpg().write_bytes(b"irgendein anderes Bild")
    s = guest.run("check")
    assert s.state == wallpaper.FOREIGN and s.custom == ["cinnamon: /home/agent/hund.png"]
    assert guest.run("auto").done == "nachfragen"
    lq = (guest.home / ".config/pcmanfm-qt/lxqt/settings.conf").read_text()
    assert "#0b1117" in lq


def test_missing_image_is_installed(guest):
    assert guest.run("check").state == wallpaper.MISSING
    assert guest.run("auto").done == "umgestellt" and guest.jpg().read_bytes() == wallpaper.data()


# ---------------------------------------------------------------- Einbindung
@linux_only
def test_new_agent_pcs_and_clones_get_new_image():
    ud = cloudinit.user_data(cloudinit.GuestConfig(hostname="pc", username="agent", password="pw", apps=[]))
    assert cloudinit.wallpaper_b64() in ud and screen.WALLPAPER_JPG in ud
    clone = cloudinit.clone_user_data("klon", "agent", "pw")
    assert cloudinit.CLONE_WALLPAPER_SCRIPT in clone and wallpaper.STAGED in clone
    assert cloudinit.wallpaper_b64() in clone
    script = cloudinit.clone_firstboot_script()
    assert f"{cloudinit.CLONE_WALLPAPER_SCRIPT} >/dev/null" in script
    subprocess.run(["sh", "-n"], input=script, text=True, check=True)
    subprocess.run(["bash", "-n"], input="#!/bin/bash\n" + wallpaper.guest_script("agent", "auto"), text=True,
                   check=True)


def test_cli_wallpaper_command():
    a = cli.build_parser().parse_args(["wallpaper", "pc", "--force"])
    assert (a.name, a.force, a.check, a.func) == ("pc", True, False, cli.cmd_wallpaper)


def test_update_needs_running_agent_pc():
    from types import SimpleNamespace

    m = SimpleNamespace(name="pc", is_running=lambda: False)
    with pytest.raises(RuntimeError, match="muss laufen"):
        wallpaper.update(m)


def test_live_update_goes_via_stdin(monkeypatch):
    """Das Bild steckt im Skript (> 128 KB) – es muss über die Standardeingabe in den Gast, nicht als Argument."""
    from types import SimpleNamespace

    seen = {}

    def guest_run(script, **kw):
        seen.update(kw, size=len(script))
        return f"{wallpaper.MARK} STATE=alt\n{wallpaper.MARK} DONE=umgestellt\n"
    m = SimpleNamespace(name="pc", is_running=lambda: True, progress=lambda: SimpleNamespace(ready=True),
                        config=SimpleNamespace(first_boot_pending=False, username="agent"), guest_run=guest_run)
    s = wallpaper.update(m)
    assert s.done == "umgestellt" and seen["via_stdin"] is True and seen["size"] > 128 * 1024
