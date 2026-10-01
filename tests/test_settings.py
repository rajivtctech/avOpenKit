"""Settings, About and the language chooser (spec F16, F17, section 5a)."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QSettings
from PyQt6.QtWidgets import QDialog

from avopenkit import __version__, languages
from avopenkit.core import ffmpeg
from avopenkit.core.queue import DONE
from avopenkit.ui.dialogs import AboutDialog, SettingsDialog
from avopenkit.ui.main_window import MainWindow

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="uses shell wrapper scripts")


# ---------------------------------------------------------------- FFmpeg build facts

@pytest.mark.parametrize("configuration, licence", [
    ("--prefix=/usr --enable-shared", "LGPL v2.1 or later"),
    ("--enable-version3 --enable-shared", "LGPL v3 or later"),
    ("--enable-gpl --enable-libx264", "GPL v2 or later"),
    ("--enable-gpl --enable-version3 --enable-libx264", "GPL v3 or later"),
    ("--enable-gpl --enable-nonfree --enable-libfdk-aac", "nonfree"),
    ("", "LGPL v2.1 or later"),
])
def test_build_licence(configuration, licence):
    assert ffmpeg.build_licence(configuration) == licence


def test_uses_override(tools, tmp_path):
    assert not ffmpeg.uses_override(tools, None) and not ffmpeg.uses_override(tools, "")
    assert ffmpeg.uses_override(tools, str(Path(tools.ffmpeg).parent))
    assert ffmpeg.uses_override(tools, tools.ffmpeg)            # the program itself also works
    assert not ffmpeg.uses_override(tools, str(tmp_path))


# ---------------------------------------------------------------- languages

def lrelease():
    """Qt 6's lrelease. A bare `lrelease` on PATH may be a chooser that looks for Qt 5."""
    for candidate in ("/usr/lib/qt6/bin/lrelease", shutil.which("lrelease6"),
                      shutil.which("lrelease-qt6"), shutil.which("lrelease")):
        if candidate and Path(candidate).exists() and subprocess.run(
                [candidate, "-version"], capture_output=True).returncode == 0:
            return candidate
    return None


TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="{code}">
<context><name>MainWindow</name>
  <message><source>Run</source><translation>{run}</translation></message>
  <message><source>Open a file…</source><translation>{open}</translation></message>
</context>
<context><name>TrimPanel</name>
  <message><source>Trim</source><translation>{trim}</translation></message>
</context>
<context><name>tasks</name>
  <message><source>This file has no video.</source><translation>{novideo}</translation></message>
