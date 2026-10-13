# Collapsible section cards (ui/section_card.py).

import json

import pytest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel

from jv_studio.core import app_config
from jv_studio.ui import section_card
from jv_studio.ui.qt_helpers import build_editor_card, build_section_card
from jv_studio.ui.section_card import SectionCard


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_state():
    section_card.reset_state()
    yield
    section_card.reset_state()


def rows(n=1):
    out = []
    for i in range(n):
        row = QHBoxLayout()
        row.addWidget(QLabel(f"row {i}"))
        out.append(row)
    return out


def saved():
    return json.loads(app_config.CONFIG_PATH.read_text()).get("collapsed_cards", []) if app_config.CONFIG_PATH.exists() else []


def test_a_card_starts_open_and_collapsing_hides_only_the_body(qapp):
    card = build_editor_card("patch_editor", "Filter", *rows(3))
    assert isinstance(card, SectionCard) and not card.is_collapsed()
    open_height = card.sizeHint().height()
    card.arrow().click()
    assert card.is_collapsed() and card._body.isHidden() and card.sizeHint().height() < open_height
    card.arrow().click()
    assert not card.is_collapsed() and card.sizeHint().height() == open_height


def test_the_state_is_remembered_per_scope_and_title(qapp):
    build_editor_card("patch_editor", "Filter", *rows()).set_collapsed(True)
    assert saved() == ["patch_editor/Filter"]
    section_card.reset_state()
    assert build_editor_card("patch_editor", "Filter", *rows()).is_collapsed()
    assert not build_editor_card("other_page", "Filter", *rows()).is_collapsed()  # same title, another page


def test_a_change_the_user_did_not_ask_for_is_not_remembered(qapp):
    build_editor_card("patch_editor", "Filter", *rows()).set_collapsed(True, remember=False)
    assert saved() == []


def test_a_plain_card_has_no_arrow_and_a_non_collapsible_one_stays_plain(qapp):
    assert not isinstance(build_section_card("Audio", *rows()), SectionCard)
    assert not isinstance(build_editor_card("patch_editor", "Wave", *rows(), collapsible=False), SectionCard)


def test_a_card_that_asks_for_attention_shows_a_dot_only_while_collapsed(qapp):
    card = build_editor_card("patch_editor", "Common", *rows())
    card.set_attention(True, "unsent edits")
    assert card._attention_dot.isHidden()
    card.set_collapsed(True)
    assert not card._attention_dot.isHidden()
    card.set_collapsed(False)
    assert card._attention_dot.isHidden()
