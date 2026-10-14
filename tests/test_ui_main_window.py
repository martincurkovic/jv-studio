# The main window: restoring the saved ports, the connection card, and the hardware check.

import pytest
from PySide6.QtCore import Qt
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
    assert session.is_open and w.connection_label.isHidden() and w.btn_detect.isEnabled()  # the ports are not printed in the window


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
    assert titles == ["&File", "&Edit", "&Hardware", "&View", "&Help"]


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
    assert w.patch_label.text() == 'Temporary patch · Init Patch' and w.problems_label.isHidden() and w.problems_label.text() == ""
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
    assert w.patch_label.text() == 'USER:005 · User 005'
    assert not w.names_progress.isVisible() and not w.btn_cancel.isVisible()


def test_opening_the_ports_reads_everything_needed_to_start_editing(env):
    ports, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session, autoload=True)
    w.worker.process_pending()  # the four reads run one after another
    assert w.patch_label.text() == 'Temporary patch · Init Patch' and w._temp_synced
    assert w.names_list.count() == 128 and w.perf_list.count() == 32
    assert w.performance_panel.label.text().startswith("Temporary performance") and ports.respond.writes == []
    assert not w._autoload_steps and not w._long_job


def test_the_auto_load_runs_once_per_set_of_ports_and_never_over_edits(env):
    ports, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session, autoload=True)
    w.worker.process_pending()
    w._shown[1].name = "Mine"  # an edit the user has not stored
    w._maybe_autoload()  # same ports (a diagnostic closed and reopened them): nothing is read again
    assert w.worker.is_idle()
    w._autoload_ports = None  # new ports: the names are read again, the edited patch is left alone
    w._maybe_autoload()
    w.worker.process_pending()
    assert w._shown[1].name == "Mine" and w.names_list.count() == 128


def test_the_auto_load_stops_at_the_first_failure(env):
    ports, session, _ = env
    ports.respond.gm_mode = True  # a unit that answers nothing
    app_config.save_ports("JV In", "JV Out")
    w = window(session, autoload=True)
    w.worker.process_pending()
    assert not w._autoload_steps and w.names_list.count() == 0 and w.worker.is_idle()
    assert "at startup" in w.statusBar().currentMessage()  # a status line, not a dialog (a dialog would have blocked this test)


def test_without_the_switch_nothing_is_read_at_startup(env):
    _, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session)
    assert w.worker.is_idle() and w.names_list.count() == 0


def test_the_patch_list_has_a_fixed_width_matching_the_mode_switch(env):
    w, _ = connected(env)
    w.show()
    assert w.library.minimumWidth() == w.library.maximumWidth() == w.mode_tabs.sizeHint().width() + 21


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
    assert "1 differ" in w.statusBar().currentMessage()
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
    assert ports.respond.writes == []  # (not on the temporary patch: nothing is sent live)
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


def test_the_logo_is_top_left_and_is_the_embedded_art(env):
    from jv_studio.ui.ascii_logo import LOGO

    _, session, _ = env
    w = window(session)
    assert w.lbl_logo.text() == LOGO.strip("\n") and w.lbl_logo.text().startswith("     ██╗██╗")  # the owner's art, unchanged


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
    assert "factory patch here" in w.names_list.item(5).toolTip()  # the list's factory comparison follows


