# avOpenKit — Specifications

Rev K · **agreed by Rajiv Tyagi, 2026-10-01** (Rev F), amended with his decisions of the same day · T&C Technology · **internal project** — costing
sheets waived

## Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2026-10-01 | First draft for review. Decisions D1–D9 in §9 are open. |
| B | 2026-10-01 | D6 decided: system FFmpeg on Linux, bundled FFmpeg on Windows. §6, §7 and new F16 updated; bundling obligations written into §7. D1–D5 and D7–D9 remain open. |
| C | 2026-10-01 | D1 decided: the product is named **avOpenKit** (was the placeholder "FFmpeg GUI"). Name checks recorded in §9. D2–D5 and D7–D9 remain open. |
| D | 2026-10-01 | Decided: internal project (D2), PyQt6 (D3), all eight tasks in version 1 (D4), Linux and Windows first (D5), interface languages (D8): English, Hindi, Spanish, French and further Indian languages. New F17 and §5a; N1 and N8 rewritten. Open: D2a licence, D7, D8a list of Indian languages, D9. |
| E | 2026-10-01 | Decided: GPL v3, public GitHub repository (D2a). Indian languages chosen by the rule "one language per differing script" (D8a); list in §5a. Open: D7, D8b (Urdu), D9 — none blocks agreement. |
| F | 2026-10-01 | **Specification agreed.** D8b decided: Urdu is not in version 1. D7 and D9 carried into design and release as planned work, not open questions. |
| G | 2026-10-01 | D9 decided after the Linux preview trial (DESIGN.md §1.1): Qt's media player for the preview, with single frames from FFmpeg as the fallback. §7 corrected: the `ffmpeg` program is not shipped on Linux, but Qt's media libraries (which include FFmpeg libraries) are shipped in packaged builds on both platforms. New F18. |
| H | 2026-10-01 | Audience stated by Rajiv: **the program serves visual artists, and its interface must be visually rich.** Visual artist added to §2; new F19 (visual feedback) and N9 (visual design). Candidate tasks for artists listed in §3 for decision. |
| I | 2026-10-01 | Decided by Rajiv: the five artist tasks are accepted (T9–T13 in §3, not yet written); the built User Guide documents are kept in the repository; downloads are published for anyone. §7 names the FFmpeg supplied with the Windows download and how each release meets its obligations. |
| J | 2026-10-01 | Tasks T9–T13 written; §3 gives what each asks and how it works. A result can now be a folder (T10), which is created only after checking that it does not exist and is never an existing one. |
| K | 2026-10-01 | Decided by Rajiv: released downloads are built on the development machine (Linux in an Ubuntu 22.04 container, Windows in the Windows 11 VM) and published from there; the GitHub Actions build is kept as an independent check on every push. §6 updated. Version 0.2.0. |

## 1. Purpose

FFmpeg can do almost anything to a video or audio file, but its command line is hard to learn,
and most people use it by copying commands they do not understand. Existing graphical tools
leave a gap: HandBrake only transcodes, and OpenShot and Shotcut are full editors with a
timeline and a project file.

**avOpenKit** covers the small everyday jobs in between. Each job is a **guided task**: the
user picks a file, answers a few plain questions, sees the exact FFmpeg command that will run,
and gets a new file. It follows the pattern of sslOpenCrypt (a GUI over the `openssl` CLI): the
real tool does the work, and the GUI builds, shows and runs the command.

It is not an editor. There is no timeline, no project file and no effects library.

## 2. Users

| User | What they need |
|---|---|
| Beginner | "Make this video small enough to send." Never sees a codec name unless they ask. |
| Regular | Trim, join, extract audio, fix rotation — quickly, without a web search each time. |
| Expert | A fast way to build a correct command, then edit it by hand before running. |
| Learner | To see which command a task produces and why, and copy it for scripts. |
| **Visual artist** — illustrator, animator, photographer, designer, film-maker | **The main audience.** To prepare their own work for showing and sending. They judge a tool by how it looks, work in picture-first programs, and want to *see* the frames and the result rather than read numbers about them. |

## 3. Guided tasks — version 1

Every task takes one or more input files and writes **new** output files. Tasks T1–T8 were
the agreed version 1 list; T9–T13, below, were added for the visual-artist audience.

