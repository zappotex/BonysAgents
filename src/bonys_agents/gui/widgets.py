# SPDX-License-Identifier: GPL-3.0-or-later
"""Kleine wiederverwendbare Bausteine der Oberfläche."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLayout, QProgressBar, QScrollArea, QSizePolicy, QSlider, QVBoxLayout,
    QWidget,
)

from bonys_agents import procutil, vm

from . import style


def open_url(url: str) -> None:
    """Adresse oder Datei öffnen. Im fertigen Programm unter Linux selbst über xdg-open mit
    bereinigter Umgebung – QDesktopServices gäbe dem Browser die mitgelieferten Bibliotheken mit."""
    if procutil.is_frozen() and sys.platform.startswith("linux"):
        target = QUrl(url).toLocalFile() if url.startswith("file:") else url
        try:
            procutil.open_external(target)
            return
        except (OSError, RuntimeError):
            pass
    QDesktopServices.openUrl(QUrl(url) if "://" in url or url.startswith("file:") else QUrl.fromLocalFile(url))


class DiskSlider(QWidget):
    """Schieberegler über feste Festplattenstufen (32 GB … 1 TB) mit Anzeige und Hinweis."""

    valueChanged = Signal(int)  # noqa: N815 – Qt-Stil

    def __init__(self, value: int = vm.DEFAULT_DISK_GB, minimum: int = vm.MIN_DISK_GB, parent=None):
        super().__init__(parent)
        self.steps = [gb for gb in vm.DISK_STEPS_GB if gb >= minimum]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, len(self.steps) - 1)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.label = QLabel()
        self.label.setMinimumWidth(style.px(110))
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.slider, 1)
        row.addWidget(self.label)
        lay.addLayout(row)
        hint = QLabel("Wächst dynamisch – belegt nur, was wirklich genutzt wird.")
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        self.slider.valueChanged.connect(self._changed)
        self.setValue(value)
        self._changed()

    def value(self) -> int:
        return self.steps[self.slider.value()]

    def setValue(self, gb: int) -> None:  # noqa: N802 – Qt-Stil
        # nächstgelegene Stufe, die mindestens so groß ist
        idx = next((i for i, s in enumerate(self.steps) if s >= gb), len(self.steps) - 1)
        self.slider.setValue(idx)

    def _changed(self, *_):
        self.label.setText(vm.format_gb(self.value()))
        self.valueChanged.emit(self.value())


class PercentBar(QWidget):
    """Fortschrittsbalken mit Prozentzahl daneben."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.label = QLabel()
        self.label.setObjectName("Percent")
        self.label.setMinimumWidth(style.px(48))
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.label)

    def set_percent(self, percent: float | None) -> None:
        """Prozent setzen; None = unbestimmt (Balken läuft hin und her)."""
        if percent is None:
            self.bar.setRange(0, 0)
            self.label.setText("")
            return
        self.bar.setRange(0, 1000)
        self.bar.setValue(round(percent * 10))
        self.label.setText(f"{percent:.0f} %")


# ---------------------------------------------------------------- flexible Anordnung
def _hfw(item, width: int) -> int:
    """Höhe eines Layout-Eintrags bei gegebener Breite (umbrechende Texte werden dabei höher)."""
    h = item.heightForWidth(width) if item.hasHeightForWidth() else item.sizeHint().height()
    return max(h, item.minimumSize().height())


class FlowLayout(QLayout):
    """Knöpfe nebeneinander – reicht die Breite nicht, geht es in der nächsten Zeile weiter."""

    def __init__(self, parent=None, spacing: int = 8, align_right: bool = False):
        super().__init__(parent)
        self._items = []
        self._gap = spacing
        self._right = align_right
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 – Qt-Name
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802 – Qt-Name
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802 – Qt-Name
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 – Qt-Name
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 – Qt-Name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 – Qt-Name
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 – Qt-Name
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def _visible(self) -> list:
        return [i for i in self._items if not i.isEmpty()]

    def sizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        items = self._visible()
        m = self.contentsMargins()
        w = sum(i.sizeHint().width() for i in items) + self._gap * max(0, len(items) - 1)
        h = max((i.sizeHint().height() for i in items), default=0)
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self) -> QSize:  # noqa: N802 – Qt-Name
        items = self._visible()
        m = self.contentsMargins()
        w = max((i.minimumSize().width() for i in items), default=0)
        h = max((i.minimumSize().height() for i in items), default=0)
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        rows: list[list] = [[]]
        used = 0
        for item in self._visible():
            w = min(item.sizeHint().width(), area.width())
            if rows[-1] and used + self._gap + w > area.width():
                rows.append([])
                used = 0
            used += (self._gap if rows[-1] else 0) + w
            rows[-1].append((item, w))
        y = area.y()
        for row in rows:
            if not row:
                continue
            height = max(item.sizeHint().height() for item, _ in row)
            width = sum(w for _, w in row) + self._gap * (len(row) - 1)
            x = area.x() + (area.width() - width if self._right else 0)
            for item, w in row:
                if apply:
                    item.setGeometry(QRect(QPoint(x, y), QSize(w, height)))
                x += w + self._gap
            y += height + self._gap
        return max(0, y - self._gap - area.y()) + m.top() + m.bottom()


