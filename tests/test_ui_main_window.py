# The main window: restoring the saved ports, the connection card, and the hardware check.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts, silent
from jv_studio.core import app_config, midi, midi_diagnostics
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    ports = FakePorts(FakeJV1010("Init Patch"))
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append((title, text)) or QMessageBox.StandardButton.Ok)
    return ports, session, messages


def window(session, **kwargs):
    # no real thread: tests run jobs with worker.process_pending(); and a short timeout, so a silent unit fails in milliseconds
    return MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False, **kwargs)


def test_a_fresh_install_has_no_ports_and_cannot_detect(env):
    _, session, _ = env
    w = window(session)
    assert "No MIDI ports are open" in w.connection_label.text() and not w.btn_detect.isEnabled() and not w.detect_action.isEnabled()


def test_the_saved_ports_are_reopened_at_startup(env):
    _, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    assert session.is_open and "JV In" in w.connection_label.text() and "JV Out" in w.connection_label.text() and w.btn_detect.isEnabled()


def test_saved_ports_the_system_no_longer_offers_are_not_opened(env):
    _, session, _ = env
    app_config.save_ports("Gone In", "Gone Out")
    w = window(session)
    assert not session.is_open and "not available" in w.statusBar().currentMessage()


def test_a_saved_port_that_fails_to_open_is_survivable(env):
    _, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    session.connection_factory = lambda *a: (_ for _ in ()).throw(RuntimeError("busy"))
    w = window(session)
    assert not session.is_open and "Couldn't open" in w.statusBar().currentMessage()


def test_detecting_shows_what_the_unit_said(env):
    _, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    w.detect_hardware()
    assert "Roland JV-1010 found" in w.detect_results_label.text() and 'Temporary patch: "Init Patch"' in w.detect_results_label.text()
    assert w.btn_detect.isEnabled() and w.btn_detect.text() == "Detect JV-1010" and w.statusBar().currentMessage() == "JV-1010 found"


def test_detecting_with_nothing_connected_says_so(env):
    _, session, messages = env
    w = window(session)
    w.detect_hardware()
    assert messages and "Settings" in messages[0][1]


def test_no_reply_is_reported_in_the_window(env, monkeypatch):
    ports, session, _ = env
    ports.respond = silent
    monkeypatch.setattr(midi_diagnostics, "RECEIVE_TIMEOUT", 0.05)
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    w.detect_hardware()
    assert "No reply" in w.detect_results_label.text() and w.statusBar().currentMessage() == "No JV-1010 found"


def test_closing_the_window_closes_the_ports(env):
    ports, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    w.close()
    assert not session.is_open and sorted(ports.closed) == ["in", "out"]


def test_the_menus_exist(env):
    _, session, _ = env
    w = window(session)
    titles = [a.text() for a in w.menuBar().actions()]
    assert titles == ["&File", "&Edit", "&Hardware", "&Help"]


# -- the read-only viewer ----------------------------------------------------------------------------------------------------


def connected(env):
    ports, session, messages = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    return w, ports


def test_reading_the_temporary_patch_fills_the_viewer(env):
    w, _ = connected(env)
    w.editor.tabs.setCurrentWidget(w.tree)  # the Raw Values tab is only filled while it shows
    w.read_temporary()
    w.worker.process_pending()
    assert w.patch_label.text() == 'the temporary patch: "Init Patch"' and "Every value is inside" in w.problems_label.text()
    assert [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())] == ["Common", "Tone 1", "Tone 2", "Tone 3", "Tone 4"]
    assert w.tree.topLevelItem(0).childCount() == 62 and w.tree.topLevelItem(1).childCount() == 128 and w.save_action.isEnabled()


def test_values_are_shown_the_way_the_panel_shows_them(env):
    w, ports = connected(env)
    w.editor.tabs.setCurrentWidget(w.tree)
    w.read_temporary()
    w.worker.process_pending()
    rows = {w.tree.topLevelItem(0).child(i).text(0): w.tree.topLevelItem(0).child(i).text(1) for i in range(62)}
    assert rows["EFX Type"] == "STEREO-EQ" and rows["Reverb Type"] == "ROOM1" and rows["Patch Name"] == "Init Patch"


def test_a_value_outside_the_manuals_range_is_called_out(env):
    w, ports = connected(env)
    # make the pretend unit hold a bad value, then read it
    unit = ports.respond
    unit.temporary.common[0x0C] = 99
    w.read_temporary()
    w.worker.process_pending()
    assert "1 value(s) outside the manual's ranges" in w.problems_label.text() and "EFX Type" in w.problems_label.text()


