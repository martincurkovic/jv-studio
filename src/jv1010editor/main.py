import platform
import sys

from PySide6.QtWidgets import QApplication

from jv1010editor.core import debug_log, diagnostics, midi
from jv1010editor.ui import diagnostics_ui, theme
from jv1010editor.ui._version import APP_VERSION
from jv1010editor.ui.main_window import MainWindow


def _log_startup():
    """The first lines of every session: version, OS, Python, Qt and the MIDI ports the system offers (the context a bug report's log needs)."""
    log = debug_log.get_logger()
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        log.info(f"=== JV-1010 Editor {APP_VERSION} on {platform.platform()}, python {platform.python_version()}")
        log.info(f"PySide6 {PySide6.__version__}, Qt {qVersion()}")
        log.info(f"MIDI inputs: {midi.list_input_names()}")
        log.info(f"MIDI outputs: {midi.list_output_names()}")
    except Exception:
        log.error("startup: couldn't enumerate the MIDI ports", exc_info=True)
    diagnostics.log_session_config("startup")


def main():
    diagnostics.install_crash_handlers()
    _log_startup()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("JV-1010 Editor")
    diagnostics_ui.install_dialog_logging()
    theme.apply_to_app(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
