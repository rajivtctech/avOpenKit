# avOpenKit — Design

Draft 4 · 2026-10-01 · implements SPECIFICATIONS.md Rev G · first code increment written, see §7

Everything marked *tested* was run on this machine (Ubuntu 26.04, FFmpeg 8.0.1, Python 3.14.4,
PyQt6 6.11.0 from pip in `.venv`) by the scripts in `trials/`. Anything not marked is a proposal.

## 1. Trial results

### 1.1 Preview player (spec D9) — `trials/preview_trial.py`

Test clip: 20 s, 1280×720, 30 fps H.264, a keyframe every 2 s.

| Approach | Seek-to-frame time | Accuracy | Notes |
|---|---|---|---|
| A. Qt Multimedia (`QMediaPlayer` + `QVideoSink`) | Linux 10–41 ms · Windows 33–91 ms | within one frame (0 to −33 ms), identical on both | Real playback with sound. Loads in 8 ms (Linux), 13 ms (Windows). |
| B. One frame from `ffmpeg -ss T -i … -frames:v 1` | Linux 63–98 ms · Windows 86–140 ms | exact frame | Stills only, no sound. No extra dependency. |

Linux: this machine, system FFmpeg 8.0.1. Windows: the Windows 11 Pro VM (build 26200.8037,
4 vCPU), Python 3.14.8, the same PyQt6 6.11.0 packages, FFmpeg 9.0.2 "essentials" build from
gyan.dev; log kept in `trials/preview_trial_windows11.log`. In the VM Qt's hardware decoding
(`d3d11`) failed to initialise and Qt fell back to software decoding by itself, so the Windows
figures are software-decode figures; a real Windows PC with a GPU was not tested.

Both are fast enough for a scrub bar on this clip, on both platforms. **Not yet tested:** 4K or
long-GOP HEVC sources, files the Qt backend cannot open, and a Windows machine with working
hardware decoding.

**Finding that affects the specification.** The PyQt6 wheels carry their own FFmpeg libraries
for Qt Multimedia (`libavcodec.so.61` etc.). Read from the installed packages: the libraries are
FFmpeg n7.1.5, configured without `--enable-gpl` and without `--enable-nonfree` (so an LGPL
build); the `PyQt6-Qt6` package declares LGPL v3; `PyQt6` itself declares GPL-3.0-only, which
is why avOpenKit must be GPL v3. A packaged
avOpenKit that uses Qt Multimedia therefore ships FFmpeg *libraries* on Linux as well as
Windows. Spec §7 currently says FFmpeg is not shipped on Linux. These libraries arrive with Qt
and carry the same kind of obligation as Qt itself, which every packaged build already ships.

**Decided (Rajiv, 2026-10-01):** use A for the preview, with B as the automatic fallback when
Qt cannot open a file. Spec Rev G records this (F18) and corrects §7: the `ffmpeg` *program* is
not shipped on Linux, but Qt's media libraries are, on both platforms.

Design consequences:

- `ui/preview.py` has one interface (`load`, `seek`, `play`, `pause`, `position_changed`) and two
  back ends: `QtPreview` and `FrameGrabPreview`. The panel does not know which one is active
  except to show a "stills only" note.
- Fallback triggers: `QMediaPlayer` reports an error, reports no video frames within a time
  limit after load, or reports a duration that disagrees with `ffprobe` by more than a second.
- The player is for looking, not measuring. Cut points, keyframe snapping and durations come
  from `probe.py`.

### 1.2 Task commands — `trials/commands_trial.sh`

Every command below ran and its output was checked with `ffprobe`. The input file name
contained a space and a quote, passed as one argument (spec N3).

