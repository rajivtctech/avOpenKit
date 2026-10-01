"""The five tasks for visual artists (spec T9-T13): crop, image sequence, contact sheet,
change speed, export for editing."""

import subprocess
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop
from PyQt6.QtGui import QColor, QImage

from avopenkit.core import probe
from avopenkit.core.queue import DONE
from avopenkit.core.runner import run_plan_blocking
from avopenkit.tasks import crop, export, sequence, sheet, speed
from avopenkit.tasks.base import TaskError, shown_size
from avopenkit.ui.main_window import MainWindow, path_size
from avopenkit.ui.widgets import plan_kind
from conftest import make_clip
from test_hardware import VAAPI
from test_tasks import fake, run


def after(args, option):
    return args[args.index(option) + 1]


def wait_until(app, condition, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if condition():
            return True
    return False


@pytest.fixture(scope="session")
def wide(tools, tmp_path_factory):
    """A 12-second 640x360 clip with a keyframe every 2 s."""
    return make_clip(tools, tmp_path_factory.mktemp("artist") / "wide clip.mp4", seconds=12)


# ---------------------------------------------------------------- T9 crop

@pytest.mark.parametrize("size, shape, position, box", [
    ((1280, 720), "1:1", 0.5, (720, 720, 280, 0, True)),
    ((1280, 720), "1:1", 0.0, (720, 720, 0, 0, True)),
    ((1280, 720), "1:1", 1.0, (720, 720, 560, 0, True)),
    ((1280, 720), "4:5", 0.5, (576, 720, 352, 0, True)),
    ((1280, 720), "9:16", 0.5, (404, 720, 438, 0, True)),      # 405 rounded down to even
    ((720, 1280), "1:1", 0.5, (720, 720, 0, 280, False)),      # tall source: cut top and bottom
    ((720, 1280), "4:5", 1.0, (720, 900, 0, 380, False)),
    ((1281, 721), "1:1", 0.5, (720, 720, 280, 0, True)),       # odd sizes come out even
])
def test_crop_box(size, shape, position, box):
    assert crop.crop_box(*size, shape, position) == box
    cw, ch, x, y, _ = box
    assert cw % 2 == 0 and ch % 2 == 0 and x + cw <= size[0] and y + ch <= size[1]


def test_crop_plan():
    p = crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4")), fake())
    a = p.jobs[0].args
    assert after(a, "-vf") == "crop=720:720:280:0" and after(a, "-c:v") == "libx264"
    assert after(a, "-c:a") == "copy" and plan_kind(p) == "mixed"
    assert "1280×720 to 720×720" in p.notes[0] and "the middle" in p.notes[0]
    assert "the left" in crop.plan(crop.Settings("1:1", 0.0, Path("o.mp4")), fake()).notes[0]


def test_crop_uses_the_picture_as_displayed():
    sideways = fake(rotation=90)                              # stored 1280x720, shown 720x1280
    assert shown_size(sideways) == (720, 1280)
    a = crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4")), sideways).jobs[0].args
    assert after(a, "-vf") == "crop=720:720:0:280"


def test_crop_refusals_and_file_type():
    with pytest.raises(TaskError, match="already this shape"):
        crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4")), fake(w=720, h=720))
    with pytest.raises(TaskError):
        crop.plan(crop.Settings("2:3", 0.5, Path("o.mp4")), fake())
    with pytest.raises(TaskError):
        crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4")), fake(vcodec=None))
    webm = fake("in.webm", vcodec="vp9", acodec="opus")
    assert crop.suggest_output(webm, crop.Settings()).suffix == ".mp4"
    a = crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4")), webm).jobs[0].args
    assert after(a, "-c:a") == "aac"                           # Opus does not go into the MP4 as it is
    hw = crop.plan(crop.Settings("1:1", 0.5, Path("o.mp4"), hw=VAAPI), fake()).jobs[0].args
    assert after(hw, "-vf") == "crop=720:720:280:0,format=nv12,hwupload"


def test_crop_runs(tools, wide, info, tmp_path):
    media = info(wide)
    for shape, size in (("1:1", (360, 360)), ("9:16", (202, 360)), ("4:5", (288, 360))):
        out = tmp_path / f"{shape.replace(':', 'x')}.mp4"
        run(crop.plan(crop.Settings(shape, 0.5, out), media, tools), tools)
        got = info(out)
        assert (got.video.width, got.video.height) == size and got.audio is not None
        assert got.duration == pytest.approx(12, abs=0.2)


def test_crop_keeps_the_part_that_was_chosen(tools, info, tmp_path):
    """Left half red, right half blue: keeping the left gives red, the right blue."""
    src = tmp_path / "halves.mp4"
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=red:size=320x240:rate=10:duration=1", "-f", "lavfi", "-i",
                    "color=blue:size=320x240:rate=10:duration=1", "-filter_complex", "hstack",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    media = info(src)                                          # 640x240

    def middle_pixel(position):
        out = tmp_path / f"p{position}.mp4"
        run(crop.plan(crop.Settings("1:1", position, out), media, tools), tools)
        raw = subprocess.run([tools.ffmpeg, "-v", "error", "-i", str(out), "-frames:v", "1",
                              "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        return raw[0], raw[2]                                  # red, blue

    red, blue = middle_pixel(0.0)
    assert red > 150 and blue < 80
    red, blue = middle_pixel(1.0)
    assert blue > 150 and red < 80


# ---------------------------------------------------------------- T10 image sequence

def touch_series(folder, names):
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x")
    return folder


def test_find_series(tmp_path):
    d = touch_series(tmp_path / "a", [f"frame-{n:04d}.png" for n in range(1, 31)])
    s = sequence.find_series(d / "frame-0001.png")
    assert (s.start, s.count, s.first, s.last, s.stem) == (1, 30, "frame-0001.png",
                                                           "frame-0030.png", "frame")
    assert s.pattern == str(d / "frame-%04d.png")
    assert sequence.find_series(d / "frame-0011.png").count == 20      # from that picture on

    d = touch_series(tmp_path / "b", [f"shot{n}.jpg" for n in range(8, 13)])   # no leading zeros
    s = sequence.find_series(d / "shot8.jpg")
    assert (s.start, s.count, s.pattern) == (8, 5, str(d / "shot%d.jpg"))

    d = touch_series(tmp_path / "100% final", ["img_001.png", "img_002.png"])
    assert sequence.find_series(d / "img_001.png").pattern == str(tmp_path / "100%% final" / "img_%03d.png")

    d = touch_series(tmp_path / "c", ["cover.png", "0001.png", "0002.png"])
    assert sequence.find_series(d / "cover.png") is None               # no number in the name
    assert sequence.find_series(d / "0001.png").stem == "sequence"     # a name that is only a number
    assert sequence.find_series(d / "0009.png") is None                # that picture is not there


def test_video_to_pictures_plan(tmp_path):
    media = fake(tmp_path / "in.mp4", duration=10, fps=30)
    folder = tmp_path / "in-frames"
    p = sequence.plan(sequence.Settings("png", 0, output=folder), media)
    a = p.jobs[0].args
    assert a == ["-i", str(tmp_path / "in.mp4"), "-fps_mode", "passthrough",
                 str(folder / "frame-%05d.png")]
    assert p.jobs[0].make_dirs == [folder] and p.jobs[0].outputs == [folder]
    assert any("300 pictures" in n for n in p.notes)

    p = sequence.plan(sequence.Settings("jpg", 2, output=folder, jpeg_quality=5), media)
    a = p.jobs[0].args
    assert after(a, "-vf") == "fps=2" and after(a, "-q:v") == "5" and a[-1].endswith("frame-%05d.jpg")
    assert any("About 20 pictures" in n for n in p.notes)
    many = sequence.plan(sequence.Settings("png", 0, output=folder), fake(tmp_path / "in.mp4", duration=600))
    assert any("great many files" in n for n in many.notes)


def test_video_to_pictures_never_writes_into_an_existing_folder(tmp_path):
    media = fake(tmp_path / "in.mp4")
    taken = tmp_path / "taken"
    taken.mkdir()
    with pytest.raises(TaskError, match="already exists"):
        sequence.plan(sequence.Settings(output=taken), media)
    with pytest.raises(TaskError, match="folder name"):
        sequence.plan(sequence.Settings(output=tmp_path / "pictures.png"), media)
    assert sequence.suggest_output(media, sequence.Settings()).name == "in-frames"
    (tmp_path / "in-frames").mkdir()
    assert sequence.suggest_output(media, sequence.Settings()).name == "in-frames-2"


def test_pictures_to_video_plan(tmp_path):
    d = touch_series(tmp_path / "s", [f"frame-{n:05d}.png" for n in range(1, 49)])
    media = fake(d / "frame-00001.png", duration=0.04, vcodec="png", acodec=None)
    assert sequence.is_image(media) and not sequence.is_image(fake())
    out = d / "frame-video.mp4"
    assert sequence.suggest_output(media, sequence.Settings()) == out
    p = sequence.plan(sequence.Settings(fps=24, output=out), media)
    a = p.jobs[0].args
    assert a[:6] == ["-framerate", "24", "-start_number", "1", "-i", str(d / "frame-%05d.png")]
    assert after(a, "-vf") == sequence.EVEN and after(a, "-pix_fmt") == "yuv420p"
    assert p.jobs[0].duration == pytest.approx(2.0)
    assert "48 pictures" in p.notes[0] and "frame-00048.png" in p.notes[0]

    alone = touch_series(tmp_path / "one", ["frame-0001.png"])
    with pytest.raises(TaskError, match="numbered series"):
        sequence.plan(sequence.Settings(output=alone / "o.mp4"),
                      fake(alone / "frame-0001.png", vcodec="png", acodec=None))


def test_sequence_runs_both_ways(tools, wide, info, tmp_path):
    media = info(wide)
    folder = tmp_path / "every"
    plan = sequence.plan(sequence.Settings("png", 2, output=folder), media, tools)
    run(plan, tools)
    pictures = sorted(folder.iterdir())
    assert len(pictures) == 24 and pictures[0].name == "frame-00001.png"

    back = tmp_path / "back.mp4"
    first = probe.probe(pictures[0], tools)
    run(sequence.plan(sequence.Settings(fps=12, output=back), first, tools), tools)
    got = info(back)
    assert got.duration == pytest.approx(2.0, abs=0.1) and got.video.codec == "h264"
    assert (got.video.width, got.video.height) == (640, 360)

    jpegs = tmp_path / "100% jpeg"
    run(sequence.plan(sequence.Settings("jpg", 1, output=jpegs), media, tools), tools)
    assert len(list(jpegs.glob("frame-*.jpg"))) == 12                  # a % in the folder name


def test_a_failed_sequence_job_removes_its_folder_and_nothing_else(tools, wide, info, tmp_path):
    folder = tmp_path / "broken"
    plan = sequence.plan(sequence.Settings("png", 1, output=folder), info(wide), tools)
    plan.jobs[0].args.insert(-1, "-no_such_option")
    assert not run_plan_blocking(plan, tools).ok
    assert not folder.exists() and wide.exists()


def test_odd_sized_pictures_become_an_even_sized_video(tools, info, tmp_path):
    d = tmp_path / "odd"
    d.mkdir()
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=green:size=321x241:rate=10:duration=1", str(d / "p%02d.png")], check=True)
    out = tmp_path / "even.mp4"
    run(sequence.plan(sequence.Settings(fps=10, output=out), probe.probe(d / "p01.png", tools),
                      tools), tools)
    assert (info(out).video.width, info(out).video.height) == (320, 240)


# ---------------------------------------------------------------- T11 contact sheet

def test_sheet_plan():
    s = sheet.Settings(4, 3, 320, "jpg", Path("o.jpg"))
    p = sheet.plan(s, fake(duration=12))
    a = p.jobs[0].args
    assert a.count("-i") == 12 and a[:4] == ["-ss", "0.500", "-i", "in.mp4"]
    assert [a[i + 1] for i, w in enumerate(a) if w == "-ss"][-1] == "11.500"
    graph = after(a, "-filter_complex")
    assert graph.count("trim=end_frame=1,scale=320:-2,setsar=1") == 12
    assert graph.endswith("concat=n=12:v=1:a=0,tile=4x3:padding=6:margin=6:color=black[sheet]")
    assert a[-5:] == ["-frames:v", "1", "-q:v", "2", "o.jpg"]
    assert sheet.sheet_size(fake(), s) == (1310, 564) and "1310×564" in p.notes[0]
    assert p.jobs[0].duration is None
    png = sheet.plan(sheet.Settings(2, 2, 320, "png", Path("o.png")), fake()).jobs[0].args
    assert "-q:v" not in png


def test_sheet_refusals():
    for bad in (dict(columns=0), dict(rows=13), dict(tile_width=321), dict(tile_width=32),
                dict(padding=500)):
        with pytest.raises(TaskError):
            sheet.plan(sheet.Settings(output=Path("o.jpg"), **bad), fake())
    with pytest.raises(TaskError, match=".jpg or .png"):
        sheet.plan(sheet.Settings(output=Path("o.gif")), fake())
    with pytest.raises(TaskError, match="length"):
        sheet.plan(sheet.Settings(output=Path("o.jpg")), fake(duration=0))


def test_sheet_runs_and_is_the_size_it_said(tools, wide, info, tmp_path):
    media = info(wide)
    for cols, rows, fmt in ((4, 3, "jpg"), (2, 2, "png"), (1, 5, "jpg")):
        s = sheet.Settings(cols, rows, 160, fmt, tmp_path / f"s{cols}x{rows}.{fmt}")
        run(sheet.plan(s, media, tools), tools)
        got = info(s.output)
        assert (got.video.width, got.video.height) == sheet.sheet_size(media, s)


def test_sheet_frames_come_from_across_the_video(tools, info, tmp_path):
    """First half red, second half blue: the first tile is red, the last blue."""
    src = tmp_path / "two.mp4"
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=red:size=320x180:rate=10:duration=4", "-f", "lavfi", "-i",
                    "color=blue:size=320x180:rate=10:duration=4", "-filter_complex",
                    "[0][1]concat=n=2:v=1:a=0", "-c:v", "libx264", "-g", "10", "-pix_fmt",
                    "yuv420p", str(src)], check=True)
    out = tmp_path / "s.png"
    run(sheet.plan(sheet.Settings(4, 1, 160, "png", out, padding=0), info(src), tools), tools)
    image = QImage(str(out))
    first, last = QColor(image.pixel(80, 45)), QColor(image.pixel(560, 45))
    assert first.red() > 150 and first.blue() < 80 and last.blue() > 150 and last.red() < 80


# ---------------------------------------------------------------- T12 change speed

@pytest.mark.parametrize("factor, chain", [
    (2, "atempo=2"), (8, "atempo=8"), (0.5, "atempo=0.5"), (0.25, "atempo=0.5,atempo=0.5"),
    (0.1, "atempo=0.5,atempo=0.5,atempo=0.5,atempo=0.8"), (1.5, "atempo=1.5"),
])
def test_tempo_chain(factor, chain):
    assert speed.tempo_chain(factor) == chain
    assert all(0.5 <= float(part.split("=")[1]) <= 100 for part in chain.split(","))


def test_speed_plan():
    p = speed.plan(speed.Settings(2.0, True, Path("o.mp4")), fake(duration=12))
    a = p.jobs[0].args
    assert after(a, "-vf") == "setpts=PTS/2" and after(a, "-af") == "atempo=2"
    assert p.jobs[0].duration == pytest.approx(6.0) and "2 times faster" in p.notes[0]
    silent = speed.plan(speed.Settings(8.0, False, Path("o.mp4")), fake(duration=12))
    assert "-an" in silent.jobs[0].args and "-af" not in silent.jobs[0].args
    assert any("no sound" in n for n in silent.notes)
    slow = speed.plan(speed.Settings(0.25, True, Path("o.mp4")), fake(duration=12))
    assert after(slow.jobs[0].args, "-vf") == "setpts=PTS/0.25"
    assert slow.jobs[0].duration == pytest.approx(48.0) and "25% of the original" in slow.notes[0]
    assert "-an" in speed.plan(speed.Settings(2.0, True, Path("o.mp4")), fake(acodec=None)).jobs[0].args
    assert speed.suggest_output(fake(), speed.Settings(0.5)).name == "in-slow.mp4"
    assert speed.suggest_output(fake(), speed.Settings(4.0)).name == "in-fast.mp4"


def test_speed_refusals():
    for factor in (1.0, 0.05, 150.0):
        with pytest.raises(TaskError):
            speed.plan(speed.Settings(factor, True, Path("o.mp4")), fake())


def test_speed_runs(tools, wide, info, tmp_path):
    media = info(wide)
    for factor, sound, length in ((4.0, True, 3.0), (8.0, False, 1.5), (0.5, True, 24.0),
                                  (0.25, True, 48.0)):
        clip = media if factor >= 1 else info(make_clip(tools, tmp_path / f"short{factor}.mp4",
                                                         seconds=2))
        expect = length if factor >= 1 else 2 / factor
        out = tmp_path / f"x{factor}.mp4"
        run(speed.plan(speed.Settings(factor, sound, out), clip, tools), tools)
        got = info(out)
        assert got.duration == pytest.approx(expect, abs=0.25), factor
        assert (got.audio is not None) == sound


# ---------------------------------------------------------------- T13 export for editing

def test_export_plan():
    p = export.plan(export.Settings("hq", Path("o.mov")), fake())
    a = p.jobs[0].args
    assert a == ["-i", "in.mp4", "-map", "0:v:0", "-map", "0:a?", "-c:v", "prores_ks",
                 "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le", "o.mov"]
    assert "ProRes 422 HQ" in p.notes[0] and plan_kind(p) == "encode"
    a = export.plan(export.Settings("proxy", Path("o.mov"), audio_bits=24), fake()).jobs[0].args
    assert after(a, "-profile:v") == "0" and after(a, "-c:a") == "pcm_s24le"
    assert export.suggest_output(fake(), export.Settings()).name == "in-prores.mov"


def test_export_refusals():
    with pytest.raises(TaskError, match=".mov"):
        export.plan(export.Settings("hq", Path("o.mp4")), fake())
    with pytest.raises(TaskError):
        export.plan(export.Settings("ultra", Path("o.mov")), fake())
    with pytest.raises(TaskError):
        export.plan(export.Settings("hq", Path("o.mov"), audio_bits=8), fake())


def test_export_runs(tools, info, tmp_path):
    clip = info(make_clip(tools, tmp_path / "small.mp4", seconds=2, size="320x180"))
    sizes = {}
    for quality in ("proxy", "hq"):
        out = tmp_path / f"{quality}.mov"
        run(export.plan(export.Settings(quality, out), clip, tools), tools)
        got = info(out)
        assert got.video.codec == "prores" and got.audio.codec == "pcm_s16le"
        assert got.duration == pytest.approx(2, abs=0.1)
        sizes[quality] = out.stat().st_size
    assert sizes["hq"] > sizes["proxy"] > clip.size                    # larger, as the note says


# ---------------------------------------------------------------- in the window

@pytest.fixture
def window(app, tools, wide):
    w = MainWindow(tools)
    w.resize(1180, 940)
    w.show()
    w.open_file(wide)
    yield w
    w.close()


def choose(window, word):
    for row in range(window.tasks.count()):
        if word in window.tasks.item(row).text():
            window.tasks.setCurrentRow(row)
            return window.panel()
    raise AssertionError(word)


def run_from_window(app, window):
    window.run()
    assert wait_until(app, lambda: not window.queue.running and not window.queue.waiting(), 60)
    return window.queue.items[-1]


def test_crop_form_shows_the_part_that_will_be_kept(app, window):
    panel = choose(window, "Crop")
    assert panel.view.box() == pytest.approx((140 / 640, 0, 360 / 640, 1.0))   # middle square
    assert (panel.low.text(), panel.high.text()) == ("Left", "Right")
    panel.position.setValue(0)
    assert panel.view.box()[0] == 0 and "crop=360:360:0:0" in window.console.toPlainText()
    panel.shape.setCurrentIndex(panel.shape.findData("9:16"))
    assert "crop=202:360:0:0" in window.console.toPlainText()
    assert wait_until(app, lambda: panel.view._image is not None, 10)          # a frame of the file
    item = run_from_window(app, window)
    assert item.status == DONE
    got = probe.probe(item.result, window.tools)
    assert (got.video.width, got.video.height) == (202, 360)
    item.result.unlink()


def test_sequence_form_follows_the_kind_of_file(app, window, tools, tmp_path):
    panel = choose(window, "Image sequence")
    assert panel.pages.currentIndex() == 0 and "saved as numbered pictures" in panel.mode.text()
    panel.rate.setCurrentIndex(panel.rate.findData(1.0))
    folder = Path(window.output.text())
    assert folder.name == "wide clip-frames" and "No quality loss" not in window.notes.badge.text()
    item = run_from_window(app, window)
    assert item.status == DONE and item.result == folder
    assert len(list(folder.glob("frame-*.png"))) == 12
    assert "Done: wide clip-frames" in window.status.text() and path_size(folder) > 10_000

    window.open_file(folder / "frame-00001.png")              # now a picture is open
    assert panel.pages.currentIndex() == 1 and "made into a video" in panel.mode.text()
    panel.fps.setValue(6.0)
    assert "-framerate 6" in window.console.toPlainText() and "12 pictures" in window.notes.text()
    item = run_from_window(app, window)
    assert item.status == DONE
    assert probe.probe(item.result, tools).duration == pytest.approx(2.0, abs=0.1)
    import shutil
    shutil.rmtree(folder)


def test_sheet_speed_and_export_run_from_the_window(app, window, tools):
    panel = choose(window, "Contact sheet")
    panel.columns.setValue(3)
    panel.rows.setValue(2)
    panel.width.setValue(160)
    assert "3 columns and 2 rows" in window.notes.text()
    item = run_from_window(app, window)
    assert item.status == DONE and item.result.suffix == ".jpg"
    assert probe.probe(item.result, tools).video.width == 3 * 160 + 4 * 6
    item.result.unlink()
    panel.format.setCurrentIndex(panel.format.findData("png"))
    assert window.output.text().endswith(".png")

    panel = choose(window, "Change speed")
    panel.factor.setCurrentIndex(panel.factor.findData(4.0))
    assert "4 times faster" in window.notes.text() and window.output.text().endswith("-fast.mp4")
    item = run_from_window(app, window)
    assert item.status == DONE
    assert probe.probe(item.result, tools).duration == pytest.approx(3.0, abs=0.25)
    item.result.unlink()
    window.expert_box.setChecked(True)
    panel.exact_speed.setValue(1.5)
    assert "setpts=PTS/1.5" in window.console.toPlainText()
    panel.exact_speed.setValue(0.0)                           # back to the choice above
    assert "setpts=PTS/4" in window.console.toPlainText()
    window.expert_box.setChecked(False)

    panel = choose(window, "Export for editing")
    panel.quality.setCurrentIndex(panel.quality.findData("proxy"))
    assert window.output.text().endswith("-prores.mov") and "ProRes 422 Proxy" in window.notes.text()
    assert window.notes.badge.text() == "Re-encodes"


def test_pictures_can_be_opened(app, window, tools, tmp_path):
    png = tmp_path / "still.png"
    subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=orange:size=320x240", "-frames:v", "1", str(png)], check=True)
    assert window.open_file(png)
    assert "320×240" in window.inspector.text()
    choose(window, "Image sequence")
    assert "numbered series" in window.notes.text() and window.notes.kind == "problem"
