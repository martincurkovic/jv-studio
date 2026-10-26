# The Macintosh System 6 skin (Settings > Appearance > Theme): a third palette over the same template and painters.

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from jv_studio.core import app_config
from jv_studio.ui import theme


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _delete_leftover_windows(qapp):
    """Every app-wide theme change restyles every widget that is still alive, and earlier tests leave hundreds behind (their signal connections keep
    them): deleting them first keeps a theme switch to milliseconds instead of minutes late in the suite."""
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
def _back_to_the_default_theme(qapp):
    _delete_leftover_windows(qapp)
    yield
    theme.apply_to_app(qapp, app_config.THEME_DARK)


def test_it_is_a_choice_and_a_saved_value():
    assert ("Macintosh System 6", app_config.THEME_SYSTEM6) in theme.CHOICES
    app_config.save_theme(app_config.THEME_SYSTEM6)
    assert app_config.get_saved_theme() == app_config.THEME_SYSTEM6


def test_every_palette_has_the_same_required_keys():
    # (the optional painter / font keys exist only where they change something)
    optional = {"font_family", "scroll_track_pattern", "extra_template", "card_titlebar", "hard_edges", "key_down_white", "key_down_black", "knob_track", "knob_arc", "graph_line"}
    assert set(theme.SYSTEM6_PALETTE) - optional == set(theme.DARK_PALETTE) == set(theme.LIGHT_PALETTE)


def test_the_stylesheet_renders_for_every_palette():
    for palette in (theme.DARK_PALETTE, theme.LIGHT_PALETTE, theme.SYSTEM6_PALETTE):
        css = theme.render_stylesheet(palette)
        assert "${" not in css  # nothing left unfilled


def test_system6_is_square_black_and_white_with_a_dithered_scroll_track():
    css = theme.render_stylesheet(theme.SYSTEM6_PALETTE)
    assert "border-radius: 4px" not in css and "border-radius: 3px" not in css and "border-radius: 5px" not in css
    assert "font-family: " in css and "ChiKareGo2" in css
    assert "scroll_track_checker.png" in css
    for key in ("bg", "text", "accent", "border"):
        assert theme.SYSTEM6_PALETTE[key] in ("#000000", "#ffffff")


def test_the_other_themes_keep_their_shape_and_get_no_font_or_dither():
    for palette in (theme.DARK_PALETTE, theme.LIGHT_PALETTE):
        css = theme.render_stylesheet(palette)
        assert "border-radius: 4px" in css and "font-size: 13px" in css
        assert "font-family" not in css.split("QLabel#asciiLogo")[0] and "scroll_track_checker" not in css


def test_choosing_it_applies_the_palette_and_a_black_highlight_and_leaving_restores_qt(qapp):
    theme.apply_to_app(qapp, app_config.THEME_DARK)
    before = qapp.palette().color(QPalette.ColorRole.Highlight).name()
    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    assert theme.current_palette() is theme.SYSTEM6_PALETTE
    assert qapp.palette().color(QPalette.ColorRole.Highlight).name() == "#000000"
    theme.set_theme_preference(app_config.THEME_DARK)
    assert theme.current_palette() is theme.DARK_PALETTE
    assert qapp.palette().color(QPalette.ColorRole.Highlight).name() == before


def test_the_painted_widgets_use_one_colour_in_system6(qapp):
    from jv_studio.ui.knob import VALUE_ARC_COLOR

    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    palette = theme.current_palette()
    assert palette["knob_arc"] != VALUE_ARC_COLOR and palette["graph_line"] == "#000000"
    theme.set_theme_preference(app_config.THEME_DARK)
    assert "graph_line" not in theme.current_palette() and "knob_arc" not in theme.current_palette()


def test_the_theme_flag_names_a_theme_for_one_run_and_ignores_nonsense():
    from jv_studio.main import theme_from_argv

    assert theme_from_argv(["jv-studio", "--demo", "--theme=system6"]) == "system6"
    assert theme_from_argv(["jv-studio", "--theme=dark"]) == "dark"
    assert theme_from_argv(["jv-studio", "--theme=chicago"]) is None
    assert theme_from_argv(["jv-studio", "--demo"]) is None
    assert app_config.get_saved_theme() == app_config.THEME_SYSTEM  # (reading the flag saves nothing)


def test_the_extra_rules_and_the_bundled_font_belong_to_system6_only():
    system6 = theme.render_stylesheet(theme.SYSTEM6_PALETTE)
    assert "QMenu::item:selected" in system6 and "s6_check_x.svg" in system6 and "QScrollBar::sub-line:vertical" in system6
    for palette in (theme.DARK_PALETTE, theme.LIGHT_PALETTE):
        css = theme.render_stylesheet(palette)
        assert "s6_" not in css and "QMenu" not in css
    from pathlib import Path

    icons, fonts = Path(theme._ICONS_DIR), Path(theme._FONTS_DIR)
    assert (fonts / "ChiKareGo2.ttf").is_file() and (fonts / "README.txt").is_file()  # bundled (the build scripts' DATA_ARGS), credited
    import re

    for name in set(re.findall(r"s6_[a-z_]+\.svg", system6)):
        assert (icons / name).is_file(), name


def test_a_section_card_draws_a_title_bar_only_in_system6(qapp):
    from jv_studio.ui.section_card import SectionCard

    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    card = SectionCard("Filter", [])
    assert card.layout().contentsMargins().top() == 3
    theme.set_theme_preference(app_config.THEME_DARK)
    assert card.layout().contentsMargins().top() == 10
    card.deleteLater()


def test_pressed_piano_keys_go_grey_in_system6_and_take_the_accent_elsewhere(qapp):
    from jv_studio.ui.keyboard import PianoKeyboard

    keyboard = PianoKeyboard()
    keyboard.resize(1000, 74)
    keyboard.show()
    for note in (60, 61):  # a white key and a black one
        keyboard._press(note)

    def colour_of(note):
        rect = keyboard._key_rect(note)
        return keyboard.grab().toImage().pixelColor(int(rect.center().x()), int(rect.top() + 6)).name()

    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    assert colour_of(60) == theme.SYSTEM6_PALETTE["key_down_white"] and colour_of(61) == theme.SYSTEM6_PALETTE["key_down_black"]
    theme.set_theme_preference(app_config.THEME_DARK)
    assert colour_of(60) == colour_of(61) == theme.DARK_PALETTE["accent"]
    keyboard.release_all()
    keyboard.deleteLater()
