#!/usr/bin/env python3
"""D9 trial: can the scrub-bar preview use Qt Multimedia, or should it grab frames with ffmpeg?

Makes a 20 s test clip (30 fps, a keyframe every 2 s), then for a set of positions measures
  A. QMediaPlayer + QVideoSink: time from setPosition() to the frame, and how far the delivered
     frame is from the requested position;
  B. `ffmpeg -ss T -i clip -frames:v 1`: time to get one frame (always the exact frame).
Run:  QT_QPA_PLATFORM=offscreen .venv/bin/python trials/preview_trial.py
"""
import os, subprocess, sys, tempfile, time

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

POSITIONS_MS = [0, 500, 1990, 2000, 3333, 7777, 12345, 19000]
FPS = 30


def make_clip(path):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate={FPS}:duration=20",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
         "-c:v", "libx264", "-preset", "veryfast", "-g", "60", "-keyint_min", "60",
         "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
        check=True)


def wait(signal, timeout_ms):
    loop = QEventLoop()
    ok = []
    signal.connect(lambda *a: (ok.append(a), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    try:
        signal.disconnect()
    except TypeError:
        pass
    return ok[0] if ok else None


def trial_qt(path):
    player, sink = QMediaPlayer(), QVideoSink()
    player.setVideoSink(sink)
    t0 = time.monotonic()
    player.setSource(QUrl.fromLocalFile(path))
    deadline = time.monotonic() + 10
    while player.mediaStatus() not in (QMediaPlayer.MediaStatus.LoadedMedia,
                                       QMediaPlayer.MediaStatus.BufferedMedia):
        if time.monotonic() > deadline or player.error() != QMediaPlayer.Error.NoError:
            print("  load failed:", player.errorString(), player.mediaStatus())
            return
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    print(f"  loaded in {1000*(time.monotonic()-t0):.0f} ms, duration {player.duration()} ms, "
          f"seekable {player.isSeekable()}")
    player.pause()
    wait(sink.videoFrameChanged, 2000)
    print("  requested  frame-start  error  time")
    for pos in POSITIONS_MS:
        t = time.monotonic()
        player.setPosition(pos)
        got = wait(sink.videoFrameChanged, 3000)
        dt = 1000 * (time.monotonic() - t)
        if got is None:
            print(f"  {pos:8d}   no frame within 3 s")
            continue
        start = got[0].startTime() / 1000  # µs -> ms
        print(f"  {pos:8d}   {start:9.0f}  {start-pos:+6.0f}  {dt:5.0f} ms")


def trial_ffmpeg(path):
    print("  requested  bytes   time")
    for pos in POSITIONS_MS:
        t = time.monotonic()
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{pos/1000:.3f}", "-i", path, "-frames:v", "1",
             "-vf", "scale=640:-2", "-f", "image2pipe", "-c:v", "ppm", "-"],
            capture_output=True)
        dt = 1000 * (time.monotonic() - t)
        print(f"  {pos:8d}  {len(out.stdout):7d}  {dt:5.0f} ms  {'ok' if out.returncode == 0 and out.stdout else 'FAILED'}")


def main():
    app = QGuiApplication(sys.argv)
    with tempfile.TemporaryDirectory() as d:
        clip = os.path.join(d, "clip.mp4")
        make_clip(clip)
        print("A. Qt Multimedia (QMediaPlayer + QVideoSink)")
        trial_qt(clip)
        print("B. ffmpeg single-frame grab")
        trial_ffmpeg(clip)


if __name__ == "__main__":
    main()
