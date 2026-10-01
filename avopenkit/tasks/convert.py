"""T3 Convert format: change the container, re-encoding only the streams that need it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import TaskError, check_output, need_encoder, suggest, translate

ID = "convert"

# Codecs each target container can hold by stream copy.
COPY_VIDEO = {
    "mp4": {"h264", "hevc", "mpeg4", "av1"},
    "mov": {"h264", "hevc", "mpeg4", "prores", "mjpeg"},
    "webm": {"vp8", "vp9", "av1"},
}
COPY_AUDIO = {
    "mp4": {"aac", "mp3", "ac3", "alac"},
    "mov": {"aac", "mp3", "ac3", "alac", "pcm_s16le"},
    "webm": {"opus", "vorbis"},
}
CRF = {  # quality name -> (libx264 crf, libvpx-vp9 crf)
    "high": (18, 24), "medium": (23, 32), "small": (28, 40),
}


@dataclass
class Settings:
    target: str = "mp4"        # mp4, webm, mkv, mov
    quality: str = "medium"    # used only for streams that have to be re-encoded
    output: Path | None = None


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "converted", "." + s.target)


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    if s.target not in ("mp4", "webm", "mkv", "mov"):
        raise TaskError(translate("tasks", "Unknown target format."))
    if s.quality not in CRF:
        raise TaskError(translate("tasks", "Unknown quality setting."))
    src = str(media.path)

    if s.target == "mkv":
        args = ["-i", src, "-map", "0", "-c", "copy", str(out)]
        notes = [translate("tasks", "Copies everything into an MKV file without re-encoding: "
                                    "no quality loss.")]
        return Plan([Job(args, [out], media.duration, translate("tasks", "Convert"))], notes)

    args = ["-i", src]
    notes = []
    x264_crf, vp9_crf = CRF[s.quality]
    if media.video:
        args += ["-map", "0:v:0"]
        if media.video.codec in COPY_VIDEO[s.target]:
            args += ["-c:v", "copy"]
            notes.append(translate("tasks", "Video ({0}) is copied without re-encoding.")
                         .format(media.video.codec))
        elif s.target == "webm":
            need_encoder(tools, "libvpx-vp9")
            args += ["-c:v", "libvpx-vp9", "-crf", str(vp9_crf), "-b:v", "0"]
            notes.append(translate("tasks", "Video is re-encoded from {0} to VP9. This is slow.")
                         .format(media.video.codec))
        else:
            need_encoder(tools, "libx264")
            args += ["-c:v", "libx264", "-crf", str(x264_crf), "-preset", "medium",
                     "-pix_fmt", "yuv420p"]
            notes.append(translate("tasks", "Video is re-encoded from {0} to H.264.")
                         .format(media.video.codec))
    if media.audio:
        args += ["-map", "0:a"]
        if all(a.codec in COPY_AUDIO[s.target] for a in media.streams if a.kind == "audio"):
            args += ["-c:a", "copy"]
            notes.append(translate("tasks", "Audio ({0}) is copied without re-encoding.")
                         .format(media.audio.codec))
        elif s.target == "webm":
            need_encoder(tools, "libopus")
            args += ["-c:a", "libopus", "-b:a", "128k"]
            notes.append(translate("tasks", "Audio is re-encoded to Opus."))
        else:
            args += ["-c:a", "aac", "-b:a", "160k"]
            notes.append(translate("tasks", "Audio is re-encoded to AAC."))
    if not media.video and not media.audio:
        raise TaskError(translate("tasks", "This file has no audio or video to convert."))
    if media.has_subtitles:
        notes.append(translate("tasks", "Subtitle tracks are not carried over to this format; "
                                        "choose MKV to keep them."))
    if s.target in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    args.append(str(out))
    return Plan([Job(args, [out], media.duration, translate("tasks", "Convert"))], notes)
