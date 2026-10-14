"""Which patch a performance part plays (Qt-free): the manual's "Patch Group" table plus the names of the ROM groups.

A part names its patch with three parameters: Patch Group Type, Patch Group ID and Patch Number (0-based; the unit's display counts from 001). The manual's table:
USER is type 0 id 1 (128 patches); CARD (type 0 id 2, a JV-80 card slot the JV-1010 doesn't have); PR-A to PR-E are type 0 ids 3-7 (128 each, PR-D is the General MIDI
group); the Session board (XP-A) is type 2 id 9 (255). Other ids (more boards, the JV-1080 family's PCM cards) are "unknown": shown by number, never guessed at.
The names of PR-A to PR-E and Session are the manual's lists (ROM, fixed); the USER names are whatever is on the unit, so the caller passes what it has read.
"""

from dataclasses import dataclass

from . import params


@dataclass(frozen=True)
class PatchGroup:
    key: str  # "USER", "PR-A", "XP-A"
    title: str
    type: int
    id: int
    count: int


GROUPS = (
    PatchGroup("USER", "USER", 0, 1, 128),
    PatchGroup("PR-A", "Preset A", 0, 3, 128),
    PatchGroup("PR-B", "Preset B", 0, 4, 128),
    PatchGroup("PR-C", "Preset C", 0, 5, 128),
    PatchGroup("PR-D", "Preset D (GM)", 0, 6, 128),
    PatchGroup("PR-E", "Preset E", 0, 7, 128),
    PatchGroup("XP-A", "Session", 2, 9, 255),
)

#: what each group IS, from the Owner's Manual ("Choosing and Playing Patches"); the manual gives no theme for the individual banks, so none is made up here
GROUP_HELP = {
    "USER": "Your 128 patches: the only ones that can be overwritten.",
    "PR-A": "Preset A: 128 factory patches (read-only). The unit's display calls it PrA.",
    "PR-B": "Preset B: 128 factory patches (read-only). The unit's display calls it PrB.",
    "PR-C": "Preset C: 128 factory patches (read-only). The unit's display calls it PrC.",
    "PR-D": "Preset D: the 128 General MIDI patches (read-only). The unit's display calls it PrD (GM).",
    "PR-E": "Preset E: 128 factory patches (read-only). The unit's display calls it PrE.",
    "XP-A": "Session: 255 patches from the SR-JV80-09 Wave Expansion Board built into the unit (read-only).",
}


def group_for(group_type, group_id):
    return next((g for g in GROUPS if (g.type, g.id) == (group_type, group_id)), None)


def names_of(group, user_names=None):
    """The patch names of `group` (a list, one per patch), or None when they aren't known: USER's come from the unit (`user_names`), the others from the manual."""
    if group.key == "USER":
        return list(user_names) if user_names else None
    return [p.name for p in params.load_table().preset_patches.get(group.key, ())] or None


def name_of(group_type, group_id, number, user_names=None):
    group = group_for(group_type, group_id)
    names = names_of(group, user_names) if group else None
    return names[number] if names and 0 <= number < len(names) else None


def describe(group_type, group_id, number, user_names=None):
    """"USER 005  ViennaStrgs3", "PR-A 012  Name", or just "USER 005" when the name isn't known, or "Group type 2, ID 4, patch 007" for a group we don't know."""
    group = group_for(group_type, group_id)
    if group is None:
        return f"Group type {group_type}, ID {group_id}, patch {number + 1:03d}"
    name = name_of(group_type, group_id, number, user_names)
    label = f"{group.key} {number + 1:03d}"
    return f"{label}  {name}" if name else label
