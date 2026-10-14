# Switching the unit's mode (Patch / Performance), and the audition bar following the tab, the part and Part 10.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, audition, midi, params, performance, system
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker

PART = performance.PART


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
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    return w, fake, tmp_path


def read_system(w):
    w.audition.unit_button.click()
    w.worker.process_pending()


def sound_mode(fake):
    return system.System(bytearray(fake.other[0])).get("sound_mode")


# -- switching the mode ----------------------------------------------------------------------------------------------------------


def test_switching_to_performance_mode_writes_one_byte_after_a_backup_and_reads_back(win):
    w, fake, tmp_path = win
    read_system(w)
    assert w._sound_mode == 1 and w.mode_patch_action.isChecked() and not w.mode_performance_action.isChecked()
    w.set_unit_mode(0)
    w.worker.process_pending()
    assert sound_mode(fake) == 0 and w._sound_mode == 0 and w.mode_performance_action.isChecked() and not w.mode_patch_action.isChecked()
    assert [(wr.address, wr.data) for wr in fake.writes] == [((0, 0, 0, 0), b"\x00")]  # ONE byte: the Sound Mode, nothing else of the System block
    backups = list((tmp_path / "backups").glob("SYSTEM-*.syx"))
    assert len(backups) == 1 and backups[0].stat().st_size == 504  # the whole System section (18 blocks), restorable
    assert "Performance" in w.status_pill.text()


def test_switching_back_to_patch_mode_and_the_editors_are_read_again(win):
    w, fake, _ = win
    w.audition.unit_button.click()
    w.worker.process_pending()
    w.set_unit_mode(0)
    w.worker.process_pending()
    fake.temporary.name = "Changed Mid"
    w.set_unit_mode(1)
    w.worker.process_pending()
    assert sound_mode(fake) == 1 and w._sound_mode == 1
    assert not w._temp_synced or w.patch_label.text().endswith("Changed Mid")  # (the reload ran behind the job)
    w.worker.process_pending()
    assert w.patch_label.text() == "Temporary patch · Changed Mid"


def test_nothing_is_sent_for_the_mode_the_unit_is_already_in_for_gm_or_without_ports_or_a_free_worker(win):
    w, fake, _ = win
    read_system(w)
    w.set_unit_mode(1)
    assert fake.writes == [] and "already in Patch mode" in w.statusBar().currentMessage()
    w.set_unit_mode(2)  # GM is not a mode this switch offers
    assert fake.writes == []
    w._sound_mode = 2
    w.set_unit_mode(0)
    assert fake.writes == [] and "GM System Off first" in w.statusBar().currentMessage()
    w._refresh_connection()
    assert not w.mode_patch_action.isEnabled() and not w.mode_performance_action.isEnabled()  # (the items are off in GM mode)
    w._sound_mode = 1
    w.worker.submit("temporary")  # busy
    w.set_unit_mode(0)
    assert fake.writes == []
    w.worker.process_pending()
    w._firmware_running = True
    w.set_unit_mode(0)
    assert fake.writes == []
    w._firmware_running = False  # (left on, closing the window at the end of the run would ask a question and hang)


def test_a_failed_switch_says_so_and_forgets_the_request(win):
    w, fake, _ = win
    read_system(w)
    fake.ignore_writes = True  # the unit stores nothing: the read-back catches it
    w.set_unit_mode(0)
    w.worker.process_pending()
    assert w._mode_switch is None and w._sound_mode == 1 and sound_mode(fake) == 1


# -- the pill ---------------------------------------------------------------------------------------------------------------------


def test_the_pill_says_when_the_tab_edits_another_mode_and_one_click_switches(win):
    w, fake, _ = win
    read_system(w)
    assert w.status_pill.text() == "● JV-1010 · Patch mode" and w.status_pill.property("state") == "ok"
    w.mode_tabs.setCurrentIndex(1)
    assert w.status_pill.text() == "● JV-1010 is in Patch mode · click to switch to Performance" and w.status_pill.property("state") == "warn"
    w.mode_tabs.setCurrentIndex(2)  # Rhythm Sets are Part 10 of a performance
    assert "click to switch to Performance" in w.status_pill.text()
    w.status_pill.clicked.emit()
    w.worker.process_pending()
    assert sound_mode(fake) == 0 and w.status_pill.text() == "● JV-1010 · Performance mode" and w.status_pill.property("state") == "ok"
    w.mode_tabs.setCurrentIndex(0)
    assert w.status_pill.text() == "● JV-1010 is in Performance mode · click to switch to Patch"


