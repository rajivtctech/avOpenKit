"""Explanations of the command's parts and of the form's options (spec F12)."""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QListWidget,
                             QRadioButton, QSpinBox)

from avopenkit.core import probe
from avopenkit.core.explain import (explain_command, explain_filters, explain_map,
                                    explanation_at, plumbing_explanation, token_spans)
from avopenkit.core.job import Job, command_line
from avopenkit.ui.main_window import MainWindow


def said(command, word, posix=True):
    """The explanation shown for the first occurrence of `word` in the command."""
    return explanation_at(command, command.index(word), posix)


# ---------------------------------------------------------------- splitting into words

def test_token_spans_follow_the_quoting_of_the_command_box():
    line = "ffmpeg -i 'my clip.mp4' -vf \"a,b\" plain it\\'s"
    assert [(line[s:e], v) for s, e, v in token_spans(line, posix=True)] == [
        ("ffmpeg", "ffmpeg"), ("-i", "-i"), ("'my clip.mp4'", "my clip.mp4"), ("-vf", "-vf"),
        ('"a,b"', "a,b"), ("plain", "plain"), ("it\\'s", "it's")]


def test_token_spans_match_what_is_actually_run():
    """Whatever the command box shows for a job, the words found are the job's arguments."""
    args = ["-i", "it's a \"clip\".mp4", "-vf", "split[a][b];[a]palettegen[p]", "$HOME `x`.gif"]
    text = command_line(Job(args))
    assert [v for _, _, v in token_spans(text)][1:] == args


def test_windows_style_quoting():
    line = 'ffmpeg -i "C:\\My Videos\\clip one.mp4" out.mp4'
    assert [v for _, _, v in token_spans(line, posix=False)] == [
        "ffmpeg", "-i", "C:\\My Videos\\clip one.mp4", "out.mp4"]


# ---------------------------------------------------------------- what is said

def test_option_and_value_share_one_explanation():
    cmd = "ffmpeg -i in.mp4 -crf 23 out.mp4"
    assert said(cmd, "-crf") == said(cmd, "23") and "23" in said(cmd, "-crf")
    assert "Input file number 1: in.mp4" == said(cmd, "-i") == said(cmd, "in.mp4")
    assert "result file" in said(cmd, "out.mp4") and "FFmpeg program" in said(cmd, "ffmpeg")


def test_seek_is_explained_by_where_it_is_written():
    assert "jumps there" in said("ffmpeg -ss 5 -i a.mp4 o.mp4", "-ss")
    assert "slow but exact" in said("ffmpeg -i a.mp4 -ss 5 o.mp4", "-ss")
    two = "ffmpeg -i a.mp4 -ss 5 -i b.mp4 o.mp4"                  # belongs to the second input
    assert "jumps there" in said(two, "-ss") and "number 2" in said(two, "b.mp4")


@pytest.mark.parametrize("spec, words", [
    ("0", "every stream of input 1"),
    ("0:v:0", "video stream number 1 of input 1"),
    ("0:a", "all audio streams of input 1"),
    ("1:0", "stream number 1 of input 2"),
    ("0:s?", "carry on without complaint"),
    ("[v]", "labelled [v]"),
])
def test_map(spec, words):
    assert words in explain_map(spec)


def test_codecs():
    assert "Copy every stream" in said("ffmpeg -i a -c copy b", "-c")
    assert "Copy the audio" in said("ffmpeg -i a -c:a copy b", "-c:a")
    v = said("ffmpeg -i a -c:v libx264 b", "libx264")
    assert "the video" in v and "H.264" in v and "libx264" in v
    assert "MP4 text subtitles" in said("ffmpeg -i a -c:s mov_text b", "-c:s")


def test_filter_chain_is_explained_step_by_step():
    text = explain_filters("fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];"
                           "[b][p]paletteuse=dither=bayer", "Video filters:")
    lines = text.splitlines()
    assert lines[0] == "Video filters:" and len(lines) == 6
    assert "12 frames per second" in lines[1] and "480×-1" in lines[2]
    assert "256 colours" in lines[4] and "dither=bayer" in lines[5]
    assert "no explanation" in explain_filters("frobnicate=3", "x")
    assert "90° to the right" in explain_filters("transpose=1", "x")


def test_rotation_and_loop_values():
    assert "-90°" in said("ffmpeg -display_rotation -90 -i a b", "-display_rotation")
    assert said("ffmpeg -i a -loop 0 b.gif", "-loop") == "Repeat the GIF for ever."
    assert said("ffmpeg -i a -loop -1 b.gif", "-1") == "Play the GIF once and stop."


def test_null_output_and_two_lines():
    two = "ffmpeg -i a.mp4 -pass 1 -an -f null -\nffmpeg -i a.mp4 -pass 2 out.mp4"
    assert "discarded" in explanation_at(two, two.index(" -\n") + 1, True)
    assert "Write no file" in said(two, "null")
    second = two.index("\n") + 1
    assert "FFmpeg program" in explanation_at(two, second, True)
    assert "Pass 2" in explanation_at(two, two.index("-pass 2"), True)
    assert explanation_at(two, two.index("\n"), True) is None      # between the lines
    assert explanation_at("ffmpeg  -an", 6, True) is None          # the gap between words


