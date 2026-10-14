# The System settings: the model, the display of its values, the card layout, the verified write path, and the window.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, backup, friendly, groups, hints, memory, midi, params, sysex, system, unit, validate
from jv_studio.ui.knob_control import origin_value, parse_display_text
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def table():
    return params.load_table().block(system.COMMON)


# -- the model -------------------------------------------------------------------------------------------------------------


def test_the_block_is_one_dt1_and_round_trips_through_syx():
    s = system.System.minimum()
    s.set("master_tune", 70)
    s.set("patch_receive_channel", 4)
    messages = s.to_messages()
    assert len(messages) == 1 and sysex.parse(messages[0]).address == system.BASE and len(sysex.parse(messages[0]).data) == 102
    again = system.System.blank()
    assert all(again.apply(sysex.parse(m)) for m in sysex.split_messages(s.to_syx())) and again == s
    assert sysex.parse(system.System.request()).size == 102


def test_set_clamps_and_changes_lists_what_differs_in_table_order():
    a = system.System.minimum()
    b = a.copy()
    assert system.changes(a, b) == []
    assert b.set("master_tune", 999) == 126
    b.set("efx_switch", 1)
    assert system.changes(a, b) == [("master_tune", 0, 126), ("efx_switch", 0, 1)]
    assert a != b and b.copy() == b


def test_the_selection_is_described_the_way_a_person_says_it():
    s = system.System.minimum()
    s.set("sound_mode", system.PATCH_MODE)
    s.set("patch_group_type", 0)
    s.set("patch_group_id", 1)
    s.set("patch_number", 4)
    assert s.selection_text() == "Patch mode: USER 005" and s.selection_text(["a", "b", "c", "d", "Fifth"]) == "Patch mode: USER 005  Fifth"
    s.set("sound_mode", system.PERFORMANCE_MODE)
    s.set("performance_number", 66)
    assert s.selection_text() == "Performance mode: PR-A 03"
    s.set("sound_mode", system.GM_MODE)
    assert s.selection_text() == "GM mode"
    assert [system.describe_performance(n) for n in (0, 31, 64, 127)] == ["USER 01", "USER 32", "PR-A 01", "PR-B 32"]


# -- showing values ----------------------------------------------------------------------------------------------------------


def test_master_tune_is_shown_in_hertz_and_can_be_typed():
    p = table().param("master_tune")
    assert [params.format_value(p, v) for v in (0, 63, 126)] == ["427.4 Hz", "440.0 Hz", "452.6 Hz"]
    assert parse_display_text(p, "440") == 63 and parse_display_text(p, "440.0 Hz") == 63 and parse_display_text(p, "441.2") == 69 and parse_display_text(p, "500") is None
    assert origin_value(p) == 63


def test_preview_velocity_zero_is_off_and_a_channel_is_one_based():
    t = table()
    assert params.format_value(t.param("preview_velocity_set_1"), 0) == "OFF" and params.format_value(t.param("preview_velocity_set_1"), 90) == "90"
    assert params.format_value(t.param("patch_receive_channel"), 0) == "1" and params.format_value(t.param("control_channel"), 16) == "OFF"


# -- the cards --------------------------------------------------------------------------------------------------------------


def test_every_shown_system_parameter_has_a_card_and_only_the_jv1010s_are_shown():
    cards = groups.groups(system.COMMON)
    assert groups.OTHER not in [t for t, _ in cards]
    shown = {p.key for _, members in cards for p in members}
    assert shown == {p.key for p in table().param_list() if groups.supported(p) and (system.COMMON, p.key) not in groups.HIDDEN}
    assert {"sound_mode", "master_tune", "patch_receive_channel", "receive_program_change", "efx_switch", "system_tempo", "preview_sound_mode"} <= shown
    # the JV-1080 family's (angle brackets in the manual, including a footnote's whole list) and the current-selection numbers are not controls
    assert not shown & {"arpeggio_style", "arpeggio_part_number", "pedal_1_assign", "c1_assign", "keyboard_sens", "transpose_switch", "receive_control_change", "bank_select_group1_msb"}
    assert not shown & {"performance_number", "patch_group_type", "patch_group_id", "patch_number", "arpeggio_octave_range"}


