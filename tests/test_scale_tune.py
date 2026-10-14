# Scale tune: the model and the manual's three tunings, the verified write, the worker job, and the tab in System Settings.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import backup, memory, midi, scale_tune, sysex, unit
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


# -- the model -------------------------------------------------------------------------------------------------------------


def test_addresses_are_the_manuals_17_blocks_of_12_bytes():
    assert [scale_tune.target_address(t) for t in (0, 1, 15, 16)] == [(0, 0, 0x10, 0), (0, 0, 0x11, 0), (0, 0, 0x1F, 0), (0, 0, 0x20, 0)]
    assert scale_tune.block_size() == 12 and scale_tune.TARGETS == 17 and scale_tune.target_name(16) == "Patch mode" and scale_tune.target_name(0) == "Part 1"
    with pytest.raises(ValueError):
        scale_tune.target_address(17)


def test_a_blank_set_is_equal_temperament_and_64_is_zero_cents():
    blank = scale_tune.ScaleTunes.blank()
    assert all(b == 64 for block in blank.blocks for b in block) and blank.cents(3, 5) == 0
    assert scale_tune.cents_to_raw(-64) == 0 and scale_tune.cents_to_raw(63) == 127 and scale_tune.cents_to_raw(500) == 127 and scale_tune.cents_to_raw(-500) == 0


def test_the_manuals_arabian_example_message_is_the_preset_plus_64():
    manual = bytes.fromhex("3A 6D 3E 34 0D 38 6B 3C 6F 40 36 0F".replace(" ", ""))  # F0 41 10 42 12 40 11 40 [these 12] 76 F7
    assert bytes(scale_tune.cents_to_raw(c) for c in scale_tune.PRESETS["Arabian-type Scale"]) == manual
    assert sum(scale_tune.PRESETS["Equal Temperament"]) == 0 and scale_tune.PRESETS["Just Intonation"][4] == -14 and scale_tune.PRESETS["Just Intonation"][9] == -16


def test_a_tuning_moves_to_another_tonic_by_rotation():
    just = scale_tune.PRESETS["Just Intonation"]
    on_g = scale_tune.preset_cents("Just Intonation", 7)
    assert on_g[7] == just[0] and on_g[11] == just[4] and on_g[0] == just[5] and scale_tune.preset_cents("Just Intonation", 0) == list(just)
    assert sorted(on_g) == sorted(just)


def test_the_set_round_trips_as_17_messages_and_tracks_changes():
    s = scale_tune.ScaleTunes.blank()
    s.set_block_cents(16, scale_tune.PRESETS["Just Intonation"])
    s.set(2, 4, 70)
    messages = s.to_messages()
    assert len(messages) == 17 and all(len(sysex.parse(m).data) == 12 for m in messages)
    again = scale_tune.ScaleTunes.blank()
    assert all(again.apply(sysex.parse(m)) for m in messages) and again == s
    assert s.changed_targets(scale_tune.ScaleTunes.blank()) == [2, 16] and s.changed_notes(scale_tune.ScaleTunes.blank(), 2) == [4]
    assert not again.apply(sysex.parse(sysex.dt1((0, 0, 0x10, 0), bytes(5))))  # not a whole block


# -- the unit ------------------------------------------------------------------------------------------------------------


def connection(fake):
    ports = FakePorts(fake)
    return midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory)


def test_only_the_given_blocks_are_sent_and_read_back():
    fake = FakeJV1010()
    unit_ = unit.JV1010Unit(connection(fake), timeout=0.05, sleep=lambda s: None)
    data = bytes(scale_tune.cents_to_raw(c) for c in scale_tune.PRESETS["Arabian-type Scale"])
    read = unit_.write_scale_blocks({16: data})
    assert [(w.address, w.data) for w in fake.writes] == [((0, 0, 0x20, 0), data)] and bytes(read.blocks[16]) == data and bytes(read.blocks[0]) == bytes([64] * 12)
    with pytest.raises(ValueError):
        unit_.write_scale_blocks({0: bytes(11)})
    with pytest.raises(ValueError):
        unit_.write_scale_blocks({0: bytes([200] * 12)})


def test_a_unit_that_does_not_take_a_block_is_an_error_naming_it():
    fake = FakeJV1010(ignore_writes=True)
    unit_ = unit.JV1010Unit(connection(fake), timeout=0.05, sleep=lambda s: None)
    with pytest.raises(unit.UnitError, match="scale tune of: Part 3"):
        unit_.write_scale_blocks({2: bytes([70] * 12)})


# -- the worker ----------------------------------------------------------------------------------------------------------


def worker_rig(fake=None):
    fake = fake or FakeJV1010()
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    worker = UnitWorker(session, timeout=0.05)
    seen = {"scale": [], "applied": [], "failed": []}
    worker.scale_read.connect(seen["scale"].append)
    worker.system_applied.connect(lambda path, n: seen["applied"].append((path, n)))
    worker.failed.connect(lambda label, text: seen["failed"].append((label, text)))
    return worker, fake, seen


def test_reading_the_system_settings_also_reads_the_17_scale_tunes(qapp):
    worker, fake, seen = worker_rig()
    worker.submit("system_read")
    worker.process_pending()
    assert len(seen["scale"]) == 1 and seen["scale"][0] == scale_tune.ScaleTunes.blank() and fake.writes == []
    assert len([r for r in fake.requests if r[0][:2] == (0, 0)]) == 1 + 17


