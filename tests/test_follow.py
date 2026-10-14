# The audition bar and the editor follow each other: a patch chosen in the bar is read into the editor, and a USER patch opened in the editor is selected on the unit.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import audition, midi, params, patch
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
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
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: (_ for _ in ()).throw(AssertionError("a dialog was shown: " + str(a[2]))))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    return w, fake


def settle(w):
    """Let the 350 ms wait after a choice pass, then run what the window queued."""
    w._audition_timer.stop()
    w._after_audition_choice()
    w.worker.process_pending()


def temp_reads(fake):
    return [r for r in fake.requests if r[0][0] == 3]


# -- the simulated unit follows Bank Select + Program Change like the real one ------------------------------------------------------


def test_the_simulated_unit_loads_a_chosen_patch_into_its_temporary_patch_only_when_the_real_one_would():
    unit = FakeJV1010()
    unit.user[7].name = "Seventh"
    for message in audition.patch_select(0, "USER", 7):
        unit(message)
    assert unit.temporary.name == "Seventh"
    for message in audition.patch_select(0, "PR-A", 1):
        unit(message)
    assert unit.temporary.name == "Bright Piano"  # a preset: named from the manual's list
    info = audition.parse_system_common(bytes(unit.other[0]))
    assert (info.group_type, info.group_id, info.patch_number) == (0, 3, 1)  # the System block's selection follows
    for message in audition.patch_select(5, "USER", 2):  # another channel than the Patch Receive Channel
        unit(message)
    assert unit.temporary.name == "Bright Piano"
    table = params.load_table().block("system_common")
    params.write(unit.other[0], table.param("receive_program_change"), 0)
    for message in audition.patch_select(0, "USER", 2):
        unit(message)
    assert unit.temporary.name == "Bright Piano"  # Receive Program Change OFF
    params.write(unit.other[0], table.param("receive_program_change"), 1)
    params.write(unit.other[0], table.param("sound_mode"), 0)
    for message in audition.patch_select(0, "USER", 2):
        unit(message)
    assert unit.temporary.name == "Bright Piano"  # Performance mode: the part would change, not the patch


# -- a patch chosen in the bar is read into the editor ---------------------------------------------------------------------------


def test_a_patch_chosen_in_the_bar_is_read_into_the_editor_after_the_last_choice(win):
    w, fake = win
    fake.user[5].name = "Sixth"
    w.audition.choose("USER", 5)
    assert w._audition_timer.isActive() and w._shown is None and temp_reads(fake) == []  # nothing is read until the choices stop
    settle(w)
    assert w._shown[0] == "temporary" and w.patch_label.text() == "Temporary patch · Sixth" and w._temp_synced and not w._is_dirty()
    assert fake.writes == [] and len(temp_reads(fake)) == 5  # one read of the five blocks, nothing written


def test_scrubbing_through_patches_reads_only_where_it_stops(win):
    w, fake = win
    for number in range(10, 18):
        w.audition.choose("USER", number)
    settle(w)
    assert w.patch_label.text() == "Temporary patch · User 018" and len(temp_reads(fake)) == 5


def test_unsent_edits_are_never_replaced_by_a_patch_chosen_in_the_bar(win):
    w, fake = win
    w.read_temporary()
    w.worker.process_pending()
    box = w.editor.widget_for("patch_common", "patch_name")
    box.setText("Mine")
    box.editingFinished.emit()
    w.worker.process_pending()
    reads = len(temp_reads(fake))
    w.audition.choose("USER", 3)
    settle(w)
    assert w._shown[1].name == "Mine" and w._is_dirty() and not w._temp_synced and len(temp_reads(fake)) == reads
    assert "unsent edits stay in the editor" in w.statusBar().currentMessage()
    w.read_temporary()  # asks (No by default): the edits are kept
    assert w._shown[1].name == "Mine"


