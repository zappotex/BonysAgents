# SPDX-License-Identifier: GPL-3.0-or-later
"""Musik & Radio: Adressen, Wiedergabelisten, Musikordner, Einstellungen und die Leiste (ohne echten Ton)."""

import os
from pathlib import Path

import pytest

from bonys_agents import musik, storage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------- Adressen
@pytest.mark.parametrize("url", [
    "https://hirschmilch.de:7000/chillout.mp3",
    "https://radio.example.org:8443/live",
    "  https://example.org/a.mp3  ",
])
def test_url_ok(url):
    assert musik.url_pruefen(url) == url.strip()


@pytest.mark.parametrize("url", [
    "", "http://example.org/stream", "file:///etc/passwd", "javascript:alert(1)", "https://", "ftp://example.org/x",
    "https://nutzer:geheim@example.org/stream", "https://example.org/mit leer", "https://example.org/\x00",
    "https://example.org:99999/x", "https://example.org/" + "a" * 600,
])
def test_url_abgewiesen(url):
    with pytest.raises(musik.MusikFehler):
        musik.url_pruefen(url)


# ---------------------------------------------------------------- Wiedergabelisten
def test_m3u_nur_https_ohne_doppelte(tmp_path):
    f = tmp_path / "sender.m3u"
    f.write_text("﻿#EXTM3U\n#EXTINF:-1,Mein Sender\nhttps://a.example.org/live\n"
                 "#EXTINF:-1,Unsicher\nhttp://b.example.org/live\nfile:///home/x.mp3\n/home/x.mp3\n"
                 "https://a.example.org/live\nhttps://c.example.org/stream.mp3\n", "utf-8")
    sender = musik.wiedergabeliste_lesen(f)
    assert [(s.name, s.url) for s in sender] == [("Mein Sender", "https://a.example.org/live"),
                                                  ("c.example.org", "https://c.example.org/stream.mp3")]
    assert all(s.eigen for s in sender)


def test_pls(tmp_path):
    f = tmp_path / "sender.pls"
    f.write_text("[playlist]\nFile2=https://zwei.example.org/\nTitle2=Zwei\nFile1=https://eins.example.org/\n"
                 "Title1=Eins\nFile3=http://drei.example.org/\nNumberOfEntries=3\n")
    assert [s.name for s in musik.wiedergabeliste_lesen(f)] == ["Eins", "Zwei"]


def test_wiedergabeliste_fehler(tmp_path, monkeypatch):
    ohne = tmp_path / "ohne.m3u"
    ohne.write_text("http://nur-unsicher.example.org/\n")
    with pytest.raises(musik.MusikFehler, match="keine sichere"):
        musik.wiedergabeliste_lesen(ohne)
    falsch = tmp_path / "liste.txt"
    falsch.write_text("https://example.org/\n")
    with pytest.raises(musik.MusikFehler, match="Wiedergabeliste"):
        musik.wiedergabeliste_lesen(falsch)
    monkeypatch.setattr(musik, "MAX_LISTE", 10)
    gross = tmp_path / "gross.m3u"
    gross.write_text("https://example.org/stream\n")
    with pytest.raises(musik.MusikFehler, match="zu groß"):
        musik.wiedergabeliste_lesen(gross)
    with pytest.raises(musik.MusikFehler, match="nicht lesen"):
        musik.wiedergabeliste_lesen(tmp_path / "fehlt.m3u")


# ---------------------------------------------------------------- Musikordner
def test_titel_im_ordner(tmp_path):
    m = tmp_path / "Musik"
    for rel in ("b.mp3", "a.FLAC", "Album/01.ogg", "Album/cover.jpg", ".versteckt/x.mp3", "Album/.y.mp3",
                "notiz.txt", "1/2/3/4/5/6/7/tief.mp3", "1/2/3/4/5/6/ok.mp3"):
        (m / rel).parent.mkdir(parents=True, exist_ok=True)
        (m / rel).write_bytes(b"x")
    draussen = tmp_path / "draussen"
    draussen.mkdir()
    (draussen / "fremd.mp3").write_bytes(b"x")
    (m / "verweis").symlink_to(draussen, target_is_directory=True)
    namen = [p.relative_to(m).as_posix() for p in musik.titel_im_ordner(m)]
    assert namen == ["a.FLAC", "b.mp3", "1/2/3/4/5/6/ok.mp3", "Album/01.ogg"]


