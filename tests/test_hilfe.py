# SPDX-License-Identifier: GPL-3.0-or-later
"""Hilfe-Funktion über das Bony-Netz (Aufgabe 06): hilfe, vncauth, der Betrachter des Kursleiters und die Fenster.

Das Startskript für x11vnc läuft hier wirklich (bash mit falschen Programmen statt tailscale, systemd-run usw.),
die Brücke für noVNC mit einem eigenen VNC-Server auf 127.0.0.1. Den echten Agent-PC mit x11vnc prüft der Test in
docs/bony-netz.md (Abschnitt Aufgabe 06).
"""

import os
import re
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_kurse import _als, _anmelden, _geraet, _zweite_instanz, qapp  # noqa: F401 – Fixture
from test_netz import FakeZentrale

from bonys_agents import hilfe, kurse, vncauth, websocket

ROOT = Path(__file__).resolve().parents[1]
SEITE = ROOT / "src" / "bonys_agents" / "resources" / "kursraum"
BETRACHTER = ROOT / "src" / "bonys_agents" / "trainer" / "resources" / "hilfe"


@pytest.fixture(autouse=True)
def _fenster_aufraeumen():
    """Nach jedem Test: Hintergrund-Aufrufe abwarten, offene Fenster schließen und von Qt löschen lassen."""
    yield
    import sys

    if "PySide6.QtWidgets" in sys.modules:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            _aufraeumen(app)


@pytest.fixture
def zentrale():
    z = FakeZentrale()
    yield z
    z.close()


@pytest.fixture
def laufender_kurs(zentrale):
    leiter = _anmelden(zentrale)
    zentrale.instanzen[leiter.token]["ist_kursleiter"] = True
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    anna = _zweite_instanz(zentrale)
    zentrale.geraete = [_geraet("g1", "pc-a", ip="100.64.0.7")]
    _als(anna)
    kurse.kurs_beitreten(kurs.code, "g1", "Anna")
    _als(leiter)
    kurse.status_setzen(kurs.kurs_id, kurse.LAEUFT)
    return leiter, anna, kurs


# ---------------------------------------------------------------- VNC-Passwörter (DES)
def test_des_und_vnc_passwoerter():
    # FIPS-Beispiel und Werte, die openssl (des-ecb) für dieselben Schlüssel liefert
    assert vncauth.des_block(bytes.fromhex("133457799BBCDFF1"), bytes.fromhex("0123456789ABCDEF")).hex() \
        == "85e813540f0ab405"
    assert vncauth.passwortdatei("password").hex() == "dbd83cfd727a1458"
    assert vncauth.antwort("geheim12", bytes(range(16))).hex() == "443b3fb6adf1941f7c9ae9be9dc6e1ad"
    assert vncauth.antwort("geheim12xyz", bytes(range(16))) == vncauth.antwort("geheim12", bytes(range(16)))
    with pytest.raises(ValueError):
        vncauth.antwort("x", b"kurz")


# ---------------------------------------------------------------- Startskript im Agent-PC
def _falsche_programme(tmp_path: Path, ip="100.64.0.7", x11vnc=True, apt_ok=True, lauscht=True) -> dict:
    bin_ = tmp_path / "bin"
    bin_.mkdir(parents=True)
    log = tmp_path / "aufrufe.log"
    programme = {
        "tailscale": f'[ "$1 $2" = "ip -4" ] && echo "{ip}"',
        "systemd-run": f'printf "%s\\n" "$*" >> {log}; cp "$(echo "$*" | sed -n "s/.*rm:\\([^ ]*\\).*/\\1/p")" '
                       f'{tmp_path}/gelesen; exit 0',
        "systemctl": f'echo "systemctl $*" >> {log}; [ "$1" = is-active ] && exit 0; exit 0',
        "ss": (f'echo "LISTEN 0 32 {ip}:5959 0.0.0.0:*"' if lauscht else "true"),
        "apt-get": f'echo "apt-get $*" >> {log}; ' + ("touch " + str(bin_ / "x11vnc") + "; chmod +x "
                                                       + str(bin_ / "x11vnc") if apt_ok else "exit 100"),
        "journalctl": "echo 'x11vnc: kaputt'",
        "python3": "exit 1",   # bonys_apt_busy: nichts belegt
        "sleep": "true",
    }
    if x11vnc:
        programme["x11vnc"] = "true"
    for name, text in programme.items():
        p = bin_ / name
        p.write_text("#!/bin/bash\n" + text + "\n")
        p.chmod(0o755)
    return {"bin": bin_, "log": log}


