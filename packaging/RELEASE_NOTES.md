avOpenKit does small, everyday jobs on video and audio files — trim, shrink to a size, convert,
extract audio, join, fix rotation, make a GIF, add subtitles — and shows you the exact FFmpeg
command it runs. Your original file is never overwritten.

**This is an early release.** Please read "What to know" below before relying on it.

## Downloads

| File | For | How to use it |
|---|---|---|
| `avOpenKit-linux-x86_64` | Linux, 64-bit, Ubuntu 22.04 or newer and equivalents | Needs FFmpeg 6.0 or newer installed (`sudo apt install ffmpeg` on Ubuntu 24.04 or newer). Then `chmod +x avOpenKit-linux-x86_64` and run it. |
| `avOpenKit-windows-x64.zip` | Windows 10 and 11, 64-bit | Extract the whole folder, then run `avOpenKit.exe` inside it. FFmpeg is included. |
| `avOpenKit-User-Guide.pdf`, `avOpenKit-User-Guide-A5.pdf` | Everyone | The User Guide, A4 and A5. |
| `ffmpeg-9.0.2-source.tar.gz` | — | The source code of the FFmpeg inside the Windows download. |
| `THIRD-PARTY-NOTICES.md` | — | What else is inside the downloads, and under which licences. |
| `SHA256SUMS.txt` | — | Checksums of the files above. |

## What to know

- **Windows may warn you.** The program is not signed with a publisher's certificate, so
  Windows may show "Windows protected your PC". Choose "More info", then "Run anyway".
- **The Windows version is new.** It is built and self-tested automatically, but it has had
  far less use than the Linux version.
- **English only** for now.
- **Ubuntu 22.04's own FFmpeg is too old** (4.4). On that system, install a newer FFmpeg and
  point avOpenKit to it in Settings.

avOpenKit is free software under the GNU General Public License, version 3. It uses FFmpeg but
is not affiliated with or endorsed by the FFmpeg project.
