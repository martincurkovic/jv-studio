# Macintosh System 6 theme: status and roadmap

A monochrome skin that makes JV Studio look like a Macintosh System 6 application. Started 2026-10-22 as a **demo** (owner: "ideally monochrome just for this demo"); the owner would eventually like the **window frame** (close / zoom buttons, title bar) themed too.
This file says what exists, what can and cannot be done, and what is still undecided, so the next agent doesn't re-research it. The short version of the code facts is also in `AGENTS.md` ("Macintosh System 6 skin").

Reference: <https://github.com/sakofchit/system.css> (MIT; a CSS library, System 6 look, last pushed 2023-11). **Nothing of its CSS can be used directly**: Qt style sheets (QSS) are a small CSS-2-like subset (no variables, no `box-shadow`, no real `::before`/`::after`, no `calc`). It is a visual reference and a source of SVG shapes (`icon/button.svg`, `checkmark.svg`, scroll bar arrows, `select-button.svg`), not code.

## Try it

- `uv run jv-studio --demo --theme=system6` (this run only, nothing saved; demo mode blocks Settings, which is why the flag exists), or Settings > Appearance > Theme > "Macintosh System 6 (monochrome)" with ports open.
- The bitmap-style font is NOT in the repo: `uv run --with fonttools python tools/fetch_system6_font.py` (see "Font" below). Without it the theme falls back to Geneva / Monaco / monospace and still works.
- Pictures for review: `@shot(..., scheme="system6")` recipes in `tools/screenshot_recipes.py` (the `scheme` argument is the theme name; none exist yet, and the guide's pictures are dark-theme only).

## What exists (done, 2026-10-22, tests in `tests/test_system6_theme.py`)

- A third palette, `theme.SYSTEM6_PALETTE`, selected by `app_config.THEME_SYSTEM6` (`"system6"`), offered in `theme.CHOICES`. Black, white and one grey (disabled text and borders, knob track, list row separators); selection and checked buttons are inverted video; square corners except push buttons (6 px).
- **Template tokens:** corner radii, font size/weight, pressed/selected text colours and scroll bar fills were hard-coded in `style.qss.template`; they are now palette values (`radius`, `radius_small`, `radius_button`, `radius_pill`, `font_size`, `font_size_small`, `font_weight_bold`, `text_pressed`, `text_selected`, `text_tab_selected`, `scroll_track`, `scroll_handle`, `scroll_handle_border`, `logo_rule`), so all three palettes fill the same template and **dark/light are pixel-identical to before** (checked against the committed guide screenshots). A missing key still raises at start-up.
- **Optional keys only this skin has:** `font_family`, `scroll_track_pattern` (a generated 2 x 2 checker PNG in `~/.jv-studio/generated_icons`, for a dithered scroll track), `knob_track`, `knob_arc`, `graph_line`. The painters (`knob.py`, `envelope_graph.py`) read them with `.get(...)`, so the other themes are untouched.
- **Qt's own widgets** that QSS does not draw (slider groove, native menu highlight) take their colours from the application `QPalette`: `theme._apply_qt_palette` sets a black/white one while System 6 is active and restores Qt's own when leaving (only if System 6 had replaced it).
- The ASCII logo keeps its monospace font whatever the theme says (`QLabel#asciiLogo`, `logo_rule`): the theme's font family would otherwise garble the art.
- `--theme=NAME` command-line flag (`main.theme_from_argv`).

## What can be done (still to do, roughly in order)

### Phase A: finish the skin inside the window (days, low risk)

- [ ] **Font decision** (blocks bundling): ChiKareGo2 (Giles Booth's Chicago 12 recreation) has no licence in the file or in system.css's repo. Confirm the licence or choose another font, then add `ui/fonts` to `DATA_ARGS` in the three `scripts/build_*` and un-ignore it. Chicago itself and Monaco are Apple's: don't ship them. The skin looks best at 16 px with this font; check the editor pages still fit the 1060 px minimum window width (`AGENTS.md`: the editor pages need ~725 px).
- [ ] **Push buttons as bitmap shapes:** QSS `border-image` with an SVG (system.css's `button.svg`, 30 px slices; `button-default.svg` for the default button's thick ring). Today they are rounded rectangles.
- [ ] **Checkboxes and radio buttons:** System 6 uses a white box with an X (system.css `checkmark.svg` is a tick); today a black box with a white tick (`QCheckBox::indicator:checked`).
- [ ] **Menus:** no `QMenu` rule exists in the template (Fusion draws them from the `QPalette`). Add one (black border, hard 1 px edge, inverted hover). On macOS the menu bar stays native unless `menuBar().setNativeMenuBar(False)` is used for this theme (then it is in the window, styleable).
- [ ] **Scroll bars:** arrow buttons (`QScrollBar::add-line` / `sub-line` with system.css's `scrollbar-*.svg`); today only the dithered track and a white handle.
- [ ] **Cards:** `SectionCard` headers as striped title bars (it is custom-painted in `section_card.py`; the chevron and heading would become the System 6 close-box / horizontal-lines pattern).
- [ ] **Painters in 1-bit:** knob ring and pointer, envelope curve and handles and the piano keyboard still use anti-aliased lines; a hard-edged variant (`painter.setRenderHint(Antialiasing, False)`, 1 px) would look more bitmap.
- [ ] **Dithered desktop and disabled controls:** a 50 % checker `background-image` on the root (the central widget is opaque `${bg}`, so it must become transparent or be painted), and dithered (not grey) disabled text is impossible in QSS: keep grey.
- [ ] **Colour-coded states:** amber "edited", red errors and green "connected" have no colour here. Decide how each reads in monochrome (an icon, a prefix such as `*`, bold, inverted).
- [ ] **Tooltips, progress bar** (a striped chunk), tab bar and the status bar's top rule.
- [ ] **Pictures:** `@shot` recipes with `scheme="system6"`; a README/guide picture if wanted.
- [ ] **Tests:** the palette key test already covers the required keys; add a render check for any new token and a pixel-regression of dark/light after each template change (render `tools/make_screenshots.py --out DIR` before and after and compare, as was done on 2026-10-22).

### Phase B: the window frame (the owner's eventual goal: **possible, with real costs**)

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

## Open questions for the owner

1. Is the monochrome look going to ship (then: font licence, the other themes' screenshots, an About line), or stay a demo?
2. Window frame: close + zoom only (authentic), or add a minimise box? Frameless on all three platforms, or macOS first?
3. File dialogs: native (a seam) or reimplemented?
4. Does "edited / error / connected" stay colourless, or is a little colour allowed as an exception to "monochrome"?
