# avOpenKit — Design

Draft 12 · 2026-10-01 · implements SPECIFICATIONS.md Rev I · first code increment written, see §7

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

### 1.3 Qt player hang when stopped with sound attached — `trials/player_stop_hang.py`

Found while testing the preview: `QMediaPlayer.stop()` occasionally never returns, freezing the
window. The main thread blocks inside Qt with Qt's audio-renderer thread still alive.

| Condition | Result |
|---|---|
| Audio output attached (muted or not), load → pause → stop | about 1 batch of 150 cycles in 4 hung |
| No audio output attached, same sequence | no hang in over 1000 cycles |
| Application tests before the fix | 1 run in 6 hung, in `PreviewWidget.unload()` |
| Application tests after the fix | 12 consecutive runs clean |

Seen with PyQt6 6.11.0 / PyQt6-Qt6 6.11.2 on Ubuntu 26.04, PulseAudio on PipeWire 1.6.2. Not
tested: other Qt versions, Windows. Changing Qt's audio back end (`QT_AUDIO_BACKEND`) gave no
clear difference in the runs made.

**Fix in the code:** the audio output is attached only when Play is first pressed. Scrubbing and
"Start here / End here", which is most of what the preview is for, never have one attached.

**Residual risk:** after Play has been pressed once, a later stop (opening another file, closing
the window) goes through the same Qt code and could hang, at roughly the rate above. Not yet
mitigated. Options if it shows up in use: make the preview silent, or move the player into a
helper process that can be killed.

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
  and marked "edited"; it is never handed to a shell, so `;`, `|`, `>`, `$VAR` and backticks
  are plain text. Three things stay enforced on an edited command: every line must start with
  `ffmpeg` (no other program is run); `-y` and `-n` are removed, so replacing a file remains a
  question the window asks; and the result may not be one of the command's own inputs.
  FFmpeg's output is taken to be the last argument. If a command has outputs the window does
  not know about and one exists, FFmpeg's own `-n` refuses it — the runner recognises that
  message and reports a failure, because FFmpeg's exit status is 0 in that case.
- **Hardware encoding (F14).** `core/hardware.py`. FFmpeg lists every encoder it was built
  with, whether or not the machine has the chip and driver: on the development laptop it
  lists VAAPI, Quick Sync and NVENC, and only VAAPI works. An encoder is therefore offered
  only after a short test encode succeeds, and the test uses the same arguments a real job
  would. The choice is one setting (Settings → Hardware encoding, off by default) applied by
  the five tasks that re-encode to H.264: exact trim, convert, join, bake-in rotation and
  burned-in subtitles. Shrink always uses libx264, whose two-pass mode hits a target size
  more accurately. Decoding and filtering stay in software; frames are handed to the chip at
  the end of the filter chain. If the saved encoder stops working, the window falls back to
  the standard encoder at start-up and says so.
  **Tested here: VAAPI only**, with real jobs for all five tasks. The Quick Sync, NVENC and
  AMF arguments have never run on working hardware; the test encode means a wrong argument
  would show up as "not offered", not as a failed job, but the quality they give is unchecked.
  The hardware quality number is the CRF passed straight through, which is only roughly the
  same quality.
- **Explanations (F12).** `core/explain.py` splits the command text into words by the same
  quoting rules the command box uses, and returns an explanation for each word's character
  range; an option and its value share one explanation. It works on the text as shown, so a
  hand-edited command is explained too, and an option it does not know is said to be unknown
  rather than guessed at. `ui/console.py` shows the explanation for the word under the mouse.
  A test walks every task, in both modes and every two-way choice, and fails if any word of a
  generated command lacks an explanation; another fails if any option in any form lacks one.
- **Queue (F8).** Every run goes through `core/queue.py`. Run adds the current job and starts
  the queue; Add to queue adds it without starting. The form stays usable while a job runs.
  A failed job does not stop the queue; Cancel stops the running job and leaves the rest
  waiting. Each queued job has its own work folder (`job0`, `job1`, …), so two shrink jobs
  never share a pass-log file, and the folder is removed when the job ends. A result name
  claimed by a waiting or running job cannot be claimed by another, and suggested names skip
  claimed ones. Whether to replace an existing file is asked when the job is queued, not hours
  later when it runs.
