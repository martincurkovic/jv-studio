# The real startup path (main.main), with the MIDI backend stubbed and the event loop not entered.

from PySide6.QtWidgets import QApplication

from jv_studio import main as app_main
from jv_studio.core import midi


def test_main_builds_and_shows_the_window_without_touching_real_midi(monkeypatch):
    monkeypatch.setattr(midi, "list_input_names", lambda: [])
    monkeypatch.setattr(midi, "list_output_names", lambda: [])
    shown = []
    monkeypatch.setattr(QApplication, "exec", lambda self=None: shown.append(True) or 0)
    # these two patch process-wide state (sys.excepthook, QMessageBox's static methods) for the rest of the run
    monkeypatch.setattr(app_main.diagnostics, "install_crash_handlers", lambda: None)
    monkeypatch.setattr(app_main.diagnostics_ui, "install_dialog_logging", lambda: None)
    # a real MainWindow would start its worker thread, which nothing in a test stops
    real = app_main.MainWindow
    monkeypatch.setattr(app_main, "MainWindow", lambda **kw: real(start_worker=False, **kw))
    assert app_main.main() == 0 and shown
    assert QApplication.instance().applicationName() == "JV Studio"
