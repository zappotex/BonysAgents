# SPDX-License-Identifier: GPL-3.0-or-later
"""Farben und Stylesheet der Desktop-App – passend zum Logo: Nachtblau, Orange, Eisblau."""

import re
from importlib import resources
from pathlib import Path


def resource(name: str) -> Path:
    """Pfad zu einer mitgelieferten Datei (Logo, Hintergrundbild …)."""
    return Path(str(resources.files("bonys_agents") / "resources" / name))


def _url(name: str) -> str:
    """Pfad für url(...) im Stylesheet – mit Schrägstrichen, auch unter Windows, und in Anführungszeichen.

    Ohne Anführungszeichen bricht schon ein Apostroph im Pfad das ganze Stylesheet – auf dem Mac liegt
    alles in „Bony's Agents.app“ („Could not parse application stylesheet“, die App bliebe ungestaltet).
    """
    path = resource(name).as_posix().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{path}"'


BG = "#0d141d"
PANEL = "#162130"
PANEL_2 = "#1f2d40"
BORDER = "#2b3c52"
TEXT = "#e8eef5"
MUTED = "#93a4b8"
ACCENT = "#f5a623"       # Orange – Hauptknöpfe
ACCENT_DARK = "#d98c0f"
HIGHLIGHT = "#3fa9f5"    # Eisblau – Auswahl, Fokus, Fortschritt
OK = "#4cc38a"           # Grün – läuft / alles in Ordnung
WARN = "#ffd166"
DANGER = "#ef6b6b"

# Leicht durchscheinend, damit das Hintergrundbild im Hauptfenster dezent sichtbar bleibt.
PANEL_GLASS = "rgba(22, 33, 48, 0.70)"
PANEL_2_GLASS = "rgba(31, 45, 64, 0.85)"
CONSOLE_GLASS = "rgba(7, 11, 16, 0.82)"
BACKDROP_DIM = (13, 20, 29, 166)  # Abdunklung des Hintergrundbilds (RGBA, ~65 %)

# Anzeigegröße in Prozent (Menü „Anzeigegröße“, Strg + Plus/Minus/0)
ZOOM_STEPS = (80, 90, 100, 110, 125, 150)
DEFAULT_ZOOM = 100
_zoom = DEFAULT_ZOOM


def zoom() -> int:
    return _zoom


def px(value: float) -> int:
    """Pixelwert passend zur gewählten Anzeigegröße."""
    return max(1, round(value * _zoom / 100))


def saved_zoom() -> int:
    from bonys_agents import storage

    try:
        z = int(storage.load_settings().get("zoom", DEFAULT_ZOOM))
    except (TypeError, ValueError):
        z = DEFAULT_ZOOM
    return z if z in ZOOM_STEPS else DEFAULT_ZOOM


def set_zoom(app, percent: int, save: bool = True) -> int:
    """Anzeigegröße wählen (nächstgelegene Stufe), sofort anwenden und merken."""
    global _zoom
    _zoom = min(ZOOM_STEPS, key=lambda z: abs(z - percent))
    app.setStyleSheet(stylesheet())
    if save:
        from bonys_agents import storage

        s = storage.load_settings()
        s["zoom"] = _zoom
        storage.save_settings(s)
    return _zoom


def step_zoom(app, direction: int) -> int:
    """Eine Stufe größer (+1) oder kleiner (-1); 0 = zurück auf 100 %."""
    if direction == 0:
        return set_zoom(app, DEFAULT_ZOOM)
    i = ZOOM_STEPS.index(_zoom) + direction
    return set_zoom(app, ZOOM_STEPS[max(0, min(len(ZOOM_STEPS) - 1, i))])


def stylesheet() -> str:
    """Stylesheet mit allen Größen (Schrift, Abstände) im Maßstab der Anzeigegröße.

    Linien bis 3 px bleiben, wie sie sind – sonst würden Rahmen bei 80 % verschwinden.
    """
    return re.sub(r"(\d+)px", lambda m: f"{px(int(m[1])) if int(m[1]) > 3 else m[1]}px", STYLESHEET)


def apply(app) -> None:
    """Fusion-Stil mit dunkler Palette und Stylesheet.

    Die Palette braucht Fusion für Kontrollkästchen, Pfeile und Bildlaufleisten,
    die das Stylesheet nicht selbst zeichnet.
    """
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, PANEL_2),
        (QPalette.AlternateBase, PANEL), (QPalette.Text, TEXT), (QPalette.Button, PANEL_2),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, HIGHLIGHT), (QPalette.HighlightedText, "#04121d"),
        (QPalette.ToolTipBase, BG), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, MUTED),
        (QPalette.Light, BORDER), (QPalette.Midlight, PANEL_2), (QPalette.Mid, BORDER),
        (QPalette.Dark, "#070b10"), (QPalette.Shadow, "#000000"), (QPalette.Link, HIGHLIGHT),
    ):
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(MUTED))
    app.setPalette(pal)
    set_zoom(app, saved_zoom(), save=False)


