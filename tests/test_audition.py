# The audition keyboard: the messages, the keyboard widget, the bar, and the window's wiring (the unit is the simulated one; nothing is heard).

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

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
    keyboard.resize(1080, 74)  # 36 white keys: 30 px each
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
    assert keyboard.note_at(0.5, 70) == FIRST_NOTE and keyboard.note_at(1079, 70) == LAST_NOTE
    c_sharp = keyboard._key_rect(FIRST_NOTE + 1)
    assert keyboard.note_at(c_sharp.center().x(), 10) == FIRST_NOTE + 1  # near the top: the black key
    assert keyboard.note_at(c_sharp.center().x(), 70) in (FIRST_NOTE, FIRST_NOTE + 2)  # near the bottom: a white one
    assert keyboard.note_at(-1, 5) is None and keyboard.note_at(5, 80) is None


def test_dragging_across_keys_is_a_glissando(keys):
    keyboard, events = keys
    QTest.mousePress(keyboard, Qt.MouseButton.LeftButton, pos=QPoint(15, 70))
    QTest.mouseMove(keyboard, QPoint(45, 70))
    QTest.mouseRelease(keyboard, Qt.MouseButton.LeftButton, pos=QPoint(45, 70))
    assert events == [("on", 36), ("off", 36), ("on", 38), ("off", 38)]


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


def test_the_open_state_is_remembered(qapp):
    bar = AuditionBar()
    bar.set_open(False)
    assert not app_config.get_audition_open() and not bar.is_open() and AuditionBar().is_open() is False
    bar.set_open(True)
    assert app_config.get_audition_open()


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
    assert keyboard.typing_base == 84 and right == keyboard._key_rect(96).right()  # (clipped to the last key)
    QApplication.sendEvent(keyboard, QFocusEvent(QEvent.Type.FocusIn))
    keyboard.grab()  # paints without error (offscreen windows are rarely focused, so this runs the normal path)


def test_cmd_k_shows_and_hides_the_keyboard_and_the_menu_item_follows(win):
    w, fake = win
    assert w.audition_action.shortcut().toString() == "Ctrl+K" and w.audition_action.isCheckable()
    assert w.audition.is_open() and w.audition_action.isChecked()
    w.audition_action.trigger()
    assert not w.audition.is_open() and not w.audition_action.isChecked() and not app_config.get_audition_open()
    w.audition_action.trigger()
    assert w.audition.is_open() and w.audition_action.isChecked() and app_config.get_audition_open()
    w.audition.toggle.click()  # the bar's own arrow keeps the menu item in step
    assert not w.audition_action.isChecked()


def test_hiding_the_keyboard_lets_go_of_held_notes(win):
    w, fake = win
    w.audition.keyboard._press(60)
    w.audition.set_open(False)
    assert fake.channel_messages[-1] == audition.note_off(0, 60) and not w.audition.keyboard.is_down(60)
