"""A Job is one FFmpeg run, held as an argument list - never as a command string (spec N3)."""

from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Added by the runner to every job; shown to the user as a footnote, not in each command.
PLUMBING = ["-hide_banner", "-nostdin", "-progress", "pipe:1", "-nostats"]


@dataclass
class Job:
    args: list[str]                       # everything after the program name
    outputs: list[Path] = field(default_factory=list)
    duration: float | None = None         # expected output duration, for the progress bar
    label: str = ""
    cwd: Path | None = None
    edited: bool = False                  # the user changed the command by hand (spec F2)


@dataclass
class Plan:
    """What a task will do: the jobs, plus what must exist on disk before they run."""
    jobs: list[Job]
    notes: list[str] = field(default_factory=list)          # "what will happen", plain words
    write_files: dict[Path, str] = field(default_factory=dict)
    copy_files: list[tuple[Path, Path]] = field(default_factory=list)

    @property
    def outputs(self) -> list[Path]:
        return [p for j in self.jobs for p in j.outputs]


def full_args(job: Job, overwrite: bool = False) -> list[str]:
    return [*PLUMBING, "-y" if overwrite else "-n", *job.args]


def command_line(job: Job, program: str = "ffmpeg") -> str:
    """The command as a user would type it in a terminal on this platform."""
    argv = [program, *job.args]
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def parse_command_line(text: str) -> list[str]:
    """Inverse of command_line(), for a command edited by hand. Returns args without the program."""
    argv = shlex.split(text, posix=sys.platform != "win32")
    if sys.platform == "win32":
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in argv]
    if not argv:
        raise ValueError("empty command")
    return argv[1:]
