import pytest
from PySide6.QtWidgets import QApplication

from jv_studio.ui.patch_picker import PatchPickerDialog


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_it_opens_on_the_current_patch_and_returns_the_three_values(qapp):
    d = PatchPickerDialog(0, 3, 11)  # PR-A 012
    assert d.group_combo.currentText() == "Preset A" and d.list.currentItem().text().startswith("012  ")
    assert d.result_patch() == (0, 3, 11)


def test_user_patches_are_numbers_until_their_names_are_known(qapp):
    d = PatchPickerDialog(0, 1, 4)
    assert d.list.count() == 128 and d.list.currentItem().text() == "005" and "haven't been read" in d.note.text()
    named = PatchPickerDialog(0, 1, 4, user_names=[f"Name {i}" for i in range(128)])
    assert named.list.currentItem().text() == "005  Name 4" and named.note.text() == ""


def test_filtering_by_name_or_number_and_choosing_another_group(qapp):
    d = PatchPickerDialog(0, 3, 0)
    d.group_combo.setCurrentIndex(d.group_combo.findText("Session"))
    assert d.list.count() == 255
    d.filter_edit.setText("st.concert")
    assert d.list.count() >= 1 and d.list.item(0).text() == "001  St.Concert"
    d.list.setCurrentRow(0)
    assert d.result_patch() == (2, 9, 0)
    d.filter_edit.setText("qqqqq")
    assert d.list.count() == 0 and not d.buttons.button(d.buttons.StandardButton.Ok).isEnabled()
    d.filter_edit.setText("200")  # a number matches too
    assert d.list.count() >= 1 and d.list.item(0).text().startswith("200")


def test_an_assignment_in_a_group_we_do_not_know_still_opens(qapp):
    d = PatchPickerDialog(2, 4, 6)  # some other board
    assert d.list.currentItem() is None and d.group_combo.currentIndex() == 0


def test_a_category_lists_patches_from_several_banks_and_returns_the_bank_and_number_of_the_one_chosen(qapp):
    d = PatchPickerDialog(0, 3, 0)
    items = [d.group_combo.itemText(i) for i in range(d.group_combo.count())]
    assert items[7] == "" and items[8:] == ["Piano (category)", "Key & Organ (category)", "Guitar / Bass (category)", "Orchestra / Brass (category)", "Synth / Pad (category)", "Ethnic (category)", "Rhythm & SFX (category)"]
    d.group_combo.setCurrentIndex(d.group_combo.findData("PIANO"))
    assert d.list.count() == 59 and d.list.item(7).text() == "008  Bright Piano" and d.list.item(7).toolTip() == "Preset A 002" and "CATEGORY knob" in d.note.text()
    d.list.setCurrentRow(7)
    assert d.result_patch() == (0, 3, 1)  # Preset A, patch 002: what the part stores
    d.list.setCurrentRow(0)
    assert d.result_patch() == (2, 9, 0)  # PIANO 001 is the Session's St.Concert
    d.filter_edit.setText("grand")
    assert [d.list.item(i).text().split("  ")[1] for i in range(d.list.count())][:3] == ["9ft.Grand 1", "9ft.Grand 2", "Power Grand"]
    d.filter_edit.setText("008")  # the number the unit shows in the category
    assert d.list.item(0).text() == "008  Bright Piano"


def test_a_synth_pad_patch_past_the_session_banks_first_half_is_returned_as_its_own_number(qapp):
    d = PatchPickerDialog(0, 3, 0)
    d.group_combo.setCurrentIndex(d.group_combo.findData("SYNTH/PAD"))
    d.filter_edit.setText("DanceStack 8")
    assert d.list.count() == 1 and d.list.item(0).text() == "055  DanceStack 8"
    d.list.setCurrentRow(0)
    assert d.result_patch() == (2, 9, 150)
