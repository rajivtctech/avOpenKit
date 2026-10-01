"""The main window: task list, file inspector, task form, command console, progress."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                             QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import errors
from ..core.ffmpeg import Tools
from ..core.job import PLUMBING, Plan, command_line
from ..core.probe import MediaInfo, ProbeError, probe
from ..core.runner import JobRunner
from ..tasks.base import TaskError, clock
from .panels import MEDIA_FILTER, PANELS, JoinPanel


def human_size(n: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return ""


class MainWindow(QMainWindow):
    def __init__(self, tools: Tools) -> None:
        super().__init__()
        self.tools = tools
        self.media: MediaInfo | None = None
        self.plan: Plan | None = None
        self._output_custom = False
        self._workdir = Path(tempfile.mkdtemp(prefix="avopenkit-"))
        self.runner = JobRunner(tools, self)
        self.setWindowTitle("avOpenKit")
        self.setAcceptDrops(True)
        self.resize(1000, 720)
        self._build()
        self.runner.progress.connect(self._on_progress)
        self.runner.log.connect(self._on_log)
        self.runner.job_started.connect(self._on_job_started)
        self.runner.finished.connect(self._on_finished)
        self.tasks.setCurrentRow(0)
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.tasks = QListWidget()
        self.tasks.setMaximumWidth(190)
        self.stack = QStackedWidget()
        self.panels = []
        for cls in PANELS:
            panel = cls()
            panel.changed.connect(self.refresh)
            self.panels.append(panel)
            self.stack.addWidget(panel)
            self.tasks.addItem(panel.title())
            if isinstance(panel, JoinPanel):
                panel.request_probe.connect(self._add_join_clips)
        self.tasks.currentRowChanged.connect(self._task_changed)

        open_button = QPushButton(self.tr("Open a file…"))
        open_button.clicked.connect(self._open_dialog)
        self.file_label = QLabel(self.tr("No file open. Drop a file here, or use Open."))
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_row = QHBoxLayout()
        file_row.addWidget(open_button)
        file_row.addWidget(self.file_label, 1)

        self.inspector = QLabel("")
        self.inspector.setWordWrap(True)
        self.blurb = QLabel("")
        self.blurb.setWordWrap(True)
        font = self.blurb.font()
        font.setBold(True)
        self.blurb.setFont(font)

        self.output = QLineEdit()
        self.output.textEdited.connect(self._output_edited)
        save_as = QPushButton(self.tr("Save as…"))
        save_as.clicked.connect(self._save_dialog)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel(self.tr("Result:")))
        out_row.addWidget(self.output, 1)
        out_row.addWidget(save_as)

        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setFrameShape(QFrame.Shape.StyledPanel)
        self.notes.setMargin(6)

        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(mono)
        self.console.setMaximumHeight(130)
        self.console.setPlaceholderText(self.tr("The FFmpeg command will appear here."))
        self.plumbing = QLabel(self.tr("avOpenKit also adds, to follow progress and never "
                                       "overwrite a file: {0}").format(" ".join(PLUMBING) + " -n"))
        self.plumbing.setWordWrap(True)
        self.copy_button = QPushButton(self.tr("Copy command"))
        self.copy_button.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.console.toPlainText()))
        self.run_button = QPushButton(self.tr("Run"))
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.runner.cancel)
        run_row = QHBoxLayout()
        run_row.addWidget(self.copy_button)
        run_row.addStretch()
        run_row.addWidget(self.cancel_button)
        run_row.addWidget(self.run_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.open_folder = QPushButton(self.tr("Open folder"))
        self.play = QPushButton(self.tr("Play result"))
        for b in (self.open_folder, self.play):
            b.setVisible(False)
        self.open_folder.clicked.connect(lambda: self._open_result(folder=True))
        self.play.clicked.connect(lambda: self._open_result(folder=False))
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.play)
        status_row.addWidget(self.open_folder)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(mono)
        self.log.setPlaceholderText(self.tr("FFmpeg's own messages appear here."))

        right = QVBoxLayout()
        right.addLayout(file_row)
        right.addWidget(self.inspector)
        right.addWidget(self.blurb)
        right.addWidget(self.stack)
        right.addLayout(out_row)
        right.addWidget(self.notes)
        right.addWidget(self.console)
        right.addWidget(self.plumbing)
        right.addLayout(run_row)
        right.addWidget(self.progress)
        right.addLayout(status_row)
        right.addWidget(self.log, 1)
        holder = QWidget()
        holder.setLayout(right)

        split = QSplitter()
        split.addWidget(self.tasks)
        split.addWidget(holder)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.statusBar().showMessage(
            f"avOpenKit {__version__} - FFmpeg {self.tools.version_text} ({self.tools.ffmpeg})")

    # ------------------------------------------------------------------ files

    def panel(self):
        return self.panels[max(self.tasks.currentRow(), 0)]

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open a file"), "",
            self.tr("Media files") + f" ({MEDIA_FILTER});;" + self.tr("All files") + " (*)")
        if path:
            self.open_file(path)

    def _probe(self, path) -> MediaInfo | None:
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return probe(path, self.tools, keyframes=True)
        except ProbeError as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "avOpenKit",
                                self.tr("{0} could not be read as audio or video.\n\n{1}")
                                .format(Path(path).name, e))
            return None
        finally:
            QGuiApplication.restoreOverrideCursor()

    def open_file(self, path) -> bool:
        media = self._probe(path)
        if media is None:
            return False
        self.media = media
        self.file_label.setText(str(media.path))
        self.inspector.setText(self.describe(media))
        for panel in self.panels:
            panel.set_media(media)
        self._output_custom = False
        self._clear_result()
        self.refresh()
        return True

    def _add_join_clips(self, paths: list) -> None:
        clips = [m for m in (self._probe(p) for p in paths) if m is not None]
        if clips:
            self.panels[[type(p) for p in self.panels].index(JoinPanel)].add_clips(clips)

    def describe(self, m: MediaInfo) -> str:
        parts = [self.tr("Length {0}").format(clock(m.duration)), human_size(m.size)]
        if m.video:
            v = m.video
            text = self.tr("Video: {0}, {1}×{2}, {3} frames per second").format(
                v.codec.upper(), v.width, v.height, f"{v.fps:.3g}")
            if v.rotation:
                text += self.tr(", stored rotation {0}°").format(v.rotation)
            parts.append(text)
        else:
            parts.append(self.tr("No video"))
        if m.audio:
            a = m.audio
            parts.append(self.tr("Sound: {0}, {1} channel(s), {2} Hz").format(
                a.codec.upper(), a.channels, a.sample_rate))
        else:
            parts.append(self.tr("No sound"))
        if m.has_subtitles:
            parts.append(self.tr("Has subtitle tracks"))
        return "  ·  ".join(parts)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        if isinstance(self.panel(), JoinPanel):
            self._add_join_clips(paths)
        else:
            self.open_file(paths[0])

    # ------------------------------------------------------------------ plan

    def _task_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        self.blurb.setText(self.panel().blurb())
        self._output_custom = False
        self.refresh()

    def _output_edited(self) -> None:
        self._output_custom = True
        self.refresh()

    def _save_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Save the result as"),
                                              self.output.text())
        if path:
            self.output.setText(path)
            self._output_custom = True
            self.refresh()

    def _effective_media(self) -> MediaInfo | None:
        panel = self.panel()
        return panel.first_clip() if isinstance(panel, JoinPanel) else self.media

    def refresh(self) -> None:
        """Rebuild the plan from the current form and show its command (spec F1)."""
        if self.runner.running:
            return
        panel = self.panel()
        media = self._effective_media()
        self.plan = None
        self.console.clear()
        self.run_button.setEnabled(False)
        if media is None and panel.needs_media():
            self.notes.setText(self.tr("Open a file to begin."))
            return
        settings = panel.settings()
        if media is not None and not self._output_custom:
            self.output.setText(str(panel.module.suggest_output(media, settings)))
        text = self.output.text().strip()
        settings.output = Path(text) if text else None
        try:
            plan = panel.module.plan(settings, media, self.tools, self._workdir)
        except TaskError as e:
            self.notes.setText(str(e))
            return
        self.plan = plan
        self.notes.setText("\n".join(plan.notes))
        self.console.setPlainText("\n".join(command_line(j) for j in plan.jobs))
        self.run_button.setEnabled(True)

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        if self.plan is None or self.runner.running:
            return
        overwrite = False
        taken = [p for p in self.plan.outputs if Path(p).exists()]
        if taken:
            answer = QMessageBox.question(
                self, "avOpenKit",
                self.tr("{0} already exists. Replace it?").format(Path(taken[0]).name))
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        self._clear_result()
        self.log.clear()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self._set_running(True)
        self.runner.start(self.plan, overwrite)

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.tasks.setEnabled(not running)
        self.stack.setEnabled(not running)
        self.output.setEnabled(not running)

    def _clear_result(self) -> None:
        self.status.setText("")
        self.play.setVisible(False)
        self.open_folder.setVisible(False)

    def _on_job_started(self, index: int, total: int) -> None:
        label = self.plan.jobs[index].label if self.plan else ""
        self.status.setText(label if total == 1 else f"{label} ({index + 1}/{total})")

    def _on_progress(self, overall: float, block: dict) -> None:
        if overall < 0:
            self.progress.setRange(0, 0)       # length unknown: show activity, not a number
            return
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(overall * 1000))

    def _on_log(self, text: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text)

    def _on_finished(self, ok: bool, cancelled: bool) -> None:
        self._set_running(False)
        self.progress.setRange(0, 1000)
        plan = self.plan
        if ok and plan:
            self.progress.setValue(1000)
            out = Path(plan.outputs[-1])
            self._result = out
            source = self._effective_media()
            text = self.tr("Done: {0} ({1})").format(out.name, human_size(out.stat().st_size))
            if source and source.size:
                text += self.tr(" - the original is {0}").format(human_size(source.size))
            self.status.setText(text)
            self.play.setVisible(True)
            self.open_folder.setVisible(True)
            self._output_custom = False      # suggest a fresh name for the next run
        elif cancelled:
            self.progress.setValue(0)
            self.status.setText(self.tr("Cancelled. The unfinished file was deleted."))
        else:
            self.progress.setValue(0)
            reason = errors.explain(self.log.toPlainText())
            self.status.setText(self.tr("Failed. {0}").format(
                reason or self.tr("See FFmpeg's messages below.")))
        self.refresh()

    def _open_result(self, folder: bool) -> None:
        target = self._result.parent if folder else self._result
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def closeEvent(self, event) -> None:
        if self.runner.running:
            self.runner.cancel()
        shutil.rmtree(self._workdir, ignore_errors=True)
        super().closeEvent(event)
