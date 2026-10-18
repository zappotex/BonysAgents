# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspakete (.bonyspaket): Format-Prüfung, Entpack-Schutz, Bibliothek, Katalog aus dem Internet, Fortschritt."""

import copy
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from bonys_agents import kurspaket as kp

PAKET = {
    "format": kp.FORMAT_ID,
    "format_version": 1,
    "min_version": "0.1.0",
    "id": "test-paket",
    "name": "Testpaket",
    "beschreibung": "Ein Kurspaket für die Tests.",
    "stufe": "anfaenger",
    "version": "1.0.0",
    "teilnehmer": {"min": 5, "max": 10},
    "lernziele": ["etwas lernen"],
    "rezept": {"name": "agent-kurs", "desktop": "cinnamon", "apps": ["brave", "hermes"], "disk_gb": 64},
    "lektionen": [
        {"ordner": "01-ankommen", "titel": "Ankommen", "dauer_minuten": 10},
        {"ordner": "02-uebung", "titel": "Übung", "dauer_minuten": 20,
         "pruefung": {"skript": "pruefung/datei.sh", "geschafft": "Gut!", "noch_nicht": "Fehlt noch."}},
        {"ordner": "03-vorlage", "titel": "Vorlage", "dauer_minuten": 5, "pruefung": {"typ": "vorlage-vorhanden"}},
    ],
}
QUIZ = {"fragen": [{"frage": "Was ist ein Agent?", "antworten": ["Ein Chatbot", "Er handelt selbst"],
                    "richtig": 1}]}


def paket_ordner(basis: Path, daten: dict | None = None, name: str = "test-paket") -> Path:
    d = basis / name
    (d / "lektionen" / "01-ankommen").mkdir(parents=True)
    (d / "lektionen" / "02-uebung" / "pruefung").mkdir(parents=True)
    (d / "lektionen" / "03-vorlage").mkdir(parents=True)
    (d / "paket.json").write_text(json.dumps(daten or PAKET, ensure_ascii=False), encoding="utf-8")
    (d / "ablaufplan.md").write_text("# Ablaufplan\n\nBlock 1 …\n", encoding="utf-8")
    (d / "handout.md").write_text("# Handout\n", encoding="utf-8")
    for o in ("01-ankommen", "02-uebung", "03-vorlage"):
        (d / "lektionen" / o / "anleitung.md").write_text(f"# {o}\n\n1. Schritt\n", encoding="utf-8")
    (d / "lektionen" / "01-ankommen" / "quiz.json").write_text(json.dumps(QUIZ), encoding="utf-8")
    (d / "lektionen" / "01-ankommen" / "kursleitung.md").write_text("Nur für die Kursleitung", encoding="utf-8")
    (d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").write_text("#!/bin/bash\ntest -s ~/x\n")
    return d


def mit(**aenderungen) -> dict:
    d = copy.deepcopy(PAKET)
    d.update(aenderungen)
    return d


def zippen(ordner: Path, ziel: Path, praefix: str = "") -> Path:
    with zipfile.ZipFile(ziel, "w") as zf:
        for p in sorted(ordner.rglob("*")):
            if p.is_file():
                zf.write(p, praefix + p.relative_to(ordner).as_posix())
    return ziel


@pytest.fixture(autouse=True)
def _keine_mitgelieferten(monkeypatch):
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [])


# ---------------------------------------------------------------- Format
def test_laden_gueltig(tmp_path):
    p = kp.laden(paket_ordner(tmp_path))
    assert p.id == "test-paket" and p.stufe_text == "Anfänger" and p.version == "1.0.0"
    assert p.dauer_minuten == 35 and p.dauer_text == "35 min"
    assert p.teilnehmer_text == "5–10 Personen"
    assert p.rezept.name == "agent-kurs" and p.rezept.fuer_erstellen()["app_ids"] == ["brave", "hermes"]
    assert p.lektionen[0].quiz()[0].richtig == 1
    assert p.lektionen[0].kursleitung() == "Nur für die Kursleitung"
    assert p.lektionen[1].pruefung.zeitlimit == kp.PRUEF_ZEIT_STANDARD
    assert p.lektionen[2].pruefung.typ == "vorlage-vorhanden" and not p.lektionen[2].pruefung.skript
    assert [s[2] for s in p.skripte()] == ["lektionen/02-uebung/pruefung/datei.sh"]
    assert "Ablaufplan" in p.ablaufplan() and p.handout().startswith("# Handout")