| # | Task | What the user chooses | Method |
|---|---|---|---|
| T1 | **Trim** | Start and end, on a preview with a scrub bar | *Fast* (default): stream copy, no quality loss, cut lands on the nearest keyframe before the chosen start. *Exact*: re-encode, frame-accurate. The GUI states which one it is doing and what the real cut points will be. |
| T2 | **Shrink to a size** | A target size in MB, from presets or typed | Two-pass encode. Video bitrate = (target size × 8 ÷ duration) − audio bitrate, less a container-overhead margin. Resolution is stepped down when the bitrate would be too low for the source size. |
| T3 | **Convert format** | Target: MP4 (H.264 + AAC), WebM (VP9 + Opus), MKV, MOV | Stream copy when the existing codecs are legal in the target container; otherwise re-encode at a quality setting (CRF), not a bitrate. |
| T4 | **Extract audio** | Keep original / MP3 / AAC (M4A) / Opus / WAV | Stream copy when "keep original" is possible; otherwise transcode. |
| T5 | **Join clips** | Files and their order | Concat demuxer (no re-encode) when all clips match in codec, resolution, frame rate and audio layout; otherwise concat filter with re-encode to the first clip's parameters. Mismatches are listed before running. |
| T6 | **Fix rotation** | 90° left / 90° right / 180° / flip | Rotation metadata only (instant, no re-encode) by default; *bake in* option re-encodes with `transpose` for players that ignore the metadata. |
| T7 | **Make a GIF** | Section, width, frame rate | Two-step `palettegen` / `paletteuse` for correct colours. Estimated file size shown before running. |
| T8 | **Subtitles** | An `.srt` / `.ass` file; *burn in* or *add as track* | Burn in: `subtitles` filter (re-encode). Add as track: mux without re-encoding video. |

**Accepted by Rajiv on 2026-10-01, for the visual-artist audience, and written the same day:**

| # | Task | What the user chooses | Method |
|---|---|---|---|
| T9 | **Crop to a shape** | Shape (square, 4:5, 9:16) and which part to keep, shown on a picture of the video | `crop` to the largest piece of that shape; video re-encoded, sound copied. |
| T10 | **Image sequence** | A video open: picture format, and how many per second. A picture open: pictures per second | A video into a new folder of numbered pictures; or the numbered series the open picture belongs to, into an H.264 video. The direction follows the kind of file that is open. |
| T11 | **Contact sheet** | Columns, rows, width of each frame, JPEG or PNG | One seek per frame, then `tile`, so a long film costs no more than a short clip. |
| T12 | **Change speed** | Faster or slower, with or without sound | `setpts` for the picture and `atempo` for the sound, which keeps its pitch. Frames are dropped or repeated; none are interpolated. |
| T13 | **Export for editing** | ProRes Proxy, LT, 422 or HQ | `prores_ks`, 10-bit 4:2:2, uncompressed sound, in a MOV file. |

Candidates for a later version, not in version 1: crop, resize, change speed, loudness
normalisation (`loudnorm`), mute/replace audio, extract frames as images, video from an image
sequence, screen recording, batch folders.

## 4. Functional requirements