def test_renaming_the_open_patch_reloads_it(listed):
    w, ports, tmp_path, mw, monkeypatch = listed
    w._read_user_from_item(w.names_list.item(5))
    w.worker.process_pending()
    monkeypatch.setattr(mw.RenameDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(mw.RenameDialog, "name", lambda self: "Renamed")
    w.rename_user(5)
    w.worker.process_pending()
    assert 'USER:006 · Renamed' in w.patch_label.text() and not w._is_dirty()


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
    tempo = w.editor.widget_for("patch_common", "patch_tempo")
    assert "tempo" in tempo.toolTip().lower() and "Range: 20 to 250" in tempo.toolTip() and "Drag to turn" in tempo.toolTip()
    cutoff = w.editor.widget_for("patch_tone", "cutoff_frequency", 0)
    assert "cutoff" in cutoff.toolTip().lower()
    assert w.btn_detect.toolTip() and w.btn_settings.toolTip() and w.btn_send.toolTip() and w.btn_write.toolTip()
    key_assign = w.editor.widget_for("patch_common", "key_assign_mode")
    assert "POLY" in key_assign.toolTip()


def test_the_window_has_no_stray_labels_or_size_grip(env):
    w, _ = connected(env)
    assert not hasattr(w, "stock_label") and w.connection_label.isHidden()
    assert not w.statusBar().isSizeGripEnabled()
    margins = w.statusBar().contentsMargins()
    assert margins.left() >= 10 and margins.right() >= 10  # clear of the window's rounded corners


# -- the Performances mode ---------------------------------------------------------------------------------------------------


def perf_mode(env):
    w, ports = connected(env)
    w.mode_tabs.setCurrentIndex(1)
    return w, ports


def test_the_mode_tabs_swap_the_list_the_editor_and_the_menu_wording(env):
    w, _ = connected(env)
    assert not w._performance_mode() and w.library_header.text() == "USER Patches" and w.open_action.text() == "Open Patch .syx..."
    w.mode_tabs.setCurrentIndex(1)
    assert w._performance_mode() and w.list_stack.currentWidget() is w.perf_list and w.right_stack.currentWidget() is w.performance_panel
    assert w.library_header.text() == "USER Performances" and w.btn_read_names.text() == "Read Performance Names"
    assert w.open_action.text() == "Open Performance .syx..." and w.read_action.text() == "Read Temporary Performance" and w.send_action.text() == "Send to Temporary Performance"
    w.mode_tabs.setCurrentIndex(0)
    assert w.list_stack.currentWidget() is w.names_list and w.save_action.text() == "Save Patch as .syx..."


def test_reading_the_temporary_performance_fills_the_editor(env):
    w, ports = perf_mode(env)
    ports.respond.temp_performance.name = "Live Rig"
    ports.respond.temp_performance.set("performance_part", "part_level", 99, part=3)
    w.read_temporary()  # routed to the performance panel
    w.worker.process_pending()
    panel = w.performance_panel
    assert panel.label.text() == 'Temporary performance · Live Rig' and panel.problems_label.isHidden()
    assert panel.editor.widget_for("performance_part", "part_level", part=3, grid=True).value() == 99
    assert w.patch_label.text().startswith("No patch open")  # the patch side was not touched
    assert ports.respond.writes == []


def test_the_performance_names_list_and_opening_one(env):
    w, ports = perf_mode(env)
    w.read_names()
    w.worker.process_pending()
    assert w.perf_list.count() == 32 and w.perf_list.item(4).text() == "05  Perf 05" and "32 USER performance names" in w.statusBar().currentMessage()
    w._open_perf_from_item(w.perf_list.item(4))
    w.worker.process_pending()
    assert w.performance_panel.label.text() == 'USER performance 05 · Perf 05' and w.names_list.count() == 0


def test_live_edits_reach_the_temporary_performance_only_when_it_is_the_one_shown(env):
    w, ports = perf_mode(env)
    w.read_temporary()
    w.worker.process_pending()
    panel = w.performance_panel
    panel.editor.widget_for("performance_part", "part_level", part=5, grid=True).setValue(88)
    w.worker.process_pending()
    assert ports.respond.temp_performance.get("performance_part", "part_level", part=5) == 88 and panel.is_dirty() and "(edited)" in panel.label.text()
    ports.respond.writes.clear()
    panel.revert_edits()  # (the edit above is on the unit already; reverting only changes what is shown)
    w._open_perf_from_item(type("I", (), {"data": lambda self, role: 6})())
    panel.live_check.setChecked(True)
    w.worker.process_pending()
    panel.editor.widget_for("performance_common", "performance_tempo").setValue(140)
    w.worker.process_pending()
    assert ports.respond.writes == []  # a USER performance: edits stay local until sent
    w.send_temporary()
    w.worker.process_pending()
    assert ports.respond.temp_performance.get("performance_common", "performance_tempo") == 140 and panel._temp_synced


def test_performance_undo_redo_and_revert_follow_the_mode(env):
    w, ports = perf_mode(env)
    w.read_temporary()
    w.worker.process_pending()
    panel = w.performance_panel
    panel.live_check.setChecked(False)
    level = panel.editor.widget_for("performance_part", "part_level", part=2, grid=True)
    level.setValue(50)
    level.setValue(70)
    assert w.undo_action.isEnabled() and w.revert_action.isEnabled()
    w.undo()
    assert panel._shown[1].get("performance_part", "part_level", part=2) == 50
    w.undo()
    assert not panel.is_dirty() and w.redo_action.isEnabled()
    w.redo()
    assert panel._shown[1].get("performance_part", "part_level", part=2) == 50
    w.revert_edits()
    assert not panel.is_dirty() and not w.undo_action.isEnabled()
    w.mode_tabs.setCurrentIndex(0)
    assert not w.undo_action.isEnabled()  # the patch side has its own (empty) history


def test_reading_another_performance_over_edits_asks_first(env, monkeypatch):
    w, ports = perf_mode(env)
    w.read_temporary()
    w.worker.process_pending()
    panel = w.performance_panel
    panel.live_check.setChecked(False)
    panel.editor.widget_for("performance_common", "performance_tempo").setValue(99)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No)
    w.read_temporary()
    w.worker.process_pending()
    assert asked and panel.editor.widget_for("performance_common", "performance_tempo").value() == 99


