# SPDX-License-Identifier: GPL-3.0-or-later
"""Sprache der Oberfläche: Wahl der Sprache, Katalog, ``tr()`` und der Abgleich aller ``tr()``-Texte mit en.json."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bonys_agents import i18n, storage

ROOT = Path(__file__).resolve().parent.parent


def _sammler():
    spec = importlib.util.spec_from_file_location("i18n_sammeln", ROOT / "packaging" / "i18n-sammeln.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # Dataclasses suchen ihr Modul dort
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def deutsch_danach():
    yield
    i18n.setzen(i18n.DEUTSCH)   # andere Tests prüfen deutsche Texte


# ---------------------------------------------------------------- Sprache wählen
@pytest.mark.parametrize("name, erwartet", [
    ("de_DE", "de"), ("de_AT", "de"), ("de-CH", "de"), ("DE", "de"),
    ("en_US", "en"), ("fr_FR", "en"), ("", "en"), ("C", "en"),
])
def test_system_sprache_aus_name(name, erwartet):
    assert i18n.system_sprache(name) == erwartet


@pytest.mark.parametrize("env, erwartet", [
    ({"LANG": "de_DE.UTF-8"}, "de"),
    ({"LANGUAGE": "en_GB:de", "LANG": "de_DE.UTF-8"}, "en"),   # LANGUAGE zuerst, erster Eintrag zählt
    ({"LC_ALL": "C", "LANG": "de_DE.UTF-8"}, "de"),              # „C“ wird übersprungen
    ({}, "en"),
])
def test_system_sprache_aus_umgebung(env, erwartet):
    assert i18n.system_sprache(env=env) == erwartet


def test_auto_bleibt_deutsch_solange_nicht_freigeschaltet(monkeypatch):
    monkeypatch.setattr(i18n, "FREIGESCHALTET", False)
    assert i18n.waehlen(i18n.AUTO, "en") == "de"
    assert i18n.waehlen("en", "de") == "en"   # ausdrückliche Wahl wirkt schon (zum Ausprobieren)


def test_auto_folgt_dem_system_nach_freischaltung(monkeypatch):
    monkeypatch.setattr(i18n, "FREIGESCHALTET", True)
    assert i18n.waehlen(i18n.AUTO, "en") == "en"
    assert i18n.waehlen(i18n.AUTO, "de") == "de"
    assert i18n.waehlen("de", "en") == "de"


def test_einstellung_rundweg(datadir):
    assert i18n.einstellung() == i18n.AUTO
    i18n.einstellung_setzen("en")
    assert i18n.einstellung() == "en"
    assert storage.load_settings()["sprache"] == "en"
    with pytest.raises(ValueError):
        i18n.einstellung_setzen("fr")


def test_einstellung_von_hand_veraendert(datadir):
    s = storage.load_settings()
    s["sprache"] = ["en"]
    storage.save_settings(s)
    assert i18n.einstellung() == i18n.AUTO


def test_freigeschaltet():
    assert i18n.FREIGESCHALTET   # Phase 2 fertig: „auto“ folgt der Systemsprache


def test_sprachmenue_merkt_wahl(datadir, monkeypatch):
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from bonys_agents.gui import main_window

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(main_window.MainWindow, "show_doctor", lambda self: None)
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *a, **k: None)
    w = main_window.MainWindow()
    w.timer.stop()
    menu = next(a.menu() for a in w.about_btn.menu().actions() if a.menu() and a.text() == "Sprache / Language")
    texte = [a.text() for a in menu.actions()]
    assert texte[1:] == ["Deutsch", "English"]
    assert menu.actions()[0].isChecked()   # Standard: automatisch
    menu.actions()[2].trigger()
    assert i18n.einstellung() == "en"
    assert i18n.sprache() == "de"   # gilt erst nach dem Neustart
    w.close()


def test_starten_mit_einstellung(datadir, monkeypatch):
    monkeypatch.delenv(i18n.UMGEBUNG, raising=False)
    monkeypatch.setattr(i18n, "FREIGESCHALTET", False)
    assert i18n.starten("en_US") == "de"
    i18n.einstellung_setzen("en")
    assert i18n.starten("de_DE") == "en"
    assert i18n.sprache() == "en"


def test_umgebung_hat_vorrang(datadir, monkeypatch):
    i18n.einstellung_setzen("de")
    monkeypatch.setenv(i18n.UMGEBUNG, "EN")
    assert i18n.starten("de_DE") == "en"
    monkeypatch.setenv(i18n.UMGEBUNG, "fr")   # Unbekanntes zählt nicht
    assert i18n.starten("de_DE") == "de"


def test_setzen_unbekannt_wird_deutsch():
    assert i18n.setzen("xx") == "de"


# ---------------------------------------------------------------- tr()
def test_tr_deutsch_unveraendert():
    i18n.setzen("de")
    assert i18n.tr("Unerwarteter Fehler") == "Unerwarteter Fehler"
    assert i18n.tr("Agent-PC „{name}“", name="test") == "Agent-PC „test“"


def test_tr_englisch_mit_platzhaltern():
    i18n.setzen("en")
    assert i18n.tr("Unerwarteter Fehler") == "Unexpected error"
    assert i18n.tr("{fehler}\n\nEinzelheiten: {pfad}", fehler="Kaputt", pfad="/tmp/x") == "Kaputt\n\nDetails: /tmp/x"


def test_tr_ohne_uebersetzung_bleibt_deutsch():
    i18n.setzen("en")
    assert i18n.tr("Gibt es nicht im Katalog {n}", n=3) == "Gibt es nicht im Katalog 3"


def test_leere_eintraege_zaehlen_nicht(monkeypatch, tmp_path):
    i18n.katalog.cache_clear()
    monkeypatch.setattr(i18n.resources, "files", lambda _pkg: tmp_path)
    (tmp_path / "resources" / "i18n").mkdir(parents=True)
    (tmp_path / "resources" / "i18n" / "en.json").write_text(json.dumps({"Ja": "", "Nein": "No", "x": 3}), "utf-8")
    try:
        assert i18n.katalog("en") == {"Nein": "No"}
    finally:
        i18n.katalog.cache_clear()


def test_kaputter_katalog_stuerzt_nicht(monkeypatch, tmp_path):
    i18n.katalog.cache_clear()
    monkeypatch.setattr(i18n.resources, "files", lambda _pkg: tmp_path)
    (tmp_path / "resources" / "i18n").mkdir(parents=True)
    (tmp_path / "resources" / "i18n" / "en.json").write_text("{kaputt", "utf-8")
    try:
        assert i18n.katalog("en") == {}
        assert i18n.katalog("de") == {}
    finally:
        i18n.katalog.cache_clear()


# ---------------------------------------------------------------- Sammelwerkzeug
def test_sammler_findet_tr_aufrufe(tmp_path):
    s = _sammler()
    (tmp_path / "a.py").write_text(
        'from bonys_agents.i18n import tr\nfrom bonys_agents import i18n\n'
        'x = tr("Hallo {name}", name=n)\ny = i18n.tr("Tschüss")\nz = tr(variable)\n'
        'w = andere.tr("nicht gemeint")\nv = "kein Aufruf"\n', "utf-8")
    texte, berechnet = s.sammeln(tmp_path)
    assert set(texte) == {"Hallo {name}", "Tschüss"}
    assert texte["Hallo {name}"] == [f"{tmp_path.name}/a.py:3"]
    assert berechnet == [f"{tmp_path.name}/a.py:5"]


def test_sammler_findet_markierte_texte(tmp_path):
    """n_() markiert Texte, die erst beim Anzeigen mit tr(variable) übersetzt werden (Zustände, Konstanten)."""
    s = _sammler()
    (tmp_path / "a.py").write_text('from bonys_agents.i18n import n_, tr\nLAEUFT = n_("läuft")\nx = tr(LAEUFT)\n',
                                   "utf-8")
    texte, berechnet = s.sammeln(tmp_path)
    assert set(texte) == {"läuft"}
    assert berechnet == [f"{tmp_path.name}/a.py:3"]


def test_n_aendert_nichts():
    i18n.setzen("en")
    assert i18n.n_("läuft") == "läuft"   # Werte bleiben deutsch – Vergleiche und Schlüssel ändern sich nicht
    assert i18n.tr(i18n.n_("läuft")) == "running"


def test_zahlen_und_restzeit_auf_englisch():
    from bonys_agents import desktops
    from bonys_agents import progress as pct

    assert desktops.format_ram(1536) == "1,5 GB"
    assert pct.format_eta(3 * 60) == "noch ca. 3 Min."
    i18n.setzen("en")
    assert desktops.format_ram(1536) == "1.5 GB"
    assert pct.format_eta(3 * 60) == "about 3 min left"
    assert pct.format_eta(90 * 60) == "about 1 h 30 min left"


def test_sammler_prueft_offen_verwaist_platzhalter():
    s = _sammler()
    texte = {"A {n}": ["x:1"], "B": ["x:2"], "C {pfad}": ["x:3"]}
    b = s.pruefen(texte, {"A {n}": "A {n}", "B": "", "C {pfad}": "C {path}", "alt": "old"})
    assert b.offen == ["B"]
    assert b.platzhalter == ["C {pfad}"]
    assert b.verwaist == ["alt"]
    assert not b.sauber


def test_sammler_schreibt_sortiert(tmp_path):
    s = _sammler()
    pfad = tmp_path / "en.json"
    s.katalog_schreiben({"b": "", "ä": "ae", "a": "a"}, pfad)
    assert list(json.loads(pfad.read_text("utf-8"))) == ["a", "b", "ä"]
    assert "ä" in pfad.read_text("utf-8")   # ensure_ascii=False: lesbar beim Übersetzen


def test_alle_texte_sind_uebersetzt():
    """Jeder tr()-Text im Code hat eine englische Übersetzung mit denselben Platzhaltern – und nichts ist verwaist.

    Schlägt das fehl: ``python packaging/i18n-sammeln.py`` und die leeren Einträge in en.json übersetzen."""
    s = _sammler()
    texte, berechnet = s.sammeln()
    b = s.pruefen(texte, s.katalog_laden(), berechnet)
    assert texte, "keine tr()-Texte gefunden – sucht der Sammler am richtigen Ort?"
    assert b.offen == [], "nicht übersetzt"
    assert b.platzhalter == [], "Platzhalter weichen ab"
    assert b.verwaist == [], "verwaist – packaging/i18n-sammeln.py --aufraeumen"


def test_katalog_ist_gueltiges_json_mit_texten():
    daten = json.loads((ROOT / "src" / "bonys_agents" / "resources" / "i18n" / "en.json").read_text("utf-8"))
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in daten.items())


def test_kursraum_seite_hat_englische_texte():
    """Die Seite des Kursraums (kursraum.js, index.html) holt ihre Texte aus texte.js – alle übersetzt."""
    from bonys_agents import kursraum

    texte = kursraum.seiten_texte()
    assert "✋ Hand heben" in texte and "Kursraum verlassen" in texte and "{name} ist da." in texte
    js = kursraum.texte_js("en").decode("utf-8")
    assert 'sprache = "en";' in js
    daten = json.loads(js.split("var texte = ", 1)[1].split(", sprache = ", 1)[0])
    assert set(daten) == set(texte) and daten["✋ Hand heben"] == "✋ Raise hand"
    assert 'sprache = "de";' in kursraum.texte_js("de").decode("utf-8")


def test_seiten_im_browser_sind_uebersetzt(tmp_path):
    """Seiten der Kursleiter-Version im Browser: alle Texte im Katalog, Sprache vom Browser bzw. Accept-Language."""
    from pathlib import Path

    from bonys_agents import i18n

    (tmp_path / "a.html").write_text('<title>Titel</title><h1 data-tr>Hallo</h1><button title="Knopf" data-tr-title>⛶'
                                     '</button><input placeholder="z. B. Alex" data-tr-placeholder>', "utf-8")
    (tmp_path / "a.js").write_text("tr(\"Doppelt {x}\", { x }); tr('Bony\\'s'); fehler('kein tr')", "utf-8")
    assert i18n.seiten_texte(tmp_path) == ["Doppelt {x}", "Bony's", "Hallo", "Knopf", "z. B. Alex", "Titel"]
    js = i18n.seiten_js(["Falscher Code."]).decode()
    assert '"Falscher Code.": "Wrong code."' in js and "sprache = null" in js and "navigator.language" in js
    assert i18n.sprache_aus_accept("en-US,en;q=0.9,de;q=0.8") == "en"
    assert i18n.sprache_aus_accept("de-AT,de;q=0.9") == "de" and i18n.sprache_aus_accept(None) == "de"
    assert i18n.tr_in("en", "Falscher Code.") == "Wrong code."
    assert i18n.tr_in("de", "Falscher Code.") == "Falscher Code."
    seiten = Path(i18n.__file__).parent / "trainer" / "resources" / "present"
    if seiten.is_dir():
        offen = [t for t in i18n.seiten_texte(seiten) if t not in i18n.katalog("en")]
        assert not offen, offen
