"""Hardware encoding (spec F14): offered only when a test encode works; off by default."""

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from avopenkit.core import ffmpeg, hardware
from avopenkit.core.explain import explain_command
from avopenkit.core.hardware import HwEncoder
from avopenkit.tasks import convert, join, rotate, shrink, subtitles, trim
from avopenkit.ui.dialogs import SettingsDialog
from avopenkit.ui.main_window import MainWindow
from test_tasks import fake, marker, marker_corner, run  # noqa: F401  (marker is a fixture)

VAAPI = HwEncoder("vaapi", "h264_vaapi", "VAAPI test", "/dev/dri/renderD128")
QSV = HwEncoder("qsv", "h264_qsv", "QSV test")
NVENC = HwEncoder("nvenc", "h264_nvenc", "NVENC test")
AMF = HwEncoder("amf", "h264_amf", "AMF test")


def after(args, option):
    return args[args.index(option) + 1]


# ---------------------------------------------------------------- arguments

def test_arguments_for_each_kind_of_encoder():
    assert VAAPI.global_args() == ["-vaapi_device", "/dev/dri/renderD128"]
    assert VAAPI.filter_tail() == "format=nv12,hwupload"
    assert VAAPI.codec_args(21) == ["-c:v", "h264_vaapi", "-qp", "21"]
    assert QSV.global_args() == [] and QSV.codec_args(21) == ["-c:v", "h264_qsv", "-global_quality", "21"]
    assert NVENC.codec_args(21) == ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    assert AMF.codec_args(21) == ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", "21", "-qp_p", "21"]


def test_the_test_encode_uses_the_same_arguments_as_a_real_job():
    args = hardware.test_args(VAAPI)
    assert args[3:5] == VAAPI.global_args()
    assert after(args, "-vf").endswith(VAAPI.filter_tail())
    assert after(args, "-c:v") == "h264_vaapi" and args[-3:] == ["-f", "null", "-"]


def test_candidates_come_from_what_ffmpeg_was_built_with(tools):
    def with_encoders(*names):
        return ffmpeg.Tools("f", "p", "8", (8,), "", frozenset(names), frozenset())
    assert hardware.candidates(with_encoders("libx264")) == []
    ids = [h.id for h in hardware.candidates(with_encoders("h264_qsv", "h264_nvenc", "h264_amf"))]
    assert ids == ["qsv", "nvenc", "amf"]
    vaapi = [h for h in hardware.candidates(with_encoders("h264_vaapi")) if h.id == "vaapi"]
    assert all(h.device.startswith("/dev/dri/renderD") for h in vaapi)
    if not sys.platform.startswith("linux"):
        assert vaapi == []


# ---------------------------------------------------------------- the tasks

def test_software_encoding_is_unchanged_when_hardware_is_off():
    a = trim.plan(trim.Settings(1, 5, True, Path("o.mp4")), fake()).jobs[0].args
    assert a[0] == "-ss" and "-vf" not in a and after(a, "-c:v") == "libx264"


def test_exact_trim_with_hardware():
    p = trim.plan(trim.Settings(1, 5, True, Path("o.mp4"), crf=24, hw=VAAPI), fake())
    a = p.jobs[0].args
    assert a[:2] == ["-vaapi_device", "/dev/dri/renderD128"] and a[2] == "-ss"
    assert after(a, "-vf") == "format=nv12,hwupload"
    assert after(a, "-c:v") == "h264_vaapi" and after(a, "-qp") == "24"
    assert "libx264" not in a and "-preset" not in a
    assert any("graphics chip (VAAPI test)" in n for n in p.notes)


def test_fast_trim_and_other_copies_ignore_hardware():
    a = trim.plan(trim.Settings(1, 5, False, Path("o.mp4"), hw=VAAPI), fake()).jobs[0].args
    assert "-vaapi_device" not in a and "copy" in a
    a = rotate.plan(rotate.Settings("right", False, Path("o.mp4"), hw=VAAPI), fake()).jobs[0].args
    assert a[0] == "-display_rotation"
    a = convert.plan(convert.Settings("mov", output=Path("o.mov"), hw=QSV), fake()).jobs[0].args
    assert after(a, "-c:v") == "copy"


