# Macintosh System 6 theme: status and roadmap

A skin that makes JV Studio look like a Macintosh System 6 application: black, white and greys, plus a little colour only where it carries meaning. Started 2026-10-22 as a monochrome **demo**; the owner has since kept it as a theme (2026-10-26), allowed greys and state colours, and **decided against the custom window frame** (Phase B below is kept only as the record of what it would cost).
This file says what exists, what can and cannot be done, and what is still undecided, so the next agent doesn't re-research it. The short version of the code facts is also in `AGENTS.md` ("Macintosh System 6 skin").

Reference: <https://github.com/sakofchit/system.css> (MIT; a CSS library, System 6 look, last pushed 2023-11). **Nothing of its CSS can be used directly**: Qt style sheets (QSS) are a small CSS-2-like subset (no variables, no `box-shadow`, no real `::before`/`::after`, no `calc`). It is a visual reference and a source of SVG shapes (`icon/button.svg`, `checkmark.svg`, scroll bar arrows, `select-button.svg`), not code.

## Try it

- `uv run jv-studio --demo --theme=system6` (this run only, nothing saved; demo mode blocks Settings, which is why the flag exists), or Settings > Appearance > Theme > "Macintosh System 6 (monochrome)" with ports open.
- The bitmap-style font (ChiKareGo2, CC BY, credited in `ui/fonts/README.txt`) is committed and bundled; `tools/fetch_system6_font.py` only re-creates it.
- Pictures for review: `uv run python tools/make_screenshots.py --out DIR --scheme system6 --overwrite [--only NAME ...]` photographs the existing recipes in the skin (nothing is written to the guide). The guide's own pictures stay dark-theme only.

## What exists (done, 2026-10-22, tests in `tests/test_system6_theme.py`)

- A third palette, `theme.SYSTEM6_PALETTE`, selected by `app_config.THEME_SYSTEM6` (`"system6"`), offered in `theme.CHOICES`. Black, white and one grey (disabled text and borders, knob track, list row separators); selection and checked buttons are inverted video; square corners except push buttons (6 px).
- **Template tokens:** corner radii, font size/weight, pressed/selected text colours and scroll bar fills were hard-coded in `style.qss.template`; they are now palette values (`radius`, `radius_small`, `radius_button`, `radius_pill`, `font_size`, `font_size_small`, `font_weight_bold`, `text_pressed`, `text_selected`, `text_tab_selected`, `scroll_track`, `scroll_handle`, `scroll_handle_border`, `logo_rule`), so all three palettes fill the same template and **dark/light are pixel-identical to before** (checked against the committed guide screenshots). A missing key still raises at start-up.
- **Optional keys only this skin has:** `font_family`, `scroll_track_pattern` (a generated 2 x 2 checker PNG in `~/.jv-studio/generated_icons`, for a dithered scroll track), `knob_track`, `knob_arc`, `graph_line`. The painters (`knob.py`, `envelope_graph.py`) read them with `.get(...)`, so the other themes are untouched.
- **Qt's own widgets** that QSS does not draw (slider groove, native menu highlight) take their colours from the application `QPalette`: `theme._apply_qt_palette` sets a black/white one while System 6 is active and restores Qt's own when leaving (only if System 6 had replaced it).
- The ASCII logo keeps its monospace font whatever the theme says (`QLabel#asciiLogo`, `logo_rule`): the theme's font family would otherwise garble the art.
- `--theme=NAME` command-line flag (`main.theme_from_argv`).

## Done 2026-10-26 (the second pass; the font licence was confirmed as CC BY)

