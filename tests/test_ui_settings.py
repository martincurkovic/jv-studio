# The Settings dialog against fake ports: choosing ports, both diagnostics, errors, the theme.

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts, corrupting_loopback, loopback, silent
from jv_studio.core import app_config, midi, midi_diagnostics
from jv_studio.ui import loopback_results_dialog, settings_dialog, theme
from jv_studio.ui.midi_session import MidiSession


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class Rig:
    """A session whose connections run over one FakePorts, and the dialogs' message boxes recorded instead of shown."""

    def __init__(self, respond=None):
        self.ports = FakePorts(respond)
        self.opened = []
        self.session = MidiSession(self._factory)
        self.messages = []

    def _factory(self, input_name, output_name):
        self.opened.append((input_name, output_name))
        return midi.MidiConnection(input_name, output_name, input_factory=self.ports.input_factory, output_factory=self.ports.output_factory)


@pytest.fixture
def rig(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: ["JV In", "Other In"])
    monkeypatch.setattr(midi, "list_output_names", lambda: ["JV Out", "Other Out"])
    r = Rig(FakeJV1010())
    for kind in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, kind, lambda parent, title, text, kind=kind: r.messages.append((kind, title, text)) or QMessageBox.StandardButton.Ok)
    return r


def dialog(rig):
    d = settings_dialog.SettingsDialog(rig.session)
    return d


def pick(d, input_name, output_name):
    d.combo_input.setCurrentIndex(d.combo_input.findData(input_name))
    d.combo_output.setCurrentIndex(d.combo_output.findData(output_name))


def test_the_ports_are_listed_with_none_first(rig):
    d = dialog(rig)
    assert [d.combo_input.itemText(i) for i in range(d.combo_input.count())] == ["(None)", "JV In", "Other In"]
    assert [d.combo_output.itemText(i) for i in range(d.combo_output.count())] == ["(None)", "JV Out", "Other Out"]
    assert d.combo_input.currentData() is None


def test_the_open_ports_are_preselected(rig):
    rig.session.open("Other In", "JV Out")
    d = dialog(rig)
    assert (d.combo_input.currentData(), d.combo_output.currentData()) == ("Other In", "JV Out")


def test_ok_opens_the_ports_and_remembers_them(rig):
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    d._apply_and_close()
    assert rig.session.is_open and (rig.session.input_name, rig.session.output_name) == ("JV In", "JV Out")
    assert app_config.get_saved_ports() == ("JV In", "JV Out")


def test_choosing_none_closes_the_connection(rig):
    rig.session.open("JV In", "JV Out")
    d = dialog(rig)
    pick(d, None, None)
    d._apply_and_close()
    assert not rig.session.is_open and app_config.get_saved_ports() == (None, None)


def test_a_port_that_will_not_open_is_reported_and_nothing_is_saved(rig, monkeypatch):
    def boom(*args):
        raise RuntimeError("device vanished")

    rig.session.connection_factory = boom
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    d._apply_and_close()
    assert rig.messages and rig.messages[0][0] == "critical" and "device vanished" in rig.messages[0][2]
    assert app_config.get_saved_ports() == (None, None) and not rig.session.is_open


# -- hardware test ------------------------------------------------------------------------------------------------------


def test_the_hardware_test_needs_both_ports(rig):
    d = dialog(rig)
    d._run_hardware_test()
    assert rig.messages[0][0] == "warning" and rig.opened == []


def test_the_hardware_test_finds_the_unit_and_shows_its_patch_name(rig):
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    d._run_hardware_test()
    assert "Roland JV-1010 found" in d.hardware_results_label.text() and 'Temporary patch: "Warm Pad"' in d.hardware_results_label.text()
    assert d.btn_hardware_test.isEnabled() and d.btn_hardware_test.text() == "Run Hardware Test" and not d.hardware_progress.isVisible()


