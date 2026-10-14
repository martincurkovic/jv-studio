"""The JV-1010's parameter table (generated from the manual by tools/extract_params.py) and how to read, write and show a value (Qt-free).

A BLOCK is one fixed-size piece of memory the unit sends and receives whole (a patch common, a patch tone, ...). A block's bytes live in a plain
`bytearray`; `read`/`write` turn a parameter's bytes into a value and back, including values split over two 4-bit bytes ("nibbled") and
name strings. `format_value` is what a UI shows for a raw value.
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass(frozen=True)
class Choice:
    label: str
    jv1010: bool = True  # False: the manual puts it in <> (a JV-1080/2080/XP value the JV-1010 ignores)


@dataclass(frozen=True)
class Param:
    key: str
    name: str
    offset: int  # data index inside its block
    size: int  # bytes
    min: int
    max: int
    nibbled: bool = False
    string: bool = False
    display_min: int | None = None
    display_max: int | None = None
    display_text: str | None = None
    labels: tuple[str, ...] = ()
    choices: tuple[Choice, ...] = ()
    footnote: int | None = None
    jv1080_only: bool = False  # the whole parameter is a JV-1080-family one the JV-1010 ignores
    side_table: bool = False  # its meaning depends on another table (the wave group / patch group tables)

    def has_choices(self):
        return bool(self.choices or self.labels)

    def choice_labels(self):
        return [c.label for c in self.choices] if self.choices else list(self.labels)


@dataclass(frozen=True)
class Block:
    key: str
    section: str
    size: int
    params: tuple[Param, ...]
    footnotes: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "_by_key", {p.key: p for p in self.params})

    def param(self, key):
        return self._by_key[key]

    def param_list(self):
        return self.params

    def __contains__(self, key):
        return key in self._by_key

    def new_buffer(self):
        return bytearray(self.size)


@dataclass(frozen=True)
class MemoryEntry:
    address: tuple[int, int, int, int]
    name: str
    section: str | None


@dataclass(frozen=True)
class FactoryPatch:
    number: int  # 1-128
    name: str
    voices: int  # tones in use, as the manual's Patch List gives it
    key_assign: str  # "POLY" or "SOLO"


@dataclass(frozen=True)
class PresetPatch:
    name: str
    voices: int
    key_assign: str | None  # "POLY" or "SOLO"; None for the Session board's list (the manual doesn't give it)


@dataclass(frozen=True)
class EfxParam:
    n: int  # 1-12: which of the patch's EFX Parameter 1-12 it is
    name: str | None  # None: "(not used)" by this effect type
    min: int = 0
    max: int = 127


@dataclass(frozen=True)
class CategoryPatch:
    """One entry of the manual's Patch Category List: the number the unit shows in the category, and where the patch lives (group "PR-A".."PR-E"/"XP-A", number from 1)."""

    no: int
    name: str
    group: str
    number: int


@dataclass(frozen=True)
class EfxType:
    number: int  # 1-40, as the unit's display shows it (the EFX Type parameter holds number - 1)
    name: str
    params: tuple[EfxParam, ...]

    def param(self, n):
        """What EFX Parameter `n` (1-12) means for this type: an `EfxParam`, with name None when the type doesn't use it (or has fewer than n parameters)."""
        return self.params[n - 1] if 1 <= n <= len(self.params) else EfxParam(n, None)


@dataclass(frozen=True)
class ParameterTable:
    model_id: int
    device_id: int
    blocks: dict
    memory_map: tuple[MemoryEntry, ...]
    factory_user_patches: tuple[FactoryPatch, ...] = ()
    efx_types: tuple[EfxType, ...] = ()
    preset_patches: dict = field(default_factory=dict)  # "PR-A".."PR-E", "XP-A" -> tuple[PresetPatch]
    patch_categories: dict = field(default_factory=dict)  # "PIANO".."RHYTHM&SFX" -> tuple[CategoryPatch], in the unit's order

    def efx_type(self, value):
        """The EfxType for the EFX Type parameter's raw value (0-39), or None outside that."""
        return self.efx_types[value] if 0 <= value < len(self.efx_types) else None

    def block(self, key):
        return self.blocks[key]


def _param(raw):
    return Param(
        key=raw["key"],
        name=raw["name"],
        offset=raw["offset"],
        size=raw["bytes"],
        min=raw["min"],
        max=raw["max"],
        nibbled=raw.get("nibbled", False),
        string=raw.get("string", False),
        display_min=raw.get("display_min"),
        display_max=raw.get("display_max"),
        display_text=raw.get("display_text"),
        labels=tuple(raw.get("labels", ())),
        choices=tuple(Choice(c["label"], c["jv1010"]) for c in raw.get("choices", ())),
        footnote=raw.get("footnote"),
        jv1080_only=raw.get("jv1080_only", False),
        side_table=raw.get("side_table", False),
    )


