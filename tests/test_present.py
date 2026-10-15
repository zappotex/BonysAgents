# SPDX-License-Identifier: GPL-3.0-or-later
"""Live-Vorführung: RFB-Filter (Zuschauer können nichts eingeben), WebSocket-Rahmen, Server mit Code,
Ratenbegrenzung, Pause, Entfernen, Ende – gegen einen nachgebauten VNC-Server (echte RFB-Nachrichten)."""

import json
import socket
import ssl
import struct
import threading
import time
from pathlib import Path

import pytest

from bonys_agents import qemu, rfb, share, websocket
from bonys_agents.trainer import present

pytestmark = pytest.mark.kursleiter

CLIPBOARD_EXT = struct.unpack("!i", struct.pack("!I", 0xC0A1E5CE))[0]


def _client_hello() -> bytes:
    """Was noVNC nach dem Handshake schickt – und was ein Zuschauer zu tippen/klicken versucht."""
    return (b"RFB 003.008\n" + b"\x01" + b"\x00"
            + rfb.set_encodings([7, 16, 0, -32 + 9, -256 + 0, -223, -258, -309, -312, -313, CLIPBOARD_EXT, -239])
            + rfb.update_request(False, 0, 0, 1280, 800)
            + rfb.key_event(True, 0x61) + rfb.key_event(False, 0x61)
            + rfb.pointer_event(1, 100, 100) + rfb.pointer_event(0, 100, 100)
            + rfb.cut_text(b"geheim")
            + struct.pack("!BxBB", rfb.XVP, 1, 2)                           # XVP: Neustart
            + struct.pack("!BBHII", rfb.QEMU_MSG, 0, 1, 0x61, 30)          # QEMU: erweiterte Taste
            + struct.pack("!BBH", rfb.QEMU_MSG, 1, 0)                       # QEMU: Ton an
            + rfb.update_request(True, 0, 0, 1280, 800))


def _messages(data: bytes) -> list[bytes]:
    """Datenstrom an QEMU (nach dem Handshake) wieder in Nachrichten zerlegen – für die Prüfung."""
    out, pos = [], 0
    while pos < len(data):
        t = data[pos]
        if t == rfb.SET_ENCODINGS:
            n = struct.unpack("!H", data[pos + 2:pos + 4])[0]
            size = 4 + 4 * n
        else:
            size = {rfb.SET_PIXEL_FORMAT: 20, rfb.FB_UPDATE_REQUEST: 10, rfb.KEY_EVENT: 8, rfb.POINTER_EVENT: 6}[t]
        out.append(data[pos:pos + size])
        pos += size
    return out


# ---------------------------------------------------------------- RFB-Filter
@pytest.mark.parametrize("step", [1, 3, 1000])
def test_filter_drops_all_input_from_viewers(step):
    f = rfb.ClientFilter(quality="medium")
    data = _client_hello()
    items = []
    for i in range(0, len(data), step):     # auch byteweise – Nachrichten kommen zerstückelt an
        items += f.feed(data[i:i + step])
    raw = b"".join(b for _k, b in items)
    assert raw.startswith(b"RFB 003.008\n\x01\x01")  # ClientInit immer „geteilt“
    msgs = _messages(raw[14:])
    assert [m[0] for m in msgs] == [rfb.SET_ENCODINGS, rfb.FB_UPDATE_REQUEST, rfb.FB_UPDATE_REQUEST]
    encs = [e for (e,) in struct.iter_unpack("!i", msgs[0][4:])]
    assert CLIPBOARD_EXT not in encs and -258 not in encs and -309 not in encs and -313 not in encs
    assert encs[:3] == [7, 16, 0] and -223 in encs and -239 in encs
    assert set(encs) & set(rfb.JPEG_QUALITY) == {-32 + rfb.QUALITY["medium"][0]}   # Qualität vom Proxy
    assert set(encs) & set(rfb.COMPRESS_LEVEL) == {-256 + rfb.QUALITY["medium"][1]}
    assert [k for k, _b in items].count("update") == 2
    assert f.dropped_input == 5 and f.dropped == 8   # 2 Tasten, 2 Maus, 1 QEMU-Taste + Zwischenablage, XVP, Ton