def test_lektionen_sind_optional(tmp_path):
    d = paket_ordner(tmp_path, mit(lektionen=[], dauer_minuten=120))
    p = kp.laden(d)
    assert p.lektionen == [] and p.dauer_text == "2 h"


@pytest.mark.parametrize("aenderung, meldung", [
    ({"format": "etwas"}, "Kein Kurspaket"),
    ({"stufe": "profi"}, "„stufe“ muss"),
    ({"id": "Mit Leerzeichen"}, "„id“"),
    ({"version": "eins"}, "„version“"),
    ({"name": ""}, "„name“ darf nicht leer"),
    ({"name": 5}, "„name“ muss ein Text"),
    ({"name": "a\nb"}, "einzeilig"),
    ({"min_version": "99.0.0"}, "braucht Bony's Agents 99.0.0"),
    ({"format_version": 2}, "neuer"),
    ({"teilnehmer": {"min": 10, "max": 5}}, "„min“ ist größer"),
    ({"rezept": {"desktop": "windows"}}, "unbekannter Desktop"),
    ({"rezept": {"apps": ["Brave Browser"]}}, "App-Kennungen"),
    ({"rezept": {"disk_gb": 5}}, "„disk_gb“ muss zwischen"),
    ({"quellen": [{"titel": "x", "url": "http://example.org"}]}, "nur https"),
    ({"lektionen": [{"ordner": "ankommen", "titel": "A"}]}, "„ordner“"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A"}, {"ordner": "01-a", "titel": "B"}]}, "doppelt"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"skript": "../../boese.sh"}}]}, "innerhalb"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"skript": "/etc/x.sh"}}]}, "innerhalb"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"skript": "p.exe"}}]}, "enden"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"typ": "zaubern"}}]}, "unbekannter „typ“"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"skript": "p.sh", "zeitlimit": 9999}}]},
     "„zeitlimit“"),
    ({"lektionen": [{"ordner": "01-a", "titel": "A", "pruefung": {"skript": "p.sh", "als": "admin"}}]}, "„als“"),
])
def test_ungueltige_paket_json(aenderung, meldung):
    with pytest.raises(kp.PaketFehler, match=meldung):
        kp.paket_pruefen(mit(**aenderung))


def test_fehlende_dateien(tmp_path):
    d = paket_ordner(tmp_path)
    (d / "ablaufplan.md").unlink()
    with pytest.raises(kp.PaketFehler, match="Ablaufplan"):
        kp.laden(d)
    d = paket_ordner(tmp_path / "b")
    (d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    with pytest.raises(kp.PaketFehler, match="Prüfskript"):
        kp.laden(d)
    d = paket_ordner(tmp_path / "c")
    (d / "lektionen" / "01-ankommen" / "anleitung.md").unlink()
    with pytest.raises(kp.PaketFehler, match="anleitung.md fehlt"):
        kp.laden(d)
    d = paket_ordner(tmp_path / "d")
    (d / "paket.json").write_text("{kaputt")
    with pytest.raises(kp.PaketFehler, match="kein gültiges JSON"):
        kp.laden(d)


def test_quiz_pruefen():
    with pytest.raises(kp.PaketFehler, match="2 bis 6"):
        kp.quiz_pruefen({"fragen": [{"frage": "?", "antworten": ["nur eine"], "richtig": 0}]})
    with pytest.raises(kp.PaketFehler, match="„richtig“"):
        kp.quiz_pruefen({"fragen": [{"frage": "?", "antworten": ["a", "b"], "richtig": 2}]})
    with pytest.raises(kp.PaketFehler, match="fragen"):
        kp.quiz_pruefen([])


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="keine Links")
def test_pruefskript_als_link_abgelehnt(tmp_path):
    d = paket_ordner(tmp_path)
    s = d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh"
    s.unlink()
    try:
        s.symlink_to("/etc/hostname")
    except OSError:
        pytest.skip("Links nicht erlaubt (Windows ohne Entwicklermodus)")
    with pytest.raises(kp.PaketFehler, match="Prüfskript"):
        kp.laden(d)


# ---------------------------------------------------------------- Entpack-Schutz
def _zip(tmp_path: Path, eintraege: list[tuple[str, bytes]], name="x.bonyspaket", modus: dict | None = None) -> Path:
    ziel = tmp_path / name
    with zipfile.ZipFile(ziel, "w") as zf:
        for n, inhalt in eintraege:
            info = zipfile.ZipInfo(n)
            if modus and n in modus:
                info.external_attr = modus[n] << 16
            zf.writestr(info, inhalt)
    return ziel