</context>
</TS>
"""


@pytest.fixture
def i18n(tmp_path):
    """A translations folder holding a compiled Hindi file and an uncompiled Tamil one."""
    tool = lrelease()
    if tool is None:
        pytest.skip("lrelease is not installed")
    folder = tmp_path / "i18n"
    folder.mkdir()
    (folder / "avopenkit_hi.ts").write_text(TS.format(
        code="hi", run="चलाएँ", open="फ़ाइल खोलें…", trim="काटें",
        novideo="इस फ़ाइल में वीडियो नहीं है।"), encoding="utf-8")
    subprocess.run([tool, "-silent", str(folder / "avopenkit_hi.ts"), "-qm",
                    str(folder / "avopenkit_hi.qm")], check=True)
    (folder / "avopenkit_ta.ts").write_text(TS.format(
        code="ta", run="x", open="x", trim="x", novideo="x"), encoding="utf-8")
    return folder


def test_only_english_is_offered_until_a_translation_is_compiled():
    assert languages.available() == ["en"]
    assert languages.effective("hi") == "en" and languages.effective("", system="fr") == "en"


def test_every_language_of_the_specification_is_named_in_its_own_script():
    assert list(languages.LANGUAGES) == ["en", "hi", "es", "fr", "bn", "pa", "or", "ta", "te",
                                         "kn", "ml"]
    assert languages.LANGUAGES["hi"] == "हिन्दी" and languages.LANGUAGES["ta"] == "தமிழ்"
    assert "ur" not in languages.LANGUAGES                       # not in version 1 (spec D8b)


def test_a_compiled_translation_is_offered_and_an_uncompiled_one_is_not(i18n):
    assert languages.available(i18n) == ["en", "hi"]             # Tamil has only a .ts


def test_first_run_follows_the_system_language_when_supported(i18n):
    assert languages.effective("", i18n, system="hi") == "hi"
    assert languages.effective("", i18n, system="de") == "en"
    assert languages.effective("", i18n, system="ta") == "en"    # not reviewed yet
    assert languages.effective("en", i18n, system="hi") == "en"  # an explicit choice wins
    assert languages.effective("hi", i18n, system="en") == "hi"


def test_installing_a_language_translates_the_window_and_the_tasks(app, tools, clips, i18n):
    try:
        assert languages.install(app, "hi", i18n) == "hi"
        w = MainWindow(tools)
        try:
            assert w.run_button.text() == "चलाएँ"
            assert w.tasks.item(0).text() == "काटें"
            assert "ffmpeg " not in w.run_button.text()
            w.open_file(clips["main"])
            assert w.console.toPlainText().startswith("ffmpeg -ss")    # commands stay as they are
            # A task message raised from the non-GUI task layer is translated too.
            from avopenkit.tasks import shrink
            from avopenkit.tasks.base import TaskError
            from test_tasks import fake
            with pytest.raises(TaskError, match="वीडियो नहीं"):
                shrink.plan(shrink.Settings(5, 96, Path("o.mp4")), fake(vcodec=None))
        finally:
            w.close()
    finally:
        assert languages.install(app, "en", i18n) == "en"
    w = MainWindow(tools)
    try:
        assert w.run_button.text() == "Run"                      # back to English, nothing left over
    finally:
        w.close()


# ---------------------------------------------------------------- Settings dialog

@pytest.fixture
def window(app, tools):
    w = MainWindow(tools)
    yield w
    w.close()


def choices(dialog):
    return [(dialog.language.itemText(i), dialog.language.itemData(i))
            for i in range(dialog.language.count())]


def test_language_list_shows_only_what_is_available(app, tools, i18n):
    plain = SettingsDialog(QSettings(), tools)
    assert [c[1] for c in choices(plain)] == ["", "en"]
    assert "English" in choices(plain)[0][0]                     # what "follow" means right now
    with_hindi = SettingsDialog(QSettings(), tools, i18n_folder=i18n)
    assert choices(with_hindi)[1:] == [("English", "en"), ("हिन्दी", "hi")]


def test_language_choice_is_saved_and_asks_for_a_restart(app, tools, i18n):
    settings = QSettings()
    d = SettingsDialog(settings, tools, i18n_folder=i18n)
    d.language.setCurrentIndex(d.language.findData("hi"))
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted and d.language_changed
    assert settings.value("language", "", type=str) == "hi" and d.tools is None

    again = SettingsDialog(settings, tools, i18n_folder=i18n)
    assert again.language.currentData() == "hi"                  # remembered
    again.accept()
    assert not again.language_changed

    d = SettingsDialog(settings, tools, i18n_folder=i18n)
    d.language.setCurrentIndex(d.language.findData("hi"))
    d.reject()
    assert settings.value("language", "", type=str) == "hi"


def test_choosing_english_explicitly_on_an_english_system_needs_no_restart(app, tools):
    d = SettingsDialog(QSettings(), tools)
    d.language.setCurrentIndex(d.language.findData("en"))
    d.accept()
    assert QSettings().value("language", "", type=str) == "en" and not d.language_changed


def wrapper_folder(tmp_path, tools, name="ff", banner=None, with_probe=True):
    """A folder of small scripts standing in for another FFmpeg installation."""
    folder = tmp_path / name
    folder.mkdir()
    for prog, real in (("ffmpeg", tools.ffmpeg), ("ffprobe", tools.ffprobe)):
        if prog == "ffprobe" and not with_probe:
            continue
        body = f'exec "{real}" "$@"' if banner is None else f"echo '{banner}'"
        script = folder / prog
        script.write_text(f"#!/bin/sh\n{body}\n")
        script.chmod(0o755)
    return folder


@posix_only
def test_pointing_to_another_ffmpeg_takes_effect_at_once(app, tools, clips, window, tmp_path):
    folder = wrapper_folder(tmp_path, tools)
    d = SettingsDialog(window.settings, window.tools, parent=window)
    assert tools.ffmpeg in d.in_use.text()
    d.ffmpeg_path.setText(str(folder))
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted and not d.error.isVisible()
    assert d.tools is not None and d.tools.ffmpeg == str(folder / "ffmpeg")
    window.apply_settings(d)
    assert window.tools.ffmpeg == str(folder / "ffmpeg") and window.preview.tools is window.tools
    assert str(folder) in window.statusBar().currentMessage()
    assert "Now using FFmpeg" in window.status.text()
    assert window.settings.value("ffmpeg_path", "", type=str) == str(folder)

    window.open_file(clips["main"])                               # probes with the new ffprobe
    out = tmp_path / "via wrapper.mp4"
    window.output.setText(str(out))
    window._output_edited()
    window.run()
    end = time.monotonic() + 30
    while time.monotonic() < end and (window.queue.running or window.queue._go):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    assert window.queue.items[0].status == DONE and out.stat().st_size > 0

    back = SettingsDialog(window.settings, window.tools, parent=window)
    assert back.ffmpeg_path.text() == str(folder)
    back.ffmpeg_path.clear()                                      # "Automatic"
    back.accept()
    window.apply_settings(back)
    assert window.tools.ffmpeg == tools.ffmpeg
    assert window.settings.value("ffmpeg_path", "", type=str) == ""


@posix_only
@pytest.mark.parametrize("make, words", [
    (lambda t, tools: t / "nowhere", "were not both found"),
    (lambda t, tools: wrapper_folder(t, tools, with_probe=False), "were not both found"),
    (lambda t, tools: wrapper_folder(t, tools, banner="ffmpeg version 4.4.2 Copyright"), "needs 6.0"),
    (lambda t, tools: wrapper_folder(t, tools, banner="hello"), "did not answer as FFmpeg"),
])
def test_a_bad_ffmpeg_choice_is_refused_and_nothing_is_saved(app, tools, tmp_path, make, words):
    settings = QSettings()
    d = SettingsDialog(settings, tools)
    d.show()
    d.ffmpeg_path.setText(str(make(tmp_path, tools)))
    d.accept()
    assert d.result() != QDialog.DialogCode.Accepted and d.isVisible()
    assert d.error.isVisible() and words in d.error.text()
    assert d.tools is None and settings.value("ffmpeg_path", "", type=str) == ""
    d.reject()


def test_ffmpeg_cannot_be_changed_while_a_job_runs(app, tools, tmp_path):
    settings = QSettings()
    d = SettingsDialog(settings, tools, busy=True)
    assert not d.ffmpeg_path.isEnabled()
    d.ffmpeg_path.setText(str(tmp_path))                          # even if it were changed
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted and d.tools is None
    assert settings.value("ffmpeg_path", "", type=str) == ""


# ---------------------------------------------------------------- About and the menus

def test_about_says_which_ffmpeg_is_in_use_and_under_what_licence(app, tools):
    d = AboutDialog(tools)
    text = d.ffmpeg_summary.text()
    assert tools.ffmpeg in text and tools.version_text in text
    assert ffmpeg.build_licence(tools.configuration) in text
    assert "not supplied by avOpenKit" in text                    # the system's copy, on Linux
    assert d.configuration.toPlainText() == tools.configuration and "--enable-" in tools.configuration
    assert "PyQt6" in d.components.text() and "GPL v3" in d.components.text()
    whole = " ".join(w.text() for w in d.findChildren(type(d.ffmpeg_summary)))
    assert __version__ in whole and "General Public License, version 3" in whole
    assert "not affiliated" in whole and "github.com/rajivtctech/avOpenKit" in whole


def test_about_flags_a_build_that_may_not_be_redistributed(app, tools):
    nonfree = ffmpeg.Tools(tools.ffmpeg, tools.ffprobe, "7.0", (7, 0),
                           "--enable-gpl --enable-nonfree", frozenset(), frozenset())
    assert "may not be redistributed" in AboutDialog(nonfree).ffmpeg_summary.text()


def test_menus_offer_settings_and_about(window):
    actions = [a.text().replace("&", "") for menu in window.menuBar().actions()
               for a in menu.menu().actions()]
    assert actions == ["Settings…", "About avOpenKit"]
