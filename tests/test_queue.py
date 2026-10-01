"""The job queue (spec F8)."""

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QMessageBox

from avopenkit.core import probe
from avopenkit.core.job import Job, Plan
from avopenkit.core.queue import CANCELLED, DONE, FAILED, RUNNING, WAITING, JobQueue
from avopenkit.tasks import convert, trim
from avopenkit.ui.main_window import MainWindow
from conftest import make_clip


def wait_until(app, condition, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if condition():
            return True
    return False


def idle(queue):
    return lambda: not queue.running and not queue._go


def trim_plan(tools, clip, out, start=1, end=3):
    return trim.plan(trim.Settings(start, end, output=out), probe.probe(clip, tools), tools)


@pytest.fixture
def queue(app, tools):
    q = JobQueue(tools)
    yield q
    q.shutdown()
    wait_until(app, lambda: not q.running, 10)


# ---------------------------------------------------------------- the queue itself

def test_items_run_one_after_another_in_order(app, queue, tools, clips, tmp_path):
    outs = [tmp_path / f"{n}.mp4" for n in "abc"]
    order = []
    queue.item_started.connect(order.append)
    items = [queue.add(o.name, trim_plan(tools, clips["main"], o)) for o in outs]
    assert [i.status for i in items] == [WAITING] * 3 and not queue.running
    assert queue.claimed() == {o.resolve() for o in outs}
    queue.start()
    assert queue.running and items[0].status == RUNNING and items[1].status == WAITING
    assert wait_until(app, idle(queue))
    assert [i.status for i in items] == [DONE] * 3 and order == [i.id for i in items]
    assert all(o.stat().st_size > 0 for o in outs)
    assert [i.result for i in items] == outs and queue.claimed() == set()
    assert all(i.progress == 1.0 and i.log for i in items)


def test_a_failed_item_does_not_stop_the_queue(app, queue, tools, clips, tmp_path):
    good1, bad, good2 = (tmp_path / n for n in ("1.mp4", "bad.mp4", "2.mp4"))
    a = queue.add("a", trim_plan(tools, clips["main"], good1))
    broken = trim_plan(tools, clips["main"], bad)
    broken.jobs[0].args.insert(-1, "-no_such_option")
    b = queue.add("b", broken)
    c = queue.add("c", trim_plan(tools, clips["main"], good2))
    queue.start()
    assert wait_until(app, idle(queue))
    assert (a.status, b.status, c.status) == (DONE, FAILED, DONE)
    assert not bad.exists() and b.result is None and "no_such_option" in b.log


def test_cancel_stops_the_queue_and_start_resumes_it(app, queue, tools, clips, tmp_path):
    long_clip = make_clip(tools, tmp_path / "long.mp4", seconds=60, size="1280x720")
    slow_out, next_out = tmp_path / "slow.webm", tmp_path / "next.mp4"
    slow = queue.add("slow", convert.plan(convert.Settings("webm", output=slow_out),
                                          probe.probe(long_clip, tools), tools))
    nxt = queue.add("next", trim_plan(tools, clips["main"], next_out))
    queue.start()
    assert wait_until(app, lambda: slow.progress > 0, 20)
    queue.cancel()
    assert wait_until(app, lambda: not queue.running, 10)
    assert slow.status == CANCELLED and not slow_out.exists()
    assert nxt.status == WAITING                         # not started behind the user's back
    queue.start()
    assert wait_until(app, idle(queue))
    assert nxt.status == DONE and next_out.exists()


def test_remove_and_clear(app, queue, tools, clips, tmp_path):
    a = queue.add("a", trim_plan(tools, clips["main"], tmp_path / "a.mp4"))
    b = queue.add("b", trim_plan(tools, clips["main"], tmp_path / "b.mp4"))
    assert queue.remove(b.id) and queue.items == [a] and not queue.remove(999)
    queue.start()
    assert not queue.remove(a.id)                        # a running item cannot be removed
    assert wait_until(app, idle(queue))
    assert not (tmp_path / "b.mp4").exists()
    queue.add("c", trim_plan(tools, clips["main"], tmp_path / "c.mp4"))
    queue.clear_finished()
    assert [i.title for i in queue.items] == ["c"]


def test_each_item_work_folder_is_removed_when_it_ends(app, queue, tools, clips, tmp_path):
    work = tmp_path / "job0"
    work.mkdir()
    (work / "scratch").write_text("x")
    queue.add("a", trim_plan(tools, clips["main"], tmp_path / "a.mp4"), workdir=work)
    queue.start()
    assert wait_until(app, idle(queue))
    assert not work.exists()


def test_item_whose_support_file_is_missing_fails_and_the_queue_goes_on(app, queue, tools,
                                                                       clips, tmp_path):
    plan = Plan([Job(["-i", "x", "y"], [tmp_path / "y"])],
                copy_files=[(tmp_path / "gone.srt", tmp_path / "w" / "subs.srt")])
    a = queue.add("a", plan)
    b = queue.add("b", trim_plan(tools, clips["main"], tmp_path / "b.mp4"))
    queue.start()
    assert wait_until(app, idle(queue))
    assert a.status == FAILED and "gone.srt" in a.log and b.status == DONE


# ---------------------------------------------------------------- the window

@pytest.fixture
def window(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    w.open_file(clips["main"])
    yield w
    w.close()


def test_add_to_queue_keeps_jobs_apart(app, window):
    window.tasks.setCurrentRow(1)                         # Shrink: two passes, a pass-log file
    window.panel().size.setValue(0.5)
    first_name, first_cmd = window.output.text(), window.console.toPlainText()
    window.add_to_queue()
    assert not window.queue.running and "Press Start" in window.status.text()
    second_name, second_cmd = window.output.text(), window.console.toPlainText()
    assert second_name != first_name                      # the first name is spoken for
    assert "job0" in first_cmd and "job1" in second_cmd   # separate pass-log folders
    window.add_to_queue()
    assert window.queue_list.count() == 2 and "2 waiting" in window.queue_label.text()
    assert window.start_button.isEnabled()

    window.start_queue()
    assert wait_until(app, idle(window.queue))
    assert [i.status for i in window.queue.items] == [DONE, DONE]
    for name in (first_name, second_name):
        assert 0 < Path(name).stat().st_size <= 500_000
        Path(name).unlink()
    assert "done" in window.queue_list.item(0).text()
    assert not list(window._workdir.glob("job[01]"))      # both work folders cleaned up
    assert not window.start_button.isEnabled() and not window.cancel_button.isEnabled()


def test_two_jobs_cannot_claim_the_same_result(window, tmp_path):
    out = tmp_path / "same.mp4"
    window.output.setText(str(out))
    window._output_edited()
    window.add_to_queue()
    window.output.setText(str(out))
    window._output_edited()
    window.add_to_queue()
    assert len(window.queue.items) == 1 and "already writes same.mp4" in window.status.text()


def test_form_stays_usable_and_jobs_can_be_added_while_one_runs(app, window, tools, tmp_path):
    long_clip = make_clip(tools, tmp_path / "long.mp4", seconds=40, size="1280x720")
    window.open_file(long_clip)
    window.tasks.setCurrentRow(2)
    panel = window.panel()
    panel.target.setCurrentIndex(panel.target.findData("webm"))
    slow_out = tmp_path / "slow.webm"
    window.output.setText(str(slow_out))
    window._output_edited()
    window.run()
    assert window.queue.running and window.tasks.isEnabled() and window.stack.isEnabled()

    window.tasks.setCurrentRow(3)                         # Extract audio, while that runs
    assert window.console.toPlainText().startswith("ffmpeg ") and window.run_button.isEnabled()
    audio_out = Path(window.output.text())
    window.run()                                          # joins the queue behind the first
    assert [i.status for i in window.queue.items] == [RUNNING, WAITING]
    window.queue.runner.cancel()                          # end the slow one; the queue goes on
    assert wait_until(app, idle(window.queue))
    assert [i.status for i in window.queue.items] == [CANCELLED, DONE]
    assert audio_out.exists() and not slow_out.exists()
    audio_out.unlink()


def test_selecting_a_queue_item_shows_its_outcome(app, window, tmp_path):
    good, bad = tmp_path / "good.mp4", tmp_path / "bad.mp4"
    window.output.setText(str(good))
    window._output_edited()
    window.add_to_queue()
    window.expert_box.setChecked(True)
    window.output.setText(str(bad))
    window._output_edited()
    window.console.setPlainText(window.console.toPlainText().replace("-c copy", "-c nonsense"))
    window.add_to_queue()
    window.start_queue()
    assert wait_until(app, idle(window.queue))
    window.queue_list.setCurrentRow(0)
    assert "Done: good.mp4" in window.status.text() and window.play.isVisible()
    window.queue_list.setCurrentRow(1)
    assert "Failed" in window.status.text() and not window.play.isVisible()
    assert "nonsense" in window.log.toPlainText()
    window.queue_list.setCurrentRow(0)
    window.remove_button.click()
    assert [i.title for i in window.queue.items] == ["Trim → bad.mp4"]
    window.clear_button.click()
    assert window.queue_list.count() == 0


def test_existing_result_is_asked_about_when_queued_not_when_run(app, window, tmp_path,
                                                               monkeypatch):
    out = tmp_path / "old.mp4"
    out.write_bytes(b"old")
    window.output.setText(str(out))
    window._output_edited()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.add_to_queue()
    assert not window.queue.items and out.read_bytes() == b"old"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.add_to_queue()
    assert window.queue.items[0].overwrite
    window.start_queue()
    assert wait_until(app, idle(window.queue))
    assert window.queue.items[0].status == DONE and out.stat().st_size > 100


def test_an_edited_command_keeps_its_edit_but_moves_to_a_new_work_folder(window):
    window.tasks.setCurrentRow(1)
    window.panel().size.setValue(0.5)
    window.expert_box.setChecked(True)
    window.console.setPlainText(window.console.toPlainText().replace("-preset medium",
                                                                     "-preset veryfast"))
    assert "job0" in window.console.toPlainText()
    out = Path(window.plan.outputs[-1])
    window.add_to_queue()
    text = window.console.toPlainText()
    assert "veryfast" in text and "job1" in text and "job0" not in text and window._edited
    assert window.queue.items[0].plan.jobs[0].args.count("veryfast") == 1
    window.add_to_queue()                                 # same result name as the queued job
    assert len(window.queue.items) == 1 and "already writes" in window.status.text()
    assert not out.exists()
