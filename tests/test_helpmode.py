# SPDX-License-Identifier: GPL-3.0-or-later
"""Hilfe-Modus: Teilnehmer verbindet sich ausgehend mit dem Kurs-Server, Ansehen nur nach Zustimmung, Steuern nur
nach zweiter Zustimmung (geprüft beim Teilnehmer), Beenden trennt sofort, Protokoll ohne Bildinhalte."""

import json
import time
from types import SimpleNamespace

import pytest
from test_present import Client, FakeVNC, _novnc, _wait

from bonys_agents import helpmode, present, rfb, share, storage, websocket


class Machine:
    def __init__(self):
        self.name = "teilnehmer-pc"
        self.vnc = FakeVNC()

    def vnc_connect(self):
        return self.vnc.connect()


@pytest.fixture
def course(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "daten")
    srv = present.Presentation(port=0, bind="127.0.0.1", advertise=False, novnc=_novnc(tmp_path))
    srv.clients = []
    srv.start()
    yield srv
    srv.stop()
    for c in srv.clients:   # alle Rückrufe fertig, bevor der echte Datenordner wieder gilt
        c.close()
        if c._thread:
            c._thread.join(5)
        _wait(lambda c=c: c.watching == 0)


def _target(srv, code=None, fp=None):
    return share.Target("127.0.0.1", srv.port, srv.code if code is None else code,
                        srv.fingerprint if fp is None else fp)


def _participant(srv, **kw):
    calls = {"view": 0, "control": 0, "closed": []}
    m = Machine()
    c = helpmode.HelpClient(_target(srv), m, "Kim",
                            on_view_request=lambda: calls.__setitem__("view", calls["view"] + 1),
                            on_control_request=lambda: calls.__setitem__("control", calls["control"] + 1),
                            on_closed=lambda r: calls["closed"].append(r), **kw)
    srv.clients.append(c)
    c.connect()
    assert _wait(lambda: srv.helpdesk.session_list() and c.session_id)
    return c, m, calls


def _teacher(srv, url: str) -> Client:
    t = Client(srv)
    sid = url.split("/help/")[1].split("#")[0]
    token = url.split("#t=")[1]
    assert t.request("GET", f"/help/{sid}")[0] == 200
    st, _h, body = t.request("POST", "/bonys/v1/help/auth", {"s": sid, "t": token})
    assert st == 200 and t.cookie.startswith(helpmode.COOKIE + "=")
    t.sid = sid
    return t


def _view_ws(t: Client):
    st, head, conn = t.request("GET", f"/bonys/v1/help/view?s={t.sid}", headers={
        "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": websocket.new_key(),
        "Sec-WebSocket-Version": "13"})
    if st != 101:
        return st, None
    s, f = conn
    return st, websocket.Connection(f, s.makefile("wb"), client=True)


def _status(t: Client) -> dict:
    return json.loads(t.request("GET", f"/bonys/v1/help/status?s={t.sid}")[2])


def test_wrong_code_and_fingerprint_are_refused(course):
    m = Machine()
    with pytest.raises(share.FingerprintMismatch):
        helpmode.HelpClient(_target(course, fp="00" * 32), m).connect()
    with pytest.raises(share.WrongCode):
        helpmode.HelpClient(_target(course, code="0000-AAAA"), m).connect()
    for _ in range(share.MAX_FAILS_PER_ADDR - 1):
        with pytest.raises(share.WrongCode):
            helpmode.HelpClient(_target(course, code="0000-AAAA"), m).connect()
    with pytest.raises(helpmode.HelpError, match="Minute"):
        helpmode.HelpClient(_target(course), m).connect()      # richtiger Code – aber gesperrt
    assert course.helpdesk.session_list() == []


def test_request_appears_for_teacher(course):
    c, _m, _calls = _participant(course)
    c.request("Brave startet nicht")
    assert _wait(lambda: course.helpdesk.session_list()[0].state == helpmode.WAITING)
    s = course.helpdesk.session_list()[0]
    assert (s.name, s.vm, s.message) == ("Kim", "teilnehmer-pc", "Brave startet nicht")
    assert course.helpdesk.requests_total == 1
    c.cancel()
    assert _wait(lambda: course.helpdesk.session_list()[0].state == helpmode.CONNECTED)


def test_no_picture_without_consent(course):
    c, m, calls = _participant(course)
    sid = c.session_id
    url = course.helpdesk.view_url(sid)
    assert _wait(lambda: calls["view"] == 1)                 # Teilnehmer wird gefragt
    t = _teacher(course, url)
    assert _status(t)["view"] is False
    assert _view_ws(t)[0] == 409                             # noch kein Bild
    # auch ein selbst gebauter Tunnel ohne Anforderung wird abgelehnt
    with pytest.raises(share.WrongCode):
        helpmode._open_ws(_target(course), f"{helpmode.API}/tunnel?s={sid}&t=ausgedachtertunnel", {})
    c.allow_view(False)
    assert _wait(lambda: _status(t)["state"] == helpmode.DENIED)
    assert _view_ws(t)[0] in (403, 409)
    assert m.vnc.received == []                              # der Agent-PC wurde nie verbunden


