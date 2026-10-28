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


# ---------------------------------------------------------------- Moderation (Phase 1: lesend)
def _get(portal, pfad, token=None):
    c = http.client.HTTPConnection("127.0.0.1", portal.port, timeout=10)
    kopf = {"Authorization": f"Bearer {token}"} if token else {}
    c.request("GET", pfad, headers=kopf)
    r = c.getresponse()
    daten = json.loads(r.read())
    c.close()
    return r.status, daten


def test_moderation_braucht_moderator_token_und_trennt_die_zugaenge(portal, tmp_path):
    einreicher, moderator = portal.token_neu("autor-1"), portal.moderator_neu("bony")
    assert _get(portal, "/moderation/liste")[0] == 401
    assert _get(portal, "/moderation/liste", "falsch")[0] == 401
    assert _get(portal, "/moderation/liste", einreicher)[0] == 403          # Einreicher-Token öffnet nie die Moderation
    assert _post(portal, _paket(tmp_path), moderator)[0] == 401              # Moderator-Token nimmt nichts an
    assert _get(portal, "/moderation/liste", moderator) == (200, {"einreichungen": []})
    for datei in ("tokens.json", "moderatoren.json"):
        text = (portal.DATEN / datei).read_text()
        assert einreicher not in text and moderator not in text
        assert (portal.DATEN / datei).stat().st_mode & 0o777 == 0o600


def test_moderation_liste_und_detail_zeigen_nur_feste_felder(portal, tmp_path):
    einreicher, moderator = portal.token_neu("autor-geheim"), portal.moderator_neu("bony")
    _post(portal, _paket(tmp_path), einreicher)
    sid = _post(portal, _paket(tmp_path, mit_skript=True), einreicher)[1]["submission_id"]

    status, liste = _get(portal, "/moderation/liste", moderator)
    assert status == 200 and len(liste["einreichungen"]) == 2
    assert set(liste["einreichungen"][0]) == {"id", "status", "zeit", "paket_id", "name", "version"}
    assert "autor-geheim" not in json.dumps(liste)

    status, d = _get(portal, f"/moderation/einreichung/{sid}", moderator)
    assert status == 200 and d["status"] == "needs_review" and d["kette_ok"] is True
    assert d["bericht"]["skripte"] and "dateiname" not in d["bericht"]
    assert set(d["verlauf"][0]) == {"nr", "zeit", "von", "nach", "akteur", "begruendung"}
    assert d["verlauf"][0]["akteur"] == "autor-geheim"            # Moderation sieht die Referenz, der Katalog nie
    assert "pruefsumme" not in json.dumps(d) and "eingang" not in json.dumps(d)


def test_moderation_unbekannt_ungueltig_und_veraenderter_verlauf(portal, tmp_path):
    einreicher, moderator = portal.token_neu("autor-1"), portal.moderator_neu("bony")
    sid = _post(portal, _paket(tmp_path), einreicher)[1]["submission_id"]
    for pfad in ("/moderation/einreichung/" + "0" * 32, "/moderation/einreichung/../../tokens",
                 "/moderation/einreichung/%2e%2e", f"/moderation/einreichung/{sid}?x=1", "/moderation/anderes",
                 "/moderation/liste?x"):
        assert _get(portal, pfad, moderator)[0] == 404, pfad
    verlauf = portal.DATEN / "ablage" / sid / "verlauf.jsonl"
    verlauf.write_text(verlauf.read_text().replace("Eingereicht.", "Manipuliert."))
    status, d = _get(portal, f"/moderation/einreichung/{sid}", moderator)
    assert status == 200 and d["kette_ok"] is False


def test_moderation_hat_eigene_zaehler_und_limits(portal, monkeypatch):
    moderator = portal.moderator_neu("bony")
    monkeypatch.setattr(portal, "LIMIT_FEHLVERSUCHE_MINUTE", 2)
    monkeypatch.setattr(portal, "LIMIT_MOD_FEHLVERSUCHE", 3)
    portal._FEHLVERSUCHE.clear(), portal._MOD_FEHLVERSUCHE.clear()
    assert [_post(portal, b"a", "x")[0] for _ in range(3)] == [401, 401, 429]      # Annahme gesperrt …
    assert _get(portal, "/moderation/liste", moderator)[0] == 200                  # … Moderation nicht
    assert [_get(portal, "/moderation/liste", "x")[0] for _ in range(4)] == [401, 401, 401, 429]
    assert _get(portal, "/moderation/liste", moderator)[0] == 429                  # Sperre gilt kurz auch für gültige
    portal._MOD_FEHLVERSUCHE.clear()
    monkeypatch.setattr(portal, "LIMIT_MOD_MINUTE", 2)
    portal._ZEITEN.clear()
    assert [_get(portal, "/moderation/liste", moderator)[0] for _ in range(3)] == [200, 200, 429]


def test_zugangsbefehle_listen_und_entfernen(portal, capsys):
    t1 = portal.token_neu("autor-1")
    portal.moderator_neu("bony")
    assert portal._cli(["token-liste"]) == 0 and capsys.readouterr().out.split() == ["autor-1"]
    assert portal._cli(["moderator-liste"]) == 0 and capsys.readouterr().out.split() == ["bony"]
    assert portal._cli(["moderator-entfernen", "gibt-es-nicht"]) == 1
    assert portal._cli(["moderator-entfernen", "bony"]) == 0 and portal.moderator_fuer("x") is None
    assert portal._cli(["token-entfernen", "autor-1"]) == 0 and portal.autor_fuer(t1) is None
    assert portal._cli(["moderator-neu", "bony"]) == 0 and len(capsys.readouterr().out.split()[-1]) >= 40
    with pytest.raises(ValueError):
        portal.moderator_neu(" ")


