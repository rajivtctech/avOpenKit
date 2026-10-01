"""T12 Change speed: time-lapse and slow motion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_output, clock, h264_codec, h264_encoder,
                   h264_target, hw_global, hw_note, need_encoder, need_video, number, suggest,
                   translate, video_filter)

ID = "speed"
SLOWEST, FASTEST = 0.1, 100.0


@dataclass
class Settings:
    factor: float = 2.0        # 2 is twice as fast, 0.5 is half speed
    keep_sound: bool = True
    output: Path | None = None
    crf: int = 18
    preset: str = "medium"
    hw: object = None


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "fast" if s.factor > 1 else "slow", h264_target(media))


def tempo_chain(factor: float) -> str:
    """atempo filters for a speed. One filter accepts 0.5 to 100, so slower speeds are reached
    by chaining halves: 0.25 is atempo=0.5,atempo=0.5."""
    steps = []
    while factor < 0.5 - 1e-9:
        steps.append(0.5)
        factor /= 0.5
    steps.append(factor)
    return ",".join(f"atempo={number(f)}" for f in steps)


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    if not SLOWEST <= s.factor <= FASTEST:
        raise TaskError(translate("tasks", "The speed must be between {0} and {1} times.")
                        .format(number(SLOWEST), number(FASTEST)))
    if abs(s.factor - 1.0) < 0.001:
        raise TaskError(translate("tasks", "A speed of 1 leaves the video as it is. Choose a "
                                           "faster or slower speed."))
    need_encoder(tools, h264_encoder(s.hw))
    check_encode(s.crf, s.preset)
    sound = s.keep_sound and media.audio is not None
    args = [*hw_global(s.hw), "-i", str(media.path), "-map", "0:v:0"]
    if sound:
        args += ["-map", "0:a:0"]
    args += [*video_filter(s.hw, f"setpts=PTS/{number(s.factor)}"),
             *h264_codec(s.hw, s.crf, s.preset, pix_fmt=True)]
    args += ["-af", tempo_chain(s.factor), "-c:a", "aac", "-b:a", "192k"] if sound else ["-an"]
    args.append(str(out))

    length = media.duration / s.factor
    if s.factor > 1:
        notes = [translate("tasks", "Plays {0} times faster: {1} becomes {2}. Frames are "
                                    "dropped to do it.")
                 .format(number(s.factor), clock(media.duration), clock(length))]
    else:
        notes = [translate("tasks", "Plays at {0}% of the original speed: {1} becomes {2}. "
                                    "Each frame is shown for longer, so it looks smooth only "
                                    "if the video was filmed at a high frame rate.")
                 .format(number(s.factor * 100), clock(media.duration), clock(length))]
    if sound:
        notes.append(translate("tasks", "The sound is sped up or slowed to match, keeping its "
                                        "pitch."))
    elif media.audio is not None:
        notes.append(translate("tasks", "The result has no sound."))
    notes += hw_note(s.hw)
    return Plan([Job(args, [out], length, translate("tasks", "Change speed"))], notes)
