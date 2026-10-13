"""The unit's SYSTEM settings (Qt-free): the System common block (master tune, receive switches, controller sources, the unit's current mode and selection) and how it travels.

The block is 102 bytes at address 00 00 00 00 (manual, "Parameter Address Map" 1-1-1), one DT1. Only the parameters the JV-1010 has are editable (`core/groups.py` leaves out the
JV-1080 family's, which the manual puts in angle brackets). The per-part scale tune blocks that follow it in the address map are not modelled here yet.
"""

from dataclasses import dataclass

from . import params, patch_groups, sysex

BASE = (0x00, 0x00, 0x00, 0x00)
COMMON = "system_common"

#: sound mode values (the table's choice order)
PERFORMANCE_MODE, PATCH_MODE, GM_MODE = 0, 1, 2


def _table():
    return params.load_table().block(COMMON)


@dataclass
class System:
    common: bytearray

    @classmethod
    def blank(cls):
        return cls(_table().new_buffer())

    @classmethod
    def minimum(cls):
        """Every parameter at the bottom of its range: always VALID, never a sensible setting (the same idea as `Patch.minimum`)."""
        result = cls.blank()
        for param in _table().param_list():
            params.write(result.common, param, param.min)
        return result

    def copy(self):
        return System(bytearray(self.common))

    def __eq__(self, other):
        return isinstance(other, System) and self.common == other.common

    def get(self, key):
        return params.read(self.common, _table().param(key))

    def set(self, key, value):
        """Set a parameter; returns the (clamped) value stored."""
        return params.write(self.common, _table().param(key), value)

    # -- sysex -----------------------------------------------------------------------------------------------------------

    def to_messages(self, device_id=sysex.DEVICE_ID):
        return sysex.dt1_packets(BASE, self.common, device_id)

    def to_syx(self):
        return b"".join(self.to_messages())

    @staticmethod
    def request(device_id=sysex.DEVICE_ID):
        return sysex.rq1(BASE, _table().size, device_id)

    def apply(self, message):
        """Apply a received DT1 if it lies inside the block. Returns True if it did."""
        if message.command != sysex.CMD_DT1:
            return False
        start = sysex.address_to_int(message.address) - sysex.address_to_int(BASE)
        if 0 <= start and start + len(message.data) <= len(self.common):
            self.common[start : start + len(message.data)] = message.data
            return True
        return False

    # -- reading it as a person would ------------------------------------------------------------------------------------

    def mode_name(self):
        return {PERFORMANCE_MODE: "Performance mode", PATCH_MODE: "Patch mode", GM_MODE: "GM mode"}.get(self.get("sound_mode"), "an unknown mode")

    def current_patch(self, user_names=None):
        return patch_groups.describe(self.get("patch_group_type"), self.get("patch_group_id"), self.get("patch_number"), user_names)

    def current_performance(self):
        return describe_performance(self.get("performance_number"))

    def selection_text(self, user_names=None):
        """What the unit says it is playing: "Patch mode: USER 005  Name", "Performance mode: USER 03", or "GM mode"."""
        mode = self.get("sound_mode")
        if mode == PATCH_MODE:
            return f"{self.mode_name()}: {self.current_patch(user_names)}"
        if mode == PERFORMANCE_MODE:
            return f"{self.mode_name()}: {self.current_performance()}"
        return self.mode_name()


def describe_performance(number):
    """The manual's Performance Number table: 0-31 USER, 32-63 CARD (a JV-1080 slot the JV-1010 doesn't have), 64-95 PR-A, 96-127 PR-B."""
    for first, name in ((0, "USER"), (32, "CARD"), (64, "PR-A"), (96, "PR-B")):
        if first <= number < first + 32:
            return f"{name} {number - first + 1:02d}"
    return f"performance {number}"


def changes(old, new):
    """[(key, old value, new value)] for every parameter that differs between two `System`s, in table order."""
    return [(p.key, old.get(p.key), new.get(p.key)) for p in _table().param_list() if old.get(p.key) != new.get(p.key)]
