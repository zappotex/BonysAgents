# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurse über das Bony-Netz (Aufgabe 04): bonys_agents.kurse und die Fenster „Kurse“ / Kursleitung – gegen die
Test-Zentrale aus test_netz.py auf 127.0.0.1, nie gegen den echten Server."""

import os
import time

import pytest
from test_netz import FakeZentrale

from bony_netz import Konto, NetzFehler, ZentraleFehler
from bonys_agents import edition, kurse, netz


@pytest.fixture
def zentrale():
    z = FakeZentrale()
    yield z
    z.close()


def _anmelden(z: FakeZentrale) -> Konto:
    netz.server_wechseln(z.url)
    konto = netz.instanz_anlegen(z.url)
    netz.aktiv_setzen(True)
    return konto


def _als(konto: Konto) -> None:
    """Diesen Rechner als eine andere Instanz ausgeben (wie ein zweiter Rechner)."""
    def setzen(k: Konto) -> None:
        k.instanz_id, k.token = konto.instanz_id, konto.token
    netz.aendern(setzen)


def _zweite_instanz(z: FakeZentrale) -> Konto:
    from bony_netz import Zentrale

    k = Konto(server=z.url)
    k.uebernehmen(Zentrale(z.url).instanz_registrieren())
    return k


def _geraet(gid, name, online=True, ip="100.64.0.7"):
    return {"geraet_id": gid, "name": name, "ip": ip, "online": online, "zuletzt_gesehen": 1760000000}


@pytest.fixture
def leiter(zentrale):
    konto = _anmelden(zentrale)
    kurse.kursleiter_freischalten("LEITER-OK")
    return konto


# ---------------------------------------------------------------- Logik
def test_ohne_bony_netz_kein_kontakt(zentrale):
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    zentrale.anfragen.clear()
    for fn in (kurse.teilnahmen, kurse.geleitete_kurse, kurse.eigene_geraete, kurse.ist_kursleiter):
        with pytest.raises(RuntimeError, match="ausgeschaltet"):
            fn()
    assert zentrale.anfragen == []


def test_kursleiter_code(zentrale):
    _anmelden(zentrale)
    assert not kurse.ist_kursleiter()
    with pytest.raises(ValueError):
        kurse.kursleiter_freischalten("  ")
    with pytest.raises(ZentraleFehler) as e:
        kurse.kursleiter_freischalten("falsch")
    assert e.value.meldung == "Der Kursleiter-Code ist ungültig." and not Konto.laden().ist_kursleiter
    kurse.kursleiter_freischalten(" LEITER-OK ")
    assert Konto.laden().ist_kursleiter and kurse.ist_kursleiter()


def test_kein_kursleiter_bekommt_die_meldung_der_zentrale(zentrale):
    _anmelden(zentrale)
    with pytest.raises(ZentraleFehler) as e:
        kurse.kurs_anlegen("Hermes", "Bony")
    assert e.value.status == 403 and "Kursleiter" in e.value.meldung


def test_kurs_anlegen_und_steuern(leiter, zentrale):
    with pytest.raises(ValueError, match="1 bis 60"):
        kurse.kurs_anlegen("Hermes", "Bony", 61)
    with pytest.raises(ValueError, match="Kursnamen"):
        kurse.kurs_anlegen("  ", "Bony")
    k = kurse.kurs_anlegen("  Einführung   Hermes ", "Bony", 7)
    assert (k.name, k.kursleiter_name, k.status, k.status_text) == ("Einführung Hermes", "Bony", "offen", "offen")
    assert k.code == "K001-M3PA" and abs(k.code_gueltig_bis - time.time() - 7 * 86400) < 60
    assert kurse.gemerkt(kurse.KURSLEITER_NAME) == "Bony"
    assert Konto.laden().extra[kurse.KURSLEITER_NAME] == "Bony"

    assert kurse.status_setzen(k.kurs_id, kurse.LAEUFT).laeuft
    assert kurse.status_setzen(k.kurs_id, kurse.PAUSIERT).status_text == "pausiert"
    assert [x.kurs_id for x in kurse.geleitete_kurse()] == [k.kurs_id]
    assert kurse.status_setzen(k.kurs_id, kurse.BEENDET).beendet
    assert kurse.geleitete_kurse() == []
    assert [x.status for x in kurse.geleitete_kurse(auch_beendete=True)] == ["beendet"]
    with pytest.raises(ZentraleFehler, match="schon beendet"):
        kurse.status_setzen(k.kurs_id, kurse.LAEUFT)
    with pytest.raises(ValueError):
        kurse.status_setzen(k.kurs_id, "kaputt")


def test_zu_viele_aktive_kurse(leiter):
    for i in range(3):
        kurse.kurs_anlegen(f"Kurs {i}", "Bony")
    with pytest.raises(ZentraleFehler) as e:
        kurse.kurs_anlegen("Kurs 4", "Bony")
    assert e.value.status == 409 and e.value.meldung == "Du hast schon zu viele aktive Kurse."


def test_beitreten_teilnahmen_verlassen(leiter, zentrale):
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    anna = _zweite_instanz(zentrale)
    _als(anna)
    zentrale.geraete = [_geraet("g1", "pc-a", online=False, ip="100.64.0.8"), _geraet("g2", "pc-b")]
    assert [g["name"] for g in kurse.eigene_geraete()] == ["pc-b", "pc-a"]   # online zuerst

    with pytest.raises(ValueError, match="Kurscode"):
        kurse.kurs_beitreten(" - ", "g2", "Anna")
    with pytest.raises(ValueError, match="Agent-PC"):
        kurse.kurs_beitreten(kurs.code, "", "Anna")
    with pytest.raises(ZentraleFehler) as e:
        kurse.kurs_beitreten("ZZZZ-ZZZZ", "g2", "Anna")
    assert e.value.status == 404 and e.value.meldung == "Der Kurscode ist ungültig oder abgelaufen."
    assert Konto.laden().angemeldet   # 404 heißt hier nicht „kein Bony-Netz-Server“ und meldet nicht ab

    # Groß-/Kleinschreibung und Bindestrich egal
    k = kurse.kurs_beitreten(kurs.code.lower().replace("-", " "), "g2", " Anna ")
    assert k.name == "Hermes" and kurse.gemerkt(kurse.ANZEIGENAME) == "Anna"
    [t] = kurse.teilnahmen()
    assert (t.name, t.kursleiter_name, t.status, t.mein_geraet_id, t.code) == ("Hermes", "Bony", "offen", "g2", "")

    _als(leiter)
    [g] = kurse.geleitete_kurse()
    assert [(x.anzeigename, x.geraet_name, x.geraet_ip) for x in g.teilnehmer] == [("Anna", "pc-b", "100.64.0.7")]

    _als(anna)
    kurse.kurs_verlassen(kurs.kurs_id)
    assert kurse.teilnahmen() == []


def test_kurs_voll_und_teilnehmer_entfernen(leiter, zentrale):
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    zentrale.geraete = [_geraet("g1", "pc-a")]
    zentrale.kurs_grenze = 1
    anna, ben = _zweite_instanz(zentrale), _zweite_instanz(zentrale)
    _als(anna)
    kurse.kurs_beitreten(kurs.code, "g1", "Anna")
    _als(ben)
    with pytest.raises(ZentraleFehler) as e:
        kurse.kurs_beitreten(kurs.code, "g1", "Ben")
    assert e.value.status == 409 and e.value.meldung == "Der Kurs ist voll."
    _als(leiter)
    kurse.teilnehmer_entfernen(kurs.kurs_id, anna.instanz_id)
    assert kurse.geleiteter_kurs(kurs.kurs_id).teilnehmer == []


def test_rechner_aus_bonys_vpn_ist_kein_agent_pc(leiter, zentrale):
    zentrale.geraete = [_geraet("g1", "pc-a"), _geraet("g9", "rechner-laptop")]
    netz.aendern(lambda k: k.extra.__setitem__(kurse.VPN_RECHNER, {"instanz_id": k.instanz_id,
                                                                    "name": "rechner-laptop"}))
    assert [g["name"] for g in kurse.eigene_geraete()] == ["pc-a"]
    # Merker einer anderen Instanz zählt nicht
    netz.aendern(lambda k: k.extra.__setitem__(kurse.VPN_RECHNER, {"instanz_id": "andere", "name": "pc-a"}))
    assert len(kurse.eigene_geraete()) == 2


def test_ohne_internet_und_falsche_antwort(leiter, zentrale):
    url = zentrale.url
    zentrale.webseite = 200
    with pytest.raises(netz.KeinBonyNetz):
        kurse.teilnahmen()
    zentrale.close()
    with pytest.raises(NetzFehler):
        kurse.teilnahmen()
    assert Konto.laden().angemeldet and Konto.laden().server == url


def test_instanz_geloescht_meldet_ab(leiter, zentrale):
    zentrale.instanzen.clear()
    with pytest.raises(ZentraleFehler):
        kurse.teilnahmen()
    assert not Konto.laden().angemeldet


def test_token_nie_in_meldungen(leiter, zentrale):
    token = Konto.laden().token
    for fn in (lambda: kurse.kurs_beitreten("ZZZZ-ZZZZ", "g", "A"), lambda: kurse.status_setzen("nix", "laeuft")):
        with pytest.raises(ZentraleFehler) as e:
            fn()
        assert token not in str(e.value) + e.value.meldung


def test_beobachter_meldet_beginn_einmal():
    b = kurse.Beobachter()
    offen, laeuft = kurse.Kurs("k1", "Hermes"), kurse.Kurs("k1", "Hermes", status="laeuft")
    assert b.neu_begonnen([offen]) == []
    assert b.neu_begonnen([laeuft]) == [laeuft]
    assert b.neu_begonnen([laeuft]) == []
    b.neu_begonnen([kurse.Kurs("k1", "Hermes", status="pausiert")])
    assert b.neu_begonnen([laeuft]) == [laeuft]   # wieder gestartet
    assert kurse.begonnen_text([laeuft]).startswith("Der Kurs „Hermes“ hat begonnen")


def test_datum():
    assert kurse.datum(None) == "–"
    assert kurse.datum(1760000000, uhrzeit=False).count(".") == 2


# ---------------------------------------------------------------- Fenster
@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


def _wait(qapp, w, timeout=10.0):
    end = time.monotonic() + timeout
    qapp.processEvents()
    while time.monotonic() < end:
        qapp.processEvents()
        if not w.busy:
            return
        time.sleep(0.01)
    raise AssertionError("Aufruf der Zentrale endet nicht")


def test_fenster_ohne_bony_netz(qapp, datadir, zentrale):
    from bonys_agents.gui.kurse_dialog import KurseDialog

    netz.server_wechseln(zentrale.url)
    zentrale.anfragen.clear()
    d = KurseDialog()
    d.show()
    qapp.processEvents()
    assert d.tabs.currentWidget() is d.pakete    # ohne Bony-Netz: Kurspakete zuerst
    assert not d.off.isVisible()                 # Hinweis gehört nur zu den Bony-Netz-Reitern
    d.tabs.setCurrentWidget(d.teilnahme)
    qapp.processEvents()
    assert d.off.isVisible() and not d.teilnahme.join_btn.isEnabled()
    assert d.local_btn.isVisible()   # Schulung im eigenen Netz geht immer
    assert zentrale.anfragen == []
    d.done(0)
    d.deleteLater()


def test_fenster_teilnahme(qapp, datadir, zentrale, monkeypatch):
    from bonys_agents.gui import kurse_dialog

    leiter = _anmelden(zentrale)
    zentrale.instanzen[leiter.token]["ist_kursleiter"] = True
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    anna = _zweite_instanz(zentrale)
    _als(anna)
    zentrale.geraete = [_geraet("g1", "pc-a", online=False), _geraet("g2", "pc-b")]

    d = kurse_dialog.KurseDialog()
    d.tabs.setCurrentWidget(d.teilnahme)
    d.show()
    s = d.teilnahme
    d._tick()
    _wait(qapp, s)
    assert not d.off.isVisible()
    assert [s.geraet.itemText(i) for i in range(s.geraet.count())] == ["pc-b · online", "pc-a · offline"]
    assert s.empty.isVisible()
    assert not s.join_btn.isEnabled()   # erst mit Code

    s.code.setText("ZZZZ-ZZZZ")
    s.join_btn.click()
    _wait(qapp, s)
    assert s.status.text() == "Nicht beigetreten: Der Kurscode ist ungültig oder abgelaufen."

    s.code.setText(kurs.code)
    s.name.setText("Anna")
    s.join_btn.click()
    _wait(qapp, s)
    assert s.status.text() == "Beigetreten: „Hermes“."
    qapp.processEvents()
    _wait(qapp, s)
    assert s.table.rowCount() == 1 and s.table.item(0, 3).text() == "pc-b"
    s.table.selectRow(0)
    assert not s.room_btn.isEnabled()          # Kurs läuft noch nicht
    zentrale.kurse[kurs.kurs_id]["status"] = "laeuft"
    s.tick(sofort=True)
    _wait(qapp, s)
    s.table.selectRow(0)
    assert s.table.item(0, 2).text() == "läuft" and s.room_btn.isEnabled()

    monkeypatch.setattr(kurse_dialog, "nachfragen", lambda *a, **k: True)
    s.leave_btn.click()
    _wait(qapp, s)
    assert s.table.rowCount() == 0 and kurse.teilnahmen() == []
    assert anna.token not in s.status.text()
    d.done(0)
    d.deleteLater()


@pytest.mark.kursleiter
def test_fenster_kursleitung(qapp, datadir, zentrale, monkeypatch):
    from bonys_agents.gui.kurse_dialog import KurseDialog
    from PySide6.QtWidgets import QDialog

    from bonys_agents.trainer.gui import kurse_leiten

    leiter = _anmelden(zentrale)
    d = KurseDialog()
    d.show()
    s = d.leitung
    assert d.tabs.currentWidget() is s and d.tabs.tabText(1) == "Kursleitung"
    d._tick()
    _wait(qapp, s)
    assert s.stack.currentIndex() == 0     # noch kein Kursleiter: nur Code einlösen
    s.code.setText("falsch")
    s.redeem_btn.click()
    _wait(qapp, s)
    assert s.status.text() == "Nicht freigeschaltet: Der Kursleiter-Code ist ungültig."
    s.code.setText("LEITER-OK")
    s.redeem_btn.click()
    _wait(qapp, s)
    _wait(qapp, s)
    assert s.stack.currentIndex() == 1 and Konto.laden().ist_kursleiter

    # Neuer Kurs
    n = kurse_leiten.NeuerKursDialog(s)
    assert n.days.value() == 14 and n.days.minimum() == 1 and n.days.maximum() == 60
    assert not n.ok_btn.isEnabled()
    n.name.setText("Hermes")
    n.leader.setText("Bony")
    n.days.setValue(3)
    n.ok_btn.click()
    _wait(qapp, n)
    assert n.result() == QDialog.Accepted and n.kurs.name == "Hermes"
    [k] = zentrale.kurse.values()
    assert k["kursleiter_name"] == "Bony"
    assert kurse_leiten.NeuerKursDialog(s).leader.text() == "Bony"   # gemerkt

    s.tick(sofort=True)
    _wait(qapp, s)
    assert s.table.rowCount() == 1
    assert [s.table.item(0, i).text() for i in range(4)] == ["Hermes", "offen", "0", k["code"]]

    # Teilnehmer tritt bei (zweiter Rechner)
    zentrale.geraete = [_geraet("g1", "pc-a", ip="100.64.0.9")]
    anna = _zweite_instanz(zentrale)
    _als(anna)
    kurse.kurs_beitreten(k["code"], "g1", "Anna")
    _als(leiter)

    # Kursansicht
    v = kurse_leiten.KursAnsicht(kurse.geleiteter_kurs(k["kurs_id"]), s)
    v.show()
    qapp.processEvents()
    assert v.code.text() == k["code"] and v.valid.text().startswith("gültig bis ")
    assert v.start_btn.isVisible() and not v.pause_btn.isVisible() and not v.room_btn.isVisible()
    assert [v.table.item(0, i).text() for i in range(3)] == ["Anna", "pc-a", "100.64.0.9"]
    v.copy_btn.click()
    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text() == k["code"]

    v.start_btn.click()
    _wait(qapp, v)
    assert k["status"] == "laeuft" and v.pause_btn.isVisible() and v.room_btn.isVisible()
    assert not v.start_btn.isVisible()
    v.pause_btn.click()
    _wait(qapp, v)
    assert k["status"] == "pausiert" and v.start_btn.isVisible()

    # Teilnehmer entfernen mit Rückfrage
    asked = []
    monkeypatch.setattr(kurse_leiten, "nachfragen", lambda *a, **kw: asked.append(a[2]) or True)
    v.table.selectRow(0)
    v.remove_btn.click()
    _wait(qapp, v)
    assert asked == ["„Anna“ aus dem Kurs entfernen?"] and v.table.rowCount() == 0 and k["_teiln"] == {}

    # Beenden mit Rückfrage
    v.end_btn.click()
    _wait(qapp, v)
    assert "verlieren den Zugang" not in asked[-1]   # Text steht im Detail, Frage nennt den Kurs
    assert asked[-1] == "Kurs „Hermes“ beenden?"
    assert k["status"] == "beendet" and not v.end_btn.isVisible() and not v.start_btn.isVisible()
    assert "beendet" in v.valid.text()
    assert leiter.token not in v.status.text() + v.info.text()
    v.done(0)
    d.done(0)
    d.deleteLater()


def test_hauptfenster_meldet_kursbeginn(qapp, datadir, zentrale, monkeypatch):
    from types import SimpleNamespace

    from bonys_agents import deps
    from bonys_agents.gui import main_window

    monkeypatch.setattr(deps, "check", lambda info: SimpleNamespace(ok=True, can_run=True))
    monkeypatch.setattr(main_window.updates, "auto_check_due", lambda: False)
    leiter = _anmelden(zentrale)
    zentrale.instanzen[leiter.token]["ist_kursleiter"] = True
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    zentrale.geraete = [_geraet("g1", "pc-a")]
    _als(_zweite_instanz(zentrale))
    kurse.kurs_beitreten(kurs.code, "g1", "Anna")
    zentrale.kurse[kurs.kurs_id]["status"] = "laeuft"

    win = main_window.MainWindow()
    try:
        win.timer.stop()
        win.show()
        assert win.join_btn.text() == "Kurse"
        win._kurse_zuletzt = 0.0
        win.refresh()
        win._kurse_check.wait(5000)
        qapp.processEvents()
        assert win.statusBar().currentMessage().startswith("Der Kurs „Hermes“ hat begonnen")
        # höchstens jede Minute
        abfragen = zentrale.anfragen.count("GET /api/v1/kurse/teilnahmen")
        win.refresh()
        assert zentrale.anfragen.count("GET /api/v1/kurse/teilnahmen") == abfragen
        # ohne Teilnahmen wird nicht weiter gefragt
        kurse.kurs_verlassen(kurs.kurs_id)
        win._kurse_zuletzt = 0.0
        win.refresh()
        win._kurse_check.wait(5000)
        qapp.processEvents()
        assert win._kurse_aktiv is False
        abfragen = zentrale.anfragen.count("GET /api/v1/kurse/teilnahmen")
        win._kurse_zuletzt = 0.0
        win.refresh()
        assert zentrale.anfragen.count("GET /api/v1/kurse/teilnahmen") == abfragen
    finally:
        win.timer.stop()
        win.close()


def test_anwender_hat_keine_kursleitung(qapp, datadir):
    from bonys_agents.gui.kurse_dialog import KurseDialog

    d = KurseDialog()
    tabs = [d.tabs.tabText(i) for i in range(d.tabs.count())]
    assert tabs == (["Kurspakete", "Kursleitung", "Teilnahme"] if edition.IS_TRAINER
                    else ["Kurspakete", "Teilnahme"])
    d.deleteLater()
