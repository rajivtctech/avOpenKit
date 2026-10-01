"""Preview with a scrub bar (spec F18).

One widget, two back ends behind the same few methods (load, seek, position, play, pause):

* Qt's media player - plays the file with sound;
* single frames extracted by FFmpeg - silent stills, used automatically when Qt cannot play
  the file.

Sound is attached to Qt's player only when Play is first pressed. With an audio output attached,
QMediaPlayer.stop() was seen to deadlock occasionally (Qt 6.11, about one stop in several
hundred; never without an audio output - see trials/player_stop_hang.py and DESIGN.md 1.3).
Scrubbing, which is most of what the preview is used for, therefore never has one attached.

The preview is for looking, not measuring: the position it reports is only what the user
points at. Cut points and durations are worked out from ffprobe data by the task modules.
"""

from __future__ import annotations

from PyQt6.QtCore import QProcess, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget,
                             QVBoxLayout, QWidget)

from ..core.ffmpeg import Tools, apply_child_env
from ..core.probe import MediaInfo
from ..tasks.base import clock
from . import icons
from .widgets import ThumbLoader, Timeline

FRAME_TIMEOUT_MS = 4000      # no picture this long after loading a video: use stills
DURATION_TOLERANCE = 1.0     # seconds Qt's idea of the length may differ from ffprobe's
STILL_WIDTH = 640


