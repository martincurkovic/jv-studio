import pytest

from fakes import FakePorts, FakeJV1010
from jv_studio.core import backup, memory, patch, sysex
from jv_studio.core.midi import MidiConnection
from jv_studio.core.unit import JV1010Unit, UnitError


class Clock:
    """Time moves only when something sleeps, so the 20 ms packet gaps cost nothing."""

    def __init__(self):
        self.t = 100.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def make(**kw):
    fake = FakeJV1010(**kw)
    ports = FakePorts(fake)
    conn = MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory)
    return fake, ports, JV1010Unit(conn, timeout=0.05, clock=(clock := Clock()).now, sleep=clock.sleep)


SMALL = [memory.SYSTEM, memory.RHYTHM]


def test_read_backup_gets_every_block_and_roundtrips_through_syx():
    fake, _, unit = make()
    got = backup.read_backup(unit, SMALL)
    assert got.is_complete(SMALL) and not got.is_complete([memory.PATCHES])
    parsed = backup.parse_backup(got.to_syx(SMALL))
    assert parsed.is_complete(SMALL)
    for block in memory.plan(SMALL):
        assert parsed.data(block) == bytes(fake.other[block.start])


def test_full_backup_includes_patches_and_patch_parse_syx_still_works():
    fake, _, unit = make()
    got = backup.read_backup(unit)
    assert got.is_complete()
    syx = got.to_syx()
    assert backup.parse_backup(syx).is_complete()
    patches = patch.parse_syx(syx)
    assert patches[patch.user_base(6)].name == "User 007"


def test_progress_and_cancel():
    _, _, unit = make()
    seen = []
    backup.read_backup(unit, [memory.SYSTEM], progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (18, 18)
    calls = iter([False, False, True])
    with pytest.raises(backup.Cancelled):
        backup.read_backup(unit, [memory.SYSTEM], cancelled=lambda: next(calls))


def test_nothing_is_sent_into_silence():
    fake, ports, unit = make(gm_mode=True)
    with pytest.raises(UnitError):
        backup.read_backup(unit, SMALL)
    assert len(ports.sent) == 2  # one block, one retry, then it stops


def test_restore_writes_changed_blocks_and_verifies():
    fake, _, unit = make()
    saved = backup.read_backup(unit, [memory.PATCHES])
    fake.user[3].name = "Spoiled"
    written = backup.restore(unit, saved, [memory.PATCHES])
    assert written == 128 * 5
    assert fake.user[3].name == "User 004"


def test_restore_splits_tones_and_spaces_packets():
    fake, ports, unit = make()
    saved = backup.read_backup(unit, [memory.PATCHES])
    fake.writes.clear()
    backup.restore(unit, saved, [memory.PATCHES])
    assert max(len(w.data) for w in fake.writes) <= 128
    assert all(len(m) <= 139 for m in ports.sent)


def test_restore_refuses_an_incomplete_backup_before_writing_anything():
    fake, _, unit = make()
    saved = backup.read_backup(unit, SMALL)
    with pytest.raises(backup.BackupError):
        backup.restore(unit, saved, [memory.PATCHES])
    assert fake.writes == []


def test_restore_writes_system_last_and_only_if_chosen():
    fake, _, unit = make()
    saved = backup.read_backup(unit, SMALL)
    fake.writes.clear()
    backup.restore(unit, saved, SMALL)
    first_system = next(i for i, w in enumerate(fake.writes) if w.address[0] == 0)
    assert all(w.address[0] == 0 for w in fake.writes[first_system:])
    fake.writes.clear()
    backup.restore(unit, saved, [memory.RHYTHM])
    assert all(w.address[0] != 0 for w in fake.writes)


def test_restore_detects_a_unit_that_does_not_store():
    fake, _, unit = make(ignore_writes=True)
    saved = backup.read_backup(unit, [memory.RHYTHM])
    # make the backup differ from the unit so the read-back must fail
    block = memory.plan([memory.RHYTHM])[0]
    saved.slots[block.start].data[0] ^= 1
    with pytest.raises(UnitError):
        backup.restore(unit, saved, [memory.RHYTHM])


def test_restore_cancel_reports_how_far_it_got():
    _, _, unit = make()
    saved = backup.read_backup(unit, SMALL)
    calls = iter([False, False, True])
    with pytest.raises(backup.Cancelled, match="after 2 of"):
        backup.restore(unit, saved, SMALL, cancelled=lambda: next(calls))


def test_parse_backup_ignores_foreign_and_unknown_messages_and_rejects_corruption():
    junk = sysex.dt1((0x7F, 0, 0, 0), b"\x01\x02")
    assert backup.parse_backup(junk).unknown_messages == 1
    bad = bytearray(sysex.dt1(patch.user_base(0), b"\x00"))
    bad[-2] ^= 1
    with pytest.raises(sysex.SysexError):
        backup.parse_backup(bytes(bad))


def test_default_backup_name():
    from datetime import datetime
    assert backup.default_backup_name(datetime(2026, 10, 13, 9, 5, 7)) == "jv1010-backup-20261013-090507.syx"