| # | Requirement |
|---|---|
| F1 | **Command preview.** Every task shows the complete FFmpeg command before it runs, updated live as options change, with a Copy button. |
| F2 | **Edit before run** (expert mode). The command can be edited by hand; an edited command is marked as such and runs as typed. |
| F3 | **Never overwrite an input.** Output goes to a new file. If the output name exists the user is asked; nothing is replaced silently. Inputs are opened read-only. |
| F4 | **Inspect first.** On loading a file the GUI runs `ffprobe` and shows duration, size, container, and each stream's codec, resolution, frame rate and bitrate, in plain words with the technical values available on demand. |
| F5 | **Progress.** A progress bar with percentage, elapsed and estimated remaining time, from FFmpeg's machine-readable `-progress` output measured against the probed duration. |
| F6 | **Cancel.** A running job can be cancelled; the partial output file is deleted. |
| F7 | **Errors in plain language.** A failed job shows a one-line explanation where the cause is recognised, and always the full FFmpeg log. |
| F8 | **Queue.** Several jobs can be queued and run one after another. Running the same task over many files (batch) is out of scope for version 1. |
| F9 | **Result.** On completion: output size against input size, and buttons to play the file and to open its folder. |
| F10 | **Presets.** A task's settings can be saved under a name and reused. Built-in size presets for T2 are editable. |
| F11 | **Drag and drop** of files onto the window and onto a task. |
| F12 | **Explain.** Each option has a short explanation; each part of the previewed command can be hovered for what that flag does. |
| F13 | **Two modes.** *Simple* hides codec-level options behind sensible defaults. *Expert* exposes them and enables F2. The mode is remembered. |
| F14 | **Hardware encoding** (optional, off by default): offered only when FFmpeg reports a working hardware encoder on this machine. |
| F15 | **FFmpeg check at start-up.** Version and available encoders are detected. A task whose encoder or filter is missing is shown disabled with the reason, not hidden. |
| F16 | **Which FFmpeg is used.** Linux: the system's `ffmpeg` / `ffprobe` found on the `PATH`; if missing or older than N2, the application says so and gives the install command instead of starting tasks. Windows: the bundled copy. On both, Settings can point to a different FFmpeg executable, and About shows the path, version and build configuration in use. |
| F17 | **Language selection.** The interface language is chosen in Settings from the list in §5a, each shown in its own script (हिन्दी, Español, Français …). On first run the application follows the system language when it is one of the supported ones, otherwise English. The choice is remembered. |
| F18 | **Preview.** Tasks that select a section (T1, T7) show a preview with a scrub bar, played by Qt's media player with sound. If Qt cannot open the file, the preview falls back automatically to single frames extracted by FFmpeg (silent, stills only) and says so. The preview never decides the result: cut points are computed from `ffprobe` data, not from what the player displays. |
| F19 | **Visual feedback.** The interface shows the picture, not only words about it: a thumbnail of the open file; a filmstrip of frames along the scrub bar, with the chosen part lit, the rest dimmed and keyframes marked; each task shown with its own drawn icon; the "what will happen" note coloured green when nothing is re-encoded, amber when something is and red when the job cannot run; the command in colour; queue states as coloured dots. Colour is never the only carrier of a meaning: each state also has words. |

## 5. Non-functional requirements

| # | Requirement |
|---|---|
| N1 | **Platforms:** Linux and Windows 10/11 at first release. Developed on Ubuntu 26.04 (Wayland); Windows builds tested in the Windows 11 VM. macOS is not in version 1. |
| N2 | **FFmpeg version:** minimum 6.0, because rotation-metadata editing (`-display_rotation`) is needed for T6. Developed against 8.0.1. |
| N3 | **No shell.** FFmpeg is started with an argument list, never through a shell, so file names with spaces, quotes or other special characters cannot alter the command. |
| N4 | **Responsive.** FFmpeg runs as a separate process; the window stays usable while a job runs. |
| N5 | **Offline.** No network access, no telemetry, no account. |
| N6 | **Settings** stored per user in the platform's standard configuration location; removable without affecting any media file. |
| N7 | **Tested command builders.** The code that turns task settings into an argument list is separate from the GUI and has unit tests; each task also has an end-to-end test on small generated sample clips. |
| N8 | **Languages:** see §5a. All interface text is translatable from the first line of code; no text is assembled from fragments in a way that fixes English word order. |
| N9 | **Visual design.** A deliberate, consistent look in the manner of picture and video tools: neutral greys that do not tint the image being judged, one accent colour for the next action, drawn icons that stay sharp at any screen density. A dark theme by default and a light one, chosen in Settings. Text meets a contrast ratio of at least 4.5 to 1 against its background in both themes, checked by test. Visual richness must not cost clarity: the plain-language notes and the visible command remain. |

## 5a. Interface languages

**Rule for Indian languages (Rajiv, 2026-10-01): one language per differing script.** A
language whose script and vocabulary are close to one already offered is not added — with Hindi
present, Marathi and Gujarati are not required.

| Language | Script | Also serves readers of |
|---|---|---|
| English | Latin | source language |
| Spanish | Latin | |
| French | Latin | |
| Hindi | Devanagari | Marathi, Gujarati (by the rule above), Nepali, Konkani |
| Bengali | Bengali–Assamese | Assamese |
| Punjabi | Gurmukhi | |
| Odia | Odia | |
| Tamil | Tamil | |
| Telugu | Telugu | |
| Kannada | Kannada | |
| Malayalam | Malayalam | |
| Urdu | Perso-Arabic, right-to-left | **not in version 1** (D8b) |

Notes on applying the rule:

