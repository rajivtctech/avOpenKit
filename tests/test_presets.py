"""Presets (spec F10)."""

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMessageBox

from avopenkit.core.presets import BUILTIN, PresetStore, clean_name, natural
from avopenkit.ui.main_window import MainWindow


@pytest.fixture
def store(app):
    return PresetStore(QSettings())


def test_shrink_has_built_in_sizes_in_sensible_order(store):
    assert store.names("shrink") == ["10 MB", "25 MB", "50 MB", "100 MB"]
    assert store.get("shrink", "25 MB") == {"size": 25.0}
    assert store.names("trim") == []


def test_built_in_presets_name_sizes_not_services():
    """Service limits are added at release from published figures (spec D7), not guessed."""
    for name in BUILTIN["shrink"]:
        assert name.replace(" MB", "").isdigit()


def test_save_get_delete(store):
    assert store.save("trim", "  Exact   high  ", {"exact": True}) == "Exact high"
    assert store.get("trim", "Exact high") == {"exact": True}
    store.save("trim", "Exact high", {"exact": False})            # same name: replaced
    assert store.get("trim", "Exact high") == {"exact": False} and store.names("trim") == ["Exact high"]
    store.delete("trim", "Exact high")
    store.delete("trim", "never existed")
    assert store.names("trim") == [] and store.get("trim", "Exact high") is None
    with pytest.raises(ValueError):
        store.save("trim", "   ", {})


def test_built_ins_are_editable_and_stay_deleted(store, app):
    store.save("shrink", "25 MB", {"size": 24.0})
    store.delete("shrink", "100 MB")
    again = PresetStore(QSettings())                              # as after a restart
    assert again.get("shrink", "25 MB") == {"size": 24.0}
    assert "100 MB" not in again.names("shrink")
    again.save("shrink", "Mine", {"size": 7.0})
    again.restore_builtins("shrink")
    assert again.get("shrink", "25 MB") == {"size": 25.0} and "100 MB" in again.names("shrink")
    assert again.get("shrink", "Mine") == {"size": 7.0}           # the user's own are kept


def test_presets_survive_non_latin_names_and_damaged_storage(store):
    store.save("gif", "छोटा GIF", {"width": 240})
    assert PresetStore(QSettings()).get("gif", "छोटा GIF") == {"width": 240}
    QSettings().setValue("presets/gif", "{not json")
    assert store.names("gif") == []


def test_name_helpers():
    assert clean_name("  a   b  ") == "a b" and len(clean_name("x" * 200)) == 60
    assert sorted(["100 MB", "9 MB", "25 MB"], key=natural) == ["9 MB", "25 MB", "100 MB"]


# ---------------------------------------------------------------- the window

@pytest.fixture
def window(app, tools, clips):
    w = MainWindow(tools)
    w.show()
    w.open_file(clips["main"])
    yield w
    w.close()


def names(window):
    return [window.preset_box.itemText(i) for i in range(1, window.preset_box.count())]


def test_choosing_a_built_in_size_sets_the_form(window):
    window.tasks.setCurrentRow(1)
    assert names(window) == ["10 MB", "25 MB", "50 MB", "100 MB"]
    window.preset_box.setCurrentIndex(window.preset_box.findData("10 MB"))
    window._preset_chosen(window.preset_box.currentIndex())
    assert window.panel().size.value() == 10.0 and "10 MB" in window.notes.text()
    assert window.preset_box.currentData() == "10 MB" and "applied" in window.status.text()
    window.panel().size.setValue(11.0)                    # no longer that preset
    assert window.preset_box.currentData() is None


def test_presets_belong_to_their_task(window):
    window.tasks.setCurrentRow(1)
    assert names(window)
    window.tasks.setCurrentRow(0)
    assert names(window) == []


