"""T2 Shrink to a size: two-pass H.264 at the bitrate that fits a target file size."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_kbps, check_output, need_encoder, need_video,
                   suggest, translate)

ID = "shrink"
MB = 1_000_000           # the smaller of the two meanings of "MB", so the result stays under
OVERHEAD = 0.97          # share of the target left after container overhead (DESIGN.md 1.2)
MIN_VIDEO_KBPS = 60

# Below these video bitrates a picture of this height looks worse than a smaller one would.
HEIGHT_STEPS = [(2500, 1080), (1200, 720), (600, 480), (300, 360), (0, 240)]


@dataclass
class Settings:
    target_mb: float = 25.0
    audio_kbps: int = 96
    output: Path | None = None
    # Expert options.
    preset: str = "medium"
    height: int | None = None  # None: choose from the bitrate. 0: keep the source size. Else: this height


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "small", ".mp4")


def video_kbps(target_mb: float, duration: float, audio_kbps: int) -> int:
    return int(target_mb * MB * 8 * OVERHEAD / duration / 1000 - audio_kbps)


def target_height(kbps: int, source_height: int) -> int | None:
    """A smaller height to scale to, or None to keep the source size."""
    for floor, height in HEIGHT_STEPS:
        if kbps >= floor:
            return height if height < source_height else None
    return None


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    need_encoder(tools, "libx264")
    check_encode(None, s.preset)
    check_kbps(s.audio_kbps)
    if s.height is not None and s.height != 0 and not 64 <= s.height <= 4320:
        raise TaskError(translate("tasks", "Picture height must be between 64 and 4320."))
    if s.target_mb <= 0:
        raise TaskError(translate("tasks", "The target size must be more than zero."))
    if media.duration <= 0:
        raise TaskError(translate("tasks", "The length of this file is unknown, so a bitrate "
                                           "for a target size cannot be worked out."))
    audio = s.audio_kbps if media.audio else 0
    kbps = video_kbps(s.target_mb, media.duration, audio)
    if kbps < MIN_VIDEO_KBPS:
        raise TaskError(translate(
            "tasks", "{0} MB is too small for a video {1} s long. Choose a larger size or trim "
                     "the video first.").format(f"{s.target_mb:g}", f"{media.duration:.0f}"))

    notes = []
    if media.size and s.target_mb * MB >= media.size:
        notes.append(translate("tasks", "The file is already smaller than the target; "
                                        "re-encoding it will not help."))
    video = ["-c:v", "libx264", "-b:v", f"{kbps}k", "-preset", s.preset, "-pix_fmt", "yuv420p"]
    if s.height is None:
        height = target_height(kbps, media.video.height)
    else:
        height = s.height if s.height and s.height != media.video.height else None
    if height:
        video += ["-vf", f"scale=-2:{height}"]
        notes.append(translate("tasks", "Picture resized from {0}p to {1}p.")
                     .format(media.video.height, height) if s.height is not None else
                     translate("tasks", "Picture reduced from {0}p to {1}p so it stays clear at "
                                        "this size.").format(media.video.height, height))
    notes.insert(0, translate(
        "tasks", "Re-encodes in two passes to fit {0} MB: video at {1} kbit/s, audio at {2} kbit/s.")
        .format(f"{s.target_mb:g}", kbps, audio))

    passlog = str((workdir or Path(".")) / "pass")
    src = str(media.path)
    pass1 = ["-i", src, "-map", "0:v:0", *video, "-pass", "1", "-passlogfile", passlog,
             "-an", "-f", "null", "-"]
    pass2 = ["-i", src, "-map", "0:v:0", "-map", "0:a:0?", *video,
             "-pass", "2", "-passlogfile", passlog]
    pass2 += ["-c:a", "aac", "-b:a", f"{audio}k"] if audio else ["-an"]
    pass2 += ["-movflags", "+faststart", str(out)]
    return Plan([Job(pass1, [], media.duration, translate("tasks", "Shrink - pass 1 of 2")),
                 Job(pass2, [out], media.duration, translate("tasks", "Shrink - pass 2 of 2"))],
                notes)