def test_a_unit_that_does_not_take_a_live_performance_edit_switches_it_off_once(env, monkeypatch):
    w, ports = perf_mode(env)
    w.read_temporary()
    w.worker.process_pending()
    ports.respond.ignore_writes = True
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append(text) or QMessageBox.StandardButton.Ok)
    panel = w.performance_panel
    panel.editor.widget_for("performance_common", "performance_tempo").setValue(120)
    panel.editor.widget_for("performance_common", "performance_tempo").setValue(121)
    w.worker.process_pending()
    assert len(warnings) == 1 and not panel.live_check.isChecked() and "Live sending is off" in warnings[0]


def test_writing_a_user_performance_backs_up_the_old_one(writable, monkeypatch):

    w, ports, answers, tmp_path, _ = writable
    w.mode_tabs.setCurrentIndex(1)
    w.read_temporary()
    w.worker.process_pending()
    w.read_names()
    w.worker.process_pending()
    panel = w.performance_panel
    panel.live_check.setChecked(False)
    panel.editor.widget_for("performance_common", "performance_name").setText("Mine")
    panel.editor.widget_for("performance_common", "performance_name").editingFinished.emit()
    from jv_studio.ui import performance_panel as pp

    monkeypatch.setattr(pp.SlotDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(pp.SlotDialog, "slot", lambda self: 3)
    w.write_user()
    w.worker.process_pending()
    assert ports.respond.user_performances[3].name == "Mine" and not panel.is_dirty() and w.perf_list.item(3).text() == "04  Mine"
    assert len(list((tmp_path / "backups").glob("PERF-04-*.syx"))) == 1 and not w._is_dirty()  # (and no patch was written)
    assert w.names_list.count() == 0


def test_a_performance_write_does_not_look_like_a_patch_write(writable, monkeypatch):
    w, ports, answers, tmp_path, _ = writable
    w.read_temporary()  # a patch, in patch mode
    w.worker.process_pending()
    w.mode_tabs.setCurrentIndex(1)
    w.read_temporary()
    w.worker.process_pending()
    w.performance_panel.send_temporary()
    w.worker.process_pending()
    assert w.patch_label.text().startswith('Temporary patch') and "(edited)" not in w.patch_label.text()
    assert "temporary performance" in w.statusBar().currentMessage()


def test_opening_and_saving_a_performance_file(env, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from jv_studio.core import performance

    w, ports = perf_mode(env)
    p = performance.Performance.minimum()
    p.name = "From File"
    path = tmp_path / "perf.syx"
    path.write_bytes(p.to_syx(performance.user_base(11)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    w.open_syx()
    panel = w.performance_panel
    assert "From File" in panel.label.text() and "USER performance 12" in panel.label.text() and w.save_action.isEnabled()
    out = tmp_path / "out.syx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    w.save_shown_patch()
    assert performance.parse_syx(out.read_bytes())[performance.user_base(11)] == p
    assert ports.respond.writes == []


def test_a_patch_file_is_not_a_performance(env, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from jv_studio.core import patch

    w, _ = perf_mode(env)
    path = tmp_path / "patch.syx"
    path.write_bytes(patch.Patch.minimum().to_syx(patch.user_base(0)))
    told = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: told.append(text) or QMessageBox.StandardButton.Ok)
    w.open_syx()
    assert told == ["That file holds no JV-1010 performance."]


def test_user_patch_names_read_in_patch_mode_name_the_parts_in_performance_mode(env):
    w, ports = connected(env)
    ports.respond.user[4].name = "Viola"
    w.read_names()
    w.worker.process_pending()
    w.mode_tabs.setCurrentIndex(1)
    ports.respond.temp_performance.set("performance_part", "patch_group_id", 1, part=0)
    ports.respond.temp_performance.set("performance_part", "patch_number", 4, part=0)
    w.read_temporary()
    w.worker.process_pending()
    assert w.performance_panel.editor._grid_patch[0].text() == "USER 005  Viola"


def test_the_raw_values_tab_shows_the_performance(env):
    w, _ = perf_mode(env)
    panel = w.performance_panel
    w.read_temporary()
    w.worker.process_pending()
    panel.editor.tabs.setCurrentWidget(panel.tree)
    assert panel.tree.topLevelItemCount() == 17 and panel.tree.topLevelItem(0).text(0) == "Common" and panel.tree.topLevelItem(1).text(0) == "Part 1"


def test_the_about_logo_uses_the_same_font_as_the_main_window_and_fits(env):
    from PySide6.QtWidgets import QLabel

    from jv_studio.ui.about_dialog import AboutDialog
    from jv_studio.ui.ascii_logo import logo_font

    _, session, _ = env
    w = window(session)
    d = AboutDialog()
    logo = next(label for label in d.findChildren(QLabel) if label.text().startswith("     ██╗"))
    assert logo.font().family() == w.lbl_logo.font().family() == logo_font().family() == "Menlo" and logo_font().pointSize() == 8  # (the size is set once, in logo_font)
    assert d.minimumWidth() >= logo.sizeHint().width()
    assert logo.alignment() & Qt.AlignmentFlag.AlignLeft and not logo.alignment() & Qt.AlignmentFlag.AlignHCenter  # centred, every line would shift on its own


def test_the_mode_switch_is_a_segmented_control(env):
    from jv_studio.ui.segmented import SegmentedControl

    _, session, _ = env
    w = window(session)
    assert isinstance(w.mode_tabs, SegmentedControl) and w.mode_tabs.currentIndex() == 0
    seen = []
    w.mode_tabs.currentChanged.connect(seen.append)
    w.mode_tabs._buttons[1].click()
    assert w.mode_tabs.currentIndex() == 1 and seen == [1] and w._performance_mode()
    w.mode_tabs.setCurrentIndex(0)
    assert w.mode_tabs.currentIndex() == 0 and seen == [1, 0] and not w._performance_mode()
    assert [b.property("segment") for b in w.mode_tabs._buttons] == ["first", "middle", "last"]


def test_the_list_starts_as_wide_as_the_mode_switch_and_the_live_checkbox_is_short(env):
    w, _ports = connected(env)
    w.show()
    QApplication.processEvents()
    assert abs(w.names_list.width() - w.mode_tabs.width()) <= 4  # the list's right edge lines up with the switch's
    assert w.live_check.text() == "Live edits" and not hasattr(w, "edit_hint")
    assert abs(w.live_check.geometry().center().y() - w.btn_revert.geometry().center().y()) <= 4 and w.live_check.x() > w.btn_revert.x()  # on the button row, right of Revert Edits
    assert w.performance_panel.live_check.text() == "Live edits" and not hasattr(w.performance_panel, "hint")


# -- refreshing after the unit was changed from its front panel -----------------------------------------------------------------


def loaded(env):
    ports, session, _ = env
    app_config.save_ports("JV In", "JV Out")
    w = window(session, autoload=True)
    w.worker.process_pending()
    return w, ports


def test_refresh_all_catches_up_with_changes_made_on_the_unit(env):
    w, ports = loaded(env)
    assert w.patch_label.text() == "Temporary patch · Init Patch" and w.names_list.item(2).text() == "003  User 003"
    fake = ports.respond
    fake.temporary.name = "Panel Edit"
    fake.user[2].name = "On The Unit"
    fake.user_performances[1].name = "Perf Renamed"
    fake.temp_rhythm.name = "Kit Edit"
    fake.user_rhythms[0].name = "Kit Stored"
    assert w.refresh_action.shortcut().toString() == "Ctrl+Shift+R" and w.refresh_action.isEnabled()
    w.refresh_all()
    w.worker.process_pending()
    assert w.patch_label.text() == "Temporary patch · Panel Edit" and w.names_list.item(2).text() == "003  On The Unit"
    assert w.perf_list.item(1).text() == "02  Perf Renamed" and w.rhythm_list.item(0).text() == "1  Kit Stored"
    assert w.rhythm_panel.label.text() == "Temporary rhythm set · Kit Edit" and w._temp_synced and fake.writes == []  # reads only


def test_refresh_all_keeps_unsent_edits_unless_told_to_discard_them(env, monkeypatch):
    w, ports = loaded(env)
    w.editor.widget_for("patch_common", "patch_name").setText("Mine")
    w.editor.widget_for("patch_common", "patch_name").editingFinished.emit()
    w.worker.process_pending()
    ports.respond.temporary.name = "Panel Edit"
    ports.respond.user[0].name = "On The Unit"
    answers = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers.append(a[2]) or QMessageBox.StandardButton.No)
    w.refresh_all()
    w.worker.process_pending()
    assert "patch you are editing" in answers[0] and w._shown[1].name == "Mine" and w.names_list.item(0).text() == "001  On The Unit"  # the edit stays, the names refresh
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.refresh_all()
    w.worker.process_pending()
    assert w._shown[1].name == "Panel Edit" and not w._is_dirty() and not w._autoload_force


def test_refresh_all_needs_open_ports_and_an_idle_worker(env):
    _, session, _ = env
    w = window(session, autoload=True)
    assert not w.refresh_action.isEnabled()
    w.refresh_all()
    assert w.worker.is_idle()  # nothing was queued without ports
