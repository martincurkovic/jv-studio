# The performance editor: it shows a performance, edits it in place, and emits one signal per user edit (never while showing).

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit

from jv_studio.core import performance
from jv_studio.ui.knob_control import KnobControl
from jv_studio.ui.patch_editor import ChoiceCombo
from jv_studio.ui.performance_editor import PerformanceEditor


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp):
    e = PerformanceEditor()
    e.working = performance.Performance.minimum()
    e.working.name = "Edit Me"
    e.set_performance(e.working)
    e.seen, e.recorded = [], []
    e.param_committed.connect(lambda *a: e.seen.append(a))
    e.edits_recorded.connect(e.recorded.append)
    yield e
    e.deleteLater()


def test_it_is_off_without_a_performance_and_shows_values_without_emitting(qapp):
    e = PerformanceEditor()
    assert not e.isEnabled()
    seen = []
    e.param_committed.connect(lambda *a: seen.append(a))
    p = performance.Performance.minimum()
    p.set(performance.COMMON, "performance_tempo", 133)
    p.set(performance.PART, "part_level", 99, part=4)
    e.set_performance(p)
    assert e.widget_for(performance.COMMON, "performance_tempo").value() == 133
    assert e.widget_for(performance.PART, "part_level", part=4, grid=True).value() == 99 and seen == []


def test_the_name_is_edited_and_cleaned(editor):
    box = editor.widget_for(performance.COMMON, "performance_name")
    assert isinstance(box, QLineEdit) and box.text() == "Edit Me" and box.maxLength() == 12
    box.setText("New Perf")
    box.editingFinished.emit()
    assert editor.working.name == "New Perf" and editor.seen == [(performance.COMMON, "performance_name", -1, "New Perf")]
    box.editingFinished.emit()
    assert len(editor.seen) == 1


def test_a_mixer_knob_edits_that_part_and_reports_its_number(editor):
    level = editor.widget_for(performance.PART, "part_level", part=5, grid=True)
    assert isinstance(level, KnobControl)
    level.setValue(77)
    assert editor.working.get(performance.PART, "part_level", part=5) == 77 and editor.working.get(performance.PART, "part_level", part=4) == 0
    assert editor.seen == [(performance.PART, "part_level", 5, 77)]


def test_the_on_checkbox_and_channel_combo_in_the_mixer(editor):
    on = editor.widget_for(performance.PART, "receive_switch", part=2, grid=True)
    assert isinstance(on, QCheckBox) and not on.isChecked()
    on.click()
    assert editor.working.get(performance.PART, "receive_switch", part=2) == 1 and editor.seen[-1] == (performance.PART, "receive_switch", 2, 1)
    channel = editor.widget_for(performance.PART, "midi_channel", part=2, grid=True)
    assert isinstance(channel, ChoiceCombo) and [channel.itemText(i) for i in (0, 9, 15)] == ["1", "10", "16"]
    channel.setCurrentIndex(9)
    channel.activated.emit(9)
    assert editor.working.get(performance.PART, "midi_channel", part=2) == 9 and editor.seen[-1] == (performance.PART, "midi_channel", 2, 9)


def test_the_detail_tab_edits_the_part_it_shows_not_part_one(editor):
    editor.select_part(6)
    assert editor.tabs.currentIndex() == 1 and editor.part_combo.currentData() == 6
    editor.working.set(performance.PART, "part_pan", 100, part=6)
    editor.refresh()
    pan = editor.widget_for(performance.PART, "part_pan")
    assert pan.value() == 100
    pan.setValue(30)
    assert editor.working.get(performance.PART, "part_pan", part=6) == 30 and editor.working.get(performance.PART, "part_pan", part=0) == 0
    assert editor.seen[-1] == (performance.PART, "part_pan", 6, 30)
    assert editor.widget_for(performance.PART, "part_pan", part=6, grid=True).value() == 30  # the mixer row follows


def test_a_mixer_edit_shows_in_the_detail_tab_too(editor):
    editor.select_part(3)
    editor.widget_for(performance.PART, "part_level", part=3, grid=True).setValue(55)
    assert editor.widget_for(performance.PART, "part_level").value() == 55
    editor.widget_for(performance.PART, "part_level", part=9, grid=True).setValue(11)
    assert editor.widget_for(performance.PART, "part_level").value() == 55  # another part's edit leaves the shown part alone


