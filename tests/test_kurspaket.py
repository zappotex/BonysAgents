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
    (d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").write_text("#!/bin/bash\ntest -s ~/x\n", encoding="utf-8")
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
    (d / "paket.json").write_text("{kaputt", encoding="utf-8")
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
    (src / ".herkunft.json").write_text("{}", encoding="utf-8")
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
    (basis / "nur-entwurf" / "kurs.md").write_text("# Entwurf", encoding="utf-8")
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
    (kaputt / "paket.json").write_text("[]", encoding="utf-8")
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


def _index(datei: bytes, pid="test-paket") -> bytes:
    return json.dumps({"format": kp.KATALOG_FORMAT, "pakete": [
        {"id": pid, "name": "Gemeinschaft", "version": "1.0.0", "stufe": "anfaenger",
         "datei": f"pakete/{pid}-1.0.0.bonyspaket", "sha256": hashlib.sha256(datei).hexdigest(),
         "groesse": len(datei), "community": True}]}).encode()


def test_community_katalog(datadir, tmp_path, monkeypatch):
    from bonys_agents import kurslauf

    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket").read_bytes()
    off, com = "https://example.org/off/index.json", "https://example.org/com/index.json"
    monkeypatch.setenv(kp.KATALOG_ENV, off)
    monkeypatch.setenv(kp.COMMUNITY_ENV, com)
    opener = _opener({com: _index(datei), "https://example.org/com/pakete/test-paket-1.0.0.bonyspaket": datei,
                      off: json.dumps({"format": kp.KATALOG_FORMAT, "pakete": []}).encode()})
    assert not kp.community_an()                              # Standard: aus (Datenschutz)
    assert kp.katalog_alle(opener=_opener({off: json.dumps({"format": kp.KATALOG_FORMAT, "pakete": []}).encode()})) \
        == ([], "")                                           # der Community-Server wird nicht einmal gefragt
    kp.community_setzen(True)
    assert not kp.community_an()                              # ohne Zustimmung bleibt es aus
    kp.community_zustimmung_setzen(True)
    assert kp.community_an()
    (e,), hinweis = kp.katalog_alle(opener=opener)
    assert e.community and not hinweis
    p = kp.herunterladen(e, opener=opener)
    assert p.herkunft == kp.COMMUNITY and kp.holen(e.id).herkunft == kp.COMMUNITY
    assert not p.mitgeliefert and not kurslauf.geprueft(p)
    assert "Community" in kp.HERKUNFT_TEXT[p.herkunft]
    # Die Datei selbst kann sich nicht als „nicht community“ ausgeben: Herkunft bestimmt die App
    off_eintrag = kp.katalog_laden(com, opener=opener)[0]
    assert not off_eintrag.community
    # ausgeschaltet: Community-Quelle wird nicht einmal gefragt
    kp.community_setzen(False)
    assert kp.katalog_alle(opener=_opener({off: json.dumps({"format": kp.KATALOG_FORMAT, "pakete": []}).encode()})) \
        == ([], "")
    kp.community_setzen(True)
    kp.community_zustimmung_setzen(False)                     # Zustimmung zurücknehmen schaltet auch aus
    assert not kp.community_an() and not kp.community_zugestimmt()


def test_community_fehler_blockiert_offizielle_liste_nicht(datadir, tmp_path, monkeypatch):
    kp.community_zustimmung_setzen(True)
    kp.community_setzen(True)
    datei = b"x"
    off, com = "https://example.org/off/index.json", "https://example.org/com/index.json"
    monkeypatch.setenv(kp.KATALOG_ENV, off)
    monkeypatch.setenv(kp.COMMUNITY_ENV, com)
    gleich = _index(datei, "gleich-id")
    offiziell = json.dumps({"format": kp.KATALOG_FORMAT, "pakete": json.loads(gleich)["pakete"]
                            }).replace('"community": true', '"community": false').encode()
    (e,), hinweis = kp.katalog_alle(opener=_opener({off: offiziell}))      # Community: 404
    assert not e.community and "nicht erreichbar" in hinweis
    # gleiche ID in beiden Listen: der offizielle Eintrag gewinnt
    eintraege, hinweis = kp.katalog_alle(opener=_opener({off: offiziell, com: gleich}))
    assert [x.community for x in eintraege] == [False] and not hinweis


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
    kp._fortschritt_datei().write_text('{"test-paket": {"lektion": "x", "erledigt": 5}}', encoding="utf-8")
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


# ---------------------------------------------------------------- Anzeige
def test_markdown_fuer_anzeige():
    text = ('---\ntitle: Einführung\nsubtitle: Handout\nlang: de\n---\n\n<!-- Kommentar -->\n## Teil\n\n'
            '::: tipp\nEin Tipp.\n:::\n\n::: {.feld hoehe="2cm" text="Was ist dir aufgefallen?"}\n:::\n\nEnde\n')
    out = kp.markdown_fuer_anzeige(text)
    assert out.startswith("# Einführung\n*Handout*")
    assert "Kommentar" not in out and ":::" not in out and "lang:" not in out
    assert "> **💡 Tipp:**\n> Ein Tipp." in out
    assert "**Was ist dir aufgefallen?:** ____" in out and out.rstrip().endswith("Ende")


# ---------------------------------------------------------------- Fenster
@pytest.fixture
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


def _warten(qapp, bedingung, timeout=10.0):
    import time

    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        qapp.processEvents()
        if bedingung():
            return
        time.sleep(0.01)
    raise AssertionError("Zeitüberschreitung")


def test_bibliothek_seite(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from bonys_agents.gui import kurspaket_bibliothek as kb

    basis = tmp_path / "mit"
    paket_ordner(basis, mit(id="mitgeliefert", name="Mitgeliefert", stufe="experte"), name="mitgeliefert")
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [basis])
    gestartet = []
    s = kb.BibliothekSeite(durcharbeiten=gestartet.append)
    assert s.tabelle.rowCount() == 1 and not s.loeschen_knopf.isEnabled()
    # Import per Datei (wie Drag & Drop) – erscheint in der Liste, Anfänger vor Experte
    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket")
    assert kb.ist_paket(datei) and kb.ist_paket(tmp_path / "src" / "test-paket")
    assert not kb.ist_paket(tmp_path)
    s.importieren(datei)
    _warten(qapp, lambda: s.tabelle.rowCount() == 2)
    assert s.tabelle.item(0, 0).text() == "Testpaket" and s.paket().id == "test-paket"
    assert s.loeschen_knopf.isEnabled() and s.start_knopf.text() == "Durcharbeiten"
    # gleicher Import noch einmal: Rückfrage, „Nein“ ändert nichts
    fragen = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: fragen.append(a[2]) or QMessageBox.No)
    s.importieren(datei)
    _warten(qapp, lambda: s.import_knopf.isEnabled())
    assert "schon vorhanden" in fragen[0]
    s.start_knopf.click()
    assert [p.id for p in gestartet] == ["test-paket"]
    # fehlerhafte Datei: Meldung, nichts importiert
    meldungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: meldungen.append(a[2]))
    (tmp_path / "kaputt.bonyspaket").write_bytes(b"kein zip")
    s.importieren(tmp_path / "kaputt.bonyspaket")
    _warten(qapp, lambda: bool(meldungen))
    assert "kein ZIP" in meldungen[0] and s.tabelle.rowCount() == 2
    # fremde Texte erscheinen maskiert (keine Links/Bilder aus dem Paket)
    p = kp.holen("test-paket")
    p.beschreibung = "![x](file:///etc/passwd) [klick](https://boese)"
    assert "\\!\\[x\\]" in kb._md_ganz(p) and "\\[klick\\]" in kb._md_ganz(p)
    s.deleteLater()


