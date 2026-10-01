"""The look of the program: two palettes, and one stylesheet built from whichever is in use.

The interface is for visual artists, so it follows the convention of picture tools: neutral
greys that do not tint the image being judged, one accent colour for the thing to press next,
and green / amber to say at a glance whether a job keeps the original quality.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QStyleFactory

DARK = {
    "name": "dark",
    "bg": "#16181d", "surface": "#1f2229", "raised": "#282c35", "sunken": "#111317",
    "border": "#343946", "border_strong": "#4a5162",
    "text": "#e8eaee", "muted": "#9aa2b1", "faint": "#6b7385",
    "accent": "#ff7a59", "accent_hover": "#ff916f", "accent_press": "#e8623f",
    "accent_text": "#1a0d08", "accent_soft": "#3a2620",
    "good": "#3ecf8e", "good_soft": "#16302a", "warn": "#f2c14e", "warn_soft": "#3a3018",
    "bad": "#ff5d73", "bad_soft": "#3a1c22",
    "code_bg": "#0f1115", "code_option": "#7cc4ff", "code_string": "#b6e08b",
    "selection": "#ff7a59",
}

LIGHT = {
    "name": "light",
    "bg": "#eef0f3", "surface": "#ffffff", "raised": "#f6f7f9", "sunken": "#e3e6eb",
    "border": "#d5d9e0", "border_strong": "#b6bcc8",
    "text": "#1b1e25", "muted": "#5d6573", "faint": "#8a92a0",
    "accent": "#c9431c", "accent_hover": "#d94a24", "accent_press": "#b83a16",
    "accent_text": "#ffffff", "accent_soft": "#fde6df",
    "good": "#12855a", "good_soft": "#dff5ea", "warn": "#9a6a00", "warn_soft": "#fdf1cf",
    "bad": "#c9283e", "bad_soft": "#fde2e6",
    "code_bg": "#f7f8fa", "code_option": "#1561b0", "code_string": "#3a7d1e",
    "selection": "#c9431c",
}

THEMES = {"dark": DARK, "light": LIGHT}
_current = DARK


def current() -> dict:
    return _current


def colour(name: str) -> QColor:
    return QColor(_current[name])


STYLE = """
* {{ outline: 0; }}
QWidget {{ color: {text}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {bg}; }}
QToolTip {{ background: {raised}; color: {text}; border: 1px solid {border_strong};
           padding: 6px 8px; }}
QLabel {{ background: transparent; }}
QLabel#appName {{ font-size: 15pt; font-weight: 700; letter-spacing: 0.5px; }}
QLabel#sectionLabel {{ color: {faint}; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px;
                      padding: 6px 4px 2px 4px; }}
QLabel#taskTitle {{ font-size: 17pt; font-weight: 700; }}
QLabel#taskBlurb {{ color: {muted}; font-size: 10.5pt; }}
QLabel#fileName {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#hint {{ color: {muted}; }}
QLabel#footnote {{ color: {faint}; font-size: 8.5pt; }}
QLabel#chip {{ background: {raised}; color: {muted}; border: 1px solid {border};
              border-radius: 10px; padding: 2px 9px; font-size: 8.5pt; }}
QLabel#thumb {{ background: {sunken}; border: 1px solid {border}; border-radius: 6px; }}

QFrame#card {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#dropCard {{ background: {surface}; border: 2px dashed {border_strong}; border-radius: 12px; }}
QFrame#header {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#side {{ background: {surface}; border-right: 1px solid {border}; }}

QFrame#notes {{ background: {raised}; border: 1px solid {border}; border-left: 4px solid {border_strong};
               border-radius: 8px; }}
QFrame#notes[kind="copy"] {{ background: {good_soft}; border-color: {good}; }}
QFrame#notes[kind="encode"], QFrame#notes[kind="mixed"] {{ background: {warn_soft}; border-color: {warn}; }}
QFrame#notes[kind="problem"] {{ background: {bad_soft}; border-color: {bad}; }}
QLabel#badge {{ border-radius: 9px; padding: 2px 10px; font-size: 8.5pt; font-weight: 700; }}
QLabel#badge[kind="copy"] {{ background: {good}; color: {sunken}; }}
QLabel#badge[kind="encode"], QLabel#badge[kind="mixed"] {{ background: {warn}; color: {sunken}; }}
QLabel#badge[kind="problem"] {{ background: {bad}; color: {sunken}; }}

QPushButton {{ background: {raised}; color: {text}; border: 1px solid {border};
              border-radius: 7px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {border_strong}; background: {border}; }}
QPushButton:pressed {{ background: {sunken}; }}
QPushButton:disabled {{ color: {faint}; background: {surface}; border-color: {border}; }}
QPushButton:checked {{ background: {accent_soft}; border-color: {accent}; color: {accent}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: 1px solid {accent};
                      font-weight: 700; padding: 8px 26px; font-size: 11pt; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent_press}; }}
