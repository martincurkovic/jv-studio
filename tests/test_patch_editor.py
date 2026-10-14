# The table-driven patch editor: it shows a patch, edits it in place, and emits one signal per user edit (never while showing).

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QSizePolicy, QWidget

from jv_studio.core import groups, params, patch
from jv_studio.ui.knob_control import parse_display_text
from jv_studio.ui.patch_editor import ChoiceCombo, PatchEditor


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
    assert isinstance(combo, ChoiceCombo) and [combo.itemText(i) for i in range(combo.count())] == ["Poly", "Solo"]
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


def test_the_readout_shows_the_units_own_text(editor):
    notes = editor.widget_for(patch.TONE, "keyboard_range_lower", 0)
    notes.setValue(60)
    assert notes.text() == "C4"
    pan = editor.widget_for(patch.COMMON, "patch_pan")
    pan.setValue(64)
    assert pan.text() == "0"
    pan.setValue(40)
    assert pan.text() == "L24"


def test_text_typed_the_way_the_unit_shows_it_is_understood(editor):
    notes = editor.widget_for(patch.TONE, "keyboard_range_lower", 0).param
    assert parse_display_text(notes, "C#5") == 73 and parse_display_text(notes, "c4") == 60
    pan = editor.widget_for(patch.COMMON, "patch_pan").param
    assert parse_display_text(pan, "L24") == 40 and parse_display_text(pan, "0") == 64 and parse_display_text(pan, "30R") == 94
    tune = editor.widget_for(patch.TONE, "coarse_tune", 0).param  # -48..+48 over raw 0..96
    assert parse_display_text(tune, "12") == 60 and parse_display_text(tune, "+12") == 60 and parse_display_text(tune, "-12") == 36
    assert parse_display_text(tune, "banana") is None and parse_display_text(tune, "99") is None


def test_click_then_type_opens_a_box_and_sets_the_value(editor, qapp):
    knob = _knob(editor, patch.TONE, "cutoff_frequency", 0)
    knob.show()
    knob._begin_type_edit("8")
    box = knob._type_edit
    assert box is not None
    box.setText("85")
    box.returnPressed.emit()
    qapp.processEvents()
    assert editor.widget_for(patch.TONE, "cutoff_frequency", 0).value() == 85 and editor.working.get(patch.TONE, "cutoff_frequency", tone=0) == 85
    assert editor.seen[-1] == (patch.TONE, "cutoff_frequency", 0, 85) and knob._type_edit is None


def test_typing_a_note_name_on_a_note_knob(editor, qapp):
    knob = _knob(editor, patch.TONE, "keyboard_range_lower", 0)
    knob.show()
    knob._begin_type_edit("c")
    knob._type_edit.setText("C#5")
    knob._type_edit.returnPressed.emit()
    qapp.processEvents()
    assert editor.working.get(patch.TONE, "keyboard_range_lower", tone=0) == 73


def test_escape_or_nonsense_in_the_typing_box_changes_nothing(editor, qapp):
    knob = _knob(editor, patch.TONE, "cutoff_frequency", 0)
    knob.show()
    knob._begin_type_edit("9")
    knob._type_edit._cancelled = True
    knob._type_edit.close()
    qapp.processEvents()
    knob._begin_type_edit("x")
    knob._type_edit.setText("zzz")
    knob._type_edit.returnPressed.emit()
    qapp.processEvents()
    assert editor.seen == [] and editor.working.get(patch.TONE, "cutoff_frequency", tone=0) == 0


def test_a_printable_key_on_a_focused_knob_starts_typing_but_a_shortcut_does_not(editor, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    knob = _knob(editor, patch.TONE, "cutoff_frequency", 0)
    knob.show()
    knob.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_5, Qt.KeyboardModifier.NoModifier, "5"))
    assert knob._type_edit is not None
    knob._type_edit._cancelled = True
    knob._type_edit.close()
    qapp.processEvents()
    knob.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier, "z"))
    assert knob._type_edit is None  # Ctrl+Z is Undo, not an entry


def test_a_card_with_many_knobs_puts_the_value_beside_each_knob_and_a_small_one_below(editor):
    editor.tabs.setCurrentIndex(1)
    roomy = editor.widget_for(patch.TONE, "fxm_color", 0)  # the Wave card has 3 knobs
    dense = editor.widget_for(patch.TONE, "filter_envelope_time_1", 0)
    assert roomy.layout().count() == 3 and dense.layout().count() == 2  # name, knob, value stacked vs name over a [knob | value] row