def test_anleitung_fenster(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import QMessageBox

    from bonys_agents import edition
    from bonys_agents.gui import kurspaket_anleitung as ka

    d = paket_ordner(tmp_path)
    (d / "lektionen" / "01-ankommen" / "bild.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "geheim.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    kp.importieren(d)
    paket = kp.holen("test-paket")
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)   # Quiz „später“
    f = ka.oeffnen(paket, gezeigt.append)
    assert ka.oeffnen(paket) is f                 # zweites Öffnen holt dasselbe Fenster
    assert f.info.text().startswith("Lektion 1 von 3") and not f.zurueck.isEnabled()
    assert f.notiz_knopf.isVisibleTo(f) == edition.IS_TRAINER
    assert not f.pc_knopf.isEnabled()             # noch kein Agent-PC
    f.weiter.click()
    assert kp.Fortschritt.laden(paket.id).lektion == 1 and kp.Fortschritt.laden(paket.id).erledigt == ["01-ankommen"]
    assert f.aufgabe.isVisibleTo(f) and "Prüfaufgabe" in f.aufgabe_text.text() and f.pruefen_knopf.isVisibleTo(f)
    f.weiter.click()
    assert f.weiter.text().startswith("Abschließen")
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[2]))
    f.weiter.click()
    assert "Geschafft" in infos[0] and kp.Fortschritt.laden(paket.id).text(paket) == "abgeschlossen"
    f.auswahl.setCurrentIndex(0)
    f.auswahl.activated.emit(0)
    assert kp.Fortschritt.laden(paket.id).lektion == 0
    # Bilder nur aus dem Kurspaket, nichts aus dem Netz
    a = f.ansicht
    assert a.loadResource(QTextDocument.ImageResource, QUrl("bild.png")) is not None
    assert a.loadResource(QTextDocument.ImageResource, QUrl.fromLocalFile(str(tmp_path / "geheim.png"))) is None
    assert a.loadResource(QTextDocument.ImageResource, QUrl("../../../geheim.png")) is None
    assert a.loadResource(QTextDocument.ImageResource, QUrl("https://example.org/x.png")) is None
    # Handout statt Lektion
    f._zusatz("handout")
    assert "Handout" in f.ansicht.toPlainText() and not f.weiter.isEnabled()
    f._gehe(1)
    assert f.weiter.isEnabled() and f.info.text().startswith("Lektion 2")
    kp.agent_pc_merken(paket, "agent-kurs")
    f.fortschritt = kp.Fortschritt.laden(paket.id)
    f._pc_status()
    assert "nicht verfügbar" in f.pc_text.text()
    f.close()
    qapp.processEvents()
    assert paket.id not in ka._FENSTER


