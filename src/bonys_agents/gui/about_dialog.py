# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenster „Über Bony's Agents“."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from bonys_agents import COPYRIGHT, LICENSE_ID, TAGLINE, YOUTUBE_CHANNEL_URL, __version__, edition, license_location
from bonys_agents.i18n import tr

from . import style
from .widgets import ScaledLogo, make_scrollable, open_url


def _href(name: str) -> str:
    """Link auf die mitgelieferte Lizenzdatei (öffnet im Texteditor) – sonst auf GitHub."""
    where = license_location(name)
    return where if where.startswith("https://") else QUrl.fromLocalFile(where).toString()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Über {NAME}", NAME=edition.NAME))

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(8)

        root.addWidget(ScaledLogo(160), 1)

        title = QLabel(edition.NAME)
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        version = QLabel(tr("Version {version__} · Edition {LABEL}", version__=__version__, LABEL=edition.LABEL))
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignCenter)
        tagline = QLabel(tr(TAGLINE))
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
            tr("Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent – sauber getrennt von deinem "
               "System.<br><br>{COPYRIGHT}<br>Lizenz: <b>{LICENSE_ID}</b><br><a href=\"{wert}\" "
               "style=\"{link}\">Lizenztext</a> · <a href=\"{wert2}\" style=\"{link}\">Mitgelieferte "
               "Komponenten</a><br>YouTube: <a href=\"{YOUTUBE_CHANNEL_URL}\" style=\"{link}\">{wert3}</a>",
               COPYRIGHT=COPYRIGHT, LICENSE_ID=LICENSE_ID, wert=_href("LICENSE"), link=link,
               wert2=_href("THIRD-PARTY-LICENSES"), YOUTUBE_CHANNEL_URL=YOUTUBE_CHANNEL_URL,
               wert3=YOUTUBE_CHANNEL_URL.removeprefix('https://www.'))
            + ("" if edition.IS_TRAINER else tr("<br><br><span style=\"font-size: small;\">Du möchtest selbst "
                                                "Schulungen geben? → <a href=\"{wert}\" "
                                                "style=\"{link}\">{wert2}</a></span>", wert=edition.download_url(),
                                                link=link, wert2=edition.NAMES[edition.KURSLEITER]))
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        info.setTextFormat(Qt.RichText)
        info.linkActivated.connect(open_url)  # eigener Weg: saubere Umgebung für Browser/Editor
        root.addWidget(info)
        root.addSpacing(12)

        row = QHBoxLayout()
        yt = QPushButton(tr("▶  Zum YouTube-Kanal"))
        yt.clicked.connect(lambda: open_url(YOUTUBE_CHANNEL_URL))
        close = QPushButton(tr("Schließen"))
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(yt)
        row.addWidget(close)
        row.addStretch(1)
        root.addLayout(row)
        make_scrollable(self, 460)
