"""Run jobs. ProgressParser and run_blocking need no Qt; JobRunner is the QProcess version."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import Tools
from .job import Job, Plan, full_args


class ProgressParser:
    """Turns FFmpeg's `-progress` key=value stream into one dict per progress block."""

    def __init__(self) -> None:
        self._buf = ""
        self._cur: dict[str, str] = {}

    def feed(self, text: str) -> list[dict[str, str]]:
        self._buf += text
        *lines, self._buf = self._buf.split("\n")
        blocks = []
        for line in lines:
            key, sep, value = line.strip().partition("=")
            if not sep:
                continue
            self._cur[key] = value.strip()
            if key == "progress":
                blocks.append(self._cur)
                self._cur = {}
        return blocks


def fraction(block: dict[str, str], duration: float | None) -> float | None:
    """How far a job is, 0..1, or None when it cannot be known."""
    if block.get("progress") == "end":
        return 1.0
    try:
        done = int(block["out_time_us"]) / 1_000_000
    except (KeyError, ValueError):
        return None
    if not duration or duration <= 0:
        return None
    return max(0.0, min(1.0, done / duration))


def prepare(plan: Plan) -> None:
    """Create the support files a plan needs before its jobs run."""
    for path, text in plan.write_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for src, dst in plan.copy_files:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def existing_outputs(job: Job) -> list[Path]:
    return [Path(p) for p in job.outputs if Path(p).exists()]


def exists_message(paths: list[Path]) -> str:
    return "".join(f"{p}: already exists and was not replaced.\n" for p in paths)


REFUSED = "already exists. Exiting"   # FFmpeg's -n message; its exit status is still 0


def remove_outputs(job: Job) -> None:
    """Delete a job's partial output. Only ever called for files this run was allowed to write."""
    for p in job.outputs:
        try:
            Path(p).unlink()
        except OSError:
            pass


@dataclass
class RunResult:
    ok: bool
    returncode: int
    log: str


def run_blocking(job: Job, tools: Tools, on_progress=None, overwrite: bool = False) -> RunResult:
    """Run one job and wait. Used by the tests and anywhere without an event loop.

    FFmpeg's own -n exits with status 0 when the output exists, which would look like success,
    so an existing output is refused here before FFmpeg starts - and is never deleted.
    """
    if not overwrite and (taken := existing_outputs(job)):
        return RunResult(False, -1, exists_message(taken))
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [tools.ffmpeg, *full_args(job, overwrite)], cwd=job.cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", **kwargs)
    log: list[str] = []
    reader = threading.Thread(target=lambda: log.extend(proc.stderr), daemon=True)
    reader.start()
    parser = ProgressParser()
    for line in proc.stdout:
        for block in parser.feed(line):
            if on_progress:
                on_progress(fraction(block, job.duration), block)
    rc = proc.wait()
    reader.join()
    text = "".join(log)
    if rc == 0 and REFUSED in text:
        # An output this module did not know about (a hand-edited command) already existed.
        return RunResult(False, rc, text)
    if rc != 0:
        remove_outputs(job)
    return RunResult(rc == 0, rc, text)


def run_plan_blocking(plan: Plan, tools: Tools, overwrite: bool = False) -> RunResult:
    prepare(plan)
    result = RunResult(True, 0, "")
    logs = []
    for job in plan.jobs:
        result = run_blocking(job, tools, overwrite=overwrite)
        logs.append(result.log)
        if not result.ok:
            break
    return RunResult(result.ok, result.returncode, "".join(logs))


try:
    from PyQt6.QtCore import QObject, QProcess, pyqtSignal
except ImportError:  # the Qt runner is optional for non-GUI use
    QObject = None

if QObject is not None:

    class JobRunner(QObject):
        """Runs a plan's jobs one after another without blocking the window (spec N4)."""

        progress = pyqtSignal(float, dict)   # overall 0..1 (or -1 when unknown), last block
        log = pyqtSignal(str)
        job_started = pyqtSignal(int, int)   # index, total
        finished = pyqtSignal(bool, bool)    # ok, cancelled

        def __init__(self, tools: Tools, parent=None) -> None:
            super().__init__(parent)
            self._tools = tools
            self._proc: QProcess | None = None
            self._jobs: list[Job] = []
            self._index = 0
            self._started = 0   # jobs [0, _started) were started and may have written output
            self._overwrite = False
            self._cancelled = False
            self._parser = ProgressParser()
            self._tail = ""     # end of the current job's messages, to spot REFUSED

        @property
        def running(self) -> bool:
            return self._proc is not None

        def start(self, plan: Plan, overwrite: bool = False) -> None:
            if self.running:
                raise RuntimeError("a plan is already running")
            prepare(plan)
            self._jobs, self._index, self._started = list(plan.jobs), 0, 0
            self._overwrite, self._cancelled = overwrite, False
            self._start_next()

        def cancel(self) -> None:
            if self._proc is None:
                return
            self._cancelled = True
            # FFmpeg exits cleanly on SIGTERM; a Windows console program has to be killed.
            self._proc.kill() if sys.platform == "win32" else self._proc.terminate()

        def _start_next(self) -> None:
            job = self._jobs[self._index]
            if not self._overwrite and (taken := existing_outputs(job)):
                # Refused before starting; the existing file is not ours to delete.
                self.log.emit(exists_message(taken))
                self._started = self._index
                self._finish(False)
                return
            self._started = self._index + 1
            self._tail = ""
            self._parser = ProgressParser()
            p = QProcess(self)
            if job.cwd:
                p.setWorkingDirectory(str(job.cwd))
            p.readyReadStandardOutput.connect(self._on_stdout)
            p.readyReadStandardError.connect(self._on_stderr)
            p.finished.connect(self._on_finished)
            p.errorOccurred.connect(self._on_error)
            self._proc = p
            self.job_started.emit(self._index, len(self._jobs))
            p.start(self._tools.ffmpeg, full_args(job, self._overwrite))

        def _on_stdout(self) -> None:
            text = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
            for block in self._parser.feed(text):
                f = fraction(block, self._jobs[self._index].duration)
                overall = -1.0 if f is None else (self._index + f) / len(self._jobs)
                self.progress.emit(overall, block)

        def _on_stderr(self) -> None:
            text = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
            self._tail = (self._tail + text)[-4000:]
            self.log.emit(text)

        def _on_error(self, error) -> None:
            if error == QProcess.ProcessError.FailedToStart and self._proc is not None:
                self.log.emit(f"Could not start {self._tools.ffmpeg}\n")
                self._finish(False)

        def _on_finished(self, code: int, status) -> None:
            self._on_stderr()
            ok = (status == QProcess.ExitStatus.NormalExit and code == 0
                  and not self._cancelled and REFUSED not in self._tail)
            if ok and self._index + 1 < len(self._jobs):
                self._proc.deleteLater()
                self._index += 1
                self._start_next()
                return
            self._finish(ok)

        def _finish(self, ok: bool) -> None:
            if self._proc is not None:
                self._proc.deleteLater()
                self._proc = None
            if not ok:
                for job in self._jobs[: self._started]:
                    remove_outputs(job)
            self.finished.emit(ok, self._cancelled)
