"""`jv-studio --smoke-test[=report.txt]`: check that a BUILT app has everything it needs, then exit (0 = fine, 1 = not).

CI runs this against every freshly built app, because a build can succeed and still be missing a data file (the parameter table, the stylesheet, an SVG plugin) or a
compiled module. It never touches the user's settings or a MIDI port: the settings and log go to a scratch folder, and the MIDI backend is only checked for being
there (creating a real rtmidi client on a headless CI machine can abort the process).
"""

import sys
import tempfile
from pathlib import Path

from jv_studio.core import app_config, debug_log


def run(report_path=None):
    lines = []
    failures = 0

    def check(name, fn):
        nonlocal failures
        try:
            lines.append(f"ok    {name}: {fn()}")
        except Exception as e:  # report every problem, not just the first
            failures += 1
            lines.append(f"FAIL  {name}: {e.__class__.__name__}: {e}")

    from PySide6.QtWidgets import QApplication

    original = (app_config.CONFIG_PATH, debug_log.LOG_PATH)
    with tempfile.TemporaryDirectory() as scratch:
        app_config.CONFIG_PATH = Path(scratch) / "config.json"
        debug_log.LOG_PATH = Path(scratch) / "jv-studio.log"
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            app.setApplicationName("JV Studio")
            from jv_studio.ui import theme

            theme.apply_to_app(app)

            def stylesheets():
                for palette in (theme.DARK_PALETTE, theme.LIGHT_PALETTE):
                    theme.render_stylesheet(palette)  # reads style.qss.template and the icons
                return "dark and light render"

            def svg_images():
                # the stylesheet draws checkmarks and combo-box arrows from SVG files; without Qt's SVG support they would silently not appear
                from PySide6.QtGui import QPixmap

                icon = Path(theme._ICONS_DIR) / "checkmark.svg"
                assert icon.is_file(), f"missing {icon}"
                assert not QPixmap(str(icon)).isNull(), "Qt can't load SVG images (is its svg plugin bundled?)"
                return "SVG images load"

            def parameter_table():
                from jv_studio.core import params

                table = params.load_table()
                assert len(table.block("patch_tone").params) == 128 and len(table.efx_types) == 40 and len(table.factory_user_patches) == 128
                return f"{sum(len(b.params) for b in table.blocks.values())} parameters, {len(table.efx_types)} effect types"

            def wave_names():
                from jv_studio.core import waves

                assert len(waves.groups()) == 4 and waves.describe(0, 1, 0) == "INT-A 001  Ac Piano 1A"
                return f"{sum(len(g.names) for g in waves.groups())} wave names"

            def diagrams():
                from jv_studio.ui import settings_dialog  # noqa: F401  (the dialog that shows them)

                folder = Path(settings_dialog.__file__).parent / "help" / "diagrams"
                missing = [n for n in ("midi-jv1010-cable.png", "midi-loopback-cable.png") if not (folder / n).is_file()]
                assert not missing, f"missing {missing} in {folder}"
                return "cabling diagrams present"

            def midi_backend():
                import rtmidi

                apis = rtmidi.get_compiled_api()
                assert apis, "python-rtmidi has no MIDI API compiled in"
                return f"python-rtmidi, {len(apis)} backend(s)"

            def main_window_and_editor():
                from jv_studio.core import patch, performance
                from jv_studio.ui.about_dialog import AboutDialog
                from jv_studio.ui.main_window import MainWindow

                window = MainWindow(start_worker=False)
                window.editor.set_patch(patch.Patch.minimum())
                for index in range(window.editor.tabs.count()):
                    window.editor.tabs.setCurrentIndex(index)  # builds every page: ~600 knobs, combos and graphs
                    app.processEvents()
                window.performance_panel.ensure_editor().set_performance(performance.Performance.minimum())
                for index in range(window.performance_panel.editor.tabs.count()):
                    window.performance_panel.editor.tabs.setCurrentIndex(index)
                    app.processEvents()
                AboutDialog(window)
                window.deleteLater()
                return "main window, the patch and performance editors and About build"

            for name, fn in (
                ("stylesheets", stylesheets),
                ("svg images", svg_images),
                ("parameter table", parameter_table),
                ("wave names", wave_names),
                ("diagrams", diagrams),
                ("midi backend", midi_backend),
                ("windows", main_window_and_editor),
            ):
                check(name, fn)
        finally:
            app_config.CONFIG_PATH, debug_log.LOG_PATH = original

    report = "\n".join(lines) + ("\nSMOKE TEST FAILED" if failures else "\nsmoke test passed")
    if report_path:
        Path(report_path).write_text(report + "\n", encoding="utf-8")
    else:
        print(report)
    return 1 if failures else 0
