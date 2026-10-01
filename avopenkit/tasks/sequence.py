"""T10 Image sequence: a video into numbered pictures, or numbered pictures into a video.

Which way round is decided by the file that is open: a video is turned into pictures; the first
picture of a numbered series (frame-0001.png, frame-0002.png, ...) is turned into a video."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_output, clock, h264_codec, h264_encoder,
                   hw_global, hw_note, need_encoder, need_video, number, translate, video_filter)

ID = "sequence"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"      # H.264 cannot store an odd width or height
MANY = 5000


@dataclass
class Settings:
    # video -> pictures
    format: str = "png"        # png or jpg
    rate: float = 0.0          # pictures per second of video; 0 means every frame
    # pictures -> video
    fps: float = 24.0
    output: Path | None = None
    # Expert options.
    jpeg_quality: int = 2      # 2 (best) to 31
    crf: int = 18
    preset: str = "medium"
    hw: object = None


@dataclass(frozen=True)
class Series:
    pattern: str               # as FFmpeg wants it: /folder/frame-%05d.png
    start: int
    count: int
    first: str                 # file names, for the notes
    last: str
    stem: str                  # the name without its number, for naming the result


def is_image(media: MediaInfo) -> bool:
    return media.path.suffix.lower() in IMAGE_TYPES


def find_series(path: Path) -> Series | None:
    """The numbered series a picture belongs to, counted from that picture upwards."""
    m = re.fullmatch(r"(.*?)(\d+)(\.[^.]+)", path.name)
    if not m:
        return None
    prefix, digits, suffix = m.groups()
    start = int(digits)
    padded = len(digits) > 1 and digits.startswith("0")

    def name(n: int) -> str:
        return f"{prefix}{n:0{len(digits)}d}{suffix}" if padded else f"{prefix}{n}{suffix}"

    count = 0
    while count < 1_000_000 and (path.parent / name(start + count)).is_file():
        count += 1
    if count == 0:
        return None
    spec = f"%0{len(digits)}d" if padded else "%d"
    # A % in a folder or file name would be read as part of the pattern; double it.
    literal = lambda text: text.replace("%", "%%")      # noqa: E731
    pattern = literal(str(path.parent / prefix)) + spec + literal(suffix)
    return Series(pattern, start, count, name(start), name(start + count - 1),
                  prefix.rstrip("-_ .") or "sequence")


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    if is_image(media):
        series = find_series(media.path)
        stem = series.stem if series else media.path.stem
        candidate = media.path.with_name(f"{stem}-video.mp4")
        n = 2
        while candidate.exists():
            candidate = media.path.with_name(f"{stem}-video-{n}.mp4")
            n += 1
        return candidate
    candidate = media.path.with_name(f"{media.path.stem}-frames")
    n = 2
    while candidate.exists():
        candidate = media.path.with_name(f"{media.path.stem}-frames-{n}")
        n += 1
    return candidate


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    if is_image(media):
        return _to_video(s, media, tools, out)
    return _to_pictures(s, media, out)


def _to_pictures(s: Settings, media: MediaInfo, folder: Path) -> Plan:
    if s.format not in ("png", "jpg"):
        raise TaskError(translate("tasks", "Unknown picture format."))
    if s.rate < 0 or s.rate > 240:
        raise TaskError(translate("tasks", "Pictures per second must be between 0 and 240."))
    if not 2 <= s.jpeg_quality <= 31:
        raise TaskError(translate("tasks", "JPEG quality must be between 2 and 31."))
    if folder.suffix.lower() in IMAGE_TYPES | {".mp4", ".mov", ".mkv", ".gif"}:
        raise TaskError(translate("tasks", "The result is a folder of pictures. Give it a "
                                           "folder name, without a file ending."))
    if folder.exists():
        raise TaskError(translate("tasks", "{0} already exists. Choose a new folder name, so "
                                           "that nothing already there is mixed in or replaced.")
                        .format(folder.name))
    args = ["-i", str(media.path)]
    if s.rate:
        args += ["-vf", f"fps={number(s.rate)}"]
        per_second = s.rate
    else:
        args += ["-fps_mode", "passthrough"]
        per_second = media.video.fps or 0
    if s.format == "jpg":
        args += ["-q:v", str(s.jpeg_quality)]
    # A % in the folder's own name would be read as part of the numbering pattern; double it.
    args.append(str(Path(str(folder).replace("%", "%%")) / f"frame-%05d.{s.format}"))
    expected = int(round(media.duration * per_second)) if per_second else 0
    notes = [(translate("tasks", "Saves {0} pictures per second of video as {1} files in a new "
                                 "folder, {2}.") if s.rate else
              translate("tasks", "Saves every frame of the video as a {1} file in a new "
                                 "folder, {2}."))
             .format(number(s.rate), s.format.upper(), folder.name)]
    if expected:
        notes.append(translate("tasks", "About {0} pictures.").format(expected))
    if expected > MANY:
        notes.append(translate("tasks", "That is a great many files and will take a lot of "
                                        "disk space. Trim the video first, or save fewer "
                                        "pictures per second."))
    job = Job(args, [folder], media.duration, translate("tasks", "Video to pictures"),
              make_dirs=[folder])
    return Plan([job], notes)


def _to_video(s: Settings, media: MediaInfo, tools, out: Path) -> Plan:
    series = find_series(media.path)
    if series is None or series.count < 2:
        raise TaskError(translate(
            "tasks", "Open the first picture of a numbered series - for example "
                     "frame-0001.png, with frame-0002.png and the rest beside it."))
    if not 1 <= s.fps <= 240:
        raise TaskError(translate("tasks", "Pictures per second must be between 1 and 240."))
    need_encoder(tools, h264_encoder(s.hw))
    check_encode(s.crf, s.preset)
    length = series.count / s.fps
    args = [*hw_global(s.hw), "-framerate", number(s.fps), "-start_number", str(series.start),
            "-i", series.pattern, *video_filter(s.hw, EVEN),
            *h264_codec(s.hw, s.crf, s.preset, pix_fmt=True), str(out)]
    notes = [translate("tasks", "Makes a video from {0} pictures, {1} to {2}, shown at {3} per "
                                "second: {4} long.")
             .format(series.count, series.first, series.last, number(s.fps), clock(length)),
             *hw_note(s.hw)]
    return Plan([Job(args, [out], length, translate("tasks", "Pictures to video"))], notes)
