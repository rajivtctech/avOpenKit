"""T7 Make a GIF from a section of a video."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_output, clock, need_filter, need_video, secs, suggest,
                   translate)

ID = "gif"
DITHERS = ("sierra2_4a", "floyd_steinberg", "bayer", "none")


@dataclass
class Settings:
    start: float = 0.0
    length: float = 3.0
    width: int = 480
    fps: int = 12
    output: Path | None = None
    # Expert options.
    loop: bool = True               # False: play once and stop
    dither: str = "sierra2_4a"      # FFmpeg's default; "bayer" is smaller, "none" is flat


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "clip", ".gif")


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    for name in ("palettegen", "paletteuse"):
        need_filter(tools, name)
    if s.length <= 0 or s.start < 0:
        raise TaskError(translate("tasks", "The length must be more than zero."))
    if media.duration and s.start >= media.duration:
        raise TaskError(translate("tasks", "The start is beyond the end of the file."))
    if not 16 <= s.width <= 4096 or not 1 <= s.fps <= 60:
        raise TaskError(translate("tasks", "Width must be 16 to 4096 pixels and the frame rate "
                                           "1 to 60."))
    length = min(s.length, media.duration - s.start) if media.duration else s.length
    width = min(s.width, media.video.width) if media.video.width else s.width
    if s.dither not in DITHERS:
        raise TaskError(translate("tasks", "Unknown dithering method."))
    use = "paletteuse" if s.dither == "sierra2_4a" else f"paletteuse=dither={s.dither}"
    graph = (f"fps={s.fps},scale={width}:-1:flags=lanczos,"
             f"split[a][b];[a]palettegen[p];[b][p]{use}")
    args = ["-ss", secs(s.start), "-t", secs(length), "-i", str(media.path),
            "-vf", graph, "-loop", "0" if s.loop else "-1", str(out)]
    notes = [(translate("tasks", "Makes a looping GIF from {0}, {1} long: {2} frames, {3} pixels "
                                 "wide. GIFs have no sound.") if s.loop else
              translate("tasks", "Makes a GIF that plays once, from {0}, {1} long: {2} frames, "
                                 "{3} pixels wide. GIFs have no sound."))
             .format(clock(s.start), clock(length), round(length * s.fps), width),
             translate("tasks", "GIF files grow quickly: halving the width or the frame rate "
                                "makes the file much smaller.")]
    return Plan([Job(args, [out], length, translate("tasks", "Make a GIF"))], notes)
