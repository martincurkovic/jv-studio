"""Scale tune (Qt-free): a fine pitch adjustment for each of the 12 notes C-B, applied to every octave, so tunings other than equal temperament can be played.

The unit holds 17 blocks of 12 bytes in the System area (manual "Parameter Address Map" 1-1 and 1-1-2): Part 1-16 at 00 00 10 00 ... 00 00 1F 00 and Patch Mode at 00 00 20 00.
Each byte is 0-127 for -64..+63 cents, so 64 is "no change" (equal temperament, the factory state). The manual: "Scale Tune messages for any parts are recognized in the patch mode"
and the System Scale Tune Switch decides whether they are used at all.

The three example tunings are the manual's own table (MIDI Implementation, "Scale Tune Function"), in cents above C; its worked Arabian-scale message
`3A 6D 3E 34 0D 38 6B 3C 6F 40 36 0F` is the same numbers + 64 (a test checks it). Other tonics are the same pattern rotated, which is how a tuning is moved to another key.
"""

from dataclasses import dataclass

from . import params, sysex, system

NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PART_COUNT = 16
PATCH_MODE = 16  # the target index of the Patch Mode block (after the 16 parts)
TARGETS = 17
CENTER = 64  # the raw value for 0 cents
BLOCK = "scale_tune"

PRESETS = {
    "Equal Temperament": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Just Intonation": (0, -8, 4, 16, -14, -2, -10, 2, 14, -16, 14, -12),
    "Arabian-type Scale": (-6, 45, -2, -12, -51, -8, 43, -4, 47, 0, -10, -49),
}


def block_size():
    return params.load_table().block(BLOCK).size


def target_offset(target):
    """The block's offset inside the System area: (0x10 + target) << 7 (so the Patch Mode block, target 16, is 0x20 << 7)."""
    if not 0 <= target < TARGETS:
        raise ValueError(f"scale tune target {target} out of range")
    return (0x10 + target) << 7


def target_address(target):
    return sysex.add_to_address(system.BASE, target_offset(target))


def target_name(target):
    return "Patch mode" if target == PATCH_MODE else f"Part {target + 1}"


def cents_to_raw(cents):
    return max(0, min(127, CENTER + int(cents)))


def raw_to_cents(raw):
    return raw - CENTER


def preset_cents(name, tonic=0):
    """The 12 values (cents) of preset `name` with its tonic moved to note `tonic` (0 = C ... 11 = B): note n gets what note n - tonic had."""
    base = PRESETS[name]
    return [base[(note - tonic) % 12] for note in range(12)]


@dataclass
class ScaleTunes:
    blocks: list  # 17 bytearrays of 12: parts 1-16, then Patch Mode

    @classmethod
    def blank(cls):
        """Equal temperament everywhere: every byte 64."""
        return cls([bytearray([CENTER] * block_size()) for _ in range(TARGETS)])

    def copy(self):
        return ScaleTunes([bytearray(b) for b in self.blocks])

    def __eq__(self, other):
        return isinstance(other, ScaleTunes) and self.blocks == other.blocks

    def get(self, target, note):
        return self.blocks[target][note]

    def cents(self, target, note):
        return raw_to_cents(self.blocks[target][note])

    def set(self, target, note, raw):
        self.blocks[target][note] = max(0, min(127, int(raw)))
        return self.blocks[target][note]

    def set_block_cents(self, target, cents):
        for note, value in enumerate(cents):
            self.blocks[target][note] = cents_to_raw(value)

    def changed_targets(self, other):
        """The targets whose 12 values differ from `other`'s."""
        return [t for t in range(TARGETS) if self.blocks[t] != other.blocks[t]]

    def changed_notes(self, other, target):
        return [n for n in range(len(NOTES)) if self.blocks[target][n] != other.blocks[target][n]]

    def to_messages(self, device_id=sysex.DEVICE_ID):
        return [sysex.dt1(target_address(t), bytes(self.blocks[t]), device_id) for t in range(TARGETS)]

    @staticmethod
    def requests(device_id=sysex.DEVICE_ID):
        return [sysex.rq1(target_address(t), block_size(), device_id) for t in range(TARGETS)]

    def apply(self, message):
        """Apply a received DT1 if it is exactly one scale tune block. Returns True if it did."""
        if message.command != sysex.CMD_DT1 or len(message.data) != block_size():
            return False
        for target in range(TARGETS):
            if tuple(message.address) == target_address(target):
                self.blocks[target][:] = message.data
                return True
        return False
