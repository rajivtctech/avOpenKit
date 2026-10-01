"""T11 Contact sheet: frames from across a video, laid out as one picture."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_output, clock, need_filter, need_video, secs, shown_size,
                   suggest, translate)

ID = "sheet"


@dataclass
class Settings:
    columns: int = 4
    rows: int = 4
    tile_width: int = 320
    format: str = "jpg"        # jpg or png
    output: Path | None = None
    padding: int = 6           # expert: pixels between and around the frames


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "sheet", "." + s.format)


def sheet_size(media: MediaInfo, s: Settings) -> tuple[int, int]:
    """The size of the finished sheet in pixels."""
    width, height = shown_size(media)
    tile_h = int(round(s.tile_width * height / width / 2)) * 2
    return (s.columns * s.tile_width + (s.columns + 1) * s.padding,
            s.rows * tile_h + (s.rows + 1) * s.padding)


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    for name in ("tile", "concat", "trim"):
        need_filter(tools, name)
    if not (1 <= s.columns <= 12 and 1 <= s.rows <= 12):
        raise TaskError(translate("tasks", "Columns and rows must each be between 1 and 12."))
    if not 64 <= s.tile_width <= 1920 or s.tile_width % 2:
        raise TaskError(translate("tasks", "The width of each frame must be an even number "
                                           "between 64 and 1920."))
    if not 0 <= s.padding <= 100:
        raise TaskError(translate("tasks", "The gap must be between 0 and 100 pixels."))
    if Path(out).suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise TaskError(translate("tasks", "Save the sheet as a .jpg or .png file."))
    if media.duration <= 0:
        raise TaskError(translate("tasks", "The length of this file is unknown, so frames "
                                           "cannot be picked evenly from it."))
    count = s.columns * s.rows
    # One seek per frame, each taking only the first frame it lands on: a two-hour film costs
    # no more than a short clip, where decoding the whole file to pick frames would.
    args, graph, pads = [], [], ""
    for i in range(count):
        args += ["-ss", secs(media.duration * (i + 0.5) / count), "-i", str(media.path)]
        graph.append(f"[{i}:v:0]trim=end_frame=1,scale={s.tile_width}:-2,setsar=1[v{i}]")
        pads += f"[v{i}]"
    graph.append(f"{pads}concat=n={count}:v=1:a=0,tile={s.columns}x{s.rows}:"
                 f"padding={s.padding}:margin={s.padding}:color=black[sheet]")
    args += ["-filter_complex", ";".join(graph), "-map", "[sheet]", "-frames:v", "1"]
    if Path(out).suffix.lower() != ".png":
        args += ["-q:v", "2"]
    args.append(str(out))
    width, height = sheet_size(media, s)
    notes = [translate("tasks", "Lays out {0} frames, one every {1}, in {2} columns and {3} "
                                "rows: a picture of {4}×{5} pixels.")
             .format(count, clock(media.duration / count), s.columns, s.rows, width, height)]
    return Plan([Job(args, [out], None, translate("tasks", "Contact sheet"))], notes)