def _gueltig() -> list[tuple[str, bytes]]:
    d = mit(lektionen=[])
    return [("paket.json", json.dumps(d).encode()), ("ablaufplan.md", b"# Plan\n")]


def test_entpacken_mit_ordner_oben(tmp_path):
    src = paket_ordner(tmp_path / "src")
    datei = zippen(src, tmp_path / "p.bonyspaket", praefix="test-paket/")
    kp.entpacken(datei, tmp_path / "ziel")
    assert kp.laden(tmp_path / "ziel").id == "test-paket"
    skript = tmp_path / "ziel" / "lektionen" / "02-uebung" / "pruefung" / "datei.sh"
    assert not skript.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.mark.parametrize("name", ["../boese.md", "a/../../boese.md", "/etc/boese.md", "C:/boese.md",
                                  "a\\..\\boese.md"])
def test_pfad_ausbruch(tmp_path, name):
    datei = _zip(tmp_path, _gueltig() + [(name, b"x")])
    with pytest.raises(kp.PaketFehler, match="Pfad"):
        kp.entpacken(datei, tmp_path / "ziel")
    assert not (tmp_path / "boese.md").exists()


def test_link_im_zip(tmp_path):
    datei = _zip(tmp_path, _gueltig() + [("link.md", b"/etc/passwd")], modus={"link.md": stat.S_IFLNK | 0o777})
    with pytest.raises(kp.PaketFehler, match="Verweis"):
        kp.entpacken(datei, tmp_path / "ziel")


def test_unerlaubte_dateiart(tmp_path):
    datei = _zip(tmp_path, _gueltig() + [("programm.exe", b"MZ")])
    with pytest.raises(kp.PaketFehler, match="Dateiart"):
        kp.entpacken(datei, tmp_path / "ziel")


def test_ohne_paket_json(tmp_path):
    datei = _zip(tmp_path, [("ablaufplan.md", b"x")])
    with pytest.raises(kp.PaketFehler, match="paket.json fehlt"):
        kp.entpacken(datei, tmp_path / "ziel")
    (tmp_path / "kein.zip").write_bytes(b"kein zip")
    with pytest.raises(kp.PaketFehler, match="kein ZIP"):
        kp.entpacken(tmp_path / "kein.zip", tmp_path / "ziel2")


def test_groessengrenze(tmp_path, monkeypatch):
    monkeypatch.setattr(kp, "MAX_DATEI", 1000)
    datei = _zip(tmp_path, _gueltig() + [("gross.txt", b"x" * 2000)])
    with pytest.raises(kp.PaketFehler, match="zu groß"):
        kp.entpacken(datei, tmp_path / "ziel")
    monkeypatch.setattr(kp, "MAX_DATEI", 10_000)
    monkeypatch.setattr(kp, "MAX_GESAMT", 3000)
    datei = _zip(tmp_path, _gueltig() + [(f"t{i}.txt", b"x" * 900) for i in range(5)], name="y.bonyspaket")
    with pytest.raises(kp.PaketFehler, match="zu groß"):
        kp.entpacken(datei, tmp_path / "ziel")


def test_zip_bombe_mit_falscher_groesse(tmp_path, monkeypatch):
    """Gelogene Größen im ZIP-Verzeichnis: Es zählen die wirklich entpackten Bytes."""
    monkeypatch.setattr(kp, "MAX_DATEI", 5000)
    datei = tmp_path / "bombe.bonyspaket"
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, inhalt in _gueltig():
            zf.writestr(n, inhalt)
        zf.writestr("bombe.txt", b"0" * 100_000)
    roh = bytearray(datei.read_bytes())
    # Größe im zentralen Verzeichnis auf 10 Bytes „lügen“
    i = roh.rfind(b"PK\x01\x02")
    while i >= 0:
        laenge = int.from_bytes(roh[i + 28:i + 30], "little")
        if roh[i + 46:i + 46 + laenge] == b"bombe.txt":
            roh[i + 24:i + 28] = (10).to_bytes(4, "little")
        i = roh.rfind(b"PK\x01\x02", 0, i)
    datei.write_bytes(bytes(roh))
    with pytest.raises(kp.PaketFehler):
        kp.entpacken(datei, tmp_path / "ziel")


