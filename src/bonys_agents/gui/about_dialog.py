# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Über Bony's Agents“."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from bonys_agents import APP_NAME, COPYRIGHT, LICENSE_ID, TAGLINE, YOUTUBE_CHANNEL_URL, __version__, license_location

from . import style
from .widgets import ScaledLogo, make_scrollable, open_url


def _href(name: str) -> str:
    """Link auf die mitgelieferte Lizenzdatei (öffnet im Texteditor) – sonst auf GitHub."""
    where = license_location(name)
    return where if where.startswith("https://") else QUrl.fromLocalFile(where).toString()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Über {APP_NAME}")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(8)

        root.addWidget(ScaledLogo(160), 1)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignCenter)
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("Tagline")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setWordWrap(True)
        for w in (title, version):
            root.addWidget(w)
        root.addSpacing(6)
        root.addWidget(tagline)
        root.addSpacing(10)

        link = f"color: {style.HIGHLIGHT};"
        info = QLabel(
            "Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent – sauber getrennt von deinem System.<br><br>"
            f"{COPYRIGHT}<br>"
            f"Lizenz: <b>{LICENSE_ID}</b><br>"
            f'<a href="{_href("LICENSE")}" style="{link}">Lizenztext</a> · '
            f'<a href="{_href("THIRD-PARTY-LICENSES")}" style="{link}">Mitgelieferte Komponenten</a><br>'
            f'YouTube: <a href="{YOUTUBE_CHANNEL_URL}" style="{link}">'
            f"{YOUTUBE_CHANNEL_URL.removeprefix('https://www.')}</a>"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        info.setTextFormat(Qt.RichText)
        info.linkActivated.connect(open_url)  # eigener Weg: saubere Umgebung für Browser/Editor
        root.addWidget(info)
        root.addSpacing(12)

        row = QHBoxLayout()
        yt = QPushButton("▶  Zum YouTube-Kanal")
        yt.clicked.connect(lambda: open_url(YOUTUBE_CHANNEL_URL))
        close = QPushButton("Schließen")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(yt)
        row.addWidget(close)
        row.addStretch(1)
        root.addLayout(row)
        make_scrollable(self, 460)
