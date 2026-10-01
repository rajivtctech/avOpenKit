"""T13 Export for editing: ProRes in a MOV file, the format editing programs handle best."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import TaskError, check_output, need_encoder, need_video, suggest, translate

ID = "export"
# name -> (prores_ks profile number, name as editing programs show it)
PROFILES = {"proxy": (0, "ProRes 422 Proxy"), "lt": (1, "ProRes 422 LT"),
            "standard": (2, "ProRes 422"), "hq": (3, "ProRes 422 HQ")}


@dataclass
class Settings:
    quality: str = "standard"
    output: Path | None = None
    audio_bits: int = 16       # expert: 16 or 24


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "prores", ".mov")


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    need_video(media)
    if s.quality not in PROFILES:
        raise TaskError(translate("tasks", "Unknown ProRes quality."))
    if s.audio_bits not in (16, 24):
        raise TaskError(translate("tasks", "Audio must be 16 or 24 bits."))
    if Path(out).suffix.lower() != ".mov":
        raise TaskError(translate("tasks", "ProRes is saved in a .mov file."))
    need_encoder(tools, "prores_ks")
    number_, name = PROFILES[s.quality]
    args = ["-i", str(media.path), "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "prores_ks", "-profile:v", str(number_), "-pix_fmt", "yuv422p10le",
            "-c:a", f"pcm_s{s.audio_bits}le", str(out)]
    notes = [translate("tasks", "Saves as {0}, a format made for editing: every frame is "
                                "stored whole, so an editing program can move through it "
                                "smoothly.").format(name),
             translate("tasks", "Expect a file many times larger than the original. This is "
                                "for handing work to an editor, not for sending or sharing.")]
    return Plan([Job(args, [out], media.duration, translate("tasks", "Export for editing"))],
                notes)
