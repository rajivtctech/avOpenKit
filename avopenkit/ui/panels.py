"""One small form per task. A panel only collects settings; the task module builds the command."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QPushButton, QRadioButton,
                             QSpinBox, QVBoxLayout, QWidget)

from ..core.probe import MediaInfo
from ..tasks import audio, convert, gif, join, rotate, shrink, subtitles, trim
from ..tasks.base import X264_PRESETS

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
        self.expert = False
        self.form = QFormLayout(self)
        # Codec-level options. Hidden in simple mode, and then not used either: settings()
        # passes them on only in expert mode, so a hidden value never changes the result.
        self.expert_box = QGroupBox(self.tr("Expert options"))
        self.expert_form = QFormLayout(self.expert_box)
        self.expert_box.setVisible(False)

    def attach_preview(self, preview) -> None:
        self.preview = preview

    # -- presets (spec F10) --------------------------------------------------------------

    def preset_fields(self) -> dict:
        """name -> (widget, is_expert) for everything a preset stores. File-specific values
        (start and end times, the subtitle file, the clips to join, the result name) are left
        out: a preset is for reuse on other files."""
        return {}

    @staticmethod
    def _read_widget(w):
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        if isinstance(w, QComboBox):
            return w.currentData() if w.currentData() is not None else w.currentText()
        if isinstance(w, (QCheckBox, QRadioButton)):
            return w.isChecked()
        return w.text()

    @staticmethod
    def _write_widget(w, value) -> None:
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(value)
        elif isinstance(w, QComboBox):
            index = w.findData(value)
            if index < 0 and isinstance(value, str):
                index = w.findText(value)
            w.setCurrentIndex(max(index, 0))
        elif isinstance(w, QRadioButton):
            # An exclusive group cannot be unchecked directly: check the other button.
            other = next((b for b in w.group().buttons() if b is not w), None) if w.group() else None
            (w if value else other or w).setChecked(True)
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        else:
            w.setText(str(value))

    def state(self) -> dict:
        """What a preset saves now: expert values only when expert mode is on."""
        out = {name: self._read_widget(w) for name, (w, expert) in self.preset_fields().items()
               if self.expert or not expert}
        if self.expert and any(expert for _, expert in self.preset_fields().values()):
            out["_expert"] = True
        return out

    def set_state(self, state: dict) -> bool:
        """Apply a preset. Returns True when it holds expert values that simple mode ignores."""
        self.blockSignals(True)
        try:
            for name, (w, _expert) in self.preset_fields().items():
                if name in state:
                    try:
                        self._write_widget(w, state[name])
                    except (TypeError, ValueError):
                        pass                 # a preset from another version: skip that value
        finally:
            self.blockSignals(False)
        self.changed.emit()
        return bool(state.get("_expert")) and not self.expert

    def set_expert(self, on: bool) -> None:
        self.expert = on
        self.expert_box.setVisible(on)
        self.changed.emit()

    def _finish(self) -> None:
        """Called last by each panel: put the expert options under its ordinary rows."""
        self.form.addRow(self.expert_box)

    def _crf_box(self, default: int, maximum: int = 51) -> QSpinBox:
        box = QSpinBox()
        box.setRange(0, maximum)
        box.setValue(default)
        box.setToolTip(self.tr("Constant rate factor: lower is better quality and a larger "
                               "file. 18 is close to lossless to the eye, 23 is FFmpeg's "
                               "default, 28 is visibly compressed."))
        box.valueChanged.connect(self.changed)
        return box

    def _preset_box(self) -> QComboBox:
        box = QComboBox()
        for name in X264_PRESETS:
            box.addItem(name, name)
        box.setCurrentText("medium")
        box.setToolTip(self.tr("Encoder speed: slower presets make a smaller file at the same "
                               "quality, and take longer."))
        box.currentIndexChanged.connect(self.changed)
        return box

    def _kbps_box(self, default: int, automatic: bool = False) -> QSpinBox:
        """Audio bitrate. With automatic=True the lowest value means 'use the default'."""
        box = QSpinBox()
        box.setRange(0 if automatic else 8, 512)
        box.setSingleStep(16)
        box.setSuffix(" kbit/s")
        if automatic:
            box.setSpecialValueText(self.tr("Default"))
        box.setToolTip(self.tr("Audio bitrate: higher is better quality and a larger file. "
                               "128 kbit/s is fine for most listening; 192 for music."))
        box.setValue(default)
        box.valueChanged.connect(self.changed)
        return box

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
        self.start.setToolTip(self.tr("Where the part you want to keep begins."))
        self.end.setToolTip(self.tr("Where the part you want to keep ends."))
        self.fast.setToolTip(self.tr(
            "Copies the audio and video as they are. Instant and lossless, but a video can "
            "only be cut at a keyframe, so the result may begin a little before the start "
            "you chose."))
        self.exact.setToolTip(self.tr(
            "Re-encodes the video so it can be cut at any frame. Slower, with a very small "
            "loss of quality."))
        self.crf, self.preset, self.kbps = self._crf_box(18), self._preset_box(), self._kbps_box(192)
        self.expert_form.addRow(self.tr("Quality (CRF), exact trim"), self.crf)
        self.expert_form.addRow(self.tr("Encoder speed, exact trim"), self.preset)
        self.expert_form.addRow(self.tr("Audio bitrate, exact trim"), self.kbps)
        self._finish()
        self.start.valueChanged.connect(self.changed)
        self.end.valueChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"exact": (self.exact, False), "crf": (self.crf, True),
                "preset": (self.preset, True), "audio_kbps": (self.kbps, True)}

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
        s = trim.Settings(self.start.value(), self.end.value(), self.exact.isChecked())
        if self.expert:
            s.crf, s.preset, s.audio_kbps = (self.crf.value(), self.preset.currentText(),
                                             self.kbps.value())
        return s


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
        self.size.setToolTip(self.tr(
            "The largest size the result may be. The video quality is set to whatever fits; "
            "a smaller size or a longer video means lower quality."))
        self.audio.setToolTip(self.tr(
            "How much of the size is spent on sound. 96 kbit/s suits speech and most video; "
            "choose more for music."))
        self.form.addRow(self.tr("Target size"), self.size)
        self.form.addRow(self.tr("Sound quality"), self.audio)
        self.preset = self._preset_box()
        self.height = QComboBox()
        self.height.addItem(self.tr("Automatic - chosen from the bitrate"), None)
        self.height.addItem(self.tr("Keep the original size"), 0)
        for h in (1080, 720, 480, 360, 240):
            self.height.addItem(f"{h}p", h)
        self.height.currentIndexChanged.connect(self.changed)
        self.height.setToolTip(self.tr(
            "Automatic makes the picture smaller when the size leaves too little for a clear "
            "picture at the original size."))
        self.expert_form.addRow(self.tr("Encoder speed"), self.preset)
        self.expert_form.addRow(self.tr("Picture height"), self.height)
        self._finish()
        self.size.valueChanged.connect(self.changed)
        self.audio.currentIndexChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"size": (self.size, False), "audio_kbps": (self.audio, False),
                "preset": (self.preset, True), "height": (self.height, True)}

    def title(self) -> str:
        return self.tr("Shrink to a size")

    def blurb(self) -> str:
        return self.tr("Make a video small enough to send, by choosing the file size you need.")

    def settings(self):
        s = shrink.Settings(self.size.value(), self.audio.currentData())
        if self.expert:
            s.preset, s.height = self.preset.currentText(), self.height.currentData()
        return s


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
        self.target.setToolTip(self.tr("The kind of file to make."))
        self.quality.setToolTip(self.tr(
            "Used only when the audio or video cannot simply be copied into the new kind of "
            "file and has to be re-encoded."))
        self.form.addRow(self.tr("Convert to"), self.target)
        self.form.addRow(self.tr("If re-encoding is needed"), self.quality)
        self.reencode = QCheckBox(self.tr("Re-encode even what could be copied"))
        self.reencode.setToolTip(self.tr(
            "Normally audio and video that already fit the new file type are copied untouched. "
            "Tick this to re-encode them anyway, for example to make the file smaller."))
        self.reencode.toggled.connect(self.changed)
        self.crf = self._crf_box(0, 63)
        self.crf.setRange(-1, 63)
        self.crf.setSpecialValueText(self.tr("From the quality setting above"))
        self.crf.setValue(-1)
        self.preset, self.kbps = self._preset_box(), self._kbps_box(0, automatic=True)
        self.expert_form.addRow("", self.reencode)
        self.expert_form.addRow(self.tr("Quality (CRF)"), self.crf)
        self.expert_form.addRow(self.tr("Encoder speed (H.264)"), self.preset)
        self.expert_form.addRow(self.tr("Audio bitrate"), self.kbps)
        self._finish()
        self.target.currentIndexChanged.connect(self.changed)
        self.quality.currentIndexChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"target": (self.target, False), "quality": (self.quality, False),
                "reencode": (self.reencode, True), "crf": (self.crf, True),
                "preset": (self.preset, True), "audio_kbps": (self.kbps, True)}

    def title(self) -> str:
        return self.tr("Convert format")

    def blurb(self) -> str:
        return self.tr("Change the file type. Audio and video are copied untouched when the "
                       "new type can hold them.")

    def settings(self):
        s = convert.Settings(self.target.currentData(), self.quality.currentData())
        if self.expert:
            s.reencode, s.preset = self.reencode.isChecked(), self.preset.currentText()
            s.crf = self.crf.value() if self.crf.value() >= 0 else None
            s.audio_kbps = self.kbps.value() or None
        return s


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
        self.format.setToolTip(self.tr(
            "Keeping the original audio loses nothing. The other choices convert it, which "
            "is useful when a player needs a particular kind of file."))
        self.form.addRow(self.tr("Save as"), self.format)
        self.kbps = self._kbps_box(0, automatic=True)
        self.kbps.setToolTip(self.tr("Higher is better quality and a larger file. Default "
                                     "leaves the choice to avOpenKit. Not used for WAV."))
        self.expert_form.addRow(self.tr("Bitrate (MP3, M4A, Opus)"), self.kbps)
        self._finish()
        self.format.currentIndexChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"format": (self.format, False), "kbps": (self.kbps, True)}

    def title(self) -> str:
        return self.tr("Extract audio")

    def blurb(self) -> str:
        return self.tr("Save just the sound from a video as an audio file.")

    def settings(self):
        s = audio.Settings(self.format.currentData())
        if self.expert:
            s.kbps = self.kbps.value() or None
        return s


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
        self.list.setToolTip(self.tr("The clips are joined from top to bottom."))
        self.reencode = QCheckBox(self.tr("Re-encode even when the clips match"))
        self.reencode.setToolTip(self.tr(
            "Matching clips are normally joined without re-encoding. Tick this if the joined "
            "file stutters or loses sound at the joins."))
        self.reencode.toggled.connect(self.changed)
        self.crf, self.preset = self._crf_box(20), self._preset_box()
        self.expert_form.addRow("", self.reencode)
        self.expert_form.addRow(self.tr("Quality (CRF), when re-encoding"), self.crf)
        self.expert_form.addRow(self.tr("Encoder speed, when re-encoding"), self.preset)
        self._finish()
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))

    def preset_fields(self) -> dict:
        return {"reencode": (self.reencode, True), "crf": (self.crf, True),
                "preset": (self.preset, True)}

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
        s = join.Settings(list(self.clips))
        if self.expert:
            s.reencode, s.crf, s.preset = (self.reencode.isChecked(), self.crf.value(),
                                           self.preset.currentText())
        return s

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
        self.action.setToolTip(self.tr("Which way to turn the picture as you see it now."))
        self.bake.setToolTip(self.tr(
            "Without this, only a note saying \"show this turned\" is stored in the file: "
            "instant and lossless, but a few players ignore it. With it, the picture itself "
            "is turned and re-encoded."))
        self.form.addRow(self.tr("Rotation"), self.action)
        self.form.addRow("", self.bake)
        self.crf, self.preset = self._crf_box(18), self._preset_box()
        self.expert_form.addRow(self.tr("Quality (CRF), when baking in"), self.crf)
        self.expert_form.addRow(self.tr("Encoder speed, when baking in"), self.preset)
        self._finish()
        self.action.currentIndexChanged.connect(self.changed)
        self.bake.toggled.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"action": (self.action, False), "bake": (self.bake, False),
                "crf": (self.crf, True), "preset": (self.preset, True)}

    def title(self) -> str:
        return self.tr("Fix rotation")

    def blurb(self) -> str:
        return self.tr("Turn a video that plays sideways or upside down.")

    def settings(self):
        s = rotate.Settings(self.action.currentData(), self.bake.isChecked())
        if self.expert:
            s.crf, s.preset = self.crf.value(), self.preset.currentText()
        return s


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
        self.start.setToolTip(self.tr("Where in the video the GIF begins."))
        self.length.setToolTip(self.tr("How many seconds of video the GIF shows."))
        self.width.setToolTip(self.tr(
            "Width of the GIF in pixels; the height follows. Halving the width makes the "
            "file roughly a quarter of the size."))
        self.fps.setToolTip(self.tr(
            "How many pictures per second. 10 to 15 looks smooth enough; fewer makes a "
            "smaller file."))
        self.form.addRow(self.tr("Length"), self.length)
        self.form.addRow(self.tr("Width"), self.width)
        self.form.addRow(self.tr("Frames per second"), self.fps)
        self.loop = QCheckBox(self.tr("Repeat for ever"))
        self.loop.setChecked(True)
        self.loop.setToolTip(self.tr("Untick to make a GIF that plays once and stops."))
        self.loop.toggled.connect(self.changed)
        self.dither = QComboBox()
        self.dither.setToolTip(self.tr(
            "A GIF has only 256 colours. Dithering mixes dots of those colours to imitate "
            "the rest; it looks smoother but makes the file larger."))
        self.dither.addItem(self.tr("Sierra - FFmpeg's default"), "sierra2_4a")
        self.dither.addItem(self.tr("Floyd-Steinberg"), "floyd_steinberg")
        self.dither.addItem(self.tr("Bayer - regular pattern, smaller file"), "bayer")
        self.dither.addItem(self.tr("None - flat colours, smallest file"), "none")
        self.dither.currentIndexChanged.connect(self.changed)
        self.expert_form.addRow("", self.loop)
        self.expert_form.addRow(self.tr("Dithering"), self.dither)
        self._finish()
        for w in (self.start, self.length, self.width, self.fps):
            w.valueChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"length": (self.length, False), "width": (self.width, False),
                "fps": (self.fps, False), "loop": (self.loop, True),
                "dither": (self.dither, True)}

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
        s = gif.Settings(self.start.value(), self.length.value(), self.width.value(),
                         self.fps.value())
        if self.expert:
            s.loop, s.dither = self.loop.isChecked(), self.dither.currentData()
        return s


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
        self.path.setToolTip(self.tr("The file holding the subtitle text and timings."))
        self.track.setToolTip(self.tr(
            "The subtitles are stored beside the video and the viewer switches them on in "
            "the player. Nothing is re-encoded. Some players and websites do not show them."))
        self.burn.setToolTip(self.tr(
            "The words become part of the picture, so they show everywhere, but they cannot "
            "be switched off and the video is re-encoded."))
        self.form.addRow(self.tr("Subtitle file"), row)
        self.form.addRow(self.tr("How"), self.track)
        self.form.addRow("", self.burn)
        self.crf, self.preset = self._crf_box(20), self._preset_box()
        self.language = QLineEdit()
        self.language.setMaxLength(3)
        self.language.setPlaceholderText(self.tr("for example hin, eng, spa"))
        self.language.setToolTip(self.tr(
            "A two- or three-letter language code stored with the track, so players can list "
            "it by language. Used only when adding a track."))
        self.language.textChanged.connect(self.changed)
        self.expert_form.addRow(self.tr("Language of the track"), self.language)
        self.expert_form.addRow(self.tr("Quality (CRF), when burning in"), self.crf)
        self.expert_form.addRow(self.tr("Encoder speed, when burning in"), self.preset)
        self._finish()
        browse.clicked.connect(self._browse)
        self.path.textChanged.connect(self.changed)

    def preset_fields(self) -> dict:
        return {"burn": (self.burn, False), "crf": (self.crf, True),
                "preset": (self.preset, True), "language": (self.language, True)}

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
        s = subtitles.Settings(Path(text) if text else None, self.burn.isChecked())
        if self.expert:
            s.crf, s.preset = self.crf.value(), self.preset.currentText()
            s.language = self.language.text().strip().lower()
        return s


PANELS = [TrimPanel, ShrinkPanel, ConvertPanel, AudioPanel, JoinPanel, RotatePanel, GifPanel,
          SubtitlesPanel]