def test_agent_pc_einrichten_vorhandener(qapp, datadir, tmp_path, monkeypatch):
    from bonys_agents.gui import kurspaket_bibliothek as kb

    paket = kp.laden(paket_ordner(tmp_path))

    class _M:
        name = "agent-kurs"

    monkeypatch.setattr(kp, "agent_pc", lambda p: _M())
    assert kb.agent_pc_einrichten(None, paket) == "agent-kurs"


def test_doku_beispiel_und_schema_gueltig(monkeypatch):
    """docs/kurspaket-format.md: das Beispiel besteht die Prüfung, Schema und Katalog sind gültiges JSON."""
    import re

    text = (Path(__file__).parent.parent / "docs" / "kurspaket-format.md").read_text(encoding="utf-8")
    bloecke = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", text, flags=re.S)
               if "…" not in b]
    beispiel = next(b for b in bloecke if b.get("format") == kp.FORMAT_ID)
    monkeypatch.setattr(kp, "__version__", kp.MIN_VERSION)
    p = kp.paket_pruefen(beispiel)
    assert p.id == "einfuehrung-hermes-agent" and len(p.lektionen) == 3
    schema = next(b for b in bloecke if b.get("$schema"))
    assert schema["properties"]["format"]["const"] == kp.FORMAT_ID
    assert set(schema["properties"]["stufe"]["enum"]) == set(kp.STUFEN)
    assert set(schema["properties"]["lektionen"]["items"]["properties"]["pruefung"]["properties"]["typ"]["enum"]) \
        == {kp.SKRIPT, *kp.EINGEBAUTE_PRUEFUNGEN}


def test_quiz_dialog(qapp):
    from bonys_agents.gui.kurspaket_anleitung import QuizDialog

    fragen = kp.quiz_pruefen({"fragen": [
        {"frage": "1?", "antworten": ["a", "b"], "richtig": 1, "erklaerung": "weil b"},
        {"frage": "2?", "antworten": ["x", "y", "z"], "richtig": 0}]})
    d = QuizDialog("Test", fragen)
    d.knopf.click()
    assert "Bitte eine Antwort" in d.rueckmeldung.text()
    d.gruppe.button(1).setChecked(True)
    d.knopf.click()
    assert d.rueckmeldung.text().startswith("Richtig!") and "weil b" in d.rueckmeldung.text()
    d.knopf.click()                                  # nächste Frage
    assert d.kopf.text() == "Frage 2 von 2"
    d.gruppe.button(2).setChecked(True)
    d.knopf.click()
    assert "Richtig ist: x" in d.rueckmeldung.text() and d.knopf.text() == "Fertig"
    d.knopf.click()
    assert d.result() == 1 and d.ergebnis == [1, 2]


