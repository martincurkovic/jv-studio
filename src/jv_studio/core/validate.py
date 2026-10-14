"""Check a patch read from a real unit against the parameter table (Qt-free).

A value the unit returns outside the range the manual gives means the table, the parser or our reading is wrong somewhere: the first reads from
real hardware are a free test of the whole generated table. Strings are checked for characters outside the unit's ASCII range."""

from dataclasses import dataclass

from . import groups, params, patch, performance, rhythm, system


@dataclass(frozen=True)
class Problem:
    block: str
    tone: int | None  # 0-3 for a tone parameter (a part 0-15, or the MIDI key 35-98 of a rhythm note)
    key: str
    name: str
    value: object
    expected: str  # the range or character set it should be in

    def __str__(self):
        if self.tone is None:
            where = self.block
        elif self.block == rhythm.NOTE:
            where = f"{self.block} key {self.tone}"  # (the MIDI key, 35-98)
        else:
            where = f"{self.block} tone {self.tone + 1}"
        return f"{where}: {self.name} = {self.value!r} (expected {self.expected})"


def _check(block, buffer, tone):
    problems = []
    for param in block.params:
        raw = params.param_bytes(buffer, param)
        if param.string:
            bad = [b for b in raw if not 32 <= b <= 125]
            if bad:
                problems.append(Problem(block.key, tone, param.key, param.name, bytes(raw).hex(" "), "ASCII 32-125"))
            continue
        value = params.read(buffer, param)
        usable = param.max - param.min + 1
        if param.choices:
            usable = len(param.choices)
        if not param.min <= value <= param.max or (param.choices and value - param.min >= usable):
            problems.append(Problem(block.key, tone, param.key, param.name, value, f"{param.min}-{param.min + usable - 1}"))
    return problems


def out_of_range(p):
    """Every parameter of patch `p` whose stored value is outside the manual's range (an empty list for a healthy patch)."""
    table = params.load_table()
    problems = _check(table.block(patch.COMMON), p.common, None)
    for i, tone in enumerate(p.tones):
        problems += _check(table.block(patch.TONE), tone, i)
    return problems


def out_of_range_system(s):
    """Every System parameter whose stored value is outside the manual's range (the block is reported as `tone` None)."""
    block = params.load_table().block(system.COMMON)
    flagged = _check(block, s.common, None)
    return [p for p in flagged if groups.supported(block.param(p.key)) and (system.COMMON, p.key) not in groups.UNUSED]  # (the JV-1080 family's parameters, which the JV-1010 ignores, are not its business)


def out_of_range_performance(p):
    """Every parameter of performance `p` whose stored value is outside the manual's range (the part is reported in `tone`, 0-15)."""
    table = params.load_table()
    problems = _check(table.block(performance.COMMON), p.common, None)
    for i, part in enumerate(p.parts):
        problems += _check(table.block(performance.PART), part, i)
    return problems


def out_of_range_rhythm(r):
    """Every parameter of rhythm set `r` whose stored value is outside the manual's range (the key is reported in `tone`, 35-98)."""
    table = params.load_table()
    problems = _check(table.block(rhythm.COMMON), r.common, None)
    for key, note in r.notes.items():
        problems += _check(table.block(rhythm.NOTE), note, key)
    return problems
