import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, audition, midi, params, rhythm
from jv_studio.ui import rhythm_panel as rp
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker

NOTE = rhythm.NOTE


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    fake = FakeJV1010("Init Patch")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    w.mode_tabs.setCurrentIndex(2)
    return w, fake, tmp_path


def click_key(editor, key):
    """A real mouse click on the mini keyboard, in the middle of `key`."""
    editor.selector.resize(1000, 66)
    QTest.mouseClick(editor.selector, Qt.MouseButton.LeftButton, pos=editor.selector._key_rect(key).center().toPoint())


def shown(w):
    w.read_temporary()
    w.worker.process_pending()
    return w.rhythm_panel, w.rhythm_panel.editor


def test_the_mode_switch_has_a_rhythm_sets_page_and_the_menu_follows(win):
    w, fake, _ = win
    assert w._side_panel() is w.rhythm_panel and w.list_stack.currentWidget() is w.rhythm_list and w.right_stack.currentWidget() is w.rhythm_panel
    assert w.library_header.text() == "USER Rhythm Sets" and w.btn_read_names.text() == "Read Rhythm Set Names"
    assert w.read_action.text() == "Read Temporary Rhythm Set" and w.open_action.text() == "Open Rhythm Set .syx..." and w.send_action.text() == "Send to Temporary Rhythm Set"
    w.mode_tabs.setCurrentIndex(1)
    assert w._side_panel() is w.performance_panel and w.read_action.text() == "Read Temporary Performance"
    w.mode_tabs.setCurrentIndex(0)
    assert w._side_panel() is None and w.read_action.text() == "Read Temporary Patch"


def test_reading_the_temporary_rhythm_set_fills_the_editor_and_changes_nothing(win):
    w, fake, _ = win
    fake.temp_rhythm.name = "Big Kit"
    fake.temp_rhythm.set(NOTE, "tone_level", 99, key=36)
    panel, editor = shown(w)
    assert panel.label.text() == "Temporary rhythm set · Big Kit" and panel.problems_label.isHidden()
    assert editor.name_edit.text() == "Big Kit" and editor.chosen_key() == 36 and editor.widget_for("tone_level").value() == 99
    assert fake.writes == [] and w.save_action.isEnabled() and w.btn_read_names.isEnabled()


def test_the_names_of_the_two_user_sets_and_opening_one(win):
    w, fake, _ = win
    w.read_names()
    w.worker.process_pending()
    assert [w.rhythm_list.item(i).text() for i in range(2)] == ["1  Rhythm 1", "2  Rhythm 2"] and "2 USER rhythm set names" in w.statusBar().currentMessage()
    w._open_rhythm_from_item(w.rhythm_list.item(1))
    w.worker.process_pending()
    assert w.rhythm_panel.label.text() == "USER rhythm set 2 · Rhythm 2" and w.names_list.count() == 0


def test_an_edit_goes_to_the_chosen_key_and_live_to_the_temporary_rhythm_set(win):
    w, fake, _ = win
    panel, editor = shown(w)
    editor.choose_key(40)
    editor.widget_for("tone_level").setValue(88)  # (a captured key would have edited key 36)
    w.worker.process_pending()
    assert panel._shown[1].get(NOTE, "tone_level", key=40) == 88 and panel._shown[1].get(NOTE, "tone_level", key=36) == 0
    assert fake.temp_rhythm.get(NOTE, "tone_level", key=40) == 88 and fake.temp_rhythm.get(NOTE, "tone_level", key=36) == 0
    assert all(wr.address[:2] == (0x02, 0x09) for wr in fake.writes) and fake.user_rhythms[0].get(NOTE, "tone_level", key=40) == 0
    assert panel.label.text().endswith("(edited)")
    panel.undo()
    w.worker.process_pending()
    assert fake.temp_rhythm.get(NOTE, "tone_level", key=40) == 0 and not panel.is_dirty()


def test_a_file_or_a_user_set_is_not_sent_live(win):
    w, fake, _ = win
    w.read_names()
    w.worker.process_pending()
    w._open_rhythm_from_item(w.rhythm_list.item(0))
    w.worker.process_pending()
    panel = w.rhythm_panel
    panel.editor.widget_for("tone_level").setValue(50)
    w.worker.process_pending()
    assert fake.writes == [] and panel.is_dirty()  # the unit's temporary rhythm set is not the shown set: nothing to hear


