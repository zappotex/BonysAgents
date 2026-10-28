# SPDX-License-Identifier: GPL-3.0-or-later
"""Annahme-Dienst des Kursportals: Anmeldung, Grenzen, Prüfung, Verlauf."""

import http.client
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from bonys_agents import kurspaket
from test_kurspaket import PAKET, paket_ordner

QUELLE = Path(__file__).resolve().parents[1] / "packaging" / "kursportal-server" / "portal_server.py"


@pytest.fixture
def portal(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("portal_server", QUELLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "DATEN", tmp_path / "daten")
    server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mod.port = server.server_address[1]
    yield mod
    server.shutdown()
    server.server_close()


def _post(portal, body, token=None, pfad="/einreichen", laenge=None):
    c = http.client.HTTPConnection("127.0.0.1", portal.port, timeout=10)
    kopf = {"Content-Length": str(len(body) if laenge is None else laenge)}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    c.request("POST", pfad, body=body, headers=kopf)
    r = c.getresponse()
    daten = json.loads(r.read())
    c.close()
    return r.status, daten


def _paket(tmp_path, mit_skript=False):
    paket = paket_ordner(tmp_path / ("q-skript" if mit_skript else "q"), {**PAKET, "lektionen": []})
    if not mit_skript:
        (paket / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").unlink()
    datei = tmp_path / "p.bonyspaket"
    kurspaket.packen(paket, datei)
    return datei.read_bytes()


def test_ohne_oder_mit_falschem_token_abgewiesen(portal, tmp_path):
    inhalt = _paket(tmp_path)
    assert _post(portal, inhalt)[0] == 401
    assert _post(portal, inhalt, "falsch")[0] == 401
    assert not (portal.DATEN / "ablage").exists()


def test_gueltige_einreichung_wird_geprueft_und_nicht_veroeffentlicht(portal, tmp_path):
    token = portal.token_neu("autor-1")
    assert token not in (portal.DATEN / "tokens.json").read_text()

    status, antwort = _post(portal, _paket(tmp_path), token)
    assert status == 200 and antwort["status"] == "approved"

    status, antwort = _post(portal, _paket(tmp_path, mit_skript=True), token)
    assert antwort["status"] == "needs_review"
    mod, ablage = portal._moderation()
    assert len(ablage.ids()) == 2


def test_zu_gross_kein_zip_und_rate_limit(portal, tmp_path, monkeypatch):
    token = portal.token_neu("autor-1")
    monkeypatch.setattr(portal, "MAX_BYTES", 100)
    assert _post(portal, b"x" * 10, token, laenge=101)[0] == 413
    monkeypatch.setattr(portal, "MAX_BYTES", 50 * 1024 * 1024)

    status, antwort = _post(portal, b"kein zip", token)
    assert status == 200 and antwort["status"] == "rejected"

    monkeypatch.setattr(portal, "LIMIT_STUNDE", 2)
    portal._ZEITEN.clear()
    assert _post(portal, b"a", token)[0] == 200
    assert _post(portal, b"a", token)[0] == 200
    assert _post(portal, b"a", token)[0] == 429


def test_zu_viele_fehlversuche_sperren_voruebergehend(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "LIMIT_FEHLVERSUCHE_MINUTE", 3)
    portal._FEHLVERSUCHE.clear()
    codes = [_post(portal, b"a", "x")[0] for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_speichergrenze_und_unbekannter_pfad(portal, tmp_path, monkeypatch):
    token = portal.token_neu("autor-1")
    monkeypatch.setattr(portal, "MAX_SPEICHER", 1)
    assert _post(portal, b"a", token)[0] == 200      # leere Ablage: 0 + 1 > 1 ist falsch
    assert _post(portal, b"a", token)[0] == 507
    assert _post(portal, b"a", token, pfad="/anderes")[0] == 404


def test_befehle_liste_und_entscheiden(portal, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    token = portal.token_neu("autor-1")
    _post(portal, _paket(tmp_path, mit_skript=True), token)
    mod, ablage = portal._moderation()
    sid = ablage.ids()[0]

    assert portal._cli(["liste"]) == 0 and sid in capsys.readouterr().out
    assert portal._cli(["entscheiden", sid, "approved", "bony", "Skript geprüft."]) == 0
    assert portal._cli(["entscheiden", sid, "published", "", "x"]) == 1
    assert ablage.status(sid) == "approved"


def test_reservierte_id_und_katalog_befehl(portal, tmp_path, monkeypatch, capsys):
    res = tmp_path / "res.json"
    res.write_text('["test-paket"]')
    monkeypatch.setattr(portal, "RESERVIERT", res)
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    token = portal.token_neu("autor-1")
    inhalt = _paket(tmp_path)      # ohne Skript -> technisch approved
    assert _post(portal, inhalt, token)[1]["status"] == "rejected"

    res.write_text("[]")
    sid = _post(portal, inhalt, token)[1]["submission_id"]
    assert portal._cli(["entscheiden", sid, "published", "bony", "frei"]) == 0
    assert "1 Paket" in capsys.readouterr().out
    index = json.loads((tmp_path / "katalog" / "index.json").read_text())
    assert [e["id"] for e in index["pakete"]] == ["test-paket"]
    assert portal._cli(["entscheiden", sid, "withdrawn", "bony", "zurück"]) == 0
    assert json.loads((tmp_path / "katalog" / "index.json").read_text())["pakete"] == []