def test_the_hardware_test_borrows_the_ports_and_gives_them_back(rig):
    rig.session.open("JV In", "JV Out")
    first = rig.session.connection
    d = dialog(rig)
    pick(d, "Other In", "Other Out")  # testing different ports than the open ones
    d._run_hardware_test()
    assert rig.opened == [("JV In", "JV Out"), ("Other In", "Other Out"), ("JV In", "JV Out")]  # opened, borrowed, restored
    assert rig.session.is_open and rig.session.connection is not first and rig.session.input_name == "JV In"


def test_no_reply_is_said_plainly(rig, monkeypatch):
    rig.ports.respond = silent
    monkeypatch.setattr(midi_diagnostics, "RECEIVE_TIMEOUT", 0.05)
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    d._run_hardware_test()
    assert "No reply" in d.hardware_results_label.text()


def test_a_failing_test_is_reported_and_the_buttons_come_back(rig):
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    rig.session.connection_factory = lambda *a: (_ for _ in ()).throw(RuntimeError("port busy"))
    d._run_hardware_test()
    assert rig.messages and "port busy" in rig.messages[-1][2] and d.btn_hardware_test.isEnabled()


# -- loopback test ----------------------------------------------------------------------------------------------------


def run_loopback(d, monkeypatch):
    shown = []
    monkeypatch.setattr(loopback_results_dialog.LoopbackResultsDialog, "exec", lambda self: shown.append(self.report()) or 0)
    d._run_loopback_test()
    return shown


def test_the_loopback_test_runs_every_size_and_shows_the_results(rig, monkeypatch):
    rig.ports.respond = loopback
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    (report,) = run_loopback(d, monkeypatch)
    assert all(f"{size:>5} bytes: PASS" in report for size in midi_diagnostics.LOOPBACK_SIZES) and "All sizes tested passed cleanly." in report
    assert d.btn_loopback_test.isEnabled() and d.btn_loopback_test.text() == "Run Loopback Test"


def test_a_corrupting_interface_shows_failures(rig, monkeypatch):
    rig.ports.respond = corrupting_loopback
    d = dialog(rig)
    pick(d, "JV In", "JV Out")
    (report,) = run_loopback(d, monkeypatch)
    assert "FAIL - corrupted" in report and "starts failing around 8 bytes" in report


def test_the_share_button_is_hidden_without_a_repository(qapp):
    dlg = loopback_results_dialog.LoopbackResultsDialog([(8, True, "OK")], "A", "A")
    assert dlg.share_button.isHidden() and not dlg.copy_button.isHidden()
    dlg.copy_button.click()
    assert "MIDI interface: A" in QApplication.clipboard().text()


# -- theme --------------------------------------------------------------------------------------------------------------


def test_picking_a_theme_applies_it_at_once_and_saves_it(rig):
    d = dialog(rig)
    d.combo_theme.setCurrentIndex(d.combo_theme.findData("dark"))
    d._on_theme_chosen(d.combo_theme.currentIndex())
    assert app_config.get_saved_theme() == "dark" and theme.current_preference() == "dark"
    theme.set_theme_preference("system")


def test_restoring_the_saved_theme_does_not_count_as_a_choice(rig):
    # only a user's `activated` applies and saves; merely opening the dialog changes nothing
    app_config.save_theme("light")
    theme.set_theme_preference("dark")
    d = dialog(rig)
    assert d.combo_theme.currentData() == "light"
    assert theme.current_preference() == "dark" and app_config.get_saved_theme() == "light"
    theme.set_theme_preference("system")


@pytest.mark.parametrize("palette", [theme.DARK_PALETTE, theme.LIGHT_PALETTE])
def test_both_palettes_render_the_whole_stylesheet(palette):
    css = theme.render_stylesheet(palette)  # a ${key} missing from a palette raises
    assert "${" not in css and palette["accent"] in css


def test_the_two_palettes_have_the_same_keys():
    assert set(theme.DARK_PALETTE) == set(theme.LIGHT_PALETTE)