def test_save_apply_and_remember_a_preset(app, tools, window, monkeypatch):
    window.tasks.setCurrentRow(6)                         # Make a GIF
    panel = window.panel()
    panel.start.setValue(2.0)
    panel.length.setValue(1.5)
    panel.width.setValue(240)
    panel.fps.setValue(8)
    assert window.save_preset_as("Small loop") == "Small loop"
    assert names(window) == ["Small loop"] and window.preset_box.currentData() == "Small loop"
    panel.width.setValue(600)
    panel.fps.setValue(20)
    assert window.apply_preset("Small loop")
    assert (panel.width.value(), panel.fps.value(), panel.length.value()) == (240, 8, 1.5)
    assert panel.start.value() == 2.0                     # times belong to the file, not the preset
    assert "scale=240" in window.console.toPlainText()

    other = MainWindow(tools)                             # presets are kept between runs
    try:
        other.tasks.setCurrentRow(6)
        assert names(other) == ["Small loop"]
    finally:
        other.close()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    panel.width.setValue(100)
    assert window.save_preset_as("Small loop") is None    # declined: the old one stays
    assert window.presets.get("gif", "Small loop")["width"] == 240
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert window.save_preset_as("Small loop") == "Small loop"
    assert window.presets.get("gif", "Small loop")["width"] == 100

    window.preset_box.setCurrentIndex(window.preset_box.findData("Small loop"))
    window._delete_preset()
    assert names(window) == [] and "deleted" in window.status.text()
    window._delete_preset()                               # nothing chosen
    assert "Choose the preset" in window.status.text()
    assert window.save_preset_as("   ") is None


def test_simple_mode_presets_hold_no_expert_values(window):
    panel = window.panel()                                # Trim
    panel.exact.setChecked(True)
    panel.crf.setValue(30)                                # hidden in simple mode
    window.save_preset_as("Exact")
    assert window.presets.get("trim", "Exact") == {"exact": True}


def test_expert_preset_round_trip_and_warning_in_simple_mode(window):
    window.expert_box.setChecked(True)
    panel = window.panel()
    panel.exact.setChecked(True)
    panel.crf.setValue(27)
    panel.preset.setCurrentText("slow")
    panel.kbps.setValue(128)
    window.save_preset_as("Archive")
    assert window.presets.get("trim", "Archive") == {
        "exact": True, "crf": 27, "preset": "slow", "audio_kbps": 128, "_expert": True}

    panel.fast.setChecked(True)
    panel.crf.setValue(18)
    panel.preset.setCurrentText("medium")
    window.apply_preset("Archive")
    assert panel.exact.isChecked() and panel.crf.value() == 27
    assert panel.preset.currentText() == "slow" and "-crf 27 -preset slow" in window.console.toPlainText()
    assert "applied" in window.status.text()

    window.expert_box.setChecked(False)
    window.apply_preset("Archive")
    assert "saved in expert mode" in window.status.text()
    assert "-crf 18" in window.console.toPlainText()      # expert values not used in simple mode

    panel.fast.setChecked(True)                           # radio pair restores both ways
    window.save_preset_as("Fast")
    window.apply_preset("Archive")
    assert panel.exact.isChecked()
    window.apply_preset("Fast")
    assert panel.fast.isChecked() and "-c copy" in window.console.toPlainText()


def test_every_task_can_save_and_reapply_its_own_state(window, clips, srt):
    window.expert_box.setChecked(True)
    for row in range(window.tasks.count()):
        window.tasks.setCurrentRow(row)
        panel = window.panel()
        state = panel.state()
        assert state.get("_expert") and len(state) > 1, panel.title()
        window.save_preset_as("probe")
        assert not panel.set_state(window.presets.get(panel.module.ID, "probe"))
        assert panel.state() == state


def test_a_preset_from_another_version_does_not_break_the_form(window):
    window.presets.save("trim", "Odd", {"exact": True, "crf": "not a number", "unknown": 5})
    assert window.apply_preset("Odd") and window.panel().exact.isChecked()
