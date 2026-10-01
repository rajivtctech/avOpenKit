"""Expert options (spec F13) and editing the command before it runs (spec F2)."""

import subprocess
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QMessageBox

from avopenkit.core import probe
from avopenkit.core.job import CommandError, Job, Plan, command_line, edited_plan, guess_output
from avopenkit.core.runner import run_blocking
from avopenkit.tasks import audio, convert, gif, join, rotate, shrink, subtitles, trim
from avopenkit.tasks.base import TaskError
from avopenkit.ui.main_window import MainWindow
from test_tasks import fake, run


def value_after(args, option):
    return args[args.index(option) + 1]


# ---------------------------------------------------------------- expert settings in the tasks

def test_defaults_are_what_simple_mode_always_produced():
    a = trim.plan(trim.Settings(1, 5, True, Path("o.mp4")), fake()).jobs[0].args
    assert (value_after(a, "-crf"), value_after(a, "-preset"), value_after(a, "-b:a")) == \
        ("18", "medium", "192k")


def test_trim_exact_overrides():
    s = trim.Settings(1, 5, True, Path("o.mp4"), crf=26, preset="veryfast", audio_kbps=96)
    a = trim.plan(s, fake()).jobs[0].args
    assert (value_after(a, "-crf"), value_after(a, "-preset"), value_after(a, "-b:a")) == \
        ("26", "veryfast", "96k")


@pytest.mark.parametrize("bad", [dict(crf=52), dict(crf=-1), dict(preset="warp"),
                                 dict(audio_kbps=4), dict(audio_kbps=900)])
def test_out_of_range_expert_values_are_refused_in_plain_words(bad):
    with pytest.raises(TaskError):
        trim.plan(trim.Settings(1, 5, True, Path("o.mp4"), **bad), fake())


def test_shrink_preset_and_height():
    base = dict(target_mb=2, audio_kbps=96, output=Path("o.mp4"))
    media = fake(w=1920, h=1080)
    a = shrink.plan(shrink.Settings(**base, preset="slow", height=0), media).jobs[1].args
    assert value_after(a, "-preset") == "slow" and "-vf" not in a          # keep source size
    a = shrink.plan(shrink.Settings(**base, height=360), media).jobs[1].args
    assert value_after(a, "-vf") == "scale=-2:360"
    a = shrink.plan(shrink.Settings(**base, height=1080), media).jobs[1].args
    assert "-vf" not in a                                                    # already that size
    with pytest.raises(TaskError):
        shrink.plan(shrink.Settings(**base, height=10), media)


def test_convert_forced_reencode_and_overrides():
    s = convert.Settings("mp4", output=Path("o.mp4"), reencode=True, crf=30, preset="fast",
                         audio_kbps=96)
    a = convert.plan(s, fake()).jobs[0].args
    assert value_after(a, "-c:v") == "libx264" and value_after(a, "-crf") == "30"
    assert value_after(a, "-preset") == "fast" and value_after(a, "-b:a") == "96k"
    a = convert.plan(convert.Settings("mkv", output=Path("o.mkv"), reencode=True),
                     fake(subs=True)).jobs[0].args
    assert value_after(a, "-c:v") == "libx264" and value_after(a, "-c:s") == "copy"
    a = convert.plan(convert.Settings("webm", output=Path("o.webm"), crf=60), fake()).jobs[0].args
    assert value_after(a, "-crf") == "60"                                    # VP9 allows up to 63
    with pytest.raises(TaskError):
        convert.plan(convert.Settings("mp4", output=Path("o.mp4"), crf=60), fake("in.mkv", vcodec="vp9"))


def test_audio_bitrate_override():
    a = audio.plan(audio.Settings("mp3", Path("o.mp3"), kbps=128), fake()).jobs[0].args
    assert a[-3:] == ["-b:a", "128k", "o.mp3"] and "-q:a" not in a
    a = audio.plan(audio.Settings("wav", Path("o.wav"), kbps=128), fake()).jobs[0].args
    assert "-b:a" not in a                                                   # meaningless for WAV