def test_convert_with_hardware_only_for_h264():
    media = fake("in.mkv", vcodec="vp9", acodec="opus")
    p = convert.plan(convert.Settings("mp4", output=Path("o.mp4"), hw=QSV), media)
    a = p.jobs[0].args
    assert after(a, "-c:v") == "h264_qsv" and after(a, "-vf") == "format=nv12"
    assert after(a, "-c:a") == "aac" and any("graphics chip" in n for n in p.notes)
    p = convert.plan(convert.Settings("webm", output=Path("o.webm"), hw=QSV), fake())
    assert after(p.jobs[0].args, "-c:v") == "libvpx-vp9"            # no hardware VP9 here
    assert not any("graphics chip" in n for n in p.notes)


def test_filters_run_before_the_frames_go_to_the_chip():
    a = rotate.plan(rotate.Settings("right", True, Path("o.mp4"), hw=VAAPI), fake()).jobs[0].args
    assert after(a, "-vf") == "transpose=1,format=nv12,hwupload"
    a = subtitles.plan(subtitles.Settings(Path("s.srt"), True, Path("/x/o.mp4"), hw=NVENC),
                       fake("/x/in.mp4"), workdir=Path("/w")).jobs[0].args
    assert after(a, "-vf") == "subtitles=subs.srt,format=yuv420p" and after(a, "-cq") == "20"


def test_join_hands_the_joined_frames_to_the_chip():
    clips = [fake("/v/a.mp4"), fake("/v/b.mp4", w=640, h=480)]
    a = join.plan(join.Settings(clips, Path("/v/o.mp4"), hw=VAAPI)).jobs[0].args
    graph = after(a, "-filter_complex")
    assert a[0] == "-vaapi_device" and "concat=n=2:v=1:a=1[vj][a]" in graph
    assert graph.endswith("[vj]format=nv12,hwupload[v]") and after(a, "-c:v") == "h264_vaapi"


def test_shrink_always_uses_the_standard_encoder():
    assert not hasattr(shrink.Settings(), "hw")


@pytest.mark.parametrize("hw", [VAAPI, QSV, NVENC, AMF])
def test_every_part_of_a_hardware_command_is_explained(hw):
    plans = [
        trim.plan(trim.Settings(1, 5, True, Path("o.mp4"), hw=hw), fake()),
        rotate.plan(rotate.Settings("left", True, Path("o.mp4"), hw=hw), fake()),
        join.plan(join.Settings([fake("/v/a.mp4"), fake("/v/b.mp4", w=640)], Path("/v/o.mp4"),
                                hw=hw)),
    ]
    from avopenkit.core.job import command_line
    for plan in plans:
        text = command_line(plan.jobs[0])
        unknown = [text[p.start:p.end] for p in explain_command(text) if not p.known]
        assert not unknown and "no explanation" not in " ".join(
            p.text for p in explain_command(text))


# ---------------------------------------------------------------- detection on this machine

@pytest.fixture(scope="session")
def working(tools):
    return hardware.detect(tools)


def test_an_encoder_that_cannot_work_is_not_offered(tools):
    assert not hardware.works(tools, HwEncoder("vaapi", "h264_vaapi", "x", "/dev/null/nothing"))
    assert not hardware.works(tools, HwEncoder("amf", "h264_no_such_encoder", "x"))
    assert hardware.find(tools, "no-such-kind") is None


def test_listed_is_not_the_same_as_working(tools, working):
    """FFmpeg lists encoders this machine may have no chip or driver for; each offered one
    must have passed its test, and each one left out must fail it."""
    assert len({h.id for h in working}) == len(working)            # one per kind
    for hw in working:
        assert hardware.works(tools, hw)
    for hw in hardware.candidates(tools):
        if hw.id not in {h.id for h in working}:
            assert not hardware.works(tools, hw)


