"""T5 Join clips end to end."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_output, h264_codec, h264_encoder, hw_global,
                   hw_note, need_encoder, suggest, translate)

ID = "join"


@dataclass
class Settings:
    clips: list[MediaInfo] = field(default_factory=list)   # in playing order
    output: Path | None = None
    # Expert options.
    reencode: bool = False     # re-encode even when the clips match
    crf: int = 20
    preset: str = "medium"
    hw: object = None          # a working HwEncoder to use instead of libx264


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "joined")


def signature(m: MediaInfo) -> tuple:
    """What must be equal for two clips to be joined without re-encoding."""
    v, a = m.video, m.audio
    return (v.codec if v else None, v.width if v else 0, v.height if v else 0,
            round(v.fps, 2) if v else 0, v.rotation if v else 0,
            a.codec if a else None, a.sample_rate if a else 0, a.channels if a else 0)


def mismatches(clips: list[MediaInfo]) -> list[str]:
    """Plain descriptions of how later clips differ from the first; empty when they all match."""
    names = [translate("tasks", "video format"), translate("tasks", "width"),
             translate("tasks", "height"), translate("tasks", "frame rate"),
             translate("tasks", "rotation"), translate("tasks", "audio format"),
             translate("tasks", "audio sample rate"), translate("tasks", "audio channels")]
    first = signature(clips[0])
    found = []
    for clip in clips[1:]:
        for name, a, b in zip(names, first, signature(clip)):
            if a != b:
                found.append(f"{clip.path.name}: {name} {b} ≠ {a}")
    return found


def list_file(clips: list[MediaInfo]) -> str:
    """Input for the concat demuxer. A quote in a path is written as '\\'' ."""
    lines = ["file '" + str(c.path.resolve()).replace("'", "'\\''") + "'" for c in clips]
    return "\n".join(lines) + "\n"


def plan(s: Settings, media: MediaInfo | None = None, tools=None,
         workdir: Path | None = None) -> Plan:
    clips = s.clips
    if len(clips) < 2:
        raise TaskError(translate("tasks", "Add at least two clips to join."))
    out = check_output(s.output, [c.path for c in clips])
    total = sum(c.duration for c in clips)
    label = translate("tasks", "Join")
    diff = mismatches(clips)
    check_encode(s.crf, s.preset)

    if not diff and not s.reencode:
        listing = (workdir or Path(".")) / "join-list.txt"
        args = ["-f", "concat", "-safe", "0", "-i", str(listing),
                "-map", "0:v?", "-map", "0:a?", "-c", "copy", str(out)]
        notes = [translate("tasks", "All {0} clips match, so they are joined without "
                                    "re-encoding: no quality loss.").format(len(clips))]
        return Plan([Job(args, [out], total, label)], notes, write_files={listing: list_file(clips)})

    if any(c.video is None for c in clips):
        raise TaskError(translate("tasks", "The clips differ and one has no video; these cannot "
                                           "be joined."))
    need_encoder(tools, h264_encoder(s.hw))
    v0 = clips[0].video
    w, h = v0.width - v0.width % 2, v0.height - v0.height % 2
    fps = f"{v0.fps:.3f}".rstrip("0").rstrip(".") if v0.fps else "30"
    with_audio = all(c.audio is not None for c in clips)
    args, graph, pads = [], [], ""
    for i, c in enumerate(clips):
        args += ["-i", str(c.path)]
        graph.append(f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]")
        pads += f"[v{i}]"
        if with_audio:
            graph.append(f"[{i}:a:0]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]")
            pads += f"[a{i}]"
    joined = "[v]" if s.hw is None else "[vj]"
    graph.append(f"{pads}concat=n={len(clips)}:v=1:a={1 if with_audio else 0}"
                 + (f"{joined}[a]" if with_audio else joined))
    if s.hw is not None:
        graph.append(f"[vj]{s.hw.filter_tail()}[v]")      # hand the joined frames to the chip
    args = [*hw_global(s.hw), *args, "-filter_complex", ";".join(graph), "-map", "[v]"]
    args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if with_audio else []
    args += [*h264_codec(s.hw, s.crf, s.preset, pix_fmt=True), str(out)]
    reason = (translate("tasks", "The clips do not match, so they are re-encoded to the first "
                                 "clip's size and frame rate ({0}×{1}, {2} fps).") if diff else
              translate("tasks", "The clips are re-encoded as asked, at the first clip's size "
                                 "and frame rate ({0}×{1}, {2} fps)."))
    notes = [reason.format(w, h, fps)]
    notes += diff
    notes += hw_note(s.hw)
    if not with_audio:
        notes.append(translate("tasks", "At least one clip has no sound, so the result is silent."))
    return Plan([Job(args, [out], total, label)], notes)
