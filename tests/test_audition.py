# The audition keyboard: the messages, the keyboard widget, the bar, and the window's wiring (the unit is the simulated one; nothing is heard).

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, audition, midi, params
from jv_studio.ui.audition_bar import AuditionBar
from jv_studio.ui.keyboard import FIRST_NOTE, LAST_NOTE, PianoKeyboard
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


# -- the messages ---------------------------------------------------------------------------------------------------------


def test_notes_and_panic_are_the_plain_channel_messages():
    assert audition.note_on(0, 60, 100) == bytes([0x90, 60, 100]) and audition.note_off(15, 61) == bytes([0x8F, 61, 0])
    assert audition.note_on(2, 60, 0)[2] == 1  # (velocity 0 would be a note-off)
    assert audition.panic(3) == [bytes([0xB3, 64, 0]), bytes([0xB3, 120, 0]), bytes([0xB3, 123, 0])]
    with pytest.raises(ValueError):
        audition.note_on(16, 60)
    with pytest.raises(ValueError):
        audition.note_on(0, 128)


@pytest.mark.parametrize(
    "group, number, msb, lsb, program",
    [("USER", 0, 80, 0, 0), ("USER", 127, 80, 0, 127), ("PR-A", 4, 81, 0, 4), ("PR-B", 0, 81, 1, 0), ("PR-C", 9, 81, 2, 9), ("PR-D", 0, 81, 3, 0), ("PR-E", 127, 81, 4, 127),
     ("XP-A", 127, 84, 0, 127), ("XP-A", 128, 84, 1, 0), ("XP-A", 254, 84, 1, 126)],
)
def test_patch_select_follows_the_manuals_bank_table(group, number, msb, lsb, program):
    assert audition.patch_select(1, group, number) == [bytes([0xB1, 0, msb]), bytes([0xB1, 32, lsb]), bytes([0xC1, program])]


def test_patch_select_refuses_what_the_table_does_not_give():
    for group, number in (("XP-A", 255), ("USER", 128), ("PR-F", 0), ("USER", -1)):
        with pytest.raises(ValueError):
            audition.patch_select(0, group, number)


def test_the_systems_midi_settings_are_read_from_the_block_and_explained():
    table = params.load_table().block("system_common")
    block = table.new_buffer()
    for key, value in (("sound_mode", 1), ("patch_receive_channel", 4), ("receive_program_change", 1), ("receive_bank_select", 1)):
        params.write(block, table.param(key), value)
    info = audition.parse_system_common(block)
    assert (info.channel, info.mode_name, info.problems()) == (4, "Patch", [])
    params.write(block, table.param("sound_mode"), 0)
    params.write(block, table.param("receive_program_change"), 0)
    problems = audition.parse_system_common(block).problems()
    assert any("Performance mode" in p for p in problems) and any("Receive Program Change is OFF" in p for p in problems)
    params.write(block, table.param("sound_mode"), 2)
    assert any("GM mode" in p for p in audition.parse_system_common(block).problems())


# -- the keyboard widget ---------------------------------------------------------------------------------------------------


@pytest.fixture
def keys(qapp):
    keyboard = PianoKeyboard()
    keyboard.resize(1000, 74)  # 57 white keys: about 17.5 px each
    events = []
    keyboard.note_on.connect(lambda n: events.append(("on", n)))
    keyboard.note_off.connect(lambda n: events.append(("off", n)))
    keyboard.show()
    return keyboard, events


def test_clicking_a_key_plays_it_and_letting_go_releases_it(keys):
    keyboard, events = keys
    QTest.mousePress(keyboard, Qt.MouseButton.LeftButton, pos=keyboard.rect().center())
    note = keyboard.note_at(keyboard.rect().center().x(), keyboard.rect().center().y())
    assert events == [("on", note)] and keyboard.is_down(note)
    QTest.mouseRelease(keyboard, Qt.MouseButton.LeftButton, pos=keyboard.rect().center())
    assert events == [("on", note), ("off", note)] and not keyboard.is_down(note)


