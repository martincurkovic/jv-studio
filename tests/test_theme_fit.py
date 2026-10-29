# ui/theme_fit.py: in the Macintosh System 6 skin a control pinned to a width that is too narrow for its wider font grows to fit, a window grows (and
# keeps a wider minimum) when its page or layout needs more room, and a skin switched WHILE windows are open is applied to them. Dark and light are
# left exactly as they were. Copied from AKAISDS's tests, without its row-widget parts.

import time

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from jv_studio.core import app_config
from jv_studio.ui import theme, theme_fit


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _delete_leftover_windows(qapp):
    """Every app-wide theme change restyles every widget that is still alive: delete the ones earlier tests left behind first."""
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent

    for _ in range(3):
        for widget in qapp.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
        gc.collect()


@pytest.fixture(autouse=True)
def _start_in_dark_and_end_there(qapp):
    _delete_leftover_windows(qapp)
    theme.apply_to_app(qapp, app_config.THEME_DARK)
    theme_fit.install(qapp)
    yield
    _delete_leftover_windows(qapp)
    theme.apply_to_app(qapp, app_config.THEME_DARK)


def _wait(qapp, until, seconds=2.0):
    deadline = time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return until()


def test_only_system6_asks_for_any_of_it():
    for key in ("fit_fixed_widths", "grow_window_for_scroll"):
        assert theme.SYSTEM6_PALETTE[key] is True
        assert key not in theme.DARK_PALETTE and key not in theme.LIGHT_PALETTE


def test_apply_to_app_installs_the_filter_once(qapp):
    first = theme_fit.install(qapp)
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    assert theme_fit.install(qapp) is first


# -- fitting a width --------------------------------------------------------------------------------------------------------------------------


def test_a_fixed_width_too_narrow_for_the_text_grows_to_fit(qapp):
    label = QLabel("A fairly long label for a narrow box")
    label.setFixedWidth(20)
    assert theme_fit.fit(label) is True
    assert label.minimumWidth() == label.maximumWidth() == label.sizeHint().width()


def test_a_wide_enough_or_free_width_is_left_alone(qapp):
    wide, free = QLabel("x"), QLabel("some text")
    wide.setFixedWidth(500)
    assert theme_fit.fit(wide) is False and wide.maximumWidth() == 500
    assert theme_fit.fit(free) is False and free.maximumWidth() == 16777215


def test_a_capped_width_is_raised_and_a_wrapping_label_is_never_fitted(qapp):
    capped = QLabel("A fairly long label for a narrow box")
    capped.setMaximumWidth(20)
    assert theme_fit.fit(capped) is True and capped.maximumWidth() == capped.sizeHint().width()
    wrapping = QLabel("A fairly long label that wraps")
    wrapping.setWordWrap(True)
    wrapping.setFixedWidth(20)
    assert theme_fit.fit(wrapping) is False


def test_the_filter_fits_on_show_in_system6_and_not_in_dark(qapp):
    dark = QLabel("A fairly long label for a narrow box")
    dark.setFixedWidth(20)
    dark.show()
    qapp.processEvents()
    assert dark.maximumWidth() == 20
    dark.close()
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    system6 = QLabel("A fairly long label for a narrow box")
    system6.setFixedWidth(20)
    system6.show()
    qapp.processEvents()
    assert system6.maximumWidth() > 20
    system6.close()


# -- windows ------------------------------------------------------------------------------------------------------------------------------------


def _scroll_window(qapp, minimum=300):
    window = QWidget()
    outer = QVBoxLayout(window)
    scroll = QScrollArea()
    page = QWidget()
    scroll.setWidget(page)
    outer.addWidget(scroll)
    window.setMinimumWidth(minimum)
    window.resize(minimum, 200)
    window.show()
    qapp.processEvents()
    return window, scroll, page


def test_a_window_is_widened_by_what_its_scroll_bar_lacks_and_keeps_that_as_its_minimum(qapp):
    window, scroll, page = _scroll_window(qapp, minimum=0)
    page.setMinimumWidth(500)
    qapp.processEvents()
    missing = scroll.horizontalScrollBar().maximum()
    assert missing > 0
    before, screen_width = window.width(), window.screen().availableGeometry().width()
    assert theme_fit.grow_window(scroll) is True
    assert window.width() == min(before + missing, screen_width)
    assert window.minimumWidth() == window.width()
    window.close()


