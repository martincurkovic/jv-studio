# Check for Updates end to end, with the network faked: the runner's manual/automatic rules, the Help menu item, the start-up check and About's button.

import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fakes import FakeJV1010, FakePorts
from jv_studio.core import app_config, midi, update_checker
from jv_studio.core.update_checker import UpdateInfo
from jv_studio.ui import main_window as main_window_module
from jv_studio.ui import update_helper
from jv_studio.ui.about_dialog import AboutDialog
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker

NEWER = UpdateInfo(version="9.0.0", tag="v9.0.0", name="JV Studio 9.0.0", html_url="https://github.com/martincurkovic/jv-studio/releases/tag/v9.0.0", notes="## What's new\n\n- Something")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def network(qapp, monkeypatch):
    """Replaces the GitHub call: `network.result` is the UpdateInfo (or None) it returns, or an Exception it raises. Message boxes are recorded."""

    class Net:
        result = None
        calls = 0
        messages = []

    net = Net()
    net.messages = []

    def fake_check(current_version=None):
        net.calls += 1
        if isinstance(net.result, Exception):
            raise net.result
        return net.result

    monkeypatch.setattr(update_checker, "check_for_update", fake_check)
    for kind in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, kind, lambda parent, title, text, kind=kind: net.messages.append((kind, title, text)) or QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(update_helper, "UpdateAvailableDialog", lambda info, parent: _Recorded(net, info))
    return net


class _Recorded:
    def __init__(self, net, info):
        self.info = info
        net.shown = info

    def show(self):
        pass


def make_window(monkeypatch, **kwargs):
    monkeypatch.setattr(midi, "list_input_names", lambda: [])
    monkeypatch.setattr(midi, "list_output_names", lambda: [])
    ports = FakePorts(FakeJV1010())
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    return MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False, **kwargs)


def run_check(window, manual):
    window._update_runner.start(manual=manual)
    window._update_runner.wait()
    QApplication.processEvents()  # (the worker's signals are delivered on the GUI thread)


def test_a_newer_release_opens_the_update_window_with_its_notes(network, monkeypatch):
    network.result = NEWER
    w = make_window(monkeypatch)
    run_check(w, manual=True)
    assert network.shown is NEWER and network.shown.notes.startswith("## What's new")
    assert app_config.get_last_update_check() > 0


def test_a_manual_check_says_when_you_are_up_to_date_and_when_it_fails(network, monkeypatch):
    w = make_window(monkeypatch)
    network.result = None
    run_check(w, manual=True)
    assert network.messages[-1][1] == "No Updates Available"
    network.result = OSError("offline")
    run_check(w, manual=True)
    assert network.messages[-1][1] == "Update Check Failed" and "offline" in network.messages[-1][2]


def test_an_automatic_check_is_silent_unless_there_is_news(network, monkeypatch):
    w = make_window(monkeypatch)
    network.result = None
    run_check(w, manual=False)
    network.result = OSError("offline")
    run_check(w, manual=False)
    assert network.messages == []


def test_an_automatic_check_skips_the_version_you_skipped_but_a_manual_one_does_not(network, monkeypatch):
    app_config.save_skipped_update_version("9.0.0")
    network.result = NEWER
    w = make_window(monkeypatch)
    run_check(w, manual=False)
    assert not hasattr(network, "shown")
    run_check(w, manual=True)
    assert network.shown is NEWER


def test_the_help_menu_item_starts_a_manual_check(network, monkeypatch):
    network.result = NEWER
    w = make_window(monkeypatch)
    help_menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Help")
    next(a for a in help_menu.actions() if a.text() == "Check for Updates...").trigger()
    w._update_runner.wait()
    QApplication.processEvents()
    assert network.calls == 1 and network.shown is NEWER


def test_the_startup_check_is_off_by_default_and_in_demo_and_throttled(network, monkeypatch):
    fired = []
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda ms, fn: fired.append(ms))
    make_window(monkeypatch)
    make_window(monkeypatch, update_check=True, demo=False)  # never checked before: it is due
    assert fired == [2000]
    fired.clear()
    app_config.save_last_update_check(time.time())  # checked a moment ago
    make_window(monkeypatch, update_check=True)
    assert fired == []
    app_config.save_last_update_check(time.time() - 2 * main_window_module.UPDATE_CHECK_INTERVAL_SECONDS)
    make_window(monkeypatch, update_check=True)
    assert fired == [2000]


def test_the_about_dialog_has_a_check_button_that_disables_itself_while_it_runs(network, monkeypatch):
    network.result = None
    dialog = AboutDialog()
    assert dialog._check_updates_button.text() == "Check for Updates" and dialog._update_progress.isHidden()
    dialog._check_updates_button.click()
    assert not dialog._check_updates_button.isEnabled() or network.calls == 1
    dialog._update_runner.wait()
    QApplication.processEvents()
    assert dialog._check_updates_button.isEnabled() and dialog._update_progress.isHidden()
    assert network.messages[-1][1] == "No Updates Available"
    dialog.done(0)
