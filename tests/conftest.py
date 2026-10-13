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