def test_anleitung_pruefen_zuruecksetzen(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from bonys_agents import kurslauf
    from bonys_agents.gui import kurspaket_anleitung as ka

    paket = kp.importieren(paket_ordner(tmp_path))
    kp.agent_pc_merken(paket, "agent-kurs")

    class M:
        name = "agent-kurs"

        def status(self):
            return "läuft"

    m = M()
    monkeypatch.setattr(ka.AnleitungFenster, "maschine", lambda self: m)
    zustaende = {"01-ankommen", "02-uebung"}
    monkeypatch.setattr(kurslauf, "startzustaende", lambda maschine, p: set(zustaende))
    aufrufe = []
    monkeypatch.setattr(kurslauf, "pruefen", lambda maschine, p, lek: aufrufe.append(("pruefen", lek.ordner))
                        or kurslauf.Ergebnis(False, "Fehlt noch."))
    monkeypatch.setattr(kurslauf, "lektion_zuruecksetzen",
                        lambda maschine, p, i: aufrufe.append(("zurueck", i)))
    f = ka.AnleitungFenster(paket)
    f.show()
    f._takt()
    f._gehe(1)
    _warten(qapp, lambda: not f.beschaeftigt())
    assert f.reset_knopf.isVisibleTo(f) and "Startzustand gesichert" in f.info.text()
    f.pruefen_knopf.click()
    _warten(qapp, lambda: not f.beschaeftigt())
    assert aufrufe == [("pruefen", "02-uebung")]
    assert f.ergebnis_text.text() == "✗ Fehlt noch." and kp.Fortschritt.laden(paket.id).pruefungen == {
        "02-uebung": False}
    # Zurücksetzen nur nach Bestätigung – „Abbrechen“ ändert nichts
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    f.reset_knopf.click()
    assert aufrufe == [("pruefen", "02-uebung")]
    f._zuruecksetzen(1)
    _warten(qapp, lambda: not f.beschaeftigt())
    assert aufrufe[-1] == ("zurueck", 1)
    assert kp.Fortschritt.laden(paket.id).pruefungen == {} and f.fortschritt.lektion == 1
    f.close()


def test_skripte_erlauben(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from bonys_agents import kurslauf
    from bonys_agents.gui import kurspaket_bibliothek as kb

    paket = kp.importieren(paket_ordner(tmp_path))
    gezeigt = []

    def exec_(self):
        gezeigt.append(self.informativeText())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)     # „Abbrechen“
    assert not kb.skripte_erlauben(None, paket)
    assert "lektionen/02-uebung/pruefung/datei.sh" in gezeigt[0] and "nie auf deinem Rechner" in gezeigt[0]
    assert kurslauf.zustimmung_noetig(paket)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if b.text() == "Erlauben und starten"))
    assert kb.skripte_erlauben(None, paket) and not kurslauf.zustimmung_noetig(paket)
    assert kb.skripte_erlauben(None, paket) and len(gezeigt) == 2              # kein drittes Mal gefragt
    assert "Nicht geprüft" in kb._vertrauen_text(paket)



def test_skripte_erlauben_nennt_root_und_zeigt_skripte(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from bonys_agents.gui import kurspaket_bibliothek as kb

    paket = kp.importieren(paket_ordner(tmp_path))
    gezeigt, angesehen, klicks = [], [], iter(["Skripte ansehen …", "Abbrechen"])

    def exec_(self):
        gezeigt.append((self.textFormat(), self.informativeText()))
        self._klick = next(klicks)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if b.text() == self._klick))
    monkeypatch.setattr(QDialog, "exec", lambda self: angesehen.append(
        self.findChild(kb.QPlainTextEdit).toPlainText()) or 0)
    assert not kb.skripte_erlauben(None, paket)
    form, text = gezeigt[0]
    assert form == kb.Qt.PlainText and "als root" in text and "Internet" in text and "Anmeldungen" in text
    assert "(läuft als " in text
    assert len(gezeigt) == 2 and "datei.sh" in angesehen[0] and "läuft als" in angesehen[0]


