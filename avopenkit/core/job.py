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
    # Result folders to create just before the job starts (image sequences). Created by the
    # runner only after it has checked that the result does not already exist.
    make_dirs: list[Path] = field(default_factory=list)


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


def split_command_line(text: str) -> list[str]:
    """A typed command as an argument list, program name included. No shell is involved:
    quotes group words and nothing else ($VAR, `cmd`, ;, | and > are plain text)."""
    argv = shlex.split(text, posix=sys.platform != "win32")
    if sys.platform == "win32":
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in argv]
    if not argv:
        raise ValueError("empty command")
    return argv


def parse_command_line(text: str) -> list[str]:
    """Inverse of command_line(): the arguments without the program name."""
    return split_command_line(text)[1:]


class CommandError(Exception):
    """A hand-edited command cannot be run. `code` says why; the window words the message."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def guess_output(args: list[str], cwd: Path | None) -> Path | None:
    """FFmpeg's output is its last argument, unless that is an option, `-` or an input."""
    last = args[-1]
    if last.startswith("-") or (len(args) >= 2 and args[-2] == "-i"):
        return None
    path = Path(last)
    return path if path.is_absolute() or cwd is None else cwd / path


def edited_plan(text: str, original: Plan | None) -> Plan:
    """Turn commands edited by hand (one per line) into a Plan that runs them as typed (F2).

    Still enforced: the program is always FFmpeg, started without a shell; -y and -n are
    removed so that replacing a file stays a question the window asks; and the result may not
    be one of the command's own inputs (F3).
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise CommandError("empty")
    same_shape = original is not None and len(lines) == len(original.jobs)
    jobs = []
    for i, line in enumerate(lines):
        try:
            argv = split_command_line(line)
        except ValueError as e:
            raise CommandError("syntax", str(e)) from e
        if Path(argv[0]).name.lower() not in ("ffmpeg", "ffmpeg.exe"):
            raise CommandError("program", argv[0])
        args = [a for a in argv[1:] if a not in ("-y", "-n")]
        if not args:
            raise CommandError("empty")
        base = original.jobs[i] if same_shape else None
        cwd = base.cwd if base else None
        out = guess_output(args, cwd)
        inputs = [Path(args[k + 1]) for k, a in enumerate(args[:-1]) if a == "-i"]
        if out is not None and any(_same_file(out, p if p.is_absolute() or cwd is None else cwd / p)
                                   for p in inputs):
            raise CommandError("over_input", str(out))
        jobs.append(Job(args, [out] if out is not None else [],
                        base.duration if base else None, base.label if base else "",
                        cwd, edited=True, make_dirs=list(base.make_dirs) if base else []))
    return Plan(jobs, [], dict(original.write_files) if original else {},
                list(original.copy_files) if original else [])
