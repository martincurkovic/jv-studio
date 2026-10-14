import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, backup, midi, params, rhythm, sysex, unit, validate
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


class Clock:
    def __init__(self):
        self.t = 100.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def connect(fake=None):
    fake = fake or FakeJV1010()
    ports = FakePorts(fake)
    conn = midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory)
    clock = Clock()
    return unit.JV1010Unit(conn, timeout=0.05, clock=clock.now, sleep=clock.sleep), fake, clock


def test_a_minimum_rhythm_set_is_valid_and_named():
    r = rhythm.RhythmSet.minimum()
    assert r.name == "INIT RHYTHM" and validate.out_of_range_rhythm(r) == []
    assert len(r.common) == 12 and sorted(r.notes) == list(range(35, 99)) and all(len(n) == 58 for n in r.notes.values())


def test_values_of_the_common_block_and_a_key():
    r = rhythm.RhythmSet.minimum()
    r.set(rhythm.NOTE, "tone_level", 99, key=38)
    r.name = "My Kit"
    assert r.get(rhythm.NOTE, "tone_level", key=38) == 99 and r.get(rhythm.NOTE, "tone_level", key=39) == 0 and r.name == "My Kit"
    with pytest.raises(ValueError):
        r.get(rhythm.NOTE, "tone_level")


def test_addresses_follow_the_manual():
    assert rhythm.user_base(0) == (0x10, 0x40, 0, 0) and rhythm.user_base(1) == (0x10, 0x41, 0, 0) and rhythm.TEMPORARY_BASE == (0x02, 0x09, 0, 0)
    assert sysex.add_to_address(rhythm.user_base(0), rhythm.note_offset(35)) == (0x10, 0x40, 0x23, 0)  # the THIRD address byte is the key number
    assert sysex.add_to_address(rhythm.user_base(1), rhythm.note_offset(98)) == (0x10, 0x41, 0x62, 0)
    with pytest.raises(ValueError):
        rhythm.note_offset(34)
    with pytest.raises(ValueError):
        rhythm.user_base(2)


def test_a_set_is_65_messages_that_round_trip_through_syx():
    r = rhythm.RhythmSet.minimum()
    r.set(rhythm.NOTE, "wave_number", 200, key=60)
    r.set(rhythm.NOTE, "coarse_tune", 70, key=98)
    messages = r.to_messages(rhythm.user_base(1))
    assert len(messages) == 65 and all(len(m) <= 140 for m in messages)
    assert [m[5:9] for m in r.requests(rhythm.user_base(1))][:2] == [bytes((0x10, 0x41, 0, 0)), bytes((0x10, 0x41, 0x23, 0))]
    found = rhythm.parse_syx(r.to_syx(rhythm.user_base(1)))
    assert list(found) == [rhythm.user_base(1)] and found[rhythm.user_base(1)] == r
    assert rhythm.parse_syx(r.to_syx(rhythm.TEMPORARY_BASE))[rhythm.TEMPORARY_BASE] == r
    assert rhythm.parse_syx(sysex.dt1((0x10, 0x00, 0, 0), b"\x20" * 12)) == {}  # a USER performance is not a rhythm set


def test_copy_and_swap_keys():
    r = rhythm.RhythmSet.minimum()
    r.set(rhythm.NOTE, "tone_level", 90, key=36)
    r.set(rhythm.NOTE, "tone_level", 40, key=38)
    r.copy_note(36, 40)
    assert r.get(rhythm.NOTE, "tone_level", key=40) == 90 and r.get(rhythm.NOTE, "tone_level", key=36) == 90
    r.swap_notes(36, 38)
    assert r.get(rhythm.NOTE, "tone_level", key=36) == 40 and r.get(rhythm.NOTE, "tone_level", key=38) == 90


def test_reading_a_set_and_the_two_names():
    u, fake, _ = connect()
    fake.user_rhythms[1].set(rhythm.NOTE, "tone_level", 77, key=50)
    assert u.read_user_rhythm_names() == ["Rhythm 1", "Rhythm 2"]
    got = u.read_user_rhythm(1)
    assert got == fake.user_rhythms[1] and got.get(rhythm.NOTE, "tone_level", key=50) == 77
    assert u.read_temporary_rhythm().name == "Temp Rhythm"
    assert len(fake.requests) == 2 + 65 + 65 and fake.writes == []


def test_writing_a_set_is_read_back_and_a_unit_that_stores_nothing_fails():
    u, fake, clock = connect()
    new = rhythm.RhythmSet.minimum()
    new.name = "Written"
    new.set(rhythm.NOTE, "wave_number", 123, key=44)
    u.write_rhythm(rhythm.user_base(0), new)
    assert fake.user_rhythms[0] == new and len(fake.writes) == 65
    u2, fake2, _ = connect(FakeJV1010(ignore_writes=True))
    with pytest.raises(unit.UnitError, match="read-back"):
        u2.write_rhythm(rhythm.user_base(0), new)


