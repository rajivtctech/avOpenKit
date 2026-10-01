"""Start avOpenKit:  python -m avopenkit [file]"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox

from .core import ffmpeg
from .ui.main_window import MainWindow


def install_translation(app: QApplication) -> None:
    """Load avopenkit_<language>.qm when one is shipped for the system language (spec F17)."""
    translator = QTranslator(app)
    folder = Path(__file__).resolve().parent / "i18n"
    if translator.load(QLocale.system(), "avopenkit", "_", str(folder)):
        app.installTranslator(translator)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("avOpenKit")
    app.setOrganizationName("T&C Technology")
    install_translation(app)
    try:
        tools = ffmpeg.detect()
    except ffmpeg.FFmpegNotFound:
        hint = ("sudo apt install ffmpeg" if sys.platform.startswith("linux")
                else "https://ffmpeg.org/download.html")
        QMessageBox.critical(None, "avOpenKit", QCoreApplication.translate(
            "main",
            "FFmpeg was not found on this computer. avOpenKit needs the ffmpeg and ffprobe "
            "programs.\n\nInstall it with:\n{0}").format(hint))
        return 1
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