def test_black_keys_sit_above_white_ones_and_the_range_is_covered(keys):
    keyboard, _ = keys
    assert keyboard.note_at(0.5, 70) == FIRST_NOTE and keyboard.note_at(999, 70) == LAST_NOTE
    c_sharp = keyboard._key_rect(FIRST_NOTE + 1)
    assert keyboard.note_at(c_sharp.center().x(), 10) == FIRST_NOTE + 1  # near the top: the black key
    assert keyboard.note_at(c_sharp.center().x(), 70) in (FIRST_NOTE, FIRST_NOTE + 2)  # near the bottom: a white one
    assert keyboard.note_at(-1, 5) is None and keyboard.note_at(5, 80) is None


def test_dragging_across_keys_is_a_glissando(keys):
    keyboard, events = keys
    QTest.mousePress(keyboard, Qt.MouseButton.LeftButton, pos=QPoint(10, 70))
    QTest.mouseMove(keyboard, QPoint(30, 70))
    QTest.mouseRelease(keyboard, Qt.MouseButton.LeftButton, pos=QPoint(30, 70))
    assert events == [("on", FIRST_NOTE), ("off", FIRST_NOTE), ("on", FIRST_NOTE + 2), ("off", FIRST_NOTE + 2)]


def test_the_computer_keyboard_plays_from_c4_and_z_x_change_the_octave(keys):
    keyboard, events = keys
    QTest.keyPress(keyboard, Qt.Key.Key_A)
    QTest.keyPress(keyboard, Qt.Key.Key_W)
    QTest.keyRelease(keyboard, Qt.Key.Key_A)
    QTest.keyRelease(keyboard, Qt.Key.Key_W)
    assert events == [("on", 60), ("on", 61), ("off", 60), ("off", 61)]
    events.clear()
    QTest.keyClick(keyboard, Qt.Key.Key_Z)
    assert keyboard.typing_base == 48
    QTest.keyPress(keyboard, Qt.Key.Key_A)
    QTest.keyClick(keyboard, Qt.Key.Key_X)  # the octave moves while a key is held: the release still ends the note that was started
    QTest.keyRelease(keyboard, Qt.Key.Key_A)
    assert events == [("on", 48), ("off", 48)] and keyboard.typing_base == 60


def test_losing_focus_or_being_disabled_releases_everything(keys):
    keyboard, events = keys
    QTest.keyPress(keyboard, Qt.Key.Key_A)
    QApplication.sendEvent(keyboard, QFocusEvent(QEvent.Type.FocusOut))  # (an offscreen window is never the active one, so no real focus change happens)
    assert events[-1] == ("off", 60) and not keyboard.is_down(60)
    events.clear()
    QTest.keyPress(keyboard, Qt.Key.Key_D)
    keyboard.setEnabled(False)
    assert ("off", 64) in events


# -- the bar ---------------------------------------------------------------------------------------------------------------


@pytest.fixture
def bar(qapp):
    bar = AuditionBar()
    bar.set_available(True)
    out, chosen = [], []
    bar.midi_out.connect(out.append)
    bar.patch_chosen.connect(lambda g, n: chosen.append((g, n)))
    return bar, out, chosen


def test_notes_use_the_channel_and_velocity_and_the_off_follows_the_channel_it_started_on(bar):
    bar, out, _ = bar
    bar.set_channel(3)
    bar.velocity.setValue(90)
    bar.keyboard.note_on.emit(60)
    bar.set_channel(5)
    bar.keyboard.note_off.emit(60)
    assert out == [bytes([0x92, 60, 90]), bytes([0x82, 60, 0])]


def test_choosing_a_patch_sends_bank_select_then_program_change_and_says_so(bar):
    bar, out, chosen = bar
    bar.set_user_names(["Alpha", "Beta", "Gamma"])
    assert bar.patch_combo.itemText(1) == "002  Beta"
    bar.patch_combo.setCurrentIndex(2)
    bar.patch_combo.activated.emit(2)
    assert out[-3:] == [bytes([0xB0, 0, 80]), bytes([0xB0, 32, 0]), bytes([0xC0, 2])] and chosen == [("USER", 2)]
    bar.bank_combo.setCurrentIndex(bar.bank_combo.findData("PR-B"))
    bar.bank_combo.activated.emit(bar.bank_combo.currentIndex())
    assert out[-3:] == [bytes([0xB0, 0, 81]), bytes([0xB0, 32, 1]), bytes([0xC0, 0])] and chosen[-1] == ("PR-B", 0)
    assert bar.patch_combo.itemText(0).startswith("001  ") and len(bar.patch_combo.itemText(0)) > 6  # the manual's name for the ROM bank's first patch
    bar.next_button.click()
    assert chosen[-1] == ("PR-B", 1) and out[-1] == bytes([0xC0, 1])