def test_join_forced_reencode():
    clips = [fake("/v/a.mp4"), fake("/v/b.mp4")]
    p = join.plan(join.Settings(clips, Path("/v/o.mp4"), reencode=True, crf=24, preset="fast"))
    a = p.jobs[0].args
    assert "-filter_complex" in a and value_after(a, "-crf") == "24" and not p.write_files
    assert "as asked" in p.notes[0]


def test_rotate_bake_overrides():
    a = rotate.plan(rotate.Settings("right", True, Path("o.mp4"), crf=22, preset="slow"),
                    fake()).jobs[0].args
    assert value_after(a, "-crf") == "22" and value_after(a, "-preset") == "slow"


def test_gif_loop_and_dither():
    a = gif.plan(gif.Settings(0, 2, output=Path("o.gif"), loop=False, dither="bayer"),
                 fake()).jobs[0].args
    assert value_after(a, "-loop") == "-1"
    assert value_after(a, "-vf").endswith("[b][p]paletteuse=dither=bayer")
    with pytest.raises(TaskError):
        gif.plan(gif.Settings(0, 2, output=Path("o.gif"), dither="sparkle"), fake())


def test_subtitle_language_goes_on_the_new_track():
    s = subtitles.Settings(Path("s.srt"), False, Path("o.mkv"), language="hin")
    a = subtitles.plan(s, fake("in.mkv", subs=True)).jobs[0].args      # one track already there
    assert a[-3:] == ["-metadata:s:s:1", "language=hin", "o.mkv"]
    with pytest.raises(TaskError):
        subtitles.plan(subtitles.Settings(Path("s.srt"), False, Path("o.mkv"), language="Hindi!"),
                       fake())


def test_expert_settings_run(tools, clips, srt, info, tmp_path):
    media = info(clips["other"])
    tagged = tmp_path / "tagged.mkv"
    run(subtitles.plan(subtitles.Settings(srt, False, tagged, language="hin"), media, tools,
                       tmp_path), tools)
    sub = next(s for s in info(tagged).streams if s.kind == "subtitle")
    assert sub.language == "hin"

    once = tmp_path / "once.gif"
    run(gif.plan(gif.Settings(0, 1, 160, 8, once, loop=False, dither="bayer"), media, tools),
        tools)
    assert info(once).video.codec == "gif"

    forced = tmp_path / "forced.mp4"
    run(convert.plan(convert.Settings("mp4", output=forced, reencode=True, crf=35,
                                      preset="ultrafast", audio_kbps=64), media, tools), tools)
    assert forced.stat().st_size < clips["other"].stat().st_size


# ---------------------------------------------------------------- edited commands

def original():
    return Plan([Job(["-i", "in.mp4", "out.mp4"], [Path("out.mp4")], 12.5, "Trim",
                     cwd=Path("/work"))])


def test_edited_plan_keeps_what_it_can_from_the_original():
    p = edited_plan("ffmpeg -i in.mp4 -an 'my out.mp4'", original())
    job = p.jobs[0]
    assert job.args == ["-i", "in.mp4", "-an", "my out.mp4"] and job.edited
    assert job.duration == 12.5 and job.cwd == Path("/work")
    assert job.outputs == [Path("/work/my out.mp4")]


def test_edited_plan_with_a_different_number_of_lines_forgets_durations():
    p = edited_plan("ffmpeg -i a.mp4 b.mp4\n\nffmpeg -i b.mp4 c.mp4\n", original())
    assert [j.duration for j in p.jobs] == [None, None] and len(p.jobs) == 2


def test_overwrite_flags_are_removed_from_edited_commands():
    job = edited_plan("ffmpeg -y -i in.mp4 -n out2.mp4", original()).jobs[0]
    assert "-y" not in job.args and "-n" not in job.args


