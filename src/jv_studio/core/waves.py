"""The names of the JV-1010's waves (Qt-free), from `data/waves.json` (see `tools/import_wave_names.py` for where they come from).

A tone's wave is three parameters: Wave Group Type, Wave Group ID and Wave Number (0-254, which the unit's display calls 001-255). The Owner's Manual's table says
which (type, id) is which group; only groups whose (type, id) the manual gives can be looked up. Anything else (a board it doesn't list, a PCM group of the
JV-1080 family) is "unknown", never guessed at.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources


@dataclass(frozen=True)
class WaveGroup:
    key: str
    title: str
    type: int
    id: int | None  # None: the manual doesn't give this board's Group ID
    names: tuple[str, ...]

    def name(self, number):
        return self.names[number] if 0 <= number < len(self.names) else None


@lru_cache(maxsize=1)
def groups():
    raw = json.loads(resources.files("jv_studio").joinpath("data/waves.json").read_text(encoding="utf-8"))
    return tuple(WaveGroup(g["key"], g["title"], g["type"], g["id"], tuple(g["names"])) for g in raw["groups"])


def selectable_groups():
    """The groups whose (type, id) are known: the ones a picker can set and a name can be looked up for."""
    return tuple(g for g in groups() if g.id is not None)


def group_for(group_type, group_id):
    return next((g for g in selectable_groups() if (g.type, g.id) == (group_type, group_id)), None)


def describe(group_type, group_id, number):
    """'INT-A 003  Ac Piano2 pA' for a tone's wave, using the unit's 1-based display number; None when the group isn't one we have names for
    (or the number is outside it)."""
    group = group_for(group_type, group_id)
    name = group.name(number) if group else None
    return None if name is None else f"{group.title} {number + 1:03d}  {name}"
