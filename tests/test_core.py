import sys
from pathlib import Path

import pytest

from avopenkit.core import ffmpeg, probe
from avopenkit.core.job import Job, command_line, full_args, parse_command_line
from avopenkit.core.runner import ProgressParser, fraction


@pytest.mark.parametrize("banner, text, version", [
    ("ffmpeg version 8.0.1-3ubuntu2 Copyright (c) 2000-2025", "8.0.1-3ubuntu2", (8, 0, 1)),
    ("ffmpeg version 9.0.2-essentials_build-www.gyan.dev Copyright", "9.0.2-essentials_build-www.gyan.dev", (9, 0, 2)),
    ("ffmpeg version n7.1.5 Copyright", "n7.1.5", (7, 1, 5)),
    ("ffmpeg version N-118193-g5f38c82536 Copyright", "N-118193-g5f38c82536", None),
    ("ffprobe version 6.0 Copyright", "6.0", (6, 0)),
    ("nonsense", "", None),
])
def test_parse_version(banner, text, version):
    assert ffmpeg.parse_version(banner) == (text, version)


def test_too_old():
    def t(v):
        return ffmpeg.Tools("f", "p", "", v, "", frozenset(), frozenset())
    assert t((5, 1, 4)).too_old
    assert not t((6, 0)).too_old
    assert not t(None).too_old          # unnumbered snapshot builds are assumed recent


def test_parse_encoders_and_filters():
    enc = ffmpeg.parse_encoders(
        "Encoders:\n V..... = Video\n ------\n V....D libx264              H.264\n"
        " A....D aac                  AAC\n S..... mov_text             3GPP\n")
    assert enc == {"libx264", "aac", "mov_text"}
    flt = ffmpeg.parse_filters(
        "Filters:\n  T.. = Timeline support\n ... palettegen        V->V       Find palette\n"
        " TSC subtitles         V->V       Render\n .S. concat            N->N       Concat\n")
    assert flt == {"palettegen", "subtitles", "concat"}


def test_detect_finds_what_the_tasks_need(tools):
    assert not tools.too_old
    for name in ("libx264", "aac"):
        assert tools.has_encoder(name)
    for name in ("palettegen", "paletteuse", "scale", "transpose"):
        assert tools.has_filter(name)


def test_probe_parse():
    data = {"format": {"duration": "12.5", "size": "1000", "format_name": "mov,mp4", "bit_rate": "640"},
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                 "avg_frame_rate": "30000/1001", "side_data_list": [{"rotation": -90}]},
                {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2,
                 "sample_rate": "48000", "tags": {"language": "hin"}},
                {"index": 2, "codec_type": "video", "codec_name": "mjpeg",
                 "disposition": {"attached_pic": 1}},
                {"index": 3, "codec_type": "subtitle", "codec_name": "mov_text"}]}
    m = probe.parse(Path("x.mp4"), data)
    assert m.duration == 12.5 and m.size == 1000
    assert m.video.codec == "h264" and m.video.rotation == -90
    assert m.video.fps == pytest.approx(29.97, abs=0.01)
    assert m.audio.language == "hin" and m.audio.sample_rate == 48000
    assert m.has_subtitles


def test_probe_parse_tolerates_missing_fields():
    m = probe.parse(Path("x"), {"format": {"duration": "N/A"},
                                "streams": [{"codec_type": "audio", "avg_frame_rate": "0/0"}]})
    assert m.duration == 0 and m.video is None and m.audio.fps == 0


def test_parse_keyframes():
    assert probe.parse_keyframes("0.000000,K__\n0.033,___\n2.000000,K__\nN/A,K__\n") == (0.0, 2.0)


def test_probe_real_file(clips, info):
    m = info(clips["main"], keyframes=True)
    assert m.duration == pytest.approx(8, abs=0.1)
    assert (m.video.width, m.video.height) == (640, 360)
    assert m.audio.codec == "aac"
    assert m.keyframes == pytest.approx((0, 2, 4, 6), abs=0.01)


def test_probe_rejects_non_media(tools, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    with pytest.raises(probe.ProbeError):
        probe.probe(p, tools)


def test_progress_parser_handles_split_chunks():
    p = ProgressParser()
    assert p.feed("frame=10\nout_time_us=5000") == []
    blocks = p.feed("00\nprogress=continue\nframe=20\nout_time_us=N/A\nprogress=end\n")
    assert [b["progress"] for b in blocks] == ["continue", "end"]
    assert blocks[0]["out_time_us"] == "500000"
    assert fraction(blocks[0], 2.0) == pytest.approx(0.25)
    assert fraction(blocks[0], None) is None
    assert fraction(blocks[1], 2.0) == 1.0
    assert fraction({"out_time_us": "N/A", "progress": "continue"}, 2.0) is None
    assert fraction({"out_time_us": "9000000", "progress": "continue"}, 2.0) == 1.0


def test_full_args_never_overwrites_unless_told():
    job = Job(["-i", "a", "b"])
    assert "-n" in full_args(job) and "-y" not in full_args(job)
    assert "-y" in full_args(job, overwrite=True) and "-n" not in full_args(job, overwrite=True)
    assert full_args(job)[-3:] == ["-i", "a", "b"]


@pytest.mark.parametrize("args", [
    ["-i", "plain.mp4", "out.mp4"],
    ["-i", "my clip's file.mp4", "-vf", "fps=12,split[a][b];[a]palettegen[p]", "out put.gif"],
    ["-i", 'say "hi".mp4', "-c", "copy", "वीडियो.mkv"],
    ["-i", "-leading-dash.mp4", "$HOME `x` ; rm.mp4"],
])
def test_command_line_round_trip(args):
    text = command_line(Job(list(args)))
    assert text.startswith("ffmpeg ")
    if sys.platform != "win32":
        assert parse_command_line(text) == args


def test_parse_command_line_rejects_empty():
    with pytest.raises(ValueError):
        parse_command_line("   ")


def test_programs_started_from_a_packaged_build_get_the_system_libraries(monkeypatch):
    """A packaged Linux build runs with LD_LIBRARY_PATH set to its own libraries; FFmpeg must
    not inherit that, or the system's FFmpeg fails to start on a newer distribution."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    assert ffmpeg.child_env()["LD_LIBRARY_PATH"] == "/tmp/_MEI123"      # from source: untouched

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    if sys.platform == "win32":
        assert ffmpeg.child_env()["LD_LIBRARY_PATH"] == "/tmp/_MEI123"  # not a Windows matter
        return
    assert "LD_LIBRARY_PATH" not in ffmpeg.child_env()                  # there was none before
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/mylibs")
    env = ffmpeg.child_env()
    assert env["LD_LIBRARY_PATH"] == "/opt/mylibs" and "LD_LIBRARY_PATH_ORIG" not in env
    assert env["PATH"]                                                  # the rest is kept


def test_an_ffmpeg_that_will_not_start_is_reported_not_used(tmp_path):
    if sys.platform == "win32":
        pytest.skip("uses shell scripts")
    for name in ("ffmpeg", "ffprobe"):
        script = tmp_path / name
        script.write_text("#!/bin/sh\nexit 127\n")
        script.chmod(0o755)
    with pytest.raises(ffmpeg.FFmpegUnusable) as e:
        ffmpeg.detect(str(tmp_path))
    assert e.value.path == str(tmp_path / "ffmpeg")
    assert isinstance(e.value, ffmpeg.FFmpegNotFound)