@pytest.mark.parametrize("text, code", [
    ("", "empty"), ("   \n  ", "empty"), ("ffmpeg", "empty"), ("ffmpeg -y", "empty"),
    ("ffmpeg -i 'unclosed out.mp4", "syntax"),
    ("rm -rf /tmp/x", "program"), ("ffprobe in.mp4", "program"),
    ("sh -c 'ffmpeg -i a b'", "program"),
    ("ffmpeg -i in.mp4 -c copy in.mp4", "over_input"),
    ("ffmpeg -i in.mp4 -c copy ./in.mp4", "over_input"),
])
def test_edited_plan_refuses(text, code):
    with pytest.raises(CommandError) as e:
        edited_plan(text, original())
    assert e.value.code == code


def test_shell_syntax_in_an_edited_command_is_plain_text():
    job = edited_plan("ffmpeg -i in.mp4 out.mp4 ; rm -rf $HOME `id` | tee x > y", None).jobs[0]
    assert job.args == ["-i", "in.mp4", "out.mp4", ";", "rm", "-rf", "$HOME", "`id`", "|",
                        "tee", "x", ">", "y"]


def test_path_to_ffmpeg_is_accepted_as_the_program():
    assert edited_plan("/usr/bin/ffmpeg -i a.mp4 b.mp4", None).jobs[0].args == ["-i", "a.mp4", "b.mp4"]


@pytest.mark.parametrize("args, expected", [
    (["-i", "a.mp4", "b.mp4"], Path("b.mp4")),
    (["-i", "a.mp4", "-f", "null", "-"], None),
    (["-i", "a.mp4"], None),
    (["-i", "a.mp4", "-an"], None),
])
def test_guess_output(args, expected):
    assert guess_output(args, None) == expected


def test_ffmpeg_refusing_an_unknown_output_is_a_failure_and_keeps_the_file(tools, clips, tmp_path):
    """A job whose outputs are unknown reaches FFmpeg's own -n check, which exits 0."""
    out = tmp_path / "taken.mp4"
    out.write_bytes(b"keep me")
    job = Job(["-i", str(clips["same"]), "-c", "copy", str(out)], outputs=[])
    result = run_blocking(job, tools)
    assert not result.ok and result.returncode == 0 and out.read_bytes() == b"keep me"


# ---------------------------------------------------------------- the window

