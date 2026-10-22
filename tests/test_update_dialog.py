# tests for ui/update_dialog.py - the "new version available" dialog and its
# rendered release notes

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from jv_studio.core.update_checker import UpdateInfo
from jv_studio.ui import update_dialog
from jv_studio.ui.update_dialog import UpdateAvailableDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _info(notes=""):
    return UpdateInfo(
        version="1.3.0",
        tag="v1.3.0",
        name="JV Studio 1.3.0",
        html_url="https://github.com/martincurkovic/jv-studio/releases/tag/v1.3.0",
        notes=notes,
    )


def test_release_notes_are_rendered_from_markdown(qapp):
    dialog = UpdateAvailableDialog(
        _info("## What's new\n\n- **Rhythm set** editor\n- Faster `loading`")
    )
    view = dialog.notes_view
    assert view is not None
    html = view.toHtml()
    # rendered, not shown as raw Markdown source
    assert "##" not in view.toPlainText()
    assert "**" not in view.toPlainText()
    assert "Rhythm set" in view.toPlainText()
    assert "font-weight" in html  # the bold run
    assert view.isReadOnly()


def test_no_notes_section_when_the_release_has_no_description(qapp):
    for notes in ("", "   \n"):
        dialog = UpdateAvailableDialog(_info(notes))
        assert dialog.notes_view is None


def test_dialog_is_resizable_with_notes(qapp):
    dialog = UpdateAvailableDialog(_info("- a\n- b"))
    # no longer pinned to its sizeHint (it used to be SetFixedSize)
    assert dialog.minimumSize() != dialog.maximumSize()


def test_note_links_open_in_the_browser_not_in_the_widget(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(update_dialog, "_open_url", opened.append)
    dialog = UpdateAvailableDialog(_info("[docs](https://example.com/docs)"))
    assert dialog.notes_view.openLinks() is False
    dialog._open_notes_link(QUrl("https://example.com/docs"))
    assert opened == ["https://example.com/docs"]


def test_note_links_other_than_web_links_are_ignored(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(update_dialog, "_open_url", opened.append)
    dialog = UpdateAvailableDialog(_info("x"))
    for url in ("file:///etc/passwd", "javascript:alert(1)", "myapp://thing"):
        dialog._open_notes_link(QUrl(url))
    assert opened == []


def test_links_use_the_themes_accent_color(qapp):
    from PySide6.QtGui import QColor
    from jv_studio.ui import theme

    dialog = UpdateAvailableDialog(
        _info("see [the docs](https://example.com) and plain text")
    )
    accent = QColor(theme.current_palette()["accent"])
    document = dialog.notes_view.document()
    link_colors, plain_colors = [], []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            (link_colors if fmt.isAnchor() else plain_colors).append(
                fmt.foreground().color()
            )
            it += 1
        block = block.next()
    assert link_colors and all(c == accent for c in link_colors)
    # only the link run was recolored
    assert all(c != accent for c in plain_colors)


def test_the_heading_names_the_new_and_the_installed_version(qapp):
    from PySide6.QtWidgets import QLabel

    dialog = UpdateAvailableDialog(_info("x"))
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "JV Studio 1.3.0 is available" in texts
    assert any(t.startswith("You have version ") for t in texts)


def test_skipping_a_version_is_remembered(qapp):
    from jv_studio.core import app_config

    UpdateAvailableDialog(_info("x"))._skip_version()
    assert app_config.get_skipped_update_version() == "1.3.0"
