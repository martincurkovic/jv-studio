"""Check a patch read from a real unit against the parameter table (Qt-free).

A value the unit returns outside the range the manual gives means the table, the parser or our reading is wrong somewhere: the first reads from
real hardware are a free test of the whole generated table. Strings are checked for characters outside the unit's ASCII range."""

from dataclasses import dataclass

from . import params, patch, performance


@dataclass(frozen=True)
class Problem:
    block: str
    tone: int | None  # 0-3 for a tone parameter
    key: str
    name: str
    value: object
    expected: str  # the range or character set it should be in

    def __str__(self):
        where = f"{self.block}" + (f" tone {self.tone + 1}" if self.tone is not None else "")
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


def out_of_range_performance(p):
    """Every parameter of performance `p` whose stored value is outside the manual's range (the part is reported in `tone`, 0-15)."""
    table = params.load_table()
    problems = _check(table.block(performance.COMMON), p.common, None)
    for i, part in enumerate(p.parts):
        problems += _check(table.block(performance.PART), part, i)
    return problems
