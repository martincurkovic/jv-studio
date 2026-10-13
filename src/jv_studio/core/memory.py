"""The JV-1010's whole user memory as a list of blocks (Qt-free): what a full backup reads and a restore writes.

From the manual's Parameter Address Map (the memory map at p.74 and each section's index table). Offsets inside a section are 7-bit address bytes, so
"part 1 at 10 00" is +0x10 in the third address byte:

    System        00 00 00 00   common 00 00 | part 1-16 scale tune 10 00..1F 00 | patch mode scale tune 20 00
    Performances  10 nn 00 00   nn = 00..1F (USER:01-32): common 00 00 | part 1-16 at 10 00..1F 00
    Rhythm setups 10 40|41 00 00 (USER:1-2): common 00 00 | note for key 35..98 at 23 00..62 00
    Patches       11 nn 00 00   nn = 00..7F (USER:001-128): common 00 00 | tone 1-4 at 10 00, 12 00, 14 00, 16 00

The temporary areas (01.., 02.., 03..) are the unit's edit buffers, not stored memory: a backup does not include them.
"""

from dataclasses import dataclass

from . import params, patch, sysex

SYSTEM = "system"
PERFORMANCES = "performances"
RHYTHM = "rhythm"
PATCHES = "patches"
SECTIONS = (SYSTEM, PERFORMANCES, RHYTHM, PATCHES)  # the order they are read; restore writes the system last

SECTION_TITLES = {SYSTEM: "System settings", PERFORMANCES: "USER performances", RHYTHM: "USER rhythm setups", PATCHES: "USER patches"}

PERFORMANCE_COUNT = 32
RHYTHM_COUNT = 2
PERFORMANCE_PARTS = 16
RHYTHM_NOTES = range(35, 99)  # keys 35-98


@dataclass(frozen=True)
class MemBlock:
    section: str
    label: str  # for messages: "USER:007 patch tone 2"
    address: sysex.Address
    size: int
    kind: str  # the parameter-table block describing it (patch_common, patch_tone, ...)

    @property
    def start(self):
        return sysex.address_to_int(self.address)

    @property
    def end(self):
        return self.start + self.size


def _size(kind):
    return params.load_table().block(kind).size


def _block(section, label, base, offset, kind):
    return MemBlock(section, label, sysex.add_to_address(base, offset), _size(kind), kind)


def plan(sections=SECTIONS):
    """Every block of the chosen sections, in the order a backup reads them."""
    blocks = []
    if SYSTEM in sections:
        base = (0, 0, 0, 0)
        blocks.append(_block(SYSTEM, "system common", base, 0, "system_common"))
        for part in range(PERFORMANCE_PARTS):
            blocks.append(_block(SYSTEM, f"part {part + 1} scale tune", base, (0x10 + part) << 7, "scale_tune"))
        blocks.append(_block(SYSTEM, "patch mode scale tune", base, 0x20 << 7, "scale_tune"))
    if PERFORMANCES in sections:
        for n in range(PERFORMANCE_COUNT):
            base = (0x10, n, 0, 0)
            blocks.append(_block(PERFORMANCES, f"USER performance {n + 1:02d} common", base, 0, "performance_common"))
            for part in range(PERFORMANCE_PARTS):
                blocks.append(_block(PERFORMANCES, f"USER performance {n + 1:02d} part {part + 1}", base, (0x10 + part) << 7, "performance_part"))
    if RHYTHM in sections:
        for n in range(RHYTHM_COUNT):
            base = (0x10, 0x40 + n, 0, 0)
            blocks.append(_block(RHYTHM, f"USER rhythm {n + 1} common", base, 0, "rhythm_common"))
            for key in RHYTHM_NOTES:
                blocks.append(_block(RHYTHM, f"USER rhythm {n + 1} key {key}", base, key << 7, "rhythm_note"))
    if PATCHES in sections:
        for n in range(patch.USER_PATCH_COUNT):
            base = patch.user_base(n)
            blocks.append(_block(PATCHES, f"USER:{n + 1:03d} common", base, 0, "patch_common"))
            for tone in range(patch.TONE_COUNT):
                blocks.append(_block(PATCHES, f"USER:{n + 1:03d} tone {tone + 1}", base, patch.tone_offset(tone), "patch_tone"))
    return blocks


def total_bytes(blocks):
    return sum(b.size for b in blocks)
