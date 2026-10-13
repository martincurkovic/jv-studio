import pytest

from jv_studio.core import params, performance as perf, sysex, validate


def test_a_minimum_performance_is_valid_and_named():
    p = perf.Performance.minimum()
    assert p.name == "INIT PERF" and validate.out_of_range_performance(p) == []
    assert len(p.common) == 66 and len(p.parts) == 16 and all(len(x) == 25 for x in p.parts)


def test_values_of_the_common_block_and_a_part():
    p = perf.Performance.minimum()
    p.set(perf.COMMON, "performance_tempo", 132)
    p.set(perf.PART, "midi_channel", 9, part=9)
    p.set(perf.PART, "part_level", 99, part=3)
    assert p.get(perf.COMMON, "performance_tempo") == 132 and p.get(perf.PART, "midi_channel", part=9) == 9
    assert p.get(perf.PART, "part_level", part=3) == 99 and p.get(perf.PART, "part_level", part=4) == 0
    with pytest.raises(ValueError):
        p.get(perf.PART, "part_level")


def test_a_patch_assignment_is_three_parameters_and_a_nibbled_number():
    p = perf.Performance.minimum()
    p.set(perf.PART, "patch_group_id", 3, part=0)
    p.set(perf.PART, "patch_number", 200, part=0)
    assert p.get(perf.PART, "patch_number", part=0) == 200
    number = params.load_table().block(perf.PART).param("patch_number")
    assert p.parts[0][number.offset : number.offset + 2] == bytes([200 >> 4, 200 & 0x0F])  # high nibble first


def test_addresses_follow_the_manual():
    assert perf.user_base(0) == (0x10, 0, 0, 0) and perf.user_base(31) == (0x10, 0x1F, 0, 0)
    assert perf.part_offset(0) == 0x10 << 7 and sysex.add_to_address(perf.TEMPORARY_BASE, perf.part_offset(15)) == (1, 0, 0x1F, 0)  # offset 1F 00: the THIRD address byte counts the parts
    with pytest.raises(ValueError):
        perf.user_base(32)


def test_a_performance_is_seventeen_messages_that_round_trip_through_syx():
    p = perf.Performance.minimum()
    p.name = "Round Trip"
    p.set(perf.PART, "part_pan", 100, part=15)
    messages = p.to_messages(perf.user_base(5))
    assert len(messages) == 17 and all(len(m) <= 140 for m in messages)
    parsed = perf.parse_syx(p.to_syx(perf.user_base(5)))
    assert list(parsed) == [perf.user_base(5)] and parsed[perf.user_base(5)] == p


def test_the_requests_use_each_blocks_own_address_and_size():
    requests = perf.Performance.requests(perf.TEMPORARY_BASE)
    assert len(requests) == 17
    first, second = sysex.parse(requests[0]), sysex.parse(requests[1])
    assert (first.address, first.size) == ((1, 0, 0, 0), 66) and (second.address, second.size) == ((1, 0, 0x10, 0), 25)


def test_patch_files_and_other_addresses_are_not_mistaken_for_performances():
    from jv_studio.core import patch

    assert perf.parse_syx(patch.Patch.minimum().to_syx(patch.user_base(3))) == {}
    assert perf.parse_syx(sysex.dt1((0x10, 0x40, 0, 0), b"\x20" * 12)) == {}  # a USER rhythm setup


def test_out_of_range_values_are_reported_per_part():
    p = perf.Performance.minimum()
    p.parts[4][params.load_table().block(perf.PART).param("part_level").offset] = 127
    p.parts[7][params.load_table().block(perf.PART).param("midi_channel").offset] = 99
    problems = validate.out_of_range_performance(p)
    assert [(x.tone, x.key) for x in problems] == [(7, "midi_channel")]
