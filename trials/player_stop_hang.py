#!/usr/bin/env python3
"""Trial: does QMediaPlayer.stop() hang when an audio output is attached?

Loads a clip, pauses, waits a varying few milliseconds, then stops - many times over.
  mode "audio"    QAudioOutput attached (muted, so nothing is heard)
  mode "noaudio"  no audio output

Run:  QT_QPA_PLATFORM=offscreen timeout 120 .venv/bin/python trials/player_stop_hang.py audio CLIP 150
A clean batch prints "RESULT ... cycles ok". A hung batch prints nothing more and is ended by
`timeout`: stop() blocks the main thread inside Qt, so no Python code can report it.

Seen on Ubuntu 26.04, PyQt6 6.11.0 / PyQt6-Qt6 6.11.2, PulseAudio on PipeWire 1.6.2
(2026-10-01): with audio about 1 batch in 4 hung; without audio none did in over 1000 cycles.
"""
import sys
import time

from PyQt6.QtCore import QEventLoop, QT_VERSION_STR, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QApplication

mode, clip, cycles = sys.argv[1], sys.argv[2], int(sys.argv[3])
app = QApplication([])


def spin(ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)


for i in range(cycles):
    player, widget, audio = QMediaPlayer(), QVideoWidget(), QAudioOutput()
    player.setVideoOutput(widget)
    if mode == "audio":
        audio.setMuted(True)
        player.setAudioOutput(audio)
    player.setSource(QUrl.fromLocalFile(clip))
    player.pause()
    spin(i % 40 * 6)
    player.pause()
    print(f"cycle {i}", end="\r", flush=True)
    player.stop()
    player.setSource(QUrl())
    del player, widget, audio
print(f"RESULT Qt {QT_VERSION_STR} {mode}: {cycles} cycles ok")
