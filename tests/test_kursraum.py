# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursraum (Aufgabe 05): bonys_agents.kursraum, die mitgelieferte Seite und die Knöpfe „Kursraum betreten/öffnen“.

Gegen die Test-Zentrale aus test_netz.py und einen Test-Server für die LiveKit-Schnittstelle (Twirp) auf 127.0.0.1.
Das Fenster selbst (Qt WebEngine, echte Verbindung) wird hier nicht geöffnet – das prüft der Ende-zu-Ende-Test mit
livekit-server (siehe docs/bony-netz.md).
"""

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_kurse import _als, _anmelden, _geraet, _wait, _zweite_instanz, qapp  # noqa: F401 – Fixture
from test_netz import FakeZentrale, karte_fuer

from bony_netz import ZentraleFehler
from bonys_agents import kurse, kursraum

ROOT = Path(__file__).resolve().parents[1]
SEITE = ROOT / "src" / "bonys_agents" / "resources" / "kursraum"


@pytest.fixture
def zentrale():
    z = FakeZentrale()
    yield z
    z.close()


class FakeLiveKit:
    """Server-Schnittstelle von LiveKit (Twirp RoomService) – merkt sich die Aufrufe."""

    def __init__(self):
        self.aufrufe: list[tuple[str, str, dict]] = []   # (Methode, Authorization, Body)
        self.antwort: tuple[int, dict] = (200, {})
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.aufrufe.append((self.path, self.headers.get("Authorization", ""), body))
                code, daten = outer.antwort
                roh = json.dumps(daten).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"ws://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def livekit():
    lk = FakeLiveKit()
    yield lk
    lk.close()


@pytest.fixture
def laufender_kurs(zentrale):
    """Kursleiter (angemeldet) mit laufendem Kurs „Hermes“ und Teilnehmerin Anna."""
    leiter = _anmelden(zentrale)
    zentrale.instanzen[leiter.token]["ist_kursleiter"] = True
    kurs = kurse.kurs_anlegen("Hermes", "Bony")
    anna = _zweite_instanz(zentrale)
    zentrale.geraete = [_geraet("g1", "pc-a")]
    _als(anna)
    kurse.kurs_beitreten(kurs.code, "g1", "Anna")
    _als(leiter)
    kurse.status_setzen(kurs.kurs_id, kurse.LAEUFT)
    return leiter, anna, kurs


# ---------------------------------------------------------------- Eintrittskarte
def test_eintreten_kursleiter_und_teilnehmer(zentrale, laufender_kurs):
    leiter, anna, kurs = laufender_kurs
    k = kursraum.eintreten(kurs.kurs_id)
    assert k.kursleiter and k.rolle == "kursleiter" and k.raum == kurs.kurs_id and k.kursraum_url == "wss://k.test"
    assert k.token == zentrale.karten[-1] and k.ablauf and k.ablauf > time.time() + 5 * 3600
    assert k.token not in repr(k)   # nie versehentlich ins Log
    _als(anna)
    k = kursraum.eintreten(kurs.kurs_id)
    assert not k.kursleiter and k.rolle == "teilnehmer"
    seite = k.fuer_seite(kursname="Hermes")
    assert seite["token"] == k.token and seite["rolle"] == "teilnehmer" and seite["kursname"] == "Hermes"


def test_eintreten_nur_wenn_der_kurs_laeuft(zentrale, laufender_kurs):
    leiter, anna, kurs = laufender_kurs
    for status in (kurse.PAUSIERT, kurse.BEENDET):
        zentrale.kurse[kurs.kurs_id]["status"] = status
        with pytest.raises(kursraum.KursraumFehler) as e:
            kursraum.eintreten(kurs.kurs_id)
        assert str(e.value) == kursraum.KURS_LAEUFT_NICHT
    with pytest.raises(ZentraleFehler) as e:   # fremder Kurs: Meldung der Zentrale unverändert
        kursraum.eintreten("gibtsnicht")
    assert e.value.meldung == "Kurs nicht gefunden."
    assert leiter.token not in str(e.value)


def test_eintreten_ohne_bony_netz(zentrale, laufender_kurs):
    from bonys_agents import netz

    netz.aktiv_setzen(False)
    zentrale.anfragen.clear()
    with pytest.raises(RuntimeError):
        kursraum.eintreten(laufender_kurs[2].kurs_id)
    assert zentrale.anfragen == []


def test_eintreten_falsche_antwort(zentrale, laufender_kurs, monkeypatch):
    kurs = laufender_kurs[2]
    for antwort in ([], {"kursraum_url": "wss://k"}, {"kursraum_url": "ftp://k", "eintrittskarte": "x"}):
        monkeypatch.setattr(kurse, "_aufruf", lambda fn, a=antwort: a)
        with pytest.raises(kursraum.KursraumFehler):
            kursraum.eintreten(kurs.kurs_id)


def test_token_ablauf():
    assert abs(kursraum.token_ablauf(karte_fuer(True, gueltig=60)) - (time.time() + 60)) < 5
    for kaputt in ("", "abc", "a.b.c", "a.e30.c", "a.bnVsbA.c"):
        assert kursraum.token_ablauf(kaputt) is None
    k = kursraum.Karte("k", "wss://x", "r", "teilnehmer", "t", ablauf=time.time() - 1)
    assert k.abgelaufen() and not kursraum.Karte("k", "wss://x", "r", "teilnehmer", "t").abgelaufen()


def test_server_adresse():
    assert kursraum.server_adresse("wss://kurs.example.de") == "https://kurs.example.de"
    assert kursraum.server_adresse("wss://kurs.example.de:7443/") == "https://kurs.example.de:7443"
    assert kursraum.server_adresse("ws://127.0.0.1:7880") == "http://127.0.0.1:7880"
    assert kursraum.server_adresse(" WSS://k.example.de/livekit/ ") == "https://k.example.de/livekit"
    for falsch in ("", "k.example.de", "ftp://k", "wss://"):
        with pytest.raises(kursraum.KursraumFehler):
            kursraum.server_adresse(falsch)


# ---------------------------------------------------------------- LiveKit-Server: stummschalten, entfernen
def _karte(livekit, kursleiter=True, gueltig=3600):
    token = karte_fuer(kursleiter, gueltig)
    return kursraum.Karte("k1", livekit.url, "raum1", "kursleiter" if kursleiter else "teilnehmer", token,
                          kursraum.token_ablauf(token))


def test_stummschalten_und_entfernen(livekit):
    k = _karte(livekit)
    kursraum.stummschalten(k, "anna", "TR_mik")
    kursraum.entfernen(k, "anna")
    assert livekit.aufrufe == [
        ("/twirp/livekit.RoomService/MutePublishedTrack", f"Bearer {k.token}",
         {"room": "raum1", "identity": "anna", "track_sid": "TR_mik", "muted": True}),
        ("/twirp/livekit.RoomService/RemoveParticipant", f"Bearer {k.token}", {"room": "raum1", "identity": "anna"}),
    ]


def test_steuerung_nur_kursleiter_und_mit_gueltiger_karte(livekit):
    with pytest.raises(kursraum.KursraumFehler, match="nur der Kursleiter"):
        kursraum.entfernen(_karte(livekit, kursleiter=False), "anna")
    with pytest.raises(kursraum.KursraumFehler, match="abgelaufen"):
        kursraum.entfernen(_karte(livekit, gueltig=-10), "anna")
    with pytest.raises(kursraum.KursraumFehler):
        kursraum.stummschalten(_karte(livekit), "anna", "")
    assert livekit.aufrufe == []


@pytest.mark.parametrize("code,daten,text", [
    (401, {"code": "unauthenticated", "msg": "invalid token"}, "nicht angenommen"),
    (403, {"code": "permission_denied"}, "erlaubt das dieser Karte nicht"),
    (404, {"code": "not_found", "msg": "participant not found"}, "nicht mehr im Kursraum"),
    (500, {"code": "internal", "msg": "kaputt"}, "Fehler 500 geantwortet: kaputt"),
])
def test_fehler_des_livekit_servers(livekit, code, daten, text):
    livekit.antwort = (code, daten)
    k = _karte(livekit)
    with pytest.raises(kursraum.KursraumFehler, match=text) as e:
        kursraum.entfernen(k, "anna")
    assert k.token not in str(e.value)


def test_livekit_server_nicht_erreichbar():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    token = karte_fuer(True)
    k = kursraum.Karte("k1", f"ws://127.0.0.1:{port}", "r", "kursleiter", token, kursraum.token_ablauf(token))
    with pytest.raises(kursraum.KursraumFehler, match="nicht erreichbar") as e:
        kursraum.entfernen(k, "anna")
    assert token not in str(e.value)


# ---------------------------------------------------------------- Regeln für die Seite
def test_seiten_datei_nur_aus_dem_ordner(tmp_path):
    ordner = tmp_path / "kursraum"
    (ordner / "vendor").mkdir(parents=True)
    (ordner / "index.html").write_text("<html>")
    (ordner / "vendor" / "lib.js").write_text("x")
    (ordner / "notiz.txt").write_text("geheim")
    (tmp_path / "geheim.html").write_text("nein")
    assert kursraum.seiten_datei("/", ordner) == ((ordner / "index.html").resolve(), "text/html")
    assert kursraum.seiten_datei("/vendor/lib.js", ordner)[1] == "text/javascript"
    for pfad in ("/../geheim.html", "/vendor/../../geheim.html", "/%2e%2e/geheim.html", "/notiz.txt",
                 "/fehlt.js", "/vendor", "//etc/passwd", "/C:/x.js", "/vendor\\lib.js"):
        assert kursraum.seiten_datei(pfad, ordner) is None, pfad


def test_seiten_datei_symlink_nach_aussen(tmp_path):
    ordner = tmp_path / "kursraum"
    ordner.mkdir()
    (tmp_path / "draussen.js").write_text("x")
    try:
        (ordner / "link.js").symlink_to(tmp_path / "draussen.js")
    except OSError:
        pytest.skip("keine Symlinks")
    assert kursraum.seiten_datei("/link.js", ordner) is None


def test_berechtigungen_nur_fuer_die_eigene_seite():
    for art in ("MediaAudioCapture", "MediaVideoCapture", "MediaAudioVideoCapture", "DesktopVideoCapture",
                "DesktopAudioVideoCapture"):
        assert kursraum.erlaubt("kursraum", "app", art)
        assert not kursraum.erlaubt("https", "app", art)
        assert not kursraum.erlaubt("kursraum", "anderer", art)
        assert not kursraum.erlaubt("file", "", art)
    for art in ("Geolocation", "Notifications", "ClipboardReadWrite", "MouseLock", "LocalFontsAccess", "Unsupported"):
        assert not kursraum.erlaubt("kursraum", "app", art)


def test_wayland_kein_bildschirm_teilen(monkeypatch):
    monkeypatch.setattr(kursraum.sys, "platform", "linux")
    for sitzung, anzeige, wl in (("wayland", "", True), ("x11", "wayland-0", False), ("", "wayland-0", True),
                                 ("", "", False), ("tty", "", False)):
        monkeypatch.setenv("XDG_SESSION_TYPE", sitzung)
        monkeypatch.setenv("WAYLAND_DISPLAY", anzeige)
        assert kursraum.wayland() is wl, (sitzung, anzeige)
        moeglich, hinweis = kursraum.bildschirm_teilen()
        assert moeglich is not wl and (hinweis == kursraum.WAYLAND_HINWEIS) is wl
    monkeypatch.setattr(kursraum.sys, "platform", "win32")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert kursraum.bildschirm_teilen() == (True, "")


def test_sandbox_nur_ohne_apparmor_profil(tmp_path, monkeypatch):
    monkeypatch.setattr(kursraum.sys, "platform", "linux")
    sperre, label = tmp_path / "sperre", tmp_path / "label"
    sperre.write_text("1\n")
    label.write_text("unconfined\n")
    assert kursraum.sandbox_abschalten(sperre, (label,))            # Ubuntu 24.04, Quelltext-Installation
    label.write_text("bonys-agents (unconfined)\n")
    assert not kursraum.sandbox_abschalten(sperre, (label,))        # .deb mit Profil: Sandbox bleibt an
    label.write_text("bonys-agents-anders (unconfined)\n")
    assert kursraum.sandbox_abschalten(sperre, (tmp_path / "fehlt", label))
    sperre.write_text("0\n")
    assert not kursraum.sandbox_abschalten(sperre, (label,))        # Mint, Debian: keine Sperre
    assert not kursraum.sandbox_abschalten(tmp_path / "fehlt", (label,))
    monkeypatch.setattr(kursraum.sys, "platform", "win32")
    sperre.write_text("1\n")
    assert not kursraum.sandbox_abschalten(sperre, (label,))


def test_paket_bringt_webengine_mit():
    """Bauplan und .deb passen zum Kursraum: Module nicht ausgeschlossen, System-Bibliotheken als Abhängigkeit."""
    spec = (ROOT / "packaging" / "bonys-agents.spec").read_text("utf-8")
    deb = (ROOT / "packaging" / "linux" / "build-deb.sh").read_text("utf-8")
    profil = (ROOT / "packaging" / "linux" / "apparmor-bonys-agents").read_text("utf-8")
    ausgeschlossen = spec.split("EXCLUDES = [", 1)[1].split("]", 1)[0]
    for modul in ("QtWebEngineCore", "QtWebEngineWidgets", "QtWebChannel", "QtNetwork", "QtPrintSupport"):
        assert f'"PySide6.{modul}"' not in ausgeschlossen, modul
    assert "fetch-livekit.py" in deb
    assert 'WEBENGINE="$STAGE/opt/$APP/_internal/PySide6/Qt/libexec/QtWebEngineProcess"' in deb
    assert '[ ! -f "$WEBENGINE" ] || chmod 755 "$WEBENGINE"' in deb
    depends = deb.split('WEBENGINE_DEPENDS=",', 1)[1].split('"', 1)[0]
    for paket in ("libnss3", "libnspr4", "libasound2", "libgbm1", "libdrm2", "libxkbfile1", "libxtst6",
                  "libxcb-dri3-0"):
        assert paket in depends, paket
    assert "profile bonys-agents /opt/bonys-agents/BonysAgents" in profil and "userns," in profil
    assert kursraum.APPARMOR_PROFIL == "bonys-agents" and "/etc/apparmor.d/abi/4.0" in deb


# ---------------------------------------------------------------- Die mitgelieferte Seite
def test_seite_vollstaendig_und_ohne_fremde_quellen():
    html = (SEITE / "index.html").read_text("utf-8")
    js = (SEITE / "kursraum.js").read_text("utf-8")
    quellen = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert set(quellen) == {"kursraum.css", "qwebchannel.js", "vendor/livekit-client.umd.js", "kursraum.js"}
    for q in quellen:
        assert "://" not in q
        if q not in ("qwebchannel.js", "vendor/livekit-client.umd.js"):
            assert kursraum.seiten_datei("/" + q, SEITE) is not None, q
    assert "Content-Security-Policy" in html and "script-src 'self'" in html
    # Chat und Namen nur als Text – nie als HTML; Karte nie ins Log
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js
    assert not re.search(r"console\.\w+\([^)]*token", js)
    # Themen der Datennachrichten wie in der Aufgabe
    for thema in ("'chat'", "'hand'", "'freigabe'"):
        assert thema in js
    assert "reliable: true" in js and "room.disconnect()" in js


def test_livekit_version_ueberall_gleich():
    fetch = (ROOT / "packaging" / "fetch-livekit.py").read_text("utf-8")
    assert f'VERSION = "{kursraum.LIVEKIT_VERSION}"' in fetch
    third = (ROOT / "THIRD-PARTY-LICENSES").read_text("utf-8")
    zeile = next(z for z in third.splitlines() if z.strip().startswith("livekit-client"))
    assert kursraum.LIVEKIT_VERSION in zeile.split() and "Apache-2.0" in zeile
    stempel = SEITE / "vendor" / "VERSION"
    if stempel.is_file():   # nur nach packaging/fetch-livekit.py
        assert stempel.read_text().split()[0] == kursraum.LIVEKIT_VERSION


# ---------------------------------------------------------------- Knöpfe in „Kurse“
def test_knopf_kursraum_betreten(qapp, datadir, zentrale, laufender_kurs, monkeypatch):  # noqa: F811
    from bonys_agents.gui import kurse_dialog, kursraum_fenster

    leiter, anna, kurs = laufender_kurs
    _als(anna)
    geoeffnet = []

    def oeffnen(kurs_id, name, parent=None, fertig=None):
        geoeffnet.append((kurs_id, name))
        fertig(None)

    monkeypatch.setattr(kursraum_fenster, "oeffnen", oeffnen)
    d = kurse_dialog.KurseDialog()
    d.tabs.setCurrentWidget(d.teilnahme)
    d.show()
    s = d.teilnahme
    d._tick()
    _wait(qapp, s)
    s.table.selectRow(0)
    assert s.room_btn.isEnabled()
    s.room_btn.click()
    assert geoeffnet == [(kurs.kurs_id, "Hermes")] and not s.busy and s.status.text() == ""

    # Fehler (z. B. Kurs inzwischen pausiert) erscheint in der Statuszeile
    monkeypatch.setattr(kursraum_fenster, "oeffnen",
                        lambda kurs_id, name, parent=None, fertig=None: fertig(kursraum.KURS_LAEUFT_NICHT))
    s.room_btn.click()
    assert s.status.text() == f"Kursraum: {kursraum.KURS_LAEUFT_NICHT}"
    assert s.room_btn.isEnabled()
    d.done(0)
    d.deleteLater()


def test_kurse_fenster_sperrt_den_kursraum_nicht(qapp, datadir):  # noqa: F811
    from PySide6.QtCore import Qt

    from bonys_agents.gui.kurse_dialog import KurseDialog

    d = KurseDialog()
    assert d.windowModality() == Qt.WindowModal
    d.deleteLater()


@pytest.mark.kursleiter
def test_knopf_kursraum_oeffnen(qapp, datadir, zentrale, laufender_kurs, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt

    from bonys_agents.gui import kursraum_fenster
    from bonys_agents.trainer.gui import kurse_leiten

    leiter, anna, kurs = laufender_kurs
    geoeffnet = []
    monkeypatch.setattr(kursraum_fenster, "oeffnen",
                        lambda kurs_id, name, parent=None, fertig=None: (geoeffnet.append(kurs_id), fertig(None)))
    v = kurse_leiten.KursAnsicht(kurse.geleiteter_kurs(kurs.kurs_id))
    assert v.windowModality() == Qt.WindowModal
    v.show()
    qapp.processEvents()
    assert v.room_btn.isVisible() and v.room_btn.isEnabled()
    v.room_btn.click()
    assert geoeffnet == [kurs.kurs_id] and not v.busy
    v.done(0)
    v.deleteLater()


def test_hinweis_ohne_webengine_auf_linux_arm(monkeypatch):
    import platform

    monkeypatch.setattr(kursraum.sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")
    assert kursraum.linux_arm() and kursraum.kein_webengine_text() == kursraum.KEIN_WEBENGINE_ARM
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    assert kursraum.kein_webengine_text() == kursraum.KEIN_WEBENGINE


def test_oeffnen_ohne_webengine_oder_seite(qapp, monkeypatch):  # noqa: F811
    from bonys_agents.gui import kursraum_fenster

    gemeldet = []
    monkeypatch.setattr(kursraum_fenster, "QWebEngineView", None)
    kursraum_fenster.oeffnen("k1", "Hermes", fertig=gemeldet.append)
    monkeypatch.undo()
    if kursraum_fenster.verfuegbar():
        monkeypatch.setattr(kursraum, "livekit_da", lambda ordner=None: False)
        kursraum_fenster.oeffnen("k1", "Hermes", fertig=gemeldet.append)
        assert gemeldet == [kursraum.KEIN_WEBENGINE, kursraum.KEINE_SEITE]
    else:
        assert gemeldet == [kursraum.KEIN_WEBENGINE]
