"""The main window: task list, file inspector, task form, command console, progress."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import (QDesktopServices, QFontDatabase, QGuiApplication, QIcon, QPainter,
                         QPixmap)
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout,
                             QWidget)

from .. import __version__
from ..core import errors, hardware
from ..core.ffmpeg import Tools, child_env
from ..core.job import PLUMBING, CommandError, Plan, command_line, edited_plan
from ..core.presets import PresetStore, clean_name
from ..core.probe import MediaInfo, ProbeError, probe
from ..core.queue import (CANCELLED, DONE, FAILED, RUNNING, WAITING, JobQueue, QueueItem)
from ..tasks.base import TaskError, clock
from ..core.explain import plumbing_explanation
from . import icons, theme
from .console import CommandConsole
from .dialogs import AboutDialog, SettingsDialog
from .panels import MEDIA_FILTER, PANELS, JoinPanel
from .preview import PreviewWidget
from .widgets import (BLURB_ROLE, ICON_ROLE, CommandHighlighter, FlowLayout, NotesBox,
                      TaskDelegate, ThumbLoader, chip, plan_kind, rounded)


def human_size(n: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return ""


def path_size(path: Path) -> int:
    """Size of a file, or of everything in a folder (a result can be a folder of pictures)."""
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return path.stat().st_size


class MainWindow(QMainWindow):
    def __init__(self, tools: Tools) -> None:
        super().__init__()
        self.tools = tools
        self.media: MediaInfo | None = None
        self.plan: Plan | None = None          # what Run will run
        self._form_plan: Plan | None = None    # what the form asks for, before any hand edit
        self._edited = False                   # the command was changed by hand (spec F2)
        self._setting_console = False
        self._shown_command = ""
        self._result: Path | None = None
        self.settings = QSettings()
        self._output_custom = False
        self._workdir = Path(tempfile.mkdtemp(prefix="avopenkit-"))
        self._draft = 0                        # each queued job gets its own work folder
        self._shown: int | None = None         # queue item whose progress and log are shown
        self._applying_preset = False
        self._waiting_for_file = True
        self.hw = None                         # working hardware encoder in use, or None
        self._hw_found: list | None = None     # encoders that passed the test, once looked for
        self.presets = PresetStore(self.settings)
        self.queue = JobQueue(tools, self)
        self.runner = self.queue.runner
        self.setWindowTitle("avOpenKit")
        self.setAcceptDrops(True)
        self.resize(1180, 940)
        self._build()
        self.queue.changed.connect(self._queue_changed)
        self.queue.progress.connect(self._on_progress)
        self.queue.log.connect(self._on_log)
        self.queue.item_started.connect(self._on_item_started)
        self.queue.item_finished.connect(self._on_item_finished)
        self.tasks.setCurrentRow(0)
        self.expert_box.setChecked(self.settings.value("expert", False, type=bool))
        self._apply_mode()
        self._restore_hardware()
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSizeF(9.5)

        # ---- left: tasks and queue
        self.tasks = QListWidget()
        self.tasks.setObjectName("tasks")
        self.tasks.setItemDelegate(TaskDelegate(self.tasks))
        self.tasks.setMouseTracking(True)
        self.tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        self.preview = PreviewWidget(self.tools)
        self.preview.setVisible(False)
        self.panels = []
        for cls in PANELS:
            panel = cls()
            panel.attach_preview(self.preview)
            panel.changed.connect(self._form_changed)
            self.panels.append(panel)
            self.stack.addWidget(panel)
            item = QListWidgetItem(panel.title(), self.tasks)
            item.setData(BLURB_ROLE, panel.blurb())
            item.setData(ICON_ROLE, panel.module.ID)
            item.setToolTip(panel.blurb())
            if isinstance(panel, JoinPanel):
                panel.request_probe.connect(self._add_join_clips)
        self.tasks.setMinimumHeight(len(self.panels) * TaskDelegate.HEIGHT + 8)
        self.tasks.currentRowChanged.connect(self._task_changed)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queue")
        self.queue_list.setWordWrap(True)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_list.currentRowChanged.connect(self._queue_row_changed)
        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.setIcon(icons.icon("play"))
        self.start_button.setToolTip(self.tr("Run the waiting jobs one after another."))
        self.start_button.clicked.connect(self.start_queue)
        self.remove_button = QPushButton(self.tr("Remove"))
        self.remove_button.setIcon(icons.icon("remove"))
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button = QPushButton(self.tr("Clear finished"))
        self.clear_button.setObjectName("ghost")
        self.clear_button.setIcon(icons.icon("clear", theme.colour("muted")))
        self.clear_button.clicked.connect(self.queue.clear_finished)
        queue_buttons = QHBoxLayout()
        queue_buttons.addWidget(self.start_button)
        queue_buttons.addWidget(self.remove_button)
        tasks_label = QLabel(self.tr("TASKS"))
        self.queue_title = self.tr("QUEUE")
        tasks_label.setObjectName("sectionLabel")
        self.queue_label = QLabel(self.queue_title)
        self.queue_label.setObjectName("sectionLabel")
        side = QVBoxLayout()
        side.setContentsMargins(6, 10, 6, 10)
        side.setSpacing(4)
        side.addWidget(tasks_label)
        side.addWidget(self.tasks)
        side.addSpacing(6)
        side.addWidget(self.queue_label)
        side.addWidget(self.queue_list, 1)
        side.addLayout(queue_buttons)
        side.addWidget(self.clear_button)
        self.left = QFrame()
        self.left.setObjectName("side")
        self.left.setLayout(side)
        self.left.setFixedWidth(264)

        # ---- header
        mark = QLabel()
        mark.setPixmap(icons.logo(30))
        name = QLabel("avOpenKit")
        name.setObjectName("appName")
        self.expert_box = QCheckBox(self.tr("Expert mode"))
        self.expert_box.setToolTip(self.tr("Show codec-level options and allow the command "
                                           "to be edited before it runs."))
        self.expert_box.toggled.connect(self._mode_toggled)
        settings_button = QPushButton()
        settings_button.setObjectName("ghost")
        settings_button.setIcon(icons.icon("settings", theme.colour("muted")))
        settings_button.setToolTip(self.tr("Settings"))
        settings_button.clicked.connect(self.open_settings)
        head = QHBoxLayout()
        head.setContentsMargins(14, 8, 12, 8)
        head.addWidget(mark)
        head.addWidget(name)
        head.addStretch()
        head.addWidget(self.expert_box)
        head.addWidget(settings_button)
        header = QFrame()
        header.setObjectName("header")
        header.setLayout(head)

        # ---- the file
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(132, 76)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label = QLabel(self.tr("No file open. Drop a file here, or use Open."))
        self.file_label.setObjectName("fileName")
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_hint = QLabel(self.tr("Video or sound - MP4, MOV, MKV, WebM, MP3, WAV and "
                                        "most others."))
        self.file_hint.setObjectName("hint")
        self.inspector = QLabel("")            # the file's facts as one line of text
        self.inspector.setVisible(False)
        self.chips = FlowLayout()
        open_button = QPushButton(self.tr("Open a file…"))
        open_button.setIcon(icons.icon("open"))
        open_button.clicked.connect(self._open_dialog)
        facts = QVBoxLayout()
        facts.setSpacing(6)
        facts.addWidget(self.file_label)
        facts.addWidget(self.file_hint)
        facts.addLayout(self.chips)
        file_row = QHBoxLayout()
        file_row.setContentsMargins(12, 10, 12, 10)
        file_row.setSpacing(14)
        file_row.addWidget(self.thumb)
        file_row.addLayout(facts, 1)
        file_row.addWidget(open_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.file_card = QFrame()
        self.file_card.setObjectName("dropCard")
        self.file_card.setLayout(file_row)
        self.poster = ThumbLoader(self.tools, self)
        self.poster.ready.connect(self._show_poster)
        self._show_poster()

        # ---- the task
        self.task_title = QLabel("")
        self.task_title.setObjectName("taskTitle")
        self.blurb = QLabel("")
        self.blurb.setObjectName("taskBlurb")
        self.blurb.setWordWrap(True)

        self.preset_box = QComboBox()
        self.preset_box.activated.connect(self._preset_chosen)
        self.save_preset = QPushButton(self.tr("Save as preset…"))
        self.save_preset.clicked.connect(self._save_preset)
        self.delete_preset = QPushButton(self.tr("Delete preset"))
        self.delete_preset.setObjectName("ghost")
        self.delete_preset.clicked.connect(self._delete_preset)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(self.tr("Preset:")))
        preset_row.addWidget(self.preset_box, 1)
        preset_row.addWidget(self.save_preset)
        preset_row.addWidget(self.delete_preset)

        self.output = QLineEdit()
        self.output.textEdited.connect(self._output_edited)
        save_as = QPushButton(self.tr("Save as…"))
        save_as.setIcon(icons.icon("save"))
        save_as.clicked.connect(self._save_dialog)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel(self.tr("Result:")))
        out_row.addWidget(self.output, 1)
        out_row.addWidget(save_as)

        form = QVBoxLayout()
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(10)
        form.addLayout(preset_row)
        form.addWidget(self.stack)
        form.addLayout(out_row)
        form_card = QFrame()
        form_card.setObjectName("card")
        form_card.setLayout(form)

        # ---- what will happen, and the command
        self.notes = NotesBox()

        self.console = CommandConsole()
        self.console.setReadOnly(True)
        self.console.setToolTip("")           # per-word explanations are shown on hover
        self.console.setFont(mono)
        self.console.setMinimumHeight(86)
        self.console.setMaximumHeight(150)
        self.console.setPlaceholderText(self.tr("The FFmpeg command will appear here. Rest "
                                                "the mouse on any part of it to see what "
                                                "that part does."))
        self._highlighter = CommandHighlighter(self.console.document())
        self.console.textChanged.connect(self._console_changed)
        self.edited_label = QLabel(self.tr("Edited by hand. The form above is ignored until "
                                           "you press Reset."))
        self.edited_label.setObjectName("hint")
        self.edited_label.setWordWrap(True)
        self.reset_button = QPushButton(self.tr("Reset"))
        self.reset_button.setIcon(icons.icon("reset"))
        self.reset_button.setToolTip(self.tr("Discard the edit and show the command the form "
                                             "produces."))
        self.reset_button.clicked.connect(self._reset_edit)
        self.edited_row = QWidget()
        edited_layout = QHBoxLayout(self.edited_row)
        edited_layout.setContentsMargins(0, 0, 0, 0)
        edited_layout.addWidget(self.edited_label, 1)
        edited_layout.addWidget(self.reset_button)
        self.edited_row.setVisible(False)
        self.plumbing = QLabel(self.tr("avOpenKit also adds, to follow progress and never "
                                       "overwrite a file: {0}").format(" ".join(PLUMBING) + " -n"))
        self.plumbing.setObjectName("footnote")
        self.plumbing.setWordWrap(True)
        self.plumbing.setToolTip(plumbing_explanation())

        self.copy_button = QPushButton(self.tr("Copy command"))
        self.copy_button.setIcon(icons.icon("copy"))
        self.copy_button.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.console.toPlainText()))
        self.run_button = QPushButton(self.tr("Run"))
        self.run_button.setObjectName("primary")
        self.run_button.setIcon(icons.icon("play", theme.colour("accent_text"), theme.colour("faint")))
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.setIcon(icons.icon("stop"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip(self.tr("Stop the job that is running. Jobs still "
                                              "waiting stay in the queue."))
        self.cancel_button.clicked.connect(self.queue.cancel)
        self.queue_button = QPushButton(self.tr("Add to queue"))
        self.queue_button.setIcon(icons.icon("queue"))
        self.queue_button.setToolTip(self.tr("Keep this job for later and go on preparing "
                                             "others. Start the queue when you are ready."))
        self.queue_button.clicked.connect(self.add_to_queue)
        run_row = QHBoxLayout()
        run_row.addWidget(self.copy_button)
        run_row.addStretch()
        run_row.addWidget(self.cancel_button)
        run_row.addWidget(self.queue_button)
        run_row.addWidget(self.run_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.open_folder = QPushButton(self.tr("Open folder"))
        self.open_folder.setIcon(icons.icon("folder"))
        self.play = QPushButton(self.tr("Play result"))
        self.play.setIcon(icons.icon("play"))
        for b in (self.open_folder, self.play):
            b.setVisible(False)
        self.open_folder.clicked.connect(lambda: self._open_result(folder=True))
        self.play.clicked.connect(lambda: self._open_result(folder=False))
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.play)
        status_row.addWidget(self.open_folder)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setFont(mono)
        self.log.setMinimumHeight(90)
        self.log.setPlaceholderText(self.tr("FFmpeg's own messages appear here."))

        command = QVBoxLayout()
        command.setContentsMargins(14, 12, 14, 12)
        command.setSpacing(8)
        command.addWidget(self.console)
        command.addWidget(self.edited_row)
        command.addWidget(self.plumbing)
        command.addLayout(run_row)
        command.addWidget(self.progress)
        command.addLayout(status_row)
        command_card = QFrame()
        command_card.setObjectName("card")
        command_card.setLayout(command)

        right = QVBoxLayout()
        right.setContentsMargins(18, 14, 18, 14)
        right.setSpacing(10)
        right.addWidget(self.file_card)
        right.addSpacing(4)
        right.addWidget(self.task_title)
        right.addWidget(self.blurb)
        right.addWidget(self.preview, 2)
        right.addWidget(form_card)
        right.addWidget(self.notes)
        right.addWidget(command_card)
        right.addWidget(self.log, 1)
        holder = QWidget()
        holder.setLayout(right)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.left)
        body.addWidget(scroll, 1)
        whole = QVBoxLayout()
        whole.setContentsMargins(0, 0, 0, 0)
        whole.setSpacing(0)
        whole.addWidget(header)
        whole.addLayout(body, 1)
        central = QWidget()
        central.setLayout(whole)
        self.setCentralWidget(central)
        tools_menu = self.menuBar().addMenu(self.tr("&Tools"))
        tools_menu.addAction(self.tr("&Settings…"), self.open_settings)
        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        help_menu.addAction(self.tr("&About avOpenKit"), self.open_about)
        self._show_ffmpeg_in_status_bar()

    def _show_poster(self, _index: int = 0, image=None) -> None:
        """The small picture of the open file: a frame from it, or an icon when there is none."""
        if image is not None and not image.isNull():
            # Drawn at the screen's own resolution, so it stays sharp on high-density displays.
            ratio = max(self.thumb.devicePixelRatioF(), 2.0)
            size = self.thumb.size() * ratio
            pm = QPixmap.fromImage(image).scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                 Qt.TransformationMode.SmoothTransformation)
            pm = pm.copy((pm.width() - size.width()) // 2, (pm.height() - size.height()) // 2,
                         size.width(), size.height())
            pm.setDevicePixelRatio(ratio)
            self.thumb.setPixmap(rounded(pm, 6))
            for panel in self.panels:
                panel.set_poster(image)
            return
        if self.media is None:
            name = "drop"
        else:
            name = "film" if self.media.video is not None else "note"
        self.thumb.setPixmap(icons.pixmap(name, theme.colour("faint"), 34))

    def _show_file(self, media: MediaInfo) -> None:
        """Fill the file card: name, facts as chips, and a picture from the file."""
        self.file_label.setText(str(media.path))
        self.file_hint.setVisible(False)
        self.inspector.setText(self.describe(media))
        self.chips.clear()
        for text in self.facts(media):
            self.chips.addWidget(chip(text))
        self.file_card.setObjectName("card")
        self.file_card.style().unpolish(self.file_card)
        self.file_card.style().polish(self.file_card)
        self._show_poster()
        if media.video is not None and media.duration > 0:
            self.poster.load(media.path, [min(media.duration * 0.1, 10.0)], 228)
        else:
            self.poster.cancel()

    def _show_ffmpeg_in_status_bar(self) -> None:
        self.statusBar().showMessage(
            f"avOpenKit {__version__} - FFmpeg {self.tools.version_text} ({self.tools.ffmpeg})")

    # ------------------------------------------------------------------ settings and about

    def hardware_found(self) -> list:
        """Hardware encoders that pass a test encode with the FFmpeg in use. Looked for once."""
        if self._hw_found is None:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._hw_found = hardware.detect(self.tools)
            finally:
                QGuiApplication.restoreOverrideCursor()
        return self._hw_found

    def _restore_hardware(self) -> None:
        """Use the saved hardware encoder only if it still works; otherwise say so (F14)."""
        wanted = self.settings.value("hardware", "", type=str)
        self.hw = hardware.find(self.tools, wanted) if wanted else None
        if wanted and self.hw is None:
            self.status.setText(self.tr(
                "The hardware encoder chosen in Settings is not working now, so the standard "
                "encoder is being used."))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.tools, self.queue.running, self,
                                hardware=self.hardware_found())
        if dialog.exec():
            self.apply_settings(dialog)

    def apply_settings(self, dialog: SettingsDialog) -> None:
        """Act on an accepted Settings dialog."""
        self._clear_result()
        messages = []
        if dialog.tools is not None:
            self.set_tools(dialog.tools)
            messages.append(self.tr("Now using FFmpeg {0} from {1}.").format(
                self.tools.version_text, self.tools.ffmpeg))
        if dialog.language_changed:
            messages.append(self.tr("The language changes the next time avOpenKit starts."))
        if dialog.theme_changed:
            messages.append(self.tr("The new appearance is used the next time avOpenKit starts."))
        if dialog.hardware_changed or dialog.tools is not None:
            self._restore_hardware()
            if dialog.hardware_changed:
                messages.append(self.tr("Hardware encoding: {0}.").format(self.hw.label)
                                if self.hw else self.tr("Hardware encoding is off."))
            elif self.status.text():
                messages.append(self.status.text())
            self.refresh()
        self.status.setText(" ".join(messages))

    def set_tools(self, tools: Tools) -> None:
        """Switch to a different FFmpeg (spec F16). Jobs already queued run with it too."""
        self.tools = tools
        self._hw_found = None                  # another FFmpeg may have other encoders
        self.queue.runner.set_tools(tools)
        self.preview.tools = tools
        self._show_ffmpeg_in_status_bar()
        self.refresh()

    def open_about(self) -> None:
        AboutDialog(self.tools, self).exec()

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
        self._show_file(media)
        for panel in self.panels:
            panel.set_media(media)
        self._output_custom = False
        self._edited = False
        self._clear_result()
        self._sync_preview()
        self.refresh()
        return True

    def _add_join_clips(self, paths: list) -> None:
        clips = [m for m in (self._probe(p) for p in paths) if m is not None]
        if clips:
            self.panels[[type(p) for p in self.panels].index(JoinPanel)].add_clips(clips)

    def describe(self, m: MediaInfo) -> str:
        return "  ·  ".join(self.facts(m))

    def facts(self, m: MediaInfo) -> list[str]:
        """The file's facts in plain words, one per chip."""
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
        return parts

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
        # Let the form be as tall as the task in view, not as tall as the tallest task.
        for i, panel in enumerate(self.panels):
            keep = QSizePolicy.Policy.Preferred if i == row else QSizePolicy.Policy.Ignored
            panel.setSizePolicy(QSizePolicy.Policy.Preferred, keep)
        self.stack.adjustSize()
        self.task_title.setText(self.panel().title())
        self.blurb.setText(self.panel().blurb())
        self._output_custom = False
        self._edited = False
        self._reload_presets()
        self._sync_preview()
        self.refresh()

    def _form_changed(self) -> None:
        if not self._applying_preset:
            self.preset_box.setCurrentIndex(0)   # the form no longer matches the named preset
        self.refresh()

    # ------------------------------------------------------------------ presets (spec F10)

    def _reload_presets(self, select: str | None = None) -> None:
        self.preset_box.clear()
        self.preset_box.addItem(self.tr("Choose a preset…"), None)
        for name in self.presets.names(self.panel().module.ID):
            self.preset_box.addItem(name, name)
        self.preset_box.setCurrentIndex(max(self.preset_box.findData(select), 0) if select else 0)

    def _preset_chosen(self, index: int) -> None:
        name = self.preset_box.itemData(index)
        if name is None:
            return
        self.apply_preset(name)

    def apply_preset(self, name: str) -> bool:
        state = self.presets.get(self.panel().module.ID, name)
        if state is None:
            return False
        self._applying_preset = True
        try:
            ignored = self.panel().set_state(state)
        finally:
            self._applying_preset = False
        self.preset_box.setCurrentIndex(max(self.preset_box.findData(name), 0))
        self._clear_result()
        self.status.setText(
            self.tr("Preset \"{0}\" was saved in expert mode. Its expert options are used only "
                    "when Expert mode is on.").format(name) if ignored else
            self.tr("Preset \"{0}\" applied.").format(name))
        return True

    def _save_preset(self) -> None:
        current = self.preset_box.currentData() or ""
        name, ok = QInputDialog.getText(self, "avOpenKit", self.tr("Name for this preset:"),
                                        text=current)
        if ok:
            self.save_preset_as(name)

    def save_preset_as(self, name: str) -> str | None:
        """Save the current form under a name; an existing preset of that name is replaced
        only after asking."""
        name = clean_name(name)
        if not name:
            return None
        task = self.panel().module.ID
        if self.presets.get(task, name) is not None:
            answer = QMessageBox.question(
                self, "avOpenKit", self.tr("A preset named \"{0}\" exists. Replace it?")
                .format(name))
            if answer != QMessageBox.StandardButton.Yes:
                return None
        name = self.presets.save(task, name, self.panel().state())
        self._reload_presets(name)
        self.status.setText(self.tr("Preset \"{0}\" saved.").format(name))
        return name

    def _delete_preset(self) -> None:
        name = self.preset_box.currentData()
        if name is None:
            self.status.setText(self.tr("Choose the preset to delete first."))
            return
        self.presets.delete(self.panel().module.ID, name)
        self._reload_presets()
        self.status.setText(self.tr("Preset \"{0}\" deleted.").format(name))

    # ------------------------------------------------------------------ modes and editing

    def _mode_toggled(self, on: bool) -> None:
        self.settings.setValue("expert", on)
        self._apply_mode()
        self.refresh()

    def _apply_mode(self) -> None:
        """Simple: defaults, read-only command. Expert: codec options, editable command."""
        expert = self.expert_box.isChecked()
        if not expert:
            self._edited = False
        self.console.setReadOnly(not expert)
        for panel in self.panels:
            panel.blockSignals(True)
            panel.set_expert(expert)
            panel.blockSignals(False)

    def _set_console(self, text: str) -> None:
        self._setting_console = True
        self._shown_command = text
        self.console.setPlainText(text)
        self._setting_console = False

    def _console_changed(self) -> None:
        if self._setting_console or self.console.isReadOnly():
            return
        # Only a change of the words is an edit. Re-colouring the command also raises this
        # signal, and must not be mistaken for the user typing.
        if not self._edited and self.console.toPlainText() == self._shown_command:
            return
        self._edited = True
        self._use_edit()

    def _reset_edit(self) -> None:
        self._edited = False
        self.refresh()

    def _use_edit(self) -> None:
        """Make the hand-edited text the plan, or say why it cannot be run."""
        self.edited_row.setVisible(True)
        try:
            self.plan = edited_plan(self.console.toPlainText(), self._form_plan)
        except CommandError as e:
            self.plan = None
            self.run_button.setEnabled(False)
            self.queue_button.setEnabled(False)
            self.notes.show_notes(self._command_error(e), "problem", self.tr("Cannot run"))
            return
        self.run_button.setEnabled(True)
        self.queue_button.setEnabled(True)
        self.notes.show_notes(self.tr(
            "This command was edited by hand and runs as typed, so avOpenKit can no longer "
            "say what it will do. It still never replaces a file without asking; -y and -n "
            "in the command are ignored."), "", self.tr("Edited by hand"))

    def _command_error(self, e: CommandError) -> str:
        return {
            "empty": self.tr("There is no command to run."),
            "syntax": self.tr("The command cannot be read: a quotation mark is not closed."),
            "program": self.tr("Each line must start with ffmpeg. Other programs are not run."),
            "over_input": self.tr("The result cannot be saved over an input file."),
        }.get(e.code, str(e))

    def _sync_preview(self) -> None:
        """Show the preview for tasks that select a section, loaded with the open file."""
        wanted = self.panel().uses_preview and self.media is not None
        if wanted and self.preview.media is not self.media:
            self.preview.load(self.media)
        elif not wanted:
            self.preview.pause()
        self.preview.setVisible(wanted)
        if wanted:
            self.panel().show_selection()

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

    def _draft_dir(self) -> Path:
        """Work folder for the job being prepared. It becomes that job's own when queued."""
        return self._workdir / f"job{self._draft}"

    def _free_name(self, path: Path) -> Path:
        """A suggested result name that no waiting or running job has already taken."""
        claimed = self.queue.claimed()
        m = re.fullmatch(r"(.*?)(?:-(\d+))?", path.stem)
        stem, n = m.group(1), int(m.group(2) or 1)
        candidate = path
        while candidate.resolve() in claimed or candidate.exists():
            n += 1
            candidate = path.with_name(f"{stem}-{n}{path.suffix}")
        return candidate

    def _plan_from_form(self) -> tuple[Plan | None, str]:
        """The plan the form asks for, or None and the reason. Also fills in the result name
        unless the user has typed their own."""
        panel = self.panel()
        media = self._effective_media()
        self._waiting_for_file = media is None and panel.needs_media()
        if self._waiting_for_file:
            return None, self.tr("Open a file to begin.")
        settings = panel.settings()
        if hasattr(settings, "hw"):
            settings.hw = self.hw
        if media is not None and not self._output_custom:
            self.output.setText(str(self._free_name(panel.module.suggest_output(media, settings))))
        text = self.output.text().strip()
        settings.output = Path(text) if text else None
        try:
            return panel.module.plan(settings, media, self.tools, self._draft_dir()), ""
        except TaskError as e:
            return None, str(e)

    def refresh(self) -> None:
        """Rebuild the plan from the current form and show its command (spec F1)."""
        if self._edited:
            self._use_edit()
            return
        self.edited_row.setVisible(False)
        plan, problem = self._plan_from_form()
        self.plan = self._form_plan = plan
        ready = plan is not None
        if ready:
            kind = plan_kind(plan)
            badge = {"copy": self.tr("No quality loss"), "encode": self.tr("Re-encodes"),
                     "mixed": self.tr("Partly re-encoded")}.get(kind, "")
            self.notes.show_notes("\n".join(plan.notes), kind, badge)
        elif self._waiting_for_file:
            self.notes.show_notes(problem, "", "")
        else:
            self.notes.show_notes(problem, "problem", self.tr("Cannot run yet"))
        self._set_console("\n".join(command_line(j) for j in plan.jobs) if ready else "")
        self.run_button.setEnabled(ready)
        self.queue_button.setEnabled(ready)

    # ------------------------------------------------------------------ queue and run

    def _enqueue(self) -> QueueItem | None:
        """Put the current plan in the queue, after the checks that protect existing files."""
        plan = self.plan
        if plan is None:
            return None
        claimed = self.queue.claimed()
        for p in plan.outputs:
            if Path(p).resolve() in claimed:
                self._clear_result()
                self.status.setText(self.tr("A job in the queue already writes {0}. Choose a "
                                            "different result name.").format(Path(p).name))
                return None
        overwrite = False
        taken = [p for p in plan.outputs if Path(p).exists()]
        if taken:
            answer = QMessageBox.question(
                self, "avOpenKit",
                self.tr("{0} already exists. Replace it?").format(Path(taken[0]).name))
            if answer != QMessageBox.StandardButton.Yes:
                return None
            overwrite = True
        workdir = self._draft_dir()
        workdir.mkdir(parents=True, exist_ok=True)
        title = self.panel().title()
        if plan.outputs:
            title = f"{title} → {Path(plan.outputs[-1]).name}"
        source = self._effective_media()
        item = self.queue.add(title, plan, overwrite, source.size if source else 0, workdir)

        # The next job is prepared in a fresh work folder and with a fresh result name.
        self._draft += 1
        if self._edited:
            self._form_plan, _ = self._plan_from_form()
            self._set_console(self.console.toPlainText().replace(str(workdir),
                                                                 str(self._draft_dir())))
        else:
            self._output_custom = False
        self.refresh()
        return item

    def add_to_queue(self) -> None:
        item = self._enqueue()
        if item is not None and not self.queue.running:
            self._clear_result()
            self.status.setText(self.tr("Added to the queue. Press Start to run it."))

    def run(self) -> None:
        """Queue the current job and start the queue (any jobs already waiting run first)."""
        if self._enqueue() is not None:
            self.preview.pause()
            self.queue.start()

    def start_queue(self) -> None:
        self.preview.pause()
        self.queue.start()

    def _remove_selected(self) -> None:
        row = self.queue_list.currentRow()
        if 0 <= row < len(self.queue.items):
            self.queue.remove(self.queue.items[row].id)
            self.refresh()

    def _status_dot(self, status: str) -> QIcon:
        """A coloured dot for a queue row, so its state can be read without the words."""
        tint = {WAITING: "muted", RUNNING: "accent", DONE: "good", FAILED: "bad",
                CANCELLED: "faint"}[status]
        pm = QPixmap(24, 24)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.colour(tint))
        p.drawEllipse(6, 6, 12, 12)
        p.end()
        return QIcon(pm)

    def _status_word(self, status: str) -> str:
        return {WAITING: self.tr("waiting"), RUNNING: self.tr("running"), DONE: self.tr("done"),
                FAILED: self.tr("failed"), CANCELLED: self.tr("cancelled")}[status]

    def _queue_changed(self) -> None:
        selected = self.queue_list.currentRow()
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for item in self.queue.items:
            text = f"{item.title} - {self._status_word(item.status)}"
            row = QListWidgetItem(self._status_dot(item.status), text, self.queue_list)
            row.setToolTip(text)
        if 0 <= selected < len(self.queue.items):
            self.queue_list.setCurrentRow(selected)
        self.queue_list.blockSignals(False)
        waiting = len(self.queue.waiting())
        self.queue_label.setText(self.tr("QUEUE ({0} waiting)").format(waiting) if waiting
                                 else self.queue_title)
        self.start_button.setEnabled(waiting > 0 and not self.queue.running)
        self.cancel_button.setEnabled(self.queue.running)
        shown = self.queue.item(self._shown) if self._shown is not None else None
        if shown is not None:
            self._show_item(shown, with_log=False)

    def _queue_row_changed(self, row: int) -> None:
        if 0 <= row < len(self.queue.items):
            self._shown = self.queue.items[row].id
            self._show_item(self.queue.items[row])

    def _clear_result(self) -> None:
        self.status.setText("")
        self.play.setVisible(False)
        self.open_folder.setVisible(False)

    def _show_item(self, item: QueueItem, with_log: bool = True) -> None:
        """Show one queue item's progress, outcome and FFmpeg messages."""
        if with_log:
            self.log.setPlainText(item.log)
        self._clear_result()
        self._result = None
        self.progress.setRange(0, 1000)
        if item.status == RUNNING:
            self._set_progress(item.progress)
            self.status.setText(item.step or self.tr("Running"))
        elif item.status == WAITING:
            self.progress.setValue(0)
            self.status.setText(self.tr("Waiting in the queue."))
        elif item.status == DONE:
            self.progress.setValue(1000)
            out = item.result
            if out is not None:
                self._result = out
                text = self.tr("Done: {0} ({1})").format(out.name, human_size(path_size(out)))
                if item.source_size:
                    text += self.tr(" - the original is {0}").format(
                        human_size(item.source_size))
                self.play.setVisible(True)
                self.open_folder.setVisible(True)
            else:
                text = self.tr("Done.")
            self.status.setText(text)
        elif item.status == CANCELLED:
            self.progress.setValue(0)
            self.status.setText(self.tr("Cancelled. The unfinished file was deleted."))
        else:
            self.progress.setValue(0)
            reason = errors.explain(item.log)
            self.status.setText(self.tr("Failed. {0}").format(
                reason or self.tr("See FFmpeg's messages below.")))

    def _set_progress(self, overall: float) -> None:
        if overall < 0:
            self.progress.setRange(0, 0)       # length unknown: show activity, not a number
            return
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(overall * 1000))

    def _on_item_started(self, item_id: int) -> None:
        """The display follows whichever job is running."""
        self._shown = item_id
        item = self.queue.item(item_id)
        self.queue_list.blockSignals(True)
        self.queue_list.setCurrentRow(self.queue.items.index(item))
        self.queue_list.blockSignals(False)
        self._show_item(item)

    def _on_progress(self, item_id: int, overall: float) -> None:
        if item_id == self._shown:
            self._set_progress(overall)

    def _on_log(self, item_id: int, text: str) -> None:
        if item_id == self._shown:
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
            self.log.insertPlainText(text)

    def _on_item_finished(self, item_id: int) -> None:
        item = self.queue.item(item_id)
        if item is not None and item_id == self._shown:
            self._show_item(item)
        self.refresh()          # a result name may now be taken on disk, or free again

    def _open_result(self, folder: bool) -> None:
        if self._result is None:
            return
        target = self._result.parent if folder else self._result
        if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
            # Qt would start the player with this program's bundled libraries in its
            # environment (see child_env); start it ourselves with the system's.
            try:
                subprocess.Popen(["xdg-open", str(target)], env=child_env())
                return
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def closeEvent(self, event) -> None:
        self.queue.shutdown()
        self.poster.cancel()
        self.preview.unload()
        shutil.rmtree(self._workdir, ignore_errors=True)
        super().closeEvent(event)