def test_a_page_that_grows_after_the_window_is_shown_still_widens_it_in_system6(qapp):
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    window, scroll, page = _scroll_window(qapp)
    page.setMinimumWidth(500)
    assert _wait(qapp, lambda: scroll.horizontalScrollBar().maximum() == 0)
    assert window.width() >= 500 and window.minimumWidth() >= 500
    window.close()


def test_a_window_with_a_pinned_minimum_grows_to_what_its_layout_needs_in_system6(qapp):
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    dialog = QDialog()
    layout = QHBoxLayout(dialog)
    wide = QLabel("x")
    wide.setFixedWidth(500)
    layout.addWidget(wide)
    dialog.setMinimumSize(300, 100)  # (Qt lets an explicit minimum win over the layout's own)
    dialog.resize(300, 100)
    dialog.show()
    assert _wait(qapp, lambda: dialog.width() >= 500)
    assert dialog.minimumWidth() >= 500
    dialog.close()


def test_dark_never_widens_a_window(qapp):
    window, scroll, page = _scroll_window(qapp)
    page.setMinimumWidth(500)
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.01)
    assert window.width() == 300 and scroll.horizontalScrollBar().maximum() > 0
    window.close()


# -- a skin switched while windows are open -----------------------------------------------------------------------------------------------


def test_widgets_already_shown_are_refitted_on_a_switch_to_system6_and_restored_when_it_leaves(qapp):
    label = QLabel("A fairly long label for a narrow box")
    label.setFixedWidth(20)
    label.show()
    qapp.processEvents()
    assert label.maximumWidth() == 20
    theme.set_theme_preference(app_config.THEME_SYSTEM6)
    assert _wait(qapp, lambda: label.maximumWidth() > 20)
    theme.set_theme_preference(app_config.THEME_DARK)
    assert _wait(qapp, lambda: label.maximumWidth() == 20)
    assert label.minimumWidth() == 20
    label.close()


def test_a_window_already_open_gets_a_wider_minimum_on_a_switch_and_its_old_one_back_when_it_leaves(qapp):
    window, scroll, page = _scroll_window(qapp)
    page.setMinimumWidth(500)  # (what the new skin's font does to the page)
    qapp.processEvents()
    assert window.width() == 300
    theme.set_theme_preference(app_config.THEME_SYSTEM6)
    assert _wait(qapp, lambda: scroll.horizontalScrollBar().maximum() == 0)
    assert window.width() >= 500 and window.minimumWidth() >= 500
    theme.set_theme_preference(app_config.THEME_DARK)
    assert _wait(qapp, lambda: window.minimumWidth() == 300)
    window.close()


# -- widths that must stay equal ------------------------------------------------------------------------------------------------------------------


def test_grouped_widgets_are_widened_to_the_widest_so_they_stay_one_width(qapp):
    window = QWidget()
    layout = QVBoxLayout(window)
    short, long_ = QPushButton("Settings"), QPushButton("Open Editor With A Long Name")
    for button in (short, long_):
        button.setFixedWidth(40)
        layout.addWidget(button)
    theme_fit.group("stacked", short, long_)
    window.show()
    qapp.processEvents()
    assert short.width() == long_.width() == 40
    theme.set_theme_preference(app_config.THEME_SYSTEM6)
    assert _wait(qapp, lambda: short.minimumWidth() == long_.minimumWidth() > 40)
    assert short.minimumWidth() >= long_.sizeHint().width()
    theme.set_theme_preference(app_config.THEME_DARK)
    assert _wait(qapp, lambda: short.minimumWidth() == long_.minimumWidth() == 40)
    window.close()


def test_a_fixed_width_container_and_its_header_grow_with_what_is_inside_it(qapp):
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    window = QWidget()
    outer = QHBoxLayout(window)
    header = QLabel("Key range")
    header.setFixedWidth(120)
    cell = QWidget()
    cell.setFixedWidth(120)
    inside = QHBoxLayout(cell)
    inside.setContentsMargins(0, 0, 0, 0)
    for _ in range(2):
        spin = QSpinBox()
        spin.setFixedWidth(100)
        inside.addWidget(spin)
    theme_fit.group("range", header, cell)
    outer.addWidget(header)
    outer.addWidget(cell)
    window.show()
    assert _wait(qapp, lambda: cell.minimumWidth() >= 200)
    assert header.minimumWidth() == cell.minimumWidth()
    window.close()