def test_katalog_dialog_community(qapp, datadir, tmp_path, monkeypatch):
    from bonys_agents.gui import kurspaket_bibliothek as kb

    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket").read_bytes()
    off, com = "https://example.org/off/index.json", "https://example.org/com/index.json"
    monkeypatch.setenv(kp.KATALOG_ENV, off)
    monkeypatch.setenv(kp.COMMUNITY_ENV, com)
    opener = _opener({com: _index(datei), off: json.dumps({"format": kp.KATALOG_FORMAT, "pakete": []}).encode()})
    monkeypatch.setattr(kp.urllib.request, "urlopen", opener)
    kp.community_zustimmung_setzen(True)
    kp.community_setzen(True)
    d = kb.KatalogDialog()
    _warten(qapp, lambda: d.tabelle.rowCount() == 1)
    assert "Community" in d.tabelle.item(0, 0).text()
    d.tabelle.selectRow(0)
    assert "nicht von Bony's Agents" in d.text.text()
    d.community_box.setChecked(False)
    _warten(qapp, lambda: d.tabelle.rowCount() == 0 and not kp.community_an())
    d.close()


def test_katalog_dialog_community_fragt_vor_dem_ersten_einschalten(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from bonys_agents.gui import kurspaket_bibliothek as kb

    datei = zippen(paket_ordner(tmp_path / "src"), tmp_path / "p.bonyspaket").read_bytes()
    off, com = "https://example.org/off/index.json", "https://example.org/com/index.json"
    monkeypatch.setenv(kp.KATALOG_ENV, off)
    monkeypatch.setenv(kp.COMMUNITY_ENV, com)
    abgefragt: list[str] = []

    def opener(req, timeout=None):
        abgefragt.append(req.full_url)
        return _opener({com: _index(datei), off: json.dumps({"format": kp.KATALOG_FORMAT, "pakete": []}).encode()})(
            req, timeout=timeout)

    monkeypatch.setattr(kp.urllib.request, "urlopen", opener)
    gezeigt: list[str] = []
    antwort = {"ja": False}

    def exec_(self):
        gezeigt.append(self.text())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons()
                                          if b.text() == ("Einschalten" if antwort["ja"] else "Nicht einschalten")))
    d = kb.KatalogDialog()
    _warten(qapp, lambda: "Lade" not in d.text.text())
    assert not d.community_box.isChecked() and not kp.community_an()
    assert all("com/" not in u for u in abgefragt)                      # Community-Server nie angefragt
    d.community_box.setChecked(True)                                    # Nein → bleibt aus, nichts gespeichert
    assert len(gezeigt) == 1 and "IP-Adresse" in gezeigt[0] and "speichert diese" in gezeigt[0]
    assert kp.DATENSCHUTZ_URL in gezeigt[0]                  # Link auf die Datenschutzerklärung im Zustimmungsdialog
    assert kp.DATENSCHUTZ_URL in " ".join(x.text() for x in d.findChildren(kb.QLabel))   # und im Katalogfenster
    assert not d.community_box.isChecked() and not kp.community_an() and not kp.community_zugestimmt()
    assert all("com/" not in u for u in abgefragt)
    antwort["ja"] = True
    d.community_box.setChecked(True)                                    # Ja → an und gemerkt
    _warten(qapp, lambda: d.tabelle.rowCount() == 1)
    assert kp.community_an() and kp.community_zugestimmt() and len(gezeigt) == 2
    d.community_box.setChecked(False)
    d.community_box.setChecked(True)                                    # zweites Einschalten: nicht noch einmal fragen
    assert len(gezeigt) == 2
    d.close()


def test_sprachfassungen_nach_sprache():
    """Englische Fassung = deutsche ID + „-en“; gezeigt wird die passende Sprache, Pakete ohne Gegenstück immer."""
    from types import SimpleNamespace as P

    pakete = [P(id="kurs", sprache="de"), P(id="kurs-en", sprache="en"), P(id="nur-de", sprache="de"),
              P(id="only-en", sprache="en"), P(id="wien", sprache="de-AT"), P(id="wien-en", sprache="en")]
    ids = lambda liste: [p.id for p in liste]  # noqa: E731
    assert ids(kp.nach_sprache(pakete, "de")) == ["kurs", "nur-de", "only-en", "wien"]
    assert ids(kp.nach_sprache(pakete, "en")) == ["kurs-en", "nur-de", "only-en", "wien-en"]
    assert ids(kp.nach_sprache(pakete, "en", alle=True)) == ids(pakete)
    assert kp.gegenstueck("kurs") == "kurs-en" and kp.gegenstueck("kurs-en") == "kurs"
