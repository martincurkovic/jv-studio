import pytest

from jv_studio.core import params, patch, patch_collection as pc, sysex


def named(name, level=0):
    p = patch.Patch.minimum()
    p.name = name
    p.set(patch.COMMON, "patch_level", level)
    return p


def whole_blocks(p, base, bad_checksum=False):
    """The 5 DT1 messages of a patch as a librarian writes them: every block whole (a tone as ONE 129-byte message), optionally with the checksum a buggy tool would put."""
    messages = []
    for offset, data in p.blocks():
        raw = bytearray(sysex.dt1(sysex.add_to_address(base, offset), bytes(data)))
        if bad_checksum:
            raw[-2] = (raw[-2] + 2) % 128
        messages.append(bytes(raw))
    return messages


def a_bank(*patches, base=patch.TEMPORARY_BASE, bad=()):
    return b"".join(b"".join(whole_blocks(p, base, bad_checksum=i in bad)) for i, p in enumerate(patches))


def test_a_check_free_parse_reads_a_message_whose_checksum_is_wrong():
    raw = bytearray(sysex.dt1((3, 0, 0, 0), [1, 2, 3]))
    raw[-2] ^= 0x01
    with pytest.raises(sysex.SysexError, match="bad checksum"):
        sysex.parse(bytes(raw))
    assert sysex.parse(bytes(raw), check_checksum=False).data == bytes([1, 2, 3])


def test_patches_that_all_say_temporary_patch_are_told_apart_by_their_order():
    stream = a_bank(named("First"), named("Second"), named("Third"))
    assert [p.name for p in patch.parse_syx(stream).values()] == ["Third"]  # the strict reader: the same address, the last one wins
    found = pc.parse(stream)
    assert [(e.index, e.patch.name, e.base, e.repaired) for e in found.entries] == [(1, "First", patch.TEMPORARY_BASE, 0), (2, "Second", patch.TEMPORARY_BASE, 0), (3, "Third", patch.TEMPORARY_BASE, 0)]
    assert found.incomplete == found.ignored == found.unusable == 0


def test_a_bank_with_one_address_per_patch_and_split_tones_reads_the_same_way():
    a, b = named("Slot One"), named("Slot Two")
    stream = a.to_syx(patch.user_base(0)) + b"\xfe" + b.to_syx(patch.user_base(127)) + sysex.dt1((0, 0, 0, 0), [1])  # (our own files split a tone 128 + 1; junk and a System message between)
    found = pc.parse(stream)
    assert [(e.patch.name, e.base) for e in found.entries] == [("Slot One", patch.user_base(0)), ("Slot Two", patch.user_base(127))] and found.ignored == 1
    assert found.entries[0].patch == a


def test_a_patch_with_wrong_checksums_is_used_and_counted_when_its_values_are_in_range():
    stream = a_bank(named("Fine"), named("Slipped", 99), bad={1})
    strict_error = None
    try:
        patch.parse_syx(stream)
    except sysex.SysexError as e:
        strict_error = str(e)
    assert strict_error == "bad checksum"
    found = pc.parse(stream)
    assert [(e.patch.name, e.repaired, e.damaged) for e in found.entries] == [("Fine", 0, False), ("Slipped", 5, False)]
    assert found.entries[1].patch.get(patch.COMMON, "patch_level") == 99 and found.repaired == 1 and len(found.offered()) == 2


def test_wrong_checksums_together_with_values_outside_the_ranges_look_damaged_and_are_not_offered():
    broken = named("Broken")
    efx = params.load_table().block(patch.COMMON).param("efx_type")
    broken.common[efx.offset] = 0x7F  # EFX type is 0-39
    stream = a_bank(named("Good"), broken, bad={1})
    found = pc.parse(stream)
    assert [e.damaged for e in found.entries] == [False, True] and found.damaged == 1
    assert [e.patch.name for e in found.offered()] == ["Good"]
    # the same values with CORRECT checksums are not "damaged": the checksum says the file means it (the editor flags the values)
    assert [e.damaged for e in pc.parse(a_bank(named("Good"), broken)).entries] == [False, False]


def test_blank_init_patch_slots_are_counted_and_hidden_by_default():
    stream = a_bank(named("Real"), named("INIT PATCH"), named("Real 2"))
    found = pc.parse(stream)
    assert found.blank == 1 and [e.patch.name for e in found.offered()] == ["Real", "Real 2"] and len(found.offered(show_blank=True)) == 3
    assert [e.index for e in found.offered()] == [1, 3]  # (numbers are positions in the file, so they match what the file's author would call them)


def test_a_patch_missing_blocks_is_not_offered_and_other_messages_are_ignored():
    whole = whole_blocks(named("Whole"), patch.TEMPORARY_BASE)
    stream = b"".join(whole) + b"".join(whole_blocks(named("Short"), patch.TEMPORARY_BASE)[:3]) + sysex.identity_request()
    found = pc.parse(stream)
    assert [e.patch.name for e in found.entries] == ["Whole"] and found.incomplete == 1 and found.ignored == 1


def test_a_file_with_no_patch_in_it_has_no_entries():
    assert pc.parse(b"\xf0\x7e\x10\x06\x01\xf7").entries == [] and pc.parse(b"").entries == []