def test_zu_viele_dateien(tmp_path, monkeypatch):
    monkeypatch.setattr(kp, "MAX_DATEIEN", 3)
    datei = _zip(tmp_path, _gueltig() + [(f"t{i}.txt", b"x") for i in range(3)])
    with pytest.raises(kp.PaketFehler, match="zu viele"):
        kp.entpacken(datei, tmp_path / "ziel")


def test_beiwerk_wird_uebersprungen(tmp_path):
    datei = _zip(tmp_path, _gueltig() + [("__MACOSX/._paket.json", b"x"), (".git/config", b"x")])
    kp.entpacken(datei, tmp_path / "ziel")
    assert not (tmp_path / "ziel" / "__MACOSX").exists() and not (tmp_path / "ziel" / ".git").exists()


def test_packen_und_wieder_laden(tmp_path):
    src = paket_ordner(tmp_path / "src")
    (src / ".herkunft.json").write_text("{}")
    datei = kp.packen(src, tmp_path / kp.dateiname(kp.laden(src)))
    assert datei.name == "test-paket-1.0.0.bonyspaket"
    with zipfile.ZipFile(datei) as zf:
        assert ".herkunft.json" not in zf.namelist()
    kp.entpacken(datei, tmp_path / "ziel")
    assert kp.laden(tmp_path / "ziel").name == "Testpaket"


# ---------------------------------------------------------------- Bibliothek
def test_import_liste_loeschen(datadir, tmp_path):
    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket")
    p = kp.importieren(datei)
    assert p.herkunft == kp.DATEI and [k.id for k in kp.liste()] == ["test-paket"]
    with pytest.raises(kp.PaketExistiert, match="schon vorhanden"):
        kp.importieren(datei)
    f = kp.Fortschritt.laden("test-paket")
    f.lektion = 1
    f.speichern()
    # neuere Version: aktualisieren, Fortschritt bleibt
    neu = paket_ordner(tmp_path / "neu", mit(version="1.1.0"))
    with pytest.raises(kp.PaketExistiert, match="neuer") as e:
        kp.importieren(neu)
    assert e.value.alt.version == "1.0.0" and e.value.neu.version == "1.1.0"
    assert kp.importieren(neu, ersetzen=True).version == "1.1.0"
    assert kp.holen("test-paket").version == "1.1.0"
    assert kp.Fortschritt.laden("test-paket").lektion == 1
    with pytest.raises(kp.PaketExistiert, match="ÄLTER"):
        kp.importieren(datei)
    kp.loeschen("test-paket")
    assert kp.liste() == [] and not kp.Fortschritt.laden("test-paket").begonnen
    assert not [p for p in kp.bibliothek_dir().iterdir() if p.name.startswith(".")]


def test_fehlerhafter_import_hinterlaesst_nichts(datadir, tmp_path):
    datei = _zip(tmp_path, [("paket.json", b"{}"), ("ablaufplan.md", b"x")])
    with pytest.raises(kp.PaketFehler):
        kp.importieren(datei)
    assert [p.name for p in kp.bibliothek_dir().iterdir()] == []


def test_mitgelieferte(datadir, tmp_path, monkeypatch):
    basis = tmp_path / "mit"
    paket_ordner(basis)
    (basis / "nur-entwurf").mkdir()
    (basis / "nur-entwurf" / "kurs.md").write_text("# Entwurf")
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [basis])
    (p,) = kp.liste()
    assert p.mitgeliefert
    with pytest.raises(kp.PaketFehler, match="Mitgelieferte"):
        kp.loeschen(p.id)
    # importierte Fassung verdeckt die mitgelieferte
    kp.importieren(paket_ordner(tmp_path / "eigen", mit(version="2.0.0")), ersetzen=True)
    assert kp.holen("test-paket").version == "2.0.0" and not kp.holen("test-paket").mitgeliefert


def test_kaputtes_paket_in_der_bibliothek(datadir):
    kaputt = kp.bibliothek_dir() / "kaputt"
    kaputt.mkdir(parents=True)
    (kaputt / "paket.json").write_text("[]")
    b = kp.bestand()
    assert b.pakete == [] and b.fehler[0][0] == "kaputt"


# ---------------------------------------------------------------- Katalog
class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _opener(dateien: dict[str, bytes]):
    def opener(req, timeout=None):
        if req.full_url not in dateien:
            raise OSError("404")
        return _Antwort(dateien[req.full_url])
    return opener