def test_text_sicht_bereinigt_fremde_zeichen(portal):
    assert portal._text("a\x1b[31mb\nc" + "x" * 500, 20).startswith("a [31mb c")
    assert len(portal._text("x" * 500, 20)) == 20 and portal._text(None) == ""
    assert portal._texte("kein-list") == [] and len(portal._texte(["a"] * 500)) == 200


# ---------------------------------------------------------------- Moderation (Phase 2: schreibend)
def _entscheiden(portal, sid, nach, begruendung="Geprüft.", token=None, extra=None, roh=None):
    body = roh if roh is not None else json.dumps({"nach": nach, "begruendung": begruendung, **(extra or {})}).encode()
    return _post(portal, body, token, pfad=f"/moderation/entscheiden/{sid}")


def test_entscheiden_akteur_kommt_vom_token_und_aendert_den_katalog(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    einreicher, moderator = portal.token_neu("autor-1"), portal.moderator_neu("bony")
    sid = _post(portal, _paket(tmp_path, mit_skript=True), einreicher)[1]["submission_id"]

    assert _entscheiden(portal, sid, "approved")[0] == 401
    assert _entscheiden(portal, sid, "approved", token=einreicher)[0] == 403

    status, antwort = _entscheiden(portal, sid, "approved", "Skript gelesen.", moderator, extra={"akteur": "fremd"})
    assert (status, antwort["status"], antwort["akteur"]) == (200, "approved", "bony")
    status, antwort = _entscheiden(portal, sid, "published", "Freigabe.", moderator)
    assert status == 200 and antwort["katalog_ok"] is True
    index = json.loads((tmp_path / "katalog" / "index.json").read_text())
    assert [e["id"] for e in index["pakete"]] == ["test-paket"]

    detail = _get(portal, f"/moderation/einreichung/{sid}", moderator)[1]
    assert [(e["nach"], e["akteur"]) for e in detail["verlauf"][-2:]] == [("approved", "bony"), ("published", "bony")]
    assert detail["kette_ok"] is True and "fremd" not in json.dumps(detail)

    assert _entscheiden(portal, sid, "withdrawn", "Zurück.", moderator)[0] == 200
    assert json.loads((tmp_path / "katalog" / "index.json").read_text())["pakete"] == []


def test_entscheiden_lehnt_verbotenes_und_ungueltiges_ab(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    einreicher, moderator = portal.token_neu("autor-1"), portal.moderator_neu("bony")
    sid = _post(portal, _paket(tmp_path, mit_skript=True), einreicher)[1]["submission_id"]       # needs_review

    status, antwort = _entscheiden(portal, sid, "published", token=moderator)
    assert status == 409 and "nicht erlaubt" in antwort["meldung"]                # needs_review -> published
    assert _entscheiden(portal, sid, "approved", "", moderator)[0] == 422         # Begründung fehlt
    assert _entscheiden(portal, sid, "approved", "x" * 2001, moderator)[0] == 422
    assert _entscheiden(portal, sid, "uploaded", token=moderator)[0] == 422       # kein Zielstatus für Menschen
    assert _entscheiden(portal, sid, "approved", token=moderator, roh=b"kein json")[0] == 400
    assert _entscheiden(portal, sid, "approved", token=moderator, roh=b'{"nach": 1, "begruendung": 2}')[0] == 400
    assert _entscheiden(portal, "0" * 32, "approved", token=moderator)[0] == 404
    assert _entscheiden(portal, "../x", "approved", token=moderator)[0] == 404
    assert _post(portal, b"x" * 20000, moderator, pfad=f"/moderation/entscheiden/{sid}")[0] == 413
    assert _post(portal, b"", moderator, pfad=f"/moderation/entscheiden/{sid}")[0] == 413
    mod, ablage = portal._moderation()
    assert ablage.status(sid) == "needs_review"                                    # nichts davon hat etwas geändert


def test_entscheiden_sperrt_reservierte_ids_auch_serverseitig(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "KATALOG", tmp_path / "katalog")
    einreicher, moderator = portal.token_neu("autor-1"), portal.moderator_neu("bony")
    sid = _post(portal, _paket(tmp_path), einreicher)[1]["submission_id"]          # approved
    res = tmp_path / "res.json"
    res.write_text('["test-paket"]')                                               # ID wird nachträglich reserviert
    monkeypatch.setattr(portal, "RESERVIERT", res)
    status, antwort = _entscheiden(portal, sid, "published", token=moderator)
    assert status == 409 and "mitgelieferten" in antwort["meldung"]
    assert not (tmp_path / "katalog" / "index.json").exists()


def test_entscheiden_zaehlt_fehlversuche_getrennt(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "LIMIT_MOD_FEHLVERSUCHE", 2)
    portal._MOD_FEHLVERSUCHE.clear()
    sid = "0" * 32
    assert [_entscheiden(portal, sid, "approved", token="x")[0] for _ in range(3)] == [401, 401, 429]
