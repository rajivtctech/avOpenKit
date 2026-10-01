"""T1 Trim: keep the part between two points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (check_output, check_range, clock, need_encoder, secs, suggest, translate)

ID = "trim"
H264_CONTAINERS = {".mp4", ".m4v", ".mov", ".mkv"}


@dataclass
class Settings:
    start: float = 0.0
    end: float = 0.0
    exact: bool = False        # False: stream copy on keyframes. True: re-encode, frame-accurate
    output: Path | None = None


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    ext = media.path.suffix
    if s.exact and media.video and ext.lower() not in H264_CONTAINERS:
        ext = ".mp4"
    return suggest(media.path, "trimmed", ext)


def keyframe_before(media: MediaInfo, t: float) -> float | None:
    """The keyframe a stream-copy cut starting at t really starts on, when keyframes are known."""
    if not media.keyframes:
        return None
    return max((k for k in media.keyframes if k <= t + 0.0005), default=media.keyframes[0])


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    check_range(s.start, s.end, media.duration)
    end = min(s.end, media.duration) if media.duration else s.end
    src = str(media.path)

    if s.exact and media.video:
        need_encoder(tools, "libx264")
        args = ["-ss", secs(s.start), "-to", secs(end), "-i", src,
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-c:a", "aac", "-b:a", "192k", str(out)]
        notes = [translate("tasks", "Re-encodes the video so the cut is exact: {0} to {1} ({2}).")
                 .format(clock(s.start), clock(end), clock(end - s.start)),
                 translate("tasks", "Slower than a fast trim, with a very small loss of quality.")]
        return Plan([Job(args, [out], end - s.start, translate("tasks", "Trim (exact)"))], notes)

    args = ["-ss", secs(s.start), "-to", secs(end), "-i", src,
            "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
            "-c", "copy", "-avoid_negative_ts", "make_zero", str(out)]
    notes = [translate("tasks", "Copies the audio and video without re-encoding: no quality loss.")]
    real_start = keyframe_before(media, s.start) if media.video else s.start
    if real_start is None:
        real_start = s.start
        notes.append(translate(
            "tasks", "The video will start on the keyframe at or before {0}, so the result may "
                     "begin a little earlier than asked.").format(clock(s.start)))
    elif abs(real_start - s.start) > 0.02:
        notes.append(translate(
            "tasks", "The video will start at {0}, the nearest keyframe before {1}. "
                     "Choose Exact for a cut exactly at {1}.")
            .format(clock(real_start), clock(s.start)))
    return Plan([Job(args, [out], end - real_start, translate("tasks", "Trim (fast)"))], notes)
