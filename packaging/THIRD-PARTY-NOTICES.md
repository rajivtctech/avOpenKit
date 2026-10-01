# Third-party software supplied with avOpenKit

avOpenKit itself is free software under the GNU General Public License, version 3 (see
`LICENSE`). Its source code is at <https://github.com/rajivtctech/avOpenKit>.

## FFmpeg (Windows download only)

The Windows download contains `ffmpeg.exe` and `ffprobe.exe` in its `ffmpeg` folder. avOpenKit
runs them as separate programs; they are not part of avOpenKit's own code. You may replace them
with another FFmpeg: put it in a folder of its own and choose that folder in Settings.

| | |
|---|---|
| What | FFmpeg 9.0.2, "essentials" build for 64-bit Windows |
| Built by | www.gyan.dev — downloaded from <https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2> |
| Licence | GNU General Public License, version 3 — the text is in `ffmpeg/LICENSE` |
| Build configuration | In `ffmpeg/README.txt`, as supplied by the builder |
| Source code | FFmpeg at commit `946fcce07b6dcd0331c8cc609192aeff5e1924f8` (release 9.0.2). The complete archive of that commit is attached to every avOpenKit release as `ffmpeg-9.0.2-source.tar.gz`, beside the downloads. |

This FFmpeg build also contains other free-software libraries, listed under "External
libraries" in `ffmpeg/README.txt` — among them x264 and x265 (GPL), libvpx, libopus, libmp3lame
and libass. Their source is published by their own projects. avOpenKit's releases host the
FFmpeg source itself; they do not host a copy of each of those libraries' sources.

avOpenKit uses FFmpeg but is not affiliated with or endorsed by the FFmpeg project. FFmpeg is a
trademark of Fabrice Bellard.

The Linux download does not contain FFmpeg. It uses the `ffmpeg` and `ffprobe` installed on the
computer.

## Qt and PyQt6

Both downloads contain Qt (GNU Lesser General Public License, version 3) and PyQt6 (GNU General
Public License, version 3), and with Qt the media libraries it uses for the preview — FFmpeg
libraries built by the Qt project without the GPL parts (LGPL). Source: <https://www.qt.io> and
<https://www.riverbankcomputing.com/software/pyqt/>.

## Python

Both downloads contain the Python interpreter and standard library (Python Software Foundation
License). Source: <https://www.python.org>.

## Patents

Some audio and video formats, including H.264, H.265 and AAC, are covered by patents in some
countries. The licences above grant no patent rights. Whether a patent licence is needed for
your use is for you to determine.