| Task | Command (arguments after `ffmpeg -nostdin`) | Result |
|---|---|---|
| T1 fast | `-ss S -to E -i IN -map 0 -c copy -avoid_negative_ts make_zero OUT` | Asked 3.5–9.0 s; got 7.14 s, because the copy starts at the keyframe at 2.0 s. |
| T1 exact | `-ss S -to E -i IN -c:v libx264 -crf 18 -c:a aac OUT` | 5.500 s exactly. |
| T2 | pass 1: `-i IN -c:v libx264 -b:v Vk -pass 1 -passlogfile P -an -f null NUL`; pass 2: `… -pass 2 -passlogfile P -c:a aac -b:a Ak OUT` | Target 2000 kB → 1930 kB, with V = (size × 8 × 0.97 ÷ duration) − A. |
| T3 copy | `-i IN -map 0 -c copy OUT.mkv` | H.264/AAC carried over. |
| T3 re-encode | `-i IN -c:v libvpx-vp9 -crf Q -b:v 0 -c:a libopus OUT.webm` | VP9/Opus. |
| T4 keep | `-i IN -vn -c:a copy OUT.m4a` | AAC, full length. |
| T4 MP3 | `-i IN -vn -c:a libmp3lame -q:a 2 OUT.mp3` | MP3. |
| T5 | `-f concat -safe 0 -i LIST -map 0 -c copy OUT` | 20 s + 6 s → 26.02 s. LIST quotes each path. |
| T6 metadata | `-display_rotation A -i IN -map 0 -c copy OUT` | A = 90, −90, 180 read back by `ffprobe` as 90, −90, −180. |
| T6 bake in | `-i IN -vf transpose=1 -c:v libx264 -c:a copy OUT` | 1280×720 → 720×1280. |
| T7 | `-ss S -t D -i IN -vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" OUT.gif` | 3 s → 36 frames, 607 kB. One command, no temporary palette file. |
| T8 burn in | `-i IN -vf subtitles=SUBS -c:v libx264 -c:a copy OUT` | Rendered (Latin and Devanagari lines in the test file; not inspected by eye). |
| T8 track | `-i IN -i SUBS -map 0 -map 1 -c copy -c:s mov_text OUT.mp4` | `mov_text` stream present. |
| F5 | `-progress pipe:1 -nostats` | Keys include `out_time_us`, `total_size`, `speed`, `progress=continue/end`. |

Consequences for the design:

- **T1 fast must show the real cut.** Before running, read the keyframe times with `ffprobe`
  and show "will start at 2.0 s (nearest keyframe before 3.5 s)". Offer snapping the handle to
  keyframes.
- **T2 lands a few per cent under target**, which is the safe side. The 3 % margin stays
  adjustable until tested on longer and lower-bitrate material.
- **T6 directions, measured** with a clip carrying a marker in its top-left corner, decoded
  after each operation: `-display_rotation -90` and `transpose=1` turn the picture right
  (clockwise); `-display_rotation 90` and `transpose=2` turn it left. The metadata value is
  **absolute**, not added to what the file already has (applying 90 twice still gives 90), so
  the task adds the existing rotation itself. `-display_hflip` / `-display_vflip` mirror
  without re-encoding. All of this is now covered by tests.
- **`ffmpeg -n` exits with status 0 when the output already exists.** A runner that trusted the
  exit status would report success with nothing written. The runner therefore refuses an
  existing output before starting FFmpeg, and on failure deletes only files this run created.
- **T8 burn-in** output has to be looked at, per script, before each language is released.

## 2. Structure

```
avopenkit/
  __main__.py            start-up, language, FFmpeg check (F15, F16)
  core/
    probe.py             ffprobe -> MediaInfo (streams, duration, keyframes)
    ffmpeg.py            locate ffmpeg/ffprobe, version, encoder and filter lists
    job.py               Job (argument lists, output paths, expected duration), JobQueue
    runner.py            QProcess wrapper: -progress parsing, cancel, log capture
    errors.py            log patterns -> plain-language explanations (F7)
    presets.py           named settings per task (F10)
  tasks/
    base.py              Task: settings dataclass -> list[Job]; validation; "what will happen"
    trim.py  shrink.py  convert.py  audio.py  join.py  rotate.py  gif.py  subtitles.py
  ui/
    main_window.py  task_list.py  inspector.py  preview.py  console.py  queue_panel.py
    panels/              one panel per task
  i18n/                  avopenkit_<lang>.ts and compiled .qm
tests/
  unit/                  settings -> argument list, no FFmpeg needed
  e2e/                   run FFmpeg on generated clips, check with ffprobe
trials/                  the two scripts behind section 1
```

Rules that keep the layers apart (spec N7):

