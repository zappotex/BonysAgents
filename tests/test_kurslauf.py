# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspakete im Agent-PC: Prüfskripte nur über den Gast-Agent, Startzustände (qcow2-Schnappschüsse),
Signatur und Zustimmung zu fremden Skripten."""

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_kurspaket import mit, paket_ordner

from bonys_agents import kurslauf, kurspaket, qemu, signing


@pytest.fixture(autouse=True)
def _keine_mitgelieferten(monkeypatch):
    monkeypatch.setattr(kurspaket, "mitgeliefert_dirs", lambda: [])


class FakeConfig:
    username = "agent"
    first_boot_pending = False


class FakeVM:
    def __init__(self, disk: Path | None = None, running: bool = True, ready: bool = True):
        self.disk = disk or Path("/gibt/es/nicht.qcow2")
        self.running = running
        self.ready = ready
        self.config = FakeConfig()
        self.gestoppt = self.gestartet = 0

    def is_running(self):
        return self.running

    def progress(self):
        return type("P", (), {"ready": self.ready})()

    def qga_endpoint(self):
        return "qga"

    def qmp_endpoint(self):
        return "qmp"

    def stop(self):
        self.gestoppt += 1
        self.running = False

    def start(self):
        self.gestartet += 1
        self.running = True


class FakeGA:
    """Gast-Agent-Attrappe: merkt sich jeden Aufruf, liefert den eingestellten Exit-Code."""
    aufrufe: list = []
    rc = 0
    fehler = False

    def __init__(self, target, timeout=5.0):
        if FakeGA.fehler:
            raise qemu.GuestAgentError("nicht erreichbar")

    def exec(self, path, args, stdin=None, timeout=120, poll=None):
        FakeGA.aufrufe.append((path, list(args), stdin, timeout))
        return FakeGA.rc, "GEHEIME AUSGABE", ""

    def run(self, script, timeout=120):
        FakeGA.aufrufe.append(("run", script, None, timeout))
        return 0, ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def ga(monkeypatch):
    FakeGA.aufrufe, FakeGA.rc, FakeGA.fehler = [], 0, False
    monkeypatch.setattr(qemu, "GuestAgent", FakeGA)
    return FakeGA


@pytest.fixture
def keine_prozesse(monkeypatch):
    """Kein Prozess auf diesem Rechner – Skripte aus dem Paket dürfen nur in den Gast."""
    def verboten(*a, **k):
        raise AssertionError(f"Prozess auf dem Rechner gestartet: {a[:1]}")

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, verboten)
    monkeypatch.setattr(os, "system", verboten)


# ---------------------------------------------------------------- Prüfungen
def test_befehl_im_gast():
    prog, args = kurslauf.befehl_im_gast(Path("p.sh"), "benutzer", "agent", 20)
    assert prog == "/usr/bin/timeout" and args[:3] == ["-k", "3", "20"]
    assert args[3:7] == ["/usr/sbin/runuser", "-u", "agent", "--"] and args[-2:] == ["/bin/bash", "-s"]
    assert "HOME=/home/agent" in args and "-i" in args
    prog, args = kurslauf.befehl_im_gast(Path("p.py"), "root", "agent", 5)
    assert "/usr/sbin/runuser" not in args and args[-2:] == ["/usr/bin/python3", "-"] and "HOME=/root" in args
    with pytest.raises(ValueError):
        kurslauf.befehl_im_gast(Path("p.exe"), "root", "agent", 5)
    with pytest.raises(ValueError):
        kurslauf.befehl_im_gast(Path("p.sh"), "benutzer", "agent; rm -rf /", 5)


def test_pruefung_nur_im_agent_pc(datadir, tmp_path, ga, keine_prozesse):
    paket = kurspaket.laden(paket_ordner(tmp_path))
    lek = paket.lektionen[1]
    m = FakeVM()
    e = kurslauf.pruefen(m, paket, lek)
    assert e == kurslauf.Ergebnis(True, "Gut!")
    path, args, stdin, timeout = ga.aufrufe[-1]
    assert path == "/usr/bin/timeout" and stdin == (lek.pfad / "pruefung" / "datei.sh").read_bytes()
    assert timeout > lek.pruefung.zeitlimit
    ga.rc = 1
    assert kurslauf.pruefen(m, paket, lek) == kurslauf.Ergebnis(False, "Fehlt noch.")
    ga.rc = kurslauf.ZEITLIMIT_RC
    e = kurslauf.pruefen(m, paket, lek)
    assert not e.geschafft and "zu lange" in e.text
    assert "GEHEIME AUSGABE" not in e.text      # die Ausgabe des Skripts erscheint nirgends
    ga.fehler = True
    with pytest.raises(kurslauf.NichtBereit, match="antwortet noch nicht"):
        kurslauf.pruefen(m, paket, lek)
    with pytest.raises(kurslauf.NichtBereit):
        kurslauf.pruefen(FakeVM(ready=False), paket, lek)
    with pytest.raises(kurslauf.NichtBereit):
        kurslauf.pruefen(None, paket, lek)


def test_eingebaute_pruefungen(datadir, tmp_path, ga, monkeypatch):
    from bonys_agents import templates

    paket = kurspaket.laden(paket_ordner(tmp_path))
    vorlage = paket.lektionen[2]
    monkeypatch.setattr(templates, "list_templates", lambda: [])
    assert not kurslauf.pruefen(None, paket, vorlage).geschafft
    monkeypatch.setattr(templates, "list_templates", lambda: ["basis"])
    assert kurslauf.pruefen(None, paket, vorlage).geschafft
    vorlage.pruefung.typ = "agent-pc-laeuft"
    assert kurslauf.pruefen(FakeVM(), paket, vorlage).geschafft
    assert not kurslauf.pruefen(FakeVM(running=False), paket, vorlage).geschafft
    assert ga.aufrufe == []                     # eingebaute Prüfungen fassen den Gast nicht an


# ---------------------------------------------------------------- Startzustände
qemu_img = pytest.mark.skipif(not shutil.which("qemu-img"), reason="qemu-img fehlt")


@pytest.fixture
def platte(tmp_path, monkeypatch):
    monkeypatch.setattr(kurslauf, "_qemu_img", lambda: Path(shutil.which("qemu-img")))
    disk = tmp_path / "disk.qcow2"
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), "16M"], check=True, capture_output=True)
    return disk


def _schreiben(disk: Path, inhalt: bytes) -> None:
    subprocess.run(["qemu-io", "-c", f"write -P {inhalt[0]} 0 64k", str(disk)], check=True, capture_output=True)


def _lesen(disk: Path) -> int:
    out = subprocess.run(["qemu-io", "-c", "read -v 0 1", str(disk)], check=True, capture_output=True,
                         text=True).stdout
    return int(out.split(":", 1)[1].split()[0], 16)


@qemu_img
def test_startzustaende_offline(datadir, tmp_path, platte, ga):
    if not shutil.which("qemu-io"):
        pytest.skip("qemu-io fehlt")
    d = paket_ordner(tmp_path / "p", mit(lektionen=[
        {"ordner": "01-ankommen", "titel": "A"}, {"ordner": "02-uebung", "titel": "B"},
        {"ordner": "03-vorlage", "titel": "C"}]))
    paket = kurspaket.laden(d)
    m = FakeVM(platte, running=False)
    _schreiben(platte, b"\x01")
    assert kurslauf.lektion_vorbereiten(m, paket, 0)
    assert not kurslauf.lektion_vorbereiten(m, paket, 0)     # gibt es schon
    _schreiben(platte, b"\x02")
    assert kurslauf.lektion_vorbereiten(m, paket, 1)
    _schreiben(platte, b"\x03")
    kurslauf.lektion_vorbereiten(m, paket, 2)
    assert kurslauf.startzustaende(m, paket) == {"01-ankommen", "02-uebung", "03-vorlage"}
    _schreiben(platte, b"\x09")
    # Zurück auf Lektion 2: Stand von damals, Lektion 3 ist danach weg, Agent-PC startet wieder
    kurslauf.lektion_zuruecksetzen(m, paket, 1)
    assert _lesen(platte) == 2 and m.gestartet == 1
    assert kurslauf.startzustaende(m, paket) == {"01-ankommen", "02-uebung"}
    m.running = True
    m.stop()
    kurslauf.lektion_zuruecksetzen(m, paket, 0, starten=False)
    assert _lesen(platte) == 1
    assert kurslauf.alle_loeschen(m, paket) == 1
    assert kurslauf.schnappschuesse(m) == set()
    with pytest.raises(kurslauf.NichtBereit):
        kurslauf.lektion_zuruecksetzen(m, paket, 1)


def test_startzustand_im_laufenden_betrieb(datadir, tmp_path, ga, monkeypatch):
    befehle = []

    class FakeQMP:
        def __init__(self, target, timeout=5.0):
            pass

        def hmp(self, line):
            befehle.append(line)
            return ""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(qemu, "QMP", FakeQMP)
    vorhanden = set()
    monkeypatch.setattr(kurslauf, "schnappschuesse", lambda m: vorhanden)
    d = paket_ordner(tmp_path)
    start = d / "lektionen" / "02-uebung" / "start"
    start.mkdir()
    (start / "ordner.sh").write_text("mkdir -p ~/Kurs\n")
    import json
    daten = json.loads((d / "paket.json").read_text())
    daten["lektionen"][1]["start"] = {"skript": "start/ordner.sh", "als": "benutzer"}
    (d / "paket.json").write_text(json.dumps(daten))
    paket = kurspaket.laden(d)
    m = FakeVM()
    assert kurslauf.lektion_vorbereiten(m, paket, 1)
    # erst sync, dann Startskript im Gast, dann Schnappschuss über den Monitor
    assert ga.aufrufe[0][1][-2:] == ["/bin/bash", "-s"] and ga.aufrufe[0][2] == b"mkdir -p ~/Kurs\n"
    assert ga.aufrufe[1][:2] == ("run", "sync")
    assert befehle == ["snapshot_blkdev_internal disk0 bonys-paket-test-paket-02"]
    # ohne laufenden Agent-PC kein Startskript
    with pytest.raises(kurslauf.NichtBereit):
        kurslauf.lektion_vorbereiten(FakeVM(running=False), paket, 1)
    # Startskript schlägt fehl → kein Schnappschuss
    ga.rc = 2
    befehle.clear()
    with pytest.raises(RuntimeError, match="Startskript"):
        kurslauf.lektion_vorbereiten(m, paket, 1)
    assert befehle == []


# ---------------------------------------------------------------- Vertrauen
def _schluessel():
    secret = bytes(range(32))
    key_id = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    public = base64.b64encode(b"Ed" + key_id + signing.ed25519_public_key(secret)).decode()
    return secret, key_id, public


def test_signatur(datadir, tmp_path):
    secret, key_id, public = _schluessel()
    d = paket_ordner(tmp_path)
    text = kurslauf.pruefsummen_text(d)
    (d / kurslauf.PRUEFSUMMEN).write_text(text)
    (d / kurslauf.SIGNATUR).write_text(signing.sign(text.encode(), secret, key_id, "Kurspaket test-paket"))
    paket = kurspaket.laden(d)
    assert kurslauf.signatur_pruefen(paket, public)
    assert not kurslauf.signatur_pruefen(paket)               # anderer (offizieller) Schlüssel
    (d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").write_text("rm -rf ~\n")
    assert not kurslauf.signatur_pruefen(paket, public)       # Datei verändert
    (d / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").write_text("#!/bin/bash\ntest -s ~/x\n")
    assert kurslauf.signatur_pruefen(paket, public)
    (d / "extra.txt").write_text("dazugeschmuggelt")
    assert not kurslauf.signatur_pruefen(paket, public)       # zusätzliche Datei
    # die Signatur übersteht Packen und Importieren
    (d / "extra.txt").unlink()
    datei = kurspaket.packen(d, tmp_path / "p.bonyspaket")
    assert kurslauf.signatur_pruefen(kurspaket.importieren(datei), public)


def test_zustimmung_zu_skripten(datadir, tmp_path):
    d = paket_ordner(tmp_path)
    paket = kurspaket.importieren(d)
    assert [s[2] for s in paket.skripte()] == ["lektionen/02-uebung/pruefung/datei.sh"]
    assert kurslauf.zustimmung_noetig(paket)
    kurslauf.zustimmen(paket)
    assert not kurslauf.zustimmung_noetig(paket)
    # geänderte Fassung: erneut fragen
    (paket.pfad / "lektionen" / "02-uebung" / "pruefung" / "datei.sh").write_text("#!/bin/bash\nexit 0\n")
    assert kurslauf.zustimmung_noetig(paket)
    paket.herkunft = kurspaket.MITGELIEFERT
    assert not kurslauf.zustimmung_noetig(paket)
    ohne = kurspaket.laden(paket_ordner(tmp_path / "ohne", mit(lektionen=[])))
    assert not kurslauf.zustimmung_noetig(ohne)
