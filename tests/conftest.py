import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for fakes

# Forced, not setdefault: a desktop that exports QT_QPA_PLATFORM would otherwise run the tests on a real display.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# No test may touch the user's real ~/.jv-studio (config, log). Redirect them before anything creates the logger.
_TMP = Path(tempfile.mkdtemp(prefix="jv-studio-tests-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

from jv_studio.core import app_config, debug_log, diagnostics  # noqa: E402

debug_log.LOG_PATH = _TMP / "jv-studio.log"
diagnostics.CRASH_PATH = _TMP / "crash.log"
app_config.CONFIG_PATH = _TMP / "config.json"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_config():
    app_config.CONFIG_PATH.unlink(missing_ok=True)
    yield


@pytest.fixture(scope="session", autouse=True)
def _destroy_qt_widgets_before_exit():
    """Windows and editors the tests leave behind (their signal connections keep them alive) are torn down by PySide at interpreter exit, and that order
    segfaults intermittently inside Shiboken's `recursive_invalidate` (exit status 139 AFTER every test passed). Delete them here, while the event loop and the
    interpreter are still whole."""
    yield
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for _ in range(3):
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()