def test_filter_passes_input_only_while_allowed_and_never_clipboard():
    allowed = {"on": False}
    f = rfb.ClientFilter(allow_input=lambda: allowed["on"])
    f.feed(b"RFB 003.008\n\x01\x01")
    assert f.feed(rfb.key_event(True, 0x61)) == []
    allowed["on"] = True
    assert f.feed(rfb.key_event(True, 0x61) + rfb.pointer_event(1, 5, 5)) == [
        ("pass", rfb.key_event(True, 0x61)), ("pass", rfb.pointer_event(1, 5, 5))]
    assert f.feed(rfb.cut_text(b"x" * 100)) == []     # Zwischenablage nie
    allowed["on"] = False
    assert f.feed(rfb.pointer_event(1, 5, 5)) == []


def test_filter_without_quality_keeps_client_levels():
    f = rfb.ClientFilter()
    f.feed(b"RFB 003.008\n\x01\x01")
    (_k, raw), = f.feed(rfb.set_encodings([7, -32 + 6, -256 + 2, CLIPBOARD_EXT]))
    assert [e for (e,) in struct.iter_unpack("!i", raw[4:])] == [7, -26, -254]


@pytest.mark.parametrize("bad", [b"GET / HTTP/1.1\r\n", b"RFB 004.000\n"])
def test_filter_rejects_non_vnc(bad):
    with pytest.raises(rfb.ProtocolError):
        rfb.ClientFilter().feed(bad)


def test_filter_rejects_other_security_and_unknown_messages():
    with pytest.raises(rfb.ProtocolError):
        rfb.ClientFilter().feed(b"RFB 003.008\n\x02")          # VNC-Passwort o. Ä. – nicht erlaubt
    f = rfb.ClientFilter()
    f.feed(b"RFB 003.008\n\x01\x01")
    with pytest.raises(rfb.ProtocolError):
        f.feed(b"\x96" + b"\0" * 9)                              # EnableContinuousUpdates – Länge „unbekannt“
    f = rfb.ClientFilter()
    f.feed(b"RFB 003.008\n\x01\x01")
    with pytest.raises(rfb.ProtocolError):
        f.feed(struct.pack("!BxxxI", rfb.CLIENT_CUT_TEXT, 50 * 1024 * 1024))


def test_filter_rfb_33_has_no_security_choice():
    f = rfb.ClientFilter()
    assert f.feed(b"RFB 003.003\n\x00") == [("pass", b"RFB 003.003\n"), ("pass", b"\x01")]


# ---------------------------------------------------------------- WebSocket
def test_websocket_frames_roundtrip_masked_and_fragmented():
    p = websocket.FrameParser(expect_masked=True)
    big = bytes(range(256)) * 300
    data = websocket.encode_frame(websocket.OP_BINARY, big, mask=True) + websocket.encode_frame(
        websocket.OP_PING, b"hi", mask=True)
    # zwei Fragmente einer Textnachricht
    data += bytes([0x01, 0x80 | 3]) + b"\0\0\0\0" + b"abc" + bytes([0x80, 0x80 | 2]) + b"\0\0\0\0" + b"de"
    out = []
    for i in range(0, len(data), 7):
        out += p.feed(data[i:i + 7])
    assert out == [(websocket.OP_BINARY, big), (websocket.OP_PING, b"hi"), (websocket.OP_TEXT, b"abcde")]
    with pytest.raises(websocket.WebSocketClosed):
        websocket.FrameParser(expect_masked=True).feed(websocket.encode_frame(websocket.OP_BINARY, b"x"))
    with pytest.raises(websocket.WebSocketClosed):
        websocket.FrameParser(max_payload=10).feed(websocket.encode_frame(websocket.OP_BINARY, b"x" * 11, mask=True))
    assert websocket.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="  # Beispiel aus RFC 6455


# ---------------------------------------------------------------- QEMU: VNC nur lokal
def test_vnc_only_local_in_qemu_command(tmp_path):
    spec = qemu.LaunchSpec(qemu_bin=Path("qemu"), arch="x86_64", accel="kvm", name="x", cpus=2, ram_mb=2048,
                           disk=tmp_path / "d.qcow2", qmp_port=1, ssh_port=2, serial_log=tmp_path / "s",
                           pidfile=tmp_path / "p", vnc="unix:/run/user/1000/bonys-agents-1000/ab,c.vnc")
    cmd = qemu.build_command(spec)
    sock = str(Path("/run/user/1000/bonys-agents-1000/ab,,c.vnc"))   # unter Windows mit „\\“ – dort gilt 127.0.0.1
    assert cmd[cmd.index("-vnc") + 1] == f"unix:{sock},share=force-shared,lossy=on"
    assert qemu.vnc_option("127.0.0.1:3") == "127.0.0.1:3,share=force-shared,lossy=on"
    for bad in ("0.0.0.0:0", ":0", "192.168.1.2:1", "127.0.0.1:0,password=off"):
        with pytest.raises(ValueError):
            qemu.vnc_option(bad)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or not hasattr(__import__("os"), "getuid"), reason="Unix")
