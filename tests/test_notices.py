# Help > Third-Party Notices...: the licence notices that ship inside the app (ui/help/THIRD_PARTY_NOTICES.md).

import os

import pytest
from PySide6.QtWidgets import QApplication, QTextBrowser

from jv_studio.ui import about_dialog
from jv_studio.ui.about_dialog import NoticesDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_notices_file_ships_in_the_help_folder_the_builds_already_bundle():
    assert os.path.dirname(about_dialog._NOTICES_PATH).endswith(os.path.join("ui", "help"))
    assert os.path.exists(about_dialog._NOTICES_PATH)


def test_the_viewer_shows_every_credit_the_app_owes(qapp):
    dialog = NoticesDialog()
    assert dialog.windowTitle() == "Third-party notices"
    text = dialog.findChild(QTextBrowser).toPlainText()
    for name in ("ChiKareGo2", "Giles Booth", "CC BY", "system.css", "AKAISDS", "jv1010tool", "GumiElectronic", "Roland"):
        assert name in text, name
    dialog.close()


def test_a_missing_notices_file_is_said_not_crashed_on(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(about_dialog, "_NOTICES_PATH", str(tmp_path / "nope.md"))
    dialog = NoticesDialog()
    assert "Couldn't load the notices" in dialog.findChild(QTextBrowser).toPlainText()
    dialog.close()


def test_the_help_menu_lists_it_between_about_and_updates_and_opens_the_viewer(qapp, monkeypatch):
    from jv_studio.ui import main_window

    opened = []

    class Stub:
        def __init__(self, parent):
            opened.append(parent)

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(main_window, "NoticesDialog", Stub)
    window = main_window.MainWindow(start_worker=False)
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == "Help")
    texts = [a.text() for a in help_menu.actions() if not a.isSeparator()]
    assert texts[-3:] == ["About JV Studio...", "Third-Party Notices...", "Check for Updates..."]
    next(a for a in help_menu.actions() if a.text() == "Third-Party Notices...").trigger()
    assert opened == [window, "exec"]
    window.close()