def test_clicking_the_pill_when_nothing_mismatches_offers_the_modes(win, monkeypatch):
    w, fake, _ = win
    read_system(w)
    shown = []
    monkeypatch.setattr(w, "_show_mode_menu", lambda: shown.append("menu"))
    w.status_pill.clicked.emit()
    assert shown == ["menu"] and fake.writes == []
    monkeypatch.undo()
    w._show_mode_menu()  # (a real menu, shown without blocking)
    assert [a.text() for a in w._mode_menu.actions()] == ["Patch Mode", "Performance Mode"]
    w._mode_menu.close()


def test_the_menu_actions_switch_the_mode(win):
    w, fake, _ = win
    read_system(w)
    assert w.mode_patch_action.isEnabled() and w.mode_performance_action.text() == "Performance Mode"
    w.mode_performance_action.trigger()
    w.worker.process_pending()
    assert sound_mode(fake) == 0
    w.mode_patch_action.trigger()
    w.worker.process_pending()
    assert sound_mode(fake) == 1


def test_gm_on_and_off_keep_the_pill_and_the_mode_items_honest(win, monkeypatch):
    w, fake, _ = win
    read_system(w)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.gm_system_on()
    assert w.status_pill.property("state") == "warn" and not w.mode_patch_action.isEnabled()
    w.gm_system_off()
    assert w._sound_mode is None and w.mode_patch_action.isEnabled()


# -- the audition bar follows the tab, the part and Part 10 -------------------------------------------------------------------------


def prepare_performance(fake):
    perf = fake.temp_performance
    for part, channel in enumerate((0, 1, 2, 3)):
        perf.set(PART, "midi_channel", channel, part=part)
        perf.set(PART, "receive_switch", 1, part=part)
        perf.set(PART, "receive_program_change_switch", 1, part=part)
    perf.set(PART, "patch_group_type", 0, part=1)
    perf.set(PART, "patch_group_id", 3, part=1)  # part 2: Preset A, patch 001
    perf.set(PART, "patch_number", 0, part=1)
    perf.set(PART, "patch_group_id", 1, part=2)  # part 3: USER 008
    perf.set(PART, "patch_number", 7, part=2)
    perf.set(PART, "midi_channel", 9, part=9)  # part 10 on channel 10


def open_performances(w):
    w.mode_tabs.setCurrentIndex(1)
    w.read_temporary()
    w.worker.process_pending()
    w.performance_panel.ensure_editor()


def test_editing_a_part_puts_the_audition_bar_on_its_channel_and_patch(win):
    w, fake, _ = win
    prepare_performance(fake)
    read_system(w)
    open_performances(w)
    editor = w.performance_panel.editor
    editor.select_part(1)  # Part 2
    assert w.audition.channel() == 1 and w.audition.bank_combo.currentData() == "PR-A" and w.audition.patch_combo.currentIndex() == 0
    editor.select_part(2)  # Part 3: a USER patch on channel 3
    assert w.audition.channel() == 2 and w.audition.bank_combo.currentData() == "USER" and w.audition.patch_combo.currentIndex() == 7
    assert fake.channel_messages == []  # looking at a part plays and sends nothing
    editor.part_combo.setCurrentIndex(1)
    editor.part_combo.activated.emit(1)  # the Part box
    assert w.audition.channel() == 1


def test_changing_a_parts_channel_or_patch_in_the_editor_moves_the_bar(win):
    w, fake, _ = win
    prepare_performance(fake)
    read_system(w)
    open_performances(w)
    editor = w.performance_panel.editor
    editor.select_part(1)
    editor.widget_for(PART, "midi_channel").set_raw(4)  # (shown: the next line is the edit)
    combo = editor.widget_for(PART, "midi_channel")
    combo.setCurrentIndex(5)
    combo.activated.emit(5)
    assert w.audition.channel() == 5
    working = w.performance_panel.shown_performance()
    working.set(PART, "patch_group_id", 5, part=1)  # an edit made from the Choose Patch... dialog arrives as these three values
    working.set(PART, "patch_number", 12, part=1)
    w.performance_panel._on_param_committed(PART, "patch_number", 1, 12)
    assert w.audition.bank_combo.currentData() == "PR-C" and w.audition.patch_combo.currentIndex() == 12


def test_the_rhythm_tab_puts_the_bar_on_part_10s_channel_and_switches_the_patch_boxes_off(win):
    w, fake, _ = win
    read_system(w)
    w.mode_tabs.setCurrentIndex(2)
    assert w.audition.channel() == 9  # no performance read yet: channel 10
    assert not w.audition.bank_combo.isEnabled() and not w.audition.patch_combo.isEnabled() and not w.audition.next_button.isEnabled() and "rhythm set" in w.audition.bank_combo.toolTip()
    before = fake.channel_messages[:]
    w.audition.keyboard.patch_step.emit(1)  # the `.` key
    w.audition.keyboard.bank_step.emit(1)
    w.audition._send_patch()
    assert fake.channel_messages == before  # a patch chosen on Part 10 would replace its rhythm set: nothing is sent
    w.mode_tabs.setCurrentIndex(0)
    assert w.audition.bank_combo.isEnabled() and w.audition.channel() == 0


