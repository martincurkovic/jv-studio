# The worker thread's jobs, run synchronously with process_pending() (and once on a real thread).

import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeJV1010, FakePorts
from jv1010editor.core import midi, patch
from jv1010editor.ui.midi_session import MidiSession
from jv1010editor.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def rig(fake=None, open_ports=True):
    fake = fake or FakeJV1010("Warm Pad")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    if open_ports:
        session.open("in", "out")
    worker = UnitWorker(session, timeout=0.05)
    events = {"patch": [], "names": [], "progress": [], "failed": [], "busy": []}
    worker.patch_read.connect(lambda label, p, problems: events["patch"].append((label, p, problems)))
    worker.names_read.connect(events["names"].append)
    worker.progress.connect(lambda d, t: events["progress"].append((d, t)))
    worker.failed.connect(lambda label, msg: events["failed"].append((label, msg)))
    worker.busy_changed.connect(events["busy"].append)
    return worker, fake, events


def test_reading_the_temporary_patch_emits_it_with_no_problems(qapp):
    worker, fake, events = rig()
    worker.submit("temporary")
    worker.process_pending()
    ((label, read, problems),) = events["patch"]
    assert label == "temporary" and read.name == "Warm Pad" and problems == [] and fake.writes == []


def test_a_user_patch_is_read_from_its_slot(qapp):
    worker, fake, events = rig()
    worker.submit("user", 12)
    worker.process_pending()
    assert events["patch"][0][0] == "user:12" and events["patch"][0][1].name == "User 013"


def test_the_128_names_come_with_progress(qapp):
    worker, _, events = rig()
    worker.submit("names")
    worker.process_pending()
    assert len(events["names"][0]) == 128 and events["progress"][-1] == (128, 128)


def test_cancel_stops_a_names_read_early(qapp):
    worker, _, events = rig()
    worker.progress.connect(lambda d, t: worker.cancel() if d == 10 else None)
    worker.submit("names")
    worker.process_pending()
    assert len(events["names"][0]) == 10


def test_a_value_outside_the_table_is_reported_with_the_patch(qapp):
    fake = FakeJV1010()
    fake.temporary.common[0x0C] = 99  # EFX type max is 39
    worker, _, events = rig(fake)
    worker.submit("temporary")
    worker.process_pending()
    (_, _, problems) = events["patch"][0]
    assert [p.key for p in problems] == ["efx_type"]


def test_no_open_ports_is_a_clear_failure_not_a_crash(qapp):
    worker, _, events = rig(open_ports=False)
    worker.submit("temporary")
    worker.process_pending()
    assert events["failed"] == [("temporary", "No MIDI ports are open: choose them in Settings.")] and events["patch"] == []


def test_a_silent_unit_fails_the_job_and_the_worker_carries_on(qapp):
    worker, _, events = rig(FakeJV1010(gm_mode=True))
    worker.submit("temporary")
    worker.submit("temporary")
    worker.process_pending()
    assert [f[0] for f in events["failed"]] == ["temporary", "temporary"]  # both ran: one failure did not kill the queue


def test_an_unexpected_exception_is_caught_and_reported(qapp):
    worker, _, events = rig()
    worker.submit("nonsense")
    worker.process_pending()
    assert events["failed"] and "Unexpected error" in events["failed"][0][1]


def test_busy_changes_are_reported_once_per_batch(qapp):
    worker, _, events = rig()
    worker.submit("temporary")
    worker.submit("user", 1)
    assert not worker.is_idle()
    worker.process_pending()
    assert worker.is_idle() and events["busy"] == [True, False]


def test_a_real_thread_runs_jobs_one_at_a_time_and_stops(qapp):
    worker, _, events = rig()
    worker.start()
    worker.submit("temporary")
    worker.submit("user", 3)
    assert worker.wait_until_idle(5)
    worker.stop()
    assert worker.wait(3000)
    QApplication.processEvents()
    assert [e[0] for e in events["patch"]] == ["temporary", "user:3"]


# -- writing, backing up, restoring --------------------------------------------------------------------------------------------


