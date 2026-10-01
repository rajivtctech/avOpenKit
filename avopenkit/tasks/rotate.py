"""T6 Fix rotation.

Directions were measured with a corner-marker clip (DESIGN.md 1.2):
  -display_rotation  90  turns the picture left (counter-clockwise)   = transpose=2
  -display_rotation -90  turns the picture right (clockwise)          = transpose=1
The metadata value is absolute, not added to what the file already has, so the existing
rotation is added here. A baked-in filter acts on the picture as it is displayed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_output, h264_codec, h264_encoder, hw_global,
                   hw_note, need_encoder, need_video, suggest, translate, video_filter)

ID = "rotate"
METADATA_CONTAINERS = {".mp4", ".m4v", ".mov", ".mkv"}
DELTA = {"left": 90, "right": -90, "180": 180}
FILTER = {"left": "transpose=2", "right": "transpose=1", "180": "hflip,vflip",
          "hflip": "hflip", "vflip": "vflip"}


@dataclass
class Settings:
    action: str = "right"      # left, right, 180, hflip, vflip
    bake: bool = False         # True: re-encode so every player shows it turned
    output: Path | None = None
    # Expert options, used only when baking in.
    crf: int = 18
    preset: str = "medium"
    hw: object = None          # a working HwEncoder to use instead of libx264 when baking in


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "rotated")


def normalise(angle: int) -> int:
    """Into the range -180 < angle <= 180."""
    angle %= 360
    return angle - 360 if angle > 180 else angle


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    if s.action not in FILTER:
        raise TaskError(translate("tasks", "Unknown rotation."))
    src = str(media.path)
    label = translate("tasks", "Rotate")
    existing = media.video.rotation
    notes = []

    bake = s.bake
    if not bake and media.path.suffix.lower() not in METADATA_CONTAINERS:
        bake = True
        notes.append(translate("tasks", "This file type cannot store a rotation, so the video "
                                        "is re-encoded."))
    if not bake and s.action in ("hflip", "vflip") and existing:
        bake = True
        notes.append(translate("tasks", "This file already has a stored rotation, so the flip "
                                        "is applied by re-encoding."))

    if bake:
        need_encoder(tools, h264_encoder(s.hw))
        check_encode(s.crf, s.preset)
        args = [*hw_global(s.hw), "-i", src, "-map", "0:v:0", "-map", "0:a?",
                *video_filter(s.hw, FILTER[s.action]),
                *h264_codec(s.hw, s.crf, s.preset), "-c:a", "copy", str(out)]
        notes.insert(0, translate("tasks", "Re-encodes the video with the picture turned, so "
                                           "every player shows it the same way."))
        notes += hw_note(s.hw)
        return Plan([Job(args, [out], media.duration, label)], notes)

    if s.action in DELTA:
        option = ["-display_rotation", str(normalise(existing + DELTA[s.action]))]
    else:
        option = ["-display_" + s.action]
    args = [*option, "-i", src, "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
            "-c", "copy", str(out)]
    notes.insert(0, translate("tasks", "Changes only the stored rotation: instant, no quality "
                                       "loss."))
    notes.append(translate("tasks", "A few players ignore the stored rotation. If the result "
                                    "still looks wrong there, use Bake in."))
    return Plan([Job(args, [out], media.duration, label)], notes)
