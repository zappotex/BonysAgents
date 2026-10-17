# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony-Netz in Bony's Agents (bonys_agents.netz und das Fenster „Bony-Netz“) gegen eine kleine Test-Zentrale
auf 127.0.0.1 – nie gegen den echten Server."""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bony_netz import Konto, NetzFehler
from bonys_agents import netz


class FakeZentrale:
    """Antwortet wie die Zentrale (API.md) – oder als gewöhnliche Webseite (``webseite``)."""

    def __init__(self):
        self.instanzen: dict[str, dict] = {}   # token -> {instanz_id, ist_kursleiter}
        self.anfragen: list[str] = []
        self.webseite = None   # None | 200 | 404
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, data=None, html=False):
                body = (b"<html>Hallo</html>" if html else json.dumps(data).encode()) if data is not None or html \
                    else b""
                self.send_response(code)
                self.send_header("Content-Type", "text/html" if html else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _route(self):
                outer.anfragen.append(f"{self.command} {self.path}")
                if outer.webseite:
                    return self._send(outer.webseite, html=True)
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                key = (self.command, self.path)
                if key == ("GET", "/api/v1/info"):
                    return self._send(200, {"server_name": "Test-Zentrale", "version": "1.2.3",
                                            "login_server": "https://vpn.test", "kursraum_url": "wss://k.test"})
                if key == ("POST", "/api/v1/instanzen"):
                    n = len(outer.instanzen) + 1
                    data = {"instanz_id": f"inst{n:04d}abcdefgh", "token": f"bz_geheim{n}",
                            "login_server": "https://vpn.test"}
                    outer.instanzen[data["token"]] = {"instanz_id": data["instanz_id"], "ist_kursleiter": False}
                    return self._send(201, data)
                instanz = outer.instanzen.get(token)
                if instanz is None:
                    return self._send(401, {"detail": "Diese Instanz ist nicht (mehr) angemeldet."})
                if key == ("GET", "/api/v1/instanz"):
                    return self._send(200, {**instanz, "erstellt": 1760000000})
                if key == ("DELETE", "/api/v1/instanz"):
                    del outer.instanzen[token]
                    return self._send(204)
                return self._send(404, {"detail": "Nicht gefunden"})

            do_GET = do_POST = do_DELETE = _route

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def zentrale(tmp_path, monkeypatch):
    monkeypatch.setenv("BONY_NETZ_ORDNER", str(tmp_path / "bony-netz"))
    z = FakeZentrale()
    yield z
    z.close()


def _free_port_url() -> str:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


# ---------------------------------------------------------------- Logik
def test_standard_ist_aus():
    assert not netz.aktiv(Konto.laden())
    assert netz.aktiv(netz.aktiv_setzen(True))
    assert netz.aktiv(Konto.laden())


def test_ganzer_ablauf(zentrale):
    z = netz.server_wechseln(zentrale.url)
    assert z.verbunden and z.text == "Verbunden mit Test-Zentrale" and z.info["version"] == "1.2.3"
    assert not z.konto.angemeldet

    konto = netz.instanz_anlegen(zentrale.url)
    assert konto.angemeldet
    neu = Konto.laden()   # wie nach einem Neustart der App
    assert neu.angemeldet and neu.instanz_id == konto.instanz_id and neu.server == zentrale.url
    assert netz.kurz_id(neu.instanz_id) == "inst0001"

    # Kein zweites Anlegen, wenn schon eine Instanz da ist (z. B. aus Bony's VPN)
    assert netz.instanz_anlegen(zentrale.url).instanz_id == konto.instanz_id
    assert len(zentrale.instanzen) == 1

    zentrale.instanzen[konto.token]["ist_kursleiter"] = True
    z = netz.zustand()
    assert z.verbunden and z.konto.ist_kursleiter and Konto.laden().ist_kursleiter
    assert "bz_" not in z.text + z.detail

    assert not netz.instanz_loeschen().angemeldet
    assert not Konto.laden().angemeldet and zentrale.instanzen == {}


def test_anmeldung_ungueltig_wird_verworfen(zentrale):
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    zentrale.instanzen.clear()   # Instanz auf dem Server gelöscht
    z = netz.zustand()
    assert z.text == netz.ANMELDUNG_UNGUELTIG and not z.konto.angemeldet and not Konto.laden().angemeldet


def test_loeschen_wenn_auf_dem_server_schon_weg(zentrale):
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    zentrale.instanzen.clear()
    assert not netz.instanz_loeschen().angemeldet


@pytest.mark.parametrize("code", [200, 404])
def test_falscher_server_ergibt_verstaendliche_meldung(zentrale, code):
    zentrale.webseite = code
    with pytest.raises(netz.KeinBonyNetz, match="kein Bony-Netz-Server"):
        netz.server_info(zentrale.url)
    netz.aendern(lambda k: k.server_wechseln(zentrale.url))
    z = netz.zustand()
    assert not z.verbunden and "kein Bony-Netz-Server" in z.text


def test_falscher_server_wird_nicht_uebernommen(zentrale):
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    zentrale.webseite = 404
    with pytest.raises(netz.KeinBonyNetz):
        netz.server_wechseln(zentrale.url + "/anders")
    konto = Konto.laden()
    assert konto.server == zentrale.url and konto.angemeldet


def test_ohne_verbindung(zentrale):
    netz.aendern(lambda k: k.server_wechseln(_free_port_url()))
    z = netz.zustand()
    assert z.text == netz.KEINE_VERBINDUNG and not z.verbunden and "nicht erreichbar" in z.detail
    with pytest.raises(NetzFehler):
        netz.server_wechseln(_free_port_url())


def test_konto_datei_nur_fuer_den_benutzer(zentrale):
    netz.aktiv_setzen(True)
    if os.name == "posix":
        assert oct(Konto.pfad().stat().st_mode & 0o777) == "0o600"


# ---------------------------------------------------------------- Fenster
@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


def _wait(qapp, dialog, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if not dialog.busy:
            return
        time.sleep(0.01)
    raise AssertionError("Aufruf der Zentrale endet nicht")


def test_fenster_ausgeschaltet_fragt_nicht(qapp, zentrale):
    from bonys_agents.gui.netz_dialog import NetzDialog

    netz.aendern(lambda k: k.server_wechseln(zentrale.url))
    d = NetzDialog()
    qapp.processEvents()
    assert not d.active.isChecked() and not d.check_btn.isEnabled() and not d.create_btn.isEnabled()
    assert d.status.text() == "Bony-Netz ist ausgeschaltet."
    assert zentrale.anfragen == []
    d.deleteLater()


def test_fenster_anlegen_neustart_loeschen(qapp, zentrale, monkeypatch):
    from bonys_agents.gui import netz_dialog

    netz.aendern(lambda k: k.server_wechseln(zentrale.url))
    d = netz_dialog.NetzDialog()
    d.active.setChecked(True)
    assert d.busy and not d.check_btn.isEnabled()   # während des Aufrufs gesperrt
    _wait(qapp, d)
    assert netz.aktiv(Konto.laden())
    assert d.status.text() == "Verbunden mit Test-Zentrale" and "Version 1.2.3" in d.server_info.text()

    d.create_btn.click()
    _wait(qapp, d)
    _wait(qapp, d)   # danach wird der Zustand gefragt
    konto = Konto.laden()
    assert konto.angemeldet
    assert d.instance.text() == f"Instanz-ID: {konto.instanz_id[:8]} · Kursleiter: nein"
    assert d.delete_btn.isVisibleTo(d) and not d.create_btn.isVisibleTo(d)
    assert konto.token not in d.instance.text() + d.status.text() + d.status.toolTip()
    d.deleteLater()

    # Neues Fenster (wie nach Neustart): noch angemeldet, Zustand wird gleich gefragt
    zentrale.instanzen[konto.token]["ist_kursleiter"] = True
    d = netz_dialog.NetzDialog()
    _wait(qapp, d)
    assert d.instance.text().endswith("Kursleiter: ja")

    monkeypatch.setattr(netz_dialog, "confirm_delete", lambda *a, **k: True)
    d.delete_btn.click()
    _wait(qapp, d)
    assert not Konto.laden().angemeldet and zentrale.instanzen == {}
    assert d.status.text() == "Instanz gelöscht." and d.create_btn.isVisibleTo(d)
    d.deleteLater()


def test_fenster_falscher_server(qapp, zentrale):
    from bonys_agents.gui.netz_dialog import NetzDialog

    netz.aktiv_setzen(True)
    netz.aendern(lambda k: k.server_wechseln(zentrale.url))
    d = NetzDialog()
    _wait(qapp, d)
    zentrale.webseite = 200
    d.server.setText(zentrale.url + "/anders")
    assert not d.create_btn.isEnabled()   # erst „Prüfen“
    d.check_btn.click()
    _wait(qapp, d)
    assert "kein Bony-Netz-Server" in d.status.text() and "nicht übernommen" in d.status.text()
    assert Konto.laden().server == zentrale.url
    d.deleteLater()
