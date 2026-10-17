"""Tests ohne Server: Konto, Gerätenamen, Erstbeitritts-Skript.

Start: python -m pytest -q
"""

import os
import stat
import subprocess
import sys

import pytest

from bony_netz import STANDARD_SERVER, Konto, Zentrale, ZentraleFehler, erstbeitritt_skript, geraetename
from bony_netz.zentrale import kurscode_formatieren


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BONY_NETZ_ORDNER", str(tmp_path / "bn"))


def test_konto_leer_und_speichern():
    k = Konto.laden()
    assert k.server == STANDARD_SERVER and not k.angemeldet
    k.uebernehmen({"instanz_id": "i1", "token": "bz_x", "login_server": "https://vpn.x"})
    k.extra["letzter_kurs"] = "k1"
    k.speichern()
    neu = Konto.laden()
    assert neu.angemeldet and neu.token == "bz_x" and neu.extra == {"letzter_kurs": "k1"}
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(Konto.pfad()).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(Konto.pfad().parent).st_mode) == 0o700


def test_konto_kaputte_datei():
    Konto.pfad().parent.mkdir(parents=True)
    Konto.pfad().write_text("{kaputt")
    assert not Konto.laden().angemeldet


def test_serverwechsel_meldet_ab():
    k = Konto()
    k.uebernehmen({"instanz_id": "i1", "token": "t"})
    k.server_wechseln(STANDARD_SERVER + "/")
    assert k.angemeldet                      # gleicher Server: bleibt angemeldet
    k.server_wechseln("zentrale.example.de")
    assert k.server == "https://zentrale.example.de" and not k.angemeldet


def test_geraetename():
    assert geraetename("Agent PC 1 (Büro)") == "agent-pc-1-buero"
    assert geraetename("   ") == "agent-pc"
    assert geraetename("Größe---Test!!") == "groesse-test"
    assert len(geraetename("x" * 100)) == 63


def test_kurscode_formatieren():
    assert kurscode_formatieren("k7qx m3pa") == "K7QX-M3PA"
    assert kurscode_formatieren("K7QX-M3PA") == "K7QX-M3PA"


def test_ohne_anmeldung():
    with pytest.raises(ZentraleFehler) as e:
        Zentrale("https://zentrale.example.de").geraete()
    assert e.value.anmeldung_ungueltig


@pytest.mark.skipif(sys.platform.startswith("win"), reason="nur POSIX (bash unter Windows ist der WSL-Platzhalter)")
def test_skript_ist_gueltiges_bash_und_sicher_maskiert():
    skript = erstbeitritt_skript("https://vpn.bony23.de", "hskey-auth-abc'; rm -rf /", "Agent PC 1")
    assert "--hostname" in skript and "agent-pc-1" in skript
    assert "'hskey-auth-abc'\"'\"'; rm -rf /'" in skript       # sauber in Anführungszeichen
    ergebnis = subprocess.run(["bash", "-n"], input=skript, text=True, capture_output=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    with pytest.raises(ValueError):
        erstbeitritt_skript("http://vpn.unsicher", "k", "n")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="nur POSIX")
def test_skript_shellcheck():
    try:
        ergebnis = subprocess.run(["shellcheck", "-S", "warning", "-"], text=True, capture_output=True,
                                  input=erstbeitritt_skript("https://vpn.x", "k", "n"))
    except FileNotFoundError:
        pytest.skip("shellcheck nicht installiert")
    assert ergebnis.returncode == 0, ergebnis.stdout



@pytest.mark.skipif(sys.platform.startswith("win"), reason="nur POSIX")
def test_skript_installiert_und_behaelt_den_geraetenamen(tmp_path):
    """Frischer Agenten-PC ohne Tailscale: /etc/os-release (setzt u. a. NAME="Debian GNU/Linux") darf den
    Gerätenamen nicht überschreiben. Läuft mit falschen Programmen statt apt, curl und tailscale."""
    import shutil

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for werkzeug in ("date", "seq", "sleep", "grep", "rm", "chmod", "cp"):
        (bin_dir / werkzeug).symlink_to(shutil.which(werkzeug))
    aufrufe = tmp_path / "aufrufe"
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="Debian GNU/Linux"\nID=debian\nVERSION_CODENAME=trixie\n')
    (tmp_path / "tailscale").write_text('#!/bin/bash\n[ "$1" = status ] && exit 1\necho "tailscale $*" >> "$AUFRUFE"\n')
    falsch = {
        "getent": "exit 0",
        "curl": 'echo "curl $*" >> "$AUFRUFE"',
        "install": "exit 0",
        "systemctl": "exit 0",
        "apt-get": f'if [[ "$*" == install*tailscale ]]; then cp {tmp_path}/tailscale {bin_dir}/tailscale; '
                   f'chmod +x {bin_dir}/tailscale; fi',
    }
    for name, rumpf in falsch.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{rumpf}\n")
        (bin_dir / name).chmod(0o755)
    skript = (erstbeitritt_skript("https://vpn.bony23.de", "hskey-auth-test", "Agent PC 7")
              .replace("/var/log/bony-netz-beitritt.log", str(tmp_path / "log"))
              .replace("/etc/os-release", str(os_release)))
    datei = tmp_path / "beitritt.sh"
    datei.write_text(skript)
    umgebung = {**os.environ, "PATH": str(bin_dir), "AUFRUFE": str(aufrufe)}
    ergebnis = subprocess.run([shutil.which("bash"), str(datei)], env=umgebung, capture_output=True, text=True)
    assert ergebnis.returncode == 0, (tmp_path / "log").read_text()
    zeilen = aufrufe.read_text().splitlines()
    assert zeilen[0].startswith("curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg")
    up = next(z for z in zeilen if z.startswith("tailscale up"))
    assert "--hostname agent-pc-7 " in up and "Debian" not in up
    assert not datei.exists()   # Skript mit Schlüssel entfernt
