"""What a bug report needs beyond the per-action log lines: crash capture, and a one-line picture of how the app is configured.

An exception raised inside a Qt slot goes to stderr (nowhere, in a packaged app) and a native crash leaves no trace at all, so
`install_crash_handlers()` sends both to the log: Python exceptions to `jv1010editor.log`, native crashes (faulthandler) to `crash.log` beside it.
"""

import faulthandler
import sys
import threading

from . import app_config, debug_log

CRASH_PATH = debug_log.LOG_PATH.parent / "crash.log"
_CRASH_LOG_MAX_BYTES = 100_000

_crash_file = None  # faulthandler needs the file kept open for the whole run


def _log_qt_message(msg_type, _context, message):
    from PySide6.QtCore import QtMsgType

    level = {
        QtMsgType.QtDebugMsg: "debug",
        QtMsgType.QtInfoMsg: "info",
        QtMsgType.QtWarningMsg: "warning",
        QtMsgType.QtCriticalMsg: "error",
        QtMsgType.QtFatalMsg: "critical",
    }.get(msg_type, "warning")
    getattr(debug_log.get_logger(), level)(f"Qt: {message}")


def install_crash_handlers():
    global _crash_file
    log = debug_log.get_logger()

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    def thread_excepthook(args):
        name = args.thread.name if args.thread else "?"
        log.critical(f"Unhandled exception in thread {name!r}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    try:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(_log_qt_message)
    except Exception:
        log.warning("couldn't install the Qt message handler", exc_info=True)
    try:
        previous = CRASH_PATH.read_text(errors="replace") if CRASH_PATH.exists() else ""
        if "Fatal Python error" in previous or "Current thread" in previous:
            log.warning(f"the previous session crashed natively - traceback in {CRASH_PATH}")
        _crash_file = open(CRASH_PATH, "w" if len(previous) > _CRASH_LOG_MAX_BYTES else "a")
        faulthandler.enable(_crash_file, all_threads=True)
    except Exception:
        log.warning("couldn't enable faulthandler", exc_info=True)


def log_session_config(reason):
    log = debug_log.get_logger()
    try:
        input_name, output_name = app_config.get_saved_ports()
        log.info(f"config ({reason}): in={input_name!r} out={output_name!r} theme={app_config.get_saved_theme()}")
    except Exception:
        log.error(f"couldn't read the config for the log ({reason})", exc_info=True)