def test_real_jobs_run_on_the_hardware_encoder(tools, working, clips, srt, info, tmp_path,
                                              marker):  # noqa: F811
    if not working:
        pytest.skip("no working hardware encoder on this machine")
    hw = working[0]
    media = info(clips["main"])

    out = tmp_path / "trim.mp4"
    run(trim.plan(trim.Settings(3.5, 7, True, out, hw=hw), media, tools), tools)
    assert info(out).video.codec == "h264" and info(out).duration == pytest.approx(3.5, abs=0.15)

    out = tmp_path / "burn.mp4"
    run(subtitles.plan(subtitles.Settings(srt, True, out, hw=hw), media, tools, tmp_path), tools)
    assert info(out).video.codec == "h264" and info(out).duration == pytest.approx(8, abs=0.2)

    out = tmp_path / "joined.mp4"
    run(join.plan(join.Settings([media, info(clips["other"])], out, hw=hw), None, tools,
                  tmp_path), tools)
    got = info(out)
    assert got.duration == pytest.approx(11, abs=0.2) and got.audio is not None
    assert (got.video.width, got.video.height) == (640, 360)

    webm = tmp_path / "src.webm"
    run(convert.plan(convert.Settings("webm", "small", webm), info(clips["other"]), tools), tools)
    out = tmp_path / "back.mp4"
    run(convert.plan(convert.Settings("mp4", output=out, hw=hw), info(webm), tools), tools)
    assert (info(out).video.codec, info(out).audio.codec) == ("h264", "aac")

    out = tmp_path / "turned.mp4"
    run(rotate.plan(rotate.Settings("right", True, out, hw=hw), info(marker), tools), tools)
    assert marker_corner(tools, out) == ("top-right", (240, 320))


# ---------------------------------------------------------------- Settings and the window

def test_settings_offer_nothing_when_no_hardware_encoder_works(app, tools):
    d = SettingsDialog(QSettings(), tools)
    assert not d.hardware.isEnabled() and d.hardware.count() == 1
    d.accept()
    assert not d.hardware_changed and QSettings().value("hardware", "", type=str) == ""


def test_settings_offer_the_working_encoders_and_default_to_off(app, tools):
    settings = QSettings()
    d = SettingsDialog(settings, tools, hardware=[VAAPI, QSV])
    assert d.hardware.isEnabled() and d.hardware.currentData() == ""             # off by default
    assert [d.hardware.itemData(i) for i in range(d.hardware.count())] == ["", "vaapi", "qsv"]
    d.hardware.setCurrentIndex(d.hardware.findData("qsv"))
    d.accept()
    assert d.hardware_changed and settings.value("hardware", "", type=str) == "qsv"
    again = SettingsDialog(settings, tools, hardware=[VAAPI, QSV])
    assert again.hardware.currentData() == "qsv"
    again.accept()
    assert not again.hardware_changed


def test_window_uses_software_by_default(app, tools, clips):
    w = MainWindow(tools)
    try:
        assert w.hw is None
        w.open_file(clips["main"])
        w.panel().exact.setChecked(True)
        assert "libx264" in w.console.toPlainText()
    finally:
        w.close()


def test_a_saved_encoder_that_no_longer_works_falls_back_and_says_so(app, tools, clips):
    QSettings().setValue("hardware", "no-such-kind")
    w = MainWindow(tools)
    try:
        assert w.hw is None and "not working now" in w.status.text()
        w.open_file(clips["main"])
        w.panel().exact.setChecked(True)
        assert "libx264" in w.console.toPlainText()
    finally:
        w.close()


def test_choosing_a_working_encoder_changes_the_commands(app, tools, working, clips):
    if not working:
        pytest.skip("no working hardware encoder on this machine")
    hw = working[0]
    w = MainWindow(tools)
    try:
        assert w.hardware_found() == working
        w.open_file(clips["main"])
        w.panel().exact.setChecked(True)
        d = SettingsDialog(w.settings, w.tools, parent=w, hardware=w.hardware_found())
        d.hardware.setCurrentIndex(d.hardware.findData(hw.id))
        d.accept()
        w.apply_settings(d)
        assert w.hw == hw and hw.label in w.status.text()
        assert hw.encoder in w.console.toPlainText() and "libx264" not in w.console.toPlainText()
        assert "graphics chip" in w.notes.text()
        w.tasks.setCurrentRow(1)                                    # Shrink keeps libx264
        assert "libx264" in w.console.toPlainText()

        d = SettingsDialog(w.settings, w.tools, parent=w, hardware=w.hardware_found())
        d.hardware.setCurrentIndex(0)
        d.accept()
        w.apply_settings(d)
        assert w.hw is None and "is off" in w.status.text()
        w.tasks.setCurrentRow(0)
        assert "libx264" in w.console.toPlainText()
    finally:
        w.close()
    QSettings().setValue("hardware", hw.id)                         # remembered at next start
    again = MainWindow(tools)
    try:
        assert again.hw == hw
    finally:
        again.close()
