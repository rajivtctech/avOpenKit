"""T8 Subtitles: burn into the picture, or add as a track that can be switched on and off."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
import re

from .base import (TaskError, check_encode, check_output, need_encoder, need_filter, need_video,
                   suggest, translate)

ID = "subtitles"
SUB_TYPES = {".srt", ".ass", ".ssa", ".vtt"}
# Subtitle codec for a soft track in each container.
TRACK_CODEC = {".mp4": "mov_text", ".m4v": "mov_text", ".mov": "mov_text",
               ".mkv": "copy", ".webm": "webvtt"}


@dataclass
class Settings:
    subtitle_file: Path | None = None
    burn: bool = False
    output: Path | None = None
    # Expert options.
    crf: int = 20              # burn in only
    preset: str = "medium"     # burn in only
    language: str = ""         # track only: three-letter code such as hin, eng, spa


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    ext = media.path.suffix
    if s.burn and ext.lower() not in (".mp4", ".m4v", ".mov", ".mkv"):
        ext = ".mp4"
    elif not s.burn and ext.lower() not in TRACK_CODEC:
        ext = ".mkv"
    return suggest(media.path, "subtitled", ext)


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    need_video(media)
    if s.subtitle_file is None or not str(s.subtitle_file):
        raise TaskError(translate("tasks", "Choose a subtitle file."))
    subs = Path(s.subtitle_file)
    if subs.suffix.lower() not in SUB_TYPES:
        raise TaskError(translate("tasks", "The subtitle file must be .srt, .ass, .ssa or .vtt."))
    out = check_output(s.output, [media.path, subs])
    src = str(media.path.resolve())
    label = translate("tasks", "Subtitles")

    if s.burn:
        need_filter(tools, "subtitles")
        need_encoder(tools, "libx264")
        check_encode(s.crf, s.preset)
        # The filter's own escaping rules for paths are easy to get wrong (colons, quotes,
        # backslashes), so the file is copied to a plain name in the work folder and FFmpeg is
        # run from there: the filter argument then contains no special characters at all.
        work = workdir or Path(".")
        local = work / ("subs" + subs.suffix.lower())
        args = ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-vf", f"subtitles={local.name}",
                "-c:v", "libx264", "-crf", str(s.crf), "-preset", s.preset, "-c:a", "copy",
                str(Path(out).resolve())]
        notes = [translate("tasks", "Draws the subtitles into the picture and re-encodes the "
                                    "video. They cannot be switched off afterwards.")]
        return Plan([Job(args, [out], media.duration, label, cwd=work)], notes,
                    copy_files=[(subs, local)])

    codec = TRACK_CODEC.get(Path(out).suffix.lower())
    if codec is None:
        raise TaskError(translate("tasks", "A subtitle track can be added to MP4, MOV, MKV or "
                                           "WebM files. Save the result as one of those."))
    if codec == "copy" and subs.suffix.lower() == ".vtt":
        codec = "srt"
    args = ["-i", src, "-i", str(subs.resolve()), "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
            "-map", "1:0", "-c", "copy", "-c:s", codec]
    if s.language:
        if not re.fullmatch(r"[a-z]{2,3}", s.language):
            raise TaskError(translate("tasks", "The language is a two- or three-letter code, "
                                               "such as hin, eng or spa."))
        new_index = sum(1 for st in media.streams if st.kind == "subtitle")
        args += [f"-metadata:s:s:{new_index}", f"language={s.language}"]
    args.append(str(out))
    notes = [translate("tasks", "Adds the subtitles as a separate track without re-encoding. "
                                "The viewer switches them on in the player.")]
    return Plan([Job(args, [out], media.duration, label)], notes)
