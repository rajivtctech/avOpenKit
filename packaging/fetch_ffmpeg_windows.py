#!/usr/bin/env python3
"""Fetch the FFmpeg that is supplied with the Windows build, into packaging/ffmpeg-win/.

One exact build is named here and checked by its SHA-256, so every Windows release contains a
known FFmpeg whose source and licence can be stated (SPECIFICATIONS.md section 7):

    FFmpeg 9.0.2 "essentials" build for 64-bit Windows from www.gyan.dev
    licence: GPL v3 (its README)
    source:  https://github.com/FFmpeg/FFmpeg at commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8

To change the bundled FFmpeg, change the four constants together, and the same commit in
.github/workflows/build.yml (the source archive attached to each release) and in
packaging/THIRD-PARTY-NOTICES.md.
"""

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "9.0.2"
URL = ("https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/"
       "ffmpeg-9.0.2-essentials_build.zip")
SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
SOURCE_COMMIT = "946fcce07b6dcd0331c8cc609192aeff5e1924f8"
WANTED = {"bin/ffmpeg.exe": "ffmpeg.exe", "bin/ffprobe.exe": "ffprobe.exe",
          "LICENSE": "LICENSE", "README.txt": "README.txt"}


def main() -> int:
    out = Path(__file__).resolve().parent / "ffmpeg-win"
    out.mkdir(exist_ok=True)
    print("downloading", URL)
    data = urllib.request.urlopen(URL).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        print(f"SHA-256 mismatch: got {digest}, expected {SHA256}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():
            inner = member.split("/", 1)[1] if "/" in member else member
            if inner in WANTED:
                (out / WANTED[inner]).write_bytes(z.read(member))
                print("  ", WANTED[inner])
    missing = [n for n in WANTED.values() if not (out / n).is_file()]
    if missing:
        print("not found in the archive:", missing, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