STATUS_COLORS = {
    "läuft": OK,
    "wird eingerichtet": WARN,
    "startet mit Desktop": OK,
    "Einrichtung abgebrochen": DANGER,
    "wird heruntergefahren": WARN,
    "gestoppt": MUTED,
    "nicht verfügbar – Vorlage fehlt": DANGER,
}

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-size: 14px;
}}
QMainWindow, QDialog, QMessageBox, QMenu, QToolTip, QStatusBar {{ background: {BG}; }}
QToolTip {{ border: 1px solid {BORDER}; padding: 4px; }}
QLabel, QCheckBox {{ background: transparent; }}
QLabel#Title {{ font-size: 22px; font-weight: 600; }}
QLabel#Tagline {{ color: {HIGHLIGHT}; font-size: 13px; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Section {{ color: {MUTED}; font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
QFrame#Card {{
    background: {PANEL_GLASS};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QListWidget {{
    background: {PANEL_GLASS};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{ padding: 10px 8px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {PANEL_2}; color: {TEXT}; border-left: 3px solid {HIGHLIGHT}; }}
QListWidget::item:hover {{ background: {PANEL_2_GLASS}; }}
QPushButton {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton:hover {{ border-color: {HIGHLIGHT}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {PANEL_2}; }}
QPushButton#Primary {{
    background: {ACCENT};
    color: #1d1200;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#Primary:disabled {{ background: {PANEL_2}; color: {MUTED}; }}
QPushButton#Small {{ padding: 4px 12px; font-size: 13px; }}
QPushButton#Tab {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0; padding: 4px 6px; color: {MUTED}; font-size: 12px; font-weight: 600; letter-spacing: 1px;
}}
QPushButton#Tab:checked {{ color: {TEXT}; border-bottom-color: {HIGHLIGHT}; }}
QPushButton#Tab:hover {{ color: {TEXT}; }}
QPushButton#Quiet {{ background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 8px 10px; }}
QPushButton#Quiet:hover {{ color: {TEXT}; border-color: {BORDER}; }}
QLabel#Percent {{ color: {HIGHLIGHT}; font-weight: 600; }}
QFrame#Hint {{
    background: rgba(63, 169, 245, 0.12);
    border: 1px solid rgba(63, 169, 245, 0.45);
    border-radius: 8px;
}}
QFrame#Hint[tone="danger"] {{
    background: rgba(239, 107, 107, 0.12);
    border-color: rgba(239, 107, 107, 0.5);
}}
QPushButton#Danger {{ color: {DANGER}; }}
QPushButton#Danger:hover {{ border-color: {DANGER}; }}
QLineEdit, QSpinBox, QComboBox {{
    min-height: 22px;
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {HIGHLIGHT}; }}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {PANEL_2};
    selection-color: {TEXT};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollArea#Glass {{ background: {PANEL_GLASS}; border: 1px solid {BORDER}; border-radius: 8px; }}
QPlainTextEdit {{
    background: {CONSOLE_GLASS};
    border: 1px solid {BORDER};
    border-radius: 8px;
    font-family: "JetBrains Mono", "Cascadia Mono", "Menlo", "Consolas", monospace;
    font-size: 12px;
    color: #c3d0dd;
}}
QProgressBar {{
    background: {PANEL_2};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {HIGHLIGHT}; border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 6px; background: {PANEL_2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {HIGHLIGHT}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 16px; margin: -6px 0; border-radius: 8px;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    background: {PANEL_2}; border: 1px solid {MUTED}; border-radius: 4px;
}}
QCheckBox::indicator:hover {{ border-color: {HIGHLIGHT}; }}
QCheckBox::indicator:checked {{ background: {HIGHLIGHT}; border-color: {HIGHLIGHT}; image: url({_url("check.svg")}); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({_url("arrow-down.svg")}); width: 12px; height: 12px; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 22px; }}
QSpinBox::up-arrow {{ image: url({_url("arrow-up.svg")}); width: 12px; height: 12px; }}
QSpinBox::down-arrow {{ image: url({_url("arrow-down.svg")}); width: 12px; height: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {BORDER}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