def test_stepping_stops_at_the_ends_and_choose_selects_by_number(bar):
    bar, out, chosen = bar
    bar.prev_button.click()
    assert chosen == []  # patch 1 has no previous one
    bar.choose("XP-A", 130)
    assert chosen[-1] == ("XP-A", 130) and out[-3:] == [bytes([0xB0, 0, 84]), bytes([0xB0, 32, 1]), bytes([0xC0, 2])] and bar.current_label().startswith("XP-A 131")


def test_choosing_a_patch_lets_go_of_held_notes_first(bar):
    bar, out, _ = bar
    bar.keyboard.note_on.emit(60)
    bar.keyboard._press(64)
    out.clear()
    bar.choose("PR-A", 0)
    assert bar.keyboard.is_down(64) is False and bytes([0x80, 64, 0]) in out and out.index(bytes([0x80, 64, 0])) < out.index(bytes([0xB0, 0, 81]))


def test_panic_releases_and_silences_the_channel(bar):
    bar, out, _ = bar
    bar.set_channel(2)
    bar.keyboard._press(60)
    out.clear()
    bar.panic()
    assert out[0] == bytes([0x81, 60, 0]) and out[-3:] == audition.panic(1)


def test_an_unavailable_bar_plays_nothing_and_says_why(bar):
    bar, out, _ = bar
    bar.keyboard._press(60)
    out.clear()
    bar.set_available(False, "Open the MIDI ports in Settings to play the unit.")
    assert out == [bytes([0x80, 60, 0])] and not bar.body.isEnabled() and "Settings" in bar.note.text()
    out.clear()
    bar.keyboard.note_on.emit(61)
    assert out == []


def test_what_the_unit_says_sets_the_channel_and_the_note(bar):
    bar, _, _ = bar
    bar.show_system(audition.SystemMidi(channel=6, program_change=False, bank_select=True, sound_mode=1))
    assert bar.channel() == 6 and "Receive Program Change is OFF" in bar.note.text()


def test_the_bar_always_starts_closed_because_an_open_one_owns_the_keyboard(qapp):
    bar = AuditionBar()
    assert not bar.is_open() and bar.body.isHidden()
    bar.set_open(True)
    assert AuditionBar().is_open() is False  # (nothing is remembered between launches)
    bar.set_open(False)


def test_the_channel_is_a_box_of_1_to_16_and_idle_notes_are_not_shown(bar):
    bar, _, _ = bar
    assert [bar.channel_combo.itemText(i) for i in range(16)] == [str(n) for n in range(1, 17)] and bar.channel() == 0
    bar.set_channel(16)
    assert bar.channel() == 15 and bar.channel_combo.currentText() == "16"
    assert bar.note.isHidden() and bar.note.text() == ""  # the old "click the keys..." line is gone
    assert bar.typing_label.text() == "Octave: C4 to E5"
    QTest.keyClick(bar.keyboard, Qt.Key.Key_Z)
    assert bar.typing_label.text() == "Octave: C3 to E4"


# -- the bar owns the computer keyboard while it is open ------------------------------------------------------------------------


def key_event(kind, key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(kind, key, modifiers, text)


@pytest.fixture
def routed(bar):
    bar, out, chosen = bar
    bar.set_open(True)
    bar._window_in_front = lambda: True  # (an offscreen window is never the active one)
    yield bar, out
    bar.set_open(False)


def test_while_open_every_ordinary_key_goes_to_the_piano_not_to_a_text_box(routed):
    bar, out = routed
    box = QLineEdit()
    press = key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a")
    assert bar.eventFilter(box, press) is True and out == [audition.note_on(0, 60, 100)]
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyRelease, Qt.Key.Key_A, "a")) is True and out[-1] == audition.note_off(0, 60)
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, Qt.Key.Key_Q, "q")) is True  # a letter that plays nothing is still not typed
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, Qt.Key.Key_Backspace)) is True
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, Qt.Key.Key_5, "5")) is True
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, Qt.Key.Key_Z, "z")) is True and bar.keyboard.typing_base == 48 and len(out) == 2


