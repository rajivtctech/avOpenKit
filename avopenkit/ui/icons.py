"""Line icons, drawn for this program and kept as SVG text so they follow the theme's colours.

Every icon is a 24 x 24 drawing made of strokes; `icon()` renders it in whatever colour is asked
for, at whatever size, so the same drawing serves the dark and the light theme and stays sharp
on high-resolution screens.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from . import theme

STROKES = {
    # the eight tasks
    "trim": '<circle cx="6" cy="6.5" r="2.6"/><circle cx="6" cy="17.5" r="2.6"/>'
            '<path d="M8.2 8.2 20 19M8.2 15.8 20 5"/>',
    "shrink": '<path d="M3 3l6 6M9 4.5V9H4.5M21 21l-6-6M15 19.5V15h4.5M21 3l-6 6M19.5 9H15V4.5'
              'M3 21l6-6M4.5 15H9v4.5"/>',
    "convert": '<path d="M4 8.5h14.5M15 5l3.5 3.5L15 12M20 15.5H5.5M9 12l-3.5 3.5L9 19"/>',
    "audio": '<path d="M9 17.5V6l10-2v11.5"/><circle cx="6.5" cy="17.5" r="2.5"/>'
             '<circle cx="16.5" cy="15.5" r="2.5"/>',
    "join": '<rect x="2.5" y="7" width="8" height="10" rx="1.6"/>'
            '<rect x="13.5" y="7" width="8" height="10" rx="1.6"/><path d="M10.5 12h3"/>',
    "rotate": '<path d="M20 12a8 8 0 1 1-2.9-6.2"/><path d="M20.2 3.5v5h-5"/>',
    "gif": '<rect x="6.5" y="8" width="14" height="11.5" rx="1.6"/>'
           '<path d="M3.5 16V6.2A1.7 1.7 0 0 1 5.2 4.5H16"/><path d="M11.8 11.3v4.9l4-2.45z"/>',
    "subtitles": '<rect x="3" y="5" width="18" height="14" rx="2"/>'
                 '<path d="M6.5 15.2h5M13.5 15.2h4M6.5 12h3M11.5 12h6"/>',
    "crop": '<path d="M6.5 2.5v13a2 2 0 0 0 2 2h13M2.5 6.5h13a2 2 0 0 1 2 2v13"/>',
    "sequence": '<rect x="7.5" y="7.5" width="13" height="13" rx="1.6"/>'
                '<path d="M4.5 16.5V5.7a1.2 1.2 0 0 1 1.2-1.2h10.8"/>'
                '<path d="M9.5 18l3.2-3.8 2.3 2.6 1.5-1.7 2.6 2.9"/>',
    "sheet": '<rect x="3" y="4" width="18" height="16" rx="1.8"/>'
             '<path d="M9 4v16M15 4v16M3 9.3h18M3 14.7h18"/>',
    "speed": '<path d="M4 6.5l7.5 5.5L4 17.5zM12.5 6.5 20 12l-7.5 5.5z"/>',
    "export": '<rect x="3" y="9.5" width="18" height="10.5" rx="1.6"/>'
              '<path d="M3.2 9.5 4.5 5.3l16.2 2.3-.7 1.9M8.3 5.9l1.5 3.4M13.4 6.6l1.5 2.9"/>',
    # actions
    "open": '<path d="M3 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="1.8"/>'
            '<path d="M5.5 15.5h-.3A1.7 1.7 0 0 1 3.5 13.8V5.2a1.7 1.7 0 0 1 1.7-1.7h8.6a1.7 1.7 0 0 1 1.7 1.7v.3"/>',
    "queue": '<path d="M4 6.5h11M4 12h11M4 17.5h7M18 14.5v6M15 17.5h6"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "remove": '<path d="M6 6l12 12M18 6 6 18"/>',
    "clear": '<path d="M4.5 7h15M9.5 7V4.8h5V7M6.5 7l.8 12.2h9.4L17.5 7M10 10.5v5.5M14 10.5v5.5"/>',
    "folder": '<path d="M3 8a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/>'
                '<circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
    "volume": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a7.8 7.8 0 0 1 0 11"/>',
    "mute": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM16 9.5l5 5M21 9.5l-5 5"/>',
    "mark_in": '<path d="M8 4.5H5.5v15H8M10.5 12h8.5M15.5 8.5 19 12l-3.5 3.5"/>',
    "mark_out": '<path d="M16 4.5h2.5v15H16M13.5 12H5M8.5 8.5 5 12l3.5 3.5"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.9-6.2"/><path d="M3.8 3.5v5h5"/>',
    # states
    "check": '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.8 2.8L16.2 9.5"/>',
    "encode": '<path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9 18 18M18 6l-2.1 2.1'
              'M8.1 15.9 6 18"/><circle cx="12" cy="12" r="3"/>',
    "alert": '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.3"/>',
    "film": '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="M7.5 4.5v15M16.5 4.5v15'
            'M3 9.5h4.5M3 14.5h4.5M16.5 9.5H21M16.5 14.5H21"/>',
    "note": '<path d="M9 17.5V6l10-2v11.5"/><circle cx="6.5" cy="17.5" r="2.5"/>'
            '<circle cx="16.5" cy="15.5" r="2.5"/>',
    "drop": '<path d="M12 4v10M8 10.5l4 4 4-4M4.5 16.5v2a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-2"/>',
}

FILLS = {
    "play": '<path d="M8 5.2v13.6a.7.7 0 0 0 1.1.6l10.2-6.8a.7.7 0 0 0 0-1.2L9.1 4.6A.7.7 0 0 0 8 5.2z"/>',
    "pause": '<rect x="6.5" y="5" width="4" height="14" rx="1.2"/><rect x="13.5" y="5" width="4" height="14" rx="1.2"/>',
}

NAMES = sorted(set(STROKES) | set(FILLS))


def svg(name: str, colour: str) -> bytes:
    if name in FILLS:
        body, attrs = FILLS[name], f'fill="{colour}" stroke="none"'
    else:
        body, attrs = STROKES[name], (f'fill="none" stroke="{colour}" stroke-width="1.7" '
                                      'stroke-linecap="round" stroke-linejoin="round"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {attrs}>'
            f'{body}</svg>').encode()


def pixmap(name: str, colour: str | QColor | None = None, size: int = 20, ratio: float = 2.0) -> QPixmap:
    """The icon as a picture `size` logical pixels square, sharp at the given screen ratio."""
    c = QColor(colour) if colour is not None else theme.colour("text")
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, c.name()))).render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, colour: str | QColor | None = None, disabled: str | QColor | None = None) -> QIcon:
    result = QIcon(pixmap(name, colour, 24))
    result.addPixmap(pixmap(name, disabled if disabled is not None else theme.colour("faint"), 24),
                     QIcon.Mode.Disabled)
    return result


def logo(size: int = 28, ratio: float = 2.0) -> QPixmap:
    """The program's mark: a play triangle cut into a rounded tile in the accent colour."""
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(pm.width())
    gradient = QLinearGradient(0, 0, s, s)
    gradient.setColorAt(0.0, QColor("#ff9a6b"))
    gradient.setColorAt(1.0, QColor("#f0483a"))
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, s, s), s * 0.26, s * 0.26)
    p.fillPath(tile, gradient)
    play = QPainterPath()
    play.moveTo(s * 0.37, s * 0.27)
    play.lineTo(s * 0.74, s * 0.50)
    play.lineTo(s * 0.37, s * 0.73)
    play.closeSubpath()
    p.fillPath(play, QColor("#ffffff"))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm
