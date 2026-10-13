# The firmware update in the app: the dialog's checks, the worker job, and the window's menu item and safeguards (made-up files; the output is a fake port).

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from firmware_files import FakeClock, write_set
from fakes import FakePorts
from jv_studio.core import firmware, midi
from jv_studio.ui import main_window
from jv_studio.ui.firmware_dialog import FirmwareDialog
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folder(tmp_path):
    return write_set(tmp_path / "fw")


def tick_all(dialog):
    for box in dialog.checks:
        box.setChecked(True)


def test_start_needs_a_good_folder_and_every_box_ticked(qapp, folder):
    dialog = FirmwareDialog()
    assert not dialog.start_button.isEnabled() and dialog.firmware() is None
    tick_all(dialog)
    assert not dialog.start_button.isEnabled()  # boxes alone are not enough
    dialog.load_folder(folder)
    assert dialog.start_button.isEnabled() and dialog.firmware().ok
    dialog.checks[0].setChecked(False)
    assert not dialog.start_button.isEnabled()


def test_files_that_fail_verification_can_never_be_started(qapp, tmp_path):
    dialog = FirmwareDialog(folder=write_set(tmp_path / "bad", corrupt=2))
    tick_all(dialog)
    assert not dialog.start_button.isEnabled() and "can't be played" in dialog.summary.text()
    assert any("adds up to checksum" in dialog.findings.item(i).text() for i in range(dialog.findings.count()))


def test_the_dialog_says_it_is_unverified_and_what_it_found(qapp, folder):
    dialog = FirmwareDialog(folder=folder)
    assert "UNVERIFIED" in dialog.findChild(type(dialog.summary), "warningLabel").text()
    assert "3 files" in dialog.summary.text() and "Not a release this app knows" in dialog.summary.text()
    assert any(item.text().startswith("Warning:") for item in map(dialog.findings.item, range(dialog.findings.count())))


# -- the worker --------------------------------------------------------------------------------------------------------


def rig(monkeypatch):
    ports = FakePorts()  # a sink: nothing answers
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    clock = FakeClock()
    real_play = firmware.play
    monkeypatch.setattr(firmware, "play", lambda *a, **k: real_play(*a, sleep=clock.sleep, clock=clock.clock, **k))  # no real waiting
    return ports, session, UnitWorker(session, timeout=0.05)


def test_the_worker_plays_the_set_and_reports_it(qapp, folder, monkeypatch):
    ports, session, worker = rig(monkeypatch)
    update = firmware.load(folder)
    done, status, progress = [], [], []
    worker.firmware_done.connect(lambda b, m: done.append((b, m)))
    worker.firmware_status.connect(status.append)
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.submit("firmware", update)
    worker.process_pending()
    assert done == [(3, 882)] and len(ports.sent) == 882 and len(status) == 3 and progress[-1][0] == progress[-1][1]


def test_the_worker_cancels_and_reports_how_far_it_got(qapp, folder, monkeypatch):
    ports, session, worker = rig(monkeypatch)
    cancelled, done = [], []
    worker.cancelled.connect(lambda label, text: cancelled.append((label, text)))
    worker.firmware_done.connect(lambda *a: done.append(a))
    worker.progress.connect(lambda d, t: worker.cancel() if d > 100 else None)
    worker.submit("firmware", firmware.load(folder))
    worker.process_pending()
    assert not done and cancelled[0][0] == "firmware" and "play the update again from the first block" in cancelled[0][1] and 0 < len(ports.sent) < 882


def test_the_worker_refuses_a_failed_set_and_a_closed_port(qapp, tmp_path, folder, monkeypatch):
    ports, session, worker = rig(monkeypatch)
    failed = []
    worker.failed.connect(lambda label, text: failed.append((label, text)))
    worker.submit("firmware", firmware.load(write_set(tmp_path / "bad", corrupt=2)))
    worker.process_pending()
    assert ports.sent == [] and "did not pass verification" in failed[0][1]
    session.close()
    worker.submit("firmware", firmware.load(folder))
    worker.process_pending()
    assert "No MIDI ports are open" in failed[1][1]


# -- the window --------------------------------------------------------------------------------------------------------


class StubDialog:
    DialogCode = FirmwareDialog.DialogCode
    chosen = None

    def __init__(self, parent=None):
        pass

    def exec(self):
        return self.DialogCode.Accepted

    def firmware(self):
        return StubDialog.chosen


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    ports, session, worker = rig(monkeypatch)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append((title, text)) or QMessageBox.StandardButton.Ok)
    w = MainWindow(session, worker=worker, start_worker=False)
    return w, ports, messages


def test_the_menu_item_needs_open_ports_and_is_off_in_demo(qapp, monkeypatch):
    session = MidiSession(lambda i, o: None)
    w = MainWindow(session, worker=UnitWorker(session), start_worker=False)
    assert not w.firmware_action.isEnabled() and "unverified" in w.firmware_action.text()


def test_updating_through_the_window_sends_the_files_and_explains_what_next(win, folder, monkeypatch):
    w, ports, messages = win
    assert w.firmware_action.isEnabled()
    StubDialog.chosen = firmware.load(folder)
    monkeypatch.setattr(main_window, "FirmwareDialog", StubDialog)
    w.update_firmware()
    assert w._firmware_running
    w.worker.process_pending()
    assert not w._firmware_running and len(ports.sent) == 882
    assert messages[-1][0] == "Firmware sent" and "can't tell whether it was accepted" in messages[-1][1] and "Factory Reset" in messages[-1][1]


def test_a_dialog_that_returns_nothing_sends_nothing(win, monkeypatch):
    w, ports, _ = win
    StubDialog.chosen = None
    monkeypatch.setattr(main_window, "FirmwareDialog", StubDialog)
    w.update_firmware()
    assert not w._firmware_running and w.worker.is_idle() and ports.sent == []


def test_quitting_or_cancelling_mid_update_asks_first_and_defaults_to_no(win, monkeypatch):
    w, ports, _ = win
    asked = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, buttons, default: asked.append((title, default)) or QMessageBox.StandardButton.No)
    w._firmware_running = True
    event = QCloseEvent()
    w.closeEvent(event)
    assert not event.isAccepted() and asked[-1] == ("Firmware update running", QMessageBox.StandardButton.No)
    w._cancel_job()
    assert asked[-1][0] == "Stop the firmware update?" and w.worker._cancel is False  # (answered No: the update goes on)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.StandardButton.Yes)
    w._cancel_job()
    assert w.worker._cancel is True
    w._firmware_running = False  # (or closing the window at the end of the test session would ask)