def test_unknown_things_in_an_edited_command_are_said_to_be_unknown():
    cmd = "ffmpeg -i a.mp4 -zzz 7 -an out.mp4"
    parts = {cmd[p.start:p.end]: p for p in explain_command(cmd, True)}
    assert not parts["-zzz"].known and not parts["7"].known and "no explanation" in parts["-zzz"].text
    assert parts["-an"].known and parts["out.mp4"].known
    other = explain_command("rm -rf x", True)
    assert not other[0].known and "only runs FFmpeg" in other[0].text
    assert "ignores this" in said("ffmpeg -y -i a b", "-y")


def test_plumbing_is_explained():
    text = plumbing_explanation()
    for flag in ("-hide_banner", "-nostdin", "-progress", "-nostats", "-n"):
        assert flag + ":" in text


# ---------------------------------------------------------------- the window

@pytest.fixture
def window(app, tools, clips):
    w = MainWindow(tools)
    w.resize(1100, 900)
    w.show()
    w.open_file(clips["main"])
    yield w
    w.close()


def visit_every_task(window, clips, srt):
    for row in range(window.tasks.count()):
        window.tasks.setCurrentRow(row)
        panel = window.panel()
        if hasattr(panel, "add_clips") and len(panel.clips) < 2:
            panel.add_clips([probe.probe(clips["same"], window.tools)])
        if hasattr(panel, "path"):
            panel.path.setText(str(srt))
        yield panel


def variants(panel):
    """Flip each two-way choice, so both forms of the task's command are seen."""
    yield "default"
    for name in ("exact", "bake", "burn"):
        if hasattr(panel, name):
            getattr(panel, name).setChecked(True)
            yield name
    for combo in ("target", "format", "action"):
        if hasattr(panel, combo):
            box = getattr(panel, combo)
            for i in range(box.count()):
                box.setCurrentIndex(i)
                yield f"{combo}={box.itemData(i)}"


def test_every_part_of_every_generated_command_has_an_explanation(window, clips, srt):
    """Nothing the tasks produce may fall through to 'no explanation'."""
    seen = 0
    for expert in (False, True):
        window.expert_box.setChecked(expert)
        for panel in visit_every_task(window, clips, srt):
            for variant in variants(panel):
                text = window.console.toPlainText()
                assert text, (panel.title(), variant, window.notes.text())
                parts = explain_command(text)
                words = sum(len(token_spans(line)) for line in text.split("\n"))
                assert len(parts) == words                         # every word is covered
                unknown = [text[p.start:p.end] for p in parts if not p.known]
                assert not unknown, (panel.title(), variant, unknown)
                assert not any("no explanation" in p.text for p in parts), (panel.title(), variant)
                seen += 1
    assert seen > 40


def point_of(console, needle):
    cursor = console.textCursor()
    cursor.setPosition(console.toPlainText().index(needle) + 1)
    rect = console.cursorRect(cursor)
    return QPoint(rect.left() + 2, rect.center().y())


def test_hovering_the_command_box_explains_the_word_under_the_mouse(window):
    console = window.console
    assert "Input file number 1" in console.explanation_for(point_of(console, "-i "))
    assert "without re-encoding" in console.explanation_for(point_of(console, "copy"))
    assert "FFmpeg program" in console.explanation_for(QPoint(3, point_of(console, "ffmpeg").y()))
    below = QPoint(10, console.viewport().height() - 2)
    assert console.explanation_for(below) is None                  # empty space below the text
    cursor = console.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    end = console.cursorRect(cursor)
    assert console.explanation_for(QPoint(end.right() + 60, end.center().y())) is None


def test_hover_also_explains_a_hand_edited_command(window):
    window.expert_box.setChecked(True)
    window.console.setPlainText(window.console.toPlainText().replace("-c copy", "-c copy -an"))
    assert window.console.explanation_for(point_of(window.console, "-an")) == "Leave out the sound."


def test_every_option_in_every_form_has_a_short_explanation(window, clips, srt):
    window.expert_box.setChecked(True)
    kinds = (QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QRadioButton, QLineEdit, QListWidget)
    checked = 0
    for panel in visit_every_task(window, clips, srt):
        for widget in panel.findChildren(QSpinBox) + panel.findChildren(QDoubleSpinBox) + \
                panel.findChildren(QComboBox) + panel.findChildren(QCheckBox) + \
                panel.findChildren(QRadioButton) + panel.findChildren(QLineEdit) + \
                panel.findChildren(QListWidget):
            if isinstance(widget.parent(), kinds):
                continue                                            # the text field inside a spin box
            assert widget.toolTip().strip(), (panel.title(), type(widget).__name__,
                                              getattr(widget, "text", lambda: "")())
            checked += 1
    assert checked > 35
    assert window.expert_box.toolTip() and window.plumbing.toolTip()
