# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec, shared by the Linux and Windows builds.

    Linux:    packaging/build_linux.sh      -> dist/avOpenKit            (one file)
    Windows:  see .github/workflows/build.yml -> dist/avOpenKit/         (a folder, zipped)

PyInstaller cannot cross-compile: each binary is built on the system it targets. A Linux binary
also needs a C library at least as new as the one it was built with.

FFmpeg (SPECIFICATIONS.md section 7):
  Linux    ffmpeg and ffprobe are NOT bundled; the program uses the ones installed.
  Windows  they ARE bundled, from packaging/ffmpeg-win/ (put there by
           packaging/fetch_ffmpeg_windows.py). Windows is a folder rather than one file because
           a single file would unpack some 300 MB to a temporary folder at every start.
Qt's own media libraries, which the preview uses, are bundled on both because they are part of Qt.
"""

import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"

# Compiled translations, when any exist (only reviewed languages are compiled).
datas = [(str(p), "avopenkit/i18n") for p in Path("avopenkit/i18n").glob("*.qm")]
binaries = []
if WINDOWS:
    ff = Path("packaging/ffmpeg-win")
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        if not (ff / name).is_file():
            raise SystemExit(f"{ff / name} is missing: run packaging/fetch_ffmpeg_windows.py first")
        binaries.append((str(ff / name), "ffmpeg"))
    datas += [(str(ff / "LICENSE"), "ffmpeg"), (str(ff / "README.txt"), "ffmpeg")]
    datas += [("packaging/THIRD-PARTY-NOTICES.md", "."), ("LICENSE", ".")]

excludes = [
    "tkinter", "pytest", "_pytest", "unittest", "pydoc",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtWebChannel",
    "PyQt6.QtWebSockets", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets", "PyQt6.QtRemoteObjects", "PyQt6.QtSpatialAudio",
    "PyQt6.QtStateMachine", "PyQt6.QtTextToSpeech", "PyQt6.QtXml", "PyQt6.QtDBus",
]

a = Analysis(
    ["packaging/avopenkit_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

if WINDOWS:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="avOpenKit", debug=False,
              strip=False, upx=False, console=False)
    COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="avOpenKit")
else:
    # upx=False: UPX-packed libraries have failed to load before; not worth the saving.
    EXE(pyz, a.scripts, a.binaries, a.datas, [], name="avOpenKit", debug=False, strip=False,
        upx=False, console=False)
