"""Is a USER patch the factory one? (Qt-free)

The manual's Patch List (p.100-ish; extracted into `parameters.json`) gives each factory USER patch's number, name and key assign mode. A unit bought
second hand may have had them overwritten. Comparing the name and key assign mode is only a hint: a patch can keep its name and change every
parameter, and a factory patch edited and saved under the same name looks stock here. Only a byte-for-byte comparison with a known-good dump proves it.
"""

from . import params

SAME = "same"
DIFFERENT = "different"


def _norm(text):
    return " ".join(text.replace("\u2019", "'").replace("\u2018", "'").split()).lower()


def compare_one(number, summary):
    """(status, FactoryPatch) for the summary of USER slot `number` (0-based)."""
    expected = params.load_table().factory_user_patches[number]
    same = _norm(summary.name) == _norm(expected.name) and summary.key_assign == expected.key_assign
    return (SAME if same else DIFFERENT, expected)


def compare(summaries):
    """[(status, FactoryPatch)] for each summary: SAME if the name and key assign match the factory patch in that slot, else DIFFERENT."""
    return [compare_one(number, summary) for number, summary in enumerate(summaries)]


def count_same(summaries):
    return sum(1 for status, _ in compare(summaries) if status == SAME)

