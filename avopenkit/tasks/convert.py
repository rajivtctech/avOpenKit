"""T3 Convert format: change the container, re-encoding only the streams that need it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.job import Job, Plan
from ..core.probe import MediaInfo
from .base import (TaskError, check_encode, check_kbps, check_output, h264_codec, h264_encoder,
                   hw_global, hw_note, need_encoder, suggest, translate, video_filter)

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
    # Expert options.
    crf: int | None = None     # overrides the quality name
    preset: str = "medium"
    audio_kbps: int | None = None
    reencode: bool = False     # re-encode even what could be copied
    hw: object = None          # a working HwEncoder to use for H.264 instead of libx264


def suggest_output(media: MediaInfo, s: Settings) -> Path:
    return suggest(media.path, "converted", "." + s.target)


def plan(s: Settings, media: MediaInfo, tools=None, workdir: Path | None = None) -> Plan:
    out = check_output(s.output, [media.path])
    if s.target not in ("mp4", "webm", "mkv", "mov"):
        raise TaskError(translate("tasks", "Unknown target format."))
    if s.quality not in CRF:
        raise TaskError(translate("tasks", "Unknown quality setting."))
    check_encode(s.crf, s.preset, 63 if s.target == "webm" else 51)
    check_kbps(s.audio_kbps)
    src = str(media.path)
    container = "mp4" if s.target == "mkv" else s.target      # MKV re-encodes like MP4
    copy_video = set() if s.reencode else COPY_VIDEO[container]
    copy_audio = set() if s.reencode else COPY_AUDIO[container]

    if s.target == "mkv" and not s.reencode:
        args = ["-i", src, "-map", "0", "-c", "copy", str(out)]
        notes = [translate("tasks", "Copies everything into an MKV file without re-encoding: "
                                    "no quality loss.")]
        return Plan([Job(args, [out], media.duration, translate("tasks", "Convert"))], notes)

    args = ["-i", src]
    notes = []
    x264_crf, vp9_crf = CRF[s.quality]
    if s.crf is not None:
        x264_crf = vp9_crf = s.crf
    if media.video:
        args += ["-map", "0:v:0"]
        if media.video.codec in copy_video:
            args += ["-c:v", "copy"]
            notes.append(translate("tasks", "Video ({0}) is copied without re-encoding.")
                         .format(media.video.codec))
        elif s.target == "webm":
            need_encoder(tools, "libvpx-vp9")
            args += ["-c:v", "libvpx-vp9", "-crf", str(vp9_crf), "-b:v", "0"]
            notes.append(translate("tasks", "Video is re-encoded from {0} to VP9. This is slow.")
                         .format(media.video.codec))
        else:
            need_encoder(tools, h264_encoder(s.hw))
            args = [*hw_global(s.hw), *args, *video_filter(s.hw),
                    *h264_codec(s.hw, x264_crf, s.preset, pix_fmt=True)]
            notes.append(translate("tasks", "Video is re-encoded from {0} to H.264.")
                         .format(media.video.codec))
            notes += hw_note(s.hw)
    if media.audio:
        args += ["-map", "0:a"]
        if all(a.codec in copy_audio for a in media.streams if a.kind == "audio"):
            args += ["-c:a", "copy"]
            notes.append(translate("tasks", "Audio ({0}) is copied without re-encoding.")
                         .format(media.audio.codec))
        elif s.target == "webm":
            need_encoder(tools, "libopus")
            args += ["-c:a", "libopus", "-b:a", f"{s.audio_kbps or 128}k"]
            notes.append(translate("tasks", "Audio is re-encoded to Opus."))
        else:
            args += ["-c:a", "aac", "-b:a", f"{s.audio_kbps or 160}k"]
            notes.append(translate("tasks", "Audio is re-encoded to AAC."))
    if not media.video and not media.audio:
        raise TaskError(translate("tasks", "This file has no audio or video to convert."))
    if media.has_subtitles and s.target == "mkv":
        args += ["-map", "0:s?", "-c:s", "copy"]
    elif media.has_subtitles:
        notes.append(translate("tasks", "Subtitle tracks are not carried over to this format; "
                                        "choose MKV to keep them."))
    if s.target in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    args.append(str(out))
    return Plan([Job(args, [out], media.duration, translate("tasks", "Convert"))], notes)