def test_the_name_is_edited_and_sent(win):
    w, fake, _ = win
    panel, editor = shown(w)
    editor.name_edit.setText("Renamed")
    editor.name_edit.editingFinished.emit()
    w.worker.process_pending()
    assert panel._shown[1].name == "Renamed" and fake.temp_rhythm.name == "Renamed"


def test_the_wave_card_names_the_wave_and_a_tone_that_is_off_looks_off(win):
    w, fake, _ = win
    fake.temp_rhythm.set(NOTE, "tone_switch", 1, key=36)
    fake.temp_rhythm.set(NOTE, "wave_group_id", 1, key=36)  # INT-A
    fake.temp_rhythm.set(NOTE, "wave_number", 2, key=36)
    panel, editor = shown(w)
    assert "INT-A 003" in editor.key_label.text() and "INT-A 003" in editor._key_tooltip(36)
    assert 36 not in editor.selector._dimmed and 37 in editor.selector._dimmed and "tone off" in editor._key_tooltip(37)
    editor.widget_for("tone_switch").setCurrentIndex(0)
    editor.widget_for("tone_switch").activated.emit(0)
    assert 36 in editor.selector._dimmed and "tone off" in editor.key_label.text()


def test_copying_a_key_sends_the_whole_key_and_undo_puts_it_back(win):
    w, fake, _ = win
    panel, editor = shown(w)
    for name, value in (("tone_level", 90), ("coarse_tune", 70), ("cutoff_frequency", 33), ("tone_pan", 20), ("reverb_send_level", 55), ("filter_type", 1)):
        control = editor.widget_for(name)
        control.setValue(value) if hasattr(control, "setValue") else (control.set_raw(value), control.activated.emit(0))
    w.worker.process_pending()
    undo_before = len(panel._undo)
    writes_before = len(fake.writes)
    editor.copy_key_to(36, 50)
    w.worker.process_pending()
    assert panel._shown[1].notes[50] == panel._shown[1].notes[36] and fake.temp_rhythm.notes[50] == fake.temp_rhythm.notes[36]
    assert len(fake.writes) - writes_before == 1  # one block for the key, not one write per value
    assert len(panel._undo) == undo_before + 1
    panel.undo()
    w.worker.process_pending()
    assert panel._shown[1].notes[50] == rhythm.RhythmSet.minimum().notes[50] and fake.temp_rhythm.notes[50] == rhythm.RhythmSet.minimum().notes[50]
    panel.redo()
    w.worker.process_pending()
    assert fake.temp_rhythm.notes[50] == fake.temp_rhythm.notes[36]


def test_swapping_two_keys(win):
    w, fake, _ = win
    panel, editor = shown(w)
    editor.widget_for("tone_level").setValue(90)
    editor.swap_keys(36, 37)
    w.worker.process_pending()
    working = panel._shown[1]
    assert working.get(NOTE, "tone_level", key=37) == 90 and working.get(NOTE, "tone_level", key=36) == 0
    assert fake.temp_rhythm == working


def test_send_to_temporary_and_write_to_user_back_up_first(win, monkeypatch):
    w, fake, tmp_path = win
    panel, editor = shown(w)
    panel.live_check.setChecked(False)
    editor.name_edit.setText("Mine")
    editor.name_edit.editingFinished.emit()
    panel.send_temporary()
    w.worker.process_pending()
    assert fake.temp_rhythm.name == "Mine" and panel._temp_synced
    monkeypatch.setattr(rp.SlotDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(rp.SlotDialog, "slot", lambda self: 1)
    w.read_names()
    w.worker.process_pending()
    w.write_user()
    w.worker.process_pending()
    assert fake.user_rhythms[1].name == "Mine" and not panel.is_dirty() and w.rhythm_list.item(1).text() == "2  Mine"
    assert len(list((tmp_path / "backups").glob("RHYTHM-2-*.syx"))) == 1 and fake.user_rhythms[0].name == "Rhythm 1"


def test_a_failed_live_edit_switches_live_sending_off_once(win, monkeypatch):
    w, fake, _ = win
    panel, editor = shown(w)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a) or QMessageBox.StandardButton.Ok)
    fake.ignore_writes = True
    editor.widget_for("tone_level").setValue(10)
    editor.widget_for("tone_level").setValue(20)
    w.worker.process_pending()
    assert len(warnings) == 1 and not panel.live_check.isChecked() and not panel._temp_synced


