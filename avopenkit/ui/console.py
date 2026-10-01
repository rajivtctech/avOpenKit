"""The command box: shows the FFmpeg command and explains each part on hover (spec F1, F12)."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit, QToolTip

from ..core.explain import explanation_at


class CommandConsole(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)

    def position_at(self, point: QPoint) -> int | None:
        """The character under a point of the viewport, or None when the point is not on text."""
        cursor = self.cursorForPosition(point)
        rect = self.cursorRect(cursor)
        if not rect.top() <= point.y() <= rect.bottom():
            return None                      # below the last line
        # cursorForPosition returns the nearest gap between characters; the character under
        # the mouse is the one that starts at or before the point.
        if point.x() < rect.left() and cursor.positionInBlock() > 0:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
        elif point.x() > rect.left() + self.fontMetrics().averageCharWidth() and cursor.atBlockEnd():
            return None                      # to the right of the end of a line
        return cursor.position()

    def explanation_for(self, point: QPoint) -> str | None:
        position = self.position_at(point)
        if position is None:
            return None
        return explanation_at(self.toPlainText(), position)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            text = self.explanation_for(self.viewport().mapFrom(self, event.pos()))
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)