- **Presets (F10).** One JSON object per task in `QSettings`. A preset stores the form, not the
  file: start and end times, the subtitle file, the clips to join and the result name are left
  out. Expert values are stored only when saved in expert mode. The built-in shrink presets
  are sizes only (10, 25, 50, 100 MB) and become ordinary, editable presets once copied to the
  user's settings; presets named after services wait for spec D7.
- **Modes (F13).** Each task's settings carry the codec-level values (CRF, encoder speed, audio
  bitrate, and a few per task) with defaults equal to what simple mode has always produced.
  A panel passes its expert widgets on **only in expert mode**, so a value left in a hidden
  widget cannot change a simple-mode result; a test checks that switching to expert mode
  without touching anything leaves every task's command unchanged. The mode is kept in
  `QSettings`.
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

## 3a. Look (spec F19, N9)

The audience is visual artists, so the look is designed, not left to the toolkit's defaults.

- `ui/theme.py`: two palettes (dark, the default, and light) and one stylesheet built from
  whichever is in use, on Qt's Fusion style so it looks the same on every desktop. Neutral
  greys, one accent colour (coral) for the next action, green and amber for "kept" and
  "re-encoded". A test checks every text/background pair in both themes for a contrast ratio
  of 4.5 or better; it caught the light theme's first accent colour at 3.6.
- `ui/icons.py`: 31 line icons drawn for this program, kept as SVG text and rendered in the
  theme's colours at any size. No icon files and no third-party icon set.
- `ui/widgets.py`:
  - `Timeline` replaces the plain slider in the preview: twelve frames from the file as a
    filmstrip, the chosen part lit and the rest dimmed, a green tick at every keyframe, a
    playhead. It is still a `QSlider` underneath, so values, keyboard steps and the rest of the
    preview code are unchanged; click or drag anywhere goes to that moment.
  - `ThumbLoader` fetches frames one at a time with short FFmpeg runs that each seek straight
    to their moment, without blocking the window; used for the filmstrip and the file's
    thumbnail.
  - `TaskDelegate` draws each task as a card with its icon, name and description.
  - `NotesBox` is the "what will happen" box; `plan_kind()` reads the plan's arguments to
    colour it green (everything copied), amber (something re-encoded) or red (cannot run).
  - `CommandHighlighter` colours the command. It changes only formats, never text; because
    re-colouring still raises the editor's change signal, the window now treats a change as a
    hand edit only when the words differ from what it last set.
  - `FlowLayout` wraps the file's fact labels, so they never force the window wider.
- **A stylesheet trap worth recording:** a rule of the form `QFrame#card QWidget { background:
  transparent }` outranks a button's own rule and silently removed the background from every
  button and field inside a card. The general `QWidget` rule now sets no background and no such
  descendant rules exist.
- The appearance choice takes effect at the next start, like the language.
- Not done: the look has been judged from off-screen renders only, not on a real screen; no
  artist has seen it.

## 4. Languages (spec §5a)

- All user-visible text goes through `tr()`; sentences are whole strings with placeholders.
  `pylupdate6` currently extracts 432 strings. It finds a string only when the call is
  written as `self.tr(...)` or `translate("context", ...)`; a module-level helper named `tr`
  is silently skipped.
- `avopenkit/languages.py` holds the eleven languages of the specification, each named in its
  own script, and loads `avopenkit_<code>.qm`. Switching language takes effect on restart.
- The language list is built from the `.qm` files present. `tools/update_translations.sh`
  creates or refreshes a language's `.ts` file and compiles a `.qm` **only** for codes listed
  in `avopenkit/i18n/reviewed.txt`, so an unreviewed language cannot appear in the chooser.
  Today no translation exists and the chooser offers English only.
- The saved choice is either a language or "follow this computer's language". On first run the
  system language is used when it is available, otherwise English (F17).
- FFmpeg commands, logs and codec names are never passed through `tr()`; a test checks that
  the command stays unchanged with a translation loaded.
- **Finding:** Qt ships its own translations (standard dialog buttons such as OK and Cancel,
  the file dialogs) for Spanish and French but for none of the Indian languages in the list.
  For those, the texts of Qt's standard buttons and dialogs will have to be supplied in our
  own translation files; not done yet.