def test_the_user_names_are_listed_and_a_double_click_reads_that_patch(env):
    w, _ = connected(env)
    w.read_names()
    w.worker.process_pending()
    assert w.names_list.count() == 128 and w.names_list.item(4).text() == "005  User 005"
    w._read_user_from_item(w.names_list.item(4))
    w.worker.process_pending()
    assert w.patch_label.text() == 'USER:005: "User 005"'
    assert not w.names_progress.isVisible() and not w.btn_cancel.isVisible()


def test_nothing_is_written_while_looking(env):
    w, ports = connected(env)
    w.read_temporary()
    w.read_names()
    w.worker.process_pending()
    assert ports.respond.writes == []


def test_a_failed_read_is_reported_and_leaves_the_window_usable(env, monkeypatch):
    ports, session, _ = env
    ports.respond.gm_mode = True
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append(text) or QMessageBox.StandardButton.Ok)
    w, _ = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    assert warnings and "GM mode" in warnings[0] and w.btn_read_temporary.isEnabled()


def test_saving_writes_a_syx_that_reads_back_as_the_same_patch(env, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from jv_studio.core import patch

    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    target = tmp_path / "out.syx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    w.save_shown_patch()
    assert patch.parse_syx(target.read_bytes())[patch.TEMPORARY_BASE] == ports.respond.temporary


def test_nothing_to_save_before_a_read(env):
    ports, session, _ = env
    w = window(session)
    assert not w.save_action.isEnabled()


def test_settings_and_reads_are_off_while_the_worker_is_busy(env, monkeypatch):
    w, _ = connected(env)
    monkeypatch.setattr(w.worker, "is_idle", lambda: False)
    w._refresh_connection()
    assert not w.btn_settings.isEnabled() and not w.btn_read_temporary.isEnabled() and not w.settings_action.isEnabled()
    opened = []
    monkeypatch.setattr("jv_studio.ui.main_window.SettingsDialog", lambda *a: opened.append(a))
    w.open_settings()
    assert opened == [] and "Wait" in w.statusBar().currentMessage()


# -- writing, backup and restore ---------------------------------------------------------------------------------------------


@pytest.fixture
def writable(env, monkeypatch, tmp_path):
    """A connected window whose backups go to tmp_path, with every dialog answered for us."""
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    w, ports = connected(env)
    answers = {"backup_first": QMessageBox.StandardButton.No}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers["backup_first"])
    return w, ports, answers, tmp_path, QFileDialog


def test_write_and_send_are_off_until_a_patch_is_shown(env):
    w, _ = connected(env)
    assert not w.btn_send.isEnabled() and not w.btn_write.isEnabled() and not w.write_action.isEnabled()
    w.read_temporary()
    w.worker.process_pending()
    assert w.btn_send.isEnabled() and w.btn_write.isEnabled()


def test_send_to_temporary_patch_writes_and_reads_back(writable):
    w, ports, *_ = writable
    ports.respond.user[3].name = "From Slot"
    w._read_user_from_item(type("I", (), {"data": lambda self, role: 3})())
    w.worker.process_pending()
    w.send_temporary()
    w.worker.process_pending()
    assert ports.respond.temporary.name == "From Slot" and "read back" in w.statusBar().currentMessage()


def test_write_to_user_confirms_backs_up_and_updates_the_list(writable, monkeypatch):
    from jv_studio.ui import main_window as mw

    w, ports, answers, tmp_path, _ = writable
    w.read_temporary()
    w.read_names()
    w.worker.process_pending()
    monkeypatch.setattr(mw.WriteUserDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.WriteUserDialog, "slot", lambda self: 9)
    w.write_user()
    w.worker.process_pending()
    assert ports.respond.user[9].name == "Init Patch" and w.names_list.item(9).text() == "010  Init Patch"
    assert len(list((tmp_path / "backups").glob("USER-010-*.syx"))) == 1


def test_cancelling_the_slot_dialog_writes_nothing(writable, monkeypatch):
    from jv_studio.ui import main_window as mw

    w, ports, *_ = writable
    w.read_temporary()
    w.worker.process_pending()
    monkeypatch.setattr(mw.WriteUserDialog, "exec", lambda self: self.DialogCode.Rejected)
    w.write_user()
    w.worker.process_pending()
    assert ports.respond.writes == []


def test_the_first_write_offers_a_whole_unit_backup_and_cancel_stops_it(writable, monkeypatch):
    from jv_studio.ui import main_window as mw

    w, ports, answers, *_ = writable
    answers["backup_first"] = QMessageBox.StandardButton.Cancel
    w.read_temporary()
    w.worker.process_pending()
    monkeypatch.setattr(mw.WriteUserDialog, "exec", lambda self: self.DialogCode.Accepted)
    w.write_user()
    w.worker.process_pending()
    assert ports.respond.writes == []