def test_shortcuts_and_navigation_keys_still_work(routed):
    bar, out = routed
    box = QLineEdit()
    for key, modifier in ((Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier), (Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier),
                          (Qt.Key.Key_S, Qt.KeyboardModifier.MetaModifier), (Qt.Key.Key_A, Qt.KeyboardModifier.AltModifier)):
        assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, key, "k", modifier)) is False
    for key in (Qt.Key.Key_Tab, Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_F2, Qt.Key.Key_F12):
        assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, key)) is False
    assert out == []


def test_the_keys_are_given_back_when_the_bar_closes_the_unit_goes_or_another_window_is_in_front(routed):
    bar, out = routed
    box = QLineEdit()
    press = key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a")
    bar._window_in_front = lambda: False  # a dialog or the System Settings window
    assert bar.eventFilter(box, press) is False
    bar._window_in_front = lambda: True
    assert bar.eventFilter(bar.keyboard, press) is False  # (the piano handles its own events)
    bar.set_available(False)  # no unit: a dead keyboard must not swallow typing
    assert not bar.routing_keys() and bar.eventFilter(box, press) is False
    bar.set_available(True)
    assert bar.eventFilter(box, press) is True
    bar.set_open(False)
    assert not bar.routing_keys() and bar.eventFilter(box, press) is False


def test_typing_in_a_real_text_box_is_swallowed_while_the_bar_is_open(win):
    w, fake = win
    w.audition._window_in_front = lambda: True
    box = QLineEdit()
    box.show()
    w.audition.set_open(True)
    QTest.keyClick(box, Qt.Key.Key_A)
    assert box.text() == "" and audition.note_on(0, 60, 100) in fake.channel_messages  # the key played C4 and did not type
    w.audition.set_open(False)
    QTest.keyClick(box, Qt.Key.Key_A)
    assert box.text() == "a"


# -- the window ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    fake = FakeJV1010("Init Patch")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a: QMessageBox.StandardButton.Ok)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    return w, fake


def test_notes_and_patch_choices_reach_the_unit_and_the_shown_patch_is_no_longer_in_step(win):
    w, fake = win
    w._temp_synced = True
    w.audition.keyboard.note_on.emit(64)
    w.audition.choose("USER", 5)
    assert fake.channel_messages[0] == bytes([0x90, 64, 100]) and fake.channel_messages[-3:] == audition.patch_select(0, "USER", 5)
    assert w._temp_synced is False and "Chose USER 006" in w.statusBar().currentMessage()


def test_the_keyboard_is_off_without_ports_and_during_long_jobs(win):
    w, fake = win
    assert w.audition.body.isEnabled()
    w._long_job = True
    w._refresh_connection()
    assert not w.audition.body.isEnabled()
    w._long_job = False
    w.session.close()
    w._refresh_connection()
    assert not w.audition.body.isEnabled() and "Settings" in w.audition.note.text()


def test_nothing_is_sent_while_firmware_is_playing(win):
    w, fake = win
    w._firmware_running = True
    w._send_midi(audition.note_on(0, 60))
    assert fake.channel_messages == []
    w._firmware_running = False


def test_from_unit_reads_the_receive_channel_and_mode(win):
    w, fake = win
    w.audition.unit_button.click()
    w.worker.process_pending()
    assert w.audition.channel() == 0 and w.audition.note.text().startswith("The unit is in Patch mode and receives on channel 1.")
    assert fake.requests[-1][0] == (0, 0, 0, 0)


def test_the_list_menu_can_play_a_user_patch(win):
    w, fake = win
    w.worker.submit("names")
    w.worker.process_pending()
    assert w.audition.patch_combo.itemText(2).endswith("User 003")


# -- shortcuts and the live read-out -----------------------------------------------------------------------------------------


