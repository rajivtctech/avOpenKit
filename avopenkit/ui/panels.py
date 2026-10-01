"""One small form per task. A panel only collects settings; the task module builds the command."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QPushButton, QRadioButton, QSpinBox,
                             QVBoxLayout, QWidget)

from ..core.probe import MediaInfo
from ..tasks import audio, convert, gif, join, rotate, shrink, subtitles, trim

MEDIA_FILTER = "*.mp4 *.m4v *.mov *.mkv *.webm *.avi *.wmv *.flv *.mpg *.mpeg *.ts *.3gp " \
               "*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.wma *.gif"


def seconds_box(maximum: float = 86400.0) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(2)
    box.setSingleStep(0.5)
    box.setRange(0.0, maximum)
    box.setSuffix(" s")
    return box


class TaskPanel(QWidget):
    """Base class. Subclasses set `module`, build their widgets and return a Settings object."""

    changed = pyqtSignal()
    module = None
    uses_preview = False          # True for tasks that select a section of the file (F18)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.media: MediaInfo | None = None
        self.preview = None
        self.form = QFormLayout(self)

    def attach_preview(self, preview) -> None:
        self.preview = preview

    def _time_row(self, box: QDoubleSpinBox, button_text: str) -> QHBoxLayout:
        """A seconds box with a button that sets it from the preview's current position."""
        button = QPushButton(button_text)
        button.clicked.connect(lambda: self._take_position(box))
        box.valueChanged.connect(self._show_in_preview)
        row = QHBoxLayout()
        row.addWidget(box, 1)
        row.addWidget(button)
        return row

    def _take_position(self, box: QDoubleSpinBox) -> None:
        if self.preview is not None and self.preview.media is not None:
            box.setValue(round(self.preview.position(), 2))

    def _show_in_preview(self, seconds: float) -> None:
        """Typing a time shows that moment, so the cut point can be seen."""
        if (self.preview is not None and self.preview.media is not None and self.isVisible()
                and abs(self.preview.position() - seconds) > 0.02):
            self.preview.seek(seconds)

    def title(self) -> str:
        raise NotImplementedError

    def blurb(self) -> str:
        raise NotImplementedError

    def set_media(self, media: MediaInfo | None) -> None:
        self.media = media

    def settings(self):
        raise NotImplementedError

    def needs_media(self) -> bool:
        return True

    def _radio_pair(self, first: str, second: str) -> tuple[QRadioButton, QRadioButton]:
        a, b = QRadioButton(first), QRadioButton(second)
        a.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(a)
        group.addButton(b)
        a.toggled.connect(self.changed)
        return a, b


class TrimPanel(TaskPanel):
    module = trim
    uses_preview = True

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.start, self.end = seconds_box(), seconds_box()
        self.fast, self.exact = self._radio_pair(
            self.tr("Fast - no quality loss, starts on a keyframe"),
            self.tr("Exact - re-encodes, cuts exactly where asked"))
        self.form.addRow(self.tr("Start"), self._time_row(self.start, self.tr("Start here")))
        self.form.addRow(self.tr("End"), self._time_row(self.end, self.tr("End here")))
        self.form.addRow(self.tr("Method"), self.fast)
        self.form.addRow("", self.exact)
        self.start.valueChanged.connect(self.changed)
        self.end.valueChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Trim")

    def blurb(self) -> str:
        return self.tr("Keep the part between two points and drop the rest.")

    def set_media(self, media) -> None:
        super().set_media(media)
        if media:
            for box in (self.start, self.end):
                box.blockSignals(True)
                box.setMaximum(max(media.duration, 0.01))
            self.start.setValue(0.0)
            self.end.setValue(media.duration)
            for box in (self.start, self.end):
                box.blockSignals(False)

    def settings(self):
        return trim.Settings(self.start.value(), self.end.value(), self.exact.isChecked())


