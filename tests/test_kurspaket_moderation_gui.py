# SPDX-License-Identifier: GPL-3.0-or-later
"""Moderationsdialog offscreen: Anzeige, Knopfzustände, Entscheidung."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from bonys_agents import kurspaket, kurspaket_moderation as mod  # noqa: E402
from bonys_agents.gui.moderation_dialog import ModerationDialog  # noqa: E402
from test_kurspaket import PAKET, paket_ordner  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path):
    app = APP
    paket = paket_ordner(tmp_path / "q", {**PAKET, "lektionen": []})
    datei = tmp_path / "p.bonyspaket"
    kurspaket.packen(paket, datei)   # mit Skript -> needs_review
    ablage = mod.Moderation(tmp_path / "ablage")
    ablage.einreichen(datei, "autor-1")
    d = ModerationDialog(ablage)
    d.resize(800, 550)
    yield d
    d.close()
    app.processEvents()


def test_zeigt_einreichung_mit_bericht_und_passenden_knoepfen(dialog):
    assert dialog.tabelle.rowCount() == 1
    assert dialog.knoepfe[mod.APPROVED].isEnabled() is False   # noch nichts gewählt
    dialog.tabelle.selectRow(0)
    text = dialog.details.toPlainText()
    assert "test-paket" in text and "Skript" in text
    assert dialog.knoepfe[mod.APPROVED].isEnabled()
    assert dialog.knoepfe[mod.REJECTED].isEnabled()
    assert not dialog.knoepfe[mod.PUBLISHED].isEnabled()


def test_entscheidung_braucht_akteur_und_wird_protokolliert(dialog, monkeypatch):
    warnungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnungen.append(a[2]))
    dialog.tabelle.selectRow(0)

    assert dialog.entscheiden(mod.APPROVED, "ok") is False and warnungen
    dialog.akteur.setText("mod-1")
    assert dialog.entscheiden(mod.APPROVED, "Skript geprüft.") is True

    assert dialog.knoepfe[mod.PUBLISHED].isEnabled()
    assert "mod-1" in dialog.details.toPlainText()
    assert dialog.ablage.status(dialog.aktuelle_id()) == mod.APPROVED


def test_knopf_klick_entscheidet(dialog, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a: ("Skript geprüft.", True))
    dialog.akteur.setText("mod-1")
    dialog.tabelle.selectRow(0)
    dialog.knoepfe[mod.APPROVED].click()
    assert dialog.ablage.status(dialog.aktuelle_id()) == mod.APPROVED


def test_datei_pruefen_nimmt_paket_lokal_auf_und_sperrt_mitgelieferte_ids(tmp_path, datadir):
    from bonys_agents.gui.moderation_dialog import lokale_ablage

    app = APP
    ablage = lokale_ablage()
    assert ablage.wurzel.parent == kurspaket.storage.data_dir() and ablage.reserviert    # mitgelieferte IDs
    d = ModerationDialog(ablage)
    try:
        paket = paket_ordner(tmp_path / "q", {**PAKET, "lektionen": [], "id": "eigenes-paket"})
        datei = tmp_path / "e.bonyspaket"
        kurspaket.packen(paket, datei)
        assert d.einreichen(datei) and d.tabelle.rowCount() == 1
        gesperrt = paket_ordner(tmp_path / "r", {**PAKET, "lektionen": [], "id": sorted(ablage.reserviert)[0]})
        datei2 = tmp_path / "g.bonyspaket"
        kurspaket.packen(gesperrt, datei2)
        assert d.einreichen(datei2)
        assert sorted(ablage.status(i) for i in ablage.ids()) == [mod.NEEDS_REVIEW, mod.REJECTED]
        zeile = next(r for r in range(2) if d.tabelle.item(r, 3).text() == "Abgelehnt")
        d.tabelle.selectRow(zeile)
        assert "mitgelieferten" in d.details.toPlainText()
    finally:
        d.close()
        app.processEvents()