def test_velocity_steps_snap_to_the_nearest_multiple_of_ten_then_move_one():
    up = [audition.step_velocity(v, 1) for v in (1, 5, 10, 94, 95, 97, 100, 123, 124, 127)]
    assert up == [10, 10, 20, 100, 110, 110, 110, 127, 127, 127]
    down = [audition.step_velocity(v, -1) for v in (127, 125, 120, 94, 95, 97, 100, 11, 10, 5, 1)]
    assert down == [120, 120, 110, 80, 90, 90, 90, 1, 1, 1, 1]


def test_c_and_v_snap_the_velocity_to_a_multiple_of_ten_then_step(bar):
    bar, out, _ = bar
    keyboard = bar.keyboard
    bar.velocity.setValue(97)
    QTest.keyClick(keyboard, Qt.Key.Key_V)
    assert bar.velocity.value() == 110 and bar.playing_label.text() == "Velocity 110"  # 97 is nearest to 100, one step up
    bar.velocity.setValue(97)
    QTest.keyClick(keyboard, Qt.Key.Key_C)
    assert bar.velocity.value() == 90
    QTest.keyClick(keyboard, Qt.Key.Key_C)
    assert bar.velocity.value() == 80
    for _ in range(30):
        QTest.keyClick(keyboard, Qt.Key.Key_C)
    assert bar.velocity.value() == 1
    QTest.keyClick(keyboard, Qt.Key.Key_V)
    assert bar.velocity.value() == 10
    for _ in range(30):
        QTest.keyClick(keyboard, Qt.Key.Key_V)
    assert bar.velocity.value() == 127
    assert out == []  # (changing the velocity sends nothing)
    QTest.keyPress(keyboard, Qt.Key.Key_A)
    assert out[-1] == audition.note_on(0, 60, 127)
    QTest.keyRelease(keyboard, Qt.Key.Key_A)


def test_the_notes_being_played_are_shown_live(bar):
    bar, _, _ = bar
    keyboard = bar.keyboard
    QTest.keyPress(keyboard, Qt.Key.Key_A)
    assert bar.playing_label.text() == "C4"
    QTest.keyPress(keyboard, Qt.Key.Key_D)
    QTest.keyPress(keyboard, Qt.Key.Key_G)
    assert bar.playing_label.text() == "C4   E4   G4"
    QTest.keyRelease(keyboard, Qt.Key.Key_D)
    assert bar.playing_label.text() == "C4   G4"
    QTest.keyRelease(keyboard, Qt.Key.Key_A)
    QTest.keyRelease(keyboard, Qt.Key.Key_G)
    assert bar.playing_label.text() == ""
    QTest.keyPress(keyboard, Qt.Key.Key_W)  # a black key
    assert bar.playing_label.text() == "C#4"
    keyboard.release_all()
    assert bar.playing_label.text() == ""


def test_a_bar_under_the_keyboard_marks_the_octave_the_computer_keys_play(keys):
    keyboard, _ = keys
    left, right = keyboard._typing_span()
    assert left == keyboard._key_rect(60).left() and right == keyboard._key_rect(76).right()  # C4 to E5
    QTest.keyClick(keyboard, Qt.Key.Key_Z)
    assert keyboard._typing_span()[0] == keyboard._key_rect(48).left()  # it follows Z at once (a repaint is queued without a note)
    for _ in range(8):
        QTest.keyClick(keyboard, Qt.Key.Key_X)
    left, right = keyboard._typing_span()
    assert keyboard.typing_base == LAST_NOTE - 12 and right == keyboard._key_rect(LAST_NOTE).right()  # (the highest octave: clipped to the last key)
    QApplication.sendEvent(keyboard, QFocusEvent(QEvent.Type.FocusIn))
    keyboard.grab()  # paints without error (offscreen windows are rarely focused, so this runs the normal path)


def test_cmd_k_shows_and_hides_the_keyboard_and_the_menu_item_follows(win):
    w, fake = win
    assert w.audition_action.shortcut().toString() == "Ctrl+K" and w.audition_action.isCheckable()
    assert not w.audition.is_open() and not w.audition_action.isChecked()  # closed at startup
    w.audition_action.trigger()
    assert w.audition.is_open() and w.audition_action.isChecked()
    w.audition_action.trigger()
    assert not w.audition.is_open() and not w.audition_action.isChecked()
    w.audition_action.trigger()
    w.audition.toggle.click()  # the bar's own arrow keeps the menu item in step
    assert not w.audition_action.isChecked()


