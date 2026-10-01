# avOpenKit

Guided tasks for everyday video and audio jobs, built on FFmpeg. You pick a file, answer a few
plain questions, **see the exact FFmpeg command that will run**, and get a new file. Your
original is never overwritten.

avOpenKit is not a video editor: there is no timeline and no project file. It covers the small
jobs in between a converter and an editor.

**Status: early development (0.1.0).** The eight tasks work on Linux from source. There are no
packaged downloads yet, and Windows has not been tested beyond a preview-player trial.

## Tasks

| Task | What it does |
|---|---|
| Trim | Keep the part between two points. Fast (no quality loss, starts on a keyframe) or exact (re-encodes). |
| Shrink to a size | Two-pass encode to fit a file size you choose. |
| Convert format | MP4, WebM, MKV or MOV; copies audio and video untouched when the new type can hold them. |
| Extract audio | Keep the original audio, or save as MP3, M4A, Opus or WAV. |
| Join clips | Without re-encoding when the clips match; otherwise re-encoded to the first clip's size. |
| Fix rotation | Change the stored rotation instantly, or bake it in for players that ignore it. |
| Make a GIF | A section of video as a looping GIF with a proper colour palette. |
| Subtitles | Burn into the picture, or add as a track that can be switched on and off. |

Trim and Make a GIF have a preview with a scrub bar, so the start and end can be picked by
looking. Before running, each task says in plain words what will happen — for example, that a fast trim
will really start at the keyframe before the point you chose.

## Run from source (Linux)

Needs Python 3.10 or newer and FFmpeg 6.0 or newer (`sudo apt install ffmpeg`).

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m avopenkit            # or: .venv/bin/python -m avopenkit some-video.mp4
```

## Tests

```
.venv/bin/python -m pytest
```

The tests generate their own clips, run every task through the real FFmpeg and check the results
with `ffprobe`. They also drive the window without a display.

## Documents

- [SPECIFICATIONS.md](SPECIFICATIONS.md) — what the program must do, and the decisions behind it.
- [DESIGN.md](DESIGN.md) — how it is built, with the trial results the design rests on.

## Licence

avOpenKit is free software under the GNU General Public License, version 3 — see
[LICENSE](LICENSE). It uses PyQt6 (GPL v3) and Qt (LGPL v3), and runs the separate `ffmpeg` and
`ffprobe` programs.

avOpenKit uses FFmpeg but is not affiliated with or endorsed by the FFmpeg project. FFmpeg is a
trademark of Fabrice Bellard.

Copyright © 2026 Rajiv Tyagi, T&C Technology.
