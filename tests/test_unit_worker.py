# The worker thread's jobs, run synchronously with process_pending() (and once on a real thread).

import pytest
from PySide6.QtWidgets import QApplication

from fakes import FakeJV1010, FakePorts
from jv_studio.core import midi, patch
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


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
    from jv_studio.core import app_config

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
    from jv_studio.core import app_config, backup

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker, fake, events = rig()
    worker.submit("write_user", 6, patch.Patch.minimum())
    worker.process_pending()
    assert events["failed"] and "nothing was written" in events["failed"][0][1] and fake.writes == []


def test_write_user_writes_nothing_if_the_old_patch_cannot_be_read(qapp, tmp_path, monkeypatch):
    from jv_studio.core import app_config

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")
    worker, fake, events = rig(FakeJV1010(gm_mode=True))
    worker.submit("write_user", 6, patch.Patch.minimum())
    worker.process_pending()
    assert events["failed"] and fake.writes == []


def test_backup_then_restore_roundtrip_through_a_file(qapp, tmp_path):
    from jv_studio.core import backup, memory

    worker, fake, events = rig()
    more = extra_events(worker)
    path = tmp_path / "unit.syx"
    worker.submit("backup", path, [memory.RHYTHM])
    worker.process_pending()
    assert more["backup"] == [(str(path), path.stat().st_size)]
    key = memory.plan([memory.RHYTHM])[3].start
    original = bytes(fake.block_data(key))
    fake.block_data(key)[0] ^= 1
    worker.submit("restore", backup.parse_backup(path.read_bytes()), [memory.RHYTHM])
    worker.process_pending()
    assert more["restore"] == [130] and bytes(fake.block_data(key)) == original


def test_cancelling_a_backup_saves_nothing_and_is_not_an_error(qapp, tmp_path):
    from jv_studio.core import memory

    worker, _, events = rig()
    more = extra_events(worker)
    worker.progress.connect(lambda d, t: worker.cancel() if d == 3 else None)
    path = tmp_path / "unit.syx"
    worker.submit("backup", path, [memory.PATCHES])
    worker.process_pending()
    assert more["cancelled"] and not path.exists() and not events["failed"] and not more["backup"]


def test_restoring_an_incomplete_backup_fails_before_writing(qapp, tmp_path):
    from jv_studio.core import backup, memory

    worker, fake, events = rig()
    worker.submit("restore", backup.Backup(), [memory.PATCHES])
    worker.process_pending()
    assert events["failed"] and "missing" in events["failed"][0][1] and fake.writes == []


def _backups_to(tmp_path, monkeypatch):
    from jv_studio.core import app_config

    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "config.json")


def test_renaming_a_user_patch_changes_only_its_name_and_backs_it_up(qapp, tmp_path, monkeypatch):
    _backups_to(tmp_path, monkeypatch)
    worker, fake, events = rig()
    more = extra_events(worker)
    fake.user[4].set(patch.COMMON, "patch_tempo", 143)
    before = fake.user[4].copy()
    worker.submit("rename_user", 4, "Brand New")
    worker.process_pending()
    after = fake.user[4]
    assert after.name == "Brand New" and after.get(patch.COMMON, "patch_tempo") == 143
    assert after.tones == before.tones and more["written"][0][:2] == ("user:4", "Brand New")
    assert patch.parse_syx(open(more["written"][0][2], "rb").read())[patch.user_base(4)].name == "User 005"


def test_copy_user_duplicates_one_slot_over_another_after_backing_up_the_target(qapp, tmp_path, monkeypatch):
    _backups_to(tmp_path, monkeypatch)
    worker, fake, events = rig()
    more = extra_events(worker)
    worker.submit("copy_user", 2, 9)
    worker.process_pending()
    assert fake.user[9] == fake.user[2] and fake.user[9].name == "User 003"
    assert patch.parse_syx(open(more["written"][0][2], "rb").read())[patch.user_base(9)].name == "User 010"  # the overwritten one is on disk