@lru_cache(maxsize=1)
def load_table():
    raw = json.loads(resources.files("jv_studio").joinpath("data/parameters.json").read_text(encoding="utf-8"))
    blocks = {
        key: Block(key, b["section"], b["size"], tuple(_param(p) for p in b["params"]), {int(n): t for n, t in b["footnotes"].items()})
        for key, b in raw["blocks"].items()
    }
    memory = tuple(MemoryEntry(tuple(int(x, 16) for x in e["address"].split()), e["name"], e["section"]) for e in raw["memory_map"])
    factory = tuple(FactoryPatch(f["number"], f["name"], f["voices"], f["key_assign"]) for f in raw.get("factory_user_patches", ()))
    efx = tuple(
        EfxType(t["number"], t["name"], tuple(EfxParam(p["n"], p["name"], p.get("min", 0), p.get("max", 127)) for p in t["params"]))
        for t in raw.get("efx_types", ())
    )
    presets = {group: tuple(PresetPatch(e["name"], e["voices"], e["key_assign"]) for e in entries) for group, entries in raw.get("preset_patches", {}).items()}
    categories = {name: tuple(CategoryPatch(e["no"], e["name"], e["group"], e["number"]) for e in entries) for name, entries in raw.get("patch_categories", {}).items()}
    return ParameterTable(int(raw["model_id"], 16), int(raw["device_id"], 16), blocks, memory, factory, efx, presets, categories)


# -- reading and writing values ------------------------------------------------------------------------------------------


def clamp(param, value):
    return max(param.min, min(param.max, int(value)))


def read(block_bytes, param):
    """The value of `param` in a block's bytes: an int, or a str for a name."""
    raw = block_bytes[param.offset : param.offset + param.size]
    if param.string:
        return "".join(chr(b) if 32 <= b <= 125 else " " for b in raw).rstrip()
    if param.nibbled:
        return (raw[0] << 4) | (raw[1] & 0x0F)
    return raw[0]


def write(block_bytes, param, value):
    """Store `value` (clamped to the parameter's range) into a block's bytes. Returns the value actually stored."""
    if param.string:
        text = str(value)[: param.size].ljust(param.size)
        block_bytes[param.offset : param.offset + param.size] = bytes(ord(c) if 32 <= ord(c) <= 125 else 32 for c in text)
        return text.rstrip()
    value = clamp(param, value)
    if param.nibbled:
        block_bytes[param.offset : param.offset + 2] = bytes([(value >> 4) & 0x0F, value & 0x0F])
    else:
        block_bytes[param.offset] = value
    return value


def param_bytes(block_bytes, param):
    return bytes(block_bytes[param.offset : param.offset + param.size])


# -- showing a value ----------------------------------------------------------------------------------------------------


_MIDDLE_C_OCTAVE = 4  # which octave number note 60 is in: 4 is Roland's (the manual's "C-1 - G9", its Rhythm Set List: key 36 = C2), 3 is Ableton's and Yamaha's


def set_middle_c(octave):
    """Name note 60 `C<octave>`: 4 (Roland, as the manual and the unit) or 3 (Ableton, Yamaha). Only the NAMES change, never a note number. Call it once at start-up, before any
    widget shows or parses a note name (the app reads it from the settings in `main`)."""
    global _MIDDLE_C_OCTAVE
    if octave not in (3, 4):
        raise ValueError(f"middle C is C3 or C4, not C{octave}")
    _MIDDLE_C_OCTAVE = octave


def middle_c_octave():
    return _MIDDLE_C_OCTAVE


def note_name(note):
    """The name of a MIDI note: Roland's convention by default (the manual's "C-1 - G9": note 60 is C4); `set_middle_c(3)` makes it Ableton's (60 is C3)."""
    return f"{_NOTE_NAMES[note % 12]}{note // 12 - 1 + (_MIDDLE_C_OCTAVE - 4)}"


def format_value(param, value):
    """What a person reads for a raw value: a choice's name, the displayed number (+1, -63...), a pan, a note..."""
    if param.string:
        return str(value)
    if param.choices and 0 <= value - param.min < len(param.choices):
        return param.choices[value - param.min].label
    if param.labels and 0 <= value - param.min < len(param.labels):
        return param.labels[value - param.min]
    if param.key == "master_tune":  # the manual's range 427.4-452.6 Hz over 0-126, in steps of 0.2 Hz: 63 is A = 440.0
        return f"{427.4 + 0.2 * value:.1f} Hz"
    if param.key.startswith("preview_velocity_set_") and value == 0:  # "OFF, 1-127"
        return "OFF"
    text = param.display_text or ""
    if re.fullmatch(r"L6[34] - 6[34]R", text):  # pan: centre is 64 on a 0-127 scale, 63 on 1-127 ("L63 - 63R" is 1-127, centre 64)
        centre = 64
        if value == centre:
            return "0"
        return f"L{centre - value}" if value < centre else f"{value - centre}R"
    if text == "C-1 - G9":
        return note_name(value)
    if text.startswith("OFF,1 - "):  # "OFF,1 - 3": 0 is OFF, the rest count from 1
        return "OFF" if value == 0 else str(value)
    if text == "1 - 16,OFF":  # a MIDI channel, 17 is OFF
        return "OFF" if value >= 16 else str(value + 1)
    if param.display_min is not None and param.max != param.min:
        shown = param.display_min + (value - param.min) * (param.display_max - param.display_min) / (param.max - param.min)
        shown = round(shown)
        return f"{shown:+d}" if shown and param.display_min < 0 else str(shown)
    return str(value)