def extra_events(worker):
    events = {"backup": [], "restore": [], "written": [], "cancelled": []}
    worker.backup_done.connect(lambda path, size: events["backup"].append((path, size)))
    worker.restore_done.connect(events["restore"].append)
    worker.write_done.connect(lambda *a: events["written"].append(a))
    worker.cancelled.connect(lambda *a: events["cancelled"].append(a))
    return events


def test_send_temporary_writes_and_verifies(qapp):
    worker, fake, events = rig()
    more = extra_events(worker)
    new = patch.Patch.minimum()
    new.name = "Sent"
    worker.submit("send_temporary", new)
    worker.process_pending()
    assert more["written"] == [("temporary", "Sent", "")] and fake.temporary.name == "Sent" and not events["failed"]


def test_a_unit_that_stores_nothing_fails_the_send(qapp):
    worker, fake, events = rig(FakeJV1010(ignore_writes=True))
    new = patch.Patch.minimum()
    new.name = "Lost"
    worker.submit("send_temporary", new)
    worker.process_pending()
    assert events["failed"] and "read-back" in events["failed"][0][1]


def test_write_user_saves_the_old_patch_first(qapp, tmp_path, monkeypatch):
    from jv1010editor.core import app_config

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    worker, fake, events = rig()
    more = extra_events(worker)
    new = patch.Patch.minimum()
    new.name = "Replacement"
    worker.submit("write_user", 6, new)
    worker.process_pending()
    ((label, name, path),) = more["written"]
    assert label == "user:6" and name == "Replacement" and fake.user[6].name == "Replacement"
    old = patch.parse_syx(open(path, "rb").read())[patch.user_base(6)]
    assert old.name == "User 007"  # the backup holds what was there before
    assert path.startswith(str(tmp_path / "backups"))


def test_write_user_writes_nothing_if_the_backup_cannot_be_saved(qapp, tmp_path, monkeypatch):
    from jv1010editor.core import app_config, backup

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker, fake, events = rig()
    worker.submit("write_user", 6, patch.Patch.minimum())
    worker.process_pending()
    assert events["failed"] and "nothing was written" in events["failed"][0][1] and fake.writes == []


def test_write_user_writes_nothing_if_the_old_patch_cannot_be_read(qapp, tmp_path, monkeypatch):
    from jv1010editor.core import app_config

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    worker, fake, events = rig(FakeJV1010(gm_mode=True))
    worker.submit("write_user", 6, patch.Patch.minimum())
    worker.process_pending()
    assert events["failed"] and fake.writes == []


def test_backup_then_restore_roundtrip_through_a_file(qapp, tmp_path):
    from jv1010editor.core import backup, memory

    worker, fake, events = rig()
    more = extra_events(worker)
    path = tmp_path / "unit.syx"
    worker.submit("backup", path, [memory.RHYTHM])
    worker.process_pending()
    assert more["backup"] == [(str(path), path.stat().st_size)]
    key = memory.plan([memory.RHYTHM])[3].start
    original = bytes(fake.other[key])
    fake.other[key][0] ^= 1
    worker.submit("restore", backup.parse_backup(path.read_bytes()), [memory.RHYTHM])
    worker.process_pending()
    assert more["restore"] == [130] and bytes(fake.other[key]) == original


def test_cancelling_a_backup_saves_nothing_and_is_not_an_error(qapp, tmp_path):
    from jv1010editor.core import memory

    worker, _, events = rig()
    more = extra_events(worker)
    worker.progress.connect(lambda d, t: worker.cancel() if d == 3 else None)
    path = tmp_path / "unit.syx"
    worker.submit("backup", path, [memory.PATCHES])
    worker.process_pending()
    assert more["cancelled"] and not path.exists() and not events["failed"] and not more["backup"]


def test_restoring_an_incomplete_backup_fails_before_writing(qapp, tmp_path):
    from jv1010editor.core import backup, memory

    worker, fake, events = rig()
    worker.submit("restore", backup.Backup(), [memory.PATCHES])
    worker.process_pending()
    assert events["failed"] and "missing" in events["failed"][0][1] and fake.writes == []
