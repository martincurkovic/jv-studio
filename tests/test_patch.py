# A patch as five blocks, and how it travels as sysex.

import pytest

from jv_studio.core import patch, sysex


def sample_patch():
    p = patch.Patch.blank()
    p.name = "Test Patch"
    p.set(patch.COMMON, "efx_type", 12)
    p.set(patch.COMMON, "patch_tempo", 120)
    for i in range(4):
        p.set(patch.TONE, "wave_number", 100 + i, tone=i)
        p.set(patch.TONE, "cutoff_frequency", 10 * i + 5, tone=i)
        p.set(patch.TONE, "reverb_send_level", 77 - i, tone=i)  # data index 128: the byte that needs the second packet
    return p


def test_a_blank_patch_has_the_manuals_block_sizes():
    p = patch.Patch.blank()
    assert len(p.common) == 0x4A and [len(t) for t in p.tones] == [0x81] * 4


def test_values_are_read_and_written_per_block_and_tone():
    p = sample_patch()
    assert p.name == "Test Patch" and p.get(patch.COMMON, "patch_tempo") == 120
    assert [p.get(patch.TONE, "wave_number", tone=i) for i in range(4)] == [100, 101, 102, 103]
    with pytest.raises(ValueError):
        p.get(patch.TONE, "wave_number")  # which tone?


def test_the_patch_goes_out_as_dt1_messages_at_the_manuals_addresses():
    messages = [sysex.parse(m) for m in sample_patch().to_messages(patch.user_base(2))]
    addresses = [m.address for m in messages]
    # common at 11 02 00 00 (74 bytes, one packet); each tone at 11 02 10/12/14/16 00 as 128 bytes + the 129th at +01 00
    assert addresses == [
        (0x11, 2, 0x00, 0),
        (0x11, 2, 0x10, 0), (0x11, 2, 0x11, 0),
        (0x11, 2, 0x12, 0), (0x11, 2, 0x13, 0),
        (0x11, 2, 0x14, 0), (0x11, 2, 0x15, 0),
        (0x11, 2, 0x16, 0), (0x11, 2, 0x17, 0),
    ]
    assert [len(m.data) for m in messages] == [74, 128, 1, 128, 1, 128, 1, 128, 1]


def test_the_requests_use_each_blocks_fixed_start_address_and_size():
    requests = [sysex.parse(m) for m in patch.Patch.requests(patch.TEMPORARY_BASE)]
    assert [(r.address, r.size) for r in requests] == [
        ((3, 0, 0x00, 0), 0x4A), ((3, 0, 0x10, 0), 0x81), ((3, 0, 0x12, 0), 0x81), ((3, 0, 0x14, 0), 0x81), ((3, 0, 0x16, 0), 0x81)
    ]


def test_a_patch_survives_a_round_trip_through_syx_bytes():
    original = sample_patch()
    parsed = patch.parse_syx(original.to_syx(patch.user_base(9)))
    assert list(parsed) == [(0x11, 9, 0, 0)] and parsed[(0x11, 9, 0, 0)] == original


def test_messages_may_arrive_in_any_order_and_split_packets_are_reassembled():
    original = sample_patch()
    messages = [sysex.parse(m) for m in original.to_messages(patch.TEMPORARY_BASE)]
    received = patch.Patch.blank()
    for m in reversed(messages):
        assert received.apply(m, patch.TEMPORARY_BASE)
    assert received == original


def test_a_message_for_another_patch_is_not_applied():
    p = patch.Patch.blank()
    other = sysex.parse(sample_patch().to_messages(patch.user_base(5))[0])
    assert not p.apply(other, patch.user_base(4))
    assert p == patch.Patch.blank()


def test_a_bank_file_with_several_patches_is_split_by_patch():
    a, b = sample_patch(), sample_patch()
    b.name = "Second"
    stream = a.to_syx(patch.user_base(0)) + b"\xfe" + b.to_syx(patch.user_base(127)) + sysex.dt1((0, 0, 0, 0), [1])  # (junk and a system DT1 in between)
    parsed = patch.parse_syx(stream)
    assert list(parsed) == [(0x11, 0, 0, 0), (0x11, 127, 0, 0)]
    assert parsed[(0x11, 127, 0, 0)].name == "Second"


def test_a_corrupt_message_in_a_file_is_reported_not_skipped():
    data = bytearray(sample_patch().to_syx(patch.user_base(1)))
    data[10] ^= 0x01
    with pytest.raises(sysex.SysexError):
        patch.parse_syx(bytes(data))


def test_user_patch_numbers_are_validated():
    assert patch.user_base(127) == (0x11, 0x7F, 0, 0)
    for bad in (-1, 128):
        with pytest.raises(ValueError):
            patch.user_base(bad)
