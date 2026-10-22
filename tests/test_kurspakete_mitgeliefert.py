# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitgelieferte Kurspakete (``kurspakete/``): gültig, ohne Zugangsdaten, Prüfskripte tun, was sie sollen, und das
Pack-Skript der Release-Aktion (``packaging/kurspakete.py``) liefert signierte Pakete samt ``index.json``."""

import base64
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import kurslauf, kurspaket, signing

ROOT = Path(__file__).resolve().parent.parent
QUELLE = ROOT / "kurspakete"
HERMES = QUELLE / "einfuehrung-hermes-agent"
MCP = QUELLE / "was-ist-ein-mcp-server"
N8N = QUELLE / "n8n-grundlagen"


def _ordner() -> list[Path]:
    return sorted(p for p in QUELLE.iterdir() if (p / kurspaket.PAKET_JSON).is_file())


def test_alle_gueltig_und_ohne_geheimnisse():
    ids = []
    for o in _ordner():
        p = kurspaket.laden(o)
        ids.append(p.id)
        assert p.id == o.name
        assert kurspaket.geheimnisse_suchen(o) == [], o.name
        assert p.lizenz == "CC-BY-SA-4.0" and not p.rezept.unbekannte_apps()
        for lek in p.lektionen:
            lek.quiz()
            assert lek.anleitung().strip()
    assert "einfuehrung-hermes-agent" in ids and len(ids) == 8
    fertig = {kurspaket.laden(o).id for o in _ordner() if not kurspaket.laden(o).entwurf}
    assert fertig == {"einfuehrung-hermes-agent", "was-ist-ein-mcp-server", "n8n-grundlagen"}   # dazu fünf Entwürfe
    assert {kurspaket.laden(o).stufe for o in _ordner()} == {"anfaenger", "fortgeschritten", "experte"}


def test_werden_als_mitgeliefert_gefunden():
    assert QUELLE in kurspaket.mitgeliefert_dirs()


def test_hermes_paket():
    p = kurspaket.laden(HERMES)
    assert p.dauer_minuten == 120 and p.pause_minuten == 10 and len(p.lektionen) == 9
    # Zeitplan des Kurses: Lektionen 1–8 + Pause = 120 Minuten, Lektion 9 ist der Zusatz
    assert sum(lek.dauer_minuten for lek in p.lektionen[:8]) + p.pause_minuten == 120
    assert [lek.pruefung.typ for lek in p.lektionen if lek.pruefung] == ["skript", "skript", "vorlage-vorhanden"]
    assert len(p.lernziele) == 6 and "kostenlos" in p.kosten
    text = (HERMES / "ablaufplan.md").read_text() + (HERMES / "handout.md").read_text()
    assert "Nous" in text and "hermes --tui" in text and "/tools" in text and "64K" in text
    assert "<!--" not in text   # Bony's Agents zeigt kein HTML


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Prüfskripte sind für Linux im Agent-PC")
def test_hermes_pruefskripte_in_einem_test_home(tmp_path):
    """Die Skripte laufen sonst nur im Agent-PC – hier nur zum Test in einem leeren Ordner als HOME."""
    lek = HERMES / "lektionen"
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}

    def rc(*befehl) -> int:
        return subprocess.run(list(befehl), env=env, cwd=tmp_path, capture_output=True, timeout=30).returncode

    hermes = lek / "03-hermes-startklar" / "pruefung" / "hermes-eingerichtet.py"
    assert rc(sys.executable, "-I", str(hermes)) == 1
    (home / ".hermes" / ".env").write_text("OPENROUTER_API_KEY=x\n", encoding="utf-8")   # Schlüssel genügt nicht
    assert rc(sys.executable, "-I", str(hermes)) == 1
    # Standard-Einstellung eines frisch installierten Hermes: „auto“ ist noch keine Wahl
    frisch = 'model:\n  default: "anthropic/claude-opus-4.6"\n  provider: "auto"\n'
    (home / ".hermes" / "config.yaml").write_text(frisch, encoding="utf-8")
    assert rc(sys.executable, "-I", str(hermes)) == 1
    (home / ".hermes" / "config.yaml").write_text("model:\n  provider: nous\n  default: hermes-free\n",
                                                  encoding="utf-8")
    assert rc(sys.executable, "-I", str(hermes)) == 0
    assert ".env" not in [z for z in hermes.read_text().splitlines() if not z.lstrip().startswith("#")][0]

    if shutil.which("bash") is None:
        pytest.skip("ohne bash")
    liste = lek / "04-uebung-dateien" / "pruefung"
    start = lek / "04-uebung-dateien" / "start" / "kurs-ordner.sh"
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 1
    assert rc("bash", str(start)) == 0 and (home / "Kurs").is_dir()
    (home / "Kurs" / "einkaufsliste.txt").write_text("Brot\nMilch\n", encoding="utf-8")
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 1
    assert rc("bash", str(liste / "loesung.sh")) == 0
    assert rc("bash", str(liste / "einkaufsliste.sh")) == 0


def test_reihe_agenten_mcp_n8n():
    """Kurs 1 und 3 der Reihe „Agenten, MCP-Apps und n8n“: brauchen 0.24.0 (n8n, Agenten-Apps), je 90 Minuten."""
    mcp, n8n = kurspaket.laden(MCP), kurspaket.laden(N8N)
    for p in (mcp, n8n):
        assert p.min_version == "0.24.0" and p.dauer_minuten == 90
        assert sum(lek.dauer_minuten for lek in p.lektionen) == 90
    assert mcp.rezept.apps == ["brave", "hermes", "agenten-apps"] and n8n.rezept.apps == ["brave", "n8n"]
    # n8n-Prüfungen lesen die Datenbank im Docker-Volume – das geht nur als root
    assert {lek.pruefung.als for lek in n8n.lektionen if lek.pruefung and "n8n" in lek.pruefung.skript} == {"root"}
    text = (N8N / "lektionen" / "05-erster-workflow" / "anleitung.md").read_text()
    assert "Publish" in text and "RSS Feed Trigger" in text and "Execute step" in text
    assert "Webseiten abrufen" not in "".join(p.read_text() for p in MCP.rglob("*.md"))   # Eintrag ausgesetzt


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Prüfskripte sind für Linux im Agent-PC")
def test_reihe_pruefskripte_in_einem_test_home(tmp_path):
    """Wie oben: Skripte in einem leeren Ordner als HOME. Die n8n-Datenbank gibt es hier nicht → „noch nicht“."""
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}

    def rc(*befehl) -> int:
        return subprocess.run(list(befehl), env=env, cwd=tmp_path, capture_output=True, timeout=60).returncode

    lek = MCP / "lektionen"
    pdfcraft = lek / "04-pdfcraft-einrichten" / "pruefung" / "pdfcraft-eingerichtet.py"
    assert rc(sys.executable, "-I", str(pdfcraft)) == 1
    cli = home / ".local" / "bin" / "pdfcraft-cli"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    (home / ".hermes").mkdir()
    konfig = home / ".hermes" / "config.yaml"
    konfig.write_text("model:\n  provider: nous\nmcp_servers:\n  gridcraft:\n    command: gridcraft-cli\n")
    assert rc(sys.executable, "-I", str(pdfcraft)) == 1
    konfig.write_text(konfig.read_text() + "  pdfcraft:\n    command: /x/pdfcraft-cli\n    args: [mcp]\nweiter: 1\n")
    assert rc(sys.executable, "-I", str(pdfcraft)) == 0

    start = lek / "02-kopf-ohne-haende" / "start" / "beispiel-pdfs.py"
    assert (lek / "05-uebung-pdfs" / "start" / "beispiel-pdfs.py").read_bytes() == start.read_bytes()
    assert rc(sys.executable, "-I", str(start)) == 0 and rc(sys.executable, "-I", str(start)) == 0
    pdf = home / "Agent-Dateien" / "pdf"
    assert sorted(p.name for p in pdf.iterdir()) == ["protokoll.pdf", "rechnung-april.pdf", "rechnung-maerz.pdf"]
    assert all(p.read_bytes().startswith(b"%PDF-1.4") for p in pdf.iterdir())
    gesamt = lek / "05-uebung-pdfs" / "pruefung"
    assert rc(sys.executable, "-I", str(gesamt / "rechnungen-gesamt.py")) == 1
    if shutil.which("pdfunite") and shutil.which("pdfinfo") and shutil.which("pdftotext"):
        assert rc("bash", str(gesamt / "loesung.sh")) == 0
        assert rc(sys.executable, "-I", str(gesamt / "rechnungen-gesamt.py")) == 0
        (pdf / "rechnung-april.pdf").replace(pdf / "rechnungen-gesamt.pdf")   # nur eine Seite
        assert rc(sys.executable, "-I", str(gesamt / "rechnungen-gesamt.py")) == 1

    n8n = N8N / "lektionen"
    assert rc(sys.executable, "-I", str(n8n / "03-n8n-oeffnen" / "pruefung" / "n8n-konto.py")) == 1
    assert rc(sys.executable, "-I", str(n8n / "05-erster-workflow" / "pruefung" / "workflow-aktiv.py")) == 1
    export = n8n / "07-sichern" / "pruefung"
    assert rc(sys.executable, "-I", str(export / "export-vorhanden.py")) == 1
    (home / "Downloads").mkdir()
    (home / "Downloads" / "anderes.json").write_text('{"nodes": [{"type": "n8n-nodes-base.telegram"}]}')
    assert rc(sys.executable, "-I", str(export / "export-vorhanden.py")) == 1
    (home / "Downloads" / "anderes.json").write_text('[{"nodes": [{"type": "n8n-nodes-base.rssFeedReadTrigger"}]}]')
    assert rc(sys.executable, "-I", str(export / "export-vorhanden.py")) == 0   # Liste wie bei export:workflow
    (home / "Downloads" / "anderes.json").unlink()
    if shutil.which("bash"):
        assert rc("bash", str(export / "loesung.sh")) == 0
        assert rc(sys.executable, "-I", str(export / "export-vorhanden.py")) == 0


@pytest.mark.kursleiter
def test_statische_pruefung_wie_im_editor():
    from bonys_agents.trainer import kurspaket_editor as editor

    for o in _ordner():
        meldungen = editor.pruefen_statisch(o)
        assert not [m for m in meldungen if m.stufe in (editor.FEHLER, editor.WARNUNG)], (o.name, meldungen)


def _skript():
    spec = importlib.util.spec_from_file_location("kurspakete_packen", ROOT / "packaging" / "kurspakete.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_pack_skript_der_release_aktion(tmp_path):
    secret, key_id = bytes(range(32)), b"\x01\x02\x03\x04\x05\x06\x07\x08"
    public = base64.b64encode(b"Ed" + key_id + signing.ed25519_public_key(secret)).decode()
    m = _skript()
    bau = tmp_path / "bau"
    ordner = m.vorbereiten(bau)
    assert len(ordner) == 8
    # ohne Signatur bricht es ab
    with pytest.raises(SystemExit, match="Signatur"):
        m.packen(bau, tmp_path / "out", public)
    for o in ordner:
        daten = (o / kurslauf.PRUEFSUMMEN).read_bytes()
        (o / kurslauf.SIGNATUR).write_text(signing.sign(daten, secret, key_id, "Kurspaket von Bony's Agents v0"),
                                           encoding="utf-8")
    index = m.packen(bau, tmp_path / "out", public)
    katalog = json.loads(index.read_text())
    assert katalog["format"] == kurspaket.KATALOG_FORMAT and len(katalog["pakete"]) == 8
    hermes = next(e for e in katalog["pakete"] if e["id"] == "einfuehrung-hermes-agent")
    assert hermes["datei"] == "pakete/einfuehrung-hermes-agent-1.0.1.bonyspaket" and "entwurf" not in hermes
    datei = tmp_path / "out" / "einfuehrung-hermes-agent-1.0.1.bonyspaket"
    assert hermes["groesse"] == datei.stat().st_size

    # Die App liest die index.json wie aus dem Repo – und die Signatur übersteht den Import
    class Antwort(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    eintraege = kurspaket.katalog_laden("https://example.org/index.json",
                                        opener=lambda req, timeout: Antwort(index.read_bytes()))
    assert {e.id for e in eintraege} == {o.name for o in ordner}
    assert next(e for e in eintraege if e.id == "hermes-ueber-telegram").entwurf
    ziel = tmp_path / "entpackt"
    kurspaket.entpacken(datei, ziel)
    assert kurslauf.signatur_pruefen(kurspaket.laden(ziel), public)


def test_handbuch_baut_den_beispielkurs_aus_dem_paket():
    skript = (ROOT / "docs" / "handbuch" / "erstellen.sh").read_text()
    assert "kurspakete/einfuehrung-hermes-agent" in skript
    assert not (ROOT / "docs" / "handbuch" / "beispielkurs.md").exists()   # nur eine Quelle