- Gujarati has its own script, related to Devanagari but not the same. It is left out on
  Rajiv's instruction that it is close enough to Hindi in script and vocabulary.
- Telugu and Kannada scripts look alike but the languages are not mutually intelligible, so
  both are kept.
- That is eleven languages. Languages are released as their reviewed
  translations become ready (see Quality below); version 1 does not wait for all of them.
  English, Hindi, Spanish and French are the minimum for the first release.

Rules:

- **What is translated:** menus, task questions, option explanations (F12), plain-language error
  explanations (F7) and dialogs.
- **What stays as it is:** the FFmpeg command, FFmpeg's own log output, and codec, container and
  flag names. These are what the user would type or search for, so translating them would break
  the "learn the command" purpose.
- **Mechanism:** Qt's translation system (`.ts` source files, compiled `.qm`), one file per
  language, so a language can be added or corrected without touching code.
- **Quality:** every translation is reviewed by a fluent speaker before release. A language
  without a reviewed translation is not offered in the list.
- **Scripts and fonts:** Devanagari and other Indian scripts must display correctly on both
  platforms with fonts normally present; to be verified in testing on Ubuntu and Windows 11
  for each language added. Urdu is left out of version 1 because, being right-to-left, it
  needs the whole layout mirrored; version 1 need not be built to support mirroring.
- **User Guide language** is English for version 1 unless decided otherwise.

## 6. Architecture

| Layer | Content |
|---|---|
| GUI | PyQt6: task list, file inspector, preview with scrub bar, command console, job queue. |
| Task modules | One per task T1–T8: settings in, argument list out. No GUI code, no process handling. |
| Runner | Starts `ffmpeg` / `ffprobe`, parses `-progress` output, handles cancel, collects the log. |
| FFmpeg | The unmodified `ffmpeg` and `ffprobe` executables — the system's on Linux, bundled with the application on Windows (§7). |

This is the same split as sslOpenCrypt, and the reason is the same: the application never
re-implements media processing, so everything it does can be reproduced by the user on the
command line.

## 7. Licensing and distribution

- Application licence: **GPL v3**, public repository on GitHub, as with sslOpenCrypt and
  DigiPotLab.
- **Linux:** the `ffmpeg` and `ffprobe` programs are not shipped; the application uses the
  distribution's package.
- **Qt and its media libraries (both platforms):** packaged builds contain Qt and PyQt6, and
  with them the FFmpeg *libraries* that Qt's media player uses for the preview (F18). These are
  supplied by Qt in the PyQt6 packages, not built by us. Each release lists Qt, PyQt6 and these
  libraries with their versions and licences, and says where their source is obtained. The
  exact licence terms of the Qt-supplied FFmpeg libraries are to be read from the shipped
  package and recorded before the first release.
- **Windows:** `ffmpeg.exe` and `ffprobe.exe` are bundled. The build must be a GPL build
  (it needs `libx264`) and must **not** be a `--enable-nonfree` build, which cannot be
  redistributed. FFmpeg runs as a separate program and is not linked into the application, so
  the application's own licence is unaffected. Each Windows release must:
  1. name the exact FFmpeg version, build source and build configuration, in the release notes
     and in About;
  2. host the complete corresponding FFmpeg source archive **alongside the release downloads** —
     a link to ffmpeg.org alone is not sufficient;
  3. include the GPL licence text and a statement that the product uses FFmpeg;
  4. place no restriction on replacing the bundled FFmpeg (F16 allows it).
  The product name and logo do not use the FFmpeg name; documentation says "uses FFmpeg".
- **Patents** are outside what the licence grants: H.264, H.265 and AAC are patent-encumbered in
  some countries. Accepted for a free, open-source release; to be reviewed with legal advice
  before any paid edition.
- **The Windows build supplied** is FFmpeg 9.0.2, "essentials" build from www.gyan.dev (GPL v3
  by its README), fetched by `packaging/fetch_ffmpeg_windows.py`, which names the exact file and
  checks its SHA-256. Its source is FFmpeg commit `946fcce07b6dcd0331c8cc609192aeff5e1924f8`;
  the release workflow attaches the complete archive of that commit to every release, with
  `THIRD-PARTY-NOTICES.md`. **Limit of what is hosted:** that FFmpeg build also contains other
  libraries (x264, x265 and others, listed in its README). Their sources are published by their
  own projects and are not copied into avOpenKit's releases. Whether that is sufficient is to
  be confirmed with legal advice before any paid edition, together with the patent question.