QPushButton#primary:disabled {{ background: {raised}; color: {faint}; border-color: {border}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {muted}; }}
QPushButton#ghost:hover {{ background: {raised}; color: {text}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {sunken}; color: {text};
    border: 1px solid {border}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {selection}; selection-color: {accent_text}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {faint}; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox::down-arrow {{ image: url({arrow_down}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {raised}; color: {text}; border: 1px solid {border_strong};
    selection-background-color: {accent}; selection-color: {accent_text}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button
    {{ background: transparent; border: 0; width: 20px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({arrow_up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({arrow_down}); width: 10px; height: 10px; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px;
    border: 1.5px solid {border_strong}; background: {sunken}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({tick}); }}
QRadioButton::indicator:checked {{ background: {accent}; border: 4px solid {sunken};
    width: 11px; height: 11px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}

QGroupBox {{ background: {raised}; border: 1px solid {border}; border-radius: 8px;
            margin-top: 14px; padding: 12px 10px 8px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {muted}; }}
QGroupBox QLineEdit, QGroupBox QSpinBox, QGroupBox QDoubleSpinBox, QGroupBox QComboBox
    {{ background: {sunken}; }}

QListWidget {{ background: transparent; border: 0; }}
QListWidget#tasks::item {{ border-radius: 8px; margin: 2px 6px; }}
QListWidget#queue {{ background: {sunken}; border: 1px solid {border}; border-radius: 8px; }}
QListWidget#queue::item {{ padding: 6px 8px; border-bottom: 1px solid {border}; color: {muted}; }}
QListWidget#queue::item:selected {{ background: {raised}; color: {text}; }}
QListWidget#clips {{ background: {sunken}; border: 1px solid {border}; border-radius: 8px; }}
QListWidget#clips::item {{ padding: 6px 8px; }}
QListWidget#clips::item:selected {{ background: {accent_soft}; color: {text}; }}

QPlainTextEdit {{ background: {code_bg}; color: {text}; border: 1px solid {border};
                 border-radius: 8px; padding: 8px; selection-background-color: {selection};
                 selection-color: {accent_text}; }}
QPlainTextEdit#log {{ color: {muted}; font-size: 8.5pt; }}

QProgressBar {{ background: {sunken}; border: 1px solid {border}; border-radius: 6px;
               height: 12px; text-align: center; color: {text}; font-size: 8pt; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}

QScrollArea {{ border: 0; background: {bg}; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border_strong}; border-radius: 4px; min-height: 28px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border_strong}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenuBar {{ background: {surface}; color: {muted}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {raised}; color: {text}; }}
QMenu {{ background: {raised}; color: {text}; border: 1px solid {border_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
QStatusBar {{ background: {surface}; color: {faint}; border-top: 1px solid {border}; font-size: 8.5pt; }}
QSplitter::handle {{ background: {border}; width: 1px; }}
"""


_art_dir: Path | None = None


def _art(t: dict) -> dict:
    """Small pictures the stylesheet needs (arrows, the tick), drawn in the theme's colours."""
    global _art_dir
    if _art_dir is None:
        _art_dir = Path(tempfile.mkdtemp(prefix="avopenkit-theme-"))
        atexit.register(shutil.rmtree, _art_dir, True)

    def draw(name: str, points: list[tuple[float, float]], colour: str, width: float) -> str:
        pm = QPixmap(48, 48)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(colour), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(x * 48, y * 48) for x, y in points])
        p.end()
        path = _art_dir / f"{t['name']}-{name}.png"
        pm.save(str(path))
        return path.as_posix()

    return {
        "arrow_down": draw("down", [(0.2, 0.35), (0.5, 0.65), (0.8, 0.35)], t["muted"], 6),
        "arrow_up": draw("up", [(0.2, 0.65), (0.5, 0.35), (0.8, 0.65)], t["muted"], 6),
        "tick": draw("tick", [(0.22, 0.52), (0.42, 0.72), (0.78, 0.3)], t["accent_text"], 7),
    }


def apply(app: QApplication, name: str = "dark") -> dict:
    """Give the whole application one of the two looks. Returns the palette in use."""
    global _current
    _current = THEMES.get(name, DARK)
    t = _current
    app.setStyle(QStyleFactory.create("Fusion"))
    p = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "sunken"),
                      (QPalette.ColorRole.AlternateBase, "surface"),
                      (QPalette.ColorRole.Button, "raised"),
                      (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Text, "text"),
                      (QPalette.ColorRole.ButtonText, "text"),
                      (QPalette.ColorRole.ToolTipBase, "raised"),
                      (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "accent_text"),
                      (QPalette.ColorRole.PlaceholderText, "faint"),
                      (QPalette.ColorRole.Link, "accent")):
        p.setColor(role, QColor(t[key]))
    app.setPalette(p)
    app.setStyleSheet(STYLE.format(**t, **_art(t)))
    return t
