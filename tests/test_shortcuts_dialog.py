# Help > Keyboard Shortcuts: the list is read from the real menu bar, so it can't drift from the actual bindings.

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow

from fakes import FakeJV1010, FakePorts
from jv_studio.core import midi
from jv_studio.ui import shortcuts_dialog as sd
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.unit_worker import UnitWorker


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _window_with_menus():
    window = QMainWindow()
    file_menu = window.menuBar().addMenu("&File")
    open_action = QAction("&Open...", window)
    open_action.setShortcut("Ctrl+O")
    file_menu.addAction(open_action)
    file_menu.addSeparator()
    file_menu.addAction(QAction("No shortcut", window))
    tools = window.menuBar().addMenu("&Tools")
    sub = tools.addMenu("More")
    deep = QAction("Deep", window)
    deep.setShortcuts(["Ctrl+D", "Ctrl+Shift+D"])
    sub.addAction(deep)
    window.menuBar().addMenu("&Empty").addAction(QAction("Nothing", window))
    return window


def test_menu_shortcuts_are_read_from_the_menu_bar(qapp):
    window = _window_with_menus()  # (kept: the menu bar dies with its window)
    sections = sd.collect_menu_shortcuts(window.menuBar())
    assert [title for title, _rows in sections] == ["File", "Tools"]  # a menu without shortcuts is left out
    assert sections[0][1] == [("Open...", sd._native("Ctrl+O"))]  # mnemonics stripped, unbound actions skipped
    assert sections[1][1][0][0] == "Deep" and " or " in sections[1][1][0][1]  # submenus are searched, every binding is shown


def test_the_dialog_lists_menu_and_extra_sections(qapp):
    window = _window_with_menus()
    dialog = sd.ShortcutsDialog(window, sd.collect_menu_shortcuts(window.menuBar()) + [sd.audition_section()])
    assert [title for title, _rows in dialog.sections][-1].startswith("Audition keyboard")


def test_the_help_menu_opens_one_reused_dialog_that_names_the_real_shortcuts(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: [])
    monkeypatch.setattr(midi, "list_output_names", lambda: [])
    ports = FakePorts(FakeJV1010())
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    help_menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Help")
    next(a for a in help_menu.actions() if a.text() == "Keyboard Shortcuts...").trigger()
    first = w._shortcuts_dialog
    assert first.isVisible()
    rows = {what: keys for _title, section in first.sections for what, keys in section}
    assert rows["Audition Keyboard"] == sd._native("Ctrl+K") and rows["Undo"]  # taken from the menu bar itself
    assert "Audition keyboard (while it is open)" in [title for title, _rows in first.sections]
    sd.show_shortcuts_dialog(w)
    assert w._shortcuts_dialog is first
    first.close()
