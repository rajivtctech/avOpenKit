"""Start avOpenKit:  python -m avopenkit [file]"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QCoreApplication, QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import languages
from .core import ffmpeg
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("avOpenKit")
    app.setOrganizationName("T&C Technology")
    settings = QSettings()
    languages.install(app, settings.value("language", "", type=str))
    override = settings.value("ffmpeg_path", "", type=str) or None
    try:
        tools = ffmpeg.detect(override)
    except ffmpeg.FFmpegNotFound:
        hint = ("sudo apt install ffmpeg" if sys.platform.startswith("linux")
                else "https://ffmpeg.org/download.html")
        QMessageBox.critical(None, "avOpenKit", QCoreApplication.translate(
            "main",
            "FFmpeg was not found on this computer. avOpenKit needs the ffmpeg and ffprobe "
            "programs.\n\nInstall it with:\n{0}").format(hint))
        return 1
    if override and not ffmpeg.uses_override(tools, override):
        QMessageBox.warning(None, "avOpenKit", QCoreApplication.translate(
            "main",
            "The FFmpeg chosen in Settings was not found in {0}. avOpenKit is using {1} "
            "instead.").format(override, tools.ffmpeg))
    if tools.too_old:
        QMessageBox.warning(None, "avOpenKit", QCoreApplication.translate(
            "main",
            "FFmpeg {0} is installed, but avOpenKit needs version {1} or newer. Some tasks "
            "will fail until FFmpeg is updated.").format(
                tools.version_text, ".".join(map(str, ffmpeg.MIN_VERSION))))
    window = MainWindow(tools)
    window.show()
    args = app.arguments()[1:]
    if args:
        window.open_file(args[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
