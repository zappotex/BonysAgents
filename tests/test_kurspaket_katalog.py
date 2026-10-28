# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für den Community-Katalog."""

import io
import json

import pytest

from bonys_agents import kurspaket, kurspaket_katalog as katalog, kurspaket_moderation as mod
from test_kurspaket import PAKET, paket_ordner


def _paket(tmp_path, name, version="1.0.0", pid="test-paket"):
    paket = paket_ordner(tmp_path / f"q-{name}", {**PAKET, "lektionen": [], "id": pid, "version": version})
    (paket / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    datei = tmp_path / f"{name}.bonyspaket"
    kurspaket.packen(paket, datei)
    return datei


def _veroeffentlichen(ablage, sid):
    if ablage.status(sid) == mod.NEEDS_REVIEW:
        ablage.entscheiden(sid, mod.APPROVED, "mod", "ok")
    ablage.entscheiden(sid, mod.PUBLISHED, "mod", "frei")


def test_nur_veroeffentlichtes_kommt_in_den_katalog_im_bestehenden_format(tmp_path):
    ablage = mod.Moderation(tmp_path / "ablage")
    frei = ablage.einreichen(_paket(tmp_path, "a"), "autor-geheim")
    ablage.einreichen(_paket(tmp_path, "b", pid="anderes-paket"), "x")     # bleibt approved
    _veroeffentlichen(ablage, frei)

    ziel = tmp_path / "katalog"
    index = katalog.katalog_schreiben(ablage, ziel)

    assert [e["id"] for e in index["pakete"]] == ["test-paket"]
    eintrag = index["pakete"][0]
    assert eintrag["datei"] == "pakete/test-paket-1.0.0.bonyspaket" and eintrag["community"] is True
    assert (ziel / eintrag["datei"]).is_file()
    assert "autor-geheim" not in (ziel / "index.json").read_text()
    # die App kann den Katalog lesen
    inhalt = (ziel / "index.json").read_bytes()
    geladen = kurspaket.katalog_laden("http://127.0.0.1/index.json", opener=lambda req, timeout: io.BytesIO(inhalt))
    assert [e.id for e in geladen] == ["test-paket"] and geladen[0].sha256 == eintrag["sha256"]


def test_neueste_version_ersetzt_aeltere_und_ruecknahme_entfernt(tmp_path):
    ablage = mod.Moderation(tmp_path / "ablage")
    alt = ablage.einreichen(_paket(tmp_path, "a", "1.0.0"), "x")
    neu = ablage.einreichen(_paket(tmp_path, "b", "1.1.0"), "x")
    ziel = tmp_path / "katalog"
    for sid in (alt, neu):
        _veroeffentlichen(ablage, sid)

    index = katalog.katalog_schreiben(ablage, ziel)
    assert [e["version"] for e in index["pakete"]] == ["1.1.0"]
    assert sorted(p.name for p in (ziel / "pakete").iterdir()) == ["test-paket-1.1.0.bonyspaket"]

    ablage.entscheiden(neu, mod.WITHDRAWN, "mod", "Rücknahme")
    index = katalog.katalog_schreiben(ablage, ziel)
    assert [e["version"] for e in index["pakete"]] == ["1.0.0"]     # die ältere gilt dann wieder


def test_veraenderte_originaldatei_wird_nicht_ausgeliefert(tmp_path):
    ablage = mod.Moderation(tmp_path / "ablage")
    sid = ablage.einreichen(_paket(tmp_path, "a"), "x")
    _veroeffentlichen(ablage, sid)
    (tmp_path / "ablage" / sid / "original.bonyspaket").write_bytes(b"manipuliert")

    assert katalog.katalog_schreiben(ablage, tmp_path / "katalog")["pakete"] == []
    assert json.loads((tmp_path / "katalog" / "index.json").read_text())["pakete"] == []


def test_reservierte_id_wird_nicht_veroeffentlicht_und_nicht_ausgeliefert(tmp_path):
    # älter eingereicht, als die ID noch nicht reserviert war
    alt = mod.Moderation(tmp_path / "ablage")
    sid = alt.einreichen(_paket(tmp_path, "a"), "x")
    alt.entscheiden(sid, mod.APPROVED, "mod", "ok") if alt.status(sid) == mod.NEEDS_REVIEW else None

    ablage = mod.Moderation(tmp_path / "ablage", reserviert={"test-paket"})
    with pytest.raises(mod.ModerationsFehler, match="mitgelieferten"):
        ablage.entscheiden(sid, mod.PUBLISHED, "mod", "frei")
    assert ablage.status(sid) != mod.PUBLISHED

    # schon veröffentlicht (vor der Regel): der Katalogbau lässt sie weg
    alt.entscheiden(sid, mod.PUBLISHED, "mod", "frei")
    assert katalog.katalog_schreiben(alt, tmp_path / "k1")["pakete"][0]["id"] == "test-paket"
    assert katalog.katalog_schreiben(ablage, tmp_path / "k2")["pakete"] == []