def test_vnc_socket_path_private(tmp_path, monkeypatch):
    import os

    from bonys_agents import vm

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    p = vm.vnc_socket_path(tmp_path / "Agent PC")
    assert p.parent.stat().st_mode & 0o777 == 0o700 and p.parent.stat().st_uid == os.getuid()
    assert len(p.relative_to(tmp_path).as_posix()) < 40 and p != vm.vnc_socket_path(tmp_path / "anderer")


# ---------------------------------------------------------------- Server
class FakeVNC:
    """Nachgebauter QEMU-VNC-Socket: schickt die Begrüßung, merkt sich alles, was beim „Agent-PC“ ankommt."""

    def __init__(self):
        self.received: list[bytearray] = []
        self.ends: list[socket.socket] = []

    def connect(self) -> socket.socket:
        ours, theirs = socket.socketpair()
        buf = bytearray()
        self.received.append(buf)
        self.ends.append(ours)

        def run():
            ours.sendall(b"RFB 003.008\n")
            while True:
                try:
                    data = ours.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                buf.extend(data)
        threading.Thread(target=run, daemon=True).start()
        return theirs


def _novnc(tmp_path: Path) -> Path:
    d = tmp_path / "novnc"
    (d / "core").mkdir(parents=True, exist_ok=True)
    (d / "core" / "rfb.js").write_text("export default class RFB {}")
    (tmp_path / "geheim.js").write_text("nein")
    return d


@pytest.fixture
def pres(tmp_path):
    fake = FakeVNC()
    p = present.Presentation("kurs-pc", fake.connect, port=0, bind="127.0.0.1", advertise=False,
                             novnc=_novnc(tmp_path), quality="high")
    p.fake = fake
    p.start()
    yield p
    p.stop()


class Client:
    """HTTPS wie ein Browser: Origin, Cookie; danach WebSocket über denselben Socket."""

    def __init__(self, p, origin: str | None = None):
        self.p = p
        self.cookie = ""
        self.origin = origin if origin is not None else f"https://127.0.0.1:{p.port}"

    def _open(self):
        raw = socket.create_connection(("127.0.0.1", self.p.port), timeout=5)
        s = share.client_context().wrap_socket(raw)
        assert __import__("hashlib").sha256(s.getpeercert(True)).hexdigest() == self.p.fingerprint
        return s

    def request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        s = self._open()
        data = json.dumps(body).encode() if body is not None else b""
        h = {"Host": f"127.0.0.1:{self.p.port}", "Content-Length": str(len(data)), "Connection": "close"}
        if self.origin:
            h["Origin"] = self.origin
        if self.cookie:
            h["Cookie"] = self.cookie
        if body is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        s.sendall(f"{method} {path} HTTP/1.1\r\n".encode() + "".join(f"{k}: {v}\r\n" for k, v in h.items()).encode()
                  + b"\r\n" + data)
        f = s.makefile("rb")
        status = int(f.readline().split()[1])
        head = {}
        while (line := f.readline().decode().strip()):
            k, v = line.split(":", 1)
            head[k.strip().lower()] = v.strip()
        if status == 101:
            return status, head, (s, f)
        n = int(head.get("content-length", "0"))
        payload = f.read(n)
        s.close()
        if "set-cookie" in head:
            self.cookie = head["set-cookie"].split(";")[0]
        return status, head, payload

    def join(self, code: str, name: str = "Alex"):
        st, head, body = self.request("POST", "/bonys/v1/present/join", {"name": name, "code": code})
        return st, json.loads(body or b"{}")

    def ws(self):
        st, head, conn = self.request("GET", "/bonys/v1/present/ws", headers={
            "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": websocket.new_key(),
            "Sec-WebSocket-Version": "13", "Sec-WebSocket-Protocol": "binary"})
        if st != 101:
            return st, None
        s, f = conn
        assert head["sec-websocket-protocol"] == "binary"
        return st, websocket.Connection(f, s.makefile("wb"), client=True)