NUR_POSIX = pytest.mark.skipif(sys.platform.startswith("win"),
                               reason="nur POSIX (bash unter Windows ist der WSL-Platzhalter)")


def _ausfuehren(tmp_path, skript, fp):
    env = {"PATH": f"{fp['bin']}:/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
    return subprocess.run(["bash", "-s"], input=skript, capture_output=True, text=True, env=env, timeout=30)


@NUR_POSIX
def test_startskript_lauscht_nur_im_bony_netz(tmp_path):
    fp = _falsche_programme(tmp_path)
    ordner = tmp_path / "run"
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.ANSEHEN, "Ab3dEf7h", ordner=str(ordner)), fp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1] == "BONYS_HILFE 100.64.0.7"
    aufruf = next(z for z in fp["log"].read_text().splitlines() if "x11vnc" in z and "--unit" in z)
    assert "--unit=bonys-hilfe" in aufruf and "RuntimeMaxSec=1800" in aufruf
    teile = aufruf.split()
    x = teile[teile.index("/usr/bin/x11vnc"):]
    assert x[x.index("-listen") + 1] == "100.64.0.7" and "-noipv6" in x
    assert "-once" in x and x[x.index("-timeout") + 1] == "120" and "-viewonly" in x
    assert x[x.index("-passwdfile") + 1] == f"rm:{ordner}/passwort"
    assert "Ab3dEf7h" not in aufruf               # nie auf der Kommandozeile
    assert (tmp_path / "gelesen").read_text() == "Ab3dEf7h\n"
    assert stat.S_IMODE(ordner.stat().st_mode) == 0o700


@NUR_POSIX
def test_startskript_bedienen_ohne_viewonly(tmp_path):
    fp = _falsche_programme(tmp_path)
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.BEDIENEN, "x1", ordner=str(tmp_path / "run")), fp)
    assert r.returncode == 0
    assert "-viewonly" not in fp["log"].read_text()


@NUR_POSIX
def test_startskript_fehler(tmp_path):
    fp = _falsche_programme(tmp_path, ip="")
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.ANSEHEN, "x1", ordner=str(tmp_path / "a")), fp)
    assert r.returncode == hilfe.RC_KEIN_NETZ
    fp = _falsche_programme(tmp_path / "b", x11vnc=False, apt_ok=False)
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.ANSEHEN, "x1", ordner=str(tmp_path / "b" / "r")), fp)
    assert r.returncode == hilfe.RC_INSTALLATION
    fp = _falsche_programme(tmp_path / "c", lauscht=False)
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.ANSEHEN, "x1", ordner=str(tmp_path / "c" / "r")), fp)
    assert r.returncode == hilfe.RC_START and "kaputt" in r.stdout
    assert not (tmp_path / "c" / "r").exists()     # Passwortdatei weg


@NUR_POSIX
def test_startskript_installiert_x11vnc_bei_bedarf(tmp_path):
    fp = _falsche_programme(tmp_path, x11vnc=False)
    r = _ausfuehren(tmp_path, hilfe.start_skript(hilfe.ANSEHEN, "x1", ordner=str(tmp_path / "r")), fp)
    assert r.returncode == 0, r.stdout
    assert "apt-get install -y --no-install-recommends x11vnc" in fp["log"].read_text()


def test_startskript_prueft_eingaben():
    with pytest.raises(ValueError):
        hilfe.start_skript("alles", "abc")
    for pw in ("", "neun12345", "a b", "a'b"):
        with pytest.raises(ValueError):
            hilfe.start_skript(hilfe.ANSEHEN, pw)
    assert re.fullmatch(r"[A-Za-z0-9]{8}", hilfe.passwort())
    assert hilfe.passwort() != hilfe.passwort()


def test_neue_agent_pcs_bringen_x11vnc_mit():
    from bonys_agents import desktops

    assert "x11vnc" in desktops.COMMON_PACKAGES.split()


# ---------------------------------------------------------------- starten/beenden mit einem falschen Agent-PC
class FalscherPC:
    def __init__(self, ausgabe="BONYS_HILFE 100.64.0.7\n", fehler=None, laeuft=True):
        self.name = "Agent 1"
        self.ausgabe, self.fehler, self.laeuft = ausgabe, fehler, laeuft
        self.skripte = []
        self.config = type("C", (), {"first_boot_pending": False, "netz_name": "pc-a"})()

    def is_running(self):
        return self.laeuft

    def progress(self):
        return type("P", (), {"ready": True})()

    def guest_run(self, skript, timeout=120, via_stdin=False, **_kw):
        self.skripte.append((skript, via_stdin))
        if self.fehler:
            raise self.fehler
        if "is-active" in skript and "systemd-run" not in skript:
            return "aktiv\n"
        return self.ausgabe