def test_view_then_control_needs_second_consent(course):
    c, m, calls = _participant(course)
    url = course.helpdesk.view_url(c.session_id)
    assert _wait(lambda: calls["view"] == 1)
    c.allow_view(True)
    t = _teacher(course, url)
    assert _wait(lambda: _status(t)["view"])
    st, ws = _view_ws(t)
    assert st == 101
    assert ws.recv() == (websocket.OP_BINARY, b"RFB 003.008\n")      # Bild kommt durch den Tunnel
    assert _wait(lambda: c.state == "sieht zu")
    ws.send(b"RFB 003.008\n\x01\x00" + rfb.update_request(False, 0, 0, 800, 600)
            + rfb.key_event(True, 0x61) + rfb.pointer_event(1, 10, 10) + rfb.cut_text(b"geheim"))
    assert _wait(lambda: m.vnc.received and len(m.vnc.received[0]) >= 24)
    time.sleep(0.3)
    got = bytes(m.vnc.received[0])
    assert got == b"RFB 003.008\n\x01\x01" + rfb.update_request(False, 0, 0, 800, 600)   # keine Eingaben

    # Steuerung anfragen – ohne zweite Zustimmung geht weiterhin nichts durch
    assert t.request("POST", "/bonys/v1/help/control", {"s": t.sid})[0] == 200
    assert _wait(lambda: calls["control"] == 1)
    ws.send(rfb.key_event(True, 0x62))
    time.sleep(0.3)
    assert bytes(m.vnc.received[0]) == got
    c.allow_control(True)
    assert _wait(lambda: _status(t)["control"] and c.state == "steuert")
    ws.send(rfb.key_event(True, 0x63) + rfb.cut_text(b"nie"))
    assert _wait(lambda: bytes(m.vnc.received[0]).endswith(rfb.key_event(True, 0x63)))
    # zurück auf „nur ansehen“ – sofort keine Eingaben mehr
    c.view_only()
    ws.send(rfb.key_event(True, 0x64))
    time.sleep(0.3)
    assert bytes(m.vnc.received[0]).endswith(rfb.key_event(True, 0x63)) and b"nie" not in bytes(m.vnc.received[0])
    assert _wait(lambda: _status(t)["control"] is False)


def test_participant_end_disconnects_immediately(course, tmp_path):
    c, m, calls = _participant(course)
    url = course.helpdesk.view_url(c.session_id)
    _wait(lambda: calls["view"] == 1)
    c.allow_view(True)
    t = _teacher(course, url)
    _wait(lambda: _status(t)["view"])
    _st, ws = _view_ws(t)
    ws.recv()
    t0 = time.monotonic()
    c.end()
    with pytest.raises(websocket.WebSocketClosed):
        while True:
            ws.recv()
    assert time.monotonic() - t0 < 1.5
    assert _wait(lambda: _status(t)["state"] == helpmode.ENDED)
    assert _view_ws(t)[0] == 409               # kein Bild mehr ohne neue Zustimmung
    log = helpmode.log_file().read_text("utf-8")
    for entry in ("Ansehen erlaubt", "Kursleiter sieht zu", "Beendet (Teilnehmer)"):
        assert entry in log
    assert "RFB" not in log


def test_teacher_end_and_course_stop(course):
    c, _m, calls = _participant(course)
    url = course.helpdesk.view_url(c.session_id)
    _wait(lambda: calls["view"] == 1)
    c.allow_view(True)
    _wait(lambda: course.helpdesk.session_list()[0].view_allowed)
    course.helpdesk.end_view(c.session_id)
    assert _wait(lambda: not c.view_allowed)
    assert url
    course.stop()
    assert _wait(lambda: calls["closed"])


def test_teacher_view_only_from_this_computer(course):
    h = SimpleNamespace(client_address=("192.168.1.20", 5000), sent=[])
    h._json = lambda status, data, extra=None: h.sent.append(status)
    assert course.helpdesk._local(h) is False and h.sent == [403]
    h.client_address = ("127.0.0.1", 5000)
    assert course.helpdesk._local(h) is True


def test_presentation_and_help_share_one_server(course):
    fake = FakeVNC()
    viewer = Client(course)
    assert viewer.join(course.code)[0] == 200
    assert json.loads(viewer.request("GET", "/bonys/v1/present/status")[2])["state"] == "idle"
    assert viewer.ws()[0] == 409
    course.set_screen("kurs-pc", fake.connect)
    st, ws = viewer.ws()
    assert st == 101 and ws.recv()[1] == b"RFB 003.008\n"
    course.keep_running = True
    course.is_alive = lambda: False                  # Agent-PC aus → Vorführung endet, Hilfe-Schalter läuft weiter
    with pytest.raises(websocket.WebSocketClosed) as e:
        while True:
            ws.recv()
    assert e.value.code == present.CLOSE_IDLE and not course.stopped.is_set()