class ColumnLayout(QLayout):
    """Gleich breite Spalten – so viele, wie nebeneinander passen (höchstens `columns`).

    Die Eigenschaft „span“ eines Eintrags gibt an, wie viele Spalten er belegt (höchstens alle).
    Bei schmalem Fenster rutschen die Felder untereinander, statt abgeschnitten zu werden.
    """

    def __init__(self, parent=None, columns: int = 3, min_width: int = 200, hspacing: int = 32, vspacing: int = 14):
        super().__init__(parent)
        self._items = []
        self._columns = columns
        self._min_width = min_width
        self._hgap = hspacing
        self._vgap = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 – Qt-Name
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802 – Qt-Name
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802 – Qt-Name
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 – Qt-Name
        return Qt.Horizontal

    def hasHeightForWidth(self) -> bool:  # noqa: N802 – Qt-Name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 – Qt-Name
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 – Qt-Name
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def _visible(self) -> list:
        return [i for i in self._items if not i.isEmpty()]

    @staticmethod
    def _span(item, cols: int) -> int:
        span = item.widget().property("span") if item.widget() else None
        return max(1, min(cols, int(span or 1)))

    def _column_width(self) -> int:
        return max([style.px(self._min_width)] + [i.minimumSize().width() for i in self._visible()])

    def sizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        m = self.contentsMargins()
        w = self._columns * self._column_width() + (self._columns - 1) * self._hgap
        return QSize(w + m.left() + m.right(), self.heightForWidth(w + m.left() + m.right()))

    def minimumSize(self) -> QSize:  # noqa: N802 – Qt-Name
        m = self.contentsMargins()
        w = max((i.minimumSize().width() for i in self._visible()), default=0)
        return QSize(w + m.left() + m.right(), 0)

    def _arrange(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        cols = max(1, min(self._columns, (area.width() + self._hgap) // (self._column_width() + self._hgap)))
        col_w = (area.width() - (cols - 1) * self._hgap) // cols
        rows: list[list] = [[]]
        used = 0
        for item in self._visible():
            span = self._span(item, cols)
            if used + span > cols:
                rows.append([])
                used = 0
            rows[-1].append(item)
            used += span
        y = area.y()
        for row in (r for r in rows if r):
            widths = [col_w * (s := self._span(i, cols)) + self._hgap * (s - 1) for i in row]
            height = max(_hfw(item, w) for item, w in zip(row, widths, strict=True))
            x = area.x()
            for item, w in zip(row, widths, strict=True):
                if apply:
                    item.setGeometry(QRect(x, y, w, height))
                x += w + self._hgap
            y += height + self._vgap
        return max(0, y - self._vgap - area.y()) + m.top() + m.bottom()


class PathLabel(QLabel):
    """Pfad, der bei Platzmangel in der Mitte gekürzt wird („/media/…/agent-pc-1“).

    Pfade haben keine Leerzeichen, ein normales Label könnte sie nicht umbrechen und würde das
    Fenster verbreitern. Der ganze Pfad steht im Tooltip und lässt sich per Rechtsklick kopieren.
    """

    def __init__(self, path: str = "", prefix: str = "", parent=None):
        super().__init__(parent)
        self._path = ""
        self._prefix = prefix
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        copy = QAction("Pfad kopieren", self)
        copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(self._path))
        self.addAction(copy)
        self.set_path(path)

    def path(self) -> str:
        return self._path

    def set_path(self, path) -> None:
        self._path = str(path)
        self.setToolTip(self._path)
        self._elide()
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._prefix + self._path) + 4, fm.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        fm = self.fontMetrics()
        return QSize(min(self.sizeHint().width(), fm.horizontalAdvance(self._prefix + "/…/") + 4), fm.height())

    def changeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._elide()
            self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        fm = self.fontMetrics()
        room = max(0, self.width() - fm.horizontalAdvance(self._prefix) - 4)
        self.setText(self._prefix + fm.elidedText(self._path, Qt.ElideMiddle, room) if self._path else "")


class ScaledLogo(QLabel):
    """Logo, das sich dem verfügbaren Platz anpasst (Seitenverhältnis bleibt, weich skaliert).

    Anders als ein Label mit fester Pixmap erzwingt es keine Mindestgröße.
    """

    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self._source = QPixmap(str(style.resource("logo.png")))
        self._size = size
        self._cache: QPixmap | None = None
        # Keine Mindestgröße über setMinimumSize: die übersteuert in Qt auch eine feste Größenregel (Kopfzeile).
        # minimumSizeHint() liefert 1×1 – damit darf das Logo beliebig schrumpfen.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def sizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        return QSize(style.px(self._size), style.px(self._size))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 – Qt-Name
        return QSize(1, 1)

    def changeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        if event.type() == QEvent.StyleChange:  # Anzeigegröße geändert
            self.updateGeometry()
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        self._cache = None
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 – Qt-Name
        side = min(self.width(), self.height())
        if side < 2 or self._source.isNull():
            return
        dpr = self.devicePixelRatioF()
        if self._cache is None or self._cache.devicePixelRatio() != dpr:
            self._cache = self._source.scaled(round(side * dpr), round(side * dpr), Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)
            self._cache.setDevicePixelRatio(dpr)
        size = self._cache.deviceIndependentSize()
        p = QPainter(self)
        p.drawPixmap(round((self.width() - size.width()) / 2), round((self.height() - size.height()) / 2), self._cache)
        p.end()


# ---------------------------------------------------------------- Fenstergrößen
def available_geometry(widget: QWidget | None = None) -> QRect:
    """Nutzbare Fläche des Bildschirms, auf dem das Fenster liegt (ohne Leisten)."""
    scr = (widget.screen() if widget else None) or QGuiApplication.primaryScreen()
    return scr.availableGeometry() if scr else QRect(0, 0, 1280, 800)


def fit_to_screen(win: QWidget, width: int, height: int) -> None:
    """Wunschgröße setzen – aber nie größer als der verfügbare Bildschirm."""
    avail = available_geometry(win.parentWidget() or win)
    win.resize(min(width, int(avail.width() * 0.95)), min(height, int(avail.height() * 0.9)))


def make_scrollable(dialog: QDialog, width: int, keep: int = 1) -> QScrollArea:
    """Inhalt eines fertig aufgebauten Dialogs in einen Bildlaufbereich verlegen.

    Die letzten `keep` Einträge (die Knopfzeile) bleiben darunter und damit immer sichtbar.
    Danach ist der Dialog frei in der Größe veränderbar und nie höher als der Bildschirm.
    """
    outer = dialog.layout()
    body = QWidget()
    inner = QVBoxLayout(body)
    inner.setContentsMargins(0, 0, 6, 0)  # etwas Luft zur Bildlaufleiste
    inner.setSpacing(max(0, outer.spacing()))
    for _ in range(outer.count() - keep):
        stretch = outer.stretch(0)
        item = outer.takeAt(0)
        if item.widget():
            inner.addWidget(item.widget(), stretch, item.alignment())
        elif item.layout():
            inner.addLayout(item.layout(), stretch)
        elif stretch:
            inner.addStretch(stretch)
        else:
            inner.addSpacing(item.sizeHint().height())
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(body)
    outer.insertWidget(0, scroll, 1)
    dialog.setSizeGripEnabled(True)

    # Startgröße: so groß, dass ohne Bildlauf alles zu sehen ist – sofern der Bildschirm reicht
    m = outer.contentsMargins()
    width = max(style.px(width), body.minimumSizeHint().width() + m.left() + m.right() + 6)
    inner_w = width - m.left() - m.right() - 6
    height = _hfw(inner, inner_w) + m.top() + m.bottom()
    for i in range(1, outer.count()):
        item = outer.itemAt(i)
        if not item.isEmpty():
            height += max(0, outer.spacing()) + _hfw(item, inner_w)
    fit_to_screen(dialog, width, height + 4)
    return scroll
