"""A simulated JV-1010 (Qt-free): the unit's side of the SysEx conversation, in memory.

It answers an Identity Request and RQ1s for every block the app reads (the temporary and USER patches, the temporary and USER performances, the system settings and the
rhythm setups) and stores DT1 writes. It is what the tests talk to (`tests/fakes.FakeJV1010`) and what `--demo` talks to (`core/demo_unit.py`, which fills it with believable
contents). Call it with the bytes of one message; it returns the messages the unit would answer with.

Options for testing the app's safety nets: `gm_mode` (the unit ignores RQ1/DT1 in GM mode, as the manual says), `ignore_writes` (it stores nothing, to test the read-back
check) and `drop_first_replies=n` (the first n RQ1s get no answer, to test retries).
"""

from . import memory, patch, performance, sysex, system

IDENTITY_REPLY = bytes.fromhex("F0 7E 10 06 02 41 6A 00 05 00 00 00 00 00 F7")


class SimulatedUnit:
    def __init__(self, gm_mode=False, identity=IDENTITY_REPLY, ignore_writes=False, drop_first_replies=0):
        self.temporary = patch.Patch.minimum()
        self.user = [patch.Patch.minimum() for _ in range(patch.USER_PATCH_COUNT)]
        for i, p in enumerate(self.user):
            p.name = f"User {i + 1:03d}"
        self.temp_performance = performance.Performance.minimum()
        self.temp_performance.name = "Temp Perf"
        self.user_performances = [performance.Performance.minimum() for _ in range(performance.USER_PERFORMANCE_COUNT)]
        for i, p in enumerate(self.user_performances):
            p.name = f"Perf {i + 1:02d}"
        # everything that is neither a patch nor a performance (system, rhythm setups): block start -> bytes, filled with a recognisable 7-bit pattern
        self.other = {}
        for block in memory.plan([memory.SYSTEM, memory.RHYTHM]):
            self.other[block.start] = bytearray((block.start + i) % 100 for i in range(block.size))
        self.gm_mode = gm_mode
        self.identity = identity
        self.ignore_writes = ignore_writes
        self.drop_first_replies = drop_first_replies
        self.requests = []  # (address, size) of every RQ1
        self.writes = []  # every DT1 received, parsed
        self.channel_messages = []  # every non-SysEx message received (notes, Bank Select, Program Change...): the unit would play or switch, here they are just kept
        # the System settings: VALID ones (a block of the pattern would hold values outside every range): Patch mode on USER 001, A = 440.0 Hz, channel 1, program change and bank select ON
        initial = system.System.minimum()
        for key, value in (("sound_mode", 1), ("patch_group_id", 1), ("master_tune", 63), ("patch_receive_channel", 0), ("receive_program_change", 1),
                           ("receive_bank_select", 1), ("efx_switch", 1), ("chorus_switch", 1), ("reverb_switch", 1), ("system_tempo", 120)):
            initial.set(key, value)
        self.other[0] = bytearray(initial.common)

    @property
    def patch(self):  # (the temporary patch: what older tests call "the patch")
        return self.temporary

    def _locate(self, address):
        """(patch or performance, its base address) the address falls in, or None."""
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
        if message and message[0] != 0xF0:
            self.channel_messages.append(bytes(message))
            return []
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