def test_choosing_a_patch_sets_three_values_as_one_gesture_and_names_it(editor, monkeypatch):
    from jv_studio.ui import performance_editor as pe

    monkeypatch.setattr(pe.PatchPickerDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(pe.PatchPickerDialog, "result_patch", lambda self: (0, 3, 11))  # PR-A 012
    editor._choose_patch(4)
    assert editor._assignment(4) == [0, 3, 11] and editor._assignment(3) != [0, 3, 11]
    assert len(editor.recorded) == 1 and {e[1] for e in editor.recorded[0]} <= {"patch_group_type", "patch_group_id", "patch_number"} and len(editor.recorded[0]) >= 2
    assert editor._grid_patch[4].text().startswith("PR-A 012  ") and all(e[2] == 4 for e in editor.recorded[0])


def test_usern_patch_names_read_from_the_unit_appear_on_the_part_buttons(editor):
    editor.working.set(performance.PART, "patch_group_id", 1, part=0)
    editor.working.set(performance.PART, "patch_number", 4, part=0)
    editor.refresh()
    assert editor._grid_patch[0].text() == "USER 005"
    editor.set_user_patch_names([f"N{i}" for i in range(128)])
    assert editor._grid_patch[0].text() == "USER 005  N4"


def test_the_effect_knobs_are_named_for_the_chosen_type_here_too(editor):
    editor.working.set(performance.COMMON, "efx_type", 23)  # REVERB
    editor.refresh()
    first = editor.widget_for(performance.COMMON, "efx_parameter_1")
    assert first.name_label.text() == "Reverb Type" and (first.knob.minimum(), first.knob.maximum()) == (0, 5)
    assert not editor.widget_for(performance.COMMON, "efx_parameter_9").isEnabled()
    combo = editor.widget_for(performance.COMMON, "efx_type")
    combo.setCurrentIndex(combo.findData(8))
    combo.activated.emit(combo.currentIndex())
    assert editor.widget_for(performance.COMMON, "efx_parameter_1").name_label.text() != "Reverb Type"
    assert editor.working.get(performance.COMMON, "efx_type") == 8


def test_the_effect_source_names_the_parts(editor):
    combo = editor.widget_for(performance.COMMON, "efx_source")
    assert [combo.itemText(i) for i in (0, 1, 9, 10, 15)] == ["Performance", "Part 1", "Part 9", "Part 11", "Part 16"]


def test_voice_reserve_is_totalled(editor):
    editor.widget_for(performance.COMMON, "voice_reserve_1").setValue(10)
    editor.widget_for(performance.COMMON, "voice_reserve_2").setValue(20)
    assert editor.reserve_label.text() == "Total reserved: 30 of 64 voices"


def test_the_voice_reserve_is_a_column_of_the_mixer_not_a_card_of_knobs(editor):
    from jv_studio.ui.section_card import SectionCard

    setup = editor.tabs.widget(3)
    assert [c.title() for c in setup.findChildren(SectionCard)] == ["Performance"]
    reserve = editor.widget_for(performance.COMMON, "voice_reserve_3")
    assert reserve is editor._common["voice_reserve_3"] and isinstance(reserve, KnobControl) and reserve.name_label.isHidden()
    reserve.setValue(12)
    assert editor.working.get(performance.COMMON, "voice_reserve_3") == 12 and editor.seen[-1] == (performance.COMMON, "voice_reserve_3", -1, 12)
    assert editor.reserve_label.text() == "Total reserved: 12 of 64 voices"


def test_the_jv1080_only_settings_are_not_there(editor):
    assert "keyboard_mode" not in editor._common and "octave_shift" not in editor._detail and "transmit_volume" not in editor._detail
    assert "patch_number" not in editor._detail and "patch_group_id" not in editor._detail  # chosen by name instead


def test_controls_explain_themselves(editor):
    assert "listens to" in editor.widget_for(performance.PART, "midi_channel", part=0, grid=True).toolTip()
    assert "Range: 20 to 250" in editor.widget_for(performance.COMMON, "performance_tempo").toolTip()
    assert "64 voices" in editor.widget_for(performance.COMMON, "voice_reserve_5").toolTip()
