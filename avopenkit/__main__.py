"""Start avOpenKit:  python -m avopenkit [file]"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import __version__, languages
from .core import ffmpeg
from .ui import icons, theme
from .ui.main_window import MainWindow


def self_test(path: str | None) -> int:
    """Check that this build can do its job, and say what it found. Used to test packaged
    builds:  avOpenKit --self-test [media file]"""
    import os
    import time

    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QEventLoop

    lines: list[str] = []

    def print(text: str) -> None:      # noqa: A001 - also kept for the report file
        lines.append(text)
        if sys.stdout is not None:
            sys.stdout.write(text + "\n")
            sys.stdout.flush()
        report = os.environ.get("AVOPENKIT_SELFTEST_REPORT")
        if report:                     # a windowed Windows program has no console to print to
            with open(report, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

    app = QApplication(sys.argv[:1])
    # Keep the test out of the user's real settings.
    scratch = tempfile.TemporaryDirectory(prefix="avopenkit-selftest-")
    app.setOrganizationName("avOpenKit-selftest")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, scratch.name)
    theme.apply(app, "dark")
    print(f"avOpenKit {__version__}; Python {sys.version.split()[0]}; Qt {QT_VERSION_STR}; "
          f"PyQt {PYQT_VERSION_STR}; packaged: {bool(getattr(sys, 'frozen', False))}")
    try:
        tools = ffmpeg.detect()
    except ffmpeg.FFmpegUnusable as e:
        print(f"FFmpeg: found at {e.path} but it could not be started")
        print("self-test FAILED")
        return 1
    except ffmpeg.FFmpegNotFound:
        print("FFmpeg: NOT FOUND")
        print("self-test FAILED")
        return 1
    # A message box would wait for ever with nobody to answer it; record it and carry on.
    asked: list[str] = []
    for kind in ("warning", "critical", "question", "information"):
        setattr(QMessageBox, kind, staticmethod(
            lambda *a, _k=kind, **k: (asked.append(f"{_k}: {a[2] if len(a) > 2 else ''}"),
                                      QMessageBox.StandardButton.No)[1]))
    print(f"FFmpeg: {tools.version_text} at {tools.ffmpeg}; {len(tools.encoders)} encoders, "
          f"{len(tools.filters)} filters; supplied with avOpenKit: {ffmpeg.is_bundled(tools)}")
    window = MainWindow(tools)
    print(f"window: {window.tasks.count()} tasks")
    ok = window.tasks.count() == 8
    # The icons are drawn from SVG at run time; a packaged build that lost Qt's SVG support
    # would show empty squares.
    drawn = icons.pixmap("trim", "#ffffff", 24).toImage()
    painted = sum(1 for x in range(drawn.width()) for y in range(drawn.height())
                  if (drawn.pixel(x, y) >> 24) > 40)
    print("icons: " + ("drawn" if painted > 40 else "NOT DRAWN"))
    ok = ok and painted > 40
    if path:
        ok = window.open_file(path) and ok
        print(f"opened: {window.inspector.text()}")
        print(f"command: {window.console.toPlainText()[:90]}...")
        end = time.monotonic() + 8
        while time.monotonic() < end and not window.preview.got_frame and not window.preview.stills:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        print("preview: " + ("Qt player delivered a picture" if window.preview.got_frame
                             else "fell back to still pictures" if window.preview.stills
                             else "NO PICTURE"))
        ok = ok and (window.preview.got_frame or window.preview.stills)

        # A real job, start to finish, through the same queue and runner the buttons use.
        result = Path(scratch.name) / ("selftest-result" + Path(path).suffix)
        panel = window.panel()
        panel.start.setValue(0.5)
        panel.end.setValue(min(2.0, window.media.duration))
        window.output.setText(str(result))
        window._output_edited()
        window.run()
        end = time.monotonic() + 60
        while time.monotonic() < end and (window.queue.running or window.queue.waiting()):
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        status = window.queue.items[-1].status if window.queue.items else "not started"
        size = result.stat().st_size if result.exists() else 0
        print(f"job: trim {status}, result {size} bytes")
        ok = ok and status == "done" and size > 0
    window.close()
    for message in asked:
        print("message box: " + " ".join(message.split())[:200])
    ok = ok and not asked
    print("self-test " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"avOpenKit {__version__}")
        return 0
    if "--self-test" in sys.argv[1:]:
        rest = [a for a in sys.argv[1:] if a != "--self-test"]
        return self_test(rest[0] if rest else None)
    app = QApplication(sys.argv)
    app.setApplicationName("avOpenKit")
    app.setOrganizationName("T&C Technology")
    settings = QSettings()
    theme.apply(app, settings.value("theme", "dark", type=str))
    app.setWindowIcon(QIcon(icons.logo(64)))
    languages.install(app, settings.value("language", "", type=str))
    override = settings.value("ffmpeg_path", "", type=str) or None
    try:
        tools = ffmpeg.detect(override)
    except ffmpeg.FFmpegUnusable as e:
        QMessageBox.critical(None, "avOpenKit", QCoreApplication.translate(
            "main",
            "FFmpeg was found at {0}, but it could not be started. Check that it runs in a "
            "terminal, or choose another FFmpeg in Settings.").format(e.path))
        return 1
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