- On this machine `/usr/bin/lrelease` is a chooser that looks for Qt 5 and fails; the script
  and tests call `/usr/lib/qt6/bin/lrelease` (package `qt6-l10n-tools`).

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

Written and tested (261 tests: unit, real FFmpeg runs checked with `ffprobe`, and the window
and preview driven without a display):

- `core/`: FFmpeg detection (F15, F16 path search), probing with keyframe times, job and plan
  model, progress parsing, blocking and `QProcess` runners with cancel (F5, F6), plain-language
  error explanations (F7).
- `tasks/`: all eight tasks T1–T8 as settings → argument list, with the "what will happen" notes.
- `ui/`: main window with task list, file inspector (F4), one form per task, result path that
  never defaults to an input (F3), live command console with Copy (F1), progress, cancel,
  result line with Play and Open folder (F9), drag and drop (F11).
- `ui/preview.py` (F18): scrub bar, Play/Pause, Mute, Qt player with automatic fallback to
  FFmpeg stills (on a player error, no picture within 4 s, or a length that disagrees with
  `ffprobe` by more than 1 s). Shown for Trim and Make a GIF, with "Start here" / "End here"
  buttons; typing a time shows that moment.
- Simple and expert modes (F13) with expert options on every task, remembered between runs;
  editing the command before it runs (F2), with Reset to return to the form's command.
- Job queue (F8) with its list, Start, Remove and Clear finished; presets (F10) with save,
  apply and delete per task.
- Settings (Tools menu): language chooser (F17) and a different FFmpeg folder (F16), which is
  checked before it is saved — both programs present, answers as FFmpeg, version 6.0 or newer —
  and takes effect at once. About (Help menu): version, licence, source link, the FFmpeg in
  use with its path, version, build configuration and the licence that configuration implies,
  and the Qt, PyQt6 and Python versions (spec §7 notices).
- Hover explanations (F12): every part of the command, the arguments avOpenKit adds, and
  every option in every form.
- Hardware encoding (F14), offered in Settings only for encoders that pass a test encode.
- The designed look (F19, N9): theme, icons, filmstrip timeline, task cards, coloured note box,
  command colouring, file thumbnail and fact labels, dark and light themes.
- All interface text goes through Qt's translation calls; `pylupdate6` extracts 180 strings.

- User Guide (spec §8): `docs/USER_GUIDE.md`, built by `docs/build_guide.sh` into A4 and A5,
  each as a styled PDF and an editable ODT. Part 7.3, the reference of every command each task
  generates, is produced by the task modules (`tools/make_guide_assets.py reference`), and the
  screenshots are taken from the running program (`… screenshots`). `tests/test_guide.py` fails
  if that reference is out of date, if a button or label the guide quotes does not exist in the
  program, or if a message the guide explains is not one the program produces.

- Single-file Linux program: `avopenkit.spec` and `packaging/build_linux.sh` (PyInstaller, own
  build environment `.venv-build`) make `dist/avOpenKit`, 84 MB. `--self-test [file]` checks a
  build from the outside: FFmpeg found, window built, and the preview player delivering a
  picture, which is the part most likely to break when Qt's media plug-in is packaged. Built
  on Ubuntu 26.04 (glibc 2.43), so it will not run on older distributions; a release build
  needs an older build machine or CI runner.

- Downloads for anyone: `.github/workflows/build.yml` builds on Ubuntu 22.04 and on Windows,
  runs the tests, builds with `avopenkit.spec`, runs the packaged program's `--self-test` on a
  generated clip, and on a `v*` tag publishes a release with both downloads, the User Guide,
  the FFmpeg source archive, the notices and checksums. On Windows the self-test must also
  report that the program used its own bundled FFmpeg. The Windows tests are reported but do
  not stop the build; the self-test does.

Not yet written: the translations themselves; the five artist tasks T9–T13 (spec §3).

Found while writing the guide: re-encoding a video whose width or height is odd fails in
libx264, and no task corrects it. The guide gives the expert-mode workaround
(`-vf 'scale=trunc(iw/2)*2:trunc(ih/2)*2'`, tested); a built-in fix is not written.

Known limits: probing reads keyframe times on the window's thread, which will pause the
window on very long files; the Windows build has not been run; the preview has only been
run without a display and never on Windows, 4K or HEVC material; keyframe positions are not
marked on the scrub bar; the residual hang risk in §1.3.