class ShrinkPanel(TaskPanel):
    module = shrink

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.size = QDoubleSpinBox()
        self.size.setRange(0.1, 100000.0)
        self.size.setDecimals(1)
        self.size.setValue(25.0)
        self.size.setSuffix(" MB")
        self.audio = QComboBox()
        for kbps in (64, 96, 128, 192):
            self.audio.addItem(self.tr("{0} kbit/s").format(kbps), kbps)
        self.audio.setCurrentIndex(1)
        self.form.addRow(self.tr("Target size"), self.size)
        self.form.addRow(self.tr("Sound quality"), self.audio)
        self.size.valueChanged.connect(self.changed)
        self.audio.currentIndexChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Shrink to a size")

    def blurb(self) -> str:
        return self.tr("Make a video small enough to send, by choosing the file size you need.")

    def settings(self):
        return shrink.Settings(self.size.value(), self.audio.currentData())


class ConvertPanel(TaskPanel):
    module = convert

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.target = QComboBox()
        self.target.addItem(self.tr("MP4 - plays almost everywhere"), "mp4")
        self.target.addItem(self.tr("WebM - for web pages"), "webm")
        self.target.addItem(self.tr("MKV - keeps everything, including subtitles"), "mkv")
        self.target.addItem(self.tr("MOV - for Apple software"), "mov")
        self.quality = QComboBox()
        self.quality.addItem(self.tr("High quality, larger file"), "high")
        self.quality.addItem(self.tr("Balanced"), "medium")
        self.quality.addItem(self.tr("Smaller file, lower quality"), "small")
        self.quality.setCurrentIndex(1)
        self.form.addRow(self.tr("Convert to"), self.target)
        self.form.addRow(self.tr("If re-encoding is needed"), self.quality)
        self.target.currentIndexChanged.connect(self.changed)
        self.quality.currentIndexChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Convert format")

    def blurb(self) -> str:
        return self.tr("Change the file type. Audio and video are copied untouched when the "
                       "new type can hold them.")

    def settings(self):
        return convert.Settings(self.target.currentData(), self.quality.currentData())


class AudioPanel(TaskPanel):
    module = audio

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.format = QComboBox()
        self.format.addItem(self.tr("Keep the original audio - no quality loss"), "copy")
        self.format.addItem(self.tr("MP3 - plays everywhere"), "mp3")
        self.format.addItem(self.tr("M4A (AAC)"), "m4a")
        self.format.addItem(self.tr("Opus - smallest"), "opus")
        self.format.addItem(self.tr("WAV - uncompressed, large"), "wav")
        self.form.addRow(self.tr("Save as"), self.format)
        self.format.currentIndexChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Extract audio")

    def blurb(self) -> str:
        return self.tr("Save just the sound from a video as an audio file.")

    def settings(self):
        return audio.Settings(self.format.currentData())


class JoinPanel(TaskPanel):
    module = join
    request_probe = pyqtSignal(list)      # paths the window should probe and hand back

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.clips: list[MediaInfo] = []
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        add = QPushButton(self.tr("Add clips…"))
        remove = QPushButton(self.tr("Remove"))
        up, down = QPushButton(self.tr("Move up")), QPushButton(self.tr("Move down"))
        buttons = QHBoxLayout()
        for b in (add, remove, up, down):
            buttons.addWidget(b)
        buttons.addStretch()
        box = QVBoxLayout()
        box.addWidget(self.list)
        box.addLayout(buttons)
        self.form.addRow(QLabel(self.tr("Clips, in playing order")))
        self.form.addRow(box)
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))

    def title(self) -> str:
        return self.tr("Join clips")

    def blurb(self) -> str:
        return self.tr("Put several clips end to end to make one file.")

    def needs_media(self) -> bool:
        return False

    def set_media(self, media) -> None:
        super().set_media(media)
        if media and not self.clips:
            self.add_clips([media])

    def add_clips(self, clips: list[MediaInfo]) -> None:
        self.clips.extend(clips)
        self._refill()

    def _refill(self, select: int | None = None) -> None:
        self.list.clear()
        for c in self.clips:
            self.list.addItem(c.path.name)
        if select is not None and 0 <= select < len(self.clips):
            self.list.setCurrentRow(select)
        self.changed.emit()

    def _add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("Add clips"), "",
                                                self.tr("Media files") + f" ({MEDIA_FILTER});;"
                                                + self.tr("All files") + " (*)")
        if paths:
            self.request_probe.emit(paths)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            del self.clips[row]
            self._refill(min(row, len(self.clips) - 1))

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        target = row + step
        if row >= 0 and 0 <= target < len(self.clips):
            self.clips[row], self.clips[target] = self.clips[target], self.clips[row]
            self._refill(target)

    def settings(self):
        return join.Settings(list(self.clips))

    def first_clip(self) -> MediaInfo | None:
        return self.clips[0] if self.clips else None


