# SPDX-License-Identifier: GPL-3.0-or-later
"""Online-Moderation: Client und Dialog gegen den echten Annahme-Server (lokaler Port)."""

import io
import json
import os
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from bonys_agents import kurspaket_moderation as mod  # noqa: E402
from bonys_agents import kurspaket_moderation_client as client  # noqa: E402
from bonys_agents.gui.moderation_dialog import ModerationDialog  # noqa: E402
from test_kursportal_server import _paket, _post, portal  # noqa: E402,F401  (portal = Fixture)

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def server(portal, datadir, tmp_path, monkeypatch):      # noqa: F811
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    monkeypatch.setenv(client.PORTAL_ENV, f"http://127.0.0.1:{portal.port}")
    portal.einreicher = portal.token_neu("autor-geheim")
    portal.moderator = portal.moderator_neu("bony")
    portal.sid = _post(portal, _paket(tmp_path, mit_skript=True), portal.einreicher)[1]["submission_id"]
    return portal


def test_zugang_wird_mit_rechten_600_gespeichert_und_geprueft(datadir):
    assert client.zugang_laden() is None
    client.zugang_speichern("abc123", "https://kurse.example.org/")
    z = client.zugang_laden()
    assert (z.url, z.token) == ("https://kurse.example.org", "abc123")
    assert client._zugang_datei().stat().st_mode & 0o777 == 0o600
    for token in ("", "mit leerzeichen", "x" * 201):
        with pytest.raises(client.OnlineFehler):
            client.zugang_speichern(token, "https://kurse.example.org")
    with pytest.raises(client.OnlineFehler, match="https"):
        client.zugang_speichern("abc", "http://kurse.example.org")
    client.zugang_loeschen()
    assert client.zugang_laden() is None


def test_client_liest_und_entscheidet_ueber_den_server(server):
    ablage = client.OnlineAblage(client.Zugang(client.portal_url(), server.moderator))
    ablage.aktualisieren()
    assert ablage.ids() == [server.sid] and ablage.status(server.sid) == "needs_review"
    assert ablage.bericht(server.sid)["paket_id"] == "test-paket"          # nur Listenfelder, noch kein Detail
    assert ablage.verlauf(server.sid)[0].akteur == "autor-geheim" and ablage.kette_ok(server.sid)
    assert ablage.bericht(server.sid)["skripte"]

    ablage.entscheiden(server.sid, mod.APPROVED, "ignoriert", "Skript gelesen.")
    assert ablage.status(server.sid) == "approved"
    assert ablage.verlauf(server.sid)[-1].akteur == "bony"                  # Akteur kommt vom Token
    with pytest.raises(client.OnlineFehler, match="nicht erlaubt"):
        ablage.entscheiden(server.sid, mod.WITHDRAWN, "x", "Nein.")
    with pytest.raises(client.OnlineFehler, match="Begründung"):
        ablage.entscheiden(server.sid, mod.PUBLISHED, "x", "")
    ablage.entscheiden(server.sid, mod.PUBLISHED, "x", "Frei.")
    assert json.loads((server.KATALOG / "index.json").read_text())["pakete"][0]["id"] == "test-paket"


def test_client_meldet_falsche_zugaenge_verstaendlich(server):
    url = client.portal_url()
    with pytest.raises(client.OnlineFehler, match="gilt nicht"):
        client.OnlineAblage(client.Zugang(url, "falsch")).aktualisieren()
    with pytest.raises(client.OnlineFehler, match="nicht zu einem Moderator"):
        client.OnlineAblage(client.Zugang(url, server.einreicher)).aktualisieren()
    with pytest.raises(client.OnlineFehler, match="Ungültige"):
        client.OnlineAblage(client.Zugang(url, server.moderator)).detail_laden("../x")
    with pytest.raises(client.OnlineFehler, match="https"):
        client.OnlineAblage(client.Zugang("http://kurse.example.org", "t"))


def test_client_traut_antworten_nicht_und_folgt_keiner_weiterleitung():
    def opener_mit(inhalt):
        def opener(req, timeout=None):
            r = io.BytesIO(inhalt)
            r.__enter__ = lambda: r
            return r
        return opener

    z = client.Zugang("https://kurse.example.org", "t")
    for inhalt in (b"kein json", b"[1, 2]", b'{"einreichungen": "x"}'):
        with pytest.raises(client.OnlineFehler, match="unverständlich"):
            client.OnlineAblage(z, opener=opener_mit(inhalt)).aktualisieren()
    o = client.OnlineAblage(z, opener=opener_mit(json.dumps({"einreichungen": [
        {"id": "nicht-hex", "status": "approved"},
        {"id": "a" * 32, "status": "approved\x1b[31m", "name": "N" * 500, "zeit": "", "paket_id": "p", "version": "1"}
    ]}).encode()))
    o.aktualisieren()
    assert o.ids() == ["a" * 32] and "\x1b" not in o.status("a" * 32) and len(o.bericht("a" * 32)["name"]) <= 120
    assert client._KeineWeiterleitung().redirect_request() is None
    err = urllib.error.HTTPError("https://x", 302, "Found", {}, None)
    assert "302" in client.OnlineAblage._fehlertext(err)


def test_dialog_online_anmelden_ansehen_entscheiden_abmelden(server, monkeypatch):
    warnungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnungen.append(a[2]))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("falsch", True))
    d = ModerationDialog(mod.Moderation(server.DATEN / "lokal"))
    try:
        d.quelle.setCurrentIndex(1)                                         # falsches Token → zurück zu „Lokal“
        assert warnungen and "gilt nicht" in warnungen[-1] and d.quelle.currentIndex() == 0
        assert d.ablage is d.lokal

        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (server.moderator, True))
        d.quelle.setCurrentIndex(1)
        assert d.quelle.currentIndex() == 1 and d.ablage is d.online and d.tabelle.rowCount() == 1
        assert not d.akteur.isEnabled() and not d.datei_knopf.isEnabled() and d.abmelden_knopf.isEnabled()
        d.tabelle.selectRow(0)
        text = d.details.toPlainText()
        assert "test-paket" in text.lower() and "Skripte:" in text and "**" not in text    # Klartext, kein Markdown

        monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a: ("Skript gelesen.", True))
        d.knoepfe[mod.APPROVED].click()
        assert d.ablage.status(server.sid) == "approved" and "bony" in d.details.toPlainText()
        assert client.zugang_laden().token == server.moderator

        d.abmelden_knopf.click()                                            # Token weg, wieder lokal
        assert client.zugang_laden() is None and d.quelle.currentIndex() == 0 and d.ablage is d.lokal
    finally:
        d.close()
        APP.processEvents()


def test_dialog_zeigt_verlaufsmanipulation_und_unerreichbaren_server(server, monkeypatch):
    warnungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnungen.append(a[2]))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (server.moderator, True))
    verlauf = server.DATEN / "ablage" / server.sid / "verlauf.jsonl"
    verlauf.write_text(verlauf.read_text().replace("Eingereicht.", "Manipuliert."))
    d = ModerationDialog(mod.Moderation(server.DATEN / "lokal"))
    try:
        d.quelle.setCurrentIndex(1)
        d.tabelle.selectRow(0)
        assert "verändert" in d.details.toPlainText() and "Nicht entscheiden" in d.details.toPlainText()
        d.online.zugang.url = "http://127.0.0.1:9"                           # Server nicht erreichbar
        d.aktualisieren_knopf.click()
        assert warnungen and "nicht erreichbar" in warnungen[-1]
    finally:
        d.close()
        APP.processEvents()
