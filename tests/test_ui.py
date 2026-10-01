"""The window, driven without a display (QT_QPA_PLATFORM=offscreen, set in conftest)."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from avopenkit.core import probe
from avopenkit.ui.main_window import MainWindow, human_size
from avopenkit.ui.panels import JoinPanel


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tools):
    w = MainWindow(tools)
    yield w
    w.close()


def wait_finished(window, timeout_ms=60000):
    loop = QEventLoop()
    result = []
    window.runner.finished.connect(lambda ok, cancelled: (result.append((ok, cancelled)), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    assert result, "the job did not finish in time"
    return result[0]


def select(window, title_part):
    for row in range(window.tasks.count()):
        if title_part in window.tasks.item(row).text():
            window.tasks.setCurrentRow(row)
            return window.panel()
    raise AssertionError(title_part)


def test_human_size():
    assert human_size(999) == "999 B" and human_size(1500) == "1.5 kB"
    assert human_size(25_000_000) == "25.0 MB"


def test_starts_empty_with_all_eight_tasks(window):
    assert window.tasks.count() == 8
    assert not window.run_button.isEnabled() and window.console.toPlainText() == ""


def test_every_task_shows_a_command_once_a_file_is_open(window, clips, srt):
    assert window.open_file(clips["main"])
    assert "640×360" in window.inspector.text()
    for row in range(window.tasks.count()):
        window.tasks.setCurrentRow(row)
        panel = window.panel()
        if isinstance(panel, JoinPanel):
            assert not window.run_button.isEnabled()          # only one clip so far
            panel.add_clips([probe.probe(clips["same"], window.tools)])
        if hasattr(panel, "path"):
            assert not window.run_button.isEnabled()          # no subtitle file yet
            panel.path.setText(str(srt))
        assert window.run_button.isEnabled(), panel.title()
        text = window.console.toPlainText()
        assert text.startswith("ffmpeg ") and window.notes.text()
        assert Path(window.output.text()) != clips["main"]


def test_unreadable_file_is_refused(window, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    bad = tmp_path / "notes.txt"
    bad.write_text("not media")
    assert not window.open_file(bad) and window.media is None


def test_trim_runs_from_the_window(window, clips, tmp_path):
    window.open_file(clips["main"])
    panel = select(window, "Trim")
    panel.start.setValue(2.0)
    panel.end.setValue(5.0)
    out = tmp_path / "from window.mp4"
    window.output.setText(str(out))
    window._output_edited()
    assert "-ss 2.000 -to 5.000" in window.console.toPlainText()
    window.run()
    assert not window.run_button.isEnabled() and window.cancel_button.isEnabled()
    ok, cancelled = wait_finished(window)
    assert ok and not cancelled
    assert probe.probe(out, window.tools).duration == pytest.approx(3, abs=0.2)
    assert window.progress.value() == 1000 and "Done" in window.status.text()
    assert window.run_button.isEnabled()
    assert Path(window.output.text()) != out        # a fresh name is suggested for the next run


def test_two_pass_shrink_runs_from_the_window(window, clips, tmp_path):
    window.open_file(clips["main"])
    panel = select(window, "Shrink")
    panel.size.setValue(0.5)
    out = tmp_path / "small.mp4"
    window.output.setText(str(out))
    window._output_edited()
    assert window.console.toPlainText().count("ffmpeg ") == 2
    window.run()
    ok, _ = wait_finished(window)
    assert ok and 0 < out.stat().st_size <= 500_000


def test_cancel_deletes_the_partial_file(window, tools, clips, tmp_path):
    from conftest import make_clip
    long_clip = make_clip(tools, tmp_path / "long.mp4", seconds=60, size="1280x720")
    window.open_file(long_clip)
    panel = select(window, "Convert")
    panel.target.setCurrentIndex(panel.target.findData("webm"))   # slow VP9 encode
    out = tmp_path / "never.webm"
    window.output.setText(str(out))
    window._output_edited()
    window.run()
    QTimer.singleShot(1500, window.runner.cancel)
    ok, cancelled = wait_finished(window)
    assert not ok and cancelled
    assert not out.exists() and "Cancelled" in window.status.text()


def test_failure_is_explained_and_existing_file_survives(window, clips, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    window.open_file(clips["main"])
    select(window, "Extract audio")
    out = tmp_path / "taken.m4a"
    out.write_bytes(b"keep me")
    window.output.setText(str(out))
    window._output_edited()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    window.run()                                   # user declines to replace
    assert not window.runner.running and out.read_bytes() == b"keep me"
