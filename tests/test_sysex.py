# The JV-1010's exclusive messages. The manual's own worked examples (MIDI Implementation, "Examples of Exclusive Messages and Calculating the
# Checksum") are the test vectors.

import pytest

from jv1010editor.core import sysex


def test_the_manuals_dt1_example_sets_performance_reverb_type_to_delay():
    # address 01 00 00 28 = Temporary Performance + Common 00 00 + REVERB TYPE 00 28; value 06 = DELAY
    assert sysex.dt1((0x01, 0x00, 0x00, 0x28), [0x06]) == bytes.fromhex("F0 41 10 6A 12 01 00 00 28 06 51 F7")


def test_the_manuals_rq1_example_requests_user_03_performance_part_3():
    assert sysex.rq1((0x10, 0x02, 0x12, 0x00), 0x19) == bytes.fromhex("F0 41 10 6A 11 10 02 12 00 00 00 00 19 43 F7")


def test_checksum_makes_the_low_seven_bits_of_the_sum_zero():
    for data in ([0x01, 0x00, 0x00, 0x28, 0x06], [0x10, 0x02, 0x12, 0x00, 0, 0, 0, 0x19], list(range(1, 100))):
        assert (sum(data) + sysex.checksum(data)) % 128 == 0
    assert sysex.checksum([]) == 0
    assert sysex.checksum([127]) == 1


def test_addresses_add_in_seven_bit_bytes():
    assert sysex.add_to_address((0x03, 0, 0x10, 0), 128) == (0x03, 0, 0x11, 0)  # data index 128 of Patch Tone 1 is address +01 00
    assert sysex.add_to_address((0x11, 0x7F, 0x16, 0x00), 0x81) == (0x11, 0x7F, 0x17, 0x01)
    assert sysex.int_to_address(sysex.address_to_int((0x11, 0x05, 0x12, 0x40))) == (0x11, 0x05, 0x12, 0x40)
    with pytest.raises(ValueError):
        sysex.int_to_address(1 << 28)


def test_sizes_use_the_same_bytes_as_the_manual_prints_them():
    assert sysex.size_to_bytes(0x81) == (0, 0, 1, 1)  # Patch Tone: "Total size 00 00 01 01"
    assert sysex.size_to_bytes(0x4A) == (0, 0, 0, 0x4A)


def test_more_than_128_bytes_is_split_into_packets_at_the_right_addresses():
    data = bytes(i % 100 for i in range(129))
    packets = sysex.dt1_packets((0x03, 0, 0x10, 0), data)
    assert len(packets) == 2
    first, second = (sysex.parse(p) for p in packets)
    assert (first.address, first.data) == ((0x03, 0, 0x10, 0), data[:128])
    assert (second.address, second.data) == ((0x03, 0, 0x11, 0), data[128:])  # the 129th byte is at address +01 00
    assert len(sysex.dt1_packets((0x03, 0, 0, 0), bytes(74))) == 1  # a patch common fits one packet


def test_dt1_refuses_data_that_is_not_seven_bit():
    with pytest.raises(ValueError):
        sysex.dt1((0, 0, 0, 0), [0x80])


def test_parse_reads_back_what_was_built():
    m = sysex.parse(sysex.dt1((0x11, 0x05, 0x00, 0x00), [1, 2, 3]))
    assert (m.command, m.address, m.data, m.device_id) == (sysex.CMD_DT1, (0x11, 5, 0, 0), bytes([1, 2, 3]), 0x10)
    r = sysex.parse(sysex.rq1((0x11, 0x05, 0x10, 0x00), 0x81))
    assert (r.command, r.address, r.size) == (sysex.CMD_RQ1, (0x11, 5, 0x10, 0), 0x81)


def test_parse_rejects_corruption_and_other_models():
    good = bytearray(sysex.dt1((0x11, 0, 0, 0), [5, 6]))
    bad = bytearray(good)
    bad[-3] ^= 0x01
    with pytest.raises(sysex.SysexError, match="checksum"):
        sysex.parse(bad)
    with pytest.raises(sysex.SysexError, match="complete"):
        sysex.parse(good[:-1])
    other = bytearray(good)
    other[3] = 0x42
    with pytest.raises(sysex.SysexError, match="model"):
        sysex.parse(other)
    assert sysex.parse(bytes.fromhex("F0 43 10 4C F7")) is None  # someone else's sysex: not ours, not an error


def test_identity_request_and_the_manuals_reply():
    assert sysex.IDENTITY_REQUEST == bytes.fromhex("F0 7E 10 06 01 F7") == sysex.identity_request()
    reply = sysex.parse(bytes.fromhex("F0 7E 10 06 02 41 6A 00 05 00 00 00 00 00 F7"))
    assert isinstance(reply, sysex.IdentityReply) and reply.is_jv1010() and reply.device_id == 0x10
    assert reply.is_roland() and reply.family == 0x6A and reply.family_number == 5 and reply.revision == bytes(4)
    other = sysex.parse(bytes.fromhex("F0 7E 10 06 02 41 6A 00 00 00 00 00 00 00 F7"))  # same family, another model number (a JV-1080?)
    assert other.is_roland() and not other.is_jv1010()
    foreign = sysex.parse(bytes.fromhex("F0 7E 00 06 02 00 20 32 21 00 09 00 01 02 03 04 F7"))  # a 3-byte manufacturer ID
    assert foreign.manufacturer == bytes([0x00, 0x20, 0x32]) and not foreign.is_roland() and foreign.revision == bytes([1, 2, 3, 4])
    assert sysex.parse(bytes.fromhex("F0 7E 10 06 02 41 6A F7")) is None  # too short to be one


def test_split_messages_handles_files_with_several_messages_and_junk():
    a, b = sysex.dt1((0, 0, 0, 0), [1]), sysex.dt1((0, 0, 0, 1), [2])
    assert sysex.split_messages(b"\x00" + a + b"\x01\x02" + b + bytes([0xF0, 0x41])) == [a, b]
