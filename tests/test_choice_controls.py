import pytest
from PySide6.QtWidgets import QApplication, QCheckBox

from jv_studio.core import groups, params, patch, performance, rhythm, system
from jv_studio.ui.choice_controls import ChoiceCombo, SwitchBox, ToggleChoice, make_choice_control, short_name
from jv_studio.ui.patch_editor import PatchEditor


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def param(block, key):
    return params.load_table().block(block).param(key)


def test_the_control_follows_the_kind_of_list(qapp):
    assert isinstance(make_choice_control(param(patch.COMMON, "portamento_switch")), SwitchBox)  # OFF / ON
    assert isinstance(make_choice_control(param(patch.TONE, "lfo1_external_sync")), SwitchBox)  # OFF / CLOCK: a check box too
    assert isinstance(make_choice_control(param(patch.COMMON, "key_assign_mode")), ToggleChoice)  # POLY | SOLO
    assert isinstance(make_choice_control(param(patch.COMMON, "voice_priority")), ToggleChoice)  # LAST | LOUDEST
    assert isinstance(make_choice_control(param(patch.TONE, "pan_control_switch")), ChoiceCombo)  # OFF / CONTINUOUS / KEY-ON: three
    assert isinstance(make_choice_control(param(patch.COMMON, "patch_category")), ChoiceCombo)  # 39 of them
    assert isinstance(make_choice_control(param(system.COMMON, "volume_control_source")), ChoiceCombo)  # two, but long names: two buttons would be wider than a box
    assert isinstance(make_choice_control(param(patch.COMMON, "key_assign_mode"), allow_toggle=False), ChoiceCombo)


def test_a_switch_is_a_check_box_that_says_what_it_does_and_edits_silently(qapp):
    box = make_choice_control(param(patch.COMMON, "portamento_switch"))
    assert isinstance(box, QCheckBox) and box.text() == "Portamento" and not box.isChecked()  # " Switch" is dropped: the card says it
    seen = []
    box.edited.connect(seen.append)
    box.set_raw(1)  # showing a value is not an edit
    assert box.isChecked() and seen == [] and box.current_raw() == 1
    box.click()
    assert seen == [0] and not box.isChecked()
    box.click()
    assert seen == [0, 1]
    clock = make_choice_control(param(patch.TONE, "lfo1_external_sync"))
    assert clock.text() == "LFO1 External Sync" and clock.on_label == "Clock"
    clock.click()
    assert clock.current_raw() == 1


def test_a_toggle_shows_both_options_and_one_click_chooses(qapp):
    toggle = make_choice_control(param(patch.COMMON, "key_assign_mode"))
    assert [b.text() for b in toggle._buttons] == ["Poly", "Solo"]
    toggle.set_raw(0)
    assert [b.isChecked() for b in toggle._buttons] == [True, False] and toggle.current_raw() == 0
    seen = []
    toggle.edited.connect(seen.append)
    toggle._buttons[1].click()
    assert seen == [1] and [b.isChecked() for b in toggle._buttons] == [False, True]
    toggle._buttons[1].click()  # clicking the one that is chosen keeps it chosen
    assert toggle.current_raw() == 1
    toggle.set_raw(7)  # a value the unit holds that is neither option: neither is lit
    assert [b.isChecked() for b in toggle._buttons] == [False, False] and toggle.current_raw() is None and seen == [1, 1]


def test_a_value_the_unit_holds_that_is_not_offered_is_still_shown_in_a_box(qapp):
    combo = make_choice_control(param(patch.COMMON, "patch_category"))
    combo.set_raw(30)
    assert combo.currentData() == 30
    sound = make_choice_control(param(system.COMMON, "sound_mode"), hide=(2,))  # GM is hidden: two options left, so two buttons
    assert isinstance(sound, ToggleChoice) and [b.text() for b in sound._buttons] == ["Performance", "Patch"]


def test_short_names():
    assert short_name("Redamper Control Switch") == "Redamper Control" and short_name("Solo Legato") == "Solo Legato" and short_name("Switch") == "Switch"


def test_on_off_parameters_are_check_boxes_in_a_grid_at_the_top_of_their_card_in_every_editor(qapp):
    editor = PatchEditor()
    editor.set_patch(patch.Patch.minimum())
    editor.tabs.setCurrentIndex(0)
    for key in ("solo_legato", "portamento_switch", "velocity_range_switch"):
        assert isinstance(editor.widget_for(patch.COMMON, key), SwitchBox)
    for key in ("key_assign_mode", "voice_priority", "clock_source", "portamento_mode", "portamento_type", "portamento_start"):
        assert isinstance(editor.widget_for(patch.COMMON, key), ToggleChoice), key
    editor.tabs.setCurrentIndex(1)
    for key in ("fxm_switch", "redamper_control_switch", "volume_control_switch", "hold_1_control_switch", "pitch_bend_control_switch", "lfo1_key_sync", "lfo2_key_sync", "lfo1_external_sync", "lfo2_external_sync"):
        assert isinstance(editor.widget_for(patch.TONE, key, 0), SwitchBox), key
    # no drop-down is left for a two-option list in the patch editor except where the names are long
    for _, widget in [(k, w) for k, w in editor._widgets.items()]:
        if isinstance(widget, ChoiceCombo):
            assert widget.count() != 2 or sum(len(widget.itemText(i)) for i in range(widget.count())) > 24, widget.param.key


def test_every_editor_shows_the_raw_value_and_reports_a_click_in_the_same_way(qapp):
    editor = PatchEditor()
    working = patch.Patch.minimum()
    editor.set_patch(working)
    seen = []
    editor.param_committed.connect(lambda *a: seen.append(a))
    editor.widget_for(patch.COMMON, "key_assign_mode")._buttons[1].click()
    editor.widget_for(patch.COMMON, "solo_legato").click()
    assert working.get(patch.COMMON, "key_assign_mode") == 1 and working.get(patch.COMMON, "solo_legato") == 1
    assert [s[1] for s in seen] == ["key_assign_mode", "solo_legato"]
    working.set(patch.COMMON, "key_assign_mode", 0)
    working.set(patch.COMMON, "solo_legato", 0)
    editor.refresh()  # shows, tells no one
    assert editor.widget_for(patch.COMMON, "key_assign_mode").current_raw() == 0 and not editor.widget_for(patch.COMMON, "solo_legato").isChecked() and len(seen) == 2
