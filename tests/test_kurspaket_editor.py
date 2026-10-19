# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspaket-Editor (Kursleiter-Edition): Speichern, Duplizieren, Geheimnis-Prüfung, Prüfskript-Vorlagen, PDF,
„Kurspaket prüfen“ (nur im Agent-PC) und das Editor-Fenster."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from bonys_agents import kurslauf
from bonys_agents import kurspaket as kp

from test_kurspaket import PAKET, _warten, paket_ordner

pytestmark = pytest.mark.kursleiter

ed = None   # bonys_agents.trainer.kurspaket_editor – die Fixture importiert es (fehlt in der Anwender-Version)


@pytest.fixture(autouse=True)
def _editor(monkeypatch):
    global ed
    from bonys_agents.trainer import kurspaket_editor

    ed = kurspaket_editor
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [])
    monkeypatch.setattr(ed, "_min_version", lambda: "0.1.0")


# ---------------------------------------------------------------- paket.json schreiben
def test_paket_json_hin_und_zurueck(tmp_path):
    p = kp.laden(paket_ordner(tmp_path))
    d = kp.paket_json(p)
    assert d["id"] == "test-paket" and d["rezept"]["apps"] == ["brave", "hermes"]
    assert "dauer_minuten" not in d          # = Summe der Lektionen
    assert d["lektionen"][1]["pruefung"] == {"skript": "pruefung/datei.sh", "geschafft": "Gut!",
                                             "noch_nicht": "Fehlt noch."}
    assert d["lektionen"][2]["pruefung"]["typ"] == "vorlage-vorhanden"
    zurueck = kp.paket_pruefen(json.loads(kp.json_text(d)), p.pfad)
    assert kp.paket_json(zurueck) == d


def test_loesung_im_format(tmp_path):
    daten = json.loads(json.dumps(PAKET))
    daten["lektionen"][1]["pruefung"]["loesung"] = "pruefung/loesung.sh"
    d = paket_ordner(tmp_path, daten)
    with pytest.raises(kp.PaketFehler, match="Lösungsskript"):
        kp.laden(d)
    (d / "lektionen/02-uebung/pruefung/loesung.sh").write_text("echo Käse > ~/x\n", encoding="utf-8")
    p = kp.laden(d)
    assert p.lektionen[1].pruefung.loesung == "pruefung/loesung.sh"
    assert [a for _l, a, _p in p.skripte()] == ["Prüfung", "Lösung (nur „Kurspaket prüfen“)"]
    daten["lektionen"][1]["pruefung"]["loesung"] = "pruefung/datei.sh"
    with pytest.raises(kp.PaketFehler, match="anderes Skript"):
        kp.paket_pruefen(daten)


