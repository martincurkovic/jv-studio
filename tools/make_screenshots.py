"""Regenerate the README's pictures (docs/screenshots/) and the user guide's (src/jv_studio/ui/help/screenshots/) from the simulated JV-1010: offscreen, at twice their on-screen size.

    uv run python tools/make_screenshots.py                        # make the pictures that don't exist yet
    uv run python tools/make_screenshots.py --list                 # every picture, where it goes and whether it exists
    uv run python tools/make_screenshots.py --only NAME [NAME...]  # just these (with or without .png)
    uv run python tools/make_screenshots.py --overwrite            # redo every one
    uv run python tools/make_screenshots.py --out DIR              # somewhere else (then nothing is "skipped")
    uv run python tools/make_screenshots.py --out DIR --scheme system6   # the same pictures in another theme, to look at it

Nothing real is touched: the settings and log go to a scratch folder and the app talks to the demo unit (`jv-studio --demo`, built-in
contents, never `~/.jv-studio/demo-backup.syx`), so it needs no MIDI port and no hardware. An existing picture is only replaced with --overwrite.
Pictures are window CONTENTS (no title bar), 2x, which is what ui/quickstart_dialog.py's _SCREENSHOT_PIXEL_RATIO expects.
Adding one: write a `@shot` function in tools/screenshot_recipes.py; `tests/test_make_screenshots.py` checks every picture quickstart.md mentions has one.
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"  # a 2x picture, like a Retina screenshot
os.environ["JV_STUDIO_DEMO_INSTANT"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
FOLDERS = {"readme": ROOT / "docs" / "screenshots", "guide": ROOT / "src" / "jv_studio" / "ui" / "help" / "screenshots"}

# The real ~/.jv-studio stays out of it: set before anything opens the log or reads the config.
_SCRATCH = Path(tempfile.mkdtemp(prefix="jv-studio-shots-"))

from jv_studio.core import app_config, debug_log  # noqa: E402

app_config.CONFIG_PATH = _SCRATCH / "config.json"
debug_log.LOG_PATH = _SCRATCH / "jv-studio.log"

import screenshot_recipes as recipes  # noqa: E402


def run(names, folder_for, overwrite, scheme=None):
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    from jv_studio.ui import theme

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("JV Studio")
    made = skipped = failed = 0
    for name in names:
        s = recipes.SHOTS[name]
        folder = folder_for(s)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{name}.png"
        if target.exists() and not overwrite:
            print(f"skip  {name}.png (exists; --overwrite to replace)")
            skipped += 1
            continue
        theme.apply_to_app(app, scheme or s.scheme)
        ctx = recipes.Context(app, scheme or s.scheme)
        try:
            result = s.recipe(ctx)
            pixmap = result if isinstance(result, QPixmap) else result.grab()
            if pixmap.isNull() or pixmap.width() < 20:
                raise RuntimeError("the window came out empty")
            pixmap.save(str(target))
            print(f"saved {name}.png  {pixmap.width()}x{pixmap.height()}  ->  {folder}")
            made += 1
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"FAIL  {name}: {e}")
            failed += 1
        finally:
            ctx.cleanup()
    print(f"\n{made} saved, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="NAME", help="just these pictures (names as in --list, with or without .png)")
    parser.add_argument("--overwrite", action="store_true", help="replace pictures that already exist (default: leave them)")
    parser.add_argument("--out", type=Path, help="write everything here instead of the README and guide folders")
    parser.add_argument("--scheme", help="photograph every picture in this theme (dark, light, system6) instead of the recipe's own: for looking at a theme, use with --out")
    parser.add_argument("--list", action="store_true", help="list the pictures and whether each exists, then stop")
    args = parser.parse_args(argv)

    def folder_for(s):
        return args.out or FOLDERS[s.folder]

    if args.list:
        for name, s in recipes.SHOTS.items():
            mark = "exists" if (folder_for(s) / f"{name}.png").exists() else "missing"
            print(f"{name:28} {s.folder:7} {mark:8} {s.description}")
        return 0
    names = list(recipes.SHOTS)
    if args.only:
        wanted = [n.removesuffix(".png") for n in args.only]
        unknown = [n for n in wanted if n not in recipes.SHOTS]
        if unknown:
            print("unknown picture(s):", ", ".join(unknown), "\nknown:", ", ".join(recipes.SHOTS))
            return 2
        names = wanted
    try:
        return run(names, folder_for, args.overwrite, args.scheme)
    finally:
        shutil.rmtree(_SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