- **Form of the downloads.** Linux: one file, without FFmpeg, built on Ubuntu 22.04 so that it
  runs on that and newer systems. Windows: a zipped folder with `avOpenKit.exe` and FFmpeg
  inside — a folder rather than one file, because a single file would unpack about 300 MB to a
  temporary folder at every start. The released files are built on the development machine (Linux in an
  Ubuntu 22.04 container, Windows in the Windows 11 VM) and published with
  `packaging/release_local.sh`; `.github/workflows/build.yml` builds and tests both on every
  push as an independent check, and publishes only when run by hand.
- Packaging: PyInstaller builds for Linux and Windows from a GitHub Actions matrix, as
  DigiPotLab does. The same two downloads can also be built on the development machine without
  GitHub: Linux in an Ubuntu 22.04 container, Windows in the Windows 11 VM (see README).
- Windows builds cannot be tested under Wine on this machine (Wine does not load Qt6); they are
  tested in the Windows 11 VM.

## 8. Deliverables

1. This specifications sheet, kept current.
2. The application, with unit and end-to-end tests.
3. A verbose **User Guide**, beginner to expert: what the program is, installing it, a first job
   step by step, each task in turn, then presets, expert mode, reading the FFmpeg log,
   troubleshooting, and a reference of every command each task can generate.
4. Release binaries for Linux and Windows; for Windows, with the FFmpeg source archive
   and notices required by §7.

Costing sheets: none — the project is internal (D2). If it gains a customer or a paid
edition, both costing sheets are added at that point.

## 9. Decisions

| # | Decision | Proposal |
|---|---|---|
| D1 | ~~Name.~~ | **Decided 2026-10-01 (Rajiv): avOpenKit** — "av" for audio/video, "Open" for the open command it shows, after sslOpenCrypt. Checked 2026-10-01: no product, GitHub repository, PyPI, npm, Snap or Flathub entry of that name, and no DNS record on .com/.org/.app/.io/.in/.dev. Not checked: trademark registers, and whether those domains are registered but parked. "OpenKit" alone is used by several unrelated projects. "ClipBench" was rejected: an existing paid video-clipping product and an FFmpeg toolbox on GitHub use it. |
| D2 | ~~Internal or customer project.~~ | **Decided 2026-10-01 (Rajiv): internal.** Costing sheets waived. |
| D2a | ~~Licence and publication.~~ | **Decided 2026-10-01 (Rajiv): GPL v3, GitHub.** |
| D3 | ~~GUI toolkit.~~ | **Decided 2026-10-01 (Rajiv): PyQt6.** |
| D4 | ~~Version 1 task list.~~ | **Decided 2026-10-01 (Rajiv): all eight tasks, T1–T8.** |
| D5 | ~~Platforms at first release.~~ | **Decided 2026-10-01 (Rajiv): Linux and Windows first.** macOS, and its FFmpeg supply, deferred. |
| D6 | ~~FFmpeg supply.~~ | **Decided 2026-10-01 (Rajiv):** system FFmpeg on Linux, bundled on Windows. See §7 and F16. |
| D7 | T2 size presets — *release task, not an open question.* | Values (e-mail, messaging apps) are taken from each service's published limit at release time and listed with source and date. |
| D8 | ~~Interface languages.~~ | **Decided 2026-10-01 (Rajiv): English, Hindi, Spanish, French and other Indian languages.** See §5a. |
| D8a | ~~Which other Indian languages.~~ | **Decided 2026-10-01 (Rajiv): one language per differing script.** Applied in §5a: Bengali, Punjabi, Odia, Tamil, Telugu, Kannada, Malayalam, in addition to Hindi. A reviewer for each is found before that language is released. |
| D8b | ~~Urdu.~~ | **Decided 2026-10-01 (Rajiv): not in version 1.** |
| D9 | ~~Preview player.~~ | **Decided 2026-10-01 (Rajiv): Qt's media player, with FFmpeg single-frame fallback.** Trials passed on Linux and in the Windows 11 VM (DESIGN.md §1.1). See F18 and §7. |

## 10. Out of scope

Timeline editing, transitions, titles and effects; live streaming; DVD/Blu-ray authoring;
downloading from websites; DRM-protected media; audio editing beyond the tasks above.
