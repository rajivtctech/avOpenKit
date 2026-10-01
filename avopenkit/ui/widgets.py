"""The custom-drawn parts of the window: filmstrip timeline, task cards, note box, command
colouring, and the loader that fetches thumbnails from FFmpeg."""

from __future__ import annotations

import re

from PyQt6.QtCore import QObject, QPoint, QProcess, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap,
                         QSyntaxHighlighter, QTextCharFormat)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QSlider, QStyle,
                             QStyledItemDelegate, QVBoxLayout)

from ..core.ffmpeg import Tools
from ..core.job import Plan
from . import icons, theme

BLURB_ROLE = Qt.ItemDataRole.UserRole + 1
ICON_ROLE = Qt.ItemDataRole.UserRole + 2


# ---------------------------------------------------------------- thumbnails from FFmpeg

class ThumbLoader(QObject):
    """Fetches single frames one after another, without blocking the window.

    One short FFmpeg run per frame, each seeking straight to its moment, so a two-hour film
    costs no more than a ten-second clip."""

    ready = pyqtSignal(int, QImage)        # index, picture

    def __init__(self, tools: Tools, parent=None) -> None:
        super().__init__(parent)
        self.tools = tools
        self._todo: list[tuple[int, float]] = []
        self._proc: QProcess | None = None
        self._index = 0
        self._path = ""
        self._height = 54

    def load(self, path, times: list[float], height: int = 54) -> None:
        self.cancel()
        self._path, self._height = str(path), height
        self._todo = list(enumerate(times))
        self._next()

    def cancel(self) -> None:
        self._todo = []
        if self._proc is not None:
            p, self._proc = self._proc, None
            p.finished.disconnect()
            p.kill()
            p.waitForFinished(1000)
            p.deleteLater()

    def _next(self) -> None:
        if not self._todo:
            return
        self._index, seconds = self._todo.pop(0)
        p = QProcess(self)
        p.finished.connect(self._done)
        self._proc = p
        p.start(self.tools.ffmpeg, [
            "-v", "error", "-nostdin", "-ss", f"{seconds:.3f}", "-i", self._path,
            "-frames:v", "1", "-vf", f"scale=-2:{self._height}", "-f", "image2pipe",
            "-c:v", "ppm", "-"])

    def _done(self, _code: int = 0, _status=None) -> None:
        p, self._proc = self._proc, None
        if p is None:
            return
        image = QImage.fromData(bytes(p.readAllStandardOutput()))
        p.deleteLater()
        if not image.isNull():
            self.ready.emit(self._index, image)
        self._next()


# ---------------------------------------------------------------- the timeline