def test_every_shown_system_choice_has_a_readable_distinct_name_and_most_have_a_hint():
    for _, members in groups.groups(system.COMMON):
        for param in members:
            if param.has_choices():
                names = [friendly.label(param.key, text) for text in param.choice_labels()]
                assert len(set(names)) == len(names), param.key
    assert friendly.label("sound_mode", "GM") == "General MIDI" and friendly.label("clock_source", "INT") == "Internal"
    assert friendly.label("aftertouch_source", "CH&POLY") == "Channel & Polyphonic" and friendly.label("hold_control_source", "HOLD-1") == "Hold-1"
    shown = [p.key for _, members in groups.groups(system.COMMON) for p in members]
    assert not [k for k in shown if not hints.hint(system.COMMON, k)]
    assert all(h.endswith(".") and len(h) <= 200 and "\n" not in h for h in hints.SYSTEM.values()) and all(k in table() for k in hints.SYSTEM)


def test_a_value_outside_the_range_is_reported_but_the_jv1080s_parameters_are_not():
    s = system.System.minimum()
    assert validate.out_of_range_system(s) == []
    s.common[table().param("master_tune").offset] = 127
    s.common[table().param("arpeggio_style").offset] = 120  # a JV-1080 parameter the unit may hold anything in
    assert [p.key for p in validate.out_of_range_system(s)] == ["master_tune"]


# -- writing -----------------------------------------------------------------------------------------------------------------


def connection(fake):
    ports = FakePorts(fake)
    return midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory), ports


def test_only_the_changed_parameters_are_sent_and_read_back():
    fake = FakeJV1010()
    conn, ports = connection(fake)
    unit_ = unit.JV1010Unit(conn, timeout=0.05, sleep=lambda s: None)
    read = unit_.write_system_params([("master_tune", 70), ("efx_switch", 0)])
    assert [(w.address, w.data) for w in fake.writes] == [((0, 0, 0, 6), bytes([70])), ((0, 0, 0, 8), bytes([0]))]
    assert read.get("master_tune") == 70 and unit_.read_system().get("master_tune") == 70


def test_a_unit_that_does_not_take_a_value_is_an_error():
    fake = FakeJV1010(ignore_writes=True)
    conn, _ = connection(fake)
    unit_ = unit.JV1010Unit(conn, timeout=0.05, sleep=lambda s: None)
    with pytest.raises(unit.UnitError, match="did not take: Master Tune"):
        unit_.write_system_params([("master_tune", 99)])


def worker_rig(fake=None):
    fake = fake or FakeJV1010()
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    worker = UnitWorker(session, timeout=0.05)
    seen = {"read": [], "applied": [], "failed": []}
    worker.system_read.connect(lambda s, problems: seen["read"].append((s, problems)))
    worker.system_applied.connect(lambda path, n: seen["applied"].append((path, n)))
    worker.failed.connect(lambda label, text: seen["failed"].append((label, text)))
    return worker, fake, seen


def test_the_worker_reads_the_system_settings(qapp):
    worker, fake, seen = worker_rig()
    worker.submit("system_read")
    worker.process_pending()
    ((read, problems),) = seen["read"]
    assert read.get("sound_mode") == 1 and read.get("patch_receive_channel") == 0 and fake.writes == []


def test_applying_saves_the_old_block_first_then_writes_only_the_changes_and_reports_what_the_unit_holds(qapp):
    worker, fake, seen = worker_rig()
    before = worker.process_pending() or None
    worker.submit("system_read")
    worker.process_pending()
    old = seen["read"][0][0]
    worker.submit("system_apply", [("master_tune", 70), ("receive_bank_select", 0)])
    worker.process_pending()
    ((path, count),) = seen["applied"]
    assert count == 2 and seen["failed"] == []
    raw = open(path, "rb").read()  # a normal backup of the whole System section (the common block + 17 scale tunes), holding what was there BEFORE: Restore Unit can read it
    assert path.endswith(".syx") and "SYSTEM-" in path and backup.parse_backup(raw).summary()[memory.SYSTEM] == (18, 18)
    assert sysex.parse(sysex.split_messages(raw)[0]).data == bytes(old.common)
    assert len(fake.writes) == 2 and seen["read"][-1][0].get("master_tune") == 70 and seen["read"][-1][0].get("receive_bank_select") == 0


def test_nothing_is_written_when_the_backup_cannot_be_saved(qapp, monkeypatch):
    worker, fake, seen = worker_rig()
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker.submit("system_apply", [("master_tune", 70)])
    worker.process_pending()
    assert fake.writes == [] and "nothing was written" in seen["failed"][0][1] and seen["applied"] == []


