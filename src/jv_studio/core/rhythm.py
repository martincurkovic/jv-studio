"""A JV-1010 rhythm set: a common block (the name) and one tone-like block per key, 35-98, and how they travel as sysex (Qt-free). The sibling of `performance.py`.

Addresses (manual, "Parameter Address Map"): the Temporary Rhythm Setup is 02 09 00 00 (the performance-mode temporary patch of part 10); the USER rhythm setups USER:1-2 are 10 40 00 00
and 10 41 00 00. Inside a set: Rhythm Common at offset 00 00, then the note for key k at (k << 7), i.e. third address byte = the key number (key 35 at 23 00, key 98 at 62 00).
The common block is 12 bytes and a note 58: each fits one DT1, so a set is written as 65 messages.

Each key has its own wave, tuning, filter, envelopes, level, pan and effect sends: a rhythm set is a drum kit, one sound per key. Roland's note numbers: 60 is C4 (key 35 is B1).
"""

from dataclasses import dataclass

from . import params, sysex

TEMPORARY_BASE = (0x02, 0x09, 0x00, 0x00)
USER_RHYTHM_COUNT = 2
KEYS = range(35, 99)  # 64 keys, 35-98
FIRST_KEY, LAST_KEY = KEYS[0], KEYS[-1]

COMMON = "rhythm_common"
NOTE = "rhythm_note"


def user_base(number):
    """The start address of USER rhythm set `number` (0-based: 0 is USER:1)."""
    if not 0 <= number < USER_RHYTHM_COUNT:
        raise ValueError(f"user rhythm set number {number} out of range")
    return (0x10, 0x40 + number, 0x00, 0x00)


def note_offset(key):
    if key not in KEYS:
        raise ValueError(f"rhythm key {key} is outside {FIRST_KEY}-{LAST_KEY}")
    return key << 7


def _table():
    return params.load_table()


@dataclass
class RhythmSet:
    common: bytearray
    notes: dict  # key (35-98) -> bytearray

    @classmethod
    def blank(cls):
        t = _table()
        return cls(t.block(COMMON).new_buffer(), {key: t.block(NOTE).new_buffer() for key in KEYS})

    @classmethod
    def minimum(cls):
        """A rhythm set with every parameter at the bottom of its range, named "INIT RHYTHM" (every tone off): always VALID (all-zero bytes are not: no name characters)."""
        result = cls.blank()
        table = _table()
        for block_key, buffers in ((COMMON, [result.common]), (NOTE, list(result.notes.values()))):
            for buffer in buffers:
                for param in table.block(block_key).param_list():
                    params.write(buffer, param, "INIT RHYTHM" if param.string else param.min)
        return result

    def copy(self):
        return RhythmSet(bytearray(self.common), {key: bytearray(data) for key, data in self.notes.items()})

    def __eq__(self, other):
        return isinstance(other, RhythmSet) and self.common == other.common and self.notes == other.notes

    # -- values ----------------------------------------------------------------------------------------------------------

    def _buffer(self, block, key):
        if block == COMMON:
            return self.common
        if block == NOTE:
            if key is None:
                raise ValueError("a note parameter needs a key (35-98)")
            return self.notes[key]
        raise KeyError(block)

    def get(self, block, name, key=None):
        return params.read(self._buffer(block, key), _table().block(block).param(name))

    def set(self, block, name, value, key=None):
        """Set a parameter; returns the (clamped) value stored."""
        return params.write(self._buffer(block, key), _table().block(block).param(name), value)

    @property
    def name(self):
        return self.get(COMMON, "rhythm_name")

    @name.setter
    def name(self, text):
        self.set(COMMON, "rhythm_name", text)

    def copy_note(self, source, target):
        """Make key `target` sound like key `source` (every parameter of the note block)."""
        self.notes[target][:] = self.notes[source]

    def swap_notes(self, a, b):
        self.notes[a][:], self.notes[b][:] = bytes(self.notes[b]), bytes(self.notes[a])

    # -- to and from sysex -----------------------------------------------------------------------------------------------

    def blocks(self):
        """[(offset within the set, bytes)] in the order the unit lists them."""
        return [(0, self.common)] + [(note_offset(key), self.notes[key]) for key in KEYS]

    def to_messages(self, base, device_id=sysex.DEVICE_ID):
        messages = []
        for offset, data in self.blocks():
            messages.extend(sysex.dt1_packets(sysex.add_to_address(base, offset), data, device_id))
        return messages

    @staticmethod
    def requests(base, device_id=sysex.DEVICE_ID):
        """The RQ1 messages that read a whole set from `base`: each block with its own fixed start address and size."""
        t = _table()
        out = [sysex.rq1(base, t.block(COMMON).size, device_id)]
        for key in KEYS:
            out.append(sysex.rq1(sysex.add_to_address(base, note_offset(key)), t.block(NOTE).size, device_id))
        return out

    def to_syx(self, base):
        return b"".join(self.to_messages(base))

    def apply(self, message, base):
        """Apply a received DT1 to this set if it lies inside the set at `base`. Returns True if it did."""
        if message.command != sysex.CMD_DT1:
            return False
        rel = sysex.address_to_int(message.address) - sysex.address_to_int(base)
        for offset, data in self.blocks():
            if offset <= rel and rel + len(message.data) <= offset + len(data):
                start = rel - offset
                data[start : start + len(message.data)] = message.data
                return True
        return False


def parse_syx(stream):
    """Read a .syx file of rhythm set DT1 messages: {set base address: RhythmSet}, in file order. Other messages are skipped; a corrupt one raises."""
    sets = {}
    for raw in sysex.split_messages(stream):
        msg = sysex.parse(raw)
        if not isinstance(msg, sysex.Message) or msg.command != sysex.CMD_DT1:
            continue
        a = msg.address
        if a[0] == 0x10 and 0x40 <= a[1] < 0x40 + USER_RHYTHM_COUNT:
            base = (0x10, a[1], 0, 0)
        elif a[0] == TEMPORARY_BASE[0] and a[1] == TEMPORARY_BASE[1]:
            base = TEMPORARY_BASE
        else:
            continue
        sets.setdefault(base, RhythmSet.blank()).apply(msg, base)
    return sets
