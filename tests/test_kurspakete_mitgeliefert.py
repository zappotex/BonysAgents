# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitgelieferte Kurspakete (``kurspakete/``): gültig, ohne Zugangsdaten, Prüfskripte tun, was sie sollen, und das
Pack-Skript der Release-Aktion (``packaging/kurspakete.py``) liefert signierte Pakete samt ``index.json``."""

import base64
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import kurslauf, kurspaket, signing

ROOT = Path(__file__).resolve().parent.parent
QUELLE = ROOT / "kurspakete"
HERMES = QUELLE / "einfuehrung-hermes-agent"


def _ordner() -> list[Path]:
    return sorted(p for p in QUELLE.iterdir() if (p / kurspaket.PAKET_JSON).is_file())


def test_alle_gueltig_und_ohne_geheimnisse():
    ids = []
    for o in _ordner():
        p = kurspaket.laden(o)
        ids.append(p.id)
        assert p.id == o.name
        assert kurspaket.geheimnisse_suchen(o) == [], o.name
        assert p.lizenz == "CC-BY-SA-4.0" and not p.rezept.unbekannte_apps()
        for lek in p.lektionen:
            lek.quiz()
            assert lek.anleitung().strip()
    assert "einfuehrung-hermes-agent" in ids and len(ids) == 6
    assert sum(not kurspaket.laden(o).entwurf for o in _ordner()) == 1   # Hermes fertig, fünf Entwürfe
    assert {kurspaket.laden(o).stufe for o in _ordner()} == {"anfaenger", "fortgeschritten", "experte"}


def test_werden_als_mitgeliefert_gefunden():
    assert QUELLE in kurspaket.mitgeliefert_dirs()


def test_hermes_paket():
    p = kurspaket.laden(HERMES)
    assert p.dauer_minuten == 120 and p.pause_minuten == 10 and len(p.lektionen) == 9
    # Zeitplan des Kurses: Lektionen 1–8 + Pause = 120 Minuten, Lektion 9 ist der Zusatz
    assert sum(lek.dauer_minuten for lek in p.lektionen[:8]) + p.pause_minuten == 120
    assert [lek.pruefung.typ for lek in p.lektionen if lek.pruefung] == ["skript", "skript", "vorlage-vorhanden"]
    assert len(p.lernziele) == 6 and "kostenlos" in p.kosten
    text = (HERMES / "ablaufplan.md").read_text() + (HERMES / "handout.md").read_text()
    assert "Nous" in text and "hermes --tui" in text and "/tools" in text and "64K" in text
    assert "<!--" not in text   # Bony's Agents zeigt kein HTML


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Prüfskripte sind für Linux im Agent-PC")
def test_hermes_pruefskripte_in_einem_test_home(tmp_path):
    """Die Skripte laufen sonst nur im Agent-PC – hier nur zum Test in einem leeren Ordner als HOME."""
    lek = HERMES / "lektionen"
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}

    def rc(*befehl) -> int:
        return subprocess.run(list(befehl), env=env, cwd=tmp_path, capture_output=True, timeout=30).returncode

    hermes = lek / "03-hermes-startklar" / "pruefung" / "hermes-eingerichtet.py"
    assert rc(sys.executable, "-I", str(hermes)) == 1
    (home / ".hermes" / ".env").write_text("OPENROUTER_API_KEY=x\n")      # Schlüssel allein genügt nicht
    assert rc(sys.executable, "-I", str(hermes)) == 1
    (home / ".hermes" / "config.yaml").write_text("model:\n  provider: nous\n  default: hermes-free\n")
    assert rc(sys.executable, "-I", str(hermes)) == 0
    assert ".env" not in [z for z in hermes.read_text().splitlines() if not z.lstrip().startswith("#")][0]

    if shutil.which("bash") is None:
        pytest.skip("ohne bash")
    liste = lek / "04-uebung-dateien" / "pruefung"
    start = lek / "04-uebung-dateien" / "start" / "kurs-ordner.sh"
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 1
    assert rc("bash", str(start)) == 0 and (home / "Kurs").is_dir()
    (home / "Kurs" / "einkaufsliste.txt").write_text("Brot\nMilch\n")
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 1
    assert rc("bash", str(liste / "loesung.sh")) == 0
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 0


@pytest.mark.kursleiter
def test_statische_pruefung_wie_im_editor():
    from bonys_agents.trainer import kurspaket_editor as editor

    for o in _ordner():
        meldungen = editor.pruefen_statisch(o)
        assert not [m for m in meldungen if m.stufe in (editor.FEHLER, editor.WARNUNG)], (o.name, meldungen)


def _skript():
    spec = importlib.util.spec_from_file_location("kurspakete_packen", ROOT / "packaging" / "kurspakete.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_pack_skript_der_release_aktion(tmp_path):
    secret, key_id = bytes(range(32)), b"\x01\x02\x03\x04\x05\x06\x07\x08"
    public = base64.b64encode(b"Ed" + key_id + signing.ed25519_public_key(secret)).decode()
    m = _skript()
    bau = tmp_path / "bau"
    ordner = m.vorbereiten(bau)
    assert len(ordner) == 6
    # ohne Signatur bricht es ab
    with pytest.raises(SystemExit, match="Signatur"):
        m.packen(bau, tmp_path / "out", public)
    for o in ordner:
        daten = (o / kurslauf.PRUEFSUMMEN).read_bytes()
        (o / kurslauf.SIGNATUR).write_text(signing.sign(daten, secret, key_id, "Kurspaket von Bony's Agents v0"))
    index = m.packen(bau, tmp_path / "out", public)
    katalog = json.loads(index.read_text())
    assert katalog["format"] == kurspaket.KATALOG_FORMAT and len(katalog["pakete"]) == 6
    hermes = next(e for e in katalog["pakete"] if e["id"] == "einfuehrung-hermes-agent")
    assert hermes["datei"] == "pakete/einfuehrung-hermes-agent-1.0.0.bonyspaket" and "entwurf" not in hermes
    datei = tmp_path / "out" / "einfuehrung-hermes-agent-1.0.0.bonyspaket"
    assert hermes["groesse"] == datei.stat().st_size

    # Die App liest die index.json wie aus dem Repo – und die Signatur übersteht den Import
    class Antwort(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    eintraege = kurspaket.katalog_laden("https://example.org/index.json",
                                        opener=lambda req, timeout: Antwort(index.read_bytes()))
    assert {e.id for e in eintraege} == {o.name for o in ordner}
    assert next(e for e in eintraege if e.id == "hermes-ueber-telegram").entwurf
    ziel = tmp_path / "entpackt"
    kurspaket.entpacken(datei, ziel)
    assert kurslauf.signatur_pruefen(kurspaket.laden(ziel), public)


def test_handbuch_baut_den_beispielkurs_aus_dem_paket():
    skript = (ROOT / "docs" / "handbuch" / "erstellen.sh").read_text()
    assert "kurspakete/einfuehrung-hermes-agent" in skript
    assert not (ROOT / "docs" / "handbuch" / "beispielkurs.md").exists()   # nur eine Quelle