# ---------------------------------------------------------------- Geheimnis-Prüfung
@pytest.mark.parametrize("zeile,art", [
    ("OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef0123456789abcdef", "OpenRouter"),
    ("export OPENAI_API_KEY=sk-proj-AbCdEfGhIjKlMnOpQrStUvWx", "sk-"),
    ("ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrst", "Anthropic"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz0123456789", "GitHub"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "privater Schlüssel"),
    ("Bot: 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1", "Telegram"),
    ("AWS AKIAIOSFODNN7EXAMPLE", "AWS"),
    ('"password": "Sommer2026!"', "Passwort"),
    ("db: postgres://kurs:geheim123@server/db", "Adresse"),
    ("Fragen an anna.mueller@verein-xy.de", "E-Mail"),
    ("Ruf an: +49 170 1234567", "Telefon"),
    ("IBAN DE89 3704 0044 0532 0130 00", "IBAN"),
])
def test_geheimnisse_gefunden(zeile, art):
    funde = kp.geheimnisse_suchen_text(f"Zeile 1\n{zeile}\n", "x.md")
    assert len(funde) == 1 and funde[0].zeile == 2 and art in funde[0].art
    assert zeile not in str(funde[0])        # der Wert selbst wird nie angezeigt


@pytest.mark.parametrize("zeile", [
    "OPENROUTER_API_KEY=<dein-schlüssel>",
    "export OPENAI_API_KEY=$OPENAI_API_KEY",
    "API-Schlüssel: dein eigener Schlüssel",
    "password: agent",
    "Schreibe an kurs@example.com",
    "git clone git@github.com:zappotex/x.git",
    "Kurscode K7QX-M3PA, Uhrzeit 10:00, 120 Minuten",
    "hermes setup → Nous → Free-Modell, mindestens 64K Kontext",
    "token = os.environ.get('TOKEN')",
    "sk-or-v1-…",
])
def test_keine_falschen_funde(zeile):
    assert kp.geheimnisse_suchen_text(zeile) == []


def test_export_blockiert_bei_geheimnis(tmp_path):
    d = paket_ordner(tmp_path)
    (d / "handout.md").write_text("Schlüssel: sk-or-v1-0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    with pytest.raises(kp.GeheimnisGefunden) as e:
        kp.packen(d, tmp_path / "x.bonyspaket")
    assert "handout.md, Zeile 1" in str(e.value) and "0123456789abcdef" not in str(e.value)
    assert not (tmp_path / "x.bonyspaket").exists()


# ---------------------------------------------------------------- Neu, Duplizieren, Version
def test_slug_und_version():
    assert ed.slug("Übung 1: Dateien & Größen") == "uebung-1-dateien-groessen"
    assert ed.version_erhoehen("1.2.3") == "1.2.4"
    assert ed.version_erhoehen("1.2.3", "minor") == "1.3.0"
    assert ed.version_erhoehen("1.2", "major") == "2.0.0"


def test_neu_anlegen_und_duplizieren(datadir):
    p = ed.neu_anlegen("Mein Kurs für Anfänger", "anfaenger", autor="Bony")
    assert p.id == "mein-kurs-fuer-anfaenger" and p.herkunft == kp.EIGEN and p.entwurf
    assert [x.id for x in kp.liste()] == [p.id]
    with pytest.raises(kp.PaketFehler, match="schon"):
        ed.neu_anlegen("Mein Kurs für Anfänger")
    kopie = ed.duplizieren(p, "mein-kurs-2", "Mein zweiter Kurs")
    assert kopie.name == "Mein zweiter Kurs" and kopie.version == "0.1.0"
    assert len(kp.liste()) == 2 and ed.bearbeitbar(kopie)


def test_eigene_fassung_eines_mitgelieferten(datadir, tmp_path, monkeypatch):
    basis = tmp_path / "mit"
    basis.mkdir()
    paket_ordner(basis)
    (basis / "test-paket" / kurslauf.PRUEFSUMMEN).write_text("x", encoding="utf-8")
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [basis])
    original = kp.holen("test-paket")
    assert original.mitgeliefert and not ed.bearbeitbar(original)
    eigen = ed.duplizieren(original, original.id)
    assert eigen.herkunft == kp.EIGEN and kp.holen("test-paket").pfad == eigen.pfad
    assert not (eigen.pfad / kurslauf.PRUEFSUMMEN).exists()


# ---------------------------------------------------------------- Speichern
def test_speichern_umsortieren_und_skripte(datadir, tmp_path):
    p = ed.neu_anlegen("Speichertest")
    e = ed.Entwurf.laden(p.pfad)
    (p.pfad / "lektionen" / "01-ankommen" / "bilder").mkdir()
    (p.pfad / "lektionen" / "01-ankommen" / "bilder" / "a.png").write_bytes(b"\x89PNG")
    e.paket.name = "Speichertest neu"
    e.handout = "# Handout\n"
    neu = ed.LektionEntwurf(
        kp.Lektion(ordner="", titel="Übung: Einkaufsliste", dauer_minuten=20,
                   pruefung=kp.Pruefung(aufgabe="Liste da"),
                   start=kp.Start(skript="", als="benutzer")),
        anleitung="# Übung\n", quiz=[kp.Frage("Frage?", ["a", "b"], 1)],
        pruef_skript=ed.vorlage_datei_existiert("~/Kurs/einkaufsliste.txt", "Käse"),
        loesung_skript="mkdir -p ~/Kurs\necho Käse > ~/Kurs/einkaufsliste.txt\r\n",
        start_skript="mkdir -p ~/Kurs\n")
    e.lektionen.insert(0, neu)          # neue Lektion vor die erste
    gespeichert = ed.speichern(e)
    assert [lek.ordner for lek in gespeichert.lektionen] == ["01-uebung-einkaufsliste", "02-ankommen"]
    assert gespeichert.name == "Speichertest neu" and gespeichert.handout() == "# Handout\n"
    lek = gespeichert.lektionen[0]
    assert lek.pruefung.skript == "pruefung/pruefen.sh" and lek.pruefung.loesung == "pruefung/loesung.sh"
    assert b"\r\n" not in (lek.pfad / "pruefung/loesung.sh").read_bytes()
    assert lek.start.skript == "start/start.sh" and lek.quiz()[0].richtig == 1
    assert (gespeichert.pfad / "lektionen/02-ankommen/bilder/a.png").is_file()
    assert not (gespeichert.pfad / "lektionen/01-ankommen").exists()
    assert not kurslauf.zustimmung_noetig(gespeichert)       # eigene Skripte: schon zugestimmt

    # Prüfung auf eingebaut umstellen → altes Skript verschwindet
    e = ed.Entwurf.laden(gespeichert.pfad)
    e.lektionen[0].lektion.pruefung = kp.Pruefung(typ="agent-pc-laeuft")
    e.lektionen[0].lektion.start = None
    gespeichert = ed.speichern(e)
    assert not (gespeichert.pfad / "lektionen/01-uebung-einkaufsliste/pruefung").exists()
    assert not (gespeichert.pfad / "lektionen/01-uebung-einkaufsliste/start").exists()


def test_speichern_mit_fehler_aendert_nichts(datadir):
    p = ed.neu_anlegen("Fehlertest")
    vorher = {r.as_posix(): f.read_bytes() for f, r in kp._dateien(p.pfad)}
    e = ed.Entwurf.laden(p.pfad)
    e.paket.name = ""
    with pytest.raises(kp.PaketFehler, match="name"):
        ed.speichern(e)
    e = ed.Entwurf.laden(p.pfad)
    e.ablaufplan += "\nKontakt: ich@meine-firma.de\n"
    with pytest.raises(kp.GeheimnisGefunden):
        ed.speichern(e)
    assert {r.as_posix(): f.read_bytes() for f, r in kp._dateien(p.pfad)} == vorher


def test_speichern_in_git_ordner_behaelt_versteckte(datadir, tmp_path):
    d = paket_ordner(tmp_path)
    (d / ".git").mkdir()
    (d / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    e = ed.Entwurf.laden(d)
    e.lektionen.pop(0)
    p = ed.speichern(e)
    assert (d / ".git" / "HEAD").read_text() == "ref" and p.herkunft == kp.DATEI
    assert [lek.ordner for lek in p.lektionen] == ["01-uebung", "02-vorlage"]


# ---------------------------------------------------------------- Vorlagen für Prüfskripte
def test_vorlagen_pruefskripte(tmp_path):
    s = ed.vorlage_datei_existiert("~/Kurs/einkaufs liste.txt", "Käse 'alt'")
    assert "datei=\"$HOME\"/'Kurs/einkaufs liste.txt'" in s and "grep -qiF --" in s
    with pytest.raises(ValueError):
        ed.vorlage_datei_existiert("/etc/shadow")
    with pytest.raises(ValueError):
        ed.vorlage_datei_existiert("~/../x")
    assert "systemctl --user is-active" in ed.vorlage_dienst_laeuft("hermes-gateway.service", benutzer=True)
    with pytest.raises(ValueError):
        ed.vorlage_dienst_laeuft("x; rm -rf /")
    h = ed.vorlage_hermes_eingerichtet()
    assert ".env" not in h.replace("nie .env", "") and "auth.json" not in h.replace("oder auth.json", "")
    compile(h, "hermes.py", "exec")
    # Hermes-Prüfung gegen Beispieldateien – als Text übersetzt, nur hier im Test mit einem Fake-HOME ausgeführt
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    skript = tmp_path / "h.py"
    skript.write_text(h, encoding="utf-8")

    def lauf(config: str | None) -> int:
        cfg = home / ".hermes" / "config.yaml"
        cfg.unlink(missing_ok=True)
        if config is not None:
            cfg.write_text(config, encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}   # Windows: Path.home() = USERPROFILE
        return subprocess.run([sys.executable, "-I", str(skript)], env=env).returncode

    assert lauf(None) == 1
    assert lauf("model:\n  provider: nous\n  default: hermes-4-free\n") == 0
    assert lauf("model:\n  provider: nous\n  default: ''\n") == 1
    assert lauf("model:\n  extra:\n    provider: x\n    default: y\n") == 1
    assert lauf("# Kommentar\nmodel:\n  default: \"x\"  # Kommentar\n  provider: openrouter\nagent:\n  x: 1\n") == 0


# ---------------------------------------------------------------- Aus dem Agent-PC
class _Cfg:
    username = "agent"
    desktop = "xfce"
    apps = ["brave", "hermes", "gibtsnicht"]
    ram_mb, cpus, disk_gb = 8192, 4, 64
    keyboard, timezone, template = "de", "Europe/Berlin", ""


class _VM:
    def __init__(self, tmp_path):
        self.config = _Cfg()
        self.disk = tmp_path / "disk.qcow2"
        self.laeuft = True

    def is_running(self):
        return self.laeuft

    def qga_endpoint(self):
        return "unix:/nirgends"

    def qmp_endpoint(self):
        return "unix:/nirgends"


def test_rezept_aus_agent_pc(tmp_path):
    r = ed.rezept_aus_agent_pc(_VM(tmp_path), kp.Rezept(name="agent-x"))
    assert r.desktop == "xfce" and r.apps == ["brave", "hermes"] and r.ram_mb == 8192 and r.name == "agent-x"


def test_startskript_aus_agent_pc(tmp_path, monkeypatch):
    import base64
    import io
    import tarfile

    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tf:
        daten = b"Kaese\n"
        info = tarfile.TarInfo("Kurs/liste.txt")
        info.size = len(daten)
        tf.addfile(info, io.BytesIO(daten))
    aufrufe = []

    class GA:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, programm, args, stdin=None, timeout=0):
            aufrufe.append((programm, args))
            return 0, base64.b64encode(puffer.getvalue()).decode(), ""

    monkeypatch.setattr(ed.qemu, "GuestAgent", GA)
    monkeypatch.setattr(kurslauf, "bereit", lambda m: True)
    s = ed.startskript_aus_agent_pc(_VM(tmp_path), "~/Kurs")
    assert s.startswith("#!/bin/bash") and "BONYS_DATEN" in s
    programm, args = aufrufe[0]
    assert programm == "/usr/bin/timeout" and args[-1] == "Kurs" and "runuser" in args[3]
    with pytest.raises(ValueError):
        ed.startskript_aus_agent_pc(_VM(tmp_path), "/etc")
    # Das erzeugte Skript stellt den Ordner wieder her (hier mit einem Fake-HOME – im echten Betrieb im Agent-PC)
    if sys.platform.startswith("win"):
        return   # bash ist unter Windows nur der WSL-Platzhalter
    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(["bash", "-s"], input=s.encode(), env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, check=True)
    assert (home / "Kurs" / "liste.txt").read_text() == "Kaese\n"


# ---------------------------------------------------------------- PDF
@pytest.mark.skipif(not (shutil.which("pandoc") or Path("~/.local/bin/pandoc").expanduser().is_file())
                    or not (shutil.which("typst") or Path("~/.local/bin/typst").expanduser().is_file()),
                    reason="pandoc/typst fehlen")
def test_pdf(tmp_path):
    d = paket_ordner(tmp_path)
    (d / "handout.md").write_text("---\ntitle: Handout\n---\n\n## Kurs\n\n::: tipp\nTipp\n:::\n\n"
                                  "::: {.feld text=\"Kurscode\"}\n:::\n\n![Bild](bilder/x.png)\n", encoding="utf-8")
    (d / "ablaufplan.md").write_text("## Block 1\n\nText mit #raute und \"Anführung\"\n", encoding="utf-8")
    p = kp.laden(d)
    p.name = 'Name mit "Zeichen" #x'
    for welches in ("handout", "ablaufplan"):
        ziel = ed.pdf_bauen(p, welches, tmp_path / f"{welches}.pdf")
        assert ziel.read_bytes()[:5] == b"%PDF-"


def test_pdf_ohne_werkzeuge(tmp_path, monkeypatch):
    monkeypatch.setattr(ed.shutil, "which", lambda n: None)
    monkeypatch.setattr(ed.Path, "home", lambda: tmp_path)
    with pytest.raises(ed.WerkzeugFehlt, match="pandoc"):
        ed.pdf_bauen(kp.laden(paket_ordner(tmp_path)), "ablaufplan", tmp_path / "x.pdf")


# ---------------------------------------------------------------- Kurspaket prüfen
def test_pruefen_statisch(datadir, tmp_path):
    d = paket_ordner(tmp_path)
    m = ed.pruefen_statisch(d)
    assert m[0].stufe == ed.OK and not [x for x in m if x.stufe == ed.FEHLER]
    (d / "lektionen/01-ankommen/anleitung.md").write_text("![x](bilder/fehlt.png)\n[alt](http://x.de)\n",
                                                          encoding="utf-8")
    (d / "handout.md").write_text("Token: ghp_abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")
    daten = json.loads(json.dumps(PAKET))
    daten["rezept"]["apps"] = ["brave", "gibtsnicht"]
    daten["lektionen"][1]["pruefung"]["skript"] = "pruefung/p.py"
    (d / "paket.json").write_text(json.dumps(daten), encoding="utf-8")
    (d / "lektionen/02-uebung/pruefung/p.py").write_text("def (:\n")
    texte = [str(x) for x in ed.pruefen_statisch(d)]
    assert any("fehlt.png" in t and t.startswith("✗") for t in texte)
    assert any("ohne https" in t for t in texte)
    assert any("GitHub-Token" in t for t in texte)
    assert any("gibtsnicht" in t for t in texte)
    assert any("Syntaxfehler in Zeile 1" in t for t in texte)
    (d / "paket.json").write_text("{", encoding="utf-8")
    assert ed.pruefen_statisch(d)[0].stufe == ed.FEHLER


def test_links_pruefen(tmp_path):
    import urllib.error

    d = paket_ordner(tmp_path)
    (d / "handout.md").write_text("[a](https://gut.example) [b](https://weg.example) <https://gut.example>\n",
                                  encoding="utf-8")
    p = kp.laden(d)

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=0):
        if "weg" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "weg", {}, None)
        return R()

    m = ed.links_pruefen(p, opener=opener)
    assert len(m) == 1 and "404" in m[0].text and "weg.example" in m[0].text


