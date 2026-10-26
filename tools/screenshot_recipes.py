"""The pictures `tools/make_screenshots.py` knows how to make: one `@shot` recipe each, run offscreen against the simulated JV-1010.

A recipe gets a `Context`, builds and shows whatever its picture needs and returns the widget to photograph. `folder` says where the
picture goes: "readme" = docs/screenshots (the README), "guide" = src/jv_studio/ui/help/screenshots (Help > Quick Start Guide, which
ships inside the app). Every picture `quickstart.md` mentions must have a recipe here (`tests/test_make_screenshots.py` checks).
"""

from dataclasses import dataclass
from pathlib import Path

SHOTS: dict[str, "Shot"] = {}
SIZE = (1260, 900)  # the main window, a little taller than its default so the audition bar and a full card fit


@dataclass
class Shot:
    name: str
    description: str
    recipe: callable
    scheme: str  # "dark", "light" or "system6": the theme the app is in while it is built and photographed
    folder: str  # "readme" or "guide"


def shot(name: str, description: str, scheme: str = "dark", folder: str = "guide"):
    def register(fn):
        SHOTS[name] = Shot(name, description, fn, scheme, folder)
        return fn

    return register


class Context:
    """What a recipe is given: the QApplication and helpers for building the window and waiting."""

    def __init__(self, app, scheme):
        self.app = app
        self.scheme = scheme
        self._cleanups = []

    def settle(self, rounds=4):
        for _ in range(rounds):
            self.app.processEvents()

    def window(self, size=SIZE):
        """A MainWindow on a fresh demo unit (the built-in contents, never someone's own backup), shown, with the USER names read."""
        from jv_studio.ui import demo
        from jv_studio.ui.main_window import MainWindow
        from jv_studio.ui.unit_worker import UnitWorker

        session, _unit = demo.build_demo(0, use_backup=False)
        window = MainWindow(session=session, worker=UnitWorker(session, timeout=0.5), start_worker=False, demo=True)
        window.resize(*size)
        window.show()
        self.settle()
        window.read_names()
        window.worker.process_pending()
        self.on_cleanup(window.close)
        self.settle()
        return window

    def on_cleanup(self, fn):
        self._cleanups.append(fn)

    def cleanup(self):
        for fn in reversed(self._cleanups):
            try:
                fn()
            except Exception as e:  # tidying up must not hide the picture's own result
                print(f"  (cleanup problem: {e})")
        self._cleanups.clear()
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.settle()


