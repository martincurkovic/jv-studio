import platform
import sys

from PySide6.QtWidgets import QApplication

from jv_studio.core import debug_log, diagnostics, midi
from jv_studio.ui import demo as demo_mode
from jv_studio.ui import diagnostics_ui, theme
from jv_studio.ui._version import APP_VERSION
from jv_studio.ui.main_window import MainWindow


def _log_startup():
    """The first lines of every session: version, OS, Python, Qt and the MIDI ports the system offers (the context a bug report's log needs)."""
    log = debug_log.get_logger()
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        log.info(f"=== JV Studio {APP_VERSION} on {platform.platform()}, python {platform.python_version()}")
        log.info(f"PySide6 {PySide6.__version__}, Qt {qVersion()}")
        log.info(f"MIDI inputs: {midi.list_input_names()}")
        log.info(f"MIDI outputs: {midi.list_output_names()}")
    except Exception:
        log.error("startup: couldn't enumerate the MIDI ports", exc_info=True)
    diagnostics.log_session_config("startup")


def main(argv=None):
    argv = sys.argv if argv is None else argv
    smoke = next((a for a in argv[1:] if a == "--smoke-test" or a.startswith("--smoke-test=")), None)
    if smoke is not None:  # before anything touches the user's settings, the log or a MIDI port
        from jv_studio import smoke_test

        return smoke_test.run(smoke.partition("=")[2] or None)
    diagnostics.install_crash_handlers()
    demo = demo_mode.wanted(argv)
    if demo:
        debug_log.get_logger().info("=== demo mode: a simulated JV-1010, no MIDI ports")
    else:
        _log_startup()  # (lists the real MIDI ports: not in demo mode, which never touches them)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("JV Studio")
    diagnostics_ui.install_dialog_logging()
    theme.apply_to_app(app)
    if demo:
        session, _unit = demo_mode.build_demo()
        window = MainWindow(session=session, demo=True, autoload=True)
    else:
        window = MainWindow(autoload=True)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
