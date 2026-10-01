"""Settings (language, which FFmpeg to use) and About (spec F16, F17, section 7)."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QSettings, Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QVBoxLayout)

from .. import __version__, languages
from ..core import ffmpeg
from ..core.ffmpeg import Tools

PROJECT_URL = "https://github.com/rajivtctech/avOpenKit"


class SettingsDialog(QDialog):
    """Edits the saved settings. After accept(), `tools` is the FFmpeg to use from now on
    (None when it did not change) and `language_changed` says whether a restart is needed."""

    def __init__(self, settings: QSettings, tools: Tools, busy: bool = False, parent=None,
                 i18n_folder: Path = languages.FOLDER, hardware=()) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.settings = settings
        self._current = tools
        self.tools: Tools | None = None
        self.language_changed = False
        self.hardware_changed = False
        self.theme_changed = False
        self._folder = i18n_folder

        self.language = QComboBox()
        system = languages.LANGUAGES[languages.effective("", i18n_folder)]
        self.language.addItem(self.tr("Follow this computer's language ({0})").format(system), "")
        for code in languages.available(i18n_folder):
            self.language.addItem(languages.LANGUAGES[code], code)
        saved = settings.value("language", "", type=str)
        self.language.setCurrentIndex(max(self.language.findData(saved), 0))
        language_note = QLabel(self.tr(
            "A change of language takes effect the next time avOpenKit starts. Other languages "
            "appear in this list as their translations are completed and checked."))
        language_note.setWordWrap(True)
        language_box = QGroupBox(self.tr("Language"))
        language_form = QFormLayout(language_box)
        language_form.addRow(self.tr("Language"), self.language)
        language_form.addRow(language_note)

        self.appearance = QComboBox()
        self.appearance.addItem(self.tr("Dark - neutral greys, easy on the eyes beside pictures"), "dark")
        self.appearance.addItem(self.tr("Light"), "light")
        self.appearance.setCurrentIndex(max(self.appearance.findData(
            settings.value("theme", "dark", type=str)), 0))
        appearance_note = QLabel(self.tr("A change of appearance takes effect the next time "
                                         "avOpenKit starts."))
        appearance_note.setWordWrap(True)
        appearance_box = QGroupBox(self.tr("Appearance"))
        appearance_form = QFormLayout(appearance_box)
        appearance_form.addRow(self.tr("Colours"), self.appearance)
        appearance_form.addRow(appearance_note)

        self.in_use = QLabel(self.tr("In use now: {0} (version {1})").format(
            tools.ffmpeg, tools.version_text or "?"))
        self.in_use.setWordWrap(True)
        self.in_use.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.ffmpeg_path = QLineEdit(settings.value("ffmpeg_path", "", type=str))
        self.ffmpeg_path.setPlaceholderText(self.tr(
            "Automatic - the copy supplied with avOpenKit, or the one installed on this computer"))
        browse = QPushButton(self.tr("Browse…"))
        browse.clicked.connect(self._browse)
        automatic = QPushButton(self.tr("Automatic"))
        automatic.clicked.connect(self.ffmpeg_path.clear)
        row = QHBoxLayout()
        row.addWidget(self.ffmpeg_path, 1)
        row.addWidget(browse)
        row.addWidget(automatic)
        ffmpeg_note = QLabel(self.tr(
            "To use a different FFmpeg, choose the folder that holds both the ffmpeg and "
            "ffprobe programs."))
        ffmpeg_note.setWordWrap(True)
        ffmpeg_box = QGroupBox("FFmpeg")
        ffmpeg_form = QFormLayout(ffmpeg_box)
        ffmpeg_form.addRow(self.in_use)
        ffmpeg_form.addRow(self.tr("FFmpeg folder"), row)
        ffmpeg_form.addRow(ffmpeg_note)
        if busy:
            for w in (self.ffmpeg_path, browse, automatic):
                w.setEnabled(False)
            ffmpeg_note.setText(self.tr("The FFmpeg in use cannot be changed while a job is "
                                        "running."))

        # Only encoders that passed a test encode on this machine are passed in (spec F14).
        self.hardware = QComboBox()
        self.hardware.addItem(self.tr("Off - use the standard encoder"), "")
        for hw in hardware:
            self.hardware.addItem(hw.label, hw.id)
        saved_hw = settings.value("hardware", "", type=str)
        self.hardware.setCurrentIndex(max(self.hardware.findData(saved_hw), 0))
        self.hardware.setEnabled(bool(hardware))
        hardware_note = QLabel(
            self.tr("Lets the graphics chip do the encoding when a task re-encodes video to "
                    "H.264. It is faster, but usually gives a little lower quality at the same "
                    "file size. Shrink to a size always uses the standard encoder, which hits "
                    "the target size more accurately.") if hardware else
            self.tr("No working hardware encoder was found on this computer."))
        hardware_note.setWordWrap(True)
        hardware_box = QGroupBox(self.tr("Hardware encoding"))
        hardware_form = QFormLayout(hardware_box)
        hardware_form.addRow(self.tr("Encoder"), self.hardware)
        hardware_form.addRow(hardware_note)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #ff5d73; font-weight: 600;")
        self.error.setVisible(False)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        box.addWidget(appearance_box)
        box.addWidget(language_box)
        box.addWidget(ffmpeg_box)
        box.addWidget(hardware_box)
        box.addWidget(self.error)
        box.addWidget(buttons)
        self.resize(620, self.sizeHint().height())

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Folder that holds ffmpeg and "
                                                                "ffprobe"), self.ffmpeg_path.text())
        if folder:
            self.ffmpeg_path.setText(folder)

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(True)

    def accept(self) -> None:
        """Check the FFmpeg choice before saving anything; a bad choice keeps the dialog open."""
        override = self.ffmpeg_path.text().strip()
        saved = self.settings.value("ffmpeg_path", "", type=str)
        if self.ffmpeg_path.isEnabled() and override != saved:
            try:
                tools = ffmpeg.detect(override or None)
            except ffmpeg.FFmpegNotFound:
                self._fail(self.tr("FFmpeg was not found."))
                return
            if override and not ffmpeg.uses_override(tools, override):
                self._fail(self.tr("ffmpeg and ffprobe were not both found in {0}.")
                           .format(override))
                return
            if not tools.version_text:
                self._fail(self.tr("The program in {0} did not answer as FFmpeg.")
                           .format(override))
                return
            if tools.too_old:
                self._fail(self.tr("That FFmpeg is version {0}; avOpenKit needs {1} or newer.")
                           .format(tools.version_text,
                                   ".".join(map(str, ffmpeg.MIN_VERSION))))
                return
            self.settings.setValue("ffmpeg_path", override)
            self.tools = tools
        choice = self.language.currentData()
        before = self.settings.value("language", "", type=str)
        if choice != before:
            self.language_changed = (languages.effective(choice, self._folder)
                                     != languages.effective(before, self._folder))
            self.settings.setValue("language", choice)
        if self.appearance.currentData() != self.settings.value("theme", "dark", type=str):
            self.settings.setValue("theme", self.appearance.currentData())
            self.theme_changed = True
        if self.hardware.isEnabled():
            chosen = self.hardware.currentData()
            if chosen != self.settings.value("hardware", "", type=str):
                self.settings.setValue("hardware", chosen)
                self.hardware_changed = True
        super().accept()


def licence_line(tools: Tools) -> str:
    return ffmpeg.build_licence(tools.configuration)


class AboutDialog(QDialog):
    def __init__(self, tools: Tools, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("About avOpenKit"))
        heading = QLabel(f"<h2>avOpenKit {__version__}</h2>")
        intro = QLabel(self.tr(
            "Guided tasks for everyday video and audio jobs. Every task shows the exact FFmpeg "
            "command it runs, and your original file is never overwritten."))
        intro.setWordWrap(True)
        licence = QLabel(self.tr(
            "Copyright © 2026 Rajiv Tyagi, T&C Technology.<br>"
            "avOpenKit is free software under the GNU General Public License, version 3. It "
            "comes with no warranty.<br>"
            "Source code: <a href=\"{0}\">{0}</a>").format(PROJECT_URL))
        licence.setWordWrap(True)
        licence.setOpenExternalLinks(True)

        build = ffmpeg.build_licence(tools.configuration)
        if ffmpeg.is_bundled(tools):
            origin = self.tr("supplied with avOpenKit")
        else:
            origin = self.tr("installed on this computer, not supplied by avOpenKit")
        self.ffmpeg_summary = QLabel(self.tr("Version {0}, {1}.<br>Program: {2}<br>"
                                             "Licence of this build: {3}").format(
            tools.version_text or "?", origin, tools.ffmpeg,
            self.tr("contains non-free parts and may not be redistributed")
            if build == "nonfree" else build))
        self.ffmpeg_summary.setWordWrap(True)
        self.ffmpeg_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.configuration = QPlainTextEdit(tools.configuration or self.tr("(not reported)"))
        self.configuration.setReadOnly(True)
        self.configuration.setMaximumHeight(110)
        ffmpeg_box = QGroupBox(self.tr("FFmpeg in use"))
        ffmpeg_layout = QVBoxLayout(ffmpeg_box)
        ffmpeg_layout.addWidget(self.ffmpeg_summary)
        ffmpeg_layout.addWidget(QLabel(self.tr("Build configuration:")))
        ffmpeg_layout.addWidget(self.configuration)

        self.components = QLabel(self.tr(
            "Qt {0} (LGPL v3), including Qt Multimedia and the FFmpeg libraries Qt supplies for "
            "the preview (LGPL).<br>PyQt6 {1} (GPL v3).<br>Python {2}.").format(
            QT_VERSION_STR, PYQT_VERSION_STR, sys.version.split()[0]))
        self.components.setWordWrap(True)
        components_box = QGroupBox(self.tr("Built with"))
        QVBoxLayout(components_box).addWidget(self.components)

        notice = QLabel(self.tr(
            "avOpenKit uses FFmpeg but is not affiliated with or endorsed by the FFmpeg "
            "project. FFmpeg is a trademark of Fabrice Bellard."))
        notice.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        for w in (heading, intro, licence, ffmpeg_box, components_box, notice, buttons):
            box.addWidget(w)
        self.resize(640, self.sizeHint().height())
