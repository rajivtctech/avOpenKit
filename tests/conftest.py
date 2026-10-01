import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from avopenkit.core import ffmpeg, probe  # noqa: E402


@pytest.fixture(scope="session")
def tools():
    try:
        return ffmpeg.detect()
    except ffmpeg.FFmpegNotFound:
        pytest.skip("ffmpeg is not installed")


def make_clip(tools, path, seconds=8, size="640x360", rate=30, tone=440, audio=True, gop=60):
    cmd = [tools.ffmpeg, "-v", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={tone}:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-g", str(gop), "-keyint_min", str(gop),
            "-sc_threshold", "0", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-ar", "44100", "-ac", "1"]
    subprocess.run([*cmd, str(path)], check=True)
    return Path(path)


@pytest.fixture(scope="session")
def clips(tools, tmp_path_factory):
    """Generated test clips. One name has a space, a quote and non-Latin text (spec N3)."""
    d = tmp_path_factory.mktemp("clips")
    return {
        "main": make_clip(tools, d / "my clip's वीडियो.mp4"),
        "same": make_clip(tools, d / "second.mp4", seconds=4, tone=880),
        "other": make_clip(tools, d / "other size.mp4", seconds=3, size="320x240", rate=25),
        "silent": make_clip(tools, d / "silent.mp4", seconds=3, audio=False),
        "dir": d,
    }


@pytest.fixture(scope="session")
def srt(clips):
    p = clips["dir"] / "lines: it's [here].srt"
    p.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
                 "2\n00:00:04,000 --> 00:00:06,000\nनमस्ते\n", encoding="utf-8")
    return p


@pytest.fixture
def info(tools):
    return lambda path, keyframes=False: probe.probe(path, tools, keyframes=keyframes)