def test_titel_im_ordner_grenzen(tmp_path, monkeypatch):
    for i in range(5):
        (tmp_path / f"{i}.mp3").write_bytes(b"x")
    monkeypatch.setattr(musik, "MAX_TITEL", 3)
    assert len(musik.titel_im_ordner(tmp_path)) == 3
    with pytest.raises(musik.MusikFehler):
        musik.titel_im_ordner(tmp_path / "fehlt")


# ---------------------------------------------------------------- Einstellungen
def test_einstellungen_rundweg(datadir):
    e = musik.laden()
    assert e.lautstaerke == musik.LAUTSTAERKE_STANDARD and e.quelle == "" and len(e.alle_sender()) == len(musik.SENDER)
    eigener = e.sender_hinzufuegen(musik.Sender("Mein Sender", "https://radio.example.org/live"))
    e.dateien_hinzufuegen([datadir / "a.mp3", datadir / "a.mp3", datadir / "b.exe"])
    e.lautstaerke, e.zufall, e.quelle, e.sender_url = 70, True, musik.RADIO, eigener.url
    musik.speichern(e)
    wieder = musik.laden()
    assert wieder == e
    assert wieder.dateien == [str(datadir / "a.mp3")]


def test_einstellungen_von_hand_veraendert(datadir):
    s = storage.load_settings()
    s[musik.EINSTELLUNG] = {
        "lautstaerke": 500, "zufall": "ja", "quelle": "fernsehen", "sender_url": "https://unbekannt.example.org/",
        "eigene_sender": [{"name": "Gut", "url": "https://gut.example.org/"}, {"name": "Alt", "url": "http://x/"},
                          {"name": "", "url": "https://ohne-name.example.org/"}, "kaputt",
                          {"name": "Doppelt", "url": musik.SENDER[0].url}],
        "dateien": ["/musik/a.mp3", "/bin/sh", 7], "titel": 9,
    }
    storage.save_settings(s)
    e = musik.laden()
    assert e.lautstaerke == 100 and e.zufall is False and e.quelle == "" and e.sender_url == ""
    assert [x.name for x in e.eigene_sender] == ["Gut"]
    assert e.dateien == ["/musik/a.mp3"] and e.titel == 0
    s[musik.EINSTELLUNG] = "kaputt"
    storage.save_settings(s)
    assert musik.laden() == musik.Einstellungen()


def test_sender_verwalten():
    e = musik.Einstellungen()
    with pytest.raises(musik.MusikFehler, match="gibt es schon"):
        e.sender_hinzufuegen(musik.Sender("Kopie", musik.SENDER[0].url))
    with pytest.raises(musik.MusikFehler, match="Namen"):
        e.sender_hinzufuegen(musik.Sender("  ", "https://x.example.org/"))
    with pytest.raises(musik.MusikFehler, match="nicht entfernen"):
        e.sender_entfernen(musik.SENDER[0].url)
    s = e.sender_hinzufuegen(musik.Sender("Eigen\n", "https://x.example.org/"))
    assert s.name == "Eigen"
    e.sender_url = s.url
    e.sender_entfernen(s.url)
    assert e.eigene_sender == [] and e.sender_url == ""


# ---------------------------------------------------------------- Leiste und Fenster (nachgebauter Player)
class FakePlayer:
    def __init__(self):
        from PySide6.QtCore import QUrl

        self.quelle, self.zustand, self.aufrufe = QUrl(), "gestoppt", []

    def setSource(self, url):  # noqa: N802
        self.quelle = url
        self.aufrufe.append(("quelle", url.toString()))

    def source(self):
        return self.quelle

    def play(self):
        self.zustand = "spielt"
        self.aufrufe.append(("play",))

    def pause(self):
        self.zustand = "pause"

    def stop(self):
        self.zustand = "gestoppt"


