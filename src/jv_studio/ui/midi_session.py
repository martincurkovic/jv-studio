"""The app's one MIDI connection: which ports are chosen, whether they are open, and a way for a diagnostic to borrow them."""

from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal

from jv_studio.core import debug_log, midi


class MidiSession(QObject):
    #: emitted whenever the connection opens, closes or changes
    changed = Signal()

    def __init__(self, connection_factory=midi.MidiConnection, parent=None):
        super().__init__(parent)
        self.connection_factory = connection_factory  # (input name, output name) -> a connection; tests pass one over fake ports
        self.connection = None
        self.input_name = None
        self.output_name = None

    @property
    def is_open(self):
        return self.connection is not None and self.connection.is_open

    def open(self, input_name, output_name):
        """Open the chosen ports (closing any open ones first). Choosing no port, or only one, leaves the session closed. Raises if opening fails."""
        self.close()
        if not input_name or not output_name:
            return
        self.connection = self.connection_factory(input_name, output_name)
        self.input_name, self.output_name = input_name, output_name
        self.changed.emit()

    def close(self):
        was_open = self.connection is not None
        if was_open:
            self.connection.close()
        self.connection = None
        self.input_name = self.output_name = None
        if was_open:
            self.changed.emit()

    @contextmanager
    def paused(self):
        """Close the real connection while a diagnostic opens the same ports itself (two opens of one port conflict), and reopen it afterwards."""
        input_name, output_name = self.input_name, self.output_name
        self.close()
        try:
            yield
        finally:
            if input_name and output_name:
                try:
                    self.open(input_name, output_name)
                except Exception:
                    debug_log.get_logger().error(f"midi: couldn't reopen {input_name!r}/{output_name!r} after a test", exc_info=True)