def test_starten_und_beenden():
    pc = FalscherPC()
    f = hilfe.starten(pc, hilfe.BEDIENEN)
    assert (f.ip, f.port, f.modus) == ("100.64.0.7", hilfe.PORT, hilfe.BEDIENEN)
    skript, stdin = pc.skripte[0]
    assert stdin and f.passwort in skript         # Passwort nur über die Standardeingabe
    assert f.passwort not in repr(f)
    assert hilfe.aktiv(pc) is True
    hilfe.beenden(pc)
    assert "systemctl stop bonys-hilfe.service" in pc.skripte[-1][0]
    assert f.nachricht("h1", "Agent 1") == {"id": "h1", "ip": "100.64.0.7", "port": hilfe.PORT,
                                             "modus": hilfe.BEDIENEN, "passwort": f.passwort, "pc": "Agent 1"}


def test_starten_fehlertexte():
    from bonys_agents import vm

    with pytest.raises(hilfe.HilfeFehler, match="muss laufen"):
        hilfe.starten(FalscherPC(laeuft=False), hilfe.ANSEHEN)
    with pytest.raises(hilfe.HilfeFehler, match="Gast-Agent"):
        hilfe.starten(FalscherPC(fehler=vm.NeedsPassword("x")), hilfe.ANSEHEN)
    with pytest.raises(hilfe.HilfeFehler, match="nicht mit dem Bony-Netz"):
        hilfe.starten(FalscherPC(fehler=RuntimeError("Befehl im Agent-PC fehlgeschlagen (Code 3): x")), "ansehen")
    with pytest.raises(hilfe.HilfeFehler, match="nicht installieren"):
        hilfe.starten(FalscherPC(fehler=RuntimeError("Befehl im Agent-PC fehlgeschlagen (Code 4): x")), "ansehen")
    pc = FalscherPC(ausgabe="BONYS_HILFE 192.168.1.5\n")   # nie eine Adresse außerhalb des Bony-Netzes
    with pytest.raises(hilfe.HilfeFehler, match="nicht gestartet"):
        hilfe.starten(pc, hilfe.ANSEHEN)
    assert "systemctl stop" in pc.skripte[-1][0]
    assert hilfe.aktiv(FalscherPC(laeuft=False)) is False


# ---------------------------------------------------------------- Zusage prüfen (Kursleiter)
def _zusage(**anders):
    d = {"id": "h1", "ip": "100.64.0.7", "port": 5959, "modus": "ansehen", "passwort": "Ab3dEf7h", "pc": "x"}
    d.update(anders)
    return d


def test_zusage_pruefen():
    f = hilfe.zusage_pruefen(_zusage(), "100.64.0.7")
    assert (f.ip, f.port, f.modus, f.passwort) == ("100.64.0.7", 5959, "ansehen", "Ab3dEf7h")
    assert hilfe.zusage_pruefen(_zusage(), "").ip == "100.64.0.7"   # Zentrale nennt keine Adresse
    for falsch in (_zusage(ip="192.168.0.5"), _zusage(ip="100.128.0.1"), _zusage(ip="::1"), _zusage(ip=7),
                   _zusage(port=22), _zusage(port=True), _zusage(port="5959"), _zusage(modus="alles"),
                   _zusage(passwort="a b"), _zusage(passwort="123456789"), _zusage(passwort=None)):
        with pytest.raises(hilfe.HilfeFehler):
            hilfe.zusage_pruefen(falsch)
    with pytest.raises(hilfe.HilfeFehler, match="gehört nicht"):
        hilfe.zusage_pruefen(_zusage(ip="100.64.0.9"), "100.64.0.7")


def test_teilnehmer_ip_nur_wenn_der_kurs_laeuft(zentrale, laufender_kurs):
    leiter, anna, kurs = laufender_kurs
    ip = hilfe.teilnehmer_ip(kurs.kurs_id, anna.instanz_id)
    assert ip == next(t.geraet_ip for t in kurse.geleiteter_kurs(kurs.kurs_id).teilnehmer)
    with pytest.raises(hilfe.HilfeFehler, match="nicht"):
        hilfe.teilnehmer_ip(kurs.kurs_id, "i-unbekannt")
    kurse.status_setzen(kurs.kurs_id, kurse.PAUSIERT)
    with pytest.raises(hilfe.HilfeFehler, match="läuft nicht"):
        hilfe.teilnehmer_ip(kurs.kurs_id, anna.instanz_id)


