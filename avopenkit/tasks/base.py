"""Shared pieces for the task modules.

A task module has a Settings dataclass, suggest_output() and plan(). plan() turns settings and
probe data into a Plan (argument lists plus plain-language notes). Tasks start no process and
import nothing from the ui package (spec N7).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QCoreApplication

from ..core.ffmpeg import Tools
from ..core.probe import MediaInfo


class TaskError(Exception):
    """The settings cannot be turned into a job; the message is shown to the user."""


def translate(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def secs(value: float) -> str:
    """Seconds as FFmpeg takes them on the command line."""
    return f"{value:.3f}"


def clock(value: float) -> str:
    """Seconds as people read them: 1:02.5"""
    m, s = divmod(max(0.0, value), 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m}:{s:04.1f}"


def suggest(source: Path, tag: str, ext: str | None = None) -> Path:
    """<name>-<tag><ext> beside the source, numbered if that already exists."""
    ext = ext if ext is not None else source.suffix
    candidate = source.with_name(f"{source.stem}-{tag}{ext}")
    n = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}-{tag}-{n}{ext}")
        n += 1
    return candidate


def check_output(output: Path | None, inputs: list[Path]) -> Path:
    """An output must be given and must never be one of the inputs (spec F3)."""
    if output is None or not str(output):
        raise TaskError(translate("tasks", "Choose where to save the result."))
    out = Path(output).resolve()
    for p in inputs:
        if out == Path(p).resolve():
            raise TaskError(translate("tasks", "The result cannot be saved over an input file."))
    return Path(output)


def need_encoder(tools: Tools | None, name: str) -> None:
    if tools is not None and not tools.has_encoder(name):
        raise TaskError(translate(
            "tasks", "This FFmpeg build has no '{0}' encoder, which this task needs.").format(name))


def need_filter(tools: Tools | None, name: str) -> None:
    if tools is not None and not tools.has_filter(name):
        raise TaskError(translate(
            "tasks", "This FFmpeg build has no '{0}' filter, which this task needs.").format(name))


def need_video(media: MediaInfo) -> None:
    if media.video is None:
        raise TaskError(translate("tasks", "This file has no video."))


def check_range(start: float, end: float, duration: float) -> None:
    if start < 0 or end <= start:
        raise TaskError(translate("tasks", "The end must be after the start."))
    if duration and start >= duration:
        raise TaskError(translate("tasks", "The start is beyond the end of the file."))