def scroll_to_card(editor_page, title):
    """Scroll an editor page so the card called `title` is at the top."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea

    from jv_studio.ui.section_card import SectionCard

    area = editor_page if isinstance(editor_page, QScrollArea) else editor_page.findChild(QScrollArea)
    card = next(c for c in area.widget().findChildren(SectionCard) if c.title() == title)
    area.verticalScrollBar().setValue(max(0, card.mapTo(area.widget(), QPoint(0, 0)).y() - 12))


def _patch_tone_filter(ctx):
    window = ctx.window()
    window.mode_tabs.setCurrentIndex(0)
    window.read_temporary()
    window.worker.process_pending()
    window.editor.tabs.setCurrentIndex(1)  # Tone 1
    ctx.settle()
    scroll_to_card(window.editor.tabs.currentWidget(), "Filter")
    ctx.settle()
    return window


def _performance_parts(ctx):
    window = ctx.window()
    window.mode_tabs.setCurrentIndex(1)
    window.read_names()
    window.worker.process_pending()
    window.read_temporary()
    window.worker.process_pending()
    window.performance_panel.editor.tabs.setCurrentIndex(0)  # Parts
    ctx.settle()
    return window


# -- the README's pictures (docs/screenshots) --------------------------------------------------------------------------------


@shot("patch-editor-dark", "README: a tone's filter and envelopes", "dark", "readme")
def _readme_patch_dark(ctx):
    return _patch_tone_filter(ctx)


@shot("patch-editor-light", "README: a tone's filter and envelopes", "light", "readme")
def _readme_patch_light(ctx):
    return _patch_tone_filter(ctx)


@shot("performance-dark", "README: the 16-part mixer", "dark", "readme")
def _readme_performance_dark(ctx):
    return _performance_parts(ctx)


@shot("performance-light", "README: the 16-part mixer", "light", "readme")
def _readme_performance_light(ctx):
    return _performance_parts(ctx)


@shot("patch-editor-system6", "README: the same tone page in the Macintosh System 6 theme", "system6", "readme")
def _readme_patch_system6(ctx):
    return _patch_tone_filter(ctx)


# -- the user guide's pictures (src/jv_studio/ui/help/screenshots) -------------------------------------------------------------


def _patches_window(ctx, tab=None):
    window = ctx.window()
    window.mode_tabs.setCurrentIndex(0)
    window.read_temporary()
    window.worker.process_pending()
    if tab is not None:
        window.editor.tabs.setCurrentIndex(tab)
    ctx.settle()
    return window


@shot("main-window-dark", "the whole window on the Patches side, Common tab", "dark")
def _main_window_dark(ctx):
    return _patches_window(ctx, 0)


@shot("main-window-light", "the same window in the light theme", "light")
def _main_window_light(ctx):
    return _patches_window(ctx, 0)


@shot("main-window-system6", "the same window in the Macintosh System 6 theme", "system6")
def _main_window_system6(ctx):
    return _patches_window(ctx, 0)


@shot("editor-tone-page", "a tone's page: wave, pitch, filter and level with their envelopes", "dark")
def _editor_tone_page(ctx):
    return _patches_window(ctx, 1)


@shot("editor-filter-card", "a tone's Filter card, scrolled into view", "dark")
def _editor_filter_card(ctx):
    return _patch_tone_filter(ctx)


@shot("wave-picker", "Choose Wave: a wave group and its named waves", "dark")
def _wave_picker(ctx):
    from jv_studio.ui.wave_picker import WavePickerDialog

    dialog = WavePickerDialog(0, 1, 9)
    ctx.on_cleanup(dialog.close)
    dialog.resize(380, 520)
    dialog.show()
    ctx.settle()
    return dialog


@shot("patch-picker", "Choose Patch: how a performance part picks its patch", "dark")
def _patch_picker(ctx):
    from jv_studio.ui.patch_picker import PatchPickerDialog

    window = ctx.window()
    names = [s.name for s in window._summaries]
    dialog = PatchPickerDialog(0, 1, 4, names)
    ctx.on_cleanup(dialog.close)
    dialog.resize(420, 540)
    dialog.show()
    ctx.settle()
    return dialog


@shot("write-to-user-dialog", "Write to USER: the slot, and the backup made first", "dark")
def _write_user_dialog(ctx):
    from jv_studio.ui.unit_dialogs import WriteUserDialog

    window = ctx.window()
    names = [s.name for s in window._summaries]
    # (the real folder, written the way the guide writes it: the scratch folder's temp path would end up in the picture)
    dialog = WriteUserDialog("My New Pad", names, 4, "~/.jv-studio/backups")
    ctx.on_cleanup(dialog.close)
    dialog.show()
    ctx.settle()
    dialog.resize(dialog.width(), dialog.layout().totalHeightForWidth(dialog.width()))  # (the wrapped note's height is only known once the dialog has its width)
    ctx.settle()
    return dialog


@shot("audition-keyboard", "the audition keyboard open along the bottom", "dark")
def _audition_keyboard(ctx):
    window = _patches_window(ctx, 0)
    window.audition.set_open(True)
    ctx.settle()
    return window


@shot("performance-parts", "Performances: the Parts mixer", "dark")
def _performance_parts_guide(ctx):
    return _performance_parts(ctx)


@shot("performance-part-page", "Performances: one part in full", "dark")
def _performance_part_page(ctx):
    window = _performance_parts(ctx)
    window.performance_panel.editor.tabs.setCurrentIndex(1)  # Part
    ctx.settle()
    return window


@shot("rhythm-set", "Rhythm Sets: the keyboard of keys and the chosen key's cards", "dark")
def _rhythm_set(ctx):
    window = ctx.window()
    window.mode_tabs.setCurrentIndex(2)
    window.read_names()
    window.worker.process_pending()
    window.read_temporary()
    window.worker.process_pending()
    ctx.settle()
    return window


def _system_dialog(ctx, tab):
    window = ctx.window()
    window.open_system_settings()
    window.worker.process_pending()
    ctx.settle()
    dialog = window.system_dialog
    dialog.tabs.setCurrentIndex(tab)
    ctx.settle()
    return dialog


@shot("system-settings", "Hardware > System Settings: the unit's global settings", "dark")
def _system_settings(ctx):
    return _system_dialog(ctx, 0)


@shot("scale-tune", "System Settings > Scale Tune: the 12 notes' tuning", "dark")
def _scale_tune(ctx):
    return _system_dialog(ctx, 1)
