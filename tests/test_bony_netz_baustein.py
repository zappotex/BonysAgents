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