def test_katalog_und_download(datadir, tmp_path):
    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket").read_bytes()
    index = {"format": kp.KATALOG_FORMAT, "pakete": [
        {"id": "test-paket", "name": "Testpaket", "version": "1.0.0", "stufe": "anfaenger",
         "datei": "pakete/test-paket-1.0.0.bonyspaket", "sha256": hashlib.sha256(datei).hexdigest(),
         "groesse": len(datei)},
        {"id": "kaputt", "name": "X", "version": "1", "stufe": "profi", "datei": "x", "sha256": "0" * 64,
         "groesse": 1},
        {"id": "unsicher", "name": "X", "version": "1", "stufe": "experte", "datei": "http://example.org/x",
         "sha256": "0" * 64, "groesse": 1},
    ]}
    url = "https://example.org/kurspakete/index.json"
    opener = _opener({url: json.dumps(index).encode(),
                      "https://example.org/kurspakete/pakete/test-paket-1.0.0.bonyspaket": datei})
    (e,) = kp.katalog_laden(url, opener=opener)
    assert e.url.endswith("pakete/test-paket-1.0.0.bonyspaket")
    p = kp.herunterladen(e, opener=opener)
    assert p.herkunft == kp.INTERNET and kp.holen("test-paket").herkunft == kp.INTERNET
    # falsche Prüfsumme
    e.sha256 = "1" * 64
    with pytest.raises(kp.PaketFehler, match="Prüfsumme"):
        kp.herunterladen(e, ersetzen=True, opener=opener)
    # größer als angekündigt
    e.sha256, e.groesse = hashlib.sha256(datei).hexdigest(), 100
    with pytest.raises(kp.PaketFehler, match="größer"):
        kp.herunterladen(e, ersetzen=True, opener=opener)
    assert not [x for x in kp.bibliothek_dir().iterdir() if x.name.startswith(".")]


def test_katalog_nur_https():
    with pytest.raises(kp.PaketFehler, match="https"):
        kp.katalog_laden("http://example.org/index.json", opener=_opener({}))
    with pytest.raises(kp.PaketFehler, match="ließ sich nicht laden"):
        kp.katalog_laden("https://example.org/index.json", opener=_opener({}))


# ---------------------------------------------------------------- Fortschritt und Agent-PC
def test_fortschritt(datadir, tmp_path):
    p = kp.laden(paket_ordner(tmp_path))
    f = kp.Fortschritt.laden(p.id)
    assert f.text(p) == "nicht begonnen"
    f.gehe_zu(p, 99)
    assert f.lektion == 2
    for lek in p.lektionen[:2]:
        f.erledigen(lek)
    f.erledigen(p.lektionen[0])
    f.speichern()
    f = kp.Fortschritt.laden(p.id)
    assert f.text(p) == "2 von 3 Lektionen" and round(f.anteil(p), 2) == 0.67
    f.erledigen(p.lektionen[2])
    assert f.text(p) == "abgeschlossen"
    # kaputte Datei → leerer Fortschritt statt Absturz
    kp._fortschritt_datei().write_text('{"test-paket": {"lektion": "x", "erledigt": 5}}')
    assert kp.Fortschritt.laden(p.id).lektion == 0


def test_agent_pc_vorschlag(datadir, tmp_path, monkeypatch):
    from bonys_agents import vm

    p = kp.laden(paket_ordner(tmp_path))

    class _M:
        def __init__(self, name):
            self.name = name

    monkeypatch.setattr(vm, "list_all", lambda: [_M("agent-kurs")])
    assert kp.agent_pc_vorschlag(p) == "agent-kurs-2"
    p.rezept.name = ""
    assert kp.agent_pc_vorschlag(p) == "kurs-test-paket"
    assert kp.agent_pc(p) is None
    kp.agent_pc_merken(p, "gibt-es-nicht")
    assert kp.agent_pc(p) is None


def test_kein_skript_wird_lokal_ausgefuehrt(datadir, tmp_path, monkeypatch):
    """Laden, Entpacken, Importieren und Packen dürfen nie einen Prozess starten."""
    import os
    import subprocess

    def verboten(*a, **k):
        raise AssertionError("Prozess gestartet")

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, verboten)
    monkeypatch.setattr(os, "system", verboten)
    src = paket_ordner(tmp_path / "src")
    datei = kp.packen(src, tmp_path / "p.bonyspaket")
    kp.importieren(datei)
    kp.bestand()