class FakeAusgabe:
    lautstaerke = None

    def setVolume(self, v):  # noqa: N802
        self.lautstaerke = v


@pytest.fixture
def leiste(datadir, monkeypatch):
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from bonys_agents.gui import musik_ui

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    erzeugt = []

    def neuer_player(self):
        erzeugt.append(self)
        return FakePlayer(), FakeAusgabe()

    monkeypatch.setattr(musik_ui.Abspieler, "_neuer_player", neuer_player)
    monkeypatch.setattr(musik_ui.QMessageBox, "warning", lambda *a: None)
    monkeypatch.setattr(musik_ui.QMessageBox, "information", lambda *a: None)

    def bauen():
        w = musik_ui.MusikLeiste()
        w.erzeugt = erzeugt
        return w
    return bauen


def test_kein_autoplay_beim_start(leiste):
    e = musik.laden()
    e.quelle, e.sender_url = musik.RADIO, musik.SENDER[1].url
    musik.speichern(e)
    w = leiste()
    a = w.abspieler
    assert a._player is None and not w.erzeugt and not a.laeuft   # Qt Multimedia nicht einmal geladen
    assert w.play_knopf.text() == "▶" and w.play_knopf.isEnabled() and w.name.toolTip() == musik.SENDER[1].name


def test_ohne_quelle_ist_abspielen_aus(leiste):
    w = leiste()
    assert not w.play_knopf.isEnabled() and w.name.text() == "Musik & Radio" and w.weiter_knopf.isHidden()
    assert w.einladung.text() == "Lerne auch mit Musik:" and w.layout().itemAt(0).widget() is w.einladung
    from bonys_agents.gui import musik_ui
    from bonys_agents.gui.style import resource

    assert musik_ui.schrift_laden() == "Pacifico"         # mitgelieferte Schrift lädt
    assert resource("fonts/Pacifico-OFL.txt").is_file()   # mit Lizenztext
    assert w.einladung.objectName() == "MusikEinladung"


def test_radio_abspielen_und_trennen(leiste):
    w = leiste()
    a = w.abspieler
    a.radio(musik.SENDER[0])
    assert a.laeuft and a._player.quelle.toString() == musik.SENDER[0].url and a._player.zustand == "spielt"
    assert w.play_knopf.text() == "⏸"
    assert a._ausgabe.lautstaerke == pytest.approx((musik.LAUTSTAERKE_STANDARD / 100) ** 2)
    w.play_knopf.click()
    assert not a.laeuft and a._player.zustand == "gestoppt"   # Radio wird getrennt, nicht nur angehalten
    assert musik.laden().sender_url == musik.SENDER[0].url


def test_radio_fehler_meldet_und_stoppt(leiste):
    w = leiste()
    gemeldet = []
    w.abspieler.fehler.connect(gemeldet.append)
    w.abspieler.radio(musik.SENDER[0])
    w.abspieler._fehler(None, "Verbindung abgelehnt")
    assert not w.abspieler.laeuft and "nicht erreichbar" in gemeldet[0] and "Verbindung abgelehnt" in gemeldet[0]


def test_eigene_musik(leiste, tmp_path, monkeypatch):
    dateien = [tmp_path / f"{i}.mp3" for i in range(3)]
    e = musik.laden()
    e.dateien_hinzufuegen(dateien)
    musik.speichern(e)
    w = leiste()
    a = w.abspieler
    a.musik(2)
    assert Path(a._player.quelle.toLocalFile()) == dateien[2] and not w.weiter_knopf.isHidden()
    a.weiter()
    assert a.e.titel == 0                                # am Ende wieder von vorn
    a.zurueck()
    assert a.e.titel == 2
    a.umschalten()
    assert a._player.zustand == "pause" and not a.laeuft
    a._player.aufrufe.clear()
    a.umschalten()                                       # an der Stelle weiter, ohne neu zu laden
    assert a.laeuft and a._player.aufrufe == [("play",)]
    a.e.zufall = True
    for _ in range(10):
        vorher = a.e.titel
        a.weiter()
        assert a.e.titel != vorher
    assert musik.laden().quelle == musik.MUSIK


