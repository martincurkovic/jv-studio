"""Talking to a JV-1010 over a `MidiConnection` (Qt-free, synchronous): read blocks and patches, write them back with a read-back, set one parameter.

Rules that come from the manual and from AKAISDS's hardware lessons:
- ONE request outstanding; a request must use a block's own start address and size (`Patch.requests`), and only a reply naming that address and size is accepted.
- DT1 messages larger than 128 data bytes are split into packets, and successive DT1s are at least `PACKET_GAP_MS` apart. Both are enforced here.
- Nothing is sent into silence: a read that gets no reply is retried a bounded number of times and then raises `UnitError`.
- A write is verified by reading it back; a mismatch raises. Callers (and the UI) decide when writing is allowed: reads never write.
"""

import time

from . import params, patch, sysex

DEFAULT_TIMEOUT = 1.0  # seconds to wait for one reply
DEFAULT_RETRIES = 1  # extra attempts after a timeout (so two requests at most per block)


class UnitError(RuntimeError):
    """The unit did not answer, or what it holds is not what we wrote."""


class JV1010Unit:
    def __init__(self, connection, *, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, pump=None, clock=time.monotonic, sleep=time.sleep):
        self.connection = connection
        self.timeout = timeout
        self.retries = retries
        self.pump = pump  # called while waiting, so a GUI-thread caller stays responsive (a worker thread passes None)
        self._clock = clock
        self._sleep = sleep
        self._last_dt1 = None

    # -- low level -------------------------------------------------------------------------------------------------------

    def _wait(self, seconds):
        deadline = self._clock() + seconds
        while (remaining := deadline - self._clock()) > 0:
            if self.pump is not None:
                self.pump()
            self._sleep(min(remaining, 0.005))

    def _send_dt1(self, message):
        """Send one DT1, at least PACKET_GAP_MS after the previous one."""
        if self._last_dt1 is not None:
            gap = sysex.PACKET_GAP_MS / 1000 - (self._clock() - self._last_dt1)
            if gap > 0:
                self._wait(gap)
        self.connection.send(message)
        self._last_dt1 = self._clock()

    def read_block(self, address, size):
        """The `size` bytes at `address` (a block's own start and size). Raises UnitError after the retries."""
        request = sysex.rq1(address, size)

        def accept(raw):
            try:
                reply = sysex.parse(raw)
            except sysex.SysexError:
                return False
            return isinstance(reply, sysex.Message) and reply.command == sysex.CMD_DT1 and reply.address == address and len(reply.data) == size

        for _attempt in range(1 + self.retries):
            raw = self.connection.request(request, accept, self.timeout, self.pump)
            if raw is not None:
                return sysex.parse(raw).data
        raise UnitError(f"no reply to a request for {size} bytes at {' '.join(f'{b:02X}' for b in address)} (the unit ignores data requests in GM mode)")

    # -- patches ---------------------------------------------------------------------------------------------------------

    def read_patch(self, base):
        """The whole patch at `base`: five requests (common, then the four tones), one at a time."""
        result = patch.Patch.blank()
        for (offset, buffer) in result.blocks():
            data = self.read_block(sysex.add_to_address(base, offset), len(buffer))
            buffer[:] = data
        return result

    def read_temporary_patch(self):
        return self.read_patch(patch.TEMPORARY_BASE)

    def read_user_patch(self, number):
        return self.read_patch(patch.user_base(number))

    def read_user_patch_names(self, progress=None, cancelled=None):
        """The 128 USER patch names, one request each (the common block: its first 12 bytes are the name). `progress(done, total)` after each;
        `cancelled()` is polled before each request and stops early, returning the names read so far."""
        common = params.load_table().block(patch.COMMON)
        name = common.param("patch_name")
        names = []
        for number in range(patch.USER_PATCH_COUNT):
            if cancelled is not None and cancelled():
                break
            data = self.read_block(patch.user_base(number), common.size)
            names.append(params.read(data, name))
            if progress is not None:
                progress(number + 1, patch.USER_PATCH_COUNT)
        return names

    def write_patch(self, base, new, verify=True):
        """Write `new` to the patch at `base` (DT1 packets, >= 20 ms apart) and, with `verify`, read it back: it must be identical."""
        for message in new.to_messages(base):
            self._send_dt1(message)
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)  # let the unit finish storing before it is asked for the data
            back = self.read_patch(base)
            if back != new:
                raise UnitError("the unit does not hold what was written (the read-back differs)")

    def write_param(self, base, block, key, value, tone=None):
        """Set ONE parameter (a DT1 of just its bytes) in the patch at `base`. Returns the value actually sent (clamped to the range).
        For a tone parameter pass `tone` 0-3. No read-back: this is the live-edit path (use `read_patch` to check)."""
        table = params.load_table()
        param = table.block(block).param(key)
        buffer = bytearray(table.block(block).size)
        sent = params.write(buffer, param, value)
        if block == patch.COMMON:
            offset = 0
        elif tone is None:
            raise ValueError("a tone parameter needs a tone number (0-3)")
        else:
            offset = patch.tone_offset(tone)
        address = sysex.add_to_address(base, offset + param.offset)
        self._send_dt1(sysex.dt1(address, params.param_bytes(buffer, param)))
        return sent

