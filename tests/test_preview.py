"""The preview widget: Qt player back end, FFmpeg stills fallback, and its use by the panels."""

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QApplication

from avopenkit.core import probe
from avopenkit.core.probe import MediaInfo, Stream
from avopenkit.ui.main_window import MainWindow
from avopenkit.ui.preview import PreviewWidget


def wait_until(app, condition, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if condition():
            return True
    return False


@pytest.fixture
def preview(app, tools):
    w = PreviewWidget(tools)
    w.resize(640, 420)
    w.show()
    yield w
    w.unload()
    w.close()


@pytest.fixture
def media(tools, clips):
    return probe.probe(clips["main"], tools, keyframes=True)


def test_qt_player_shows_a_frame_and_seeks(app, preview, media):
    preview.load(media)
    assert wait_until(app, lambda: preview.got_frame), "no frame from Qt's player"
    assert not preview.stills and not preview.note.isVisible()
    assert preview.slider.maximum() == int(media.duration * 1000)
    seen = []
    preview.position_changed.connect(seen.append)
    preview.seek(3.2)
    assert wait_until(app, lambda: abs(preview.position() - 3.2) < 0.05)
    assert seen and preview.slider.value() == pytest.approx(3200, abs=50)
    assert preview.time.text().startswith("0:03.2")
    preview.seek(999)                                    # clamped to the end of the file
    assert wait_until(app, lambda: abs(preview.position() - media.duration) < 0.1)


def test_sound_is_attached_only_when_play_is_pressed(app, preview, media):
    preview.load(media)
    assert wait_until(app, lambda: preview.got_frame)
    preview.seek(1.0)
    wait_until(app, lambda: abs(preview.position() - 1.0) < 0.05)
    assert not preview.audio_attached and preview.player.audioOutput() is None


def test_stills_on_request(app, preview, media):
    preview.load(media)
    reasons = []
    preview.stills_engaged.connect(reasons.append)
    preview.force_stills()
    assert preview.stills and reasons and preview.note.isVisible()
    assert not preview.play_button.isEnabled()
    assert wait_until(app, lambda: preview._still_source is not None), "no still from FFmpeg"
    assert preview._still_source.width() == 640
    first = preview._still_source.toImage()
    preview.seek(4.0)
    assert preview.position() == 4.0 and preview.slider.value() == 4000
    assert wait_until(app, lambda: preview._grab is None and preview._pending is None
                      and preview._still_source.toImage() != first)
    preview.toggle_play()                                # does nothing in stills mode
    assert preview.position() == 4.0


def test_rapid_scrubbing_keeps_only_the_newest_request(app, preview, media):
    preview.load(media)
    preview.force_stills()
    for t in (1.0, 2.0, 3.0, 4.0, 5.0):
        preview.seek(t)
    assert preview._pending == 5.0                       # 1..4 were dropped, not queued
    assert wait_until(app, lambda: preview._grab is None and preview._pending is None)


def test_falls_back_by_itself_when_the_length_disagrees(app, preview, media):
    preview.load(media)
    preview._on_duration(int((media.duration + 5) * 1000))
    assert preview.stills
    assert wait_until(app, lambda: preview._still_source is not None)


def test_falls_back_by_itself_on_a_file_qt_cannot_play(app, preview, tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"this is not a video" * 50)
    fake = MediaInfo(bad, 10.0, bad.stat().st_size, "mp4", 0,
                     (Stream(0, "video", "h264", 640, 360, 30.0),))
    preview.load(fake)
    assert wait_until(app, lambda: preview.stills, timeout=10), "fallback did not engage"
    assert preview.note.isVisible()
    preview.seek(2.0)                                    # FFmpeg fails too; nothing crashes
    assert wait_until(app, lambda: preview._grab is None)
    assert preview._still_source is None


def test_audio_only_file_has_no_picture_area(app, preview, tools, clips, tmp_path):
    import subprocess
    mp3 = tmp_path / "tone.mp3"
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=3", str(mp3)], check=True)
    preview.load(probe.probe(mp3, tools))
    app.processEvents()
    assert not preview.screen.isVisible() and preview.mute_button.isEnabled()
    assert not wait_until(app, lambda: preview.stills, timeout=FRAME_WAIT)   # no false fallback


FRAME_WAIT = 4.5      # a little over FRAME_TIMEOUT_MS


def test_window_shows_preview_only_for_section_tasks(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    try:
        assert not w.preview.isVisible()
        w.open_file(clips["main"])
        shown = {w.tasks.item(r).text(): (w.tasks.setCurrentRow(r), w.preview.isVisible())[1]
                 for r in range(w.tasks.count())}
        assert [k for k, v in shown.items() if v] == ["Trim", "Make a GIF"]
        assert w.preview.media is w.media
    finally:
        w.close()


def test_start_here_and_end_here_take_the_preview_position(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    try:
        w.open_file(clips["main"])
        w.tasks.setCurrentRow(0)
        panel = w.panel()
        assert wait_until(app, lambda: w.preview.got_frame)
        w.preview.seek(2.5)
        assert wait_until(app, lambda: abs(w.preview.position() - 2.5) < 0.05)
        panel._take_position(panel.start)
        w.preview.seek(6.0)
        assert wait_until(app, lambda: abs(w.preview.position() - 6.0) < 0.05)
        panel._take_position(panel.end)
        assert panel.start.value() == pytest.approx(2.5, abs=0.05)
        assert panel.end.value() == pytest.approx(6.0, abs=0.05)
        assert "-ss 2.5" in w.console.toPlainText() and "-to 6.0" in w.console.toPlainText()
        panel.start.setValue(1.0)                        # typing a time shows that moment
        assert wait_until(app, lambda: abs(w.preview.position() - 1.0) < 0.05)
    finally:
        w.close()
