"""ONE persistent worker thread for everything that talks to the unit, one job at a time (the pattern AKAISDS's BridgeWorker settled on).

Request/reply code must never run twice at once on one connection (interleaved requests and replies corrupt each other), and a thread per action
crashed AKAISDS when a stale thread was garbage-collected mid-call. So: one `QThread` for the window's lifetime, a FIFO of jobs, results as signals.

Reads: "temporary", "user" n (0-based), "names" (the 128 USER patch summaries), "backup" path [sections] (the whole user memory into a .syx).
Writes (each verified by a read-back): "send_temporary" patch, "write_user" n patch (the slot's old contents are saved to `app_config.backups_dir()` FIRST and
the write is abandoned if that fails), "restore" backup sections. `cancel()` stops a names read, a backup or a restore at the next block.
While `is_idle()` is False the window must not open Settings or run a diagnostic: both close the connection the job is using.
"""

import threading
from collections import deque

from PySide6.QtCore import QThread, Signal

from jv1010editor.core import app_config, backup, debug_log, memory, patch, unit, validate


class UnitWorker(QThread):
    patch_read = Signal(str, object, list)  # label ("temporary" or "user:N"), the Patch, its validate.Problems
    names_read = Signal(list)  # [unit.PatchSummary] x 128 (fewer when cancelled)
    backup_done = Signal(str, int)  # path, bytes written
    restore_done = Signal(int)  # blocks written
    write_done = Signal(str, str, str)  # label ("temporary" or "user:N"), the patch name, the path of the automatic backup ("" for temporary)
    cancelled = Signal(str, str)  # job label, what happened
    progress = Signal(int, int)
    failed = Signal(str, str)  # job label, a short message for the user
    busy_changed = Signal(bool)

    def __init__(self, session, parent=None, timeout=unit.DEFAULT_TIMEOUT):
        super().__init__(parent)
        self._session = session
        self._timeout = timeout  # seconds to wait for one reply (tests shorten it)
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._queue = deque()
        self._busy = False
        self._stopped = False
        self._cancel = False

    # -- submitting ------------------------------------------------------------------------------------------------------

    def submit(self, kind, *args):
        with self._wake:
            was_idle = not self._queue and not self._busy
            self._queue.append((kind, *args))
            self._wake.notify_all()
        shown = [a if isinstance(a, (int, str)) else type(a).__name__ for a in args]  # (a Patch or a Backup would fill the log with bytes)
        debug_log.get_logger().debug(f"UnitWorker: queued {kind} {shown!r}")
        if was_idle:
            self.busy_changed.emit(True)

    def cancel(self):
        self._cancel = True

    def is_idle(self):
        with self._lock:
            return not self._queue and not self._busy

    def wait_until_idle(self, timeout=None):
        with self._wake:
            return self._wake.wait_for(lambda: not self._queue and not self._busy, timeout)

    def stop(self):
        """Let what is queued finish, then end the thread (call `wait()` after)."""
        with self._wake:
            self._stopped = True
            self._wake.notify_all()

    # -- running ---------------------------------------------------------------------------------------------------------

    def run(self):
        while True:
            with self._wake:
                while not self._queue and not self._stopped:
                    self._wake.wait()
                if not self._queue and self._stopped:
                    return
                job = self._queue.popleft()
                self._busy = True
            self._safe_dispatch(job)
            with self._wake:
                self._busy = False
                now_idle = not self._queue
                self._wake.notify_all()
            if now_idle:
                self.busy_changed.emit(False)

    def process_pending(self):
        """Run what is queued, here and now (tests: no real thread)."""
        while True:
            with self._wake:
                if not self._queue:
                    return
                job = self._queue.popleft()
                self._busy = True
            self._safe_dispatch(job)
            with self._wake:
                self._busy = False
                now_idle = not self._queue
                self._wake.notify_all()
            if now_idle:
                self.busy_changed.emit(False)

    def _safe_dispatch(self, job):
        # an exception escaping here would kill the thread silently: every later request would queue forever and nothing would ever load
        label = job[0] if job[0] != "user" else f"user:{job[1]}"
        try:
            self._dispatch(job)
        except backup.Cancelled as e:
            debug_log.get_logger().warning(f"UnitWorker: {label} cancelled: {e}")
            self.cancelled.emit(label, str(e))
        except (unit.UnitError, backup.BackupError) as e:
            debug_log.get_logger().warning(f"UnitWorker: {label} failed: {e}")
            self.failed.emit(label, str(e))
        except Exception as e:
            debug_log.get_logger().error(f"UnitWorker: unhandled exception in {job!r}", exc_info=True)
            self.failed.emit(label, f"Unexpected error: {e}")

    def _unit(self):
        connection = self._session.connection
        if connection is None or not connection.is_open:
            raise unit.UnitError("No MIDI ports are open: choose them in Settings.")
        return unit.JV1010Unit(connection, timeout=self._timeout)

    def _dispatch(self, job):
        kind = job[0]
        if kind == "temporary":
            self._finish_patch("temporary", self._unit().read_temporary_patch())
        elif kind == "user":
            self._finish_patch(f"user:{job[1]}", self._unit().read_user_patch(job[1]))
        elif kind == "names":
            self._cancel = False
            self.names_read.emit(self._unit().read_user_patch_summaries(progress=self.progress.emit, cancelled=lambda: self._cancel))
        elif kind == "backup":
            self._backup(job[1], job[2] if len(job) > 2 else memory.SECTIONS)
        elif kind == "restore":
            self._restore(job[1], job[2])
        elif kind == "send_temporary":
            self._unit().write_patch(patch.TEMPORARY_BASE, job[1])
            debug_log.get_logger().info(f"UnitWorker: wrote {job[1].name!r} to the temporary patch (read back identical)")
            self.write_done.emit("temporary", job[1].name, "")
        elif kind == "write_user":
            self._write_user(job[1], job[2])
        else:
            raise ValueError(f"unknown job {kind!r}")

    def _backup(self, path, sections):
        self._cancel = False
        unit_ = self._unit()
        saved = backup.read_backup(unit_, sections, progress=self.progress.emit, cancelled=lambda: self._cancel)
        data = saved.to_syx(sections)
        try:
            backup.write_file(path, data)
        except OSError as e:
            raise unit.UnitError(f"Couldn't save the backup: {e}") from e
        debug_log.get_logger().info(f"UnitWorker: backup of {', '.join(sections)} saved to {path} ({len(data)} bytes)")
        self.backup_done.emit(str(path), len(data))

    def _restore(self, saved, sections):
        self._cancel = False
        log = debug_log.get_logger()
        log.warning(f"UnitWorker: restoring {', '.join(sections)} to the unit")
        count = backup.restore(self._unit(), saved, sections, progress=self.progress.emit, cancelled=lambda: self._cancel)
        log.info(f"UnitWorker: restore wrote and verified {count} blocks")
        self.restore_done.emit(count)

    def _write_user(self, number, new):
        """Save what USER:number holds now, then replace it. Without that backup on disk, nothing is written."""
        log = debug_log.get_logger()
        unit_ = self._unit()
        old = unit_.read_user_patch(number)
        path = backup.user_patch_backup_path(app_config.backups_dir(), number)
        try:
            backup.write_file(path, old.to_syx(patch.user_base(number)))
        except OSError as e:
            log.error(f"UnitWorker: couldn't back up USER:{number + 1:03d} to {path}", exc_info=True)
            raise unit.UnitError(f"Couldn't save a backup of USER:{number + 1:03d} first ({e}); nothing was written.") from e
        log.warning(f"UnitWorker: overwriting USER:{number + 1:03d} {old.name!r} with {new.name!r} (backup {path})")
        unit_.write_patch(patch.user_base(number), new)
        log.info(f"UnitWorker: USER:{number + 1:03d} written and read back identical")
        self.write_done.emit(f"user:{number}", new.name, str(path))

    def _finish_patch(self, label, read):
        problems = validate.out_of_range(read)
        log = debug_log.get_logger()
        log.info(f"UnitWorker: read {label} patch {read.name!r}: {len(problems)} value(s) outside the table's ranges")
        for problem in problems[:40]:
            log.warning(f"UnitWorker: {label}: {problem}")  # a real unit disagreeing with the manual-derived table: worth reading
        self.patch_read.emit(label, read, problems)