def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_join_page_and_wrong_code_rate_limited(pres):
    c = Client(pres)
    st, head, body = c.request("GET", "/")
    assert st == 200 and b"Vorf" in body and "default-src 'self'" in head["content-security-policy"]
    for _ in range(share.MAX_FAILS_PER_ADDR):
        assert c.join("0000-AAAA")[0] == 403
    st, data = c.join(pres.code)          # richtiger Code – aber jetzt gesperrt
    assert st == 429 and not c.cookie
    pres.fails.clear()
    assert c.join(pres.code.lower())[0] == 200 and c.cookie.startswith(present.COOKIE + "=")


def test_nothing_without_code_or_from_foreign_page(pres, tmp_path):
    c = Client(pres)
    assert c.request("GET", "/view")[0] == 303
    assert c.request("GET", "/novnc/core/rfb.js")[0] == 403
    assert c.ws()[0] == 403
    assert c.request("GET", "/bonys/v1/present/status")[0] == 403
    evil = Client(pres, origin="https://boese.example")
    assert evil.join(pres.code)[0] == 403 and not evil.cookie
    c.join(pres.code)
    assert c.request("GET", "/novnc/core/rfb.js")[0] == 200
    for path in ("/novnc/../geheim.js", "/novnc/core/../../geheim.js", "/novnc/core%2F..%2F..%2Fgeheim.js",
                 "/assets/../present.py", "/novnc/vendor/x.txt"):
        assert c.request("GET", path)[0] == 404
    evil.cookie = c.cookie                 # gestohlener Cookie hilft einer fremden Seite nicht
    assert evil.ws()[0] == 403
    assert c.request("PUT", "/")[0] == 405


def test_viewer_input_never_reaches_agent_pc(pres):
    c = Client(pres)
    c.join(pres.code)
    st, ws = c.ws()
    assert st == 101
    assert ws.recv() == (websocket.OP_BINARY, b"RFB 003.008\n")      # Bild-Richtung unverändert
    ws.send(_client_hello())
    assert _wait(lambda: len(pres.fake.received) == 1 and len(_messages(bytes(pres.fake.received[0][14:]))) >= 2)
    time.sleep(0.3)
    got = bytes(pres.fake.received[0])
    assert got.startswith(b"RFB 003.008\n\x01\x01")
    msgs = _messages(got[14:])
    kinds = [m[0] for m in msgs]
    assert rfb.KEY_EVENT not in kinds and rfb.POINTER_EVENT not in kinds and b"geheim" not in got
    # Anfragen kurz hintereinander werden zusammengefasst – die vollständige bleibt vollständig
    assert kinds[0] == rfb.SET_ENCODINGS and set(kinds[1:]) == {rfb.FB_UPDATE_REQUEST}
    assert msgs[1] == rfb.update_request(False, 0, 0, 1280, 800)
    v = pres.viewer_list()[0]
    assert v.name == "Alex" and v.connected
    ws.close()
    assert _wait(lambda: pres.viewer_list()[0].dropped_input == 5)


def test_update_requests_limited_to_frame_rate(pres):
    pres.quality = "low"        # 5 Bilder/s
    c = Client(pres)
    c.join(pres.code)
    _st, ws = c.ws()
    ws.recv()
    ws.send(b"RFB 003.008\n\x01\x01")
    t0 = time.monotonic()
    for _ in range(40):
        ws.send(rfb.update_request(True, 0, 0, 10, 10))
        time.sleep(0.02)
    time.sleep(0.4)
    n = bytes(pres.fake.received[0][14:]).count(rfb.update_request(True, 0, 0, 10, 10))
    elapsed = time.monotonic() - t0
    assert 1 <= n <= elapsed * 5 + 2


def test_frame_rate_drops_with_many_viewers(pres):
    base = rfb.QUALITY["high"][2]
    assert pres.fps() == base
    with pres.lock:
        for i in range(24):
            pres.viewers[str(i)] = present.Viewer(id=str(i), token_hash=str(i), name=f"v{i}", address="10.0.0.1")
    assert pres.fps() == pytest.approx(base * present.FULL_FPS_VIEWERS / 24)
    pres._adjust_cpu(95)
    assert pres.fps() < base * present.FULL_FPS_VIEWERS / 24


