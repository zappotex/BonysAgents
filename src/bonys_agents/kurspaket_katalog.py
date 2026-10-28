# SPDX-License-Identifier: GPL-3.0-or-later
"""Öffentlicher Community-Katalog aus veröffentlichten Kursportal-Einreichungen.

Erzeugt dasselbe ``index.json``-Format wie der bestehende Katalog (``kurspaket.katalog_laden``). Aufgenommen werden
nur Einreichungen im Status ``published``; je Paket-ID gilt nur die neueste Version. Im Katalog stehen ausschließlich
bereinigte Paketdaten – kein Autor, kein Prüfbericht, keine Fundstellen. Es wird nur geschrieben, nichts ausgeführt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from bonys_agents import kurspaket, kurspaket_moderation as mod, kurspaket_portal as portal

PAKETE = "pakete"
INDEX = "index.json"


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(t) for t in text.split("."))


def _veroeffentlicht(ablage: mod.Moderation) -> dict[str, tuple[str, dict]]:
    """Neueste veröffentlichte Version je Paket-ID: ``id -> (submission_id, bericht)``."""
    neueste: dict[str, tuple[str, dict]] = {}
    for sid in ablage.ids():
        try:
            ablage.verlauf_pruefen(sid)
            if ablage.status(sid) != mod.PUBLISHED:
                continue
            b = ablage.bericht(sid) or {}
            if not (kurspaket.ID_RE.match(b.get("paket_id", "")) and kurspaket.VERSION_RE.match(b.get("version", ""))):
                continue
            if b["paket_id"] in ablage.reserviert:
                continue      # ID eines mitgelieferten Pakets (z. B. älter eingereicht): nie im Katalog
            original = ablage.wurzel / sid / "original.bonyspaket"
            if not original.is_file() or portal._sha256(original) != b.get("sha256"):
                continue      # Datei fehlt oder wurde verändert: nicht ausliefern
        except mod.ModerationsFehler:
            continue
        alt = neueste.get(b["paket_id"])
        if alt is None or _version(b["version"]) > _version(alt[1]["version"]):
            neueste[b["paket_id"]] = (sid, b)
    return neueste


def _dateiname(b: dict) -> str:
    return f"{b['paket_id']}-{b['version']}{kurspaket.SUFFIX}"


def katalog_erzeugen(ablage: mod.Moderation) -> dict:
    """``index.json``-Inhalt; ``datei`` ist relativ zur Index-Adresse."""
    eintraege = []
    veroeff = _veroeffentlicht(ablage)
    for kid in sorted(veroeff):
        _, b = veroeff[kid]
        eintraege.append({
            "id": kid, "name": b.get("name") or kid, "version": b["version"],
            "stufe": b.get("stufe") if b.get("stufe") in kurspaket.STUFEN else "anfaenger",
            "beschreibung": b.get("beschreibung", ""), "dauer_minuten": int(b.get("dauer_minuten") or 0),
            "datei": f"{PAKETE}/{_dateiname(b)}", "sha256": b["sha256"], "groesse": int(b["groesse"]),
            "community": True})
    return {"format": kurspaket.KATALOG_FORMAT, "pakete": eintraege}


def katalog_schreiben(ablage: mod.Moderation, ziel: Path) -> dict:
    """Schreibt Pakete und ``index.json`` nach ``ziel``; nicht mehr veröffentlichte Dateien werden entfernt."""
    ziel = Path(ziel)
    veroeff = _veroeffentlicht(ablage)
    pakete = ziel / PAKETE
    pakete.mkdir(parents=True, exist_ok=True)
    soll = set()
    for sid, b in veroeff.values():
        name = _dateiname(b)
        soll.add(name)
        if not (pakete / name).is_file() or portal._sha256(pakete / name) != b["sha256"]:
            tmp = pakete / (name + ".tmp")
            shutil.copyfile(ablage.wurzel / sid / "original.bonyspaket", tmp)
            tmp.replace(pakete / name)
    for alt in pakete.iterdir():
        if alt.name not in soll:
            alt.unlink()
    index = katalog_erzeugen(ablage)
    tmp = ziel / (INDEX + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(ziel / INDEX)
    return index
