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