- `tasks/` imports nothing from `ui/` and starts no process. A task turns a settings object and
  a `MediaInfo` into one or more `Job`s. Two-pass (T2) is one task producing two jobs.
- A `Job` holds the **argument list**, never a command string. The console (F1) renders the
  list as a quoted, copyable command; the runner passes the list to `QProcess` unchanged (N3).
- An edited command (F2) is parsed back into an argument list with shell-style quoting rules
  and marked "edited"; it is never handed to a shell.
- `runner.py` always adds `-nostdin -progress pipe:1 -nostats`, and `-n` (never overwrite)
  unless the user confirmed replacing a file (F3). On cancel or failure the partial output is
  deleted (F6).

## 3. Window

```
+----------------+------------------------------------------+
| Tasks          |  [ file inspector: plain summary ▸ details ]
|  Trim          |------------------------------------------|
|  Shrink        |  preview + scrub bar   |  task questions |
|  Convert       |                        |  (simple/expert)|
|  Extract audio |------------------------------------------|
|  Join          |  what will happen: "copy, no quality loss,
|  Rotate        |   starts at 2.0 s"                        |
|  GIF           |------------------------------------------|
|  Subtitles     |  $ ffmpeg -ss 3.5 -to 9 -i …   [Copy][Run]|
|----------------|------------------------------------------|
| Queue (3)      |  progress ▓▓▓▓▓░░ 62 %  0:14 left [Cancel]|
+----------------+------------------------------------------+
```

The command console is always visible; it is the product's signature feature, as in
sslOpenCrypt. The "what will happen" line states, before running, whether the job copies or
re-encodes and anything that will differ from what was asked.

## 4. Languages (spec §5a)

- All user-visible text goes through `tr()`; sentences are whole strings with placeholders.
- `QTranslator` loads `avopenkit_<lang>.qm`; switching language takes effect on restart.
- The language list is built from the `.qm` files present, so an unreviewed language is left
  out simply by not shipping its file.
- FFmpeg commands, logs and codec names are never passed through `tr()`.

## 5. Testing

- **Unit:** each task's settings → expected argument list, including file names with spaces,
  quotes, non-Latin characters and a leading dash.
- **End to end:** `trials/commands_trial.sh` grows into pytest cases — generate clips, run the
  job through the real runner, assert on `ffprobe` output (duration, codecs, size, rotation).
- **Windows:** the same suite in the Windows 11 VM against the bundled FFmpeg.

## 6. Still to do in design

1. ~~Windows half of the preview trial~~ — done, section 1.1.
2. ~~Licence terms of the FFmpeg libraries inside the PyQt6 packages~~ — recorded in section 1.1;
   the release notice wording remains to be written.
3. ~~T6 direction mapping~~ — measured, section 1.2.
4. Choice of the Windows FFmpeg build to bundle (spec §7). The gyan.dev 9.0.2 essentials build
   worked in the trial; whether it can meet the source-hosting obligation is not yet checked.
5. Preview trial on 4K and HEVC sources.

## 7. Code status — first increment (0.1.0)

Written and tested (89 tests: unit, real FFmpeg runs checked with `ffprobe`, and the window
driven without a display):

- `core/`: FFmpeg detection (F15, F16 path search), probing with keyframe times, job and plan
  model, progress parsing, blocking and `QProcess` runners with cancel (F5, F6), plain-language
  error explanations (F7).
- `tasks/`: all eight tasks T1–T8 as settings → argument list, with the "what will happen" notes.
- `ui/`: main window with task list, file inspector (F4), one form per task, result path that
  never defaults to an input (F3), live command console with Copy (F1), progress, cancel,
  result line with Play and Open folder (F9), drag and drop (F11).
- All interface text goes through Qt's translation calls; `pylupdate6` extracts 180 strings.

Not yet written: preview player (F18), edit-before-run and simple/expert modes (F2, F13), job
queue (F8), presets (F10), hover explanations of command parts (F12), hardware encoding (F14),
Settings and About (F16, F17), translations, Windows packaging with bundled FFmpeg, User Guide.

Known limits of this increment: probing reads keyframe times on the window's thread, which
will pause the window on very long files; the Windows build has not been run.