def test_clicking_a_key_plays_it_on_the_channel_of_part_10_and_choosing_a_set_sends_bank_select(win, monkeypatch):
    w, fake, _ = win
    panel, editor = shown(w)
    monkeypatch.setattr(rp.QTimer, "singleShot", lambda ms, fn: fn())  # no waiting: the note-off at once
    w.audition.velocity.setValue(80)
    click_key(editor, 38)
    assert fake.channel_messages == [audition.note_on(9, 38, 80), audition.note_off(9, 38)] and editor.chosen_key() == 38
    editor.play_check.setChecked(False)
    fake.channel_messages.clear()
    click_key(editor, 39)
    assert fake.channel_messages == [] and editor.chosen_key() == 39  # chosen, not played
    panel.channel_combo.setCurrentIndex(11)
    panel.select_on_unit(1)
    assert fake.channel_messages == audition.rhythm_select(11, "USER", 1) and not panel._temp_synced


def test_the_rhythm_bank_table():
    assert audition.rhythm_select(9, "USER", 0)[:2] == [bytes([0xB9, 0, 80]), bytes([0xB9, 32, 0])] and audition.rhythm_select(9, "PR-E", 1)[2] == bytes([0xC9, 1])
    with pytest.raises(ValueError):
        audition.rhythm_select(9, "USER", 2)


def test_opening_and_saving_a_syx(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w, fake, _ = win
    panel, editor = shown(w)
    target = tmp_path / "kit.syx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    w.save_shown_patch()
    assert target.stat().st_size > 65 * 20 and set(rhythm.parse_syx(target.read_bytes())) == {rhythm.TEMPORARY_BASE}
    panel.live_check.setChecked(False)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    w.open_syx()
    assert panel.label.text().lower().startswith("kit.syx") and not panel._temp_synced and panel.btn_send.isEnabled() and w.send_action.isEnabled()


def test_values_outside_the_manuals_ranges_are_flagged(win):
    w, fake, _ = win
    fake.temp_rhythm.notes[60][params.load_table().block(NOTE).param("wave_group_type").offset] = 9
    panel, editor = shown(w)
    assert "1 value(s) outside" in panel.problems_label.text() and "key 60" in panel.problems_label.text()


def test_the_raw_values_tab_shows_the_common_block_and_the_chosen_key(win):
    w, fake, _ = win
    panel, editor = shown(w)
    editor.choose_key(41)
    editor.tabs.setCurrentWidget(panel.tree)
    assert [panel.tree.topLevelItem(i).text(0) for i in range(2)] == ["Common", "Key 41 (F2)"] and panel.tree.topLevelItem(1).childCount() == len(params.load_table().block(NOTE).params)
    editor.choose_key(42)
    assert panel.tree.topLevelItem(1).text(0) == "Key 42 (F#2)"


def test_the_demo_unit_holds_two_playable_kits():
    from jv_studio.core import demo_unit, validate

    unit = demo_unit.make_demo_unit()
    assert [r.name for r in unit.user_rhythms] == ["Standard Kit", "Hip Hop Kit"] and all(validate.out_of_range_rhythm(r) == [] for r in unit.user_rhythms)
    assert all(r.get(NOTE, "tone_switch", key=k) == 1 for r in unit.user_rhythms for k in rhythm.KEYS)


def test_the_mini_keyboard_chooses_keys_by_click_and_drag_and_shows_the_chosen_one(win):
    w, fake, _ = win
    panel, editor = shown(w)
    selector = editor.selector
    assert selector._first == 35 and selector._last == 98 and selector.selected() == 36 and not selector.hasFocus()
    editor.play_check.setChecked(False)
    picked = []
    selector.key_picked.connect(picked.append)
    selector.resize(1000, 66)
    black = selector._key_rect(37).center().toPoint()  # C#2: a black key wins where it overlaps a white one
    QTest.mouseClick(selector, Qt.MouseButton.LeftButton, pos=black)
    assert picked == [37] and editor.chosen_key() == 37 and selector.selected() == 37
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, pos=selector._key_rect(40).center().toPoint())
    QTest.mouseMove(selector, selector._key_rect(41).center().toPoint())
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, pos=selector._key_rect(41).center().toPoint())
    assert picked[1:] == [40, 41] and editor.chosen_key() == 41  # a drag browses the keys
    editor.choose_key(98)
    assert selector.selected() == 98
    selector.grab()  # paints (with dimmed keys: every tone of the minimum set is off)
    assert fake.channel_messages == []  # choosing is not playing when "Play on click" is off