def test_hiding_the_keyboard_lets_go_of_held_notes(win):
    w, fake = win
    w.audition.keyboard._press(60)
    w.audition.set_open(False)
    assert fake.channel_messages[-1] == audition.note_off(0, 60) and not w.audition.keyboard.is_down(60)


# -- browsing by category -------------------------------------------------------------------------------------------------------


def test_the_bank_box_lists_the_banks_then_the_categories(bar):
    bar, out, chosen = bar
    items = [bar.bank_combo.itemText(i) for i in range(bar.bank_combo.count())]
    assert items[:7] == ["USER", "Preset A", "Preset B", "Preset C", "Preset D (GM)", "Preset E", "Session"] and items[7] == ""  # (the separator)
    assert items[8:] == ["Piano (category)", "Key & Organ (category)", "Guitar / Bass (category)", "Orchestra / Brass (category)", "Synth / Pad (category)", "Ethnic (category)", "Rhythm & SFX (category)"]


def test_choosing_a_category_lists_its_patches_by_the_units_numbers_and_sends_the_bank_they_live_in(bar):
    bar, out, chosen = bar
    bar.bank_combo.setCurrentIndex(bar.bank_combo.findData("category:PIANO"))
    bar.bank_combo.activated.emit(bar.bank_combo.currentIndex())
    assert bar.patch_combo.count() == 59 and bar.patch_combo.itemText(7) == "008  Bright Piano" and "Preset A 002" in bar.patch_combo.itemData(7, Qt.ItemDataRole.ToolTipRole)
    assert out[-3:] == audition.patch_select(0, "XP-A", 0) and chosen[-1] == ("XP-A", 0)  # PIANO 001 is the Session's St.Concert
    bar.patch_combo.setCurrentIndex(7)
    bar.patch_combo.activated.emit(7)
    assert out[-3:] == audition.patch_select(0, "PR-A", 1) and chosen[-1] == ("PR-A", 1)  # Bank Select 81/0, Program Change 2
    assert bar.current_label() == "PIANO 008  Bright Piano"
    bar.next_button.click()
    assert bar.patch_combo.currentText() == "009  Classique" and chosen[-1] == ("PR-A", 2)


def test_a_category_patch_in_the_second_half_of_the_session_bank_uses_its_second_bank_select(bar):
    bar, out, chosen = bar
    bar.bank_combo.setCurrentIndex(bar.bank_combo.findData("category:SYNTH/PAD"))
    bar._fill_patches()
    index = bar.patch_combo.findText("055  DanceStack 8")  # (the manual prints no 055; see core/patch_groups and tools/extract_params.py)
    assert index >= 0 and bar.patch_combo.itemText(index - 1) == "054  DanceStack 7" and bar.patch_combo.count() == 355
    bar.patch_combo.setCurrentIndex(index)
    bar.patch_combo.activated.emit(index)
    assert out[-3:] == [audition.control_change(0, 0, 84), audition.control_change(0, 32, 1), audition.program_change(0, 22)] and chosen[-1] == ("XP-A", 150)


def test_going_back_to_a_bank_after_a_category_works_and_play_on_unit_leaves_a_category(bar):
    bar, out, chosen = bar
    bar.bank_combo.setCurrentIndex(bar.bank_combo.findData("category:ETHNIC"))
    bar._fill_patches()
    assert bar.patch_combo.count() == 27
    bar.choose("USER", 5)
    assert bar.bank_combo.currentData() == "USER" and bar.patch_combo.count() == 128 and out[-3:] == audition.patch_select(0, "USER", 5)


# -- stepping patches and banks from the computer keyboard ------------------------------------------------------------------------


