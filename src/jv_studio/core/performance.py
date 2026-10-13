"""A JV-1010 performance: a common block and 16 part blocks, and how they travel as sysex (Qt-free). The sibling of `patch.py`.

Addresses (manual, "Parameter Address Map"): the Temporary Performance is 01 00 00 00; USER performances USER:01..32 are 10 00..1F 00 00. Inside a performance:
Performance Common at offset 00 00, Part 1..16 at 10 00, 11 00 ... 1F 00 (the third address byte counts the parts), each 0x19 bytes.
The common block is 0x42 bytes and a part 0x19: both fit one DT1 (at most 128 data bytes), so a performance is written as 17 messages.
"""

from dataclasses import dataclass

from . import params, sysex

TEMPORARY_BASE = (0x01, 0x00, 0x00, 0x00)
USER_PERFORMANCE_COUNT = 32
PART_COUNT = 16
RHYTHM_PART = 9  # part 10 (0-based 9): the one that plays the temporary rhythm setup in the unit's own performances

COMMON = "performance_common"
PART = "performance_part"


def user_base(number):
    """The start address of USER performance `number` (0-based: 0 is USER:01)."""
    if not 0 <= number < USER_PERFORMANCE_COUNT:
        raise ValueError(f"user performance number {number} out of range")
    return (0x10, number, 0x00, 0x00)


def part_offset(part):
    return (0x10 + part) << 7  # Part 1..16: 10 00, 11 00 ... 1F 00 (as 7-bit address bytes)


def _table():
    return params.load_table()


@dataclass
class Performance:
    common: bytearray
    parts: list

    @classmethod
    def blank(cls):
        t = _table()
        return cls(t.block(COMMON).new_buffer(), [t.block(PART).new_buffer() for _ in range(PART_COUNT)])

    @classmethod
    def minimum(cls):
        """A performance with every parameter at the bottom of its range and the name "INIT PERF": always VALID, never a musical default (the same idea as
        `Patch.minimum`: all zero bytes is not a valid name, and a tempo is at least 20)."""
        result = cls.blank()
        table = _table()
        for block_key, buffers in ((COMMON, [result.common]), (PART, result.parts)):
            for buffer in buffers:
                for param in table.block(block_key).param_list():
                    params.write(buffer, param, "INIT PERF" if param.string else param.min)
        return result

    def copy(self):
        return Performance(bytearray(self.common), [bytearray(p) for p in self.parts])

    def __eq__(self, other):
        return isinstance(other, Performance) and self.common == other.common and self.parts == other.parts

    # -- values ----------------------------------------------------------------------------------------------------------

    def _buffer(self, block, part):
        if block == COMMON:
            return self.common
        if block == PART:
            if part is None:
                raise ValueError("a part parameter needs a part number (0-15)")
            return self.parts[part]
        raise KeyError(block)

    def get(self, block, key, part=None):
        return params.read(self._buffer(block, part), _table().block(block).param(key))

    def set(self, block, key, value, part=None):
        """Set a parameter; returns the (clamped) value stored."""
        return params.write(self._buffer(block, part), _table().block(block).param(key), value)

    @property
    def name(self):
        return self.get(COMMON, "performance_name")

    @name.setter
    def name(self, text):
        self.set(COMMON, "performance_name", text)

    # -- to and from sysex -----------------------------------------------------------------------------------------------

    def blocks(self):
        """[(offset within the performance, bytes)] in the order the unit lists them."""
        return [(0, self.common)] + [(part_offset(i), p) for i, p in enumerate(self.parts)]

    def to_messages(self, base, device_id=sysex.DEVICE_ID):
        messages = []
        for offset, data in self.blocks():
            messages.extend(sysex.dt1_packets(sysex.add_to_address(base, offset), data, device_id))
        return messages

    @staticmethod
    def requests(base, device_id=sysex.DEVICE_ID):
        """The RQ1 messages that read a whole performance from `base`: each block with its own fixed start address and size."""
        t = _table()
        out = [sysex.rq1(base, t.block(COMMON).size, device_id)]
        for i in range(PART_COUNT):
            out.append(sysex.rq1(sysex.add_to_address(base, part_offset(i)), t.block(PART).size, device_id))
        return out

    def to_syx(self, base):
        return b"".join(self.to_messages(base))

    def apply(self, message, base):
        """Apply a received DT1 to this performance if it lies inside the performance at `base`. Returns True if it did."""
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
    """Read a .syx file of performance DT1 messages: {performance base address: Performance}, in file order. Other messages are skipped; a corrupt one raises."""
    performances = {}
    for raw in sysex.split_messages(stream):
        msg = sysex.parse(raw)
        if not isinstance(msg, sysex.Message) or msg.command != sysex.CMD_DT1:
            continue
        a = msg.address
        if a[0] == 0x10 and a[1] < USER_PERFORMANCE_COUNT:
            base = (0x10, a[1], 0, 0)
        elif a[0] == 0x01:
            base = TEMPORARY_BASE
        else:
            continue
        performance = performances.setdefault(base, Performance.blank())
        performance.apply(msg, base)
    return performances
