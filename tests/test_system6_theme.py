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
    optional = {"font_family", "scroll_track_pattern", "extra_template", "card_titlebar", "hard_edges", "key_down_white", "key_down_black", "knob_track", "knob_arc", "graph_line", "fit_fixed_widths", "grow_window_for_scroll"}
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


def test_the_title_bars_white_patch_is_as_tall_behind_the_arrow_as_behind_the_title(qapp):
    # the title's label is taller than the 14 px arrow; patches of their own heights left a stripe showing under the arrow
    from PySide6.QtWidgets import QLabel

    from jv_studio.ui.section_card import SectionCard

    theme.apply_to_app(qapp, app_config.THEME_SYSTEM6)
    card = SectionCard("Tone Mixer", [])
    card._title_label.setMinimumHeight(26)  # (a font's line is only a pixel or two taller than the arrow here; make the difference plain)
    card.resize(300, 120)
    card.show()
    qapp.processEvents()
    image = card.grab().toImage()
    arrow, label = card.arrow().geometry(), card._title_label.geometry()
    assert label.height() > arrow.height()  # (the premise: they differ)
    top, bottom = min(arrow.top(), label.top()), max(arrow.bottom(), label.bottom())
    x = arrow.left() + 1  # (a column in the arrow's patch, left of its box's edge... and below the arrow itself, where a short patch showed stripes)
    for y in range(arrow.bottom() + 2, bottom + 1):
        assert image.pixelColor(x, y).name() == "#ffffff", f"a stripe shows under the arrow at y={y}"
    card.close()
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


def test_a_scroll_bars_outline_is_in_its_track_image_and_each_arrow_boxs_in_its_icon():
    # a QSS border on either was drawn over or clipped by Qt: the bar's side lines are the first and last column of the track tile, the
    # arrow boxes' sides are in their icons
    import os
    import re

    from PySide6.QtGui import QImage

    qss = theme.render_stylesheet(theme.SYSTEM6_PALETTE)
    for orientation, name, size in (("vertical", "scroll_track_v.png", (16, 2)), ("horizontal", "scroll_track_h.png", (2, 16))):
        tile = QImage(theme._write_checker(name, orientation))
        assert (tile.width(), tile.height()) == size and name in qss
        edge = [tile.pixelColor(x, y).name() for x in range(tile.width()) for y in range(tile.height()) if (x if orientation == "vertical" else y) in (0, 15)]
        assert set(edge) == {"#000000"}  # (the outline)
        inside = {tile.pixelColor(x, y).name() for x in range(tile.width()) for y in range(tile.height()) if (x if orientation == "vertical" else y) not in (0, 15)}
        assert inside == {"#000000", "#ffffff"}  # (the dither)
    for icon in set(re.findall(r"s6_scroll_[a-z_]+\.svg", qss)):
        assert os.path.isfile(os.path.join(theme._ICONS_DIR, icon)), icon
    assert "s6_scroll_up_pressed.svg" in qss


def test_spin_buttons_sit_inside_the_boxs_outline_and_every_tab_has_a_bottom_edge():
    qss = theme.render_stylesheet(theme.SYSTEM6_PALETTE)
    spin = qss[qss.index("QSpinBox::up-button, QDoubleSpinBox::up-button {") :].split("}")[0]
    assert "subcontrol-origin: padding" in spin
    tab = qss[qss.rindex("QTabBar::tab {") :].split("}")[0]
    assert "border-bottom: 1px solid #000000" in tab
    assert "color: transparent" in qss[qss.rindex("QProgressBar {") :].split("}")[0]  # (no percentage on the dither)
    other = theme.render_stylesheet(theme.DARK_PALETTE)
    assert "s6_scroll" not in other and "subcontrol-origin: padding" not in other[other.index("QSpinBox::up-button") :].split("}")[0]


def _fragments(document):
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            if iterator.fragment().isValid():
                yield iterator.fragment()
            iterator += 1
        block = block.next()


def test_markdown_code_and_links_follow_the_theme_in_system6_only(qapp):
    from PySide6.QtWidgets import QTextBrowser

    from jv_studio.ui.update_dialog import apply_theme_to_markdown

    def styled(theme_name):
        theme.apply_to_app(qapp, theme_name)
        view = QTextBrowser()
        view.setMarkdown("Text with `code` and a [link](https://example.com).")
        apply_theme_to_markdown(view.document())
        fragments = list(_fragments(view.document()))
        return next(f.charFormat() for f in fragments if f.text() == "code"), next(f.charFormat() for f in fragments if f.charFormat().isAnchor())

    code, link = styled(app_config.THEME_SYSTEM6)
    assert code.fontFamilies()[0] == "ChiKareGo2" and code.font().pixelSize() == 16 and not code.fontFixedPitch()
    assert link.foreground().color().name() == "#000000" and link.fontUnderline()  # (a black link is told from the text by its underline)
    code, link = styled(app_config.THEME_DARK)
    assert code.fontFixedPitch()  # (the other themes keep the document's own code font)
    assert link.foreground().color().name() != "#000000"
