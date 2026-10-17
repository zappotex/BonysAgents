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
        self.geraete: list[dict] = []          # [{geraet_id, name, ip, online, zuletzt_gesehen}]
        self.schluessel: list[str] = []        # ausgegebene Geräteschlüssel
        self.grenze: int | None = None         # Gerätegrenze (409)
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
                if key == ("GET", "/api/v1/geraete"):
                    return self._send(200, outer.geraete)
                if key == ("POST", "/api/v1/geraete/schluessel"):
                    if outer.grenze is not None and len(outer.geraete) >= outer.grenze:
                        return self._send(409, {"detail": f"Die Gerätegrenze ist erreicht ({outer.grenze} Geräte)."})
                    outer.schluessel.append(f"hskey-auth-{len(outer.schluessel) + 1:04d}geheim")
                    return self._send(200, {"schluessel": outer.schluessel[-1], "login_server": "https://vpn.test",
                                            "gueltig_minuten": 60})
                if self.command == "DELETE" and self.path.startswith("/api/v1/geraete/"):
                    gid = self.path.rsplit("/", 1)[1]
                    if not any(g["geraet_id"] == gid for g in outer.geraete):
                        return self._send(404, {"detail": "Gerät nicht gefunden."})
                    outer.geraete = [g for g in outer.geraete if g["geraet_id"] != gid]
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


# ---------------------------------------------------------------- Aufgabe 02: Agenten-PCs ins Netz
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from bonys_agents import cloudinit, vm  # noqa: E402
from bonys_agents import progress as pct  # noqa: E402


@pytest.fixture
def angemeldet(zentrale):
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    netz.aktiv_setzen(True)
    return zentrale


def _geraet(gid, name, online=True, ip="100.64.0.7"):
    return {"geraet_id": gid, "name": name, "ip": ip, "online": online, "zuletzt_gesehen": 1760000000}


def test_bereit_nur_wenn_an_und_angemeldet(zentrale):
    assert not netz.bereit()
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    assert not netz.bereit()          # angemeldet, aber ausgeschaltet
    netz.aktiv_setzen(True)
    assert netz.bereit()


def test_beitritt_vorbereiten(angemeldet):
    b = netz.beitritt_vorbereiten("Agent PC 1 (Büro)")
    assert b.netzname == "agent-pc-1-buero"
    assert angemeldet.schluessel[0] in b.skript and "--login-server" in b.skript
    assert "https://vpn.test" in b.skript and "agent-pc-1-buero" in b.skript
    assert angemeldet.schluessel[0] not in repr(b)
    konto = Konto.laden()
    assert konto.token not in b.skript


def test_geraetegrenze_ergibt_hinweis(angemeldet):
    angemeldet.grenze = 0
    b, hinweis = netz.beitritt_mit_hinweis("pc")
    assert b is None and "Gerätegrenze ist erreicht" in hinweis and "ohne Bony-Netz" in hinweis


def test_ohne_internet_ergibt_hinweis(angemeldet):
    angemeldet.close()
    b, hinweis = netz.beitritt_mit_hinweis("pc")
    assert b is None and "nicht erreichbar" in hinweis and "bz_" not in hinweis


def test_ausgeschaltet_ergibt_hinweis_ohne_anfrage(angemeldet):
    netz.aktiv_setzen(False)
    angemeldet.anfragen.clear()
    b, hinweis = netz.beitritt_mit_hinweis("pc")
    assert b is None and "ausgeschaltet" in hinweis and angemeldet.anfragen == []


def test_geraete_zustand_und_entfernen(angemeldet):
    angemeldet.geraete = [_geraet("1", "pc-a"), _geraet("2", "pc-b", online=False)]
    liste = netz.geraete()
    assert netz.netz_zustand("pc-a", liste) == netz.IM_NETZ
    assert netz.netz_zustand("pc-b", liste) == netz.OFFLINE
    assert netz.netz_zustand("pc-c", liste) == netz.NICHT_VERBUNDEN
    assert netz.geraet_entfernen("pc-a") is True
    assert [g["name"] for g in angemeldet.geraete] == ["pc-b"]
    assert netz.geraet_entfernen("pc-a") is False


