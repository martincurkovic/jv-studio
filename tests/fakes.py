"""Pretend MIDI ports and a pretend JV-1010, so MIDI code is tested without a backend or hardware."""

from jv_studio.core.simulated_unit import IDENTITY_REPLY, SimulatedUnit  # noqa: F401  (tests import IDENTITY_REPLY from here)


class FakePorts:
    """One input/output pair. `respond(sent_bytes)` returns the messages the "other end" answers with (delivered at once)."""

    def __init__(self, respond=None):
        self.respond = respond
        self.sent = []
        self._callback = None
        self.closed = []

    def input_factory(self, name):
        return _FakeIn(self)

    def output_factory(self, name):
        return _FakeOut(self)

    def deliver(self, message):
        """Something arrives on the input (as rtmidi would hand it: a list of ints)."""
        if self._callback is not None:
            self._callback((list(message), 0.0), None)


class _FakeIn:
    def __init__(self, ports):
        self._ports = ports

    def set_callback(self, callback):
        self._ports._callback = callback

    def close_port(self):
        self._ports.closed.append("in")

    def delete(self):
        pass


class _FakeOut:
    def __init__(self, ports):
        self._ports = ports

    def send_message(self, message):
        self._ports.sent.append(bytes(message))
        if self._ports.respond is not None:
            for reply in self._ports.respond(bytes(message)) or []:
                self._ports.deliver(reply)

    def close_port(self):
        self._ports.closed.append("out")

    def delete(self):
        pass


def loopback(message):
    """A MIDI cable from OUT to IN: whatever is sent comes straight back."""
    return [message]


def corrupting_loopback(message):
    bad = bytearray(message)
    bad[len(bad) // 2] ^= 0x01
    return [bytes(bad)]


def silent(message):
    return []


class FakeJV1010(SimulatedUnit):
    """The simulated unit with the minimal contents the tests expect (patches named "User 001", performances "Perf 01"; the temporary patch is called `patch_name`)."""

    def __init__(self, patch_name="Warm Pad", **options):
        super().__init__(**options)
        self.temporary.name = patch_name
