"""MIDI I/O over python-rtmidi (Qt-free): list the ports, and one connection that sends and receives whole SysEx messages.

`MidiConnection` is what request/reply code uses: `send()` writes a complete F0..F7 message, incoming SysEx is collected into a queue
(reassembled if the backend splits a long message), and `request()` sends one message and returns the first reply that matches, ignoring
anything else. Other MIDI (notes, clock, active sensing) is dropped: this app only talks SysEx.

Two lessons from AKAISDS that are built in:
- `close()` takes the same lock `send()` does. Deleting the native rtmidi port while another thread is inside `send_message` crashed AKAISDS (SIGSEGV).
- A failed port LISTING (macOS CoreMIDI sometimes refuses a new client right after a relaunch) logs and returns "no ports" instead of raising.
"""

import queue
import threading
import time

import rtmidi

from . import debug_log

SOX = 0xF0
EOX = 0xF7
_QUEUE_LIMIT = 8192  # incoming messages kept; a stalled consumer must not grow without bound


def _delete_quiet(port):
    # some backends need an explicit delete() (ALSA runs out of client slots otherwise); failing to is never worth raising over
    try:
        port.delete()
    except Exception:
        pass


def list_input_names():
    try:
        port = rtmidi.MidiIn()
    except Exception:
        debug_log.get_logger().error("midi: couldn't create a MidiIn to list the ports", exc_info=True)
        return []
    try:
        return port.get_ports()
    finally:
        _delete_quiet(port)


def list_output_names():
    try:
        port = rtmidi.MidiOut()
    except Exception:
        debug_log.get_logger().error("midi: couldn't create a MidiOut to list the ports", exc_info=True)
        return []
    try:
        return port.get_ports()
    finally:
        _delete_quiet(port)


def _default_input_factory(name):
    port = rtmidi.MidiIn(queue_size_limit=_QUEUE_LIMIT)
    names = port.get_ports()
    if name not in names:
        _delete_quiet(port)
        raise RuntimeError(f"no MIDI input named {name!r}; have {names}")
    port.open_port(names.index(name))
    port.ignore_types(sysex=False, timing=True, active_sense=True)
    return port


def _default_output_factory(name):
    port = rtmidi.MidiOut()
    names = port.get_ports()
    if name not in names:
        _delete_quiet(port)
        raise RuntimeError(f"no MIDI output named {name!r}; have {names}")
    port.open_port(names.index(name))
    return port


class _Trace:
    """Bounded DEBUG log of the SysEx on the wire: the first 16 bytes and the length, never the payload, at most `limit` lines per `window` seconds."""

    def __init__(self, logger, limit=300, window=10.0):
        self._logger, self._limit, self._window = logger, limit, window
        self._start, self._count, self._skipped = 0.0, 0, 0

    def __call__(self, direction, data):
        now = time.monotonic()
        if now - self._start > self._window:
            if self._skipped:
                self._logger.debug(f"midi: ... {self._skipped} more message(s) not logged")
            self._start, self._count, self._skipped = now, 0, 0
        if self._count >= self._limit:
            self._skipped += 1
            return
        self._count += 1
        self._logger.debug(f"midi {direction}: {bytes(data[:16]).hex(' ')}{' ...' if len(data) > 16 else ''} ({len(data)} bytes)")


class MidiConnection:
    """An open input and output port pair. Thread-safe: any thread may `send()`; the rtmidi callback thread fills the receive queue."""

    def __init__(self, input_name, output_name, *, input_factory=_default_input_factory, output_factory=_default_output_factory):
        self.input_name, self.output_name = input_name, output_name
        self._log = debug_log.get_logger()
        self._trace = _Trace(self._log)
        self._lock = threading.Lock()  # guards the ports: send() vs close() (see the module docstring)
        self._queue = queue.Queue(maxsize=_QUEUE_LIMIT)
        self._partial = None  # a SysEx message split across callbacks, being reassembled
        self._input = self._output = None
        try:
            self._output = output_factory(output_name)
            self._input = input_factory(input_name)
            self._input.set_callback(self._on_event)
        except Exception:
            self.close()
            raise
        self._log.info(f"midi: opened input {input_name!r} and output {output_name!r}")

    # -- receiving -------------------------------------------------------------------------------------------------------

    def _on_event(self, event, _data=None):
        message, _delta = event
        if not message:
            return
        if message[0] == SOX:
            self._partial = list(message)
        elif self._partial is not None and message[0] < 0x80:
            self._partial.extend(message)  # the continuation of a split SysEx
        else:
            return  # not SysEx (or a stray fragment): this app only talks SysEx
        if self._partial[-1] == EOX:
            complete = bytes(self._partial)
            self._partial = None
            self._trace("in ", complete)
            try:
                self._queue.put_nowait(complete)
            except queue.Full:
                self._log.warning("midi: the receive queue is full - dropping a message")

    def drain(self):
        """Throw away anything waiting (before a request, so a stale reply is not taken for the answer)."""
        dropped = 0
        while True:
            try:
                self._queue.get_nowait()
                dropped += 1
            except queue.Empty:
                return dropped

    def receive(self, timeout=0.0, pump=None):
        """The next incoming SysEx message, or None after `timeout` seconds. `pump` (e.g. `QApplication.processEvents`) is called while waiting."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self._queue.get(timeout=min(0.005, max(deadline - time.monotonic(), 0)))
            except queue.Empty:
                pass
            if pump is not None:
                pump()
            if time.monotonic() >= deadline:
                return None

    # -- sending ---------------------------------------------------------------------------------------------------------

    def send(self, message):
        message = bytes(message)
        with self._lock:
            if self._output is None:
                raise RuntimeError("the MIDI output is closed")
            self._trace("out", message)
            self._output.send_message(list(message))

    def request(self, message, accept, timeout, pump=None):
        """Send `message`; return the first reply for which `accept(reply_bytes)` is true, or None on timeout. Other messages are ignored.
        One request outstanding at a time: callers must not overlap requests on one connection."""
        self.drain()
        self.send(message)
        deadline = time.monotonic() + timeout
        ignored = 0
        while (remaining := deadline - time.monotonic()) > 0:
            reply = self.receive(remaining, pump)
            if reply is None:
                break
            if accept(reply):
                if ignored:
                    self._log.info(f"midi: ignored {ignored} unrelated message(s) while waiting for the reply")
                return reply
            ignored += 1
        return None

    # -- closing ---------------------------------------------------------------------------------------------------------

    def close(self):
        with self._lock:
            for port in (self._input, self._output):
                if port is not None:
                    try:
                        port.close_port()
                    except Exception:
                        pass
                    _delete_quiet(port)
            self._input = self._output = None
        self._log.info("midi: closed")

    @property
    def is_open(self):
        return self._output is not None