def test_applying_scale_blocks_saves_the_whole_system_section_first_and_reports_what_the_unit_holds(qapp):
    worker, fake, seen = worker_rig()
    arabian = bytes(scale_tune.cents_to_raw(c) for c in scale_tune.PRESETS["Arabian-type Scale"])
    worker.submit("system_apply", [("master_tune", 70)], {0: arabian, 16: arabian})
    worker.process_pending()
    ((path, count),) = seen["applied"]
    assert count == 3 and seen["failed"] == []
    saved = backup.parse_backup(open(path, "rb").read())
    assert saved.summary()[memory.SYSTEM] == (18, 18)  # Restore Unit can read it...
    assert bytes(saved.slots[sysex.address_to_int(scale_tune.target_address(16))].data) == bytes([64] * 12)  # ...and it holds what was there BEFORE
    assert bytes(seen["scale"][-1].blocks[0]) == arabian and bytes(seen["scale"][-1].blocks[16]) == arabian and bytes(seen["scale"][-1].blocks[5]) == bytes([64] * 12)
    assert sorted(w.address for w in fake.writes) == [(0, 0, 0, 6), (0, 0, 0x10, 0), (0, 0, 0x20, 0)]


def test_a_scale_only_apply_changes_no_system_setting(qapp):
    worker, fake, seen = worker_rig()
    worker.submit("system_apply", [], {3: bytes([70] * 12)})
    worker.process_pending()
    assert [w.address for w in fake.writes] == [(0, 0, 0x13, 0)] and seen["applied"][0][1] == 1


def test_a_bad_scale_block_is_refused_before_anything_is_saved_or_written(qapp):
    worker, fake, seen = worker_rig()
    for blocks in ({17: bytes(12)}, {0: bytes(11)}, {0: bytes([128] * 12)}):
        worker.submit("system_apply", [("master_tune", 70)], blocks)
        worker.process_pending()
    assert fake.writes == [] and len(seen["failed"]) == 3 and "valid scale tune block" in seen["failed"][0][1]


# -- the tab --------------------------------------------------------------------------------------------------------------


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
    w._backed_up = True
    w.system_action.trigger()
    w.worker.process_pending()
    return w, fake, asked


def test_the_tab_shows_the_patch_mode_tuning_in_cents(win):
    w, _, _ = win
    d = w.system_dialog
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["Settings", "Scale Tune"]
    ed = d.scale_editor
    assert ed.isEnabled() and ed.target() == 16 and ed.target_combo.currentText() == "Patch mode" and ed.target_combo.count() == 17
    assert [k.text() for k in ed._knobs] == ["0"] * 12 and [k.name_label.text() for k in ed._knobs][:3] == ["C", "C#", "D"] and not d.is_dirty()


def test_typing_a_value_marks_the_target_and_the_dialog_dirty(win):
    w, fake, _ = win
    d = w.system_dialog
    d.scale_editor._knobs[4].setValue(scale_tune.cents_to_raw(-14))
    assert d.scale_dirty() and not d.settings_dirty() and d.btn_apply.isEnabled() and fake.writes == []
    assert d.scale_editor.target_combo.itemText(0) == "Patch mode  •" and "(edited)" in d.selection_label.text()
    d.revert()
    assert not d.is_dirty() and d.scale_editor._knobs[4].text() == "0" and d.scale_editor.target_combo.itemText(0) == "Patch mode"


def test_a_preset_on_a_tonic_and_copy_to_all(win):
    w, _, _ = win
    ed = w.system_dialog.scale_editor
    ed.preset_combo.setCurrentText("Just Intonation")
    ed.tonic_combo.setCurrentText("G")
    ed.btn_set.click()
    assert ed._knobs[7].text() == "0" and ed._knobs[11].text() == "-14" and ed._knobs[0].text() == "-2" and ed._knobs[8].text() == "-8"
    ed.btn_all.click()
    assert w.system_dialog._working_scale.changed_targets(w.system_dialog._original_scale) == list(range(17))
    ed.target_combo.setCurrentIndex(5)
    ed.target_combo.activated.emit(5)
    assert ed._knobs[11].text() == "-14"


def test_apply_lists_the_scale_changes_warns_when_the_switch_is_off_and_the_unit_holds_them(win):
    w, fake, asked = win
    d = w.system_dialog
    ed = d.scale_editor
    ed.preset_combo.setCurrentText("Arabian-type Scale")
    ed.btn_set.click()
    d.apply()
    title, text = asked[-1]
    assert title == "Apply to the unit?" and "Scale tune, Patch mode: C 0 → -6, C# 0 → +45, D 0 → -2, D# 0 → -12 and 7 more notes (cents)" in text
    assert "Scale Tune Switch is OFF" in text
    w.worker.process_pending()
    assert not d.is_dirty() and [w_.address for w_ in fake.writes] == [(0, 0, 0x20, 0)]
    assert d.scale_editor._knobs[4].text() == "-51" and "1 System setting(s) changed and read back" in w.statusBar().currentMessage()


def test_with_the_switch_on_there_is_no_such_warning_and_a_settings_change_goes_with_it(win):
    w, fake, asked = win
    d = w.system_dialog
    d.editor.widget_for("scale_tune_switch").setCurrentIndex(1)
    d.editor.widget_for("scale_tune_switch").activated.emit(1)
    d.scale_editor._knobs[0].setValue(scale_tune.cents_to_raw(5))
    d.apply()
    text = asked[-1][1]
    assert "Scale Tune Switch: OFF  →  ON" in text and "Scale tune, Patch mode: C 0 → +5 (cents)" in text and "is OFF" not in text
    w.worker.process_pending()
    assert sorted(w_.address for w_ in fake.writes) == [(0, 0, 0, 7), (0, 0, 0x20, 0)] and not d.is_dirty()
