# The table-driven patch editor: it shows a patch, edits it in place, and emits one signal per user edit (never while showing).

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from jv1010editor.core import groups, params, patch
from jv1010editor.ui.patch_editor import ChoiceCombo, PatchEditor, ValueSpinBox


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