@pytest.fixture
def window(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    w.open_file(clips["main"])
    yield w
    w.close()


def finished(window, timeout_ms=60000):
    loop, result = QEventLoop(), []
    window.runner.finished.connect(lambda ok, cancelled: (result.append((ok, cancelled)), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    assert result, "the job did not finish in time"
    return result[0]


def test_simple_mode_hides_and_ignores_expert_options(window):
    panel = window.panel()                                   # Trim
    assert not window.expert_box.isChecked() and window.console.isReadOnly()
    assert not panel.expert_box.isVisible()
    panel.exact.setChecked(True)
    panel.crf.setValue(30)                                   # hidden widget, simple mode
    assert "-crf 18" in window.console.toPlainText()


def test_expert_mode_shows_options_and_uses_them(window):
    panel = window.panel()
    panel.exact.setChecked(True)
    panel.crf.setValue(30)
    window.expert_box.setChecked(True)
    assert panel.expert_box.isVisible() and not window.console.isReadOnly()
    assert "-crf 30" in window.console.toPlainText()
    panel.preset.setCurrentText("fast")
    assert "-preset fast" in window.console.toPlainText()
    window.expert_box.setChecked(False)
    assert "-crf 18" in window.console.toPlainText() and window.console.isReadOnly()


def test_every_panel_has_expert_options_that_change_nothing_until_touched(window, clips, srt):
    for row in range(window.tasks.count()):
        window.tasks.setCurrentRow(row)
        panel = window.panel()
        if hasattr(panel, "add_clips") and len(panel.clips) < 2:
            panel.add_clips([probe.probe(clips["same"], window.tools)])
        if hasattr(panel, "path"):
            panel.path.setText(str(srt))
        simple = window.console.toPlainText()
        window.expert_box.setChecked(True)
        assert panel.expert_box.isVisible() and panel.expert_form.rowCount() > 0
        assert window.console.toPlainText() == simple, panel.title()
        window.expert_box.setChecked(False)


def test_mode_is_remembered(app, tools, window):
    window.expert_box.setChecked(True)
    again = MainWindow(tools)
    try:
        assert again.expert_box.isChecked() and not again.console.isReadOnly()
    finally:
        again.close()


def test_editing_the_command_takes_over_from_the_form(window):
    window.expert_box.setChecked(True)
    panel = window.panel()
    typed = window.console.toPlainText().replace("-c copy", "-c copy -an")
    window.console.setPlainText(typed)
    assert window.edited_row.isVisible() and window.plan.jobs[0].edited
    assert "-an" in window.plan.jobs[0].args and "edited by hand" in window.notes.text()
    panel.start.setValue(1.0)                                # the form is ignored now
    assert window.console.toPlainText() == typed
    window.reset_button.click()
    assert not window.edited_row.isVisible() and not window.plan.jobs[0].edited
    assert "-an" not in window.console.toPlainText() and "-ss 1.000" in window.console.toPlainText()


@pytest.mark.parametrize("text, words", [
    ("rm -rf /tmp/whatever", "must start with ffmpeg"),
    ("ffmpeg -i 'broken", "quotation mark"),
    ("", "no command"),
])
def test_unusable_edits_cannot_be_run(window, text, words):
    window.expert_box.setChecked(True)
    window.console.setPlainText(text)
    assert not window.run_button.isEnabled() and words in window.notes.text()
    assert window.plan is None
    window.run()                                             # does nothing
    assert not window.runner.running


def test_edit_that_writes_over_the_input_is_refused(window, clips):
    window.expert_box.setChecked(True)
    window.console.setPlainText(command_line(Job(["-i", str(clips["main"]), "-c", "copy",
                                                  str(clips["main"])])))
    assert not window.run_button.isEnabled() and "over an input" in window.notes.text()


def test_an_edited_command_runs_as_typed(window, tmp_path):
    window.expert_box.setChecked(True)
    panel = window.panel()
    panel.start.setValue(2.0)
    panel.end.setValue(6.0)
    out = tmp_path / "edited result.mp4"
    window.output.setText(str(out))
    window._output_edited()
    typed = window.console.toPlainText().replace("-to 6.000", "-to 4.000")
    assert typed != window.console.toPlainText()
    window.console.setPlainText(typed)
    window.run()
    ok, _ = finished(window)
    assert ok and probe.probe(out, window.tools).duration == pytest.approx(2, abs=0.2)
    assert "Done" in window.status.text()
    assert window.console.toPlainText() == typed            # still there to run again or adjust
    assert not window.console.isReadOnly()


def test_edited_command_cannot_force_an_overwrite(window, tmp_path, monkeypatch):
    window.expert_box.setChecked(True)
    out = tmp_path / "precious.mp4"
    out.write_bytes(b"keep me")
    window.output.setText(str(out))
    window._output_edited()
    window.console.setPlainText(window.console.toPlainText().replace("ffmpeg ", "ffmpeg -y ", 1))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: (asked.append(1), QMessageBox.StandardButton.No)[1])
    window.run()
    assert asked and not window.runner.running and out.read_bytes() == b"keep me"


def test_changing_task_or_leaving_expert_mode_drops_the_edit(window):
    window.expert_box.setChecked(True)
    window.console.setPlainText(window.console.toPlainText() + " -extra")
    assert window._edited
    window.tasks.setCurrentRow(3)
    assert not window._edited and "-extra" not in window.console.toPlainText()
    window.console.setPlainText(window.console.toPlainText() + " -extra")
    window.expert_box.setChecked(False)
    assert not window._edited and "-extra" not in window.console.toPlainText()
    assert not window.edited_row.isVisible()