class PreviewWidget(QWidget):
    position_changed = pyqtSignal(float)     # seconds
    stills_engaged = pyqtSignal(str)         # reason, when the fallback takes over

    def __init__(self, tools: Tools, parent=None) -> None:
        super().__init__(parent)
        self.tools = tools
        self.media: MediaInfo | None = None
        self.stills = False
        self.got_frame = False
        self._pos = 0.0
        self._grab: QProcess | None = None
        self._pending: float | None = None
        self._still_source: QPixmap | None = None

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio_attached = False          # attached on first Play, see the module note
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)
        self.still = QLabel()
        self.still.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still.setStyleSheet("background: black;")
        self.still.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.screen = QStackedWidget()
        self.screen.addWidget(self.video)
        self.screen.addWidget(self.still)
        self.screen.setMinimumHeight(200)
        self.screen.setMaximumHeight(330)

        self.play_button = QPushButton(self.tr("Play"))
        self.mute_button = QPushButton(self.tr("Mute"))
        self.mute_button.setCheckable(True)
        self.slider = Timeline()
        self.slider.setToolTip(self.tr(
            "Click or drag to move through the video. The lit part is what the task will use; "
            "the green ticks underneath are keyframes, where a fast trim can begin."))
        self.thumbs = ThumbLoader(tools, self)
        self.thumbs.ready.connect(self.slider.set_thumb)
        self.slider.setRange(0, 0)
        self.slider.setSingleStep(100)       # milliseconds per arrow key
        self.slider.setPageStep(1000)
        self.time = QLabel("0:00.0 / 0:00.0")
        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.note.setVisible(False)
        bar = QHBoxLayout()
        bar.addWidget(self.play_button)
        bar.addWidget(self.mute_button)
        bar.addStretch()
        bar.addWidget(self.time)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        box.addWidget(self.screen, 1)
        box.addWidget(self.slider)
        box.addLayout(bar)
        box.addWidget(self.note)
        self.apply_icons()

        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(
            lambda: self._use_stills(self.tr("the built-in player showed no picture")))

        self.play_button.clicked.connect(self.toggle_play)
        self.mute_button.toggled.connect(self.audio.setMuted)
        self.mute_button.toggled.connect(lambda _on: self.apply_icons())
        self.slider.sliderMoved.connect(lambda ms: self.seek(ms / 1000))
        self.slider.actionTriggered.connect(self._slider_action)
        self.player.positionChanged.connect(self._on_player_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.errorOccurred.connect(self._on_error)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.playbackStateChanged.connect(self._on_state)
        self.video.videoSink().videoFrameChanged.connect(self._on_frame)

    # ------------------------------------------------------------------ interface

    def apply_icons(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(icons.icon("pause" if playing else "play"))
        self.mute_button.setIcon(icons.icon("mute" if self.mute_button.isChecked() else "volume"))

    def set_selection(self, start: float | None, end: float | None = None) -> None:
        """Light up the part of the file the task will use."""
        self.slider.set_selection(start, end)

    def load(self, media: MediaInfo) -> None:
        self._stop_grab()
        self.media = media
        self.stills = False
        self.got_frame = False
        self._pos = 0.0
        self._still_source = None
        self.still.clear()
        self.note.setVisible(False)
        self.play_button.setEnabled(True)
        self.mute_button.setEnabled(media.audio is not None)
        self.slider.setRange(0, int(media.duration * 1000))
        self.slider.setValue(0)
        self.slider.set_media(media.keyframes, media.video is not None)
        self.slider.set_selection(None)
        if media.video is not None and media.duration > 0:
            self.thumbs.load(media.path, self.slider.thumb_times(media.duration))
        else:
            self.thumbs.cancel()
        self.screen.setVisible(media.video is not None)
        self.screen.setCurrentWidget(self.video)
        self._show_time()
        self.player.setSource(QUrl.fromLocalFile(str(media.path)))
        self.player.pause()                  # paused, so the first frame is shown
        if media.video is not None:
            self._frame_timer.start(FRAME_TIMEOUT_MS)

    def unload(self) -> None:
        self._frame_timer.stop()
        self.thumbs.cancel()
        self._stop_grab()
        self.player.stop()
        self.player.setSource(QUrl())
        self.media = None

    def position(self) -> float:
        return self._pos

    def seek(self, seconds: float) -> None:
        if self.media is None:
            return
        seconds = max(0.0, min(seconds, self.media.duration))
        if self.stills:
            self._pos = seconds
            self._show_time()
            self._request_still(seconds)
            self.position_changed.emit(seconds)
        else:
            self.player.setPosition(int(seconds * 1000))

    def toggle_play(self) -> None:
        if self.stills or self.media is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.media.duration and self._pos >= self.media.duration - 0.05:
                self.player.setPosition(0)
            if not self.audio_attached and self.media.audio is not None:
                self.player.setAudioOutput(self.audio)
                self.audio_attached = True
            self.player.play()

    def pause(self) -> None:
        if not self.stills and self.media is not None:
            self.player.pause()

    def force_stills(self) -> None:
        """Switch to FFmpeg stills on request (also used by the tests)."""
        self._use_stills(self.tr("requested"))

    # ------------------------------------------------------------------ Qt player

    def _on_frame(self, frame) -> None:
        if frame.isValid():
            self.got_frame = True
            self._frame_timer.stop()

    def _on_player_position(self, ms: int) -> None:
        if self.stills:
            return
        self._pos = ms / 1000
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self._show_time()
        self.position_changed.emit(self._pos)

    def _on_duration(self, ms: int) -> None:
        if (self.media is not None and not self.stills and ms > 0 and self.media.duration
                and abs(ms / 1000 - self.media.duration) > DURATION_TOLERANCE):
            self._use_stills(self.tr("the built-in player read the length of the file wrongly"))

    def _on_error(self, error, text: str = "") -> None:
        if error != QMediaPlayer.Error.NoError:
            self._use_stills(text or self.tr("the built-in player could not open the file"))

    def _on_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._use_stills(self.tr("the built-in player could not open the file"))

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText(self.tr("Pause") if playing else self.tr("Play"))
        self.apply_icons()

    def _slider_action(self, _action: int) -> None:
        # Clicks on the groove and arrow/page keys; dragging is handled by sliderMoved.
        if not self.slider.isSliderDown():
            QTimer.singleShot(0, lambda: self.seek(self.slider.sliderPosition() / 1000))

    def _show_time(self) -> None:
        total = self.media.duration if self.media else 0.0
        self.time.setText(f"{clock(self._pos)} / {clock(total)}")
        if self.stills and not self.slider.isSliderDown():
            self.slider.setValue(int(self._pos * 1000))

    # ------------------------------------------------------------------ FFmpeg stills

    def _use_stills(self, reason: str) -> None:
        if self.stills or self.media is None:
            return
        self.stills = True
        self._frame_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.play_button.setEnabled(False)
        self.mute_button.setEnabled(False)
        self.screen.setCurrentWidget(self.still)
        if self.media.video is not None:
            text = self.tr("Showing still pictures without sound, because {0}. "
                           "This does not affect the result.").format(reason)
        else:
            text = self.tr("This file cannot be played here, because {0}. "
                           "This does not affect the result.").format(reason)
        self.note.setText(text)
        self.note.setVisible(True)
        self.stills_engaged.emit(reason)
        self._request_still(self._pos)

    def _request_still(self, seconds: float) -> None:
        if self.media is None or self.media.video is None:
            return
        if self._grab is not None:
            self._pending = seconds          # only the newest request matters while scrubbing
            return
        p = QProcess(self)
        apply_child_env(p)
        p.finished.connect(self._still_done)
        p.errorOccurred.connect(self._still_failed)
        self._grab = p
        p.start(self.tools.ffmpeg, [
            "-v", "error", "-nostdin", "-ss", f"{seconds:.3f}", "-i", str(self.media.path),
            "-frames:v", "1", "-vf", f"scale={STILL_WIDTH}:-2", "-f", "image2pipe",
            "-c:v", "ppm", "-"])

    def _still_done(self, _code: int = 0, _status=None) -> None:
        p, self._grab = self._grab, None
        if p is None:
            return
        image = QImage.fromData(bytes(p.readAllStandardOutput()))
        p.deleteLater()
        if not image.isNull():
            self._still_source = QPixmap.fromImage(image)
            self._paint_still()
        if self._pending is not None:
            seconds, self._pending = self._pending, None
            self._request_still(seconds)

    def _still_failed(self, _error) -> None:
        if self._grab is not None and self._grab.state() == QProcess.ProcessState.NotRunning:
            self._grab.deleteLater()
            self._grab = None

    def _stop_grab(self) -> None:
        self._pending = None
        if self._grab is not None:
            p, self._grab = self._grab, None
            p.finished.disconnect()
            p.kill()
            p.waitForFinished(1000)
            p.deleteLater()

    def _paint_still(self) -> None:
        if self._still_source is not None and self.still.width() > 0:
            self.still.setPixmap(self._still_source.scaled(
                self.still.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._paint_still()
