"""Say in plain words what each part of an FFmpeg command does (spec F12).

explain_command() takes the command text as it is shown - generated or edited by hand - and
returns one Part per word, giving the character range it occupies and its explanation. An
option and its value share one explanation, so hovering either shows the same text.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QCoreApplication


def translate(context: str, text: str) -> str:
    """Spelled out with its context at every call so that pylupdate6 finds the strings."""
    return QCoreApplication.translate(context, text)


@dataclass(frozen=True)
class Part:
    start: int      # character offsets in the whole text
    end: int
    text: str       # the explanation
    known: bool = True


# ---------------------------------------------------------------- splitting into words

def token_spans(line: str, posix: bool | None = None) -> list[tuple[int, int, str]]:
    """Words of one command line as (start, end, value), following the quoting rules the
    command box uses: quotes group words; in POSIX style a backslash escapes one character."""
    posix = sys.platform != "win32" if posix is None else posix
    out, i, n = [], 0, len(line)
    while i < n:
        if line[i].isspace():
            i += 1
            continue
        start, value, quote = i, [], None
        while i < n and (quote or not line[i].isspace()):
            ch = line[i]
            if quote:
                if ch == quote:
                    quote = None
                elif posix and quote == '"' and ch == "\\" and i + 1 < n and line[i + 1] in '"\\$`':
                    i += 1
                    value.append(line[i])
                else:
                    value.append(ch)
            elif ch == '"' or (posix and ch == "'"):
                quote = ch
            elif posix and ch == "\\" and i + 1 < n:
                i += 1
                value.append(line[i])
            else:
                value.append(ch)
            i += 1
        out.append((start, i, "".join(value)))
    return out


# ---------------------------------------------------------------- vocabulary

def codec_name(codec: str) -> str:
    names = {
        "libx264": "H.264", "libx265": "H.265 (HEVC)", "libvpx-vp9": "VP9", "libvpx": "VP8",
        "libsvtav1": "AV1", "aac": "AAC",
        "h264_vaapi": translate("explain", "H.264, made by the graphics chip through VAAPI"),
        "h264_qsv": translate("explain", "H.264, made by the graphics chip through Intel Quick Sync"),
        "h264_nvenc": translate("explain", "H.264, made by the NVIDIA graphics chip"),
        "h264_amf": translate("explain", "H.264, made by the AMD graphics chip"), "libopus": "Opus", "libmp3lame": "MP3",
        "libvorbis": "Vorbis", "flac": "FLAC", "ac3": "AC-3", "prores_ks": "ProRes",
        "pcm_s24le": translate("explain", "uncompressed 24-bit audio"),
        "pcm_s16le": translate("explain", "uncompressed 16-bit audio"),
        "mov_text": translate("explain", "MP4 text subtitles"),
        "webvtt": "WebVTT", "srt": "SubRip", "subrip": "SubRip", "gif": "GIF", "ppm": "PPM",
    }
    return names.get(codec, codec)


def stream_kind(letter: str, plural: bool = False) -> str:
    return {
        ("v", False): translate("explain", "video"), ("a", False): translate("explain", "audio"), ("s", False): translate("explain", "subtitle"),
        ("v", True): translate("explain", "video streams"), ("a", True): translate("explain", "audio streams"),
        ("s", True): translate("explain", "subtitle streams"),
    }.get((letter, plural), letter)


def explain_map(value: str) -> str:
    if value.startswith("[") and value.endswith("]"):
        return translate("explain", "Use the stream labelled {0} that the filters above produce.").format(value)
    m = re.fullmatch(r"(\d+)(?::([vas])(?::(\d+))?)?(?::(\d+))?(\?)?", value)
    if not m:
        return translate("explain", "Choose which streams go into the result: {0}.").format(value)
    inp = int(m.group(1)) + 1
    kind, index, bare_index, optional = m.group(2), m.group(3), m.group(4), m.group(5)
    if kind is None and bare_index is None:
        text = translate("explain", "Use every stream of input {0}.").format(inp)
    elif kind is None:
        text = translate("explain", "Use stream number {0} of input {1}.").format(int(bare_index) + 1, inp)
    elif index is None:
        text = translate("explain", "Use all {0} of input {1}.").format(stream_kind(kind, True), inp)
    else:
        text = translate("explain", "Use {0} stream number {1} of input {2}.").format(
            stream_kind(kind), int(index) + 1, inp)
    if optional:
        text += " " + translate("explain", "The ? means: carry on without complaint if there are none.")
    return text


def explain_codec(value: str, spec: str) -> str:
    which = {"v": translate("explain", "the video"), "a": translate("explain", "the audio"), "s": translate("explain", "the subtitles")}.get(
        spec[:1], translate("explain", "every stream"))
    if value == "copy":
        return translate("explain", "Copy {0} as it is, without re-encoding: fast, and no quality is lost.").format(which)
    return translate("explain", "Encode {0} as {1} (encoder: {2}).").format(which, codec_name(value), value)


def _explain_crop(args: str) -> str:
    parts = args.split(":")
    if len(parts) == 4:
        return translate("explain", "cut the picture down to {0}×{1}, starting {2} pixels from "
                                    "the left and {3} from the top").format(*parts)
    return translate("explain", "cut the picture down to {0}").format(args)


FILTERS = {
    "scale": lambda a: (
        translate("explain", "round the picture's width and height down to even numbers, "
                             "which H.264 needs") if "trunc(" in a else
        translate("explain", "resize the picture to {0} (-1 or -2 keeps the proportions; -2 also "
                             "keeps the size even)").format("×".join(a.split(":")[:2]))),
    "setpts": lambda a: translate("explain", "change when each frame is shown ({0}): dividing the "
                                  "time by a number plays the video that many times faster")
                        .format(a),
    "atempo": lambda a: translate("explain", "play the sound {0} times as fast without changing "
                                  "its pitch").format(a),
    "trim": lambda a: translate("explain", "take only the first frame"),
    "tile": lambda a: translate("explain", "lay the frames out in a grid of {0}, with a gap "
                                "between and around them").format(a.split(":")[0]),
    "fps": lambda a: translate("explain", "change the frame rate to {0} frames per second").format(a),
    "transpose": lambda a: {"1": translate("explain", "turn the picture 90° to the right"),
                            "2": translate("explain", "turn the picture 90° to the left")}.get(
                                a, translate("explain", "turn the picture (mode {0})").format(a)),
    "hflip": lambda a: translate("explain", "mirror the picture left to right"),
    "vflip": lambda a: translate("explain", "mirror the picture top to bottom"),
    "subtitles": lambda a: translate("explain", "draw the subtitles from {0} into the picture").format(a),
    "split": lambda a: translate("explain", "make two copies of the video, one to study and one to convert"),
    "palettegen": lambda a: translate("explain", "work out the best 256 colours for this clip"),
    "paletteuse": lambda a: translate("explain", "convert the picture to those 256 colours") + (
        " (" + a + ")" if a else ""),
    "pad": lambda a: translate("explain", "add borders so the picture fills the frame"),
    "setsar": lambda a: translate("explain", "mark the pixels as square"),
    "aformat": lambda a: translate("explain", "convert the sound to a common sample rate and channel layout"),
    "concat": lambda a: translate("explain", "join the clips end to end"),
    "crop": lambda a: _explain_crop(a),
    "format": lambda a: translate("explain", "convert the pixel format to {0}").format(a),
    "loudnorm": lambda a: translate("explain", "even out the loudness"),
    "hwupload": lambda a: translate("explain", "pass the picture to the graphics chip for encoding"),
}


def explain_filters(graph: str, heading: str) -> str:
    lines = [heading]
    for step in re.split(r"[;,]", graph):
        step = re.sub(r"\[[^\]]*\]", "", step).strip()       # drop [labels]
        if not step:
            continue
        name, _, args = step.partition("=")
        said = FILTERS[name](args) if name in FILTERS else translate("explain", "(no explanation for this filter)")
        lines.append(f"• {step}: {said}")
    return "\n".join(lines)


def _seek(value: str, state: dict) -> str:
    if state["before_input"]:
        return translate("explain", "Start at {0} seconds into the input. Written before -i, FFmpeg jumps there "
                  "quickly instead of reading everything before it.").format(value)
    return translate("explain", "Start the result at {0} seconds. Written after -i, FFmpeg reads and discards "
              "everything before that point, which is slow but exact.").format(value)


def _bitrate(value: str, spec: str) -> str:
    which = translate("explain", "audio") if spec.startswith("a") else translate("explain", "video")
    return translate("explain", "Aim for a {0} bitrate of {1}bit/s. A higher bitrate means better quality and a "
              "larger file.").format(which, value)


# name -> (takes a value, explanation(value, stream specifier, state))
OPTIONS = {
    "-i": (True, lambda v, s, st: (
        translate("explain", "Input number {0}: a numbered series of pictures, {1}. The part "
                             "beginning with % stands for the number.").format(st["inputs"], v)
        if re.search(r"%0?\d*d", v) else
        translate("explain", "Input file number {0}: {1}").format(st["inputs"], v))),
    "-ss": (True, lambda v, s, st: _seek(v, st)),
    "-to": (True, lambda v, s, st: translate("explain", "Stop at {0} seconds.").format(v)),
    "-t": (True, lambda v, s, st: translate("explain", "Take {0} seconds from the starting point.").format(v)),
    "-map": (True, lambda v, s, st: explain_map(v)),
    "-c": (True, lambda v, s, st: explain_codec(v, s)),
    "-codec": (True, lambda v, s, st: explain_codec(v, s)),
    "-vcodec": (True, lambda v, s, st: explain_codec(v, "v")),
    "-acodec": (True, lambda v, s, st: explain_codec(v, "a")),
    "-crf": (True, lambda v, s, st: translate("explain", 
        "Quality setting {0} (constant rate factor). Lower is better quality and a larger "
        "file; 18 is close to lossless to the eye, 23 is the usual default.").format(v)),
    "-preset": (True, lambda v, s, st: translate("explain", 
        "Encoder speed \"{0}\". Slower presets make a smaller file at the same quality and "
        "take longer.").format(v)),
    "-b": (True, lambda v, s, st: _bitrate(v, s)),
    "-q": (True, lambda v, s, st: (
        translate("explain", "Picture quality level {0} for JPEG: 2 is the best, larger "
                             "numbers make smaller, rougher pictures.").format(v)
        if s.startswith("v") else
        translate("explain", "Quality level {0} for the audio encoder (for MP3, lower is "
                             "better; 2 is high quality).").format(v))),
    "-framerate": (True, lambda v, s, st: translate(
        "explain", "Show the pictures that follow at {0} per second.").format(v)),
    "-start_number": (True, lambda v, s, st: translate(
        "explain", "The numbered series starts at picture number {0}.").format(v)),
    "-fps_mode": (True, lambda v, s, st: translate(
        "explain", "Keep exactly the frames the video has, without adding or dropping any.")
        if v == "passthrough" else translate("explain", "How frame timing is handled: {0}.").format(v)),
    "-pix_fmt": (True, lambda v, s, st: translate("explain", 
        "Store colour as {0}. yuv420p is the format nearly every player and phone accepts.").format(v)),
    "-pass": (True, lambda v, s, st: translate("explain", 
        "Pass {0} of a two-pass encode. Pass 1 studies the video; pass 2 uses what it learned "
        "to spend the bitrate where it is needed.").format(v)),
    "-passlogfile": (True, lambda v, s, st: translate("explain", 
        "Where the notes from pass 1 are kept for pass 2 (a temporary file).")),
    "-an": (False, lambda v, s, st: translate("explain", "Leave out the sound.")),
    "-vn": (False, lambda v, s, st: translate("explain", "Leave out the video.")),
    "-sn": (False, lambda v, s, st: translate("explain", "Leave out the subtitles.")),
    "-f": (True, lambda v, s, st: {
        "null": translate("explain", "Write no file at all (format \"null\"): the result is only measured."),
        "concat": translate("explain", "Read the next input as a list of files to play one after another."),
    }.get(v, translate("explain", "Force the file format to {0} instead of guessing it from the file name.").format(v))),
    "-safe": (True, lambda v, s, st: translate("explain", 
        "Allow the list of files to contain full paths (0 switches the safety check off).")),
    "-vf": (True, lambda v, s, st: explain_filters(v, translate("explain", "Video filters, applied in order:"))),
    "-filter:v": (True, lambda v, s, st: explain_filters(v, translate("explain", "Video filters, applied in order:"))),
    "-af": (True, lambda v, s, st: explain_filters(v, translate("explain", "Audio filters, applied in order:"))),
    "-filter_complex": (True, lambda v, s, st: explain_filters(
        v, translate("explain", "Filters that combine several inputs, applied in order:"))),
    "-movflags": (True, lambda v, s, st: translate("explain", 
        "+faststart puts the index at the start of the file, so it can begin playing before "
        "it has fully downloaded.") if "faststart" in v else translate("explain", "MP4 file options: {0}.").format(v)),
    "-avoid_negative_ts": (True, lambda v, s, st: translate("explain", 
        "Shift the timestamps so the result starts at zero, as players expect after a cut.")),
    "-display_rotation": (True, lambda v, s, st: translate("explain", 
        "Store a rotation of {0}° for players to apply (counter-clockwise; a negative number "
        "turns it right). The picture itself is not changed.").format(v)),
    "-display_hflip": (False, lambda v, s, st: translate("explain", 
        "Store an instruction for players to mirror the picture left to right.")),
    "-display_vflip": (False, lambda v, s, st: translate("explain", 
        "Store an instruction for players to mirror the picture top to bottom.")),
    "-loop": (True, lambda v, s, st: translate("explain", "Repeat the GIF for ever.") if v == "0" else
              translate("explain", "Play the GIF once and stop.") if v == "-1" else
              translate("explain", "Repeat the GIF {0} more times.").format(v)),
    "-metadata": (True, lambda v, s, st: translate("explain", "Label the stream: {0}.").format(v)),
    "-vaapi_device": (True, lambda v, s, st: translate(
        "explain", "Use the graphics chip at {0} for hardware encoding.").format(v)),
    "-qp": (True, lambda v, s, st: translate(
        "explain", "Quality setting {0} for the hardware encoder (quantiser). Lower is better "
                   "quality and a larger file.").format(v)),
    "-global_quality": (True, lambda v, s, st: translate(
        "explain", "Quality setting {0} for the hardware encoder. Lower is better quality and "
                   "a larger file.").format(v)),
    "-cq": (True, lambda v, s, st: translate(
        "explain", "Quality setting {0} for the hardware encoder. Lower is better quality and "
                   "a larger file.").format(v)),
    "-qp_i": (True, lambda v, s, st: translate(
        "explain", "Quality setting {0} for the hardware encoder's key frames.").format(v)),
    "-qp_p": (True, lambda v, s, st: translate(
        "explain", "Quality setting {0} for the hardware encoder's in-between frames.").format(v)),
    "-rc": (True, lambda v, s, st: translate(
        "explain", "How the hardware encoder controls quality: {0}.").format(v)),
    "-r": (True, lambda v, s, st: translate("explain", "Set the frame rate to {0} frames per second.").format(v)),
    "-s": (True, lambda v, s, st: translate("explain", "Set the picture size to {0}.").format(v)),
    "-ar": (True, lambda v, s, st: translate("explain", "Set the audio sample rate to {0} Hz.").format(v)),
    "-ac": (True, lambda v, s, st: translate("explain", "Set the number of audio channels to {0}.").format(v)),
    "-frames": (True, lambda v, s, st: translate("explain", "Stop after {0} frames.").format(v)),
    "-vframes": (True, lambda v, s, st: translate("explain", "Stop after {0} video frames.").format(v)),
    "-g": (True, lambda v, s, st: translate("explain", "Put a keyframe at least every {0} frames.").format(v)),
    "-tune": (True, lambda v, s, st: translate("explain", "Tune the encoder for this kind of material: {0}.").format(v)),
    "-profile": (True, lambda v, s, st: translate(
        "explain", "Which variety of the format to make: {0}. For ProRes, 0 is Proxy, 1 is LT, "
                   "2 is the standard ProRes 422 and 3 is HQ.").format(v)),
    "-level": (True, lambda v, s, st: translate("explain", "Limit the encoder to level {0}, for older players.").format(v)),
    "-threads": (True, lambda v, s, st: translate("explain", "Use {0} processor threads.").format(v)),
    "-shortest": (False, lambda v, s, st: translate("explain", "Stop when the shortest input ends.")),
    "-y": (False, lambda v, s, st: translate("explain", 
        "Replace the result file without asking. avOpenKit ignores this and asks you itself.")),
    "-n": (False, lambda v, s, st: translate("explain", 
        "Never replace an existing file. avOpenKit always adds this itself.")),
    "-hide_banner": (False, lambda v, s, st: translate("explain", "Do not print FFmpeg's version details.")),
    "-nostdin": (False, lambda v, s, st: translate("explain", "Do not wait for keys typed at the keyboard.")),
    "-nostats": (False, lambda v, s, st: translate("explain", "Do not print the running status line.")),
    "-progress": (True, lambda v, s, st: translate("explain", "Report progress in a form avOpenKit can read.")),
}


def plumbing_explanation() -> str:
    """What the arguments avOpenKit adds to every command are for."""
    state = {"inputs": 0, "before_input": True}
    lines = [f"{name}: {OPTIONS[name][1]('pipe:1', '', state)}"
             for name in ("-hide_banner", "-nostdin", "-progress", "-nostats", "-n")]
    return "\n".join(lines)


# ---------------------------------------------------------------- the command

def _is_option(word: str) -> bool:
    return len(word) > 1 and word[0] == "-" and not re.fullmatch(r"-\d+(\.\d+)?", word)


def explain_line(line: str, offset: int = 0, posix: bool | None = None) -> list[Part]:
    words = token_spans(line, posix)
    if not words:
        return []
    parts: list[Part] = []

    def add(index: int, text: str, known: bool = True) -> None:
        start, end, _ = words[index]
        parts.append(Part(offset + start, offset + end, text, known))

    program = Path(words[0][2]).name.lower()
    if program in ("ffmpeg", "ffmpeg.exe"):
        add(0, translate("explain", "The FFmpeg program. Everything after it tells FFmpeg what to read, what to "
                  "do, and what to write."))
    else:
        add(0, translate("explain", "avOpenKit only runs FFmpeg; a command must start with ffmpeg."), False)

    state = {"inputs": 0, "before_input": True}
    i, last = 1, len(words) - 1
    while i <= last:
        word = words[i][2]
        # Options written before an -i belong to that input; after the last -i, to the result.
        state["before_input"] = any(words[k][2] == "-i" for k in range(i + 1, last + 1))
        if _is_option(word):
            name, _, spec = word.partition(":")
            entry = OPTIONS.get(word) or OPTIONS.get(name)
            if entry is None:
                # Unknown option: assume it takes a value when the next word is not an option
                # and is not the final word (which is the result file).
                takes = i + 1 < last and not _is_option(words[i + 1][2])
                text, known = translate("explain", "An FFmpeg option avOpenKit has no explanation for. FFmpeg's "
                                 "own documentation describes it: ffmpeg.org/ffmpeg-all.html"), False
            else:
                takes, known = entry[0] and i + 1 <= last, True
                if name == "-i":
                    state["inputs"] += 1
                text = entry[1](words[i + 1][2] if takes else "", spec, state)
            add(i, text, known)
            if takes:
                add(i + 1, text, known)
                i += 1
        elif word == "-":
            add(i, translate("explain", "No result file: the output is discarded."))
        elif i == last and re.search(r"%0?\d*d", word):
            add(i, translate("explain", "The results: a numbered series of files, {0}. The part "
                                        "beginning with % is replaced by each picture's number.")
                .format(word))
        elif i == last:
            add(i, translate("explain", "The result file: {0}. FFmpeg chooses the file format from its ending.")
                .format(word))
        else:
            add(i, translate("explain", "A file name where FFmpeg expects none here; FFmpeg will treat it as an "
                      "extra result file."), False)
        i += 1
    return parts


def explain_command(text: str, posix: bool | None = None) -> list[Part]:
    """Parts for a whole command box: one command per line."""
    parts, offset = [], 0
    for line in text.split("\n"):
        parts += explain_line(line, offset, posix)
        offset += len(line) + 1
    return parts


def explanation_at(text: str, position: int, posix: bool | None = None) -> str | None:
    for part in explain_command(text, posix):
        if part.start <= position < part.end:
            return part.text
    return None