def test_agent_pc_des_kurses(zentrale, laufender_kurs, monkeypatch):
    from bonys_agents import vm

    leiter, anna, kurs = laufender_kurs
    _als(anna)
    pc, anderer = FalscherPC(), FalscherPC()
    anderer.config.netz_name = "pc-b"
    monkeypatch.setattr(vm, "list_vms", lambda: [anderer, pc])
    assert hilfe.agent_pc(kurs.kurs_id) is pc
    assert hilfe.kurs_laeuft(kurs.kurs_id)
    monkeypatch.setattr(vm, "list_vms", lambda: [anderer])
    with pytest.raises(hilfe.HilfeFehler, match="nicht auf diesem Rechner"):
        hilfe.agent_pc(kurs.kurs_id)
    with pytest.raises(hilfe.HilfeFehler, match="nicht"):
        hilfe.agent_pc("k-unbekannt")


# ---------------------------------------------------------------- Dieser Rechner im Bony-Netz?
def test_rechner_im_netz():
    liste = [{"name": "rechner-x", "ip": "100.64.0.3"}]
    lauf = {"BackendState": "Running", "Self": {"TailscaleIPs": ["100.64.0.3", "fd7a::3"]}}
    assert hilfe.rechner_im_netz(lauf, liste).verbunden
    r = hilfe.rechner_im_netz(None, liste)
    assert not r.verbunden and not r.installiert and "nicht installiert" in r.text
    assert "Dienst" in hilfe.rechner_im_netz({}, liste).text
    assert "aus" in hilfe.rechner_im_netz({"BackendState": "Stopped"}, liste).text
    fremd = {"BackendState": "Running", "Self": {"TailscaleIPs": ["100.101.1.1"]}}
    assert "anderen" in hilfe.rechner_im_netz(fremd, liste).text


def test_verbinden_hinweis():
    assert "Bony's VPN" in hilfe.verbinden_hinweis("linux")
    assert "Tailscale-App" in hilfe.verbinden_hinweis("win32") and "Tailscale-App" in hilfe.verbinden_hinweis("darwin")