class RotatePanel(TaskPanel):
    module = rotate

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.action = QComboBox()
        self.action.addItem(self.tr("Turn right (clockwise)"), "right")
        self.action.addItem(self.tr("Turn left (counter-clockwise)"), "left")
        self.action.addItem(self.tr("Turn upside down"), "180")
        self.action.addItem(self.tr("Mirror left-right"), "hflip")
        self.action.addItem(self.tr("Mirror top-bottom"), "vflip")
        self.bake = QCheckBox(self.tr("Bake in - re-encode so every player shows it turned"))
        self.form.addRow(self.tr("Rotation"), self.action)
        self.form.addRow("", self.bake)
        self.action.currentIndexChanged.connect(self.changed)
        self.bake.toggled.connect(self.changed)

    def title(self) -> str:
        return self.tr("Fix rotation")

    def blurb(self) -> str:
        return self.tr("Turn a video that plays sideways or upside down.")

    def settings(self):
        return rotate.Settings(self.action.currentData(), self.bake.isChecked())


class GifPanel(TaskPanel):
    module = gif
    uses_preview = True

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.start, self.length = seconds_box(), seconds_box(600.0)
        self.length.setValue(3.0)
        self.width = QSpinBox()
        self.width.setRange(16, 4096)
        self.width.setSingleStep(40)
        self.width.setValue(480)
        self.width.setSuffix(" px")
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(12)
        self.form.addRow(self.tr("Start"), self._time_row(self.start, self.tr("Start here")))
        self.form.addRow(self.tr("Length"), self.length)
        self.form.addRow(self.tr("Width"), self.width)
        self.form.addRow(self.tr("Frames per second"), self.fps)
        for w in (self.start, self.length, self.width, self.fps):
            w.valueChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Make a GIF")

    def blurb(self) -> str:
        return self.tr("Turn a few seconds of video into a looping GIF picture.")

    def set_media(self, media) -> None:
        super().set_media(media)
        if media:
            self.start.blockSignals(True)
            self.start.setMaximum(max(media.duration, 0.01))
            self.start.setValue(0.0)
            self.start.blockSignals(False)

    def settings(self):
        return gif.Settings(self.start.value(), self.length.value(), self.width.value(),
                            self.fps.value())


class SubtitlesPanel(TaskPanel):
    module = subtitles

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.path = QLineEdit()
        self.path.setPlaceholderText(self.tr("Choose an .srt, .ass or .vtt file"))
        browse = QPushButton(self.tr("Browse…"))
        row = QHBoxLayout()
        row.addWidget(self.path)
        row.addWidget(browse)
        self.track, self.burn = self._radio_pair(
            self.tr("Add as a track - can be switched on and off, no re-encoding"),
            self.tr("Burn in - always visible, re-encodes the video"))
        self.form.addRow(self.tr("Subtitle file"), row)
        self.form.addRow(self.tr("How"), self.track)
        self.form.addRow("", self.burn)
        browse.clicked.connect(self._browse)
        self.path.textChanged.connect(self.changed)

    def title(self) -> str:
        return self.tr("Subtitles")

    def blurb(self) -> str:
        return self.tr("Add subtitles to a video from a subtitle file.")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose a subtitle file"), "",
            self.tr("Subtitle files") + " (*.srt *.ass *.ssa *.vtt)")
        if path:
            self.path.setText(path)

    def settings(self):
        text = self.path.text().strip()
        return subtitles.Settings(Path(text) if text else None, self.burn.isChecked())


PANELS = [TrimPanel, ShrinkPanel, ConvertPanel, AudioPanel, JoinPanel, RotatePanel, GifPanel,
          SubtitlesPanel]