def _machine(datadir, name="pc-a", netz_name="pc-a"):
    path = datadir / "vms" / name
    path.mkdir(parents=True)
    cfg = vm.VMConfig(name=name, arch="x86_64", cpus=1, ram_mb=1024, netz_name=netz_name)
    from dataclasses import asdict

    vm.write_json(path / "vm.json", asdict(cfg))
    return vm.VM(path)


def test_loeschen_entfernt_aus_dem_netz(datadir, angemeldet):
    angemeldet.geraete = [_geraet("1", "pc-a")]
    m = _machine(datadir)
    assert netz.loeschen_hinweis(m) == "" and angemeldet.geraete == []


def test_loeschen_ohne_server_gibt_hinweis(datadir, angemeldet):
    m = _machine(datadir)
    angemeldet.close()
    hinweis = netz.loeschen_hinweis(m)
    assert "nicht aus dem Bony-Netz entfernt" in hinweis and "pc-a" in hinweis


def test_loeschen_ohne_netzname_fragt_nicht(datadir, angemeldet):
    m = _machine(datadir, netz_name="")
    angemeldet.anfragen.clear()
    assert netz.loeschen_hinweis(m) == "" and angemeldet.anfragen == []


def test_netzname_in_vm_json_wird_geprueft(datadir):
    m = _machine(datadir, netz_name="gueltig-1")
    assert m.config.netz_name == "gueltig-1"
    data = json.loads((m.path / "vm.json").read_text())
    data["netz_name"] = "Nicht gültig!"
    (m.path / "vm.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        vm.VM(m.path)


# ---------------------------------------------------------------- Im Agent-PC
def _guest(cfg_netz: str | None = "#!/bin/bash\necho beitritt\n"):
    from bonys_agents import apps

    return cloudinit.GuestConfig(hostname="pc", username="agent", password="pw1234",
                                 apps=apps.resolve(["brave"]), netz=cfg_netz)


def test_einrichtung_mit_netz_als_zweiter_schritt():
    script = cloudinit.provision_script(_guest())
    import re

    titles = re.findall(rf'echo "{cloudinit.STEP_MARKER} \d+/(\d+) ([^"]+)"', script)
    assert titles[1] == ("4", netz.SCHRITT_TITEL) and len(titles) == 4
    assert "echo beitritt" not in script          # das Skript (mit Schlüssel) kommt nur über das Seed-ISO
    assert netz.SEED_DATEI in script
    assert netz.SCHRITT_TITEL not in cloudinit.provision_script(_guest(None))
    if sys.platform != "win32":
        assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    # Fortschritt kennt den zusätzlichen Schritt
    assert len(pct.step_ranges(["brave"], netz=True)) == 4
    assert pct.step_ranges(["brave"], netz=True)[-1][1] == pytest.approx(pct.step_ranges(["brave"])[-1][1])


def test_seed_iso_enthaelt_das_skript(tmp_path):
    from test_vpnlink import iso_files

    cloudinit.write_seed_iso(tmp_path / "seed.iso", _guest("#!/bin/bash\n# hskey-geheim\n"), "id-1")
    files = iso_files(tmp_path / "seed.iso")
    assert files[netz.SEED_DATEI] == b"#!/bin/bash\n# hskey-geheim\n"
    assert b"hskey-geheim" not in files["user-data"]


def test_klon_tritt_beim_ersten_start_bei(tmp_path):
    from test_vpnlink import iso_files

    data = cloudinit.clone_user_data("pc", "agent", "pw1234", netz_beitritt=True)
    assert netz.SEED_DATEI in data and netz.FEHLER_ZEILE in data
    assert netz.SEED_DATEI not in cloudinit.clone_user_data("pc", "agent", "pw1234")
    script = cloudinit.clone_firstboot_script(netz_beitritt=True)
    assert script.index(netz.SEED_DATEI) < script.index(cloudinit.READY_MARKER)
    if sys.platform != "win32":
        assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0
    cloudinit.write_clone_seed_iso(tmp_path / "s.iso", "pc", "agent", "pw1234", "id", netz_skript="#!/bin/bash\n")
    assert iso_files(tmp_path / "s.iso")[netz.SEED_DATEI] == b"#!/bin/bash\n"


def test_vorlage_ohne_tailscale_identitaet():
    for remove in (True, False):
        s = cloudinit.generalize_script("agent", remove_personal=remove)
        assert "wipe /var/lib/tailscale" in s and netz.GAST_FERTIG in s and "\ntailscale logout" not in s


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-Shell")
def test_gast_beitritt_laeuft_einmal(tmp_path):
    """Wrapper wirklich ausführen (ohne apt-Wartezeit): einmal, wiederholbar, Schlüssel bleibt nicht liegen."""
    ziel, fertig, konsole = tmp_path / "beitritt.sh", tmp_path / "state" / "netz.done", tmp_path / "console"
    zaehler = tmp_path / "laeufe"

    def wrapper(skript: str) -> str:
        w = netz.gast_beitritt(aus_seed=False, skript=skript, console=str(konsole), fertig=str(fertig), ziel=str(ziel))
        return w.replace("    bonys_apt_wait\n", "    :\n") + 'exit "$NETZ_RC"\n'

    ok = f'#!/bin/bash\necho x >> {zaehler}\nrm -f -- "$0"\n'
    r = subprocess.run(["bash", "-c", wrapper(ok)], capture_output=True, text=True)
    assert r.returncode == 0 and fertig.exists() and not ziel.exists()
    r = subprocess.run(["bash", "-c", wrapper(ok)], capture_output=True, text=True)   # zweites Mal: nichts
    assert r.returncode == 0 and "schon verbunden" in r.stdout and zaehler.read_text() == "x\n"

    fertig.unlink()
    r = subprocess.run(["bash", "-c", wrapper("#!/bin/bash\nexit 3\n")], capture_output=True, text=True)
    assert r.returncode == 1 and not fertig.exists() and not ziel.exists()   # Schlüssel nicht liegen lassen
    assert netz.FEHLER_ZEILE in konsole.read_text()


def test_create_mit_netz(datadir, angemeldet, monkeypatch, tmp_path):
    from test_vpnlink import iso_files

    base = tmp_path / "base.img"
    base.write_bytes(b"img")
    monkeypatch.setattr(vm.images, "ensure_image", lambda image, d, cb, reuse_from=None: base)
    monkeypatch.setattr(vm.qemu, "find_binary", lambda name, os_: Path("/bin/true"))
    monkeypatch.setattr(vm.qemu, "create_disk", lambda qi, b, disk, gb: disk.write_bytes(b"disk"))
    messages = []
    m = vm.create("Netz_PC", "pw1234", app_ids=["brave"], progress=lambda *a: messages.append(a), bony_netz=True)
    assert m.config.netz_name == "netz-pc" and m.hinweise == []
    key = angemeldet.schluessel[0]
    assert key.encode() in iso_files(m.seed_iso)[netz.SEED_DATEI]
    assert key not in (m.path / "vm.json").read_text() and key not in repr(messages)
    assert vm.VM(m.path).config.netz_name == "netz-pc"

    # Gerätegrenze: trotzdem erstellt, ohne Netz, mit Hinweis
    angemeldet.grenze = 0
    m2 = vm.create("pc-2", "pw1234", app_ids=["brave"], bony_netz=True)
    assert m2.config.netz_name == "" and "Gerätegrenze" in m2.hinweise[0]
    assert netz.SEED_DATEI not in iso_files(m2.seed_iso)


def test_nachtraeglich_braucht_passwort_ohne_gast_agent(datadir, angemeldet, monkeypatch):
    m = _machine(datadir, netz_name="")
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    monkeypatch.setattr(vm.VM, "progress", lambda self: vm.Progress(0, 0, "", True))
    monkeypatch.setattr(vm.VM, "guest_agent_ready", lambda self: False)
    with pytest.raises(vm.NeedsPassword):
        netz.nachtraeglich_verbinden(m)
    assert angemeldet.schluessel == []   # kein Schlüssel verbraucht


def test_nachtraeglich_ueber_den_gast_agent(datadir, angemeldet, monkeypatch):
    m = _machine(datadir, netz_name="")
    monkeypatch.setattr(vm.VM, "is_running", lambda self: True)
    monkeypatch.setattr(vm.VM, "progress", lambda self: vm.Progress(0, 0, "", True))
    monkeypatch.setattr(vm.VM, "guest_agent_ready", lambda self: True)
    calls = []
    monkeypatch.setattr(vm.VM, "guest_run", lambda self, script, **kw: calls.append((script, kw)) or "ok")
    netz.nachtraeglich_verbinden(m)
    script, kw = calls[0]
    assert kw["via_stdin"] and angemeldet.schluessel[0] not in script   # nur base64 im Skript
    assert vm.VM(m.path).config.netz_name == "pc-a"
    if sys.platform != "win32":
        assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


def test_dialog_haekchen_nur_wenn_bereit(qapp, datadir, zentrale):
    from bonys_agents import host
    from bonys_agents.gui import create_dialog

    info = host.HostInfo(os="linux", arch="x86_64", cpus=4, ram_mb=16384, accel="kvm")
    d = create_dialog.CreateDialog(info)
    assert not d.netz_box.isVisibleTo(d) and not d.netz_box.isChecked()
    d.deleteLater()
    netz.server_wechseln(zentrale.url)
    netz.instanz_anlegen(zentrale.url)
    netz.aktiv_setzen(True)
    d = create_dialog.CreateDialog(info)
    assert d.netz_box.isVisibleTo(d) and d.netz_box.isChecked() and d.netz_box.isEnabled()
    d.deleteLater()


def test_hauptfenster_zeigt_netz_zustand(qapp, datadir, angemeldet, monkeypatch):
    from types import SimpleNamespace

    from bonys_agents import deps
    from bonys_agents.gui import main_window

    monkeypatch.setattr(deps, "check", lambda info: SimpleNamespace(ok=True, can_run=True))
    monkeypatch.setattr(main_window.updates, "auto_check_due", lambda: False)
    _machine(datadir)
    angemeldet.geraete = [_geraet("1", "pc-a")]
    win = main_window.MainWindow()
    try:
        win.timer.stop()
        win.show()
        win.refresh()
        assert win._netz_check is not None
        win._netz_check.wait(5000)
        qapp.processEvents()
        win.refresh()
        assert "Bony-Netz (pc-a): im Netz – 100.64.0.7" in win.list.item(0).toolTip()
        assert win.list.iconSize().width() == 30
        # Höchstens alle 30 Sekunden fragen
        abfragen = sum(a == "GET /api/v1/geraete" for a in angemeldet.anfragen)
        win.refresh()
        assert sum(a == "GET /api/v1/geraete" for a in angemeldet.anfragen) == abfragen
        # Fenster nicht sichtbar: keine Abfrage
        win.hide()
        win._netz_zuletzt = 0.0
        win.refresh()
        if win._netz_check:
            win._netz_check.wait(5000)
        assert sum(a == "GET /api/v1/geraete" for a in angemeldet.anfragen) == abfragen
        # Bony-Netz aus: kein Kontakt, Hinweis im Tooltip
        netz.aktiv_setzen(False)
        win.refresh()
        assert "ausgeschaltet" in win.list.item(0).toolTip()
    finally:
        win.timer.stop()
        win.close()
