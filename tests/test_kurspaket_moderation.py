# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für Moderationsmodell und Verlaufshistorie."""

import pytest

from bonys_agents import kurspaket
from bonys_agents import kurspaket_moderation as mod
from test_kurspaket import PAKET, paket_ordner


def _datei(tmp_path, mit_skript=False, name="p.bonyspaket"):
    paket = paket_ordner(tmp_path / ("q-" + name), {**PAKET, "lektionen": []})
    if not mit_skript:
        (paket / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    datei = tmp_path / name
    kurspaket.packen(paket, datei)
    return datei


def test_sauberes_paket_wird_approved_aber_nicht_veroeffentlicht(tmp_path):
    m = mod.Moderation(tmp_path / "ablage")
    sid = m.einreichen(_datei(tmp_path), "autor-1")

    assert m.status(sid) == mod.APPROVED
    assert [e.nach for e in m.verlauf(sid)] == [mod.UPLOADED, mod.SCANNING, mod.APPROVED]
    assert (tmp_path / "ablage" / sid / "original.bonyspaket").is_file()
    assert m.bericht(sid)["paket_id"] == "test-paket"
    m.verlauf_pruefen(sid)


def test_skriptpaket_braucht_mensch_und_begruendung(tmp_path):
    m = mod.Moderation(tmp_path / "ablage")
    sid = m.einreichen(_datei(tmp_path, mit_skript=True), "autor-1")
    assert m.status(sid) == mod.NEEDS_REVIEW

    with pytest.raises(mod.ModerationsFehler):
        m.entscheiden(sid, mod.APPROVED, "mod-1", " ")
    with pytest.raises(mod.ModerationsFehler):
        m.entscheiden(sid, mod.APPROVED, mod.AKTEUR_SYSTEM, "ok")
    with pytest.raises(mod.ModerationsFehler):
        m.entscheiden(sid, mod.PUBLISHED, "mod-1", "direkt")

    m.entscheiden(sid, mod.APPROVED, "mod-1", "Skript geprüft.")
    m.entscheiden(sid, mod.PUBLISHED, "mod-1", "Freigegeben.")
    m.entscheiden(sid, mod.WITHDRAWN, "mod-1", "Rücknahme.")
    assert [e.nach for e in m.verlauf(sid)][-3:] == [mod.APPROVED, mod.PUBLISHED, mod.WITHDRAWN]
    m.verlauf_pruefen(sid)


def test_abgelehnt_und_zurueckgezogen_sind_endzustaende(tmp_path):
    m = mod.Moderation(tmp_path / "ablage")
    sid = m.einreichen(tmp_path / "fehlt.bonyspaket", "autor-1")
    assert m.status(sid) == mod.REJECTED
    with pytest.raises(mod.ModerationsFehler):
        m.entscheiden(sid, mod.APPROVED, "mod-1", "doch")


def test_verlauf_manipulation_wird_erkannt(tmp_path):
    m = mod.Moderation(tmp_path / "ablage")
    sid = m.einreichen(_datei(tmp_path), "autor-1")
    verlauf = tmp_path / "ablage" / sid / "verlauf.jsonl"
    verlauf.write_text(verlauf.read_text().replace("autor-1", "anderer"), encoding="utf-8")

    with pytest.raises(mod.ModerationsFehler):
        m.verlauf_pruefen(sid)
    with pytest.raises(mod.ModerationsFehler):
        m.entscheiden(sid, mod.PUBLISHED, "mod-1", "ok")


def test_duplikat_wird_erkannt_und_ids_sind_geschuetzt(tmp_path):
    m = mod.Moderation(tmp_path / "ablage")
    datei = _datei(tmp_path)
    m.einreichen(datei, "a")
    zweite = m.einreichen(datei, "b")
    assert m.status(zweite) == mod.NEEDS_REVIEW
    assert len(m.ids()) == 2

    for schlecht in ("../x", "abc", ""):
        with pytest.raises(mod.ModerationsFehler):
            m.status(schlecht)
    with pytest.raises(mod.ModerationsFehler):
        m.einreichen(datei, "  ")


def test_gleichzeitige_entscheidungen_halten_die_kette_gueltig(tmp_path):
    import threading

    from test_kurspaket_katalog import _paket

    ablage = mod.Moderation(tmp_path / "ablage")
    sid = ablage.einreichen(_paket(tmp_path, "a"), "autor")
    if ablage.status(sid) == mod.NEEDS_REVIEW:
        ablage.entscheiden(sid, mod.APPROVED, "mod", "ok")
    ergebnisse = []

    def lauf(nach, name):
        try:
            ablage.entscheiden(sid, nach, name, "gleichzeitig")
            ergebnisse.append(nach)
        except mod.ModerationsFehler:
            ergebnisse.append("fehler")

    threads = [threading.Thread(target=lauf, args=(nach, f"m{i}"))
               for i, nach in enumerate([mod.PUBLISHED, mod.REJECTED] * 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ablage.verlauf_pruefen(sid)                       # Kette unversehrt
    assert len([e for e in ergebnisse if e != "fehler"]) == 1      # genau eine Entscheidung gewinnt
    assert ablage.status(sid) in (mod.PUBLISHED, mod.REJECTED)