- **Font bundled** (`ui/fonts/ChiKareGo2.ttf` + `README.txt` credit; folder un-ignored; `ui/fonts` and the new template are in all three build scripts' `DATA_ARGS`).
- **`ui/style_system6.qss.template`** is appended after the shared template ONLY when the palette has `extra_template` (so dark/light cannot change: checked pixel-identical against the committed guide pictures). It holds: menus and the in-window menu bar (inverted hover, ruled separators), 16 px scroll bars with an arrow box at each end and the dithered track, check boxes and radio buttons as a white box with an X, combo and spin box arrows as solid triangles in a ruled-off box, the default / primary button's heavy 3 px ring (primary is no longer a black fill here), a dithered progress chunk, a rule over the status bar. Icons `ui/icons/s6_*.svg` (black, static).
- **Cards** (`section_card.py`, palette key `card_titlebar`): a striped title bar flush with the card's top, a white patch behind the heading, and the disclosure arrow drawn as a close-box. The layout's top margin is 3 instead of 10 in this skin (`_theme_changed`).
- **Hard edges** (palette key `hard_edges`): knobs and envelope graphs are painted without anti-aliasing.
- New optional palette keys, System 6 only: `extra_template`, `card_titlebar`, `hard_edges`.

## Scroll bars, spin boxes and tabs fixed (2026-10-29, found in akaiutil-GUI's port of this skin and brought back)

- **Scroll bars** now have a full outline, boxed arrows and a dithered track. A QSS `border` on the bar clipped the arrow boxes' sides, and one on the boxes was drawn over, so the outlines live in images instead: the track's in a tile (`scroll_track_v` / `scroll_track_h`, made by `theme._write_checker(name, orientation)`: 16 x 2 / 2 x 16 with the first and last column/row black), each arrow box's in its icon (`ui/icons/s6_scroll_{up,down,left,right}[_pressed].svg`, an outlined 16 px box with the arrow; the pressed one is inverted). The thumb keeps its own border.
- **Spin boxes**: the up/down buttons are `subcontrol-origin: padding`, inside the box's outline (the shared stylesheet's `border` origin puts them over it and hides the right, top and bottom edges).
- **Tab bars**: every tab has a bottom border (the shared rule takes it off, and the pane's own top border sits under the strip, so nothing was drawn under the unselected tabs).
- **Progress bars** show no percentage (it can't be read on the dither; the comment above the rule always said so).
- Seen only in offscreen pictures on macOS (`tools/make_screenshots.py --scheme system6`). - **Card title bars**: the white patch behind the close box is as tall as the one behind the title (each had its own widget's height, and the label is taller than the 14 px arrow, so a stripe showed under the box and the edge stepped). One patch per item, all spanning the tallest. The box itself is still 11 px and sits a half pixel high in its 14 px widget.
- **Markdown** (the Quick Start guide and the update notes): inline code is set in the theme's font at the text's size (`update_dialog.restyle_code_runs`; Markdown marks a code span "monospace" at the document's own point size, which came out bigger), and links are in the text colour, underlined (`apply_theme_to_markdown`, applied once the document is loaded). Not brought over from akaiutil-GUI: equal-height buttons (the font's `…` is taller than its line, which made buttons ending in one taller) and message-box icons; neither has been looked at here.

## What can be done (still to do, roughly in order)

### Phase A: finish the skin inside the window (days, low risk)

- [x] ~~Font decision~~ (done, see above). Still to check: the editor pages fit the 1060 px minimum window width at 16 px (`AGENTS.md`: ~725 px needed). Chicago itself and Monaco are Apple's: don't ship them.
- [ ] **Push buttons as bitmap shapes:** QSS `border-image` with an SVG (system.css's `button.svg`, 30 px slices; `button-default.svg` for the default button's thick ring). Today they are rounded rectangles.
- [x] ~~**Checkboxes and radio buttons:**~~ done (X in a white box).
- [x] (old note) **Checkboxes and radio buttons:** System 6 uses a white box with an X (system.css `checkmark.svg` is a tick); today a black box with a white tick (`QCheckBox::indicator:checked`).
- [~] **Menus:** QMenu / QMenuBar rules exist now (untested on a real Mac: the native menu bar still stays native). Original note: no `QMenu` rule exists in the template (Fusion draws them from the `QPalette`). Add one (black border, hard 1 px edge, inverted hover). On macOS the menu bar stays native unless `menuBar().setNativeMenuBar(False)` is used for this theme (then it is in the window, styleable).
- [x] **Scroll bars:** done (arrow boxes, white thumb). Original note: arrow buttons (`QScrollBar::add-line` / `sub-line` with system.css's `scrollbar-*.svg`); today only the dithered track and a white handle.
- [x] **Cards:** done, title bar and close box (no click-drag; the stripes are painted by `SectionCard.paintEvent`). Original note: `SectionCard` headers as striped title bars (it is custom-painted in `section_card.py`; the chevron and heading would become the System 6 close-box / horizontal-lines pattern).
- [~] **Painters in 1-bit:** knob and envelope graph done (`hard_edges`); the piano keyboard was already unsmoothed. Original note: knob ring and pointer, envelope curve and handles and the piano keyboard still use anti-aliased lines; a hard-edged variant (`painter.setRenderHint(Antialiasing, False)`, 1 px) would look more bitmap.
- [ ] **Dithered desktop and disabled controls:** a 50 % checker `background-image` on the root (the central widget is opaque `${bg}`, so it must become transparent or be painted), and dithered (not grey) disabled text is impossible in QSS: keep grey.
- [x] **Colour-coded states** (2026-10-26, owner allowed a little colour): `warning` orange `#d65a00` (edited, differs from the factory), `critical` red `#dd0907`, `ok` green `#12850b` (the connection pill), `warning_tint` orange at 15 %. Apple's 16-colour palette's hues, darkened to read on white. Nothing else is coloured.
- [~] **Tooltips, progress bar** (progress is a dithered chunk now, tooltips a plain box; not seen on a real screen) (a striped chunk), tab bar and the status bar's top rule.
- [ ] **Pictures:** `@shot` recipes with `scheme="system6"`; a README/guide picture if wanted.
- [ ] **Tests:** the palette key test already covers the required keys; add a render check for any new token and a pixel-regression of dark/light after each template change (render `tools/make_screenshots.py --out DIR` before and after and compare, as was done on 2026-10-22).

### Phase B: the window frame (**DROPPED by the owner, 2026-10-26: native title bars stay**; kept as a record)

Only a **custom, frameless window** can look like System 6: an operating system's own title bar can't be restyled from Qt (macOS traffic lights, the Windows caption and a Linux compositor's decorations are drawn by the OS). Feasible approach, `[guess]` for everything not marked otherwise (nothing here has been tried):

1. **A `ChromeFrame` wrapper** used when the theme is System 6: `Qt.FramelessWindowHint`, a striped title bar (**close box on the left, title centred, zoom box on the right**: System 6 has no minimise button, a windowshade/collapse came in System 7; add one only if the owner wants it), a thin black window border and a **size box in the bottom-right corner** (authentic, and a natural resize handle).
2. **Move and resize** with `QWindow.startSystemMove()` / `startSystemResize(edges)` (Qt >= 5.15; the compositor or OS does the work, which keeps snapping and multi-monitor behaviour closest to native). `[guess]` they work on macOS, Windows, X11 and Wayland for a frameless window; this must be verified on each. They do nothing on the offscreen test platform, so tests can only check the wiring.
3. **Every top-level window needs it:** `MainWindow` plus 15 `QDialog` subclasses (`patch_picker`, `loopback_results_dialog`, `wave_picker`, `unit_dialogs` x4, `patch_collection_dialog`, `update_dialog`, `system_dialog`, `about_dialog`, `firmware_dialog`, `settings_dialog`, `shortcuts_dialog`, `quickstart_dialog`): a shared base class or mixin that wraps the dialog's content in the frame. Modal dialogs keep working (the frame is just a widget tree).
4. **Standard dialogs are the hard part:** 37 static `QMessageBox` calls, 3 `QInputDialog` and 9 `QFileDialog` calls (counted 2026-10-22). `QMessageBox` statics already pass through one seam (`diagnostics_ui.install_dialog_logging` replaces them), so a themed message box could be swapped in there. `QFileDialog` is the OS's own dialog by default and can't be themed; `DontUseNativeDialog` gives Qt's own widget-based dialog, which can be skinned but looks unlike a Mac. Decide: leave the file dialogs native (a visible seam), or reimplement them.
5. **What a frameless window gives up** (each needs a decision or work-around): the OS's window animations and, on macOS, the green full-screen/zoom button, Mission Control behaviour and the traffic lights (the title bar's zoom box would have to emulate maximise), Windows snap layouts / Aero snap (Windows 11's snap flyout needs a native `WM_NCHITTEST` handler, not pure Qt), the window shadow (`[guess]` frameless windows keep a shadow on macOS and lose it on Windows), and some screen-reader and OS window-switcher behaviour (`setWindowTitle` must still be set).
6. **Switching theme at run time** means `setWindowFlag(...)`, which hides and re-shows every window: simplest is "the window frame changes the next time JV Studio starts", like the Middle C setting.

Rough size: a few days for the frame, the base class and the main window, plus per-OS testing (it can't be judged offscreen), plus the standard-dialog decision. It should be **its own unit of work behind its own setting** (e.g. "Use System 6 window frames", off by default), so the in-window skin (Phase A) ships and is useful without it.

## What cannot be done (don't spend time here)

- **Using system.css's CSS** (see the top): no variables, shadows (`box-shadow`: hard 2 px drop shadows would have to be painted or faked with an extra frame), `::before`/`::after` or `calc`.
- **Restyling a native OS title bar, the macOS global menu bar, or native file/colour dialogs** from Qt. Only replacing them (Phase B) or accepting the seam works.
- **A true 1-bit look:** the app's text is anti-aliased and sub-pixel positioned, QSS cannot dither text, and a bitmap font only looks right at integer pixel scales (a Retina 2x display is fine, a fractional scale blurs). Grey is used where a dither would be.
- **Colour meaning without colour:** the other themes encode state in amber/red/green; monochrome needs another channel (see Phase A).
- **Shipping Apple's assets:** the Apple logo (`system.css`'s `icon/apple.svg`) and Apple's fonts. The look is a homage; the project is GPL-3.0 and is "not affiliated with Roland" (About), and should say the same of Apple if the theme ships.

## Gotchas for whoever works on it

- **Tests that switch themes must delete leftover widgets first** (see `_delete_leftover_windows` in `tests/test_system6_theme.py`): an app-wide `setStyleSheet` restyles every widget still alive, earlier tests leave hundreds behind, and a theme test late in the suite once took minutes (the full run hung past 10 minutes) until they were cleared.
- Adding a colour or metric to the template means adding the key to **all three** palettes (`render_stylesheet` raises otherwise); an optional painter key goes in `SYSTEM6_PALETTE` only and is read with `.get`.
- `current_palette()` is what painted widgets must read (never `QPalette`), and `theme.notifier.changed` fires after a switch for widgets that bake a colour in when they are built.
- QSS caches images by path: the generated chevrons and the checker have their content (colour) in the file name for that reason.
- `QT_QPA_PLATFORM=offscreen` shows the in-window menu bar (macOS would show the native one), so offscreen pictures always include a menu bar the real Mac window doesn't have.

## Open questions for the owner (answered 2026-10-26 unless noted)

1. Ship or demo? **Ships** as a theme ("Macintosh System 6"): font licence settled (CC BY), About credits the font and says it is not affiliated with Apple. Still to decide: whether the README or guide shows it.
2. Window frame: **no** (native).
3. File dialogs: **native** (no frame work, so no seam to hide).
4. State colours: **a little colour is allowed** (see Phase A).