def test_the_two_card_columns_keep_an_exact_half_split_when_cards_collapse(editor, qapp):
    from PySide6.QtWidgets import QScrollArea

    editor.resize(1000, 700)
    editor.show()
    editor.tabs.setCurrentIndex(1)
    qapp.processEvents()
    page = editor.tabs.currentWidget().findChild(QScrollArea).widget()
    columns = [w for w in page.findChildren(QWidget) if w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored and w.parent() is page]
    assert len(columns) == 2
    before = [c.width() for c in columns]
    assert abs(before[0] - before[1]) <= 1
    from jv_studio.ui.section_card import SectionCard

    for card in page.findChildren(SectionCard):
        card.set_collapsed(True, remember=False)
        qapp.processEvents()
        assert [c.width() for c in columns] == before, "collapsing a card moved the columns"
    for card in page.findChildren(SectionCard):
        card.set_collapsed(False, remember=False)
    qapp.processEvents()
    assert [c.width() for c in columns] == before


def test_a_value_the_unit_holds_outside_the_choices_is_shown_not_hidden(qapp):
    e = PatchEditor()
    p = patch.Patch.minimum()
    p.common[params.load_table().block(patch.COMMON).param("efx_output_assign").offset] = 1  # DIRECT-1: JV-1080 only
    e.set_patch(p)
    combo = e.widget_for(patch.COMMON, "efx_output_assign")
    assert "Direct-1" in combo.currentText() and "not offered" in combo.currentText()


def test_refresh_shows_a_change_made_elsewhere_without_emitting(editor):
    editor.working.set(patch.COMMON, "patch_tempo", 99)
    editor.refresh()
    assert editor.widget_for(patch.COMMON, "patch_tempo").value() == 99 and editor.seen == []


