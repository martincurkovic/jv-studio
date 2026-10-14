import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import midi, sysex, universal
from jv_studio.ui.audition_bar import AuditionBar
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_messages_are_the_ones_in_the_manual():
    assert universal.GM_SYSTEM_ON == bytes.fromhex("F0 7E 7F 09 01 F7") and universal.GM_SYSTEM_OFF == bytes.fromhex("F0 7E 7F 09 02 F7")
    assert universal.master_volume(100) == bytes.fromhex("F0 7F 7F 04 01 00 64 F7") and universal.master_volume(0)[6] == 0 and universal.master_volume(127)[6] == 127
    for bad in (-1, 128):
        with pytest.raises(ValueError):
            universal.master_volume(bad)


def test_every_message_is_valid_midi_sysex_and_is_told_apart():
    for message in (universal.GM_SYSTEM_ON, universal.GM_SYSTEM_OFF, universal.master_volume(64)):
        assert message[0] == 0xF0 and message[-1] == 0xF7 and all(b < 0x80 for b in message[1:-1])
    assert universal.classify(universal.GM_SYSTEM_ON) == "gm_on" and universal.classify(universal.GM_SYSTEM_OFF) == "gm_off"
    assert universal.classify(universal.master_volume(77)) == ("master_volume", 77)
    assert universal.classify(sysex.IDENTITY_REQUEST) is None and universal.classify(bytes.fromhex("F0 7F 7F 04 01 00 90 F7")) is None
    assert sysex.parse(universal.GM_SYSTEM_ON) is None  # (valid sysex the Roland parser does not handle: it is not a DT1/RQ1)


def test_the_simulated_unit_goes_into_gm_mode_and_ignores_data_requests_until_it_is_taken_out():
    unit = FakeJV1010()
    request = sysex.rq1((3, 0, 0, 0), 74)
    assert unit(request)
    unit(universal.master_volume(90))
    assert unit.master_volume == 90
    unit(universal.GM_SYSTEM_ON)
    assert unit.gm_mode and unit(request) == [] and unit(sysex.IDENTITY_REQUEST)  # (it still answers the identity request)
    unit(universal.master_volume(10))
    assert unit.master_volume == 90  # not received in GM mode
    unit(universal.GM_SYSTEM_OFF)
    assert not unit.gm_mode and unit(request) and unit.universal_messages == [("master_volume", 90), "gm_on", ("master_volume", 10), "gm_off"]


# -- the master slider ----------------------------------------------------------------------------------------------------


def test_the_master_slider_starts_at_full_and_sends_when_let_go(qapp):
    bar = AuditionBar()
    sent = []
    bar.master_volume_changed.connect(sent.append)
    assert bar.master.value() == 127 and bar.master_label.text() == "127"
    bar.master.setValue(80)  # a key or wheel step: at once
    assert sent == [80] and bar.master_label.text() == "80"
    bar.master.setSliderDown(True)  # a drag: the number follows, nothing is sent until the release
    bar.master.setValue(60)
    bar.master.setValue(50)
    assert sent == [80] and bar.master_label.text() == "50"
    bar.master.setSliderDown(False)  # (letting go emits sliderReleased once)
    assert sent == [80, 50]


# -- the window --------------------------------------------------------------------------------------------------------------


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out"])
    fake = FakeJV1010("Init Patch")
    ports = FakePorts(fake)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open("in", "out")
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    return w, fake


def test_the_master_slider_reaches_the_unit(win):
    w, fake = win
    w.audition.master.setValue(70)
    assert fake.master_volume == 70 and "Master volume 70" in w.statusBar().currentMessage() and fake.writes == []


def test_gm_system_on_asks_first_then_the_unit_stops_answering_and_gm_off_brings_it_back(win, monkeypatch):
    w, fake = win
    w._temp_synced = w.performance_panel._temp_synced = w.rhythm_panel._temp_synced = True
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[1]) or QMessageBox.StandardButton.No)
    w.gm_system_on()
    assert asked == ["GM System On"] and not fake.gm_mode and fake.universal_messages == []  # declined: nothing sent
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w.gm_system_on()
    assert fake.gm_mode and fake.universal_messages == ["gm_on"] and "GM mode" in w.statusBar().currentMessage()
    assert not w._temp_synced and not w.performance_panel._temp_synced and not w.rhythm_panel._temp_synced  # nothing the editors hold is on the unit now
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append(text) or QMessageBox.StandardButton.Ok)
    w.read_temporary()
    w.worker.process_pending()
    assert w._shown is None and "GM mode" in warnings[0]  # the read failed with the GM explanation, nothing crashed
    w.gm_system_off()
    assert not fake.gm_mode and fake.universal_messages == ["gm_on", "gm_off"]
    w.read_temporary()
    w.worker.process_pending()
    assert w._shown is not None


def test_the_gm_actions_need_open_ports_and_an_idle_worker_and_never_run_during_a_firmware_update(win, monkeypatch):
    w, fake = win
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert w.gm_on_action.isEnabled() and w.gm_off_action.isEnabled() and w.gm_on_action.text() == "GM System On..."
    w.worker.submit("temporary")  # a job is queued: the worker is not idle
    w._refresh_connection()
    assert not w.gm_on_action.isEnabled()
    w.gm_system_on()
    w.gm_system_off()
    assert fake.universal_messages == []
    w.worker.process_pending()
    w._firmware_running = True
    w.gm_system_on()
    w.gm_system_off()
    w._on_master_volume(10)
    assert fake.universal_messages == []
    w._firmware_running = False
    w.session.close()
    w._refresh_connection()
    assert not w.gm_on_action.isEnabled()