def test_comma_period_and_brackets_step_the_patch_and_the_bank(bar):
    bar, out, chosen = bar
    keyboard = bar.keyboard
    assert bar.bank_combo.currentData() == "USER" and bar.patch_combo.currentIndex() == 0
    QTest.keyClick(keyboard, Qt.Key.Key_Period)
    QTest.keyClick(keyboard, Qt.Key.Key_Period)
    assert bar.patch_combo.currentIndex() == 2 and chosen[-1] == ("USER", 2) and out[-3:] == audition.patch_select(0, "USER", 2)
    QTest.keyClick(keyboard, Qt.Key.Key_Comma)
    assert bar.patch_combo.currentIndex() == 1 and chosen[-1] == ("USER", 1)
    QTest.keyClick(keyboard, Qt.Key.Key_BracketRight)  # the next bank: Preset A, its first patch
    assert bar.bank_combo.currentData() == "PR-A" and bar.patch_combo.currentIndex() == 0 and chosen[-1] == ("PR-A", 0) and out[-3:] == audition.patch_select(0, "PR-A", 0)
    QTest.keyClick(keyboard, Qt.Key.Key_BracketLeft)
    assert bar.bank_combo.currentData() == "USER"
    QTest.keyClick(keyboard, Qt.Key.Key_BracketLeft)  # already the first: stays
    assert bar.bank_combo.currentData() == "USER" and bar.bank_combo.currentIndex() == 0


def test_the_bank_keys_walk_on_through_the_categories_past_the_separator_and_stop_at_the_end(bar):
    bar, out, chosen = bar
    for _ in range(6):
        QTest.keyClick(bar.keyboard, Qt.Key.Key_BracketRight)
    assert bar.bank_combo.currentData() == "XP-A"  # Session: the last bank
    QTest.keyClick(bar.keyboard, Qt.Key.Key_BracketRight)  # over the separator
    assert bar.bank_combo.currentData() == "category:PIANO" and bar.patch_combo.itemText(0).startswith("001  ")
    for _ in range(10):
        QTest.keyClick(bar.keyboard, Qt.Key.Key_BracketRight)
    assert bar.bank_combo.currentData() == "category:RHYTHM&SFX"  # the last entry
    QTest.keyClick(bar.keyboard, Qt.Key.Key_BracketLeft)
    assert bar.bank_combo.currentData() == "category:ETHNIC"
    for _ in range(6):
        QTest.keyClick(bar.keyboard, Qt.Key.Key_BracketLeft)
    assert bar.bank_combo.currentData() == "XP-A"  # back over the separator


def test_the_patch_keys_stop_at_the_ends_and_repeat_while_held(bar):
    bar, out, chosen = bar
    QTest.keyClick(bar.keyboard, Qt.Key.Key_Comma)
    assert bar.patch_combo.currentIndex() == 0  # nothing before the first
    from PySide6.QtGui import QKeyEvent

    for _ in range(3):  # an auto-repeating key: each repeat steps again
        bar.keyboard.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Period, Qt.KeyboardModifier.NoModifier, ".", True))
    assert bar.patch_combo.currentIndex() == 3
    bar.keyboard.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketRight, Qt.KeyboardModifier.NoModifier, "]", True))
    assert bar.bank_combo.currentData() == "USER"  # a bank key does not repeat: a held key would race through the banks


def test_the_step_keys_are_routed_to_the_bar_while_it_is_open_and_do_not_play_notes(routed):
    bar, out = routed
    box = QLineEdit()
    for key, text in ((Qt.Key.Key_Period, "."), (Qt.Key.Key_BracketRight, "]")):
        assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, key, text)) is True
    assert bar.patch_combo.currentIndex() == 1 or bar.bank_combo.currentData() == "PR-A"
    assert all(m[0] & 0xF0 != 0x90 for m in out)  # no note was played
    assert bar.eventFilter(box, key_event(QEvent.Type.KeyPress, Qt.Key.Key_Period, ".", Qt.KeyboardModifier.ControlModifier)) is False  # a shortcut still passes


def test_the_audition_button_sits_at_the_left_even_with_no_note_line(qapp):
    bar = AuditionBar()
    bar.resize(900, 300)
    bar.show()
    qapp.processEvents()
    assert bar.note.isHidden() and bar.toggle.geometry().left() < 40 and bar.toggle.width() < 200
    bar.close()


# -- following the patch the unit has selected -------------------------------------------------------------------------------------


