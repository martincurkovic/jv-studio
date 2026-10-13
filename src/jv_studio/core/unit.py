"""Talking to a JV-1010 over a `MidiConnection` (Qt-free, synchronous): read blocks and patches, write them back with a read-back, set one parameter.

Rules that come from the manual and from AKAISDS's hardware lessons:
- ONE request outstanding; a request must use a block's own start address and size (`Patch.requests`), and only a reply naming that address and size is accepted.
- DT1 messages larger than 128 data bytes are split into packets, and successive DT1s are at least `PACKET_GAP_MS` apart. Both are enforced here.
- Nothing is sent into silence: a read that gets no reply is retried a bounded number of times and then raises `UnitError`.
- A write is verified by reading it back; a mismatch raises. Callers (and the UI) decide when writing is allowed: reads never write.
"""

import time
from dataclasses import dataclass

from . import params, patch, performance, sysex

DEFAULT_TIMEOUT = 1.0  # seconds to wait for one reply
DEFAULT_RETRIES = 1  # extra attempts after a timeout (so two requests at most per block)


@dataclass(frozen=True)
class PatchSummary:
    name: str
    key_assign: str  # "POLY" or "SOLO"


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

    def read_user_patch_summaries(self, progress=None, cancelled=None):
        """The 128 USER patches as `PatchSummary(name, key_assign)`, one request each (the common block holds both). `progress(done, total)` after
        each; `cancelled()` is polled before each request and stops early, returning the summaries read so far."""
        common = params.load_table().block(patch.COMMON)
        name, assign = common.param("patch_name"), common.param("key_assign_mode")
        summaries = []
        for number in range(patch.USER_PATCH_COUNT):
            if cancelled is not None and cancelled():
                break
            data = self.read_block(patch.user_base(number), common.size)
            summaries.append(PatchSummary(params.read(data, name), params.format_value(assign, params.read(data, assign))))
            if progress is not None:
                progress(number + 1, patch.USER_PATCH_COUNT)
        return summaries

    def read_user_patch_names(self, progress=None, cancelled=None):
        return [s.name for s in self.read_user_patch_summaries(progress, cancelled)]

    def write_patch(self, base, new, verify=True):
        """Write `new` to the patch at `base` (DT1 packets, >= 20 ms apart) and, with `verify`, read it back: it must be identical."""
        for message in new.to_messages(base):
            self._send_dt1(message)
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)  # let the unit finish storing before it is asked for the data
            back = self.read_patch(base)
            if back != new:
                raise UnitError("the unit does not hold what was written (the read-back differs)")

    def write_block(self, address, data, verify=True):
        """Write ONE block (a block's own start address and whole contents) as packets of <= 128 bytes at least 20 ms apart; with `verify`, read it back and compare."""
        for message in sysex.dt1_packets(address, data):
            self._send_dt1(message)
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)
            if self.read_block(address, len(data)) != bytes(data):
                raise UnitError(f"the unit does not hold what was written at {' '.join(f'{b:02X}' for b in address)} (the read-back differs)")

    # -- performances ----------------------------------------------------------------------------------------------------

    def read_performance(self, base):
        """The whole performance at `base`: 17 requests (the common block, then the 16 parts), one at a time."""
        result = performance.Performance.blank()
        for offset, buffer in result.blocks():
            buffer[:] = self.read_block(sysex.add_to_address(base, offset), len(buffer))
        return result

    def read_temporary_performance(self):
        return self.read_performance(performance.TEMPORARY_BASE)

    def read_user_performance(self, number):
        return self.read_performance(performance.user_base(number))

    def read_user_performance_names(self, progress=None, cancelled=None):
        """The 32 USER performance names, one request each (the common block: its first 12 bytes are the name). Stops early, returning what it has, if cancelled."""
        common = params.load_table().block(performance.COMMON)
        name = common.param("performance_name")
        names = []
        for number in range(performance.USER_PERFORMANCE_COUNT):
            if cancelled is not None and cancelled():
                break
            names.append(params.read(self.read_block(performance.user_base(number), common.size), name))
            if progress is not None:
                progress(number + 1, performance.USER_PERFORMANCE_COUNT)
        return names

    def write_performance(self, base, new, verify=True):
        """Write `new` to the performance at `base` (17 DT1 messages, >= 20 ms apart) and, with `verify`, read it back: it must be identical."""
        for message in new.to_messages(base):
            self._send_dt1(message)
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)
            if self.read_performance(base) != new:
                raise UnitError("the unit does not hold what was written (the read-back differs)")

    def write_performance_param(self, base, block, key, value, part=None, verify=False):
        """Set ONE parameter of the performance at `base` (a DT1 of just its bytes); with `verify`, read its block back and check. Returns the value sent."""
        table = params.load_table()
        param = table.block(block).param(key)
        buffer = bytearray(table.block(block).size)
        sent = params.write(buffer, param, value)
        if block == performance.COMMON:
            offset = 0
        elif part is None:
            raise ValueError("a part parameter needs a part number (0-15)")
        else:
            offset = performance.part_offset(part)
        wanted = params.param_bytes(buffer, param)
        self._send_dt1(sysex.dt1(sysex.add_to_address(base, offset + param.offset), wanted))
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)
            if params.param_bytes(self.read_block(sysex.add_to_address(base, offset), table.block(block).size), param) != wanted:
                raise UnitError(f"the unit did not take {param.name} (the read-back differs)")
        return sent

    def write_param(self, base, block, key, value, tone=None, verify=False):
        """Set ONE parameter (a DT1 of just its bytes) in the patch at `base`. Returns the value actually sent (clamped to the range; the text for a name).
        For a tone parameter pass `tone` 0-3. With `verify`, read the parameter's whole block back (one request) and check its bytes."""
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
        wanted = params.param_bytes(buffer, param)
        self._send_dt1(sysex.dt1(address, wanted))
        if verify:
            self._wait(sysex.PACKET_GAP_MS / 1000)
            block_address = sysex.add_to_address(base, offset)
            if params.param_bytes(self.read_block(block_address, table.block(block).size), param) != wanted:
                raise UnitError(f"the unit did not take {param.name} (the read-back differs)")
        return sent

