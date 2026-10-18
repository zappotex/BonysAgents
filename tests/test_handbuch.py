# SPDX-License-Identifier: GPL-3.0-or-later
"""Handbücher (docs/handbuch/): Bilder vorhanden, Menü-Verweis passt zu den Dateinamen der Release-Aktion."""

import re
from pathlib import Path

import pytest

HANDBUCH = Path(__file__).resolve().parents[1] / "docs" / "handbuch"
QUELLEN = sorted(HANDBUCH.glob("*.md"))


def _bilder(text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\((bilder/[^)\s]+)\)", text)


@pytest.mark.parametrize("quelle", [q for q in QUELLEN if q.name != "README.md"], ids=lambda q: q.name)
def test_automatische_bilder_sind_da(quelle):
    """Jedes Bild außer den selbst gemachten (bilder/eigene/) erzeugt bildschirmfotos.py – es muss eingecheckt sein."""
    fehlen = [b for b in _bilder(quelle.read_text("utf-8"))
              if not b.startswith("bilder/eigene/") and not (HANDBUCH / b).is_file()]
    assert not fehlen, f"{quelle.name}: {fehlen} – docs/handbuch/erstellen.sh --nur-bilder"


def test_selbst_gemachte_bilder_sind_beschrieben():
    """Jedes Bild aus bilder/eigene/ steht in der Liste in docs/handbuch/README.md (was darauf zu sehen sein soll)."""
    liste = (HANDBUCH / "README.md").read_text("utf-8")
    for quelle in QUELLEN:
        for b in _bilder(quelle.read_text("utf-8")):
            if b.startswith("bilder/eigene/"):
                assert f"`{b.removeprefix('bilder/eigene/')}`" in liste, f"{b} fehlt in docs/handbuch/README.md"


def test_menue_verweist_auf_die_pdfs_der_release_aktion():
    pytest.importorskip("PySide6.QtWidgets")
    from bonys_agents import __version__
    from bonys_agents.gui.main_window import handbuch_url

    skript = (HANDBUCH / "erstellen.sh").read_text("utf-8")
    namen = re.findall(r"^\s*bauen \S+\.md (\S+) ", skript, re.M)
    assert "Benutzerhandbuch" in namen and "Kursleiter-Handbuch" in namen
    for name in ("Benutzerhandbuch", "Kursleiter-Handbuch"):
        url = handbuch_url(name)
        assert url.endswith(f"/releases/download/v{__version__}/BonysAgents-{name}-{__version__}.pdf")
    assert '/BonysAgents-$name-$VERSION.pdf"' in skript