def unit_selects(fake, group_type, group_id, number, mode=1):
    table = params.load_table().block("system_common")
    for key, value in (("sound_mode", mode), ("patch_group_type", group_type), ("patch_group_id", group_id), ("patch_number", number)):
        params.write(fake.other[0], table.param(key), value)


def test_the_system_block_says_which_patch_the_unit_has_selected():
    from jv_studio.core import system

    fake = FakeJV1010()
    unit_selects(fake, 0, 4, 41)  # Preset B, patch 042
    info = audition.parse_system_common(bytes(fake.other[0]))
    assert (info.group_type, info.group_id, info.patch_number, info.sound_mode) == (0, 4, 41, 1)


def test_the_bar_shows_the_selected_patch_without_sending_anything(bar):
    bar, out, chosen = bar
    info = lambda **k: audition.SystemMidi(channel=0, program_change=True, bank_select=True, sound_mode=k.pop("mode", 1), **k)
    bar.show_selected_patch(info(group_type=0, group_id=4, patch_number=41))
    assert bar.bank_combo.currentData() == "PR-B" and bar.patch_combo.currentIndex() == 41 and bar.patch_combo.currentText().startswith("042  ")
    bar.show_selected_patch(info(group_type=2, group_id=9, patch_number=200))  # the Session bank's second half
    assert bar.bank_combo.currentData() == "XP-A" and bar.patch_combo.currentIndex() == 200
    assert out == [] and chosen == []  # shown only: the unit is already there
    bar.bank_combo.setCurrentIndex(bar.bank_combo.findData("category:PIANO"))
    bar._fill_patches()
    bar.show_selected_patch(info(group_type=0, group_id=3, patch_number=1))  # browsing a category: back to the bank list the unit really uses
    assert bar.bank_combo.currentData() == "PR-A" and bar.patch_combo.currentIndex() == 1
    before = (bar.bank_combo.currentData(), bar.patch_combo.currentIndex())
    bar.show_selected_patch(info(group_type=0, group_id=4, patch_number=7, mode=0))  # Performance mode: the patch is not what plays
    bar.show_selected_patch(info(group_type=2, group_id=4, patch_number=7))  # a group the manual's table does not name
    bar.show_selected_patch(info(group_type=0, group_id=4, patch_number=200))  # beyond the bank
    bar.show_selected_patch(audition.SystemMidi(channel=0, program_change=True, bank_select=True, sound_mode=1))  # not read at all
    assert (bar.bank_combo.currentData(), bar.patch_combo.currentIndex()) == before and out == []


def test_refresh_all_follows_the_front_panel_patch_quietly(win):
    w, fake = win
    w.audition._info_note = "Some earlier note"  # what an earlier From Unit said
    unit_selects(fake, 0, 5, 12)  # Preset C, patch 013, chosen on the unit's panel
    w.refresh_all()
    w.worker.process_pending()
    assert w.audition.bank_combo.currentData() == "PR-C" and w.audition.patch_combo.currentIndex() == 12
    assert w.audition.channel() == 0 and w.audition._info_note == "Some earlier note"  # a refresh does not touch the note line (the channel follows the tab: the unit's Patch Receive Channel here)
    assert fake.channel_messages == [] and w._announce_system is True  # nothing was played or sent, and the next From Unit announces again


def test_from_unit_still_announces_and_now_selects_the_patch_too(win):
    w, fake = win
    unit_selects(fake, 0, 3, 99)
    w.audition.unit_button.click()
    w.worker.process_pending()
    assert w.audition.bank_combo.currentData() == "PR-A" and w.audition.patch_combo.currentIndex() == 99
    assert w.audition.channel() == 0 and "receives on channel 1" in w.audition.note.text()


def test_the_start_up_read_shows_the_unit_selection_too(win):
    w, fake = win
    unit_selects(fake, 2, 9, 3)
    w.session.close()
    w.session.open("in", "out")
    w._autoload_enabled = True
    w._autoload_ports = None
    w._maybe_autoload()
    w.worker.process_pending()
    assert w.audition.bank_combo.currentData() == "XP-A" and w.audition.patch_combo.currentIndex() == 3
