# Help > Quick Start Guide: the dialog renders help/quickstart.md, its links and pictures resolve, and search finds text.

import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from fakes import FakeJV1010, FakePorts
from jv_studio.core import midi
from jv_studio.ui import quickstart_dialog
from jv_studio.ui.main_window import MainWindow
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.quickstart_dialog import QuickStartDialog, _github_heading_slug, show_quickstart_dialog
from jv_studio.ui.unit_worker import UnitWorker

HELP = Path(quickstart_dialog.__file__).parent / "help"
GUIDE = (HELP / "quickstart.md").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_guide_loads_and_every_contents_link_has_a_heading(qapp):
    dialog = QuickStartDialog()
    assert dialog._markdown_loaded and "MIDI Setup" in dialog.viewer.toPlainText()
    headings = {_github_heading_slug(m.group(1)) for m in re.finditer(r"^#{2,4} (.+)$", GUIDE, re.M)}
    links = set(re.findall(r"\]\(#([^)]+)\)", GUIDE))
    assert links and links <= headings, f"links to headings that don't exist: {sorted(links - headings)}"


def test_every_picture_the_guide_names_exists():
    pictures = re.findall(r"!\[[^\]]*\]\(([^) ]+)", GUIDE)
    assert pictures
    missing = [p for p in pictures if not (HELP / p).is_file()]
    assert missing == []


def test_heading_slugs_match_githubs():
    assert _github_heading_slug("Sending & Receiving") == "sending--receiving"
    assert _github_heading_slug("Updating the Unit's Firmware") == "updating-the-units-firmware"


def test_search_counts_matches_and_steps_through_them(qapp):
    dialog = QuickStartDialog()
    dialog.show()  # (the search bar only counts as open once its dialog is on screen)
    dialog._open_search_bar()
    dialog.search_input.setText("Live edits")
    assert dialog._search_matches and dialog.search_results_label.text().startswith("1 of ")
    dialog._find_next()
    assert dialog._current_match_index == 1 % len(dialog._search_matches)
    dialog.search_input.setText("zzzz-not-in-the-guide")
    assert dialog.search_results_label.text() == "0 of 0"
    dialog._close_search_bar()
    assert dialog.search_bar.isHidden()
    dialog.close()


def test_a_missing_guide_says_so_instead_of_raising(qapp, monkeypatch):
    monkeypatch.setattr(quickstart_dialog, "_QUICKSTART_PATH", str(HELP / "nope.md"))
    dialog = QuickStartDialog()
    assert not dialog._markdown_loaded and "Couldn't load" in dialog.viewer.toPlainText()


def test_the_help_menu_opens_one_reused_guide(qapp, monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: [])
    monkeypatch.setattr(midi, "list_output_names", lambda: [])
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=FakePorts(FakeJV1010()).input_factory, output_factory=FakePorts(FakeJV1010()).output_factory))
    w = MainWindow(session, worker=UnitWorker(session, timeout=0.05), start_worker=False)
    help_menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Help")
    action = next(a for a in help_menu.actions() if a.text() == "Quick Start Guide...")
    action.trigger()
    first = w._quickstart_dialog
    assert isinstance(first, QDialog) and first.isVisible()
    show_quickstart_dialog(w)
    assert w._quickstart_dialog is first
    first.close()
