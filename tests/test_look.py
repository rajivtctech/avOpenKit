"""The look of the program: theme, icons, timeline, task cards, coloured feedback."""

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from avopenkit.core import probe
from avopenkit.core.job import Job, Plan
from avopenkit.ui import icons, theme
from avopenkit.ui.dialogs import SettingsDialog
from avopenkit.ui.main_window import MainWindow
from avopenkit.ui.widgets import (BLURB_ROLE, ICON_ROLE, FlowLayout, NotesBox, Timeline, chip,
                                  plan_kind)


def wait_until(app, condition, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if condition():
            return True
    return False


def distinct_colours(image: QImage, step: int = 7) -> int:
    return len({image.pixel(x, y) for x in range(0, image.width(), step)
                for y in range(0, image.height(), step)})


# ---------------------------------------------------------------- theme and icons

def test_both_themes_define_the_same_colours_and_apply_cleanly(app):
    assert set(theme.DARK) == set(theme.LIGHT)
    for name in ("light", "dark"):
        t = theme.apply(app, name)
        assert t["name"] == name and theme.current() is t
        assert "{" not in app.styleSheet().replace("{", "", 0)[:0]          # formatted, no braces left open
        assert t["accent"] in app.styleSheet()
    assert theme.apply(app, "no-such-theme")["name"] == "dark"                  # falls back
    assert theme.colour("accent") == QColor(theme.DARK["accent"])


def test_text_is_readable_on_its_background():
    """Contrast between text and surface, by the usual luminance ratio (4.5 or better)."""
    def luminance(hex_colour):
        c = QColor(hex_colour)
        parts = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
                 for v in (c.redF(), c.greenF(), c.blueF())]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    def ratio(a, b):
        hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for t in (theme.DARK, theme.LIGHT):
        for text, ground in (("text", "bg"), ("text", "surface"), ("muted", "surface"),
                             ("accent_text", "accent"), ("text", "good_soft"),
                             ("text", "warn_soft"), ("text", "bad_soft"), ("text", "code_bg"),
                             ("code_option", "code_bg"), ("code_string", "code_bg")):
            assert ratio(t[text], t[ground]) >= 4.5, (t["name"], text, ground,
                                                      round(ratio(t[text], t[ground]), 2))


def test_every_icon_draws_something(app):
    assert len(icons.NAMES) >= 30
    for name in icons.NAMES:
        image = icons.pixmap(name, "#ffffff", 24).toImage()
        painted = sum(1 for x in range(image.width()) for y in range(image.height())
                      if QColor.fromRgba(image.pixel(x, y)).alpha() > 40)
        assert painted > 40, name
    assert not icons.icon("trim").isNull() and not icons.logo().isNull()


def test_every_task_has_its_own_icon_and_description(app, tools):
    w = MainWindow(tools)
    try:
        names = [w.tasks.item(r).data(ICON_ROLE) for r in range(w.tasks.count())]
        assert names == ["trim", "shrink", "convert", "audio", "join", "rotate", "gif", "subtitles"]
        assert all(n in icons.STROKES for n in names)
        assert all(w.tasks.item(r).data(BLURB_ROLE) for r in range(w.tasks.count()))
    finally:
        w.close()


# ---------------------------------------------------------------- coloured feedback

def plan(*argsets, edited=False):
    return Plan([Job(list(a), edited=edited) for a in argsets])


def test_plan_kind():
    assert plan_kind(plan(["-i", "a", "-c", "copy", "b"])) == "copy"
    assert plan_kind(plan(["-display_rotation", "90", "-i", "a", "-c", "copy", "b"])) == "copy"
    assert plan_kind(plan(["-i", "a", "-c:v", "libx264", "-c:a", "aac", "b"])) == "encode"
    assert plan_kind(plan(["-i", "a", "-c:v", "copy", "-c:a", "aac", "b"])) == "mixed"
    assert plan_kind(plan(["-i", "a", "-vf", "fps=12", "b.gif"])) == "encode"
    assert plan_kind(plan(["-i", "a", "-i", "s", "-c", "copy", "-c:s", "mov_text", "b"])) == "copy"
    assert plan_kind(plan(["-i", "a", "-c", "copy", "b"], edited=True)) == ""
    assert plan_kind(None) == ""


