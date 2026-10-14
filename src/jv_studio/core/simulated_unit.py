"""A simulated JV-1010 (Qt-free): the unit's side of the SysEx conversation, in memory.

It answers an Identity Request and RQ1s for every block the app reads (the temporary and USER patches, the temporary and USER performances and rhythm sets, and the system settings) and stores DT1 writes. It is what the tests talk to (`tests/fakes.FakeJV1010`) and what `--demo` talks to (`core/demo_unit.py`, which fills it with believable
contents). Call it with the bytes of one message; it returns the messages the unit would answer with.

Options for testing the app's safety nets: `gm_mode` (the unit ignores RQ1/DT1 in GM mode, as the manual says), `ignore_writes` (it stores nothing, to test the read-back
check) and `drop_first_replies=n` (the first n RQ1s get no answer, to test retries).
"""

from . import audition, memory, patch, patch_groups, performance, rhythm, scale_tune, sysex, system, universal

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
        self.temp_rhythm = rhythm.RhythmSet.minimum()
        self.temp_rhythm.name = "Temp Rhythm"
        self.user_rhythms = [rhythm.RhythmSet.minimum() for _ in range(rhythm.USER_RHYTHM_COUNT)]
        for i, r in enumerate(self.user_rhythms):
            r.name = f"Rhythm {i + 1}"
        # everything else (the system block): block start -> bytes, filled with a recognisable 7-bit pattern (then replaced by valid values below)
        self.other = {}
        for block in memory.plan([memory.SYSTEM]):
            self.other[block.start] = bytearray((block.start + i) % 100 for i in range(block.size))
        self.gm_mode = gm_mode
        self.identity = identity
        self.ignore_writes = ignore_writes
        self.drop_first_replies = drop_first_replies
        self.requests = []  # (address, size) of every RQ1
        self.writes = []  # every DT1 received, parsed
        self.master_volume = None  # the last Master Volume received (None: never set)
        self.universal_messages = []  # every Universal SysEx received: "gm_on", "gm_off", ("master_volume", n)
        self._bank = {}  # channel -> [Bank Select MSB, LSB] last received
        self.channel_messages = []  # every non-SysEx message received (notes, Bank Select, Program Change...): the unit would play or switch, here they are just kept
        # the System settings: VALID ones (a block of the pattern would hold values outside every range): Patch mode on USER 001, A = 440.0 Hz, channel 1, program change and bank select ON
        initial = system.System.minimum()
        for key, value in (("sound_mode", 1), ("patch_group_id", 1), ("master_tune", 63), ("patch_receive_channel", 0), ("receive_program_change", 1),
                           ("receive_bank_select", 1), ("efx_switch", 1), ("chorus_switch", 1), ("reverb_switch", 1), ("system_tempo", 120)):
            initial.set(key, value)
        self.other[0] = bytearray(initial.common)
        for target in range(scale_tune.TARGETS):  # equal temperament: every scale tune byte is 64 (0 cents)
            self.other[sysex.address_to_int(scale_tune.target_address(target))] = bytearray(scale_tune.ScaleTunes.blank().blocks[target])

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
        if address[0] == rhythm.TEMPORARY_BASE[0] and address[1] == rhythm.TEMPORARY_BASE[1]:
            return self.temp_rhythm, rhythm.TEMPORARY_BASE
        if address[0] == 0x10 and 0x40 <= address[1] < 0x40 + rhythm.USER_RHYTHM_COUNT:
            return self.user_rhythms[address[1] - 0x40], (0x10, address[1], 0, 0)
        return None

    def _channel_message(self, message):
        """Bank Select and Program Change as the real unit takes them in PATCH mode (`[manual p.68]`): on the Patch Receive Channel, with Receive Program Change ON (and Bank Select ON to change
        bank), the chosen patch is LOADED INTO THE TEMPORARY PATCH and the System block's selection follows. In Performance or GM mode, or on another channel, nothing happens here."""
        status, channel = message[0] & 0xF0, message[0] & 0x0F
        if status == 0xB0 and len(message) == 3 and message[1] in (0, 32):
            self._bank.setdefault(channel, [80, 0])[0 if message[1] == 0 else 1] = message[2]
            return
        if status != 0xC0 or len(message) < 2 or self.gm_mode:
            return
        settings = system.System(self.other[0])
        if settings.get("sound_mode") == 0 and settings.get("receive_program_change"):
            self._part_program_change(channel, message[1])  # Performance mode: the parts listening on this channel take the patch
            return
        if settings.get("sound_mode") != 1 or channel != settings.get("patch_receive_channel") or not settings.get("receive_program_change"):
            return
        msb, lsb = self._bank.get(channel, [80, 0]) if settings.get("receive_bank_select") else (80, 0)
        for key, entries in audition.BANKS.items():
            for bank_msb, bank_lsb, count, first in entries:
                number = first + message[1]
                if (bank_msb, bank_lsb) == (msb, lsb) and number < first + count:
                    group = next(g for g in patch_groups.GROUPS if g.key == key)
                    if key == "USER":
                        self.temporary = self.user[number].copy()
                    else:
                        self.temporary = patch.Patch.minimum()
                        self.temporary.name = patch_groups.names_of(group)[number]
                    for param, value in (("patch_group_type", group.type), ("patch_group_id", group.id), ("patch_number", number)):
                        settings.set(param, value)
                    self.other[0][:] = settings.common
                    return

    def _part_program_change(self, channel, program):
        """In Performance mode a Program Change (with the Bank Select before it) sets the patch of every part that listens on `channel`, receives and takes program changes
        (`[manual p.68]`): the temporary performance's Patch Group Type / ID / Number change, which is what the unit's PERFORM display would show."""
        msb, lsb = self._bank.get(channel, [80, 0])
        found = next(((key, bank_first) for key, entries in audition.BANKS.items() for bank_msb, bank_lsb, count, bank_first in entries
                      if (bank_msb, bank_lsb) == (msb, lsb) and program + bank_first < bank_first + count), None)
        if found is None:
            return
        key, first = found
        group = next(g for g in patch_groups.GROUPS if g.key == key)
        for part in range(performance.PART_COUNT):
            if (self.temp_performance.get(performance.PART, "midi_channel", part=part) == channel and self.temp_performance.get(performance.PART, "receive_switch", part=part)
                    and self.temp_performance.get(performance.PART, "receive_program_change_switch", part=part)):
                for name, value in (("patch_group_type", group.type), ("patch_group_id", group.id), ("patch_number", first + program)):
                    self.temp_performance.set(performance.PART, name, value, part=part)

    def block_data(self, start):
        """The bytes of the block that starts at `start` (an int address, `memory.MemBlock.start`) as the unit holds them: a live bytearray, so a test can change it."""
        if start in self.other:
            return self.other[start]
        address = sysex.int_to_address(start)
        found = self._locate(address)
        if found is not None:
            target, base = found
            for offset, data in target.blocks():
                if sysex.add_to_address(base, offset) == address:
                    return data
        raise KeyError(start)

    def __call__(self, message):
        if message and message[0] != 0xF0:
            self.channel_messages.append(bytes(message))
            self._channel_message(bytes(message))
            return []
        if message == sysex.IDENTITY_REQUEST:
            return [self.identity]
        if (universal_kind := universal.classify(message)) is not None:
            self.universal_messages.append(universal_kind)
            if universal_kind == "gm_on":
                self.gm_mode = True  # in GM mode the unit ignores RQ1/DT1 (and the Master Volume message)
            elif universal_kind == "gm_off":
                self.gm_mode = False
            elif not self.gm_mode:
                self.master_volume = universal_kind[1]
            return []
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
