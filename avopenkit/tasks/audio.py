"""T4 Extract audio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import TaskError, check_output, need_encoder, suggest, translate

ID = "audio"

# "Keep original": the file type that holds each codec on its own.
COPY_EXT = {"aac": ".m4a", "alac": ".m4a", "mp3": ".mp3", "opus": ".opus", "vorbis": ".ogg",
            "flac": ".flac", "ac3": ".ac3", "pcm_s16le": ".wav", "pcm_s24le": ".wav"}
ENCODE = {
    "mp3": (".mp3", "libmp3lame", ["-q:a", "2"]),
    "m4a": (".m4a", "aac", ["-b:a", "192k"]),
    "opus": (".opus", "libopus", ["-b:a", "128k"]),
    "wav": (".wav", "pcm_s16le", []),
}


@dataclass
class Settings:
    format: str = "copy"       # copy, mp3, m4a, opus, wav
    output: Path | None = None


def extension(media: MediaInfo, s: Settings) -> str:
    if s.format == "copy":
        return COPY_EXT.get(media.audio.codec if media.audio else "", ".mka")
    return ENCODE[s.format][0]


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "audio", extension(media, s))


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    if media.audio is None:
        raise TaskError(translate("tasks", "This file has no audio."))
    if s.format != "copy" and s.format not in ENCODE:
        raise TaskError(translate("tasks", "Unknown audio format."))
    args = ["-i", str(media.path), "-vn", "-map", "0:a:0"]
    if s.format == "copy":
        args += ["-c:a", "copy"]
        notes = [translate("tasks", "Copies the original {0} audio without re-encoding: "
                                    "no quality loss.").format(media.audio.codec)]
    else:
        _, encoder, options = ENCODE[s.format]
        need_encoder(tools, encoder)
        args += ["-c:a", encoder, *options]
        notes = [translate("tasks", "Converts the audio from {0} to {1}.")
                 .format(media.audio.codec, s.format.upper())]
    args.append(str(out))
    return Plan([Job(args, [out], media.duration, translate("tasks", "Extract audio"))], notes)
