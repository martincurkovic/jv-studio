"""A JV-1010 patch: one common block and four tone blocks, and how they travel as sysex (Qt-free).

Addresses (manual, "Parameter Address Map"): Patch Mode Temporary Patch 03 00 00 00; User Patch USER:001..128 at 11 00..7F 00 00. Inside a patch:
Patch Common at offset 00 00, Patch Tone 1..4 at 10 00, 12 00, 14 00, 16 00.
"""

from dataclasses import dataclass

from . import params, sysex

TEMPORARY_BASE = (0x03, 0x00, 0x00, 0x00)
USER_PATCH_COUNT = 128
TONE_COUNT = 4

COMMON = "patch_common"
TONE = "patch_tone"


def user_base(number):
    """The start address of USER patch `number` (0-based: 0 is USER:001)."""
    if not 0 <= number < USER_PATCH_COUNT:
        raise ValueError(f"user patch number {number} out of range")
    return (0x11, number, 0x00, 0x00)


def tone_offset(tone):
    return (0x10 + 2 * tone) << 7  # Patch Tone n: 10 00, 12 00, 14 00, 16 00 (as 7-bit address bytes)


def _table():
    return params.load_table()


@dataclass
class Patch:
    common: bytearray
    tones: list

    @classmethod
    def blank(cls):
        t = _table()
        return cls(t.block(COMMON).new_buffer(), [t.block(TONE).new_buffer() for _ in range(TONE_COUNT)])

    @classmethod
    def minimum(cls):
        """A patch with every parameter at the bottom of its range and the name "INIT PATCH": always VALID (all zero bytes is not: a name
        needs characters from 32 and a tempo is at least 20), never a musical default. A starting point for tests and for "new patch"."""
        result = cls.blank()
        table = _table()
        for block_key, buffers in ((COMMON, [result.common]), (TONE, result.tones)):
            for buffer in buffers:
                for param in table.block(block_key).param_list():
                    params.write(buffer, param, "INIT PATCH" if param.string else param.min)
        return result

    def copy(self):
        return Patch(bytearray(self.common), [bytearray(t) for t in self.tones])

    def __eq__(self, other):
        return isinstance(other, Patch) and self.common == other.common and self.tones == other.tones

    # -- values ----------------------------------------------------------------------------------------------------------

    def _buffer(self, block, tone):
        if block == COMMON:
            return self.common
        if block == TONE:
            if tone is None:
                raise ValueError("a tone parameter needs a tone number (0-3)")
            return self.tones[tone]
        raise KeyError(block)

    def get(self, block, key, tone=None):
        return params.read(self._buffer(block, tone), _table().block(block).param(key))

    def set(self, block, key, value, tone=None):
        """Set a parameter; returns the (clamped) value stored."""
        return params.write(self._buffer(block, tone), _table().block(block).param(key), value)

    @property
    def name(self):
        return self.get(COMMON, "patch_name")

    @name.setter
    def name(self, text):
        self.set(COMMON, "patch_name", text)

    # -- to and from sysex -----------------------------------------------------------------------------------------------

    def blocks(self):
        """[(offset within the patch, bytes)] in the order the unit lists them."""
        return [(0, self.common)] + [(tone_offset(i), t) for i, t in enumerate(self.tones)]

    def to_messages(self, base, device_id=sysex.DEVICE_ID):
        """All the DT1 messages that write this patch at `base` (a tone is 129 bytes, so it goes out as 128 + 1). Send them 20 ms apart."""
        messages = []
        for offset, data in self.blocks():
            messages.extend(sysex.dt1_packets(sysex.add_to_address(base, offset), data, device_id))
        return messages

    @staticmethod
    def requests(base, device_id=sysex.DEVICE_ID):
        """The RQ1 messages that read a whole patch from `base`: each block with its own fixed start address and size."""
        t = _table()
        out = [sysex.rq1(base, t.block(COMMON).size, device_id)]
        for i in range(TONE_COUNT):
            out.append(sysex.rq1(sysex.add_to_address(base, tone_offset(i)), t.block(TONE).size, device_id))
        return out

    def to_syx(self, base):
        return b"".join(self.to_messages(base))

    def apply(self, message, base):
        """Apply a received DT1 (a `sysex.Message`) to this patch if it lies inside the patch at `base`. Returns True if it did."""
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
    """Read a .syx file (or any byte stream) of patch DT1 messages: {patch base address: Patch}, in file order. Other messages are skipped;
    a corrupt one raises `sysex.SysexError`."""
    patches = {}
    for raw in sysex.split_messages(stream):
        msg = sysex.parse(raw)
        if not isinstance(msg, sysex.Message) or msg.command != sysex.CMD_DT1:
            continue
        a = msg.address
        if a[0] == 0x11 and a[1] < USER_PATCH_COUNT:
            base = (0x11, a[1], 0, 0)
        elif a[0] == 0x03:
            base = TEMPORARY_BASE
        else:
            continue
        patch = patches.setdefault(base, Patch.blank())
        patch.apply(msg, base)
    return patches
