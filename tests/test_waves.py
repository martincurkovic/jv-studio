from jv_studio.core import waves


def test_the_groups_match_the_manuals_ranges():
    by_key = {g.key: g for g in waves.groups()}
    assert len(by_key["int_a"].names) == 255 and len(by_key["int_b"].names) == 193 and len(by_key["session"].names) == 206
    assert (by_key["int_a"].type, by_key["int_a"].id) == (0, 1) and (by_key["session"].type, by_key["session"].id) == (2, 9)
    assert by_key["vintage"].id is None  # the manual doesn't say, so it is never looked up
    assert [g.key for g in waves.selectable_groups()] == ["int_a", "int_b", "session"]


def test_a_wave_is_looked_up_by_type_id_and_number():
    assert waves.describe(0, 1, 0) == "INT-A 001  Ac Piano 1A"
    assert waves.describe(0, 1, 3) == "INT-A 004  Ac Piano2 pA"
    assert waves.describe(0, 2, 0) == "INT-B 001  Kalimba"
    assert waves.describe(2, 9, 0).startswith("SR-JV80-09 Session 001")


def test_unknown_groups_and_numbers_are_none_not_guessed():
    assert waves.describe(2, 4, 0) is None  # (the Vintage Synth board: ID unknown)
    assert waves.describe(1, 5, 0) is None  # a PCM group
    assert waves.describe(0, 2, 193) is None  # INT-B stops at 192
    assert waves.describe(0, 1, -1) is None