def test_durchspielen_nur_im_agent_pc(datadir, tmp_path, monkeypatch):
    daten = json.loads(json.dumps(PAKET))
    daten["lektionen"][1]["pruefung"]["loesung"] = "pruefung/loesung.sh"
    daten["lektionen"][0]["start"] = {"skript": "start/s.sh"}
    d = paket_ordner(tmp_path, daten)
    (d / "lektionen/02-uebung/pruefung/loesung.sh").write_text("touch ~/x\n", encoding="utf-8")
    (d / "lektionen/01-ankommen/start").mkdir()
    (d / "lektionen/01-ankommen/start/s.sh").write_text("true\n", encoding="utf-8")
    p = kp.laden(d)
    machine = _VM(tmp_path)
    zustand = {"geloest": False}
    laeufe = []

    def ausfuehren(m, skript, als, zeitlimit, nur_syntax=False):
        assert m is machine          # nie auf diesem Rechner
        laeufe.append((skript.name, nur_syntax))
        if nur_syntax:
            return 0
        if skript.name == "loesung.sh":
            zustand["geloest"] = True
            return 0
        if skript.name == "datei.sh":
            return 0 if zustand["geloest"] else 1
        return 0

    schnapp = []
    monkeypatch.setattr(kurslauf, "im_agent_pc_ausfuehren", ausfuehren)
    monkeypatch.setattr(kurslauf, "bereit", lambda m: True)
    monkeypatch.setattr(kurslauf, "startzustand_speichern", lambda m, n: schnapp.append(("neu", n)))
    monkeypatch.setattr(kurslauf, "startzustand_loeschen", lambda m, n: schnapp.append(("weg", n)))
    monkeypatch.setattr(kurslauf, "_img", lambda *a: schnapp.append(a[:3]))
    monkeypatch.setattr(kurslauf.templates, "list_templates", lambda: [])
    machine.stop = lambda: setattr(machine, "laeuft", False)
    machine.start = lambda: setattr(machine, "laeuft", True)
    m = ed.durchspielen(machine, p)
    texte = [str(x) for x in m]
    assert any("Startskript läuft" in t for t in texte)
    assert any("erkennt die Lösung." in t for t in texte)
    assert any("zurückgesetzt" in t for t in texte) and machine.laeuft
    assert ("neu", ed.TEST_SCHNAPPSCHUSS) in schnapp and ("snapshot", "-a", ed.TEST_SCHNAPPSCHUSS) in schnapp
    assert ("s.sh", True) in laeufe and ("datei.sh", True) in laeufe
    assert not [t for t in texte if t.startswith("✗")]

    # Prüfung, die die Lösung nicht erkennt, und eine, die schon vorher erfüllt ist
    monkeypatch.setattr(kurslauf, "im_agent_pc_ausfuehren",
                        lambda m, s, a, z, nur_syntax=False: 1 if s.name == "datei.sh" else 0)
    texte = [str(x) for x in ed.durchspielen(machine, p, zuruecksetzen=False)]
    assert any("erkennt die Lösung nicht" in t for t in texte)
    monkeypatch.setattr(kurslauf, "im_agent_pc_ausfuehren", lambda m, s, a, z, nur_syntax=False: 0)
    p2 = replace(p, lektionen=[replace(p.lektionen[1], pruefung=replace(p.lektionen[1].pruefung, loesung=""))])
    texte = [str(x) for x in ed.durchspielen(machine, p2, zuruecksetzen=False)]
    assert any("schon vor der Übung erfüllt" in t for t in texte)


