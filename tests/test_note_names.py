import pytest
from PySide6.QtWidgets import QApplication

from jv_studio.core import app_config, params
from jv_studio.ui.keyboard import FIRST_NOTE, LAST_NOTE, PianoKeyboard
from jv_studio.ui.knob_control import parse_display_text


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def roland_naming(monkeypatch):
    monkeypatch.setattr(params, "_MIDDLE_C_OCTAVE", 4)  # (each test starts with Roland's naming, the module's own default; set_middle_c is put back afterwards)


def test_roland_names_note_60_c4_and_ableton_names_it_c3():
    assert [params.note_name(n) for n in (0, 36, 48, 60, 61, 127)] == ["C-1", "C2", "C3", "C4", "C#4", "G9"]  # the manual's "C-1 - G9" and its Rhythm Set List (C2 = 36)
    params.set_middle_c(3)
    assert params.middle_c_octave() == 3
    assert [params.note_name(n) for n in (0, 36, 48, 60, 61, 127)] == ["C-2", "C1", "C2", "C3", "C#3", "G8"]
    with pytest.raises(ValueError):
        params.set_middle_c(5)


def test_only_the_names_move_never_the_note_numbers():
    table = params.load_table().block("system_common")
    note = table.param("preview_note_set_1")
    assert params.format_value(note, 60) == "C4"
    params.set_middle_c(3)
    assert params.format_value(note, 60) == "C3" and params.format_value(note, 0) == "C-2"
    buffer = bytearray(table.size)
    params.write(buffer, note, 60)
    assert params.read(buffer, note) == 60  # the stored value is the MIDI note either way


def test_a_typed_note_name_follows_the_naming(qapp):
    note = params.load_table().block("system_common").param("preview_note_set_1")
    assert parse_display_text(note, "C4") == 60
    params.set_middle_c(3)
    from jv_studio.ui import knob_control

    if hasattr(knob_control._text_to_value, "cache_clear"):
        knob_control._text_to_value.cache_clear()  # (the table of names is cached: the app sets the naming before any widget reads it)
    assert parse_display_text(note, "C3") == 60 and parse_display_text(note, "C#3") == 61


def test_the_setting_defaults_to_c3_and_is_remembered():
    assert app_config.get_middle_c() == 3
    app_config.save_middle_c(4)
    assert app_config.get_middle_c() == 4
    app_config.save_middle_c(3)
    assert app_config.get_middle_c() == 3
    app_config.save_middle_c(7)  # anything else means the default
    assert app_config.get_middle_c() == 3


def test_the_keyboard_reaches_lower_than_the_first_five_octaves(qapp):
    assert (FIRST_NOTE, LAST_NOTE) == (12, 108)
    keyboard = PianoKeyboard()
    keyboard.resize(1000, 82)
    assert keyboard.note_at(0.5, 70) == FIRST_NOTE and keyboard.note_at(999, 70) == LAST_NOTE
    for _ in range(5):
        keyboard.set_typing_base(keyboard.typing_base - 12)
    assert keyboard.typing_base == 12 and params.note_name(keyboard.typing_base) == "C0"  # the octave keys can go all the way down (C-1 in Ableton's naming)
    played = []
    keyboard.note_on.connect(played.append)
    keyboard._press(FIRST_NOTE)
    assert played == [12]


def test_the_settings_dialog_has_a_middle_c_box_that_saves(qapp, monkeypatch, tmp_path):
    from jv_studio.core import midi
    from jv_studio.ui.midi_session import MidiSession
    from jv_studio.ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(midi, "list_input_names", lambda: [])
    monkeypatch.setattr(midi, "list_output_names", lambda: [])
    dialog = SettingsDialog(MidiSession(lambda i, o: None))
    box = dialog.combo_middle_c
    assert [box.itemText(i)[:2] for i in range(2)] == ["C3", "C4"] and box.currentData() == 3
    box.setCurrentIndex(1)
    box.activated.emit(1)
    assert app_config.get_middle_c() == 4


# -- eight octaves, scrolling when the window is narrow -------------------------------------------------------------------------


def test_the_keyboard_spans_eight_octaves_up_to_c7_in_the_default_naming():
    from jv_studio.ui import keyboard as kb

    params.set_middle_c(3)
    assert (kb.FIRST_NOTE, kb.LAST_NOTE) == (12, 108) and params.note_name(kb.FIRST_NOTE) == "C-1" and params.note_name(kb.LAST_NOTE) == "C7"
    assert len(kb.PianoKeyboard()._whites) == 57


def test_the_audition_keyboard_scrolls_sideways_in_a_narrow_window_and_just_fits_in_a_wide_one(qapp):
    from jv_studio.ui.audition_bar import AuditionBar

    bar = AuditionBar()
    bar.set_open(True)
    bar.set_available(True)
    bar.resize(1300, 300)
    bar.show()
    qapp.processEvents()
    scroll = bar.keyboard_scroll
    assert bar.keyboard.minimumWidth() == 57 * 20 and scroll.horizontalScrollBar().maximum() == 0 and scroll.height() == bar.keyboard.height()  # wide: no scroll bar, nothing squeezed
    bar.resize(900, 300)
    qapp.processEvents()
    assert bar.keyboard.width() == 1140 and scroll.horizontalScrollBar().maximum() > 0 and scroll.height() > bar.keyboard.height()  # narrow: keys keep 20 px, there is room for the scroll bar
    assert bar.keyboard._white_width() >= 20
    bar.close()


def test_the_octave_keys_bring_the_octave_that_is_played_into_view(qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt

    from jv_studio.ui.audition_bar import AuditionBar

    bar = AuditionBar()
    bar.set_open(True)
    bar.set_available(True)
    bar.resize(900, 300)
    bar.show()
    qapp.processEvents()
    scroll, bar_h = bar.keyboard_scroll, bar.keyboard_scroll.horizontalScrollBar()
    for _ in range(4):
        QTest.keyClick(bar.keyboard, Qt.Key.Key_Z)
    low = bar_h.value()
    left, right = bar.keyboard._typing_span()
    assert low <= left and right <= low + scroll.viewport().width()  # the played octave is in view
    for _ in range(8):
        QTest.keyClick(bar.keyboard, Qt.Key.Key_X)
    high = bar_h.value()
    left, right = bar.keyboard._typing_span()
    assert high > low and high <= left and right <= high + scroll.viewport().width()
    bar.close()
