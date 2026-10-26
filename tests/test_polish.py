# The polish pass: the connection pill, Raw Values behind a menu item, tone tab dots, the accent Write button, the list filter and the "playing" marker.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, audition, midi, params, patch
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.patch_editor import PatchEditor
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    fake = FakeJV1010("Init Patch")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    return w, fake


# -- the connection pill -----------------------------------------------------------------------------------------------------------


def test_the_pill_is_hidden_without_ports_and_says_what_is_known_with_them(qapp):
    w = MainWindow(MidiSession(), worker=UnitWorker(MidiSession(), timeout=0.05), start_worker=False)
    assert w.status_pill.isHidden() and w.connection_label.text().startswith("No MIDI ports")


def test_the_pill_follows_what_the_window_learns_about_the_unit(win, monkeypatch):
    w, fake = win
    assert not w.status_pill.isHidden() and w.status_pill.text() == "● Ports open" and w.status_pill.property("state") == "idle"
    w.audition.unit_button.click()  # reads the System block: Patch mode
    w.worker.process_pending()
    assert w.status_pill.text() == "● JV-1010 · Patch mode" and w.status_pill.property("state") == "ok"
    fake.gm_mode = True  # the unit stops answering data requests
    w.read_temporary()
    w.worker.process_pending()
    assert w.status_pill.text() == "● No answer from the unit" and w.status_pill.property("state") == "bad"
    fake.gm_mode = False
    w.read_temporary()
    w.worker.process_pending()
    assert w.status_pill.property("state") == "ok"  # an answer clears it
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.gm_system_on()
    assert w.status_pill.text().startswith("● GM mode") and w.status_pill.property("state") == "warn"
    w.gm_system_off()
    assert w.status_pill.property("state") == "idle"  # the mode is not known again until it is read


def test_the_pill_names_the_simulated_unit_in_demo_mode(qapp, tmp_path, monkeypatch):
    from jv_studio.ui import demo

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    session, _ = demo.build_demo(0, use_backup=False)
    w = MainWindow(session=session, worker=UnitWorker(session, timeout=0.05), start_worker=False, demo=True)
    assert w.status_pill.text() == "● Simulated JV-1010"


def test_the_logo_is_smaller_in_the_window_than_in_about(win):
    w, _ = win
    assert "font-size: 10px" in w.lbl_logo.styleSheet()


# -- Raw Values -----------------------------------------------------------------------------------------------------------------


def test_the_raw_values_tabs_are_hidden_until_asked_for_and_the_choice_is_remembered(win):
    w, fake = win
    assert not w.raw_action.isChecked() and not app_config.get_show_raw_values()
    index = w.editor.tabs.indexOf(w.tree)
    assert not w.editor.tabs.isTabVisible(index) and w.editor.tabs.isTabVisible(0)
    w.mode_tabs.setCurrentIndex(1)
    w.mode_tabs.setCurrentIndex(2)
    for panel in (w.performance_panel, w.rhythm_panel):
        panel.ensure_editor()  # (built when its tab is first shown on screen)
        assert not panel.editor.tabs.isTabVisible(panel.editor.tabs.indexOf(panel.tree))  # (built hidden)
    w.raw_action.trigger()
    assert w.editor.tabs.isTabVisible(index) and app_config.get_show_raw_values()
    for panel in (w.performance_panel, w.rhythm_panel):
        assert panel.editor.tabs.isTabVisible(panel.editor.tabs.indexOf(panel.tree))
    w.editor.tabs.setCurrentIndex(index)
    w.raw_action.trigger()  # hiding the tab that is showing moves to the first
    assert w.editor.tabs.currentIndex() == 0 and not w.editor.tabs.isTabVisible(index) and not app_config.get_show_raw_values()


def test_a_remembered_choice_shows_the_tab_at_the_next_start(qapp, tmp_path, monkeypatch):
    app_config.save_show_raw_values(True)
    w = MainWindow(MidiSession(), worker=UnitWorker(MidiSession(), timeout=0.05), start_worker=False)
    assert w.raw_action.isChecked() and w.editor.tabs.isTabVisible(w.editor.tabs.indexOf(w.tree))


# -- tone tabs ------------------------------------------------------------------------------------------------------------------


def test_each_tone_tab_has_a_dot_that_says_whether_the_tone_is_on(qapp):
    editor = PatchEditor()
    working = patch.Patch.minimum()
    working.set(patch.TONE, "tone_switch", 1, tone=1)
    editor.set_patch(working)
    assert [editor.tabs.tabText(i) for i in range(1, 5)] == ["○ Tone 1", "● Tone 2", "○ Tone 3", "○ Tone 4"] and editor.tabs.tabText(0) == "Common"
    assert "switched off" in editor.tabs.tabToolTip(1) and editor.tabs.tabToolTip(2) == "Tone 2 is on."
    editor.tabs.setCurrentIndex(1)
    editor.widget_for(patch.TONE, "tone_switch", 0).click()  # switching a tone on in the editor moves its dot
    assert editor.tabs.tabText(1) == "● Tone 1"
    working.set(patch.TONE, "tone_switch", 0, tone=1)
    editor.refresh()  # and so does a change from outside (undo, a read)
    assert editor.tabs.tabText(2) == "○ Tone 2"