def test_pause_disconnects_and_blocks_picture(pres):
    c = Client(pres)
    c.join(pres.code)
    _st, ws = c.ws()
    ws.recv()
    pres.set_paused(True)
    with pytest.raises(websocket.WebSocketClosed) as e:
        while True:
            ws.recv()
    assert e.value.code == present.CLOSE_PAUSED
    assert c.ws()[0] == 409                       # während der Pause gar kein Bild
    st, _h, body = c.request("GET", "/bonys/v1/present/status")
    assert json.loads(body)["state"] == "paused"
    pres.set_paused(False)
    assert c.ws()[0] == 101


def test_remove_viewer(pres):
    c = Client(pres)
    c.join(pres.code, "Störer")
    _st, ws = c.ws()
    ws.recv()
    v = pres.viewer_list()[0]
    pres.remove_viewer(v.id)
    with pytest.raises(websocket.WebSocketClosed) as e:
        while True:
            ws.recv()
    assert e.value.code == present.CLOSE_REMOVED
    assert json.loads(c.request("GET", "/bonys/v1/present/status")[2])["state"] == "removed"
    assert c.join(pres.code)[0] == 403                       # gleiche Adresse eine Weile gesperrt
    assert pres.viewer_count() == 0


def test_max_viewers(tmp_path):
    p = present.Presentation("x", FakeVNC().connect, port=0, bind="127.0.0.1", advertise=False,
                             novnc=_novnc(tmp_path), max_viewers=2)
    p.start()
    try:
        assert Client(p).join(p.code)[0] == 200
        assert Client(p).join(p.code)[0] == 200
        assert Client(p).join(p.code)[0] == 503
    finally:
        p.stop()


def test_ends_when_agent_pc_stops_or_time_runs_out(tmp_path):
    alive = {"on": True}
    p = present.Presentation("x", FakeVNC().connect, is_alive=lambda: alive["on"], port=0, bind="127.0.0.1",
                             advertise=False, novnc=_novnc(tmp_path))
    p.start()
    c = Client(p)
    c.join(p.code)
    _st, ws = c.ws()
    ws.recv()
    alive["on"] = False
    assert p.stopped.wait(5) and "ausgeschaltet" in p.stop_reason
    with pytest.raises(websocket.WebSocketClosed) as e:
        while True:
            ws.recv()
    assert e.value.code == present.CLOSE_ENDED
    q = present.Presentation("y", FakeVNC().connect, port=0, bind="127.0.0.1", advertise=False,
                             novnc=_novnc(tmp_path))
    q.start()
    q.deadline = time.monotonic()
    assert q.stopped.wait(3) and "Zeit" in q.stop_reason


def test_browser_certificate_is_ecdsa_with_addresses(pres):
    raw = socket.create_connection(("127.0.0.1", pres.port), timeout=5)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cadata=pres.cert)       # Signatur ist gültig
    ctx.check_hostname = True
    with ctx.wrap_socket(raw, server_hostname="127.0.0.1") as s:   # 127.0.0.1 steht im subjectAltName
        assert s.version() in ("TLSv1.2", "TLSv1.3")
    url = pres.url()
    assert url.startswith("https://") and f"#code={pres.code}" in url


def test_missing_novnc_and_vm_without_vnc(tmp_path, monkeypatch):
    monkeypatch.setattr(present, "novnc_dir", lambda: None)
    with pytest.raises(present.PresentError):
        present.Presentation("x", FakeVNC().connect)

    class OldVM:
        name = "alt"

        def is_running(self):
            return True

        def vnc_available(self):
            return False
    with pytest.raises(present.NeedsRestart):
        present.for_vm(OldVM())


def test_cli_parses_present():
    from bonys_agents import cli

    args = cli.build_parser().parse_args(["present", "kurs-pc", "--port", "5000", "--timeout", "30",
                                          "--max-viewers", "12", "--quality", "low"])
    assert (args.name, args.port, args.timeout, args.max_viewers, args.quality) == ("kurs-pc", 5000, 30, 12, "low")


def test_cli_join_shows_browser_address_of_presentation(pres, capsys):
    from bonys_agents import cli

    assert cli.main(["join", f"127.0.0.1:{pres.port}", pres.code, "--fingerprint", pres.fingerprint]) == 0
    out = capsys.readouterr().out
    assert "Vorführung „kurs-pc“" in out and f"https://127.0.0.1:{pres.port}/#code={pres.code}" in out
