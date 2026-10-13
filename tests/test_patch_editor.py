# The table-driven patch editor: it shows a patch, edits it in place, and emits one signal per user edit (never while showing).

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from jv_studio.core import groups, params, patch
from jv_studio.ui.patch_editor import ChoiceCombo, PatchEditor, ValueSpinBox


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp):
    e = PatchEditor()
    e.working = patch.Patch.minimum()
    e.working.name = "Edit Me"
    e.set_patch(e.working)
    e.seen = []
    e.param_committed.connect(lambda *a: e.seen.append(a))
    yield e
    e.deleteLater()


def test_it_is_off_without_a_patch(qapp):
    e = PatchEditor()
    assert not e.isEnabled()


def test_it_shows_values_without_emitting(qapp):
    e = PatchEditor()
    seen = []
    e.param_committed.connect(lambda *a: seen.append(a))
    p = patch.Patch.minimum()
    p.set(patch.COMMON, "patch_tempo", 133)
    e.set_patch(p)
    assert e.widget_for(patch.COMMON, "patch_tempo").value() == 133 and seen == []


def test_every_page_has_a_control_for_every_shown_parameter(editor):
    for block in (patch.COMMON, patch.TONE):
        for _, members in groups.groups(block):
            for param in members:
                for tone in ([None] if block == patch.COMMON else range(4)):
                    editor.widget_for(block, param.key, tone)


def test_a_spin_box_edit_changes_the_patch_and_emits_once(editor):
    editor.widget_for(patch.TONE, "cutoff_frequency", 2).setValue(90)
    assert editor.working.get(patch.TONE, "cutoff_frequency", tone=2) == 90
    assert editor.seen == [(patch.TONE, "cutoff_frequency", 2, 90)]
    assert editor.working.get(patch.TONE, "cutoff_frequency", tone=1) != 90  # only that tone


def test_the_common_block_reports_tone_minus_one(editor):
    editor.widget_for(patch.COMMON, "patch_tempo").setValue(150)
    assert editor.seen == [(patch.COMMON, "patch_tempo", -1, 150)]


def test_a_combo_edit_stores_the_raw_value(editor):
    combo = editor.widget_for(patch.COMMON, "key_assign_mode")
    assert isinstance(combo, ChoiceCombo) and [combo.itemText(i) for i in range(combo.count())] == ["POLY", "SOLO"]
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    assert editor.working.get(patch.COMMON, "key_assign_mode") == 1 and editor.seen[-1][3] == 1


def test_programmatic_selection_in_a_combo_is_not_an_edit(editor):
    editor.widget_for(patch.COMMON, "key_assign_mode").setCurrentIndex(1)
    assert editor.seen == []


def test_a_name_edit_commits_when_finished_and_cleans_the_text(editor):
    box = editor.widget_for(patch.COMMON, "patch_name")
    assert isinstance(box, QLineEdit) and box.text() == "Edit Me"
    box.setText("New Name")
    box.editingFinished.emit()
    assert editor.working.name == "New Name" and editor.seen == [(patch.COMMON, "patch_name", -1, "New Name")]
    box.editingFinished.emit()  # losing focus again changes nothing
    assert len(editor.seen) == 1


def test_a_name_is_limited_to_twelve_characters(editor):
    assert editor.widget_for(patch.COMMON, "patch_name").maxLength() == 12


def test_the_spin_box_shows_and_accepts_the_units_own_text(editor):
    box = editor.widget_for(patch.TONE, "keyboard_range_lower", 0)
    box.setValue(60)
    assert box.text() == "C4"
    box.lineEdit().setText("C#5")
    box.interpretText()
    assert box.value() == 73
    pan = editor.widget_for(patch.COMMON, "patch_pan")
    pan.setValue(64)
    assert pan.text() == "0"


def test_a_value_the_unit_holds_outside_the_choices_is_shown_not_hidden(qapp):
    e = PatchEditor()
    p = patch.Patch.minimum()
    p.common[params.load_table().block(patch.COMMON).param("efx_output_assign").offset] = 1  # DIRECT-1: JV-1080 only
    e.set_patch(p)
    combo = e.widget_for(patch.COMMON, "efx_output_assign")
    assert "DIRECT-1" in combo.currentText() and "not offered" in combo.currentText()