# ---------------------------------------------------------------- Fenster
@pytest.fixture
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])




def test_editor_fenster(qapp, datadir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from bonys_agents.trainer.gui import kurspaket_editor as ke

    def unerwartet(*a, **k):   # ein Meldungsfenster würde den Test (ohne Bildschirm) blockieren
        raise AssertionError(f"Unerwartete Meldung: {a[1:3]}")

    monkeypatch.setattr(QMessageBox, "warning", unerwartet)
    monkeypatch.setattr(QMessageBox, "critical", unerwartet)
    p = ed.neu_anlegen("Fenstertest")
    gespeichert = []
    f = ke.oeffnen(p.pfad, gespeichert.append)
    assert ke.oeffnen(p.pfad) is f                      # schon offen → dasselbe Fenster
    assert f.gliederung.count() == 5 and not f.geaendert()
    # Steckbrief ändern, Version erhöhen
    f.steckbrief.name.setText("Fenstertest neu")
    f.steckbrief.version.setText(ed.version_erhoehen(f.steckbrief.version.text(), "minor"))
    # Lektion hinzufügen (hinter der ersten), Titel, Prüfung aus Vorlage, Quiz
    f.gliederung.setCurrentRow(4)
    f.plus.click()
    assert f.gliederung.count() == 6 and f._lektion_index() == 1
    ls = f.lektion_seite
    ls.titel.setText("Übung Einkaufsliste")
    ls.typ.setCurrentIndex(ls.typ.findData(kp.SKRIPT))
    antworten = iter([("~/Kurs/liste.txt", True), ("Käse", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(antworten))
    ls._vorlage_datei()
    assert "liste.txt" in ls.pruef_skript.text.toPlainText()
    ls.loesung_skript.text.setPlainText("mkdir -p ~/Kurs && echo Käse > ~/Kurs/liste.txt\n")
    ls.quiz._neu()
    ls.quiz.frage.setText("Wo liegt die Liste?")
    ls.quiz.antworten.setPlainText("~/Kurs\n/etc")
    ls.quiz.richtig.setValue(1)
    # nach vorn schieben
    f.hoch.click()
    assert f._lektion_index() == 0
    assert f.geaendert()
    assert f.speichern()
    neu = kp.laden(p.pfad)
    assert neu.name == "Fenstertest neu" and neu.version == "0.2.0"
    assert [lek.ordner for lek in neu.lektionen] == ["01-uebung-einkaufsliste", "02-ankommen"]
    lek = neu.lektionen[0]
    assert lek.pruefung.skript == "pruefung/pruefen.sh" and lek.pruefung.loesung == "pruefung/loesung.sh"
    assert lek.quiz()[0].frage == "Wo liegt die Liste?"
    assert gespeichert and not f.geaendert()
    # Geheimnis im Ablaufplan: Meldung, nichts gespeichert
    meldungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: meldungen.append((a[1], a[2])))
    f.gliederung.setCurrentRow(2)
    f.ablaufplan.setzen("Schlüssel: sk-or-v1-0123456789abcdef0123456789abcdef\n")
    assert not f.speichern() and "Geheimnis" in meldungen[0][0]
    assert "sk-or" not in kp.laden(p.pfad).ablaufplan()
    # Lektion löschen
    f.gliederung.setCurrentRow(5)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    f.minus.click()
    f.gliederung.setCurrentRow(2)
    f.ablaufplan.setzen("# Ablaufplan\n")
    assert f.speichern() and len(kp.laden(p.pfad).lektionen) == 1
    # Bild in eine neue Lektion: versteckter Ordner bis zum Speichern, danach im Lektionsordner
    f.plus.click()
    le = f.entwurf.lektionen[f._lektion_index()]
    ordner = f.lektion_ordner(le)
    assert ordner.name.startswith(".neu-")
    (ordner / "bilder").mkdir()
    (ordner / "bilder" / "x.png").write_bytes(b"\x89PNG")
    assert f.speichern()
    assert (p.pfad / "lektionen/02-lektion-2/bilder/x.png").is_file()
    assert not list((p.pfad / "lektionen").glob(".neu-*"))
    f.close()
    _warten(qapp, lambda: str(p.pfad.resolve()) not in ke._FENSTER)


def test_bibliothek_knoepfe(qapp, datadir, tmp_path, monkeypatch):
    from bonys_agents.gui import kurspaket_bibliothek as kb
    from bonys_agents.trainer.gui import kurspaket_editor as ke

    basis = tmp_path / "mit"
    basis.mkdir()
    paket_ordner(basis)
    monkeypatch.setattr(kp, "mitgeliefert_dirs", lambda: [basis])
    s = kb.BibliothekSeite()
    neu, bearbeiten, duplizieren, ordner = s.editor_knoepfe
    assert bearbeiten.isEnabled()
    geoeffnet = []
    monkeypatch.setattr(ke, "oeffnen", lambda pfad, cb=None: geoeffnet.append(pfad))
    from PySide6.QtWidgets import QMessageBox

    # mitgeliefert → „Eigene Fassung“
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.setProperty("x", 1) or 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    bearbeiten.click()
    assert geoeffnet and kp.holen("test-paket").herkunft == kp.EIGEN
    s.deleteLater()


def test_pruefen_dialog_ohne_agent_pc(qapp, datadir, tmp_path, monkeypatch):
    from bonys_agents.trainer.gui import kurspaket_editor as ke

    monkeypatch.setattr(ke, "_laufende_agent_pcs", lambda: [])
    dlg = ke.PruefenDialog(kp.laden(paket_ordner(tmp_path)))
    dlg.start.click()
    _warten(qapp, lambda: dlg.lauf is None and dlg.ergebnis.toPlainText())
    assert dlg.ergebnis.toPlainText().startswith("✓ Format in Ordnung")
    dlg.deleteLater()