def test_one_parameter_goes_to_its_key_and_is_verified():
    u, fake, _ = connect()
    assert u.write_rhythm_param(rhythm.TEMPORARY_BASE, rhythm.NOTE, "tone_level", 88, note=40, verify=True) == 88
    assert fake.temp_rhythm.get(rhythm.NOTE, "tone_level", key=40) == 88 and fake.temp_rhythm.get(rhythm.NOTE, "tone_level", key=41) == 0
    (write,) = fake.writes
    assert write.address == (0x02, 0x09, 40, params.load_table().block(rhythm.NOTE).param("tone_level").offset) and write.data == bytes([88])
    u.write_rhythm_param(rhythm.TEMPORARY_BASE, rhythm.COMMON, "rhythm_name", "Renamed", verify=True)
    assert fake.temp_rhythm.name == "Renamed"
    with pytest.raises(ValueError):
        u.write_rhythm_param(rhythm.TEMPORARY_BASE, rhythm.NOTE, "tone_level", 1)
    u2, fake2, _ = connect(FakeJV1010(ignore_writes=True))
    with pytest.raises(unit.UnitError):
        u2.write_rhythm_param(rhythm.TEMPORARY_BASE, rhythm.NOTE, "tone_level", 88, note=40, verify=True)


def test_a_backup_of_the_rhythm_section_holds_both_sets_and_restore_puts_them_back():
    u, fake, _ = connect()
    from jv_studio.core import memory

    saved = backup.read_backup(u, [memory.RHYTHM])
    assert saved.is_complete([memory.RHYTHM])
    original = rhythm.RhythmSet(bytearray(fake.user_rhythms[0].common), {k: bytearray(v) for k, v in fake.user_rhythms[0].notes.items()})
    fake.user_rhythms[0].set(rhythm.NOTE, "tone_level", 5, key=60)
    backup.restore(u, saved, [memory.RHYTHM])
    assert fake.user_rhythms[0] == original


# -- the worker --------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def rig(fake=None):
    fake = fake or FakeJV1010()
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    worker = UnitWorker(session, timeout=0.05)
    seen = {"read": [], "names": [], "written": [], "failed": [], "param": []}
    worker.rhythm_read.connect(lambda label, r, problems: seen["read"].append((label, r, problems)))
    worker.rhythm_names_read.connect(seen["names"].append)
    worker.write_done.connect(lambda *a: seen["written"].append(a))
    worker.failed.connect(lambda label, message: seen["failed"].append((label, message)))
    worker.param_written.connect(lambda *a: seen["param"].append(a))
    return worker, fake, seen


def test_the_worker_reads_rhythm_sets_and_names(qapp):
    worker, fake, seen = rig()
    worker.submit("rhythm_temporary")
    worker.submit("rhythm_user", 1)
    worker.submit("rhythm_names")
    worker.process_pending()
    assert [(label, r.name, problems) for label, r, problems in seen["read"]] == [("temporary", "Temp Rhythm", []), ("user:1", "Rhythm 2", [])]
    assert seen["names"] == [["Rhythm 1", "Rhythm 2"]] and not seen["failed"]


def test_a_value_outside_the_table_is_reported_with_the_set(qapp):
    fake = FakeJV1010()
    fake.temp_rhythm.notes[60][params.load_table().block(rhythm.NOTE).param("tone_level").offset] = 0x7F  # 127 is in range; make one that is not
    fake.temp_rhythm.notes[60][params.load_table().block(rhythm.NOTE).param("wave_group_type").offset] = 9  # 0-2
    worker, _, seen = rig(fake)
    worker.submit("rhythm_temporary")
    worker.process_pending()
    ((_, _, problems),) = seen["read"]
    assert len(problems) == 1 and "key 60" in str(problems[0])


def test_live_edit_and_send_go_to_the_temporary_rhythm_set_only(qapp):
    worker, fake, seen = rig()
    worker.submit("rhythm_write_param", rhythm.NOTE, "tone_pan", 40, 20)  # block, key, note, value
    worker.process_pending()
    assert seen["param"] == [(rhythm.NOTE, "tone_pan", 40, 20)] and fake.temp_rhythm.get(rhythm.NOTE, "tone_pan", key=40) == 20
    assert all(w.address[:2] == (0x02, 0x09) for w in fake.writes) and fake.user_rhythms[0].get(rhythm.NOTE, "tone_pan", key=40) == 0
    new = rhythm.RhythmSet.minimum()
    new.name = "Sent"
    worker.submit("rhythm_send_temporary", new)
    worker.process_pending()
    assert seen["written"] == [("rhythm:temporary", "Sent", "")] and fake.temp_rhythm == new and not seen["failed"]


def test_write_user_saves_the_old_set_first(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    worker, fake, seen = rig()
    new = rhythm.RhythmSet.minimum()
    new.name = "Replacement"
    worker.submit("rhythm_write_user", 1, new)
    worker.process_pending()
    ((label, name, path),) = seen["written"]
    assert label == "rhythm:1" and name == "Replacement" and fake.user_rhythms[1] == new and fake.user_rhythms[0].name == "Rhythm 1"
    assert path.startswith(str(tmp_path / "backups")) and "RHYTHM-2-" in path
    assert rhythm.parse_syx(open(path, "rb").read())[rhythm.user_base(1)].name == "Rhythm 2"  # the backup holds what was there before


def test_write_user_writes_nothing_if_the_backup_cannot_be_saved(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker, fake, seen = rig()
    worker.submit("rhythm_write_user", 0, rhythm.RhythmSet.minimum())
    worker.process_pending()
    assert fake.writes == [] and fake.user_rhythms[0].name == "Rhythm 1" and "nothing was written" in seen["failed"][0][1]


def test_a_unit_that_stores_nothing_fails_the_write_user(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    worker, fake, seen = rig(FakeJV1010(ignore_writes=True))
    worker.submit("rhythm_write_user", 0, rhythm.RhythmSet.minimum())
    worker.process_pending()
    assert seen["failed"] and "read-back" in seen["failed"][0][1] and not seen["written"]