def test_part_10s_real_channel_is_used_when_the_performance_says_so(win):
    w, fake, _ = win
    prepare_performance(fake)
    fake.temp_performance.set(PART, "midi_channel", 14, part=9)
    read_system(w)
    open_performances(w)
    w.mode_tabs.setCurrentIndex(2)
    assert w.audition.channel() == 14
    w.rhythm_panel.play_key(40)  # keys are played on the bar's channel
    assert fake.channel_messages[-2:][0][0] == 0x90 | 14 or fake.channel_messages[-1][0] == 0x80 | 14


def test_the_patches_tab_uses_the_units_patch_receive_channel(win):
    w, fake, _ = win
    params.write(fake.other[0], params.load_table().block("system_common").param("patch_receive_channel"), 3)
    read_system(w)
    assert w.audition.channel() == 3
    w.mode_tabs.setCurrentIndex(2)
    w.mode_tabs.setCurrentIndex(0)
    assert w.audition.channel() == 3


# -- a patch chosen for a part is read back --------------------------------------------------------------------------------------


def test_a_patch_chosen_in_the_bar_for_a_part_shows_in_the_performance_editor(win):
    w, fake, _ = win
    prepare_performance(fake)
    fake.user[4].name = "Fifth"
    params.write(fake.other[0], params.load_table().block("system_common").param("sound_mode"), 0)  # Performance mode
    read_system(w)
    open_performances(w)
    editor = w.performance_panel.editor
    editor.select_part(1)
    w.audition.choose("USER", 4)  # sent on part 2's channel
    assert fake.channel_messages[-3:] == audition.patch_select(1, "USER", 4)
    assert not w.performance_panel._temp_synced
    w._audition_timer.stop()
    w._after_audition_choice()
    w.worker.process_pending()
    shown = w.performance_panel.shown_performance()
    assert (shown.get(PART, "patch_group_id", part=1), shown.get(PART, "patch_number", part=1)) == (1, 4) and w.performance_panel._temp_synced
    assert w.audition.bank_combo.currentData() == "USER" and w.audition.patch_combo.currentIndex() == 4
    assert w.names_list.count() == 0 or not any(w.names_list.item(i).font().bold() for i in range(w.names_list.count()))  # (the patch list is not marked: this was a part)


def test_a_choice_for_a_part_with_unsent_edits_or_in_patch_mode_is_not_read_over_them(win):
    w, fake, _ = win
    prepare_performance(fake)
    read_system(w)  # Patch mode
    open_performances(w)
    w.audition.choose("USER", 4)
    w._audition_timer.stop()
    w._after_audition_choice()
    assert "Patch mode" in w.statusBar().currentMessage() and "switch to Performance" in w.statusBar().currentMessage()
    params.write(fake.other[0], params.load_table().block("system_common").param("sound_mode"), 0)
    read_system(w)
    editor = w.performance_panel.editor
    editor.widget_for(PART, "part_level", part=0, grid=True).setValue(33)
    w.worker.process_pending()
    w.audition.choose("USER", 5)
    w._audition_timer.stop()
    w._after_audition_choice()
    assert "unsent edits stay in the editor" in w.statusBar().currentMessage() and w.performance_panel.is_dirty()


# -- the simulated unit takes a Program Change per part in Performance mode ------------------------------------------------------------


def test_the_simulated_unit_changes_the_parts_that_listen_on_the_channel_in_performance_mode():
    unit = FakeJV1010()
    prepare_performance(unit)
    params.write(unit.other[0], params.load_table().block("system_common").param("sound_mode"), 0)
    for message in audition.patch_select(2, "PR-B", 9):  # channel 3: part 3 only
        unit(message)
    perf = unit.temp_performance
    assert [perf.get(PART, "patch_group_id", part=p) for p in (0, 1, 2, 3)] == [0, 3, 4, 0] and perf.get(PART, "patch_number", part=2) == 9
    assert perf.get(PART, "patch_group_id", part=1) == 3  # part 2 (channel 2) untouched
    perf.set(PART, "receive_program_change_switch", 0, part=3)
    for message in audition.patch_select(3, "PR-E", 1):
        unit(message)
    assert perf.get(PART, "patch_group_id", part=3) == 0  # a part that does not take program changes keeps its patch