def test_swap_user_exchanges_two_slots_and_backs_up_both_first(qapp, tmp_path, monkeypatch):
    _backups_to(tmp_path, monkeypatch)
    worker, fake, events = rig()
    more = extra_events(worker)
    worker.submit("swap_user", 1, 6)
    worker.process_pending()
    assert fake.user[1].name == "User 007" and fake.user[6].name == "User 002"
    assert len(more["written"]) == 2 and len(list((tmp_path / "backups").glob("USER-*.syx"))) == 2


def test_a_swap_with_a_failing_backup_writes_nothing(qapp, tmp_path, monkeypatch):
    from jv_studio.core import backup

    _backups_to(tmp_path, monkeypatch)
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker, fake, events = rig()
    worker.submit("swap_user", 1, 6)
    worker.process_pending()
    assert events["failed"] and fake.writes == []


def test_swapping_a_slot_with_itself_is_refused(qapp, tmp_path, monkeypatch):
    _backups_to(tmp_path, monkeypatch)
    worker, fake, events = rig()
    worker.submit("swap_user", 3, 3)
    worker.process_pending()
    assert events["failed"] and fake.writes == []


# -- performances ----------------------------------------------------------------------------------------------------------------


def perf_events(worker):
    events = {"read": [], "names": []}
    worker.performance_read.connect(lambda label, p, problems: events["read"].append((label, p, problems)))
    worker.performance_names_read.connect(events["names"].append)
    return events


def test_reading_performances_and_their_names(qapp):

    worker, fake, events = rig()
    got = perf_events(worker)
    worker.submit("perf_temporary")
    worker.submit("perf_user", 4)
    worker.submit("perf_names")
    worker.process_pending()
    assert [(label, p.name, problems) for label, p, problems in got["read"]] == [("temporary", "Temp Perf", []), ("user:4", "Perf 05", [])]
    assert len(got["names"][0]) == 32 and fake.writes == []


def test_a_performance_value_outside_the_table_is_reported(qapp):
    from jv_studio.core import params, performance

    fake = FakeJV1010()
    fake.temp_performance.parts[2][params.load_table().block(performance.PART).param("midi_channel").offset] = 99
    worker, _, _ = rig(fake)
    got = perf_events(worker)
    worker.submit("perf_temporary")
    worker.process_pending()
    ((_, _, problems),) = got["read"]
    assert [(p.tone, p.key) for p in problems] == [(2, "midi_channel")]


def test_a_live_performance_edit_is_verified(qapp):
    from jv_studio.core import performance

    worker, fake, events = rig()
    written = []
    worker.param_written.connect(lambda *a: written.append(a))
    worker.submit("perf_write_param", performance.PART, "part_level", 5, 88)
    worker.submit("perf_write_param", performance.COMMON, "performance_tempo", None, 140)
    worker.process_pending()
    assert written == [(performance.PART, "part_level", 5, 88), (performance.COMMON, "performance_tempo", -1, 140)]
    assert fake.temp_performance.get(performance.PART, "part_level", part=5) == 88 and fake.temp_performance.get(performance.COMMON, "performance_tempo") == 140


def test_sending_a_performance_and_writing_a_user_one_with_a_backup(qapp, tmp_path, monkeypatch):
    from jv_studio.core import performance

    _backups_to(tmp_path, monkeypatch)
    worker, fake, events = rig()
    more = extra_events(worker)
    new = performance.Performance.minimum()
    new.name = "Fresh"
    worker.submit("perf_send_temporary", new)
    worker.submit("perf_write_user", 9, new)
    worker.process_pending()
    assert fake.temp_performance == new and fake.user_performances[9] == new
    assert [w[:2] for w in more["written"]] == [("perf:temporary", "Fresh"), ("perf:9", "Fresh")]
    backups = list((tmp_path / "backups").glob("PERF-10-*.syx"))
    assert len(backups) == 1 and performance.parse_syx(backups[0].read_bytes())[performance.user_base(9)].name == "Perf 10"


def test_a_performance_write_with_a_failing_backup_writes_nothing(qapp, tmp_path, monkeypatch):
    from jv_studio.core import backup, performance

    _backups_to(tmp_path, monkeypatch)
    monkeypatch.setattr(backup, "write_file", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    worker, fake, events = rig()
    worker.submit("perf_write_user", 3, performance.Performance.minimum())
    worker.process_pending()
    assert events["failed"] and "nothing was written" in events["failed"][0][1] and fake.writes == []
