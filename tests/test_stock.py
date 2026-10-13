from jv_studio.core import params, stock
from jv_studio.core.unit import PatchSummary


def factory_summaries():
    return [PatchSummary(f.name, f.key_assign) for f in params.load_table().factory_user_patches]


def test_a_factory_dump_matches_everywhere():
    assert stock.count_same(factory_summaries()) == 128


def test_a_renamed_or_changed_slot_is_flagged_and_names_the_factory_patch():
    s = factory_summaries()
    s[4] = PatchSummary("My Patch", s[4].key_assign)
    s[9] = PatchSummary(s[9].name, "SOLO" if s[9].key_assign == "POLY" else "POLY")
    result = stock.compare(s)
    assert stock.count_same(s) == 126 and result[4][0] == stock.DIFFERENT and result[9][0] == stock.DIFFERENT
    assert result[4][1].number == 5


def test_case_spacing_and_typographic_quotes_do_not_matter():
    s = factory_summaries()
    s[56] = PatchSummary("PLAYER’S  EP", s[56].key_assign)
    assert stock.compare(s)[56][0] == stock.SAME