# ---------------------------------------------------------------- Brücke noVNC ↔ x11vnc
class VncServer:
    """Kleiner RFB-Server mit „VNC Authentication“ – zählt Verbindungen, schickt nach der Anmeldung „HALLO“ und
    gibt danach alles zurück, was kommt."""

    def __init__(self, passwort="Ab3dEf7h"):
        self.passwort = passwort
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.verbindungen = 0
        self.ergebnis = []
        threading.Thread(target=self._laufen, daemon=True).start()

    def _laufen(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.verbindungen += 1
            threading.Thread(target=self._bedienen, args=(c,), daemon=True).start()

    def _lesen(self, c, n):
        d = b""
        while len(d) < n:
            t = c.recv(n - len(d))
            if not t:
                raise OSError("weg")
            d += t
        return d

    def _bedienen(self, c):
        try:
            c.sendall(b"RFB 003.008\n")
            self._lesen(c, 12)
            c.sendall(bytes([1, 2]))
            assert self._lesen(c, 1) == b"\x02"
            herausforderung = os.urandom(16)
            c.sendall(herausforderung)
            ok = self._lesen(c, 16) == vncauth.antwort(self.passwort, herausforderung)
            self.ergebnis.append(ok)
            c.sendall(b"\0\0\0\0" if ok else b"\0\0\0\1")
            if not ok:
                return
            c.sendall(b"HALLO")
            while True:
                d = c.recv(4096)
                if not d:
                    return
                c.sendall(d)
        except OSError:
            pass
        finally:
            c.close()

    def close(self):
        self.sock.close()


def _ws_verbinden(port, pfad, herkunft="kursraum://app"):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = websocket.new_key()
    s.sendall((f"GET {pfad} HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n"
               f"Origin: {herkunft}\r\n\r\n").encode())
    antwort = b""
    while b"\r\n\r\n" not in antwort:
        t = s.recv(4096)
        if not t:
            break
        antwort += t
    kopf, _, rest = antwort.partition(b"\r\n\r\n")
    return s, kopf.decode(), rest, key


def _rfb_ueber_ws(s, rest, passwort):
    """Als Betrachter (wie noVNC) über die Brücke anmelden – gibt die ersten Bytes nach der Anmeldung zurück."""
    parser = websocket.FrameParser(expect_masked=False)
    puffer = bytearray(rest and b"".join(p for _o, p in parser.feed(rest)))

    def lesen(n):
        while len(puffer) < n:
            for _op, p in parser.feed(s.recv(4096)):
                puffer.extend(p)
        d = bytes(puffer[:n])
        del puffer[:n]
        return d

    def senden(d):
        s.sendall(websocket.encode_frame(websocket.OP_BINARY, d, mask=True))

    assert lesen(12) == b"RFB 003.008\n"
    senden(b"RFB 003.008\n")
    assert lesen(2) == bytes([1, 2])
    senden(b"\x02")
    senden(vncauth.antwort(passwort, lesen(16)))
    if lesen(4) != b"\0\0\0\0":
        return None
    return lesen(5), lesen, senden


@pytest.mark.kursleiter
def test_bruecke_leitet_genau_eine_verbindung_weiter():
    from bonys_agents.trainer.hilfe_betrachter import Bruecke

    server = VncServer()
    b = Bruecke(("127.0.0.1", server.port))
    try:
        assert b.url.startswith("ws://127.0.0.1:") and len(b.pfad) > 20
        # falscher Pfad und fremde Herkunft: abgewiesen, ohne den Agent-PC zu berühren
        s, kopf, _r, _k = _ws_verbinden(b.port, "/hilfe/falsch")
        assert kopf.startswith("HTTP/1.1 403")
        s.close()
        s, kopf, _r, _k = _ws_verbinden(b.port, b.pfad, herkunft="https://boese.example")
        assert kopf.startswith("HTTP/1.1 403")
        s.close()
        assert server.verbindungen == 0
        s, kopf, rest, key = _ws_verbinden(b.port, b.pfad)
        assert kopf.startswith("HTTP/1.1 101") and websocket.accept_key(key) in kopf and "binary" in kopf
        hallo, lesen, senden = _rfb_ueber_ws(s, rest, "Ab3dEf7h")
        assert hallo == b"HALLO" and server.ergebnis == [True]
        senden(b"ECHO")
        assert lesen(4) == b"ECHO"
        # Port ist jetzt zu – keine zweite Verbindung
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", b.port), timeout=2)
        s.close()
        ende = time.monotonic() + 5
        while b.ende is None and time.monotonic() < ende:
            time.sleep(0.02)
        assert b.ende is not None
    finally:
        b.schliessen()
        server.close()


@pytest.mark.kursleiter
def test_bruecke_falsches_passwort_und_ziel_weg():
    from bonys_agents.trainer.hilfe_betrachter import Bruecke

    server = VncServer()
    b = Bruecke(("127.0.0.1", server.port))
    s, _kopf, rest, _k = _ws_verbinden(b.port, b.pfad)
    assert _rfb_ueber_ws(s, rest, "falsch") is None and server.ergebnis == [False]
    s.close()
    b.schliessen()
    server.close()
    tot = socket.create_server(("127.0.0.1", 0))
    port = tot.getsockname()[1]
    tot.close()
    b = Bruecke(("127.0.0.1", port))
    s, kopf, _r, _k = _ws_verbinden(b.port, b.pfad)
    assert kopf.startswith("HTTP/1.1 502") and b.ende == (4010, "Agent-PC nicht erreichbar")
    s.close()
    b.schliessen()


# ---------------------------------------------------------------- Rückfall TigerVNC
@pytest.mark.kursleiter
def test_tigervnc_passwort_nur_in_einer_datei(tmp_path):
    from bonys_agents.trainer import hilfe_betrachter as hb

    f = hilfe.Freigabe("100.64.0.7", 5959, hilfe.ANSEHEN, "Ab3dEf7h")
    gestartet = []

    class Proc:
        def poll(self):
            return None

        def terminate(self):
            gestartet.append("terminate")

    def popen(befehl, **kw):
        gestartet.append(befehl)
        return Proc()

    vnc = hb.TigerVNC(f, exe="/usr/bin/vncviewer", popen=popen)
    befehl = gestartet[0]
    assert "Ab3dEf7h" not in " ".join(befehl)
    assert befehl[-1] == "100.64.0.7::5959" and "-ViewOnly=1" in befehl and "-Shared=0" in befehl
    datei = Path(next(a for a in befehl if a.startswith("-PasswordFile=")).split("=", 1)[1])
    if not sys.platform.startswith("win"):   # Windows kennt keine Unix-Rechte (Datei liegt im eigenen Profil)
        assert stat.S_IMODE(datei.stat().st_mode) == 0o600
    assert datei.read_bytes() == vncauth.passwortdatei("Ab3dEf7h")
    vnc.beenden()
    assert not datei.exists() and "terminate" in gestartet
    bedienen = hb.tigervnc_befehl("vncviewer", hilfe.Freigabe("100.64.0.7", 5959, hilfe.BEDIENEN, "x"), datei)
    assert "-ViewOnly=0" in bedienen



@pytest.mark.kursleiter
def test_tigervnc_fehlt(monkeypatch):
    from bonys_agents.trainer import hilfe_betrachter as hb

    monkeypatch.setattr(hb, "tigervnc", lambda: None)
    with pytest.raises(hb.BetrachterFehler, match="TigerVNC"):
        hb.TigerVNC(hilfe.Freigabe("100.64.0.7", 5959, hilfe.ANSEHEN, "x"))


# ---------------------------------------------------------------- Seiten
def test_seiten_haben_die_hilfe_nachrichten():
    js = (SEITE / "kursraum.js").read_text("utf-8")
    for thema in ("hilfe-anfrage", "hilfe-zusage", "hilfe-absage", "hilfe-ende", "hilfe-bitte"):
        assert f"'{thema}'" in js or f"'{thema}'" in js.replace('"', "'"), thema
    # Anfragen nur vom Kursleiter annehmen, Antworten nur auf eigene offene Anfragen
    assert "thema === 'hilfe-anfrage' && istLeiter(p) && !ichLeite()" in js
    assert "if (!o || d.id !== o.id) return;" in js
    assert {"hilfe-anfrage", "hilfe-zusage", "hilfe-absage", "hilfe-bitte", "hilfe-ende"} == {
        hilfe.ANFRAGE, hilfe.ZUSAGE, hilfe.ABSAGE, hilfe.BITTE, hilfe.ENDE}
    html = (BETRACHTER / "index.html").read_text("utf-8")
    quellen = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert set(quellen) == {"hilfe.css", "/qwebchannel.js", "hilfe.js"}
    assert "connect-src ws://127.0.0.1:*" in html
    bjs = (BETRACHTER / "hilfe.js").read_text("utf-8")
    assert 'import RFB from "/novnc/core/rfb.js"' in bjs and "innerHTML" not in bjs
    assert "rfb.viewOnly = !bedienen" in bjs and "console." not in bjs


# ---------------------------------------------------------------- Fenster beim Teilnehmer
def _warten(qapp, bedingung, timeout=10.0):  # noqa: F811
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        qapp.processEvents()
        if bedingung():
            return
        time.sleep(0.01)
    raise AssertionError("Bedingung nicht erfüllt")


def _fenster(kursleiter=False):
    """Statt KursraumFenster: ein leeres Fenster, das sich merkt, was an die Seite ginge."""
    from PySide6.QtWidgets import QWidget

    class FalschesFenster(QWidget):
        def __init__(self):
            super().__init__()
            self.karte = type("K", (), {"kurs_id": "k1", "kursleiter": kursleiter})()
            self.kursname = "Hermes"
            self.an = []

        def an_seite(self, d):
            self.an.append(d)

        def gesendet(self, thema):
            return [d for d in self.an if d.get("aktion") == "senden" and d.get("thema") == thema]

    return FalschesFenster()


@pytest.fixture
def teilnehmer(qapp, datadir, monkeypatch):  # noqa: F811
    pc = FalscherPC()
    aufrufe = []
    monkeypatch.setattr(hilfe, "agent_pc", lambda kurs_id: pc)
    monkeypatch.setattr(hilfe, "starten", lambda m, modus: aufrufe.append(("start", modus)) or
                        hilfe.Freigabe("100.64.0.7", 5959, modus, "Ab3dEf7h"))
    monkeypatch.setattr(hilfe, "beenden", lambda m: aufrufe.append(("stop",)))
    monkeypatch.setattr(hilfe, "aktiv", lambda m: True)
    monkeypatch.setattr(hilfe, "kurs_laeuft", lambda k: True)
    f = _fenster()
    yield f, pc, aufrufe


def _aufraeumen(qapp):  # noqa: F811
    """Hintergrund-Aufrufe abwarten und offene Fenster (Rückfrage, Hinweis, Meldungen) schließen."""
    from bonys_agents.gui import hilfe_ui

    ende = time.monotonic() + 10
    while hilfe_ui._RUNNING and time.monotonic() < ende:
        qapp.processEvents()
        time.sleep(0.01)
    for w in qapp.topLevelWidgets():
        if type(w).__name__ in ("Zustimmung", "Hinweis", "QMessageBox", "HilfeFenster"):
            w.close()
    from PySide6.QtCore import QEvent

    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)


