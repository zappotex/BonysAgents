# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für die lokale Portal-Intake-Schicht."""

import json
import zipfile

from bonys_agents import kurspaket, kurspaket_portal as portal
from test_kurspaket import PAKET, paket_ordner


def test_gueltiges_paket_erzeugt_technischen_vorbericht(tmp_path):
    paket = paket_ordner(tmp_path / "quelle", {**PAKET, "lektionen": []})
    (paket / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    datei = tmp_path / "test.bonyspaket"
    kurspaket.packen(paket, datei)

    bericht = portal.pruefen(datei)

    assert bericht.status == "approved"
    assert bericht.paket_id == "test-paket"
    assert bericht.version == "1.0.0"
    assert bericht.sha256 and len(bericht.sha256) == 64
    assert bericht.skripte == []
    assert bericht.findings == []


def test_paket_mit_skript_landet_in_menschlicher_pruefung(tmp_path):
    paket = paket_ordner(tmp_path / "quelle")
    datei = tmp_path / "skript.bonyspaket"
    kurspaket.packen(paket, datei)

    bericht = portal.pruefen(datei)

    assert bericht.status == "needs_review"
    assert bericht.skripte == ["lektionen/02-uebung/pruefung/datei.sh"]
    assert any("Skript" in finding for finding in bericht.findings)


def test_geheimnis_wird_abgelehnt_und_nicht_im_bericht_ausgegeben(tmp_path):
    paket = paket_ordner(tmp_path / "quelle", {**PAKET, "lektionen": []})
    (paket / "ablaufplan.md").write_text("Token: sk-or-abcdefghijklmnop1234567890\n", encoding="utf-8")
    datei = tmp_path / "geheim.bonyspaket"
    # packen würde das Geheimnis bereits blockieren; für den Portaltest entsteht ein fremdes ZIP.
    with zipfile.ZipFile(datei, "w") as zf:
        for pfad in paket.rglob("*"):
            if pfad.is_file():
                zf.write(pfad, pfad.relative_to(paket).as_posix())

    bericht = portal.pruefen(datei)

    assert bericht.status == "rejected"
    assert any("Geheimnis" in finding for finding in bericht.findings)
    assert "sk-or-" not in json.dumps(bericht.as_dict(), ensure_ascii=False)


def test_zip_mit_pfad_ausbruch_wird_vor_dem_entpacken_abgelehnt(tmp_path):
    datei = tmp_path / "boese.bonyspaket"
    with zipfile.ZipFile(datei, "w") as zf:
        zf.writestr("paket.json", json.dumps({"format": "bonys-agents-kurspaket"}))
        zf.writestr("../ausbruch.md", "x")

    bericht = portal.pruefen(datei)

    assert bericht.status == "rejected"
    assert any("Pfad" in finding for finding in bericht.findings)
    assert not (tmp_path / "ausbruch.md").exists()


def _gepackt(tmp_path, name="p.bonyspaket", daten=None, vorher=None):
    paket = paket_ordner(tmp_path / "quelle", daten or {**PAKET, "lektionen": []})
    (paket / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    if vorher:
        vorher(paket)
    datei = tmp_path / name
    kurspaket.packen(paket, datei)
    return datei


def test_externer_link_braucht_pruefung(tmp_path):
    def link(paket):
        (paket / "handout.md").write_text("Mehr: https://example.org/seite\n", encoding="utf-8")
    bericht = portal.pruefen(_gepackt(tmp_path, vorher=link))
    assert bericht.status == "needs_review"
    assert bericht.externe_links == ["https://example.org/seite"]


def test_nicht_deklariertes_skript_wird_erkannt(tmp_path):
    def skript(paket):
        (paket / "versteckt.sh").write_text("echo hi\n", encoding="utf-8")
    bericht = portal.pruefen(_gepackt(tmp_path, vorher=skript))
    assert bericht.status == "needs_review"
    assert "versteckt.sh" in bericht.skripte


def test_fundstellen_ohne_fundwert(tmp_path):
    paket = paket_ordner(tmp_path / "quelle", {**PAKET, "lektionen": []})
    (paket / "handout.md").write_text("a\nToken: sk-or-abcdefghijklmnop1234567890\n", encoding="utf-8")
    datei = tmp_path / "g.bonyspaket"
    with zipfile.ZipFile(datei, "w") as zf:
        for pfad in paket.rglob("*"):
            if pfad.is_file():
                zf.write(pfad, pfad.relative_to(paket).as_posix())
    bericht = portal.pruefen(datei)
    assert bericht.status == "rejected"
    assert bericht.fundstellen and "handout.md, Zeile 2" in bericht.fundstellen[0]
    assert "sk-or-" not in json.dumps(bericht.as_dict())
    assert str(tmp_path) not in json.dumps(bericht.as_dict())


def test_zu_grosse_datei_wird_vor_dem_entpacken_abgelehnt(tmp_path, monkeypatch):
    datei = _gepackt(tmp_path)
    monkeypatch.setattr(portal, "MAX_EINREICHUNG", 10)
    bericht = portal.pruefen(datei)
    assert bericht.status == "rejected"
    assert any("größer" in f for f in bericht.findings)


def test_duplikat_und_gleiche_id_anderer_inhalt(tmp_path):
    datei = _gepackt(tmp_path)
    sha = portal.pruefen(datei).sha256
    dup = portal.pruefen(datei, {"test-paket": {sha}})
    assert dup.status == "needs_review" and any("Duplikat" in f for f in dup.findings)
    anders = portal.pruefen(datei, {"test-paket": {"0" * 64}})
    assert anders.status == "needs_review" and any("Paket-ID" in f for f in anders.findings)


def test_umfang_ueber_grenze_braucht_pruefung(tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "GROSS_DATEIEN", 1)
    assert portal.pruefen(_gepackt(tmp_path)).status == "needs_review"


def test_bericht_ist_reproduzierbar_und_einreichung_hat_neue_id(tmp_path):
    datei = _gepackt(tmp_path)
    assert portal.pruefen(datei) == portal.pruefen(datei)
    a, b = portal.einreichen(datei), portal.einreichen(datei)
    assert a.submission_id != b.submission_id and len(a.submission_id) == 32
    assert a.bericht == b.bericht and a.eingereicht_am


def test_fehlende_datei_und_kein_zip(tmp_path):
    assert portal.pruefen(tmp_path / "nix.bonyspaket").status == "rejected"
    kaputt = tmp_path / "k.bonyspaket"
    kaputt.write_text("kein zip", encoding="utf-8")
    assert portal.pruefen(kaputt).status == "rejected"


def test_meldung_mit_absendertext_wird_bereinigt_und_gekuerzt(tmp_path):
    datei = tmp_path / "boese.bonyspaket"
    with zipfile.ZipFile(datei, "w") as zf:
        zf.writestr("paket.json", json.dumps({"format": "bonys-agents-kurspaket"}))
        zf.writestr("../" + "a" * 500 + "\x1b[31mrot\nzeile.md", "x")

    bericht = portal.pruefen(datei)

    assert bericht.status == "rejected"
    for text in bericht.findings:
        assert len(text) <= portal.MAX_MELDUNG
        assert all(c.isprintable() for c in text)


def test_zu_viele_eintraege_und_verbotene_dateiart_werden_abgelehnt(tmp_path):
    viele = tmp_path / "viele.bonyspaket"
    with zipfile.ZipFile(viele, "w") as zf:
        zf.writestr("paket.json", "{}")
        for i in range(kurspaket.MAX_DATEIEN + 1):
            zf.writestr(f"lektionen/d{i}.md", "x")
    assert portal.pruefen(viele).status == "rejected"

    exe = tmp_path / "exe.bonyspaket"
    with zipfile.ZipFile(exe, "w") as zf:
        zf.writestr("paket.json", "{}")
        zf.writestr("lektionen/virus.exe", "MZ")
    assert portal.pruefen(exe).status == "rejected"


def test_bericht_enthaelt_keinen_arbeitspfad(tmp_path):
    bericht = portal.pruefen(_gepackt(tmp_path))
    text = json.dumps(bericht.as_dict())
    assert "bonys-kursportal-" not in text and str(tmp_path) not in text


def test_mitgelieferte_id_wird_abgelehnt_und_katalogfelder_stehen_im_bericht(tmp_path):
    datei = _gepackt(tmp_path)
    bericht = portal.pruefen(datei)
    assert bericht.stufe == "anfaenger" and bericht.beschreibung and bericht.dauer_minuten >= 0

    gesperrt = portal.pruefen(datei, reserviert={"test-paket"})
    assert gesperrt.status == "rejected"
    assert any("mitgelieferten" in f for f in gesperrt.findings)
    assert portal.pruefen(datei, reserviert={"anderes"}).status == "approved"
