# avOpenKit

Guided tasks for everyday video and audio jobs, built on FFmpeg. You pick a file, answer a few
plain questions, **see the exact FFmpeg command that will run**, and get a new file. Your
original is never overwritten.

It is made for visual artists: you see a thumbnail of your file, a filmstrip of its frames with
the part you have chosen lit up, and a coloured note that says at a glance whether your picture
keeps its quality.

![The avOpenKit window](docs/img/window.png)

avOpenKit is not a video editor: there is no timeline and no project file. It covers the small
jobs in between a converter and an editor.

**Status: early release (0.2.0).** Downloads for Linux and Windows are on the
[releases page](https://github.com/rajivtctech/avOpenKit/releases). The Windows build is new: it
is built and self-tested in a Windows 11 virtual machine, but has had far less use than the
Linux one. English only for now.

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
| Crop to a shape | Square, 4:5 or 9:16 for sharing, with a picture showing what will be kept. |
| Image sequence | A video into numbered pictures, or numbered pictures into a video. |
| Contact sheet | Frames from across a video, laid out as one picture. |
| Change speed | Time-lapse and slow motion, with the sound keeping its pitch. |
| Export for editing | ProRes in a MOV file, for handing work to an editor. |

**Expert mode** adds codec-level options to every task (quality, encoder speed, audio bitrate
and others) and lets you edit the command by hand before it runs. In simple mode those options
are hidden and sensible defaults are used.

Jobs can be **queued** and run one after another while you prepare the next, and a task's
settings can be saved as a named **preset** and reused.

Trim and Make a GIF have a preview with a scrub bar, so the start and end can be picked by
looking. Before running, each task says in plain words what will happen — for example, that a fast trim
will really start at the keyframe before the point you chose.

Rest the mouse on any part of the command to see what that part does, in plain words.

**Settings** (Tools menu) chooses the language and, if you want, a different FFmpeg to use. It
also offers **hardware encoding** when your graphics chip can do it; avOpenKit checks that the
encoder really works on your computer before offering it, and it is off unless you turn it on.
**About** (Help menu) shows exactly which FFmpeg is in use, its build configuration and licence.
The program is prepared for eleven languages; a language appears in the chooser once its
translation has been completed and checked. At present only English is available.

## Download

| System | File | Notes |
|---|---|---|
| Linux, 64-bit, Ubuntu 22.04 or newer | `avOpenKit-linux-x86_64` | One file. Needs FFmpeg 6.0 or newer installed. `chmod +x` it, then run it. |
| Windows 10 / 11, 64-bit | `avOpenKit-windows-x64.zip` | Extract the folder, run `avOpenKit.exe`. FFmpeg is included. |

The released files are built on the developer's machine with the scripts described below, and
published with `packaging/release_local.sh`. [GitHub Actions](.github/workflows/build.yml)
builds and tests both from this repository on every push, as an independent check. What is inside them, and under which licences, is listed
in [THIRD-PARTY-NOTICES.md](packaging/THIRD-PARTY-NOTICES.md).

## Run from source (Linux)

Needs Python 3.10 or newer and FFmpeg 6.0 or newer (`sudo apt install ffmpeg`).

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m avopenkit            # or: .venv/bin/python -m avopenkit some-video.mp4
```

## Build the single-file program (Linux)

```
packaging/build_linux.sh          # makes dist/avOpenKit and runs its self-test
dist/avOpenKit                    # start it
dist/avOpenKit --self-test FILE   # check a build: FFmpeg found, window built, preview plays
```

The binary carries Python and Qt with it, but not FFmpeg: it uses the `ffmpeg` and `ffprobe`
installed on the computer. A binary runs only on systems whose C library is at least as new as
the one it was built on, so one built on Ubuntu 26.04 will not start on older distributions.

To get a file that runs on Ubuntu 22.04 and newer whatever this machine runs, build it in an
Ubuntu 22.04 container instead:

```
packaging/build_linux_container.sh   # makes dist/avOpenKit-linux-x86_64
```

This needs `podman` (`sudo apt install podman`; no root is needed to run it). The first run
makes the build image from [packaging/Containerfile](packaging/Containerfile), about 1 GB,
which is the only step that uses the network. Each build then runs with the network off: it
runs the tests, builds the program, self-tests it inside the container and again on this
machine.

## Build the Windows download on this machine

```
packaging/build_windows_vm.sh     # makes dist/avOpenKit-windows-x64.zip
```

PyInstaller cannot build a Windows program from Linux, so this runs the build inside a Windows
virtual machine on the same computer (VMware Workstation, a VM at `~/vmware/Windows11-Pro`). It
stages the source, FFmpeg and the Python packages, starts the VM without a window, builds,
runs the packaged program's self-test there, and brings back the zip and the logs. After the
first run, which caches its downloads, it needs no network.

## Publish a release

```
packaging/release_local.sh        # needs both downloads in dist/ and the tag's commit pushed
```

It checks that both files in `dist/` report the version in `avopenkit/__init__.py`, adds the
User Guide, the FFmpeg source archive, the notices and checksums, and creates the GitHub
release `v<version>` from them. GitHub Actions also builds the two downloads on every push;
it publishes a release only when run by hand with "publish" ticked.

## Tests

```
.venv/bin/python -m pytest
```

The tests generate their own clips, run every task through the real FFmpeg and check the results
with `ffprobe`. They also drive the window without a display.

## Documents

- **User Guide** — from first day to expert: [A4 PDF](docs/avOpenKit-User-Guide.pdf),
  [A5 PDF](docs/avOpenKit-User-Guide-A5.pdf), [source](docs/USER_GUIDE.md); editable ODT copies
  are beside them in `docs/`.

- [SPECIFICATIONS.md](SPECIFICATIONS.md) — what the program must do, and the decisions behind it.
- [DESIGN.md](DESIGN.md) — how it is built, with the trial results the design rests on.

## Licence

avOpenKit is free software under the GNU General Public License, version 3 — see
[LICENSE](LICENSE). It uses PyQt6 (GPL v3) and Qt (LGPL v3), and runs the separate `ffmpeg` and
`ffprobe` programs.

avOpenKit uses FFmpeg but is not affiliated with or endorsed by the FFmpeg project. FFmpeg is a
trademark of Fabrice Bellard.

Copyright © 2026 Rajiv Tyagi, T&C Technology.
