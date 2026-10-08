# SPDX-License-Identifier: GPL-3.0-or-later
"""Fortschritt in Prozent: vom Image-Download bis zum fertigen Desktop.

Die Phasen sind grob nach ihrer Dauer gewichtet. Innerhalb eines Einrichtungsschritts
wandert der Balken anhand der Konsolenausgabe weiter (apt: Holen/Entpacken/Einrichten).
Alles hier ist reine Berechnung ohne Seiteneffekte – so lässt es sich gut testen.
"""

from __future__ import annotations

import math
import re

from bonys_agents import apps, cloudinit, desktops

# Phasen beim Anlegen (auf dem Host), in Prozent
DOWNLOAD = (0.0, 15.0)
DISK = (15.0, 18.0)
BOOT = (18.0, 22.0)     # vom QEMU-Start bis zum ersten Einrichtungsschritt
SETUP = (22.0, 97.0)    # alle Einrichtungsschritte im Gast
FINISH = (97.0, 100.0)  # Ausschalten und Neustart mit Desktop

# Relative Dauer der Einrichtungsschritte; die Apps bringen ihr Gewicht selbst mit (AppSpec.weight).
BASE_STEP_WEIGHTS = [5.0, 38.0]  # Sprache/Tastatur, Desktop (Cinnamon; je Desktop: DesktopSpec.weight)
APP_DEFAULT = 10.0  # für unbekannte IDs (z. B. aus einer neueren Version)

_APT_SUMMARY = re.compile(r"(\d+) (?:newly installed|neu installiert)")
# Englisch und Deutsch: „Get:/Holen:“, „Unpacking/Entpacken von“, „Setting up/… wird eingerichtet“
_APT_ACTION = re.compile(r"^(?:Get:|Holen:|Unpacking |Entpacken von |Setting up |.* wird eingerichtet)", re.M)
_STEP = re.compile(rf"{cloudinit.STEP_MARKER} (\d+)/(\d+)")

# Steuerzeichen von Terminals (Farben ESC[0;32m, ESC[?7h, Abfragen wie ESC[6n …) – die serielle
# Konsole des Gasts enthält sie, in der Anzeige der App sind sie nur störender Zeichensalat.
_ANSI = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]"          # CSI: ESC[ … Buchstabe
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)?"     # OSC: ESC] … BEL bzw. ESC\
    r"|[PX^_][^\x1b]*(?:\x1b\\)?"           # DCS, SOS, PM, APC
    r"|[()*+][0-9A-Za-z]"                  # Zeichensatz wählen
    r"|[@-Z\\-_0-9=<>c])"                  # einzelne Zeichen wie ESC7, ESC=, ESCc
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    """Escape-Sequenzen und Steuerzeichen entfernen; überschriebene Zeilen (\\r) wie im Terminal."""
    text = _ANSI.sub("", text).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        if "\r" in line:
            line = next((seg for seg in reversed(line.split("\r")) if seg), "")
        lines.append(_CONTROL.sub("", line))
    return "\n".join(lines)


def step_ranges(app_ids: list[str], desktop: str = desktops.DEFAULT) -> list[tuple[float, float]]:
    """Prozentbereich jedes Einrichtungsschritts – abgewählte Apps werden neu verteilt."""
    desk = desktops.DESKTOPS[desktop].weight if desktop in desktops.DESKTOPS else BASE_STEP_WEIGHTS[1]
    weights = [BASE_STEP_WEIGHTS[0], desk] + [apps.APPS[a].weight if a in apps.APPS else APP_DEFAULT for a in app_ids]
    total = sum(weights)
    lo, span = SETUP[0], SETUP[1] - SETUP[0]
    ranges = []
    for w in weights:
        hi = lo + span * w / total
        ranges.append((lo, hi))
        lo = hi
    return ranges


def _lerp(rng: tuple[float, float], frac: float) -> float:
    frac = min(max(frac, 0.0), 1.0)
    return rng[0] + (rng[1] - rng[0]) * frac


def creation_percent(phase: str, frac: float) -> float:
    """Fortschritt beim Anlegen (Callback von vm.create)."""
    if phase == "download":
        return _lerp(DOWNLOAD, frac)
    if phase == "disk":
        return _lerp(DISK, frac)
    if phase in ("seed", "done", "start"):
        return DISK[1]
    return 0.0


def _asymptotic(lines: int, scale: float, cap: float = 0.9) -> float:
    """Ohne genaue Zahlen: nähert sich langsam ``cap``, bleibt aber nie stehen."""
    return cap * (1.0 - math.exp(-lines / scale))


def step_fraction(step_text: str) -> float:
    """Wie weit ein einzelner Schritt ist (0..1), aus seiner Konsolenausgabe geschätzt."""
    summaries = list(_APT_SUMMARY.finditer(step_text))
    if summaries:
        last = summaries[-1]
        packages = int(last.group(1))
        if packages:
            # Jedes Paket: einmal holen, entpacken, einrichten.
            done = len(_APT_ACTION.findall(step_text[last.end():]))
            return min(done / (3 * packages), 0.98)
    lines = step_text.count("\n")
    return _asymptotic(lines, scale=200.0)


def setup_percent(console: str, app_ids: list[str], ready: bool, pending: bool = False,
                  running: bool = True, resume_step: int = 0, desktop: str = desktops.DEFAULT) -> float:
    """Gesamtfortschritt (0..100) aus der Konsolenausgabe des Gasts.

    ``resume_step``: zuletzt gesehener Schritt vor einem Abbruch – nach dem Neustart steht der
    Balken dann an dessen Anfang statt wieder beim Hochfahren.
    """
    if ready:
        if not pending:
            return 100.0
        return FINISH[0] if running else 99.0
    markers = list(_STEP.finditer(console))
    if not markers and resume_step:
        ranges = step_ranges(app_ids, desktop)
        if 1 <= resume_step <= len(ranges):
            return ranges[resume_step - 1][0]
    if not markers:
        # Bootvorgang: Kernel- und cloud-init-Zeilen bis zum ersten Schritt
        return _lerp(BOOT, _asymptotic(console.count("\n"), scale=300.0, cap=0.95))
    last = markers[-1]
    step = int(last.group(1))
    ranges = step_ranges(app_ids, desktop)
    if not 1 <= step <= len(ranges):  # passt nicht zur Konfiguration – nur grob anzeigen
        return _lerp(SETUP, (step - 1) / max(int(last.group(2)), 1))
    return _lerp(ranges[step - 1], step_fraction(console[last.end():]))


def eta_seconds(t0: float, p0: float, t: float, p: float,
                min_progress: float = 3.0, min_elapsed: float = 60.0) -> float | None:
    """Grobe Restzeit aus dem bisherigen Tempo – None, solange zu wenig Daten da sind."""
    elapsed, done = t - t0, p - p0
    if elapsed < min_elapsed or done < min_progress or p >= 100:
        return None
    return (100.0 - p) * elapsed / done


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return ""
    minutes = math.ceil(seconds / 60)
    if minutes <= 1:
        return "noch knapp 1 Min."
    if minutes < 60:
        return f"noch ca. {minutes} Min."
    h, m = divmod(minutes, 60)
    return f"noch ca. {h} Std. {m} Min." if m else f"noch ca. {h} Std."