def _teilnehmerhilfe(f):
    from bonys_agents.gui import hilfe_ui

    th = hilfe_ui.TeilnehmerHilfe(f)
    th.uhr.setInterval(50)
    return th


def test_teilnehmer_stimmt_zu_und_beendet(qapp, teilnehmer):  # noqa: F811
    f, pc, aufrufe = teilnehmer
    th = _teilnehmerhilfe(f)
    th.anfrage({"id": "h1", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.dialog is not None)
    assert "Bony möchte deinen Agenten-PC „Agent 1“ sehen und bedienen. Erlauben?" in \
        th.dialog.findChildren(type(th.dialog.uhr_text))[0].text()
    # zweite Anfrage während der ersten: abgelehnt
    th.anfrage({"id": "h2", "identity": "i-leiter", "name": "Bony"})
    assert f.gesendet(hilfe.ABSAGE)[-1]["daten"]["id"] == "h2"
    th.dialog.ansehen.click()
    _warten(qapp, lambda: th.zustand == "aktiv")
    zusage = f.gesendet(hilfe.ZUSAGE)[0]
    assert zusage["an"] == ["i-leiter"] and zusage["daten"]["ip"] == "100.64.0.7"
    assert zusage["daten"]["modus"] == hilfe.ANSEHEN and aufrufe == [("start", hilfe.ANSEHEN)]
    assert th.hinweis is not None and th.hinweis.isVisible()
    assert th.hinweis.text.text() == "Bony sieht gerade deinen Agenten-PC „Agent 1“."
    hinweis = th.hinweis
    hinweis.knopf.click()   # „Beenden“
    _warten(qapp, lambda: ("stop",) in aufrufe)
    from shiboken6 import isValid

    assert th.zustand is None and f.gesendet(hilfe.ENDE) and not isValid(hinweis)
    assert {"aktion": "banner", "text": ""} in f.an
    from bonys_agents import helpmode

    protokoll = helpmode.log_file().read_text("utf-8")
    assert "Bony: Nur ansehen erlaubt (Bony-Netz)" in protokoll and "Hilfe beendet" in protokoll


def test_teilnehmer_ohne_antwort_abgelehnt(qapp, teilnehmer):  # noqa: F811
    f, pc, aufrufe = teilnehmer
    th = _teilnehmerhilfe(f)
    th.anfrage({"id": "h1", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.dialog is not None)
    th.dialog.rest = 1
    _warten(qapp, lambda: th.zustand is None, timeout=5)
    assert f.gesendet(hilfe.ABSAGE)[-1]["daten"] == {"id": "h1"} and not aufrufe


def test_teilnehmer_hilfe_endet_mit_kurs_und_kursraum(qapp, teilnehmer, monkeypatch):  # noqa: F811
    f, pc, aufrufe = teilnehmer
    th = _teilnehmerhilfe(f)
    th.anfrage({"id": "h1", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.dialog is not None)
    th.dialog.bedienen.click()
    _warten(qapp, lambda: th.zustand == "aktiv")
    assert "kann ihn bedienen" in th.hinweis.text.text()
    monkeypatch.setattr(hilfe, "kurs_laeuft", lambda k: False)   # Kurs pausiert
    th.kurs_zuletzt = 0.0
    _warten(qapp, lambda: th.zustand is None and ("stop",) in aufrufe)   # Stoppen läuft im Hintergrund
    # neue Anfrage, dann Kursraum verlassen, während gefragt wird
    th.anfrage({"id": "h3", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.dialog is not None)
    th.raum_getrennt()
    _warten(qapp, lambda: th.zustand is None)
    assert f.gesendet(hilfe.ABSAGE)[-1]["daten"]["id"] == "h3"


def test_teilnehmer_x11vnc_von_selbst_zu_ende(qapp, teilnehmer, monkeypatch):  # noqa: F811
    f, pc, aufrufe = teilnehmer
    th = _teilnehmerhilfe(f)
    th.anfrage({"id": "h1", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.dialog is not None)
    th.dialog.ansehen.click()
    _warten(qapp, lambda: th.zustand == "aktiv")
    monkeypatch.setattr(hilfe, "aktiv", lambda m: False)   # Kursleiter hat getrennt (-once)
    _warten(qapp, lambda: th.zustand is None)
    assert f.gesendet(hilfe.ENDE)


def test_teilnehmer_agent_pc_fehlt(qapp, teilnehmer, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QMessageBox

    f, pc, aufrufe = teilnehmer

    def fehlt(kurs_id):
        raise hilfe.HilfeFehler(hilfe.KEIN_AGENT_PC)

    monkeypatch.setattr(hilfe, "agent_pc", fehlt)
    th = _teilnehmerhilfe(f)
    th.anfrage({"id": "h1", "identity": "i-leiter", "name": "Bony"})
    _warten(qapp, lambda: th.zustand is None)
    absage = f.gesendet(hilfe.ABSAGE)[-1]["daten"]
    assert absage["id"] == "h1" and "nicht auf diesem Rechner" in absage["grund"]
    for box in qapp.topLevelWidgets():
        if isinstance(box, QMessageBox):
            box.close()


# ---------------------------------------------------------------- Kursleiter
@pytest.mark.kursleiter
def test_kursleiter_zusage_mit_falscher_adresse(qapp, datadir, monkeypatch):  # noqa: F811
    from bonys_agents.trainer.gui import hilfe_fenster

    f = _fenster(kursleiter=True)
    monkeypatch.setattr(hilfe, "teilnehmer_ip", lambda k, i: "100.64.0.7")
    geoeffnet = []
    monkeypatch.setattr(hilfe_fenster.KursleiterHilfe, "_oeffnen", lambda self, i, fr, t: geoeffnet.append((i, fr, t)))
    kl = hilfe_fenster.KursleiterHilfe(f)
    kl.zusage({"identity": "i-anna", "name": "Anna", "daten": _zusage(ip="100.64.0.99")})
    _warten(qapp, lambda: f.gesendet(hilfe.ENDE))
    assert not geoeffnet and any("gehört nicht" in d.get("text", "") for d in f.an)
    kl.zusage({"identity": "i-anna", "name": "Anna", "daten": _zusage(pc="Agent 1")})
    _warten(qapp, lambda: geoeffnet)
    assert geoeffnet[0][0] == "i-anna" and geoeffnet[0][2] == "Anna · Agent 1"


@pytest.mark.kursleiter
def test_betrachter_seiten_unter_dem_kursraum_schema():
    from bonys_agents.gui import kursraum_fenster
    from bonys_agents.trainer.gui import hilfe_fenster

    assert kursraum_fenster.ZUSATZ["hilfe"]("index.html")[1] == "text/html"
    assert kursraum_fenster.ZUSATZ["hilfe"]("../hilfe_fenster.py") is None
    assert hilfe_fenster.SEITE == "kursraum://app/hilfe/index.html"
    if hilfe_fenster.present.novnc_dir() is not None:
        assert kursraum_fenster.ZUSATZ["novnc"]("core/rfb.js")[1] == "text/javascript"
        assert kursraum_fenster.ZUSATZ["novnc"]("../../hilfe.py") is None


@pytest.mark.kursleiter
def test_kursansicht_helfen_und_netz_pruefen(qapp, datadir, zentrale, laufender_kurs, monkeypatch):  # noqa: F811
    from bonys_agents.gui import kursraum_fenster
    from bonys_agents.trainer.gui import kurse_leiten

    leiter, anna, kurs = laufender_kurs
    kurs = kurse.geleiteter_kurs(kurs.kurs_id)
    aufrufe = []
    monkeypatch.setattr(kursraum_fenster, "helfen",
                        lambda kid, name, iid, parent=None, fertig=None: aufrufe.append((kid, iid)) or fertig(None))
    monkeypatch.setattr(hilfe, "rechner_im_netz", lambda: hilfe.Rechner(False, "Tailscale ist aus."))
    angeboten = []
    monkeypatch.setattr(kurse_leiten.KursAnsicht, "_netz_anbieten", lambda self, r: angeboten.append(r.text))
    a = kurse_leiten.KursAnsicht(kurs)
    a.show()
    assert a.help_btn.isVisible() and not a.help_btn.isEnabled()
    a.table.selectRow(0)
    assert a.help_btn.isEnabled()
    a.help_btn.click()
    assert aufrufe == [(kurs.kurs_id, anna.instanz_id)] and "Anfrage geschickt" in a.status.text()
    a._status(kurse.PAUSIERT)
    _warten(qapp, lambda: not a.busy)
    assert not a.help_btn.isVisible()
    a._status(kurse.LAEUFT)                     # Kursstart: dieser Rechner nicht im Netz → anbieten
    _warten(qapp, lambda: angeboten)
    assert angeboten == ["Tailscale ist aus."]
    a.done(0)
    a.deleteLater()
