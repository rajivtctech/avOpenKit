"""The job queue (spec F8): plans wait in a list and run one after another."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from .ffmpeg import Tools
from .job import Plan
from .runner import JobRunner

WAITING, RUNNING, DONE, FAILED, CANCELLED = "waiting", "running", "done", "failed", "cancelled"
FINISHED = (DONE, FAILED, CANCELLED)


@dataclass
class QueueItem:
    id: int
    title: str
    plan: Plan
    overwrite: bool = False          # the user agreed to replace an existing result
    source_size: int = 0             # size of the input, for "the original is ..."
    workdir: Path | None = None      # this item's own temporary folder, removed when it ends
    status: str = WAITING
    progress: float = 0.0            # 0..1, or -1 when the length is unknown
    step: str = ""                   # label of the FFmpeg run in progress
    log: str = ""

    @property
    def result(self) -> Path | None:
        """The file this item made, once it is done and the file is there."""
        if self.status != DONE or not self.plan.outputs:
            return None
        out = Path(self.plan.outputs[-1])
        return out if out.exists() else None


def _resolved(path: Path) -> Path:
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


class JobQueue(QObject):
    changed = pyqtSignal()               # the list, or an item's status, changed
    progress = pyqtSignal(int, float)    # item id, overall progress
    log = pyqtSignal(int, str)           # item id, text from FFmpeg
    item_started = pyqtSignal(int)
    item_finished = pyqtSignal(int)

    def __init__(self, tools: Tools, parent=None) -> None:
        super().__init__(parent)
        self.runner = JobRunner(tools, self)
        self.items: list[QueueItem] = []
        self._next_id = 1
        self._current: QueueItem | None = None
        self._go = False                 # keep starting waiting items as each one ends
        self.runner.progress.connect(self._on_progress)
        self.runner.log.connect(self._on_log)
        self.runner.job_started.connect(self._on_job_started)
        self.runner.finished.connect(self._on_finished)

    # ------------------------------------------------------------------ the list

    @property
    def running(self) -> bool:
        return self._current is not None

    @property
    def current(self) -> QueueItem | None:
        return self._current

    def item(self, item_id: int) -> QueueItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def waiting(self) -> list[QueueItem]:
        return [i for i in self.items if i.status == WAITING]

    def claimed(self) -> set[Path]:
        """Results that waiting or running items will write; no other item may use them."""
        return {_resolved(p) for i in self.items if i.status in (WAITING, RUNNING)
                for p in i.plan.outputs}

    def add(self, title: str, plan: Plan, overwrite: bool = False, source_size: int = 0,
            workdir: Path | None = None) -> QueueItem:
        item = QueueItem(self._next_id, title, plan, overwrite, source_size, workdir)
        self._next_id += 1
        self.items.append(item)
        self.changed.emit()
        return item

    def remove(self, item_id: int) -> bool:
        item = self.item(item_id)
        if item is None or item.status == RUNNING:
            return False
        self.items.remove(item)
        self._drop_workdir(item)
        self.changed.emit()
        return True

    def clear_finished(self) -> None:
        self.items = [i for i in self.items if i.status not in FINISHED]
        self.changed.emit()

    # ------------------------------------------------------------------ running

    def start(self) -> None:
        self._go = True
        if not self.running:
            self._advance()

    def cancel(self) -> None:
        """Stop the running item and do not start the next; the rest stay waiting."""
        self._go = False
        if self.running:
            self.runner.cancel()

    def shutdown(self) -> None:
        self.cancel()
        for item in self.items:
            self._drop_workdir(item)

    def _advance(self) -> None:
        while self._go:
            item = next(iter(self.waiting()), None)
            if item is None:
                self._go = False
                return
            self._current = item
            item.status, item.progress = RUNNING, 0.0
            self.item_started.emit(item.id)
            self.changed.emit()
            try:
                self.runner.start(item.plan, item.overwrite)
                return
            except OSError as e:         # a support file could not be prepared
                item.log += f"{e}\n"
                self._end(item, FAILED)

    def _end(self, item: QueueItem, status: str) -> None:
        item.status = status
        if status == DONE:
            item.progress = 1.0
        self._drop_workdir(item)
        self._current = None
        self.item_finished.emit(item.id)
        self.changed.emit()

    def _drop_workdir(self, item: QueueItem) -> None:
        if item.workdir is not None:
            shutil.rmtree(item.workdir, ignore_errors=True)
            item.workdir = None

    def _on_progress(self, overall: float, _block: dict) -> None:
        if self._current is not None:
            self._current.progress = overall
            self.progress.emit(self._current.id, overall)

    def _on_log(self, text: str) -> None:
        if self._current is not None:
            self._current.log += text
            self.log.emit(self._current.id, text)

    def _on_job_started(self, index: int, total: int) -> None:
        item = self._current
        if item is not None:
            label = item.plan.jobs[index].label
            item.step = label if total == 1 else f"{label} ({index + 1}/{total})".strip()
            self.changed.emit()

    def _on_finished(self, ok: bool, cancelled: bool) -> None:
        item = self._current
        if item is None:
            return
        self._end(item, DONE if ok else CANCELLED if cancelled else FAILED)
        self._advance()