class Timeline(QSlider):
    """A scrub bar that shows the video itself: a strip of frames, the chosen part lit and the
    rest dimmed, a tick at every keyframe, and a playhead. Values are milliseconds, as for the
    plain slider it replaces, and the arrow and page keys still step through it."""

    CELLS = 12

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMinimumHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumbs: dict[int, QImage] = {}
        self._range: tuple[float, float] | None = None      # seconds
        self._keyframes: tuple[float, ...] = ()
        self._has_picture = True

    # -- data
    def set_media(self, keyframes=(), has_picture: bool = True) -> None:
        self._thumbs, self._keyframes, self._has_picture = {}, tuple(keyframes), has_picture
        self.update()

    def set_thumb(self, index: int, image: QImage) -> None:
        self._thumbs[index] = image
        self.update()

    def set_selection(self, start: float | None, end: float | None = None) -> None:
        """The part of the file a task will use, in seconds; None for no selection."""
        self._range = None if start is None or end is None or end <= start else (start, end)
        self.update()

    def selection(self) -> tuple[float, float] | None:
        return self._range

    def thumb_times(self, duration: float) -> list[float]:
        return [duration * (i + 0.5) / self.CELLS for i in range(self.CELLS)]

    # -- geometry
    def _track(self) -> QRect:
        return self.rect().adjusted(8, 10, -8, -8)

    def _x(self, ms: float) -> float:
        t = self._track()
        span = max(self.maximum() - self.minimum(), 1)
        return t.left() + t.width() * (ms - self.minimum()) / span

    def _value_at(self, x: float) -> int:
        t = self._track()
        frac = min(max((x - t.left()) / max(t.width(), 1), 0.0), 1.0)
        return int(round(self.minimum() + frac * (self.maximum() - self.minimum())))

    # -- mouse: click or drag anywhere to go there
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            self.setFocus()
            self.setSliderDown(True)
            self._drag(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self.isSliderDown():
            self._drag(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self.isSliderDown():
            self._drag(event.position().x())
            self.setSliderDown(False)
            event.accept()

    def _drag(self, x: float) -> None:
        value = self._value_at(x)
        self.setSliderPosition(value)
        self.sliderMoved.emit(value)

    def sizeHint(self) -> QSize:
        return QSize(400, 72)

    # -- drawing
    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        track = self._track()
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(track), 7, 7)
        p.fillPath(shape, QColor(t["sunken"]))

        p.save()
        p.setClipPath(shape)
        if self._has_picture:
            cell = track.width() / self.CELLS
            for i in range(self.CELLS):
                image = self._thumbs.get(i)
                target = QRectF(track.left() + i * cell, track.top(), cell + 1, track.height())
                if image is None:
                    continue
                # fill the cell, cropping the picture rather than squashing it
                scale = max(target.width() / image.width(), target.height() / image.height())
                w, h = target.width() / scale, target.height() / scale
                source = QRectF((image.width() - w) / 2, (image.height() - h) / 2, w, h)
                p.drawImage(target, image, source)
        else:
            # sound only: a quiet row of bars instead of pictures
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["border_strong"]))
            for i in range(0, track.width(), 6):
                h = 6 + (i * 37 % 23)
                p.drawRoundedRect(QRectF(track.left() + i, track.center().y() - h / 2, 3, h), 1.5, 1.5)

        if self._range and self.maximum() > self.minimum():
            a, b = self._x(self._range[0] * 1000), self._x(self._range[1] * 1000)
            dim = QColor(t["bg"])
            dim.setAlpha(190)
            p.fillRect(QRectF(track.left(), track.top(), max(a - track.left(), 0), track.height()), dim)
            p.fillRect(QRectF(b, track.top(), max(track.right() + 1 - b, 0), track.height()), dim)
        p.restore()

        if self._range and self.maximum() > self.minimum():
            a, b = self._x(self._range[0] * 1000), self._x(self._range[1] * 1000)
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(a, track.top() + 1, max(b - a, 2), track.height() - 2), 5, 5)

        # keyframes: where a lossless cut can begin
        if self._keyframes and self.maximum() > self.minimum() and len(self._keyframes) <= track.width() / 4:
            p.setPen(QPen(QColor(t["good"]), 1.5))
            for k in self._keyframes:
                x = self._x(k * 1000)
                p.drawLine(int(x), track.bottom() + 2, int(x), track.bottom() + 6)

        p.setPen(QPen(QColor(t["border"]), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)

        if self.maximum() > self.minimum():
            x = self._x(self.sliderPosition())
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(int(x), track.top() - 3, int(x), track.bottom() + 3)
            head = QPainterPath()
            head.moveTo(x - 6, track.top() - 9)
            head.lineTo(x + 6, track.top() - 9)
            head.lineTo(x, track.top() - 1)
            head.closeSubpath()
            p.fillPath(head, QColor(t["accent"]))
        if self.hasFocus():
            p.setPen(QPen(QColor(t["accent"]), 1, Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        p.end()


# ---------------------------------------------------------------- task cards

class TaskDelegate(QStyledItemDelegate):
    """Draws each task as a card: its icon, its name, and a line saying what it does."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(220, 58)

    def paint(self, painter, option, index) -> None:
        t = theme.current()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(6, 3, -6, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        if selected:
            painter.setPen(QPen(QColor(t["accent"]), 1.2))
            painter.setBrush(QColor(t["accent_soft"]))
            painter.drawRoundedRect(rect, 9, 9)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["raised"]))
            painter.drawRoundedRect(rect, 9, 9)

        name = index.data(ICON_ROLE)
        tint = t["accent"] if selected else t["muted"] if enabled else t["faint"]
        tile = QRectF(rect.left() + 9, rect.center().y() - 17, 34, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["accent"] if selected else t["raised"]))
        painter.drawRoundedRect(tile, 8, 8)
        if name:
            pm = icons.pixmap(name, t["accent_text"] if selected else tint, 22)
            painter.drawPixmap(QRectF(tile.center().x() - 11, tile.center().y() - 11, 22, 22),
                               pm, QRectF(pm.rect()))

        left = int(tile.right() + 11)
        width = int(rect.right() - left - 6)
        title = QFont(option.font)
        title.setPointSizeF(10.5)
        title.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title)
        painter.setPen(QColor(t["text"] if enabled else t["faint"]))
        painter.drawText(QRect(left, int(rect.top() + 8), width, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         index.data(Qt.ItemDataRole.DisplayRole))
        blurb = QFont(option.font)
        blurb.setPointSizeF(8.3)
        painter.setFont(blurb)
        painter.setPen(QColor(t["muted"] if enabled else t["faint"]))
        text = painter.fontMetrics().elidedText(index.data(BLURB_ROLE) or "",
                                                Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRect(left, int(rect.top() + 28), width, 18),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


# ---------------------------------------------------------------- "what will happen"

def plan_kind(plan: Plan | None) -> str:
    """Whether a plan copies, re-encodes, or does some of each - for the coloured badge.

    "copy": every audio and video stream is copied; "encode": at least one is re-encoded and
    none is copied; "mixed": some of each; "" when it cannot be said (a hand-edited command)."""
    if plan is None or not plan.jobs or any(j.edited for j in plan.jobs):
        return ""
    copies = encodes = 0
    for job in plan.jobs:
        a = job.args
        if "-vf" in a or "-filter_complex" in a:
            encodes += 1
        for i, word in enumerate(a[:-1]):
            if word in ("-c", "-c:v", "-c:a"):
                copies += a[i + 1] == "copy"
                encodes += a[i + 1] != "copy"
    if encodes and copies:
        return "mixed"
    return "encode" if encodes else "copy" if copies else ""


class NotesBox(QFrame):
    """The "what will happen" box: an icon, a badge and the plain-language notes, tinted green
    when nothing is re-encoded, amber when something is, red when the job cannot be run."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("notes")
        self.icon = QLabel()
        self.icon.setFixedSize(22, 22)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.icon)
        head.addWidget(self.badge)
        head.addStretch()
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 9, 12, 10)
        box.setSpacing(5)
        box.addLayout(head)
        box.addWidget(self.label)
        self.kind = ""
        self.show_notes("", "", "")

    def text(self) -> str:
        return self.label.text()

    def setText(self, text: str) -> None:      # same call the plain label had
        self.show_notes(text, self.kind, self.badge.text())

    def show_notes(self, text: str, kind: str, badge: str) -> None:
        t = theme.current()
        self.kind = kind
        name, tint = {"copy": ("check", t["good"]), "encode": ("encode", t["warn"]),
                      "mixed": ("encode", t["warn"]), "problem": ("alert", t["bad"])}.get(
                          kind, ("info", t["muted"]))
        self.icon.setPixmap(icons.pixmap(name, tint, 22))
        self.badge.setText(badge)
        self.badge.setVisible(bool(badge))
        self.label.setText(text)
        for w in (self, self.badge):
            w.setProperty("kind", kind)
            w.style().unpolish(w)
            w.style().polish(w)


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps to a new row when the width runs out, so a row
    of chips never forces the window wider than it is."""

    def __init__(self, parent=None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items = []
        self._gap = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def clear(self) -> None:
        while self._items:
            widget = self._items.pop().widget()
            if widget is not None:
                widget.deleteLater()
        self.invalidate()

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._place(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._place(rect, dry=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _place(self, rect: QRect, dry: bool) -> int:
        x, y, row = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and row > 0:
                x, y, row = rect.x(), y + row + self._gap, 0
            if not dry:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._gap
            row = max(row, hint.height())
        return y + row - rect.y()


def chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("chip")
    return label


# ---------------------------------------------------------------- the command, in colour

class CommandHighlighter(QSyntaxHighlighter):
    """Colours the FFmpeg command so its structure can be seen: the program, the options, and
    the quoted file names. It changes only how the text looks, never the text."""

    OPTION = re.compile(r"(?:(?<=\s)|^)-[A-Za-z_][\w:.\-]*")
    QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
    PROGRAM = re.compile(r"^\s*\S*ffmpeg(?:\.exe)?(?=\s|$)")

    def highlightBlock(self, text: str) -> None:
        t = theme.current()
        program = QTextCharFormat()
        program.setForeground(QColor(t["accent"]))
        program.setFontWeight(QFont.Weight.Bold)
        option = QTextCharFormat()
        option.setForeground(QColor(t["code_option"]))
        quoted = QTextCharFormat()
        quoted.setForeground(QColor(t["code_string"]))
        for m in self.PROGRAM.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), program)
        for m in self.OPTION.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), option)
        for m in self.QUOTED.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), quoted)


def rounded(pixmap: QPixmap, radius: float = 6.0) -> QPixmap:
    """A picture with its corners rounded, for thumbnails."""
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    size = pixmap.deviceIndependentSize()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pixmap)
    p.end()
    return out