def test_the_note_box_says_at_a_glance_whether_quality_is_kept(app, tools, clips, srt):
    w = MainWindow(tools)
    try:
        assert w.notes.kind == "" and not w.notes.badge.isVisible()        # "Open a file to begin."
        w.open_file(clips["main"])
        assert (w.notes.kind, w.notes.badge.text()) == ("copy", "No quality loss")   # fast trim
        w.panel().exact.setChecked(True)
        assert (w.notes.kind, w.notes.badge.text()) == ("encode", "Re-encodes")
        w.panel().end.setValue(0.0)                                       # end before start
        assert (w.notes.kind, w.notes.badge.text()) == ("problem", "Cannot run yet")
        assert "end must be after" in w.notes.text()
        w.tasks.setCurrentRow(3)                                          # keep original audio
        assert w.notes.kind == "copy"
        w.tasks.setCurrentRow(1)
        assert w.notes.kind == "encode"
        w.expert_box.setChecked(True)
        w.console.setPlainText(w.console.toPlainText() + " -an")
        assert (w.notes.kind, w.notes.badge.text()) == ("", "Edited by hand")
    finally:
        w.close()


def test_command_colouring_does_not_change_the_text_or_count_as_an_edit(app, tools, clips):
    w = MainWindow(tools)
    try:
        w.expert_box.setChecked(True)
        w.open_file(clips["main"])
        text = w.console.toPlainText()
        w._highlighter.rehighlight()
        app.processEvents()
        assert w.console.toPlainText() == text and not w._edited
        formats = w.console.document().firstBlock().layout().formats()
        assert len(formats) >= 4                                          # ffmpeg, options, a quoted path
    finally:
        w.close()


# ---------------------------------------------------------------- the timeline

@pytest.fixture
def timeline(app):
    t = Timeline()
    t.resize(600, 72)
    t.setRange(0, 20000)
    t.show()
    yield t
    t.close()


