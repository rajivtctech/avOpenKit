"""T9 Crop to a shape: cut the picture to a shape for sharing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_output, h264_codec, h264_encoder, h264_target,
                   hw_global, hw_note, need_encoder, need_video, shown_size, suggest, translate,
                   video_filter)

ID = "crop"
SHAPES = {"1:1": (1, 1), "4:5": (4, 5), "9:16": (9, 16)}      # width : height


@dataclass
class Settings:
    shape: str = "1:1"
    position: float = 0.5      # 0 keeps the left (or top), 1 the right (or bottom), 0.5 the middle
    output: Path | None = None
    crf: int = 18
    preset: str = "medium"
    hw: object = None


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "cropped", h264_target(media))


def crop_box(width: int, height: int, shape: str, position: float) -> tuple[int, int, int, int, bool]:
    """(crop width, crop height, x, y, sides_cut) for a picture of the given size.
    Sizes are rounded down to even numbers, which H.264 needs."""
    rw, rh = SHAPES[shape]
    position = min(max(position, 0.0), 1.0)
    if width * rh > height * rw:                 # too wide for the shape: cut the sides
        ch = height - height % 2
        cw = int(height * rw / rh)
        cw -= cw % 2
        return cw, ch, int(round((width - cw) * position)), 0, True
    cw = width - width % 2                       # too tall: cut top and bottom
    ch = int(width * rh / rw)
    ch -= ch % 2
    return cw, ch, 0, int(round((height - ch) * position)), False


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    if s.shape not in SHAPES:
        raise TaskError(translate("tasks", "Unknown shape."))
    need_encoder(tools, h264_encoder(s.hw))
    check_encode(s.crf, s.preset)
    width, height = shown_size(media)
    cw, ch, x, y, sides = crop_box(width, height, s.shape, s.position)
    if cw < 16 or ch < 16:
        raise TaskError(translate("tasks", "The picture is too small to crop to this shape."))
    if width - cw < 2 and height - ch < 2:
        raise TaskError(translate("tasks", "The picture is already this shape."))
    copy_audio = Path(out).suffix.lower() == media.path.suffix.lower()
    args = [*hw_global(s.hw), "-i", str(media.path), "-map", "0:v:0", "-map", "0:a?",
            *video_filter(s.hw, f"crop={cw}:{ch}:{x}:{y}"),
            *h264_codec(s.hw, s.crf, s.preset, pix_fmt=True)]
    args += ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]
    args.append(str(out))
    if s.position < 0.34:
        kept = translate("tasks", "the left") if sides else translate("tasks", "the top")
    elif s.position > 0.66:
        kept = translate("tasks", "the right") if sides else translate("tasks", "the bottom")
    else:
        kept = translate("tasks", "the middle")
    notes = [translate("tasks", "Cuts the picture from {0}×{1} to {2}×{3} ({4}), keeping {5}. "
                                "Re-encodes the video.")
             .format(width, height, cw, ch, s.shape, kept), *hw_note(s.hw)]
    return Plan([Job(args, [out], media.duration, translate("tasks", "Crop"))], notes)