def test_an_unfocused_wheel_does_not_change_a_value(editor, qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    control = editor.widget_for(patch.COMMON, "patch_tempo")
    before = control.value()
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    control.knob.wheelEvent(event)
    assert control.value() == before and editor.seen == []


def _knob(editor, block, key, tone=None):
    return editor.widget_for(block, key, tone).knob


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
    return editor.widget_for(patch.COMMON, f"efx_parameter_{n}").name_label.text()


def test_efx_knobs_are_named_for_the_chosen_effect_type(editor):
    editor.widget_for(patch.COMMON, "efx_type")  # builds the Common tab
    editor.working.set(patch.COMMON, "efx_type", 23)  # REVERB
    editor.refresh()
    assert [_efx_label(editor, n) for n in (1, 2, 3, 8, 9)] == ["Reverb Type", "Pre Delay Time", "Gate Time", "Output Level", "(not used)"]
    control = editor.widget_for(patch.COMMON, "efx_parameter_1")
    assert (control.knob.minimum(), control.knob.maximum()) == (0, 5) and "REVERB" in control.toolTip()
    assert not editor.widget_for(patch.COMMON, "efx_parameter_9").isEnabled()


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
    assert editor.widget_for(patch.COMMON, "efx_parameter_1").knob.value() == 5
    assert editor.seen == []


# -- wave names ------------------------------------------------------------------------------------------------------------------


def test_the_wave_card_names_the_wave(editor):
    editor.tabs.setCurrentIndex(1)
    editor.working.set(patch.TONE, "tone_switch", 1, tone=0)
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
    assert len(recorded) == 1 and {e[1] for e in recorded[0]} <= {"wave_group_type", "wave_group_id", "wave_number", "tone_switch"} and len(recorded[0]) >= 2
    assert editor.working.get(patch.TONE, "tone_switch", tone=0) == 1  # the tone was off: choosing a wave switched it on
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


def test_no_wave_turns_the_tone_off_and_keeps_the_wave(editor, monkeypatch):
    from jv_studio.ui import patch_editor as pe

    editor.tabs.setCurrentIndex(1)
    editor.working.set(patch.TONE, "tone_switch", 1, tone=0)
    editor.working.set(patch.TONE, "wave_group_id", 1, tone=0)
    editor.working.set(patch.TONE, "wave_number", 9, tone=0)
    editor.refresh()
    recorded = []
    editor.edits_recorded.connect(recorded.append)

    def pick_none(self):
        self.wants_off = True
        return self.DialogCode.Accepted

    monkeypatch.setattr(pe.WavePickerDialog, "exec", pick_none)
    editor._choose_wave(0)
    assert editor.working.get(patch.TONE, "tone_switch", tone=0) == 0 and editor.working.get(patch.TONE, "wave_number", tone=0) == 9
    assert editor._wave_labels[0].text() == "No wave (tone off)" and "Piano Thump" in editor._wave_labels[0].toolTip()
    assert [e[1] for e in recorded[0]] == ["tone_switch"]
    assert not editor.widget_for(patch.TONE, "tone_switch", 0).isChecked()  # the tone's check box follows


def test_switching_the_tone_back_on_restores_the_wave_label(editor):
    editor.tabs.setCurrentIndex(1)
    editor.working.set(patch.TONE, "wave_group_id", 1, tone=0)
    editor.working.set(patch.TONE, "wave_number", 9, tone=0)
    editor.refresh()
    assert editor._wave_labels[0].text() == "No wave (tone off)"
    editor.widget_for(patch.TONE, "tone_switch", 0).click()  # the check box in the Wave heading
    assert editor._wave_labels[0].text() == "INT-A 010  Piano Thump" and editor.working.get(patch.TONE, "tone_switch", tone=0) == 1


def test_the_picker_has_a_no_wave_button(qapp):
    from jv_studio.ui.wave_picker import WavePickerDialog

    d = WavePickerDialog(0, 1, 0)
    assert not d.wants_off
    d.off_button.click()
    assert d.wants_off


def test_the_pages_have_room_around_their_cards_and_need_no_horizontal_scroll_at_the_default_size(qapp):
    from PySide6.QtWidgets import QScrollArea

    from jv_studio.ui.main_window import MainWindow

    w = MainWindow(start_worker=False)
    w.show()
    w.editor.set_patch(patch.Patch.minimum())
    for i in range(5):
        w.editor.tabs.setCurrentIndex(i)
        qapp.processEvents()
        area = w.editor.tabs.currentWidget().findChild(QScrollArea)
        assert area.horizontalScrollBar().maximum() == 0, f"page {i} scrolls sideways at {w.size()}"
        assert area.widget().layout().contentsMargins().top() >= 8
    w.close()
    w.deleteLater()


def test_drop_downs_show_readable_names_and_the_tooltip_gives_the_units_own(editor):
    editor.tabs.setCurrentIndex(1)
    lfo = editor.widget_for(patch.TONE, "lfo1_waveform", 0)
    assert [lfo.itemText(i) for i in range(3)] == ["Triangle", "Sine", "Saw"]
    assert lfo.itemData(0, Qt.ItemDataRole.ToolTipRole) == "On the unit: TRI"
    reverb = editor.widget_for(patch.COMMON, "reverb_type")
    assert reverb.itemText(reverb.findData(4)) == "Hall 1"
    effect = editor.widget_for(patch.COMMON, "efx_type")
    assert effect.itemText(effect.findData(25)) == "Overdrive → Chorus (serial)"


def test_structure_types_are_named_with_a_description_per_option(editor):
    combo = editor.widget_for(patch.COMMON, "structure_type_1and2")
    assert isinstance(combo, ChoiceCombo) and combo.count() == 10
    assert combo.itemText(0) == "01 Independent" and combo.itemText(2) == "03 Mix → Filter → Booster" and combo.itemText(9) == "10 Filters → Ring Mod + Tone 2"
    assert "independent" in combo.itemData(0, Qt.ItemDataRole.ToolTipRole).lower() and "ring modulator" in combo.itemData(4, Qt.ItemDataRole.ToolTipRole)
    combo.setCurrentIndex(4)
    combo.activated.emit(4)
    assert editor.working.get(patch.COMMON, "structure_type_1and2") == 4  # the raw value is still 0-9


def test_the_booster_is_only_available_for_the_structure_types_that_use_it(editor):
    booster = editor.widget_for(patch.COMMON, "booster_1and2")
    combo = editor.widget_for(patch.COMMON, "structure_type_1and2")
    assert not booster.isEnabled()  # type 01
    for raw, expected in ((2, True), (3, True), (4, False), (0, False)):
        combo.setCurrentIndex(raw)
        combo.activated.emit(raw)
        assert booster.isEnabled() is expected
    other = editor.widget_for(patch.COMMON, "booster_3and4")
    assert not other.isEnabled()  # the 3 & 4 pair has its own structure type
    editor.working.set(patch.COMMON, "structure_type_3and4", 3)
    editor.refresh()
    assert other.isEnabled()


def test_an_ampersand_in_a_parameter_name_is_shown_not_taken_for_a_mnemonic(qapp):
    from PySide6.QtWidgets import QLabel

    editor = PatchEditor()
    editor.widget_for("patch_common", "structure_type_1and2")
    labels = [label.text() for label in editor.findChildren(QLabel)]
    assert "Structure Type 1&&2" in labels  # (Qt shows "&&" as one "&")


# -- the tone's on/off beside the Wave heading, and the Tone Mixer ---------------------------------------------------------------


def test_a_tones_switch_is_a_check_box_in_the_wave_cards_heading(editor):
    from PySide6.QtWidgets import QCheckBox

    from jv_studio.ui.patch_editor import SwitchBox
    from jv_studio.ui.section_card import SectionCard

    editor.tabs.setCurrentIndex(2)  # tone 2
    box = editor.widget_for(patch.TONE, "tone_switch", 1)
    assert isinstance(box, SwitchBox) and isinstance(box, QCheckBox) and box.text() == "On" and not isinstance(box, ChoiceCombo)
    wave_card = next(c for c in editor.tabs.currentWidget().findChildren(SectionCard) if c.title() == "Wave")
    assert box.parent() is not None and wave_card.isAncestorOf(box)
    assert box.isChecked() is False  # a minimum patch has its tones off
    seen = len(editor.seen)
    box.click()
    assert editor.working.get(patch.TONE, "tone_switch", tone=1) == 1 and editor.seen[seen:] == [(patch.TONE, "tone_switch", 1, 1)] and box.isChecked()
    box.click()
    assert editor.working.get(patch.TONE, "tone_switch", tone=1) == 0 and editor.seen[-1] == (patch.TONE, "tone_switch", 1, 0)
    editor.working.set(patch.TONE, "tone_switch", 1, tone=1)
    editor.refresh()  # an outside change shows, and tells no one
    assert box.isChecked() and editor.seen[-1] == (patch.TONE, "tone_switch", 1, 0)


def test_the_common_page_has_a_tone_mixer_with_a_knob_for_each_tone(editor):
    from jv_studio.ui.section_card import SectionCard

    editor.tabs.setCurrentIndex(0)
    titles = [c.title() for c in editor.tabs.widget(0).findChildren(SectionCard)]
    assert titles.count("Tone Mixer") == 1 and "Patch" in titles and "Structure" in titles
    for tone in range(4):
        editor.working.set(patch.TONE, "tone_level", 20 * (tone + 1), tone=tone)
    editor.refresh()
    assert [editor.mixer_knob(t).value() for t in range(4)] == [20, 40, 60, 80] and [editor.mixer_knob(t).name_label.text() for t in range(4)] == ["Tone 1", "Tone 2", "Tone 3", "Tone 4"]


def test_a_mixer_knob_edits_that_tones_level_and_the_level_card_follows(editor):
    editor.tabs.setCurrentIndex(2)  # build tone 2's page first
    level_knob = editor.widget_for(patch.TONE, "tone_level", 1)
    editor.tabs.setCurrentIndex(0)
    seen, recorded = len(editor.seen), []
    editor.edits_recorded.connect(recorded.append)
    editor.mixer_knob(1).setValue(99)
    assert editor.working.get(patch.TONE, "tone_level", tone=1) == 99 and editor.working.get(patch.TONE, "tone_level", tone=0) == 0
    assert editor.seen[seen:] == [(patch.TONE, "tone_level", 1, 99)] and recorded == [[(patch.TONE, "tone_level", 1, 0, 99)]]  # the same signal and undo step as the Level card's knob
    assert level_knob.value() == 99  # the knob on the tone's own Level card shows it
    level_knob.setValue(55)
    assert editor.mixer_knob(1).value() == 55 and editor.working.get(patch.TONE, "tone_level", tone=1) == 55  # and the other way round


def test_a_mixer_knob_is_greyed_while_its_tone_is_off_and_keeps_its_level(editor):
    editor.working.set(patch.TONE, "tone_level", 70, tone=2)
    editor.working.set(patch.TONE, "tone_switch", 1, tone=0)
    editor.refresh()
    assert editor.mixer_knob(0).isEnabled() and not editor.mixer_knob(2).isEnabled() and editor.mixer_knob(2).value() == 70
    assert "switched off" in editor.mixer_knob(2).toolTip()
    editor.tabs.setCurrentIndex(3)  # tone 3
    editor.widget_for(patch.TONE, "tone_switch", 2).click()
    assert editor.mixer_knob(2).isEnabled() and "switched off" not in editor.mixer_knob(2).toolTip()