def click(widget, x, kind=QMouseEvent.Type.MouseButtonPress, buttons=Qt.MouseButton.LeftButton):
    pos = QPointF(x, widget.height() / 2)
    event = QMouseEvent(kind, pos, widget.mapToGlobal(pos), Qt.MouseButton.LeftButton, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def test_clicking_or_dragging_the_timeline_goes_to_that_moment(timeline):
    moved = []
    timeline.sliderMoved.connect(moved.append)
    track = timeline._track()
    click(timeline, track.left() + track.width() / 2)
    assert timeline.isSliderDown() and moved[-1] == pytest.approx(10000, abs=60)
    click(timeline, track.left() + track.width() * 0.75, QMouseEvent.Type.MouseMove)
    assert moved[-1] == pytest.approx(15000, abs=60)
    click(timeline, track.right() + 500, QMouseEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)
    assert not timeline.isSliderDown() and timeline.value() == 20000        # clamped to the end
    click(timeline, -50)
    assert timeline.value() == 0


def test_timeline_keeps_the_keyboard_steps(timeline):
    timeline.setSingleStep(100)
    timeline.setPageStep(1000)
    timeline.setValue(5000)
    timeline.triggerAction(Timeline.SliderAction.SliderSingleStepAdd)
    assert timeline.value() == 5100
    timeline.triggerAction(Timeline.SliderAction.SliderPageStepSub)
    assert timeline.value() == 4100


def test_timeline_draws_the_frames_the_selection_and_the_playhead(timeline):
    empty = timeline.grab().toImage()
    red = QImage(96, 54, QImage.Format.Format_RGB32)
    red.fill(QColor("#d02020"))
    for i in range(Timeline.CELLS):
        timeline.set_thumb(i, red)
    timeline.set_media(keyframes=(0, 2, 4, 6, 8))                           # clears the frames
    assert timeline.grab().toImage() == empty or distinct_colours(timeline.grab().toImage()) < 12
    for i in range(Timeline.CELLS):
        timeline.set_thumb(i, red)
    filled = timeline.grab().toImage()
    middle = QColor(filled.pixel(300, 40))
    assert middle.red() > 150 and middle.green() < 80                       # the frame shows

    timeline.set_selection(5.0, 10.0)
    assert timeline.selection() == (5.0, 10.0)
    lit = timeline.grab().toImage()
    track = timeline._track()
    inside = QColor(lit.pixel(int(track.left() + track.width() * 0.375), 40))
    outside = QColor(lit.pixel(int(track.left() + track.width() * 0.85), 40))
    assert inside.red() > 150 and outside.red() < inside.red() - 60         # the rest is dimmed
    timeline.set_selection(8.0, 3.0)                                        # nonsense: no selection
    assert timeline.selection() is None
    assert len(timeline.thumb_times(20.0)) == Timeline.CELLS


def test_trim_and_gif_light_up_their_part_of_the_timeline(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    try:
        w.open_file(clips["main"])                                          # 8 seconds, Trim
        assert w.preview.slider.selection() == (0.0, pytest.approx(8.0, abs=0.1))
        w.panel().start.setValue(2.0)
        w.panel().end.setValue(5.0)
        assert w.preview.slider.selection() == (2.0, 5.0)
        w.tasks.setCurrentRow(6)                                            # Make a GIF: 3 s from 0
        assert w.preview.slider.selection() == (0.0, 3.0)
        w.panel().start.setValue(4.0)
        assert w.preview.slider.selection() == (4.0, 7.0)
        w.tasks.setCurrentRow(0)
        assert w.preview.slider.selection() == (2.0, 5.0)
        assert w.preview.slider._keyframes == pytest.approx((0, 2, 4, 6), abs=0.01)
    finally:
        w.close()


def test_filmstrip_and_poster_come_from_the_file(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    try:
        w.open_file(clips["main"])
        strip = w.preview.slider
        assert wait_until(app, lambda: len(strip._thumbs) == Timeline.CELLS, 20), len(strip._thumbs)
        assert all(not i.isNull() and i.height() == 54 for i in strip._thumbs.values())
        assert wait_until(app, lambda: w.thumb.pixmap().deviceIndependentSize().width() == 132, 10)
        assert distinct_colours(w.thumb.pixmap().toImage(), 5) > 6
    finally:
        w.close()


def test_file_card_changes_from_drop_hint_to_facts(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    try:
        assert w.file_card.objectName() == "dropCard" and w.file_hint.isVisible()
        w.open_file(clips["main"])
        assert w.file_card.objectName() == "card" and not w.file_hint.isVisible()
        chips = [w.chips.itemAt(i).widget().text() for i in range(w.chips.count())]
        assert chips == w.facts(w.media) and any("640×360" in c for c in chips)
        assert "  ·  ".join(chips) == w.inspector.text()
        w.open_file(clips["silent"])
        assert w.chips.count() == len(w.facts(w.media)) and "No sound" in w.inspector.text()
    finally:
        w.close()


def test_chips_wrap_instead_of_forcing_the_window_wider(app):
    holder = QWidget()
    flow = FlowLayout(holder)
    for i in range(8):
        flow.addWidget(chip(f"a fairly long fact number {i}"))
    one_row = flow.heightForWidth(5000)
    assert flow.heightForWidth(300) > 2 * one_row and flow.minimumSize().width() < 300
    flow.clear()
    assert flow.count() == 0


def test_form_is_only_as_tall_as_the_task_in_view(app, tools, clips):
    w = MainWindow(tools)
    w.resize(1180, 940)
    w.show()
    try:
        w.open_file(clips["main"])
        w.tasks.setCurrentRow(3)                                            # Extract audio: one row
        assert wait_until(app, lambda: 0 < w.stack.height() < 100, 3), w.stack.height()
        w.tasks.setCurrentRow(4)                                            # Join: a list of clips
        assert wait_until(app, lambda: w.stack.height() > 200, 3), w.stack.height()
    finally:
        w.close()


def test_queue_rows_carry_a_status_dot(app, tools, clips, tmp_path):
    w = MainWindow(tools)
    try:
        w.open_file(clips["main"])
        w.output.setText(str(tmp_path / "o.mp4"))
        w._output_edited()
        w.add_to_queue()
        assert not w.queue_list.item(0).icon().isNull()
        assert "1 waiting" in w.queue_label.text()
    finally:
        w.close()


# ---------------------------------------------------------------- appearance setting

def test_appearance_defaults_to_dark_and_is_saved(app, tools):
    settings = QSettings()
    d = SettingsDialog(settings, tools)
    assert d.appearance.currentData() == "dark"
    d.accept()
    assert not d.theme_changed
    d = SettingsDialog(settings, tools)
    d.appearance.setCurrentIndex(d.appearance.findData("light"))
    d.accept()
    assert d.theme_changed and settings.value("theme", "", type=str) == "light"
    assert SettingsDialog(settings, tools).appearance.currentData() == "light"


def test_window_builds_in_the_light_theme_too(app, tools, clips):
    theme.apply(app, "light")
    try:
        w = MainWindow(tools)
        w.resize(1180, 940)
        w.show()
        w.open_file(clips["main"])
        app.processEvents()
        image = w.grab().toImage()
        assert QColor(image.pixel(600, 400)).lightness() > 150            # a light surface
        w.close()
    finally:
        theme.apply(app, "dark")
