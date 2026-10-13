"""Pretend MIDI ports and a pretend JV-1010, so MIDI code is tested without a backend or hardware."""

from jv_studio.core import memory, patch, performance, sysex


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


IDENTITY_REPLY = bytes.fromhex("F0 7E 10 06 02 41 6A 00 05 00 00 00 00 00 F7")


class FakeJV1010:
    """A pretend JV-1010: answers an Identity Request, RQ1s for any patch (temporary or USER), and stores DT1 writes. `gm_mode`: it ignores RQ1/DT1
    (the manual says it does in GM mode). `ignore_writes`: it acknowledges nothing and stores nothing (to test the read-back check).
    `drop_first_replies=n`: the first n RQ1s get no answer (to test retries)."""

    def __init__(self, patch_name="Warm Pad", gm_mode=False, identity=IDENTITY_REPLY, ignore_writes=False, drop_first_replies=0):
        self.temporary = patch.Patch.minimum()
        self.temporary.name = patch_name
        self.user = [patch.Patch.minimum() for _ in range(patch.USER_PATCH_COUNT)]
        for i, p in enumerate(self.user):
            p.name = f"User {i + 1:03d}"
        self.gm_mode = gm_mode
        self.identity = identity
        self.ignore_writes = ignore_writes
        self.drop_first_replies = drop_first_replies
        self.temp_performance = performance.Performance.minimum()
        self.temp_performance.name = "Temp Perf"
        self.user_performances = [performance.Performance.minimum() for _ in range(performance.USER_PERFORMANCE_COUNT)]
        for i, p in enumerate(self.user_performances):
            p.name = f"Perf {i + 1:02d}"
        # everything that is neither a patch nor a performance (system, rhythm setups): block start -> bytes, filled with a recognisable 7-bit pattern
        self.other = {}
        for block in memory.plan([memory.SYSTEM, memory.RHYTHM]):
            self.other[block.start] = bytearray((block.start + i) % 100 for i in range(block.size))
        self.requests = []  # (address, size) of every RQ1
        self.writes = []  # every DT1 received, parsed

    @property
    def patch(self):  # (the temporary patch: what older tests call "the patch")
        return self.temporary

    def _locate(self, address):
        """(patch, base) the address falls in, or None."""
        if address[0] == 0x03:
            return self.temporary, patch.TEMPORARY_BASE
        if address[0] == 0x11 and address[1] < patch.USER_PATCH_COUNT:
            return self.user[address[1]], (0x11, address[1], 0, 0)
        if address[0] == 0x01:
            return self.temp_performance, performance.TEMPORARY_BASE
        if address[0] == 0x10 and address[1] < performance.USER_PERFORMANCE_COUNT:
            return self.user_performances[address[1]], (0x10, address[1], 0, 0)
        return None

    def __call__(self, message):
        if message == sysex.IDENTITY_REQUEST:
            return [self.identity]
        parsed = sysex.parse(message)
        if not isinstance(parsed, sysex.Message) or self.gm_mode:
            return []
        if parsed.command == sysex.CMD_RQ1:
            self.requests.append((parsed.address, parsed.size))
            if self.drop_first_replies > 0:
                self.drop_first_replies -= 1
                return []
            raw = self.other.get(sysex.address_to_int(parsed.address))
            if raw is not None:
                return [sysex.dt1(parsed.address, raw)] if len(raw) == parsed.size else []
            found = self._locate(parsed.address)
            if found is None:
                return []
            target, base = found
            for offset, data in target.blocks():
                if sysex.add_to_address(base, offset) == parsed.address and len(data) == parsed.size:
                    return [sysex.dt1(parsed.address, data)]
            return []
        if parsed.command == sysex.CMD_DT1:
            self.writes.append(parsed)
            if not self.ignore_writes:
                start = sysex.address_to_int(parsed.address)
                for block_start, raw in self.other.items():
                    if block_start <= start and start + len(parsed.data) <= block_start + len(raw):
                        raw[start - block_start : start - block_start + len(parsed.data)] = parsed.data
                        return []
                found = self._locate(parsed.address)
                if found is not None:
                    found[0].apply(parsed, found[1])
        return []
