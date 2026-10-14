"""Hear the unit from the app (Qt-free): notes, Bank Select + Program Change for choosing a patch, and a look at the unit's MIDI settings.

Plain channel messages, nothing is written to the unit's memory. Choosing a patch by Program Change CHANGES THE UNIT'S CURRENT (temporary) PATCH, which is why the window then
treats the shown patch as no longer in step with the unit. The bank table is the manual's "Bank Select" table (MIDI Implementation, p.68) [manual]:

    User 80/0 | PR-A 81/0 | PR-B 81/1 | PR-C 81/2 | PR-D (GM) 81/3 | PR-E 81/4 | Session (XP-A) 84/0 (patches 1-128) and 84/1 (patches 129-255)    (MSB/LSB, program 0-127)

The unit only acts on them in PATCH mode, with Receive Program Change and Receive Bank Select (System) ON, on the Patch Receive Channel (System); in GM mode Bank Select is ignored.
"""

from dataclasses import dataclass

from . import params

#: patch group key (core/patch_groups.py) -> [(bank MSB, bank LSB, how many patches, first patch number)]
BANKS = {
    "USER": [(80, 0, 128, 0)],
    "PR-A": [(81, 0, 128, 0)],
    "PR-B": [(81, 1, 128, 0)],
    "PR-C": [(81, 2, 128, 0)],
    "PR-D": [(81, 3, 128, 0)],
    "PR-E": [(81, 4, 128, 0)],
    "XP-A": [(84, 0, 128, 0), (84, 1, 127, 128)],
}

DEFAULT_VELOCITY = 100
VELOCITY_STEPS = [1, *range(10, 121, 10), 127]  # what C and V walk through: multiples of 10, with the two ends of the range kept


def step_velocity(current, direction):
    """Snap `current` to the nearest stop on VELOCITY_STEPS (a tie goes up), then move one stop up (direction > 0) or down: 97 -> 100 -> 110 or 90."""
    index = VELOCITY_STEPS.index(min(VELOCITY_STEPS, key=lambda v: (abs(v - current), -v)))
    return VELOCITY_STEPS[max(0, min(len(VELOCITY_STEPS) - 1, index + (1 if direction > 0 else -1)))]


SOUND_MODES = {0: "Performance", 1: "Patch", 2: "GM"}


def _channel(channel):
    if not 0 <= channel <= 15:
        raise ValueError(f"MIDI channel {channel} (0-15 here; the screen shows 1-16)")
    return channel


def _data(value, what):
    if not 0 <= value <= 127:
        raise ValueError(f"{what} {value} is outside 0-127")
    return value


def note_on(channel, note, velocity=DEFAULT_VELOCITY):
    return bytes([0x90 | _channel(channel), _data(note, "note"), max(1, _data(velocity, "velocity"))])  # (velocity 0 would be a note-off)


def note_off(channel, note):
    return bytes([0x80 | _channel(channel), _data(note, "note"), 0])


def control_change(channel, controller, value):
    return bytes([0xB0 | _channel(channel), _data(controller, "controller"), _data(value, "value")])


def program_change(channel, program):
    return bytes([0xC0 | _channel(channel), _data(program, "program")])


def panic(channel):
    """Silence a channel: hold pedal up, All Sound Off, All Notes Off (CC 64, 120, 123)."""
    return [control_change(channel, 64, 0), control_change(channel, 120, 0), control_change(channel, 123, 0)]


def patch_select(channel, group_key, number):
    """The messages that choose patch `number` (0-based) of the group `group_key` ("USER", "PR-A"..."PR-E", "XP-A"): Bank Select MSB, LSB, then Program Change.
    Raises ValueError for a group or number the manual's table doesn't give."""
    for msb, lsb, count, first in BANKS.get(group_key, ()):
        if first <= number < first + count:
            return [control_change(channel, 0, msb), control_change(channel, 32, lsb), program_change(channel, number - first)]
    raise ValueError(f"no Bank Select / Program Change for patch {number + 1} of {group_key!r}")


#: rhythm sets by Bank Select (MSB, LSB) and how many each holds, [manual p.68 and the Quick Start, "Changing a Rhythm Set"]: the Program Change counts from 0 in each
RHYTHM_BANKS = {"USER": (80, 0, 2), "PR-A": (81, 0, 2), "PR-B": (81, 1, 2), "PR-C": (81, 2, 2), "PR-D": (81, 3, 2), "PR-E": (81, 4, 2), "XP-A": (84, 0, 8)}


def rhythm_select(channel, group_key, number):
    """The messages that choose rhythm set `number` (0-based) of `group_key` on the channel of Part 10: Bank Select MSB, LSB, Program Change. ValueError if the table has no such set."""
    msb, lsb, count = RHYTHM_BANKS.get(group_key, (0, 0, 0))
    if not 0 <= number < count:
        raise ValueError(f"no Bank Select / Program Change for rhythm set {number + 1} of {group_key!r}")
    return [control_change(channel, 0, msb), control_change(channel, 32, lsb), program_change(channel, number)]


def note_name(note):
    """C4 is 60 here, as on the unit (the manual: note 0 is C-1)."""
    return params.note_name(note)


# -- the unit's own settings that decide whether this works -------------------------------------------------------------------


@dataclass(frozen=True)
class SystemMidi:
    """What the System block says about receiving notes and patch changes."""

    channel: int  # 0-15: the Patch Receive Channel
    program_change: bool
    bank_select: bool
    sound_mode: int  # 0 performance, 1 patch, 2 GM
    group_type: int = -1  # the patch the unit has selected (Patch mode): the System block's Patch Group Type, Patch Group ID and Patch Number (0-based); -1 = not read
    group_id: int = -1
    patch_number: int = -1

    @property
    def mode_name(self):
        return SOUND_MODES.get(self.sound_mode, "unknown")

    def problems(self):
        """What would stop the keyboard or a patch choice from working, in a few words each."""
        out = []
        if self.sound_mode == 0:
            out.append("The unit is in Performance mode: notes play the parts on their own channels, and patch changes go to the parts.")
        elif self.sound_mode == 2:
            out.append("The unit is in GM mode: it ignores Bank Select, so only General MIDI sounds can be chosen.")
        if not self.program_change:
            out.append("Receive Program Change is OFF on the unit: patches can't be chosen from here.")
        if self.sound_mode != 2 and not self.bank_select:
            out.append("Receive Bank Select is OFF on the unit: only patches in the current bank can be chosen.")
        return out


def parse_system_common(block):
    """A `SystemMidi` from the System common block's bytes (102 of them)."""
    table = params.load_table().block("system_common")

    def value(key):
        return params.read(block, table.param(key))

    return SystemMidi(
        channel=max(0, min(15, value("patch_receive_channel"))),
        program_change=bool(value("receive_program_change")),
        bank_select=bool(value("receive_bank_select")),
        sound_mode=value("sound_mode"),
        group_type=value("patch_group_type"),
        group_id=value("patch_group_id"),
        patch_number=value("patch_number"),
    )