def test_gm_mode_unknown_keys_and_the_jv1080s_parameters_are_refused(qapp):
    worker, fake, seen = worker_rig()
    for change in ([("sound_mode", 2)], [("no_such", 1)], [("arpeggio_style", 3)], [("patch_number", 5)], [("master_tune", 70), ("sound_mode", 2)]):
        worker.submit("system_apply", change)
        worker.process_pending()
    assert fake.writes == [] and len(seen["failed"]) == 5 and "GM mode" in seen["failed"][0][1] and "not a System setting" in seen["failed"][1][1]


def test_a_unit_that_ignores_the_write_is_reported(qapp):
    worker, fake, seen = worker_rig(FakeJV1010(ignore_writes=True))
    worker.submit("system_apply", [("master_tune", 70)])
    worker.process_pending()
    assert "did not take" in seen["failed"][0][1] and seen["applied"] == []


# -- the window ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def win(qapp, monkeypatch):
    fake = FakeJV1010("Init Patch")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    asked = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda parent, title, text, *a: asked.append((title, text)) or QMessageBox.StandardButton.Yes)
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    w._backed_up = True  # (the "back up first?" question is the window's, tested elsewhere)
    return w, fake, asked


def open_dialog(w):
    w.system_action.trigger()
    w.worker.process_pending()
    return w.system_dialog


def test_opening_system_settings_reads_and_shows_what_the_unit_is_doing(win):
    w, fake, _ = win
    d = open_dialog(w)
    assert d.has_shown() and d.selection_label.text() == "The unit is in Patch mode: USER 001" and not d.is_dirty()
    assert d.editor.widget_for("patch_receive_channel").text() == "1" and fake.writes == []
    assert not d.btn_apply.isEnabled() and d.btn_read.isEnabled()


def test_gm_mode_is_not_offered_for_the_sound_mode(win):
    w, _, _ = win
    combo = open_dialog(w).editor.widget_for("sound_mode")
    assert [combo.itemText(i) for i in range(combo.count())] == ["Performance", "Patch"]


def test_an_edit_marks_it_dirty_and_nothing_is_sent_until_apply(win):
    w, fake, _ = win
    d = open_dialog(w)
    d.editor.widget_for("master_tune").setValue(70)
    assert d.is_dirty() and "(edited)" in d.selection_label.text() and d.btn_apply.isEnabled() and fake.writes == []
    d.revert()
    assert not d.is_dirty() and d.editor.widget_for("master_tune").value() == 63 and not d.btn_apply.isEnabled()


def test_apply_lists_the_changes_asks_and_then_the_unit_holds_them(win):
    w, fake, asked = win
    d = open_dialog(w)
    d.editor.widget_for("master_tune").setValue(70)
    combo = d.editor.widget_for("receive_program_change")
    combo.setCurrentIndex(combo.findData(0))
    combo.activated.emit(combo.currentIndex())
    d.apply()
    title, text = asked[-1]
    assert title == "Apply to the unit?" and "Master Tune: 440.0 Hz  →  441.4 Hz" in text and "Receive Program Change: ON  →  OFF" in text
    assert "retunes the whole unit" in text and "saved to a file first" in text
    w.worker.process_pending()
    assert not d.is_dirty() and [(x.address, x.data) for x in fake.writes] == [((0, 0, 0, 6), bytes([70])), ((0, 0, 0, 20), bytes([0]))]
    assert "2 System setting(s) changed and read back" in w.statusBar().currentMessage()
    assert list(app_config.backups_dir().glob("SYSTEM-*.syx"))


def test_declining_the_confirmation_sends_nothing(win, monkeypatch):
    w, fake, asked = win
    d = open_dialog(w)
    d.editor.widget_for("master_tune").setValue(70)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    d.apply()
    assert w.worker.is_idle() and fake.writes == [] and d.is_dirty()


def test_the_buttons_follow_the_connection_and_the_menu_item_exists(win):
    w, _, _ = win
    d = open_dialog(w)
    d.editor.widget_for("master_tune").setValue(70)
    w.session.close()
    w._refresh_connection()
    assert not d.btn_read.isEnabled() and not d.btn_apply.isEnabled() and d.btn_revert.isEnabled()
    assert "System Settings..." in [a.text() for a in w.menuBar().actions()[2].menu().actions()]
