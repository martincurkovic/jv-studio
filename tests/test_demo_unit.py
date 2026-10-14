# The simulated JV-1010 that --demo talks to: believable contents, a working conversation, and an app that never touches real ports.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from jv_studio.core import backup, demo_unit, memory, midi, params, patch, performance, validate
from jv_studio.core.unit import JV1010Unit
from jv_studio.ui import demo as demo_mode
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def unit():
    return demo_unit.make_demo_unit()


def test_every_demo_patch_and_performance_is_valid(unit):
    for p in [unit.temporary, *unit.user]:
        assert validate.out_of_range(p) == [], p.name
    for p in [unit.temp_performance, *unit.user_performances]:
        assert validate.out_of_range_performance(p) == [], p.name


def test_the_user_patches_are_the_factory_ones_with_two_renamed(unit):
    factory = params.load_table().factory_user_patches
    differing = [i for i, p in enumerate(unit.user) if p.name != factory[i].name]
    assert differing == [4, 76] and unit.user[4].name == "My Lead" and unit.user[1].name == "St.Concert"
    assert unit.temporary == unit.user[1]
    assert [bool(p.get(patch.COMMON, "key_assign_mode")) for p in unit.user[:2]] == [False, False]


def test_the_patches_are_playable_not_silent(unit):
    for p in unit.user:
        voices = sum(p.get(patch.TONE, "tone_switch", tone=t) for t in range(4))
        assert 1 <= voices <= 4
        for t in range(4):
            if p.get(patch.TONE, "tone_switch", tone=t):
                assert p.get(patch.TONE, "velocity_range_upper", tone=t) == 127 and p.get(patch.TONE, "keyboard_range_upper", tone=t) == 127
                assert p.get(patch.TONE, "tone_level", tone=t) > 0


def test_every_demo_name_fits_the_units_twelve_characters(unit):
    names = [p.name for p in [*unit.user, *unit.user_performances]]
    assert all(0 < len(n) <= 12 for n in names) and unit.user_performances[5].name == "Demo Perf 06"
    wanted = ["Live Rig", "Layer Pad", "Split Keys", "Studio Mix", "Str+Brass"]
    assert [p.name for p in unit.user_performances[:5]] == wanted


def test_the_performances_have_named_parts_on_their_own_channels(unit):
    p = unit.user_performances[0]
    assert p.name == "Live Rig" and unit.temp_performance == p
    assert [p.get(performance.PART, "midi_channel", part=i) for i in range(8)] == list(range(8))
    assert [p.get(performance.PART, "receive_switch", part=i) for i in (0, 7, 8, 15)] == [1, 1, 0, 0]
    assert sum(p.get(performance.COMMON, f"voice_reserve_{n}") for n in range(1, 17)) <= 64


def connection(latency=0.0):
    ports = demo_unit.DemoPorts(demo_unit.make_demo_unit(), latency)
    return midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory), ports


def test_the_conversation_works_over_the_demo_ports():
    conn, ports = connection()
    u = JV1010Unit(conn, timeout=0.2)
    assert u.read_temporary_patch().name == "St.Concert" and u.read_user_patch(76).name == "Warm Pad 2"
    assert u.read_temporary_performance().name == "Live Rig" and u.read_user_performance_names()[:2] == ["Live Rig", "Layer Pad"]
    changed = u.read_user_patch(10)
    changed.name = "Edited"
    u.write_patch(patch.user_patch_base(10) if hasattr(patch, "user_patch_base") else patch.user_base(10), changed)
    assert ports.unit.user[10].name == "Edited"


def test_a_whole_unit_backup_and_restore_work_on_it():
    conn, ports = connection()
    u = JV1010Unit(conn, timeout=0.2)
    sections = [memory.SYSTEM, memory.PERFORMANCES, memory.RHYTHM, memory.PATCHES]
    saved = backup.read_backup(u, sections)
    assert saved.is_complete(sections)
    key = memory.plan([memory.RHYTHM])[2].start
    original = bytes(ports.unit.block_data(key))
    ports.unit.block_data(key)[0] ^= 1
    backup.restore(u, saved, [memory.RHYTHM])  # (a small section: the writes wait 20 ms each, for real)
    assert bytes(ports.unit.block_data(key)) == original


def test_latency_makes_a_request_take_time_but_not_other_traffic(monkeypatch):
    sleeps = []
    monkeypatch.setattr(demo_unit.time, "sleep", sleeps.append)
    conn, _ = connection(latency=0.004)
    u = JV1010Unit(conn, timeout=0.2)
    u.read_temporary_patch()
    assert sleeps == [0.004] * 5  # one per request (a patch is five)


def test_the_demo_flag_and_environment(monkeypatch):
    monkeypatch.delenv("JV_STUDIO_DEMO", raising=False)
    assert demo_mode.wanted(["jv-studio", "--demo"]) and not demo_mode.wanted(["jv-studio"])
    monkeypatch.setenv("JV_STUDIO_DEMO", "1")
    assert demo_mode.wanted(["jv-studio"])
    monkeypatch.setenv("JV_STUDIO_DEMO", "off")
    assert not demo_mode.wanted(["jv-studio"])
    monkeypatch.setenv("JV_STUDIO_DEMO_INSTANT", "1")
    assert demo_mode.latency() == 0.0


def test_the_demo_window_uses_the_simulated_unit_and_never_lists_real_ports(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: (_ for _ in ()).throw(AssertionError("a real port was listed")))
    monkeypatch.setattr(midi, "list_output_names", lambda: (_ for _ in ()).throw(AssertionError("a real port was listed")))
    session, unit = demo_mode.build_demo(request_latency=0)
    assert session.is_open
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: told.append(text) or QMessageBox.StandardButton.Ok)
    window = MainWindow(session=session, worker=UnitWorker(session, timeout=0.2), start_worker=False, demo=True)
    assert "demo" in window.windowTitle() and window.connection_label.isHidden() and window.btn_read_temporary.isEnabled()
    window.read_temporary()
    window.worker.process_pending()
    assert window.patch_label.text() == 'Temporary patch · St.Concert'
    window.open_settings()
    assert told and "simulated" in told[0]
    window.read_names()
    window.worker.process_pending()
    assert window.names_list.count() == 128 and "2 differ from the factory list" in window.statusBar().currentMessage()
    window.close()
    window.deleteLater()