def test_refresh_shows_a_change_made_elsewhere_without_emitting(editor):
    editor.working.set(patch.COMMON, "patch_tempo", 99)
    editor.refresh()
    assert editor.widget_for(patch.COMMON, "patch_tempo").value() == 99 and editor.seen == []


def test_an_unfocused_wheel_does_not_change_a_value(editor, qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    box = editor.widget_for(patch.COMMON, "patch_tempo")
    before = box.value()
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    box.wheelEvent(event)
    assert box.value() == before and editor.seen == []


def _knob(editor, block, key, tone=None):
    return editor.widget_for(block, key, tone).parentWidget().knob


def test_a_knob_drag_shows_the_value_live_and_commits_once_on_release(editor):
    knob = _knob(editor, patch.TONE, "cutoff_frequency", 0)
    box = editor.widget_for(patch.TONE, "cutoff_frequency", 0)
    knob._drag_anchor_y = 10.0  # a drag is under way (the mouse handlers set this)
    knob.setValue(40)
    knob.setValue(55)
    assert box.value() == 55 and editor.seen == [] and editor.working.get(patch.TONE, "cutoff_frequency", tone=0) != 55
    knob._drag_anchor_y = None
    knob.sliderReleased.emit()
    assert editor.seen == [(patch.TONE, "cutoff_frequency", 0, 55)] and editor.working.get(patch.TONE, "cutoff_frequency", tone=0) == 55


def test_a_wheel_or_key_step_on_a_knob_commits_after_a_short_pause_not_per_step(editor, qapp):
    import time

    knob = _knob(editor, patch.TONE, "cutoff_frequency", 0)
    knob.setValue(10)
    knob.setValue(11)
    knob.setValue(12)
    assert editor.seen == []
    deadline = time.monotonic() + 2
    while not editor.seen and time.monotonic() < deadline:
        qapp.processEvents()
    assert editor.seen == [(patch.TONE, "cutoff_frequency", 0, 12)]


def test_typing_in_the_box_moves_the_knob_without_a_second_commit(editor):
    box = editor.widget_for(patch.TONE, "cutoff_frequency", 0)
    box.setValue(77)
    assert _knob(editor, patch.TONE, "cutoff_frequency", 0).value() == 77 and len(editor.seen) == 1


def test_refresh_moves_the_knob_too(editor):
    editor.working.set(patch.TONE, "cutoff_frequency", 99, tone=3)
    editor.refresh()
    assert _knob(editor, patch.TONE, "cutoff_frequency", 3).value() == 99 and editor.seen == []


def test_a_bipolar_parameter_grows_its_arc_from_the_centre(editor):
    assert _knob(editor, patch.COMMON, "patch_pan")._origin_value == 64
    assert _knob(editor, patch.TONE, "coarse_tune", 0)._origin_value == 48  # -48..+48 over 0..96
    assert _knob(editor, patch.TONE, "cutoff_frequency", 0)._origin_value is None


def test_a_double_click_resets_a_knob_to_its_default(editor):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    knob = _knob(editor, patch.COMMON, "patch_pan")
    knob.setValue(100)
    pos = QPointF(5, 5)
    knob.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert knob.value() == 64


def _efx_label(editor, n):
    return editor._knob_parts[(patch.COMMON, None, f"efx_parameter_{n}")][0].text()


def test_efx_knobs_are_named_for_the_chosen_effect_type(editor):
    editor.widget_for(patch.COMMON, "efx_type")  # builds the Common tab
    editor.working.set(patch.COMMON, "efx_type", 23)  # REVERB
    editor.refresh()
    assert [_efx_label(editor, n) for n in (1, 2, 3, 8, 9)] == ["Reverb Type", "Pre Delay Time", "Gate Time", "Output Level", "(not used)"]
    parts = editor._knob_parts[(patch.COMMON, None, "efx_parameter_1")]
    assert (parts[1].minimum(), parts[1].maximum()) == (0, 5) and "REVERB" in parts[2].toolTip()
    assert not editor._knob_parts[(patch.COMMON, None, "efx_parameter_9")][2].isEnabled()


def test_changing_the_effect_type_renames_the_knobs_and_keeps_the_values(editor):
    box = editor.widget_for(patch.COMMON, "efx_parameter_2")
    box.setValue(90)
    editor.seen.clear()
    combo = editor.widget_for(patch.COMMON, "efx_type")
    combo.setCurrentIndex(combo.findData(8))  # ROTARY
    combo.activated.emit(combo.currentIndex())
    assert editor.working.get(patch.COMMON, "efx_type") == 8 and _efx_label(editor, 1) != "EFX Parameter 1"
    assert editor.working.get(patch.COMMON, "efx_parameter_2") == 90 and box.value() == 90  # the value is the patch's, whatever the new meaning
    assert [s[1] for s in editor.seen] == ["efx_type"]


def test_a_value_beyond_the_types_range_is_shown_truthfully(editor):
    editor.working.set(patch.COMMON, "efx_type", 23)  # REVERB: parameter 1 is 0-5
    editor.working.set(patch.COMMON, "efx_parameter_1", 100)
    editor.refresh()
    assert editor.widget_for(patch.COMMON, "efx_parameter_1").value() == 100  # the box shows the real value, the knob just stops at its end
    assert editor._knob_parts[(patch.COMMON, None, "efx_parameter_1")][1].value() == 5
    assert editor.seen == []


# -- wave names ------------------------------------------------------------------------------------------------------------------


def test_the_wave_card_names_the_wave(editor):
    editor.tabs.setCurrentIndex(1)
    editor.working.set(patch.TONE, "wave_group_type", 0, tone=0)
    editor.working.set(patch.TONE, "wave_group_id", 1, tone=0)
    editor.working.set(patch.TONE, "wave_number", 3, tone=0)
    editor.refresh()
    assert editor._wave_labels[0].text() == "INT-A 004  Ac Piano2 pA"
    editor.working.set(patch.TONE, "wave_group_id", 77, tone=0)
    editor.refresh()
    assert "no name known" in editor._wave_labels[0].text()


def test_choosing_a_wave_sets_the_three_parameters_as_one_undo_step(editor, monkeypatch):
    from jv_studio.ui import patch_editor as pe

    editor.tabs.setCurrentIndex(1)
    recorded = []
    editor.edits_recorded.connect(recorded.append)
    monkeypatch.setattr(pe.WavePickerDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(pe.WavePickerDialog, "result_wave", lambda self: (0, 2, 5))  # INT-B 006
    editor._choose_wave(0)
    assert [editor.working.get(patch.TONE, k, tone=0) for k in ("wave_group_type", "wave_group_id", "wave_number")] == [0, 2, 5]
    assert editor._wave_labels[0].text().startswith("INT-B 006")
    assert len(recorded) == 1 and {e[1] for e in recorded[0]} <= {"wave_group_type", "wave_group_id", "wave_number"} and len(recorded[0]) >= 2
    assert {s[1] for s in editor.seen} >= {"wave_group_id", "wave_number"}


def test_the_wave_picker_filters_and_returns_the_chosen_wave(qapp):
    from jv_studio.ui.wave_picker import WavePickerDialog

    d = WavePickerDialog(0, 1, 3)  # INT-A, wave 4 selected
    assert d.list.currentItem().text() == "004  Ac Piano2 pA" and d.result_wave() == (0, 1, 3)
    d.filter_edit.setText("kalimba")
    d.group_combo.setCurrentIndex(d.group_combo.findText("INT-B"))
    assert d.list.count() >= 1 and d.list.item(0).text() == "001  Kalimba"
    d.list.setCurrentRow(0)
    assert d.result_wave() == (0, 2, 0)
    d.filter_edit.setText("zzzzzz")
    assert d.list.count() == 0 and not d.buttons.button(d.buttons.StandardButton.Ok).isEnabled()