def test_back_up_then_restore_through_the_window(writable, monkeypatch):
    w, ports, answers, tmp_path, QFileDialog = writable
    target = tmp_path / "unit.syx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    w.back_up_unit()
    w.worker.process_pending()
    assert target.exists() and w._backed_up and "Backup saved" in w.statusBar().currentMessage()
    ports.respond.user[0].name = "Changed"
    from jv_studio.core import memory
    from jv_studio.ui import main_window as mw

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(mw.RestoreDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.RestoreDialog, "sections", lambda self: [memory.RHYTHM])
    w.restore_unit()
    w.worker.process_pending()
    assert "Restored 130 blocks" in w.statusBar().currentMessage()


def test_restore_dialog_leaves_system_unchecked_and_disables_missing_sections(qapp):
    from jv_studio.core import memory
    from jv_studio.ui.unit_dialogs import RestoreDialog

    summary = {memory.SYSTEM: (18, 18), memory.PERFORMANCES: (0, 544), memory.RHYTHM: (130, 130), memory.PATCHES: (640, 640)}
    d = RestoreDialog(summary)
    assert d.sections() == [memory.RHYTHM, memory.PATCHES]
    assert not d.checks[memory.PERFORMANCES].isEnabled() and not d.checks[memory.SYSTEM].isChecked()


def test_the_stock_check_counts_factory_matches_and_flags_the_rest(env):
    from jv_studio.core import params

    w, ports = connected(env)
    factory = params.load_table().factory_user_patches
    for i, f in enumerate(factory):
        ports.respond.user[i].name = f.name
        ports.respond.user[i].set("patch_common", "key_assign_mode", 0 if f.key_assign == "POLY" else 1)
    ports.respond.user[4].name = "Not Stock"
    w.read_names()
    w.worker.process_pending()
    assert w.stock_label.text().startswith("127 of 128 match")
    assert "factory patch here" in w.names_list.item(4).toolTip() and w.names_list.item(5).toolTip() == ""


