#!/usr/bin/env python3
"""Make the parts of the User Guide that come from the program itself.

    .venv/bin/python tools/make_guide_assets.py reference     rewrite the generated command
                                                              reference inside docs/USER_GUIDE.md
    .venv/bin/python tools/make_guide_assets.py screenshots   re-take docs/img/*.png

The command reference is built by running the task modules, so it always shows what the program
really generates; tests/test_guide.py fails if the guide is out of date.

Screenshots are taken without a display, at twice the screen resolution. An off-screen capture
cannot see the video surface, so the picture area of the preview is filled in from the frame the
player is holding at that moment.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GUIDE = ROOT / "docs" / "USER_GUIDE.md"
BEGIN, END = "<!-- BEGIN GENERATED COMMANDS -->", "<!-- END GENERATED COMMANDS -->"


# ---------------------------------------------------------------- command reference

def _media(name="in.mp4", duration=60.0, vcodec="h264", acodec="aac", w=1280, h=720, fps=30.0,
           rotation=0, keyframes=(), subs=False):
    from avopenkit.core.probe import MediaInfo, Stream
    streams = [Stream(0, "video", vcodec, w, h, fps, rotation=rotation)] if vcodec else []
    if acodec:
        streams.append(Stream(len(streams), "audio", acodec, channels=2, sample_rate=48000))
    if subs:
        streams.append(Stream(len(streams), "subtitle", "subrip"))
    return MediaInfo(Path(name), duration, 50_000_000, "x", 0, tuple(streams), tuple(keyframes))


def _show(title: str, plan, extra: str = "") -> str:
    lines = [f"#### {title}", "", "```"]
    lines += [shlex.join(["ffmpeg", *job.args]) for job in plan.jobs]
    lines.append("```")
    for path, text in plan.write_files.items():
        lines += ["", f"with `{path}` containing:", "", "```", text.rstrip("\n"), "```"]
    for src, dst in plan.copy_files:
        lines += ["", f"run in the work folder, after copying `{src}` to `{dst}`."]
    if extra:
        lines += ["", extra]
    return "\n".join(lines)


def command_reference() -> str:
    from avopenkit.core.hardware import HwEncoder
    from avopenkit.tasks import (audio, convert, crop, export, gif, join, rotate, sequence, sheet,
                                 shrink, speed, subtitles, trim)
    work = Path("WORK")
    vaapi = HwEncoder("vaapi", "h264_vaapi", "VAAPI", "/dev/dri/renderD128")
    m = _media(keyframes=(0, 2, 4, 6, 8, 10))
    out = []

    def section(name):
        out.append(f"### {name}")

    section("Trim")
    out.append(_show("Fast (the default)", trim.plan(trim.Settings(3.5, 9, output=Path("out.mp4")), m)))
    out.append(_show("Exact", trim.plan(trim.Settings(3.5, 9, True, Path("out.mp4")), m)))
    out.append(_show("Exact, with hardware encoding (VAAPI shown)",
                     trim.plan(trim.Settings(3.5, 9, True, Path("out.mp4"), hw=vaapi), m)))

    section("Shrink to a size")
    out.append(_show("25 MB from a 60-second 720p video: the bitrate is high enough to keep the size",
                     shrink.plan(shrink.Settings(25, 96, Path("out.mp4")), m, workdir=work)))
    out.append(_show("5 MB from the same video: the bitrate is low, so the picture is made smaller",
                     shrink.plan(shrink.Settings(5, 96, Path("out.mp4")), m, workdir=work)))

    section("Convert format")
    out.append(_show("To MKV: everything is copied",
                     convert.plan(convert.Settings("mkv", output=Path("out.mkv")), m)))
    out.append(_show("To MOV from H.264 + AAC: both fit, both are copied",
                     convert.plan(convert.Settings("mov", output=Path("out.mov")), m)))
    out.append(_show("To MP4 from an MKV holding H.264 + Opus: video copied, audio re-encoded",
                     convert.plan(convert.Settings("mp4", output=Path("out.mp4")),
                                  _media("in.mkv", acodec="opus"))))
    out.append(_show("To MP4 from VP9 + Opus, quality Balanced: both re-encoded",
                     convert.plan(convert.Settings("mp4", output=Path("out.mp4")),
                                  _media("in.webm", vcodec="vp9", acodec="opus"))))
    out.append(_show("To WebM from H.264 + AAC, quality Balanced: both re-encoded",
                     convert.plan(convert.Settings("webm", output=Path("out.webm")), m)))

    section("Extract audio")
    for fmt, name in (("copy", "Keep the original audio (AAC here, so an .m4a file)"),
                      ("mp3", "MP3"), ("m4a", "M4A (AAC)"), ("opus", "Opus"), ("wav", "WAV")):
        s = audio.Settings(fmt)
        s.output = Path("out" + audio.extension(m, s))
        out.append(_show(name, audio.plan(s, m)))

    section("Join clips")
    a, b = _media("/videos/a.mp4"), _media("/videos/b.mp4", duration=20)
    out.append(_show("Clips that match: joined without re-encoding",
                     join.plan(join.Settings([a, b], Path("out.mp4")), workdir=work)))
    c = _media("/videos/c.mp4", w=640, h=480, fps=25)
    out.append(_show("Clips that differ: re-encoded to the first clip's size and frame rate",
                     join.plan(join.Settings([a, c], Path("out.mp4")), workdir=work)))

    section("Fix rotation")
    for action, name in (("right", "Turn right"), ("left", "Turn left"),
                         ("180", "Turn upside down"), ("hflip", "Mirror left-right")):
        out.append(_show(name, rotate.plan(rotate.Settings(action, output=Path("out.mp4")), m)))
    out.append(_show("Turn right, on a file that already has a stored rotation of 90°",
                     rotate.plan(rotate.Settings("right", output=Path("out.mp4")),
                                 _media(rotation=90)),
                     "The stored value is absolute, so the existing 90° and the new −90° are "
                     "added to give 0."))
    out.append(_show("Turn right, with Bake in",
                     rotate.plan(rotate.Settings("right", True, Path("out.mp4")), m)))

    section("Make a GIF")
    out.append(_show("3 seconds from 0:02, 480 pixels wide, 12 frames per second",
                     gif.plan(gif.Settings(2, 3, 480, 12, Path("out.gif")), m)))
    out.append(_show("The same, playing once, with Bayer dithering (expert options)",
                     gif.plan(gif.Settings(2, 3, 480, 12, Path("out.gif"), loop=False,
                                           dither="bayer"), m)))

    section("Subtitles")
    out.append(_show("Add as a track, to an MP4",
                     subtitles.plan(subtitles.Settings(Path("/videos/subs.srt"), False,
                                                       Path("/videos/out.mp4")),
                                    _media("/videos/in.mp4"))))
    out.append(_show("Add as a track, to an MKV, with the language set to hin (expert option)",
                     subtitles.plan(subtitles.Settings(Path("/videos/subs.srt"), False,
                                                       Path("/videos/out.mkv"), language="hin"),
                                    _media("/videos/in.mkv"))))
    out.append(_show("Burn in",
                     subtitles.plan(subtitles.Settings(Path("/videos/subs.srt"), True,
                                                       Path("/videos/out.mp4")),
                                    _media("/videos/in.mp4"), workdir=work)))
    section("Crop to a shape")
    out.append(_show("Square, keeping the middle, from a 1280×720 video",
                     crop.plan(crop.Settings("1:1", 0.5, Path("out.mp4")), m)))
    out.append(_show("Tall (9:16), keeping the right",
                     crop.plan(crop.Settings("9:16", 1.0, Path("out.mp4")), m)))

    section("Image sequence")
    out.append(_show("A video into pictures: every frame, as PNG",
                     sequence.plan(sequence.Settings("png", 0, output=Path("/videos/in-frames")),
                                   _media("/videos/in.mp4"))))
    out.append(_show("A video into pictures: 2 per second, as JPEG",
                     sequence.plan(sequence.Settings("jpg", 2, output=Path("/videos/in-frames")),
                                   _media("/videos/in.mp4"))))
    series = sequence.Series("/videos/frame-%04d.png", 1, 48, "frame-0001.png",
                             "frame-0048.png", "frame")
    real_find = sequence.find_series
    sequence.find_series = lambda path: series            # no files are needed for the example
    try:
        out.append(_show("Pictures into a video: frame-0001.png to frame-0048.png at 24 per second",
                         sequence.plan(sequence.Settings(fps=24, output=Path("/videos/out.mp4")),
                                       _media("/videos/frame-0001.png", vcodec="png", acodec=None))))
    finally:
        sequence.find_series = real_find

    section("Contact sheet")
    out.append(_show("Two columns and two rows from a 60-second video (four frames)",
                     sheet.plan(sheet.Settings(2, 2, 320, "jpg", Path("out.jpg")), m),
                     "A sheet with more frames has one `-ss … -i` pair and one filter step for "
                     "each frame."))

    section("Change speed")
    out.append(_show("2 times faster, keeping the sound",
                     speed.plan(speed.Settings(2.0, True, Path("out.mp4")), m)))
    out.append(_show("8 times faster, without sound",
                     speed.plan(speed.Settings(8.0, False, Path("out.mp4")), m)))
    out.append(_show("Quarter speed, keeping the sound",
                     speed.plan(speed.Settings(0.25, True, Path("out.mp4")), m),
                     "One `atempo` step can halve the speed at most, so a quarter is two steps."))

    section("Export for editing")
    out.append(_show("ProRes 422",
                     export.plan(export.Settings("standard", Path("out.mov")), m)))
    out.append(_show("ProRes 422 HQ with 24-bit sound (expert option)",
                     export.plan(export.Settings("hq", Path("out.mov"), audio_bits=24), m)))
    return "\n\n".join(out)


def write_reference() -> bool:
    """Put the reference between the markers. Returns True when the file changed."""
    text = GUIDE.read_text(encoding="utf-8")
    start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
    new = text[:start] + "\n\n" + command_reference() + "\n\n" + text[end:]
    if new != text:
        GUIDE.write_text(new, encoding="utf-8")
    return new != text


# ---------------------------------------------------------------- screenshots

def screenshots() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = "2"
    import shutil
    import subprocess
    import tempfile
    import time

    from PyQt6.QtCore import QCoreApplication, QEventLoop, QPoint, QRect, QSettings, Qt
    from PyQt6.QtGui import QColor, QPainter
    from PyQt6.QtWidgets import QApplication

    from avopenkit.core import ffmpeg, hardware
    from avopenkit.ui.dialogs import AboutDialog, SettingsDialog
    from avopenkit.ui.main_window import MainWindow

    # A fixed folder, so the paths in the pictures are the same every time they are re-taken.
    base = Path(tempfile.gettempdir()) / "avopenkit-guide"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    videos = base / "Videos"
    videos.mkdir()
    QCoreApplication.setOrganizationName("avOpenKit-guide")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(base / "cfg"))
    app = QApplication([])
    from avopenkit.ui import theme
    theme.apply(app, "dark")
    tools = ffmpeg.detect()

    def clip(name, seconds, size="1280x720", tone=440):
        path = videos / name
        subprocess.run([tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={size}:rate=30:duration={seconds}", "-f", "lavfi", "-i",
                        f"sine=frequency={tone}:duration={seconds}", "-c:v", "libx264",
                        "-preset", "veryfast", "-g", "60", "-keyint_min", "60",
                        "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                       check=True)
        return path

    holiday = clip("holiday.mp4", 20)

    def spin(seconds, condition=lambda: False):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)

    def shot(window, name):
        spin(0.3)
        image = window.grab()
        preview = getattr(window, "preview", None)
        if preview is not None and preview.isVisible() and not preview.stills:
            frame = preview.video.videoSink().videoFrame().toImage()
            if not frame.isNull():
                area = QRect(preview.video.mapTo(window, QPoint(0, 0)), preview.video.size())
                painter = QPainter(image)
                painter.fillRect(area, QColor("black"))
                size = frame.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
                target = QRect(0, 0, size.width(), size.height())
                target.moveCenter(area.center())
                painter.drawImage(target, frame)
                painter.end()
        image.save(str(ROOT / "docs" / "img" / name))
        print("wrote", name, image.width(), "x", image.height())

    w = MainWindow(tools)
    w.resize(1180, 1010)
    w.show()
    w.open_file(holiday)
    spin(5, lambda: w.preview.got_frame)

    # 1. The window, on Trim, with the fast-trim keyframe note showing.
    panel = w.panel()
    w.preview.seek(3.5)
    spin(2, lambda: abs(w.preview.position() - 3.5) < 0.05)
    panel._take_position(panel.start)
    panel.end.setValue(9.0)
    w.preview.seek(3.5)
    spin(1.0)
    shot(w, "window.png")

    # 2. Shrink, with a built-in preset applied.
    w.tasks.setCurrentRow(1)
    w.panel().size.setValue(5.0)
    shot(w, "shrink.png")

    # 3. A queue: one job done, two waiting.
    w.tasks.setCurrentRow(3)
    w.run()
    spin(20, lambda: not w.queue.running)
    w.tasks.setCurrentRow(6)
    w.add_to_queue()
    w.tasks.setCurrentRow(1)
    w.add_to_queue()
    w.queue_list.setCurrentRow(0)
    shot(w, "queue.png")
    for item in list(w.queue.items):
        w.queue.remove(item.id)

    # 3a. Crop to a shape: the picture of what will be kept.
    w.tasks.setCurrentRow(8)
    panel = w.panel()
    panel.shape.setCurrentIndex(panel.shape.findData("9:16"))
    panel.position.setValue(70)
    spin(4, lambda: panel.view._image is not None)
    shot(w, "crop.png")

    # 4. Expert mode: options shown, and a command edited by hand.
    w.tasks.setCurrentRow(2)
    w.expert_box.setChecked(True)
    panel = w.panel()
    panel.target.setCurrentIndex(panel.target.findData("webm"))
    w.console.setPlainText(w.console.toPlainText().replace("-b:v 0", "-b:v 0 -row-mt 1"))
    shot(w, "expert.png")
    w.expert_box.setChecked(False)

    # 5. Settings and About.
    found = hardware.detect(tools)
    d = SettingsDialog(w.settings, tools, hardware=found)
    d.show()
    shot(d, "settings.png")
    d.reject()
    a = AboutDialog(tools)
    a.show()
    shot(a, "about.png")
    a.reject()
    w.close()
    shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "reference":
        print("guide updated" if write_reference() else "guide already up to date")
    elif what == "screenshots":
        screenshots()
    else:
        sys.exit(__doc__)
