# The memory plan: every block of the unit's user memory, against the manual's map.

from jv_studio.core import memory, params, patch, sysex


def test_the_plan_counts_match_the_manual():
    blocks = memory.plan()
    by_section = {s: [b for b in blocks if b.section == s] for s in memory.SECTIONS}
    assert len(by_section[memory.SYSTEM]) == 1 + 16 + 1  # common, 16 part scale tunes, patch-mode scale tune
    assert len(by_section[memory.PERFORMANCES]) == 32 * (1 + 16)
    assert len(by_section[memory.RHYTHM]) == 2 * (1 + 64)  # keys 35-98
    assert len(by_section[memory.PATCHES]) == 128 * (1 + 4)


def test_blocks_never_overlap_and_are_unique():
    blocks = sorted(memory.plan(), key=lambda b: b.start)
    for a, b in zip(blocks, blocks[1:]):
        assert a.end <= b.start, (a.label, b.label)
    assert len({b.address for b in blocks}) == len(blocks)


def test_every_block_is_inside_a_region_the_manual_lists():
    starts = {m.address for m in params.load_table().memory_map}
    assert (0, 0, 0, 0) in starts and (0x11, 0, 0, 0) in starts and (0x10, 0, 0, 0) in starts and (0x10, 0x40, 0, 0) in starts
    for b in memory.plan():
        assert b.address[0] in (0x00, 0x10, 0x11)  # system, USER performances/rhythm, USER patches - never the temporary areas
        assert all(0 <= x < 128 for x in b.address)


def test_spot_addresses_against_the_manuals_examples():
    by_label = {b.label: b for b in memory.plan()}
    # "the starting address of USER:03 is 10 02 00 00H, and the offset address of Performance Part 3 is 12 00H"
    assert by_label["USER performance 03 part 3"].address == (0x10, 0x02, 0x12, 0x00) and by_label["USER performance 03 part 3"].size == 0x19
    assert by_label["USER:001 common"].address == (0x11, 0, 0, 0) and by_label["USER:001 common"].size == 0x4A
    assert by_label["USER:128 tone 4"].address == (0x11, 0x7F, 0x16, 0x00) and by_label["USER:128 tone 4"].size == 0x81
    assert by_label["USER rhythm 2 key 35"].address == (0x10, 0x41, 0x23, 0x00)
    assert by_label["USER rhythm 1 key 98"].address == (0x10, 0x40, 0x62, 0x00)
    assert by_label["part 16 scale tune"].address == (0, 0, 0x1F, 0x00) and by_label["patch mode scale tune"].address == (0, 0, 0x20, 0x00)


def test_the_patch_blocks_agree_with_the_patch_model():
    for n in (0, 57, 127):
        mine = [b for b in memory.plan([memory.PATCHES]) if b.label.startswith(f"USER:{n + 1:03d} ")]
        theirs = [(sysex.add_to_address(patch.user_base(n), off), len(buf)) for off, buf in patch.Patch.blank().blocks()]
        assert [(b.address, b.size) for b in mine] == theirs


def test_the_whole_memory_is_about_98_kilobytes():
    total = memory.total_bytes(memory.plan())
    assert total == 306 + 14912 + 7448 + 75520  # system + performances + rhythm + patches, from the block sizes
    assert memory.total_bytes(memory.plan([memory.PATCHES])) == 128 * (0x4A + 4 * 0x81)


def test_a_section_can_be_planned_alone():
    assert {b.section for b in memory.plan([memory.PATCHES])} == {memory.PATCHES}
    assert memory.plan([]) == []


def test_the_factory_list_is_in_the_table():
    factory = params.load_table().factory_user_patches
    assert len(factory) == 128 and [f.number for f in factory] == list(range(1, 129))
    assert (factory[0].name, factory[1].name, factory[127].name) == ("Tremendously", "St.Concert", "Crowds")
    assert {f.key_assign for f in factory} == {"POLY", "SOLO"} and all(1 <= f.voices <= 4 for f in factory)
    assert all(f.name.isascii() and len(f.name) <= 12 for f in factory)