def test_kaputte_dateien_werden_uebersprungen(leiste, tmp_path):
    e = musik.laden()
    e.dateien_hinzufuegen([tmp_path / "a.mp3", tmp_path / "b.mp3"])
    musik.speichern(e)
    w = leiste()
    gemeldet = []
    w.abspieler.fehler.connect(gemeldet.append)
    w.abspieler.musik(0)
    w.abspieler._fehler(None, "fehlt")
    assert w.abspieler.e.titel == 1 and w.abspieler.laeuft and not gemeldet
    w.abspieler._fehler(None, "fehlt")
    w.abspieler._fehler(None, "fehlt")                   # alle Dateien kaputt → aufhören und melden
    assert not w.abspieler.laeuft and gemeldet


def test_fenster_sender_und_musik(leiste, tmp_path, monkeypatch):
    from bonys_agents.gui import musik_ui

    w = leiste()
    d = musik_ui.MusikDialog(w.abspieler)
    assert d.sender_liste.count() == len(musik.SENDER)
    d.sender_liste.setCurrentRow(0)
    assert not d.sender_weg.isEnabled()                  # mitgelieferte Sender bleiben

    antworten = iter([("Mein Radio", True), ("https://mein.example.org/live", True)])
    monkeypatch.setattr(musik_ui.QInputDialog, "getText", lambda *a, **k: next(antworten))
    d.sender_hinzufuegen()
    assert d.sender_liste.currentItem().data(musik_ui.Qt.UserRole) == "https://mein.example.org/live"
    assert d.sender_weg.isEnabled()
    assert [s.name for s in musik.laden().eigene_sender] == ["Mein Radio"]

    liste = tmp_path / "liste.m3u"
    liste.write_text("https://mein.example.org/live\nhttps://zwei.example.org/\nhttp://unsicher.example.org/\n")
    monkeypatch.setattr(musik_ui.QFileDialog, "getOpenFileName", lambda *a, **k: (str(liste), ""))
    d.wiedergabeliste_oeffnen()
    assert [s.url for s in musik.laden().eigene_sender] == ["https://mein.example.org/live",
                                                           "https://zwei.example.org/"]
    d.sender_liste.setCurrentRow(d.sender_liste.count() - 1)
    d.sender_abspielen()
    assert w.abspieler.laeuft
    d.sender_entfernen()                                 # läuft gerade → wird gestoppt
    assert not w.abspieler.laeuft and len(musik.laden().eigene_sender) == 1

    ordner = tmp_path / "Musik"
    (ordner / "Album").mkdir(parents=True)
    for rel in ("a.mp3", "Album/b.ogg", "c.txt"):
        (ordner / rel).write_bytes(b"x")
    monkeypatch.setattr(musik_ui.QFileDialog, "getExistingDirectory", lambda *a, **k: str(ordner))
    d.ordner_hinzufuegen()
    einzeln = tmp_path / "einzeln.flac"
    monkeypatch.setattr(musik_ui.QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(einzeln)], ""))
    d.dateien_hinzufuegen()
    d.ordner_hinzufuegen()                               # noch einmal: keine Doppelten
    assert d.titel_liste.count() == 3 and musik.laden().ordner == str(ordner)
    d.titel_liste.setCurrentRow(2)
    d.musik_abspielen()
    assert Path(w.abspieler._player.quelle.toLocalFile()) == einzeln
    d.liste_leeren()
    assert not w.abspieler.laeuft and musik.laden().dateien == [] and not w.play_knopf.isEnabled()


def test_ohne_qt_multimedia_keine_leiste(monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    from bonys_agents.gui import musik_ui

    monkeypatch.setattr(musik_ui, "verfuegbar", lambda: False)
    assert musik_ui.leiste() is None
