"""Each task: settings -> argument list (unit), then the real FFmpeg run checked with ffprobe."""

import subprocess
from pathlib import Path

import pytest

from avopenkit.core import probe
from avopenkit.core.probe import MediaInfo, Stream
from avopenkit.core.runner import run_plan_blocking
from avopenkit.tasks import ALL, audio, convert, gif, join, rotate, shrink, subtitles, trim
from avopenkit.tasks.base import TaskError, clock, suggest


def fake(path="in.mp4", duration=20.0, vcodec="h264", acodec="aac", w=1280, h=720, fps=30.0,
         rotation=0, keyframes=(), size=10_000_000, subs=False):
    streams = []
    if vcodec:
        streams.append(Stream(0, "video", vcodec, w, h, fps, rotation=rotation))
    if acodec:
        streams.append(Stream(1, "audio", acodec, channels=2, sample_rate=48000))
    if subs:
        streams.append(Stream(2, "subtitle", "subrip"))
    return MediaInfo(Path(path), duration, size, "mov,mp4", 0, tuple(streams), tuple(keyframes))


def run(plan, tools):
    result = run_plan_blocking(plan, tools)
    assert result.ok, result.log
    for out in plan.outputs:
        assert Path(out).stat().st_size > 0
    return result


def marker_corner(tools, path):
    """Where the white top-left marker of the 'marker' clip ends up when the file is displayed."""
    pgm = subprocess.run([tools.ffmpeg, "-v", "error", "-i", str(path), "-frames:v", "1",
                          "-pix_fmt", "gray", "-c:v", "pgm", "-f", "image2pipe", "-"],
                         capture_output=True, check=True).stdout
    head = pgm.split(None, 4)
    w, h = int(head[1]), int(head[2])
    pix = pgm[-w * h:]
    pts = [(i % w, i // w) for i, b in enumerate(pix) if b > 128]
    cx = sum(p[0] for p in pts) / len(pts) / w
    cy = sum(p[1] for p in pts) / len(pts) / h
    return ("top" if cy < 0.5 else "bottom") + "-" + ("left" if cx < 0.5 else "right"), (w, h)


@pytest.fixture(scope="session")
def marker(tools, clips):
    p = clips["dir"] / "marker.mp4"
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=black:size=320x240:rate=10:duration=1", "-vf",
                    "drawbox=x=0:y=0:w=80:h=60:color=white:t=fill", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


# ---------------------------------------------------------------- shared rules

def test_every_task_module_has_the_same_interface():
    for mod in ALL:
        assert isinstance(mod.ID, str)
        assert callable(mod.plan) and callable(mod.suggest_output) and mod.Settings


@pytest.mark.parametrize("mod, settings", [
    (trim, trim.Settings(1, 5)), (shrink, shrink.Settings()), (convert, convert.Settings()),
    (audio, audio.Settings()), (rotate, rotate.Settings()), (gif, gif.Settings()),
])
def test_output_is_required_and_never_the_input(mod, settings):
    media = fake()
    with pytest.raises(TaskError):
        mod.plan(settings, media)
    settings.output = Path("in.mp4")
    with pytest.raises(TaskError):
        mod.plan(settings, media)
    settings.output = Path("./in.mp4")
    with pytest.raises(TaskError):
        mod.plan(settings, media)


def test_suggest_numbers_when_taken(tmp_path):
    src = tmp_path / "a.mp4"
    assert suggest(src, "trimmed").name == "a-trimmed.mp4"
    (tmp_path / "a-trimmed.mp4").touch()
    assert suggest(src, "trimmed").name == "a-trimmed-2.mp4"
    assert suggest(src, "clip", ".gif").name == "a-clip.gif"


def test_clock():
    assert clock(3.5) == "0:03.5" and clock(62) == "1:02.0" and clock(3725.25) == "1:02:05.2"


# ---------------------------------------------------------------- T1 trim

def test_trim_fast_args_and_keyframe_note():
    media = fake(keyframes=(0, 2, 4, 6, 8))
    p = trim.plan(trim.Settings(3.5, 9, output=Path("o.mp4")), media)
    assert p.jobs[0].args == ["-ss", "3.500", "-to", "9.000", "-i", "in.mp4", "-map", "0:v?",
                              "-map", "0:a?", "-map", "0:s?", "-c", "copy",
                              "-avoid_negative_ts", "make_zero", "o.mp4"]
    assert p.jobs[0].duration == pytest.approx(7.0)        # starts at the 2.0 s keyframe
    assert any("0:02.0" in n for n in p.notes)


def test_trim_fast_on_a_keyframe_says_nothing_about_shifting():
    p = trim.plan(trim.Settings(4, 9, output=Path("o.mp4")), fake(keyframes=(0, 2, 4, 6)))
    assert len(p.notes) == 1 and p.jobs[0].duration == pytest.approx(5.0)


def test_trim_exact_args():
    p = trim.plan(trim.Settings(3.5, 9, exact=True, output=Path("o.mp4")), fake())
    a = p.jobs[0].args
    assert a[:6] == ["-ss", "3.500", "-to", "9.000", "-i", "in.mp4"]
    assert "libx264" in a and "copy" not in a and p.jobs[0].duration == pytest.approx(5.5)


def test_trim_rejects_bad_ranges():
    for start, end in ((5, 5), (6, 2), (-1, 3), (25, 30)):
        with pytest.raises(TaskError):
            trim.plan(trim.Settings(start, end, output=Path("o.mp4")), fake())


def test_trim_exact_output_type_for_webm_source():
    assert trim.suggest_output(fake("a.webm", vcodec="vp9"), trim.Settings(exact=True)).suffix == ".mp4"
    assert trim.suggest_output(fake("a.webm", vcodec="vp9"), trim.Settings()).suffix == ".webm"


def test_trim_runs(tools, clips, info, tmp_path):
    media = info(clips["main"], keyframes=True)
    fast = tmp_path / "fast.mp4"
    plan = trim.plan(trim.Settings(3.5, 7, output=fast), media, tools)
    run(plan, tools)
    assert info(fast).duration == pytest.approx(plan.jobs[0].duration, abs=0.15)   # 2.0 -> 7.0
    exact = tmp_path / "exact.mp4"
    run(trim.plan(trim.Settings(3.5, 7, exact=True, output=exact), media, tools), tools)
    assert info(exact).duration == pytest.approx(3.5, abs=0.1)


# ---------------------------------------------------------------- T2 shrink

def test_shrink_bitrate_formula():
    # 2 MB over 20 s with 96k audio: 2e6*8*0.97/20/1000 - 96 = 680
    assert shrink.video_kbps(2, 20, 96) == 680


def test_shrink_two_passes_and_scaling():
    p = shrink.plan(shrink.Settings(2, 96, Path("o.mp4")), fake(w=1920, h=1080),
                    workdir=Path("/w"))
    one, two = p.jobs
    assert one.outputs == [] and one.args[-3:] == ["-f", "null", "-"] and "-an" in one.args
    assert two.outputs == [Path("o.mp4")] and two.args[-1] == "o.mp4"
    for j in (one, two):
        assert j.args[j.args.index("-b:v") + 1] == "680k"
        assert j.args[j.args.index("-passlogfile") + 1] == str(Path("/w/pass"))
        assert j.args[j.args.index("-vf") + 1] == "scale=-2:480"     # 680k: 480p
    assert any("1080p" in n and "480p" in n for n in p.notes)


def test_shrink_keeps_size_when_bitrate_is_ample():
    p = shrink.plan(shrink.Settings(50, 96, Path("o.mp4")), fake(w=1280, h=720, size=10**9))
    assert "-vf" not in p.jobs[1].args


def test_shrink_refuses_impossible_targets():
    with pytest.raises(TaskError):
        shrink.plan(shrink.Settings(0.1, 96, Path("o.mp4")), fake(duration=600))
    with pytest.raises(TaskError):
        shrink.plan(shrink.Settings(5, 96, Path("o.mp4")), fake(vcodec=None))
    with pytest.raises(TaskError):
        shrink.plan(shrink.Settings(5, 96, Path("o.mp4")), fake(duration=0))


def test_shrink_runs_and_lands_under_target(tools, clips, info, tmp_path):
    out = tmp_path / "small.mp4"
    plan = shrink.plan(shrink.Settings(0.5, 64, out), info(clips["main"]), tools, tmp_path)
    run(plan, tools)
    size = out.stat().st_size
    assert 0.5 * shrink.MB * 0.6 < size <= 0.5 * shrink.MB
    assert info(out).duration == pytest.approx(8, abs=0.2)


# ---------------------------------------------------------------- T3 convert

def test_convert_copies_what_fits():
    a = convert.plan(convert.Settings("mov", output=Path("o.mov")), fake()).jobs[0].args
    assert a[a.index("-c:v") + 1] == "copy" and a[a.index("-c:a") + 1] == "copy"
    a = convert.plan(convert.Settings("mkv", output=Path("o.mkv")), fake()).jobs[0].args
    assert a == ["-i", "in.mp4", "-map", "0", "-c", "copy", "o.mkv"]


def test_convert_reencodes_only_what_does_not_fit():
    a = convert.plan(convert.Settings("mp4", output=Path("o.mp4")),
                     fake("in.mkv", vcodec="h264", acodec="opus")).jobs[0].args
    assert a[a.index("-c:v") + 1] == "copy" and a[a.index("-c:a") + 1] == "aac"
    a = convert.plan(convert.Settings("webm", "small", Path("o.webm")), fake()).jobs[0].args
    assert a[a.index("-c:v") + 1] == "libvpx-vp9" and a[a.index("-crf") + 1] == "40"
    assert a[a.index("-c:a") + 1] == "libopus"


def test_convert_warns_about_dropped_subtitles():
    p = convert.plan(convert.Settings("mp4", output=Path("o.mp4")), fake("in.mkv", subs=True))
    assert any("MKV" in n for n in p.notes)


def test_convert_runs(tools, clips, info, tmp_path):
    media = info(clips["other"])
    mkv = tmp_path / "o.mkv"
    run(convert.plan(convert.Settings("mkv", output=mkv), media, tools), tools)
    assert (info(mkv).video.codec, info(mkv).audio.codec) == ("h264", "aac")
    webm = tmp_path / "o.webm"
    run(convert.plan(convert.Settings("webm", "small", webm), media, tools), tools)
    assert (info(webm).video.codec, info(webm).audio.codec) == ("vp9", "opus")
    back = tmp_path / "back.mp4"
    run(convert.plan(convert.Settings("mp4", output=back), info(webm), tools), tools)
    assert (info(back).video.codec, info(back).audio.codec) == ("h264", "aac")


# ---------------------------------------------------------------- T4 audio

def test_audio_copy_picks_the_right_file_type():
    assert audio.suggest_output(fake(), audio.Settings()).suffix == ".m4a"
    assert audio.suggest_output(fake(acodec="opus"), audio.Settings()).suffix == ".opus"
    assert audio.suggest_output(fake(acodec="dts"), audio.Settings()).suffix == ".mka"
    assert audio.suggest_output(fake(), audio.Settings("mp3")).suffix == ".mp3"


def test_audio_args_and_no_audio():
    a = audio.plan(audio.Settings("copy", Path("o.m4a")), fake()).jobs[0].args
    assert a == ["-i", "in.mp4", "-vn", "-map", "0:a:0", "-c:a", "copy", "o.m4a"]
    a = audio.plan(audio.Settings("mp3", Path("o.mp3")), fake()).jobs[0].args
    assert a[-4:] == ["libmp3lame", "-q:a", "2", "o.mp3"]
    with pytest.raises(TaskError):
        audio.plan(audio.Settings("copy", Path("o.m4a")), fake(acodec=None))


def test_audio_runs(tools, clips, info, tmp_path):
    media = info(clips["main"])
    for fmt, codec in (("copy", "aac"), ("mp3", "mp3"), ("opus", "opus"), ("wav", "pcm_s16le")):
        s = audio.Settings(fmt)
        out = tmp_path / ("a" + audio.extension(media, s))
        s.output = out
        run(audio.plan(s, media, tools), tools)
        got = info(out)
        assert got.video is None and got.audio.codec == codec
        assert got.duration == pytest.approx(8, abs=0.2)


# ---------------------------------------------------------------- T5 join

def test_join_list_file_escapes_quotes(tmp_path):
    text = join.list_file([fake(tmp_path / "it's a clip.mp4"), fake(tmp_path / "b.mp4")])
    first = text.splitlines()[0]
    assert first.startswith("file '") and "it'\\''s a clip.mp4'" in first


def test_join_matching_clips_use_the_demuxer():
    clips = [fake("/v/a.mp4", 20), fake("/v/b.mp4", 6)]
    p = join.plan(join.Settings(clips, Path("/v/o.mp4")), workdir=Path("/w"))
    a = p.jobs[0].args
    assert a[:6] == ["-f", "concat", "-safe", "0", "-i", str(Path("/w/join-list.txt"))]
    assert "copy" in a and p.jobs[0].duration == 26
    assert list(p.write_files) == [Path("/w/join-list.txt")]


def test_join_mismatched_clips_reencode_and_say_why():
    clips = [fake("/v/a.mp4", w=1280, h=720), fake("/v/b.mp4", w=640, h=480, fps=25)]
    p = join.plan(join.Settings(clips, Path("/v/o.mp4")))
    a = p.jobs[0].args
    graph = a[a.index("-filter_complex") + 1]
    assert "scale=1280:720" in graph and "concat=n=2:v=1:a=1[v][a]" in graph
    assert not p.write_files and "libx264" in a
    assert sum("b.mp4" in n for n in p.notes) == 3          # width, height, frame rate


def test_join_needs_two_clips_and_protects_inputs():
    with pytest.raises(TaskError):
        join.plan(join.Settings([fake()], Path("o.mp4")))
    with pytest.raises(TaskError):
        join.plan(join.Settings([fake("a.mp4"), fake("b.mp4")], Path("b.mp4")))


def test_join_runs(tools, clips, info, tmp_path):
    same = tmp_path / "same.mp4"
    plan = join.plan(join.Settings([info(clips["main"]), info(clips["same"])], same), None,
                     tools, tmp_path)
    assert "-filter_complex" not in plan.jobs[0].args
    run(plan, tools)
    assert info(same).duration == pytest.approx(12, abs=0.2)

    mixed = tmp_path / "mixed.mp4"
    plan = join.plan(join.Settings([info(clips["main"]), info(clips["other"])], mixed), None,
                     tools, tmp_path)
    assert "-filter_complex" in plan.jobs[0].args
    run(plan, tools)
    got = info(mixed)
    assert got.duration == pytest.approx(11, abs=0.2)
    assert (got.video.width, got.video.height) == (640, 360) and got.audio is not None

    silent = tmp_path / "silent.mp4"
    plan = join.plan(join.Settings([info(clips["other"]), info(clips["silent"])], silent), None,
                     tools, tmp_path)
    run(plan, tools)
    assert info(silent).audio is None and info(silent).duration == pytest.approx(6, abs=0.2)


# ---------------------------------------------------------------- T6 rotate

@pytest.mark.parametrize("existing, action, expected", [
    (0, "left", "90"), (0, "right", "-90"), (0, "180", "180"),
    (90, "left", "180"), (90, "right", "0"), (-90, "right", "180"), (180, "180", "0"),
    (-90, "left", "0"),
])
def test_rotate_metadata_adds_to_existing(existing, action, expected):
    p = rotate.plan(rotate.Settings(action, output=Path("o.mp4")), fake(rotation=existing))
    a = p.jobs[0].args
    assert a[:2] == ["-display_rotation", expected] and "copy" in a


def test_rotate_falls_back_to_baking():
    p = rotate.plan(rotate.Settings("right", output=Path("o.avi")), fake("in.avi"))
    assert "transpose=1" in p.jobs[0].args
    p = rotate.plan(rotate.Settings("hflip", output=Path("o.mp4")), fake(rotation=90))
    assert "hflip" in p.jobs[0].args and "-display_hflip" not in p.jobs[0].args
    p = rotate.plan(rotate.Settings("hflip", output=Path("o.mp4")), fake())
    assert p.jobs[0].args[0] == "-display_hflip"


@pytest.mark.parametrize("action, corner, size", [
    ("right", "top-right", (240, 320)), ("left", "bottom-left", (240, 320)),
    ("180", "bottom-right", (320, 240)), ("hflip", "top-right", (320, 240)),
    ("vflip", "bottom-left", (320, 240)),
])
@pytest.mark.parametrize("bake", [False, True])
def test_rotate_turns_the_picture_the_way_the_button_says(tools, marker, info, tmp_path,
                                                         action, corner, size, bake):
    assert marker_corner(tools, marker) == ("top-left", (320, 240))
    out = tmp_path / "r.mp4"
    run(rotate.plan(rotate.Settings(action, bake, out), info(marker), tools), tools)
    assert marker_corner(tools, out) == (corner, size)


def test_rotate_right_twice_is_upside_down(tools, marker, info, tmp_path):
    once, twice = tmp_path / "1.mp4", tmp_path / "2.mp4"
    run(rotate.plan(rotate.Settings("right", output=once), info(marker), tools), tools)
    assert info(once).video.rotation == -90
    run(rotate.plan(rotate.Settings("right", output=twice), info(once), tools), tools)
    assert marker_corner(tools, twice) == ("bottom-right", (320, 240))


# ---------------------------------------------------------------- T7 gif

def test_gif_args():
    p = gif.plan(gif.Settings(2, 3, 480, 12, Path("o.gif")), fake())
    a = p.jobs[0].args
    assert a[:6] == ["-ss", "2.000", "-t", "3.000", "-i", "in.mp4"]
    assert a[a.index("-vf") + 1] == ("fps=12,scale=480:-1:flags=lanczos,"
                                     "split[a][b];[a]palettegen[p];[b][p]paletteuse")


def test_gif_clamps_to_the_file_and_never_upscales():
    p = gif.plan(gif.Settings(18, 10, 2000, 10, Path("o.gif")), fake(duration=20, w=1280))
    a = p.jobs[0].args
    assert a[a.index("-t") + 1] == "2.000" and "scale=1280:-1" in a[a.index("-vf") + 1]
    with pytest.raises(TaskError):
        gif.plan(gif.Settings(25, 3, output=Path("o.gif")), fake(duration=20))


def test_gif_runs(tools, clips, info, tmp_path):
    out = tmp_path / "o.gif"
    run(gif.plan(gif.Settings(1, 2, 200, 10, out), info(clips["main"]), tools), tools)
    got = info(out)
    assert got.video.codec == "gif" and got.video.width == 200
    assert out.read_bytes()[:6] in (b"GIF89a", b"GIF87a")


# ---------------------------------------------------------------- T8 subtitles

def test_subtitles_track_codec_follows_container():
    for ext, codec in ((".mp4", "mov_text"), (".mkv", "copy"), (".webm", "webvtt")):
        p = subtitles.plan(subtitles.Settings(Path("s.srt"), False, Path("o" + ext)), fake())
        a = p.jobs[0].args
        assert a[a.index("-c:s") + 1] == codec
    with pytest.raises(TaskError):
        subtitles.plan(subtitles.Settings(Path("s.srt"), False, Path("o.avi")), fake())
    with pytest.raises(TaskError):
        subtitles.plan(subtitles.Settings(Path("s.txt"), False, Path("o.mp4")), fake())
    with pytest.raises(TaskError):
        subtitles.plan(subtitles.Settings(None, False, Path("o.mp4")), fake())


def test_subtitles_burn_keeps_the_path_out_of_the_filter():
    p = subtitles.plan(subtitles.Settings(Path("/x/it's: [odd].srt"), True, Path("/x/o.mp4")),
                       fake("/x/in.mp4"), workdir=Path("/w"))
    job = p.jobs[0]
    assert job.args[job.args.index("-vf") + 1] == "subtitles=subs.srt"
    assert job.cwd == Path("/w")
    assert p.copy_files == [(Path("/x/it's: [odd].srt"), Path("/w/subs.srt"))]


def test_subtitles_runs(tools, clips, srt, info, tmp_path):
    media = info(clips["main"])
    soft = tmp_path / "soft.mp4"
    run(subtitles.plan(subtitles.Settings(srt, False, soft), media, tools, tmp_path), tools)
    assert info(soft).has_subtitles and info(soft).video.codec == "h264"

    burned = tmp_path / "burned.mp4"
    plan = subtitles.plan(subtitles.Settings(srt, True, burned), media, tools, tmp_path)
    run(plan, tools)
    assert not info(burned).has_subtitles
    assert info(burned).duration == pytest.approx(8, abs=0.2)

    # The burned frame at 2 s (inside the first subtitle) must differ from the source frame.
    def frame(path):
        return subprocess.run([tools.ffmpeg, "-v", "error", "-ss", "2", "-i", str(path),
                               "-frames:v", "1", "-vf", "crop=iw:ih/4:0:ih*3/4", "-pix_fmt",
                               "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    a, b = frame(clips["main"]), frame(burned)
    changed = sum(abs(x - y) > 60 for x, y in zip(a, b))
    assert changed > 200, "no subtitle pixels found in the burned-in frame"


# ---------------------------------------------------------------- failure handling

def test_failed_job_leaves_no_partial_output(tools, clips, info, tmp_path):
    out = tmp_path / "o.mp4"
    plan = trim.plan(trim.Settings(1, 3, output=out), info(clips["main"]), tools)
    plan.jobs[0].args.insert(-1, "-nonexistent_option")
    result = run_plan_blocking(plan, tools)
    assert not result.ok and not out.exists() and result.log


def test_existing_output_is_refused_and_kept(tools, clips, info, tmp_path):
    """FFmpeg's -n exits 0 when the output exists; the runner must not call that success,
    and must never delete a file it did not create."""
    out = tmp_path / "o.mp4"
    out.write_bytes(b"keep me")
    plan = trim.plan(trim.Settings(1, 3, output=out), info(clips["main"]), tools)
    result = run_plan_blocking(plan, tools)
    assert not result.ok and "already exists" in result.log
    assert out.read_bytes() == b"keep me"

    plan.jobs[0].args.insert(-1, "-nonexistent_option")      # would fail if it ran
    assert not run_plan_blocking(plan, tools).ok
    assert out.read_bytes() == b"keep me"

    plan = trim.plan(trim.Settings(1, 3, output=out), info(clips["main"]), tools)
    assert run_plan_blocking(plan, tools, overwrite=True).ok
    assert info(out).duration == pytest.approx(3, abs=0.2)     # 0 -> 3 on the keyframe at 0
