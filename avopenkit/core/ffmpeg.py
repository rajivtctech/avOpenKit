"""Locate ffmpeg/ffprobe and find out what the installed build can do (spec F15, F16)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_VERSION = (6, 0)  # -display_rotation, needed by the rotate task (spec N2)


class FFmpegNotFound(Exception):
    pass


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str
    version_text: str
    version: tuple[int, ...] | None  # None for builds with no numeric version (git snapshots)
    configuration: str
    encoders: frozenset[str]
    filters: frozenset[str]

    @property
    def too_old(self) -> bool:
        return self.version is not None and self.version < MIN_VERSION

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def has_filter(self, name: str) -> bool:
        return name in self.filters


def run_quiet(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run that never opens a console window on Windows."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kwargs)


def parse_version(banner: str) -> tuple[str, tuple[int, ...] | None]:
    """'ffmpeg version 8.0.1-3ubuntu2 Copyright ...' -> ('8.0.1-3ubuntu2', (8, 0, 1))."""
    m = re.search(r"^ff\w+ version (\S+)", banner, re.M)
    if not m:
        return "", None
    text = m.group(1)
    num = re.match(r"n?(\d+(?:\.\d+)*)", text)
    return text, (tuple(int(p) for p in num.group(1).split(".")) if num else None)


def parse_configuration(banner: str) -> str:
    m = re.search(r"^\s*configuration:\s*(.*)$", banner, re.M)
    return m.group(1).strip() if m else ""


def parse_encoders(output: str) -> frozenset[str]:
    return frozenset(re.findall(r"^ [VAS][A-Z.]{5} +(\S+)", output, re.M)) - {"="}


def parse_filters(output: str) -> frozenset[str]:
    return frozenset(re.findall(r"^ [A-Z.]{2,3} +(\S+) +\S+->\S+", output, re.M))


def build_licence(configuration: str) -> str:
    """The licence an FFmpeg build is under, from its configure flags (FFmpeg's LICENSE.md):
    LGPL v2.1+ by default; --enable-gpl makes it GPL; --enable-version3 raises either to
    version 3; --enable-nonfree makes the build unredistributable."""
    flags = set(configuration.split())
    if "--enable-nonfree" in flags:
        return "nonfree"
    gpl, v3 = "--enable-gpl" in flags, "--enable-version3" in flags
    if gpl:
        return "GPL v3 or later" if v3 else "GPL v2 or later"
    return "LGPL v3 or later" if v3 else "LGPL v2.1 or later"


def uses_override(tools: "Tools", override: str | None) -> bool:
    """True when the FFmpeg in use is the one the user pointed to in Settings."""
    if not override:
        return False
    p = Path(override)
    folder = p.parent if p.is_file() else p
    try:
        return Path(tools.ffmpeg).resolve().parent == folder.resolve()
    except OSError:
        return False


def is_bundled(tools: "Tools") -> bool:
    b = bundled_dir()
    return b is not None and Path(tools.ffmpeg).resolve().parent == b.resolve()


def bundled_dir() -> Path | None:
    """Folder holding the FFmpeg shipped with a packaged Windows build, if there is one."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    d = base / "ffmpeg"
    return d if d.is_dir() else None


def locate(override: str | None = None) -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) paths: the user's override, then the bundled copy, then PATH."""
    exe = ".exe" if sys.platform == "win32" else ""
    candidates: list[Path] = []
    if override:
        p = Path(override)
        candidates.append(p.parent if p.is_file() else p)
    if (b := bundled_dir()) is not None:
        candidates.append(b)
    for d in candidates:
        ff, fp = d / f"ffmpeg{exe}", d / f"ffprobe{exe}"
        if ff.is_file() and fp.is_file():
            return str(ff), str(fp)
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        return ff, fp
    raise FFmpegNotFound("ffmpeg and ffprobe were not found")


def detect(override: str | None = None) -> Tools:
    ffmpeg, ffprobe = locate(override)
    banner = run_quiet([ffmpeg, "-version"]).stdout
    text, version = parse_version(banner)
    return Tools(
        ffmpeg=ffmpeg, ffprobe=ffprobe, version_text=text, version=version,
        configuration=parse_configuration(banner),
        encoders=parse_encoders(run_quiet([ffmpeg, "-hide_banner", "-encoders"]).stdout),
        filters=parse_filters(run_quiet([ffmpeg, "-hide_banner", "-filters"]).stdout),
    )
