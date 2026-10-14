"""Regenerate the README's pictures (docs/screenshots/) from the simulated JV-1010: offscreen, at twice their on-screen size, dark and light.

    uv run python tools/make_screenshots.py [--out DIR] [--only NAME]

Nothing real is touched: the settings and log go to a scratch folder and the app talks to the demo unit (`jv-studio --demo`), so it needs no MIDI port and no hardware.
Pictures: patch-editor-{dark,light}.png (a tone's filter and envelopes) and performance-{dark,light}.png (the 16-part mixer).
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")  # a 2x picture, like a Retina screenshot
os.environ["JV_STUDIO_DEMO_INSTANT"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jv_studio.core import app_config, debug_log  # noqa: E402

SIZE = (1260, 900)


def _settle(app, rounds=4):
    for _ in range(rounds):
        app.processEvents()


def _scroll_to_card(editor_page, title):
    """Scroll an editor page so the card called `title` is at the top."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea

    from jv_studio.ui.section_card import SectionCard

    area = editor_page if isinstance(editor_page, QScrollArea) else editor_page.findChild(QScrollArea)
    card = next(c for c in area.widget().findChildren(SectionCard) if c.title() == title)
    area.verticalScrollBar().setValue(max(0, card.mapTo(area.widget(), QPoint(0, 0)).y() - 12))


def make(window, app, which):
    window.read_names()
    window.worker.process_pending()
    if which == "patch-editor":
        window.mode_tabs.setCurrentIndex(0)
        window.read_temporary()
        window.worker.process_pending()
        window.editor.tabs.setCurrentIndex(1)  # Tone 1
        _settle(app)
        _scroll_to_card(window.editor.tabs.currentWidget(), "Filter")
    else:
        window.mode_tabs.setCurrentIndex(1)
        window.read_names()
        window.worker.process_pending()
        window.read_temporary()
        window.worker.process_pending()
        window.performance_panel.editor.tabs.setCurrentIndex(0)  # Parts
    _settle(app)
    return window.grab()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    parser.add_argument("--only", help="make just this picture, e.g. patch-editor-dark")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    scratch = Path(tempfile.mkdtemp(prefix="jv-studio-shots-"))
    app_config.CONFIG_PATH = scratch / "config.json"
    debug_log.LOG_PATH = scratch / "jv-studio.log"

    from PySide6.QtWidgets import QApplication

    from jv_studio.ui import demo, theme
    from jv_studio.ui.main_window import MainWindow
    from jv_studio.ui.unit_worker import UnitWorker

    app = QApplication([])
    app.setApplicationName("JV Studio")
    wanted = [(w, t) for w in ("patch-editor", "performance") for t in ("dark", "light") if not args.only or args.only == f"{w}-{t}"]
    if not wanted:
        sys.exit(f"unknown picture {args.only!r}")
    for which, preference in wanted:
        theme.apply_to_app(app, preference)
        session, _unit = demo.build_demo(0, use_backup=False)  # (the pictures are committed: always the built-in contents, never someone's own backup)
        window = MainWindow(session=session, worker=UnitWorker(session, timeout=0.5), start_worker=False, demo=True)
        window.resize(*SIZE)
        window.show()
        _settle(app)
        image = make(window, app, which)
        target = out / f"{which}-{preference}.png"
        image.save(str(target))
        print(f"wrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target} ({image.width()}x{image.height()})")
        window.close()
        window.deleteLater()
        _settle(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