def test_opening_a_syx_shows_the_patch_and_a_write_needs_no_unit_read(writable, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from jv_studio.core import patch

    w, ports, *_ = writable
    p = patch.Patch.minimum()
    p.name = "From File"
    path = tmp_path / "one.syx"
    path.write_bytes(p.to_syx(patch.user_base(20)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    w.open_syx()
    assert "From File" in w.patch_label.text() and "USER:021" in w.patch_label.text() and w.btn_write.isEnabled()
    assert ports.respond.writes == []


def test_a_file_that_is_not_a_patch_is_refused_politely(writable, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w, *_ = writable
    path = tmp_path / "junk.syx"
    path.write_bytes(b"\xf0\x7e\x10\x06\x01\xf7")
    shown = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: shown.append(text) or QMessageBox.StandardButton.Ok)
    w.open_syx()
    assert shown == ["That file holds no JV-1010 patch."] and w._shown is None


# -- the patch editor in the window ------------------------------------------------------------------------------------------


def test_editing_the_temporary_patch_sends_each_edit_live_and_verified(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.editor.widget_for("patch_tone", "cutoff_frequency", 1).setValue(33)
    w.worker.process_pending()
    assert ports.respond.temporary.get("patch_tone", "cutoff_frequency", tone=1) == 33
    assert w._is_dirty() and "(edited)" in w.patch_label.text() and "Sent to the unit" in w.statusBar().currentMessage()


def test_a_name_edit_goes_live_too(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    box = w.editor.widget_for("patch_common", "patch_name")
    box.setText("Live Name")
    box.editingFinished.emit()
    w.worker.process_pending()
    assert ports.respond.temporary.name == "Live Name"


def test_edits_to_a_patch_that_is_not_on_the_unit_stay_local_until_it_is_sent(env):
    w, ports = connected(env)
    w._read_user_from_item(type("I", (), {"data": lambda self, role: 4})())
    w.worker.process_pending()
    w.editor.widget_for("patch_common", "patch_tempo").setValue(140)
    w.worker.process_pending()
    assert ports.respond.writes == [] and "Send to Temporary Patch" in w.edit_hint.text()
    w.send_temporary()
    w.worker.process_pending()
    assert ports.respond.temporary.get("patch_common", "patch_tempo") == 140 and w._temp_synced
    w.editor.widget_for("patch_common", "patch_tempo").setValue(141)  # now it is in step: live
    w.worker.process_pending()
    assert ports.respond.temporary.get("patch_common", "patch_tempo") == 141


def test_live_sending_can_be_switched_off(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(77)
    w.worker.process_pending()
    assert ports.respond.writes == [] and w._is_dirty()


def test_a_unit_that_does_not_take_a_live_edit_switches_live_sending_off_once(env, monkeypatch):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    ports.respond.ignore_writes = True
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append(text) or QMessageBox.StandardButton.Ok)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(77)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(78)
    w.worker.process_pending()
    assert len(warnings) == 1 and not w.live_check.isChecked() and "Live sending is off" in warnings[0]


def test_revert_goes_back_to_what_was_read(env, monkeypatch):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    original = w.editor.widget_for("patch_common", "patch_tempo").value()
    w.editor.widget_for("patch_common", "patch_tempo").setValue(original + 5)
    assert w.btn_revert.isEnabled()
    w.revert_edits()
    assert not w._is_dirty() and w.editor.widget_for("patch_common", "patch_tempo").value() == original and "(edited)" not in w.patch_label.text()


def test_reading_another_patch_over_edits_asks_first(env, monkeypatch):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(99)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No)
    w.read_temporary()
    w.worker.process_pending()
    assert asked and w.editor.widget_for("patch_common", "patch_tempo").value() == 99  # declined: still editing
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.read_temporary()
    w.worker.process_pending()
    assert not w._is_dirty()


def test_writing_to_user_saves_the_edited_copy(writable, monkeypatch):
    from jv_studio.ui import main_window as mw

    w, ports, answers, tmp_path, _ = writable
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(111)
    monkeypatch.setattr(mw.WriteUserDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.WriteUserDialog, "slot", lambda self: 2)
    w.write_user()
    w.worker.process_pending()
    assert ports.respond.user[2].get("patch_common", "patch_tempo") == 111 and not w._is_dirty()


def test_the_logo_is_top_left_and_matches_appheader_txt(env):
    from pathlib import Path

    _, session, _ = env
    w = window(session)
    art = (Path(__file__).resolve().parent.parent / "appheader.txt").read_text(encoding="utf-8")
    assert w.lbl_logo.text() == art.strip("\n") and w.lbl_logo.text().startswith("     ██╗██╗")


# -- undo and redo --------------------------------------------------------------------------------------------------------------


def test_undo_and_redo_walk_back_and_forward_through_edits(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    tempo = w.editor.widget_for("patch_common", "patch_tempo")
    start = tempo.value()
    tempo.setValue(100)
    tempo.setValue(120)
    assert w.undo_action.isEnabled() and not w.redo_action.isEnabled()
    w.undo()
    assert w._shown[1].get("patch_common", "patch_tempo") == 100 and tempo.value() == 100 and w.redo_action.isEnabled()
    w.undo()
    assert w._shown[1].get("patch_common", "patch_tempo") == start and not w._is_dirty()
    w.redo()
    assert w._shown[1].get("patch_common", "patch_tempo") == 100
    tempo.setValue(77)  # a new edit ends the redo line
    assert not w.redo_action.isEnabled()


def test_undo_goes_to_the_unit_too_when_live(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    tempo = w.editor.widget_for("patch_common", "patch_tempo")
    start = tempo.value()
    tempo.setValue(150)
    w.worker.process_pending()
    assert ports.respond.temporary.get("patch_common", "patch_tempo") == 150
    w.undo()
    w.worker.process_pending()
    assert ports.respond.temporary.get("patch_common", "patch_tempo") == start


def test_showing_another_patch_clears_the_history(env):
    w, ports = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(99)
    w._original = w._shown[1].copy()  # (as if written): no discard prompt
    w.read_temporary()
    w.worker.process_pending()
    assert not w.undo_action.isEnabled()


def test_an_envelope_drag_is_one_undo_step(env):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    w, ports = connected(env)
    w.resize(1100, 900)
    w.show()
    w.read_temporary()
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.tabs.setCurrentIndex(1)
    graph = next(g for t, g in w.editor._graphs if t == 0 and g.NAMES[0].startswith("filter"))
    centre = graph.handle_positions()[1]
    QTest.mousePress(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre.toPoint())
    QTest.mouseMove(graph, (centre + QPointF(40, -40)).toPoint())
    QTest.mouseRelease(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, (centre + QPointF(40, -40)).toPoint())
    assert len(w._undo) == 1 and len(w._undo[0]) >= 2  # the time and the level moved together
    w.undo()
    assert not w._is_dirty()


# -- the USER list: rename, copy, swap ------------------------------------------------------------------------------------------


@pytest.fixture
def listed(writable, monkeypatch):
    """A connected window with the 128 names read and every dialog auto-answered (the test sets what they return)."""
    from jv_studio.ui import main_window as mw

    w, ports, answers, tmp_path, _ = writable
    answers["backup_first"] = QMessageBox.StandardButton.No
    w.read_names()
    w.worker.process_pending()
    return w, ports, tmp_path, mw, monkeypatch


def test_renaming_a_user_patch_updates_the_unit_and_the_list(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    monkeypatch.setattr(mw.RenameDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.RenameDialog, "name", lambda self: "Fresh Name")
    w.rename_user(5)
    w.worker.process_pending()
    assert ports.respond.user[5].name == "Fresh Name" and w.names_list.item(5).text() == "006  Fresh Name"
    assert len(list((tmp_path / "backups").glob("USER-006-*.syx"))) == 1
    assert w.stock_label.text().startswith("0 of 128")  # the list's factory comparison follows


def test_renaming_the_open_patch_reloads_it(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    w._read_user_from_item(w.names_list.item(5))
    w.worker.process_pending()
    monkeypatch.setattr(mw.RenameDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.RenameDialog, "name", lambda self: "Renamed")
    w.rename_user(5)
    w.worker.process_pending()
    assert 'USER:006: "Renamed"' in w.patch_label.text() and not w._is_dirty()


def test_a_slot_with_unsent_edits_is_not_renamed_underneath_them(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    w._read_user_from_item(w.names_list.item(5))
    w.worker.process_pending()
    w.live_check.setChecked(False)
    w.editor.widget_for("patch_common", "patch_tempo").setValue(222)
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: told.append(text) or QMessageBox.StandardButton.Ok)
    opened = []
    monkeypatch.setattr(mw.RenameDialog, "exec", lambda self: opened.append(1) or self.DialogCode.Accepted)
    w.rename_user(5)
    assert told and "edits" in told[0] and opened == [] and ports.respond.writes == []


def test_copy_and_swap_go_through_the_window(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    monkeypatch.setattr(mw.SlotDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.SlotDialog, "slot", lambda self: 9)
    w.copy_user(2)
    w.worker.process_pending()
    assert ports.respond.user[9].name == "User 003" and w.names_list.item(9).text() == "010  User 003"
    monkeypatch.setattr(mw.SlotDialog, "slot", lambda self: 11)
    w.swap_user(0)
    w.worker.process_pending()
    assert ports.respond.user[0].name == "User 012" and ports.respond.user[11].name == "User 001"
    assert w.names_list.item(0).text() == "001  User 012" and w.names_list.item(11).text() == "012  User 001"


def test_copying_a_slot_onto_itself_does_nothing(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    monkeypatch.setattr(mw.SlotDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.SlotDialog, "slot", lambda self: 4)
    w.copy_user(4)
    w.worker.process_pending()
    assert ports.respond.writes == []


def test_the_rename_dialog_limits_the_name_and_needs_one(qapp):
    from jv_studio.ui.unit_dialogs import RenameDialog

    d = RenameDialog("Old")
    d.edit.setText("A name that is far too long")
    assert len(d.name()) == 12
    d.edit.setText("   ")
    assert not d.buttons.button(d.buttons.StandardButton.Ok).isEnabled()


def test_about_credits_the_wave_names_with_a_link(qapp):
    from PySide6.QtWidgets import QLabel

    from jv_studio.ui.about_dialog import AboutDialog

    d = AboutDialog()
    texts = [label.text() for label in d.findChildren(QLabel)]
    credit = next(t for t in texts if "gumielectronic.net/?p=2312" in t)
    assert "Wave names" in credit and 'href="https://gumielectronic.net/?p=2312"' in credit
    assert next(label for label in d.findChildren(QLabel) if label.text() == credit).openExternalLinks()


def test_controls_explain_themselves_in_tooltips(env):
    w, _ = connected(env)
    w.read_temporary()
    w.worker.process_pending()
    tempo = w.editor.widget_for("patch_common", "patch_tempo").parentWidget()
    assert "tempo" in tempo.toolTip().lower() and "Range: 20 to 250" in tempo.toolTip() and "Drag to turn" in tempo.toolTip()
    cutoff = w.editor.widget_for("patch_tone", "cutoff_frequency", 0).parentWidget()
    assert "cutoff" in cutoff.toolTip().lower()
    assert w.btn_detect.toolTip() and w.btn_settings.toolTip() and w.btn_send.toolTip() and w.btn_write.toolTip()
    key_assign = w.editor.widget_for("patch_common", "key_assign_mode")
    assert "POLY" in key_assign.toolTip()
