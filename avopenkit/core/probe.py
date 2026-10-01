"""ffprobe -> MediaInfo. Parsing is separate from running so it can be tested without FFmpeg."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ffmpeg import Tools, run_quiet


class ProbeError(Exception):
    pass


@dataclass(frozen=True)
class Stream:
    index: int
    kind: str  # "video", "audio", "subtitle", ...
    codec: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    bit_rate: int = 0
    channels: int = 0
    sample_rate: int = 0
    rotation: int = 0  # display rotation, counter-clockwise degrees, as ffprobe reports it
    language: str = ""
    attached_pic: bool = False


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    size: int
    format_name: str
    bit_rate: int
    streams: tuple[Stream, ...]
    keyframes: tuple[float, ...] = field(default=())

    def _first(self, kind: str) -> Stream | None:
        return next((s for s in self.streams if s.kind == kind and not s.attached_pic), None)

    @property
    def video(self) -> Stream | None:
        return self._first("video")

    @property
    def audio(self) -> Stream | None:
        return self._first("audio")

    @property
    def has_subtitles(self) -> bool:
        return any(s.kind == "subtitle" for s in self.streams)


def _num(value, cast=float, default=0):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _rate(text: str) -> float:
    try:
        n, _, d = (text or "0/1").partition("/")
        return float(n) / float(d or 1) if float(d or 1) else 0.0
    except ValueError:
        return 0.0


def parse(path: Path, data: dict, keyframes: tuple[float, ...] = ()) -> MediaInfo:
    fmt = data.get("format") or {}
    streams = []
    for s in data.get("streams") or []:
        rotation = 0
        for side in s.get("side_data_list") or []:
            if "rotation" in side:
                rotation = int(round(_num(side["rotation"])))
        streams.append(Stream(
            index=_num(s.get("index"), int),
            kind=s.get("codec_type", ""),
            codec=s.get("codec_name", ""),
            width=_num(s.get("width"), int),
            height=_num(s.get("height"), int),
            fps=_rate(s.get("avg_frame_rate") or s.get("r_frame_rate")),
            bit_rate=_num(s.get("bit_rate"), int),
            channels=_num(s.get("channels"), int),
            sample_rate=_num(s.get("sample_rate"), int),
            rotation=rotation,
            language=(s.get("tags") or {}).get("language", ""),
            attached_pic=bool((s.get("disposition") or {}).get("attached_pic")),
        ))
    return MediaInfo(
        path=Path(path), duration=_num(fmt.get("duration")), size=_num(fmt.get("size"), int),
        format_name=fmt.get("format_name", ""), bit_rate=_num(fmt.get("bit_rate"), int),
        streams=tuple(streams), keyframes=keyframes,
    )


def parse_keyframes(csv_text: str) -> tuple[float, ...]:
    """Lines of 'pts_time,flags' from ffprobe -show_entries packet=pts_time,flags."""
    times = []
    for line in csv_text.splitlines():
        t, _, flags = line.partition(",")
        if "K" in flags:
            try:
                times.append(float(t))
            except ValueError:
                pass
    return tuple(sorted(times))


def probe(path: Path | str, tools: Tools, keyframes: bool = False) -> MediaInfo:
    path = Path(path)
    r = run_quiet([tools.ffprobe, "-v", "error", "-print_format", "json",
                   "-show_format", "-show_streams", str(path)])
    if r.returncode != 0:
        raise ProbeError(r.stderr.strip() or f"ffprobe failed on {path}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ProbeError(str(e)) from e
    if not data.get("streams"):
        raise ProbeError(f"No audio or video found in {path.name}")
    kf: tuple[float, ...] = ()
    if keyframes and any(s.get("codec_type") == "video" for s in data["streams"]):
        k = run_quiet([tools.ffprobe, "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", str(path)])
        kf = parse_keyframes(k.stdout)
    return parse(path, data, kf)