def test_in_performance_or_gm_mode_a_choice_in_the_bar_loads_nothing(win):
    w, fake = win
    w._sound_mode = 0
    w.audition.choose("USER", 3)
    settle(w)
    assert w._shown is None and "not in Patch mode" in w.statusBar().currentMessage() and temp_reads(fake) == []
    w._sound_mode = 2
    w.audition.choose("USER", 4)
    settle(w)
    assert w._shown is None and temp_reads(fake) == []


def test_a_follow_read_that_fails_is_a_status_line_not_a_dialog(win):
    w, fake = win
    fake.gm_mode = True  # the unit ignores data requests
    w.audition.choose("USER", 3)
    settle(w)  # (the fixture makes QMessageBox.warning raise: a dialog would fail this test)
    assert "Couldn't read the patch the unit now plays" in w.statusBar().currentMessage() and w._shown is None


def test_a_choice_made_while_a_job_runs_waits_for_it(win):
    w, fake = win
    w.audition.choose("USER", 2)
    w.worker.submit("names")  # busy
    w._audition_timer.stop()
    w._after_audition_choice()
    assert w._audition_timer.isActive() and temp_reads(fake) == []  # tried again later, not lost
    w._audition_timer.stop()
    w.worker.process_pending()
    settle(w)
    assert w._shown is not None and w.patch_label.text().endswith("User 003")


# -- a USER patch opened in the editor is selected on the unit ------------------------------------------------------------------


def double_click(w, number):
    w._read_user_from_item(type("I", (), {"data": lambda self, role: number})())
    w.worker.process_pending()


def test_opening_a_user_patch_selects_it_on_the_unit_and_live_edits_start_at_once(win):
    w, fake = win
    double_click(w, 4)
    assert w._shown[0] == "user:4" and w.patch_label.text() == "USER:005 · User 005"
    assert fake.channel_messages[-3:] == audition.patch_select(0, "USER", 4) and fake.writes == []  # a plain MIDI choice: nothing was written
    assert w.audition.bank_combo.currentData() == "USER" and w.audition.patch_combo.currentIndex() == 4  # the bar shows it too
    assert not w._temp_synced  # (not yet: the unit has to be asked what it holds)
    settle(w)
    assert w._temp_synced and "playing on the unit" in w.statusBar().currentMessage() and w._shown[0] == "user:4"  # still USER:005 in the editor, not "temporary"
    w.editor.widget_for("patch_common", "patch_level").setValue(77)  # no "Send to Temporary Patch" first
    w.worker.process_pending()
    assert fake.temporary.get("patch_common", "patch_level") == 77 and fake.user[4].get("patch_common", "patch_level") != 77  # the temporary patch, never the stored one


def test_if_the_unit_does_not_follow_the_editor_says_so_and_does_not_send_edits_live(win):
    w, fake = win
    params.write(fake.other[0], params.load_table().block("system_common").param("receive_program_change"), 0)
    double_click(w, 9)
    settle(w)
    assert not w._temp_synced and "not playing it" in w.statusBar().currentMessage() and "Send to Temporary Patch" in w.statusBar().currentMessage()
    before = list(fake.writes)
    w.editor.widget_for("patch_common", "patch_level").setValue(66)
    w.worker.process_pending()
    assert fake.writes == before  # an edit is not sent to a patch the unit is not playing


def test_in_performance_mode_opening_a_patch_sends_no_program_change(win):
    w, fake = win
    w._sound_mode = 0
    double_click(w, 4)
    assert w._shown[0] == "user:4" and fake.channel_messages == [] and not w._temp_synced


def test_opening_something_else_before_the_check_arrives_forgets_the_check(win):
    w, fake = win
    double_click(w, 4)
    double_click(w, 8)  # a second double-click while the first check is waiting
    settle(w)
    assert w._shown[0] == "user:8" and w._temp_synced and w._pending_check is None


def test_a_check_for_a_patch_that_changed_meanwhile_does_not_claim_sync(win):
    w, fake = win
    double_click(w, 4)
    box = w.editor.widget_for("patch_common", "patch_name")
    box.setText("Edited Fast")
    box.editingFinished.emit()
    settle(w)
    assert not w._temp_synced and w._shown[1].name == "Edited Fast"  # (the unit holds the stored one, the editor an edited one)