# -- the accent Write button ----------------------------------------------------------------------------------------------------


def test_write_to_user_takes_the_accent_while_there_are_edits_to_keep(win):
    w, fake = win
    w.read_temporary()
    w.worker.process_pending()
    assert w.btn_write.property("primary") == "false"
    box = w.editor.widget_for("patch_common", "patch_name")
    box.setText("Edited")
    box.editingFinished.emit()
    w.worker.process_pending()
    assert w.btn_write.property("primary") == "true" and "● edited" in w.patch_label.text()
    w.revert_edits()
    assert w.btn_write.property("primary") == "false"
    w.mode_tabs.setCurrentIndex(1)
    w.read_temporary()
    w.worker.process_pending()
    assert w.performance_panel.btn_write.property("primary") == "false"
    w.performance_panel.editor.widget_for("performance_part", "part_level", part=2, grid=True).setValue(10)
    w.worker.process_pending()
    assert w.performance_panel.btn_write.property("primary") == "true"


# -- the list filter ------------------------------------------------------------------------------------------------------------


def hidden_rows(listing):
    return [listing.item(i).text() for i in range(listing.count()) if listing.item(i).isHidden()]


def test_the_filter_shows_only_matching_rows_even_ones_that_arrive_later(win):
    w, fake = win
    fake.user[2].name = "Soft Pad"
    fake.user[40].name = "Big Pad"
    w.list_filter.setText("pad")  # typed before the names are read
    w.read_names()
    w.worker.process_pending()
    shown = [w.names_list.item(i).text() for i in range(w.names_list.count()) if not w.names_list.item(i).isHidden()]
    assert shown == ["003  Soft Pad", "041  Big Pad"]
    w.list_filter.setText("042")  # a number matches too
    assert [w.names_list.item(i).text() for i in range(128) if not w.names_list.item(i).isHidden()] == ["042  User 042"]
    w.list_filter.clear()
    assert hidden_rows(w.names_list) == []


def test_each_list_has_its_own_filter_and_switching_tabs_clears_it(win):
    w, fake = win
    w.read_names()
    w.worker.process_pending()
    w.list_filter.setText("user 01")
    assert len(hidden_rows(w.names_list)) == 118
    w.mode_tabs.setCurrentIndex(1)
    assert w.list_filter.text() == "" and hidden_rows(w.perf_list) == []
    w.read_names()
    w.worker.process_pending()
    w.list_filter.setText("perf 3")
    assert [w.perf_list.item(i).text() for i in range(32) if not w.perf_list.item(i).isHidden()] == ["30  Perf 30", "31  Perf 31", "32  Perf 32"]
    w.mode_tabs.setCurrentIndex(0)
    assert hidden_rows(w.names_list) == []  # (the patch list was left as it was)


# -- the playing marker ---------------------------------------------------------------------------------------------------------


def test_the_patch_the_unit_is_playing_is_marked_in_the_list(win):
    w, fake = win
    w.read_names()
    w.worker.process_pending()
    assert all(not w.names_list.item(i).font().bold() for i in range(128))
    w.audition.choose("USER", 7)  # chosen in the bar
    assert w.names_list.item(7).font().bold() and not w.names_list.item(7).icon().isNull() and "playing" in w.names_list.item(7).toolTip()
    w.audition.choose("USER", 9)
    assert not w.names_list.item(7).font().bold() and w.names_list.item(7).icon().isNull() and w.names_list.item(9).font().bold()  # it moves
    assert w.names_list.item(9).text() == "010  User 010"  # (the text is untouched)
    w.audition.choose("PR-A", 3)  # a preset: no USER patch is playing
    assert not any(w.names_list.item(i).font().bold() for i in range(128))


def test_a_refresh_marks_what_the_front_panel_chose(win):
    w, fake = win
    w.read_names()
    w.worker.process_pending()
    table = params.load_table().block("system_common")
    for key, value in (("sound_mode", 1), ("patch_group_type", 0), ("patch_group_id", 1), ("patch_number", 21)):
        params.write(fake.other[0], table.param(key), value)
    w.refresh_all()
    w.worker.process_pending()
    assert [i for i in range(128) if w.names_list.item(i).font().bold()] == [21]
    params.write(fake.other[0], table.param("sound_mode"), 0)  # Performance mode: the patch list says nothing
    w.refresh_all()
    w.worker.process_pending()
    assert not any(w.names_list.item(i).font().bold() for i in range(128))


def test_the_mode_menu_hangs_from_the_right_edge_of_the_pill_not_its_far_left(win, monkeypatch):
    from PySide6.QtWidgets import QMenu

    w, _fake = win
    w.resize(1260, 700)
    w.show()
    QApplication.processEvents()
    asked = []  # (the offscreen screen is narrower than the window, so Qt would clamp a real popup: look at where it was ASKED to open)
    monkeypatch.setattr(QMenu, "popup", lambda self, pos, *a: asked.append((self.sizeHint().width(), pos)))
    w._show_mode_menu()
    width, pos = asked[0]
    pill_right = w.status_pill.mapToGlobal(w.status_pill.rect().bottomRight())
    assert abs(pos.x() + width - pill_right.x()) <= 2 and width < w.status_pill.width()
