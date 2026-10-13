"""The app-wide log file: `~/.jv1010editor/jv1010editor.log` (8 MB x 3, DEBUG).

A packaged GUI app has no console, so this rotating file is the only place a bug report can come from. Ask for it (and `crash.log`
beside it) before guessing at a hardware problem. One INFO line per user action is the convention; MIDI traffic is DEBUG.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_PATH = Path.home() / ".jv1010editor" / "jv1010editor.log"

_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("jv1010editor")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=8_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    except OSError as e:
        # logging must never be why the app fails to start
        logger.addHandler(logging.NullHandler())
        print(f"[WARN] Couldn't open the log at {LOG_PATH}: {e}")
    _logger = logger
    return logger
