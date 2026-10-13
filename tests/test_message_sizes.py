# The owner's interface (Midiplus MIDI 2x2) drops SysEx messages over 256 bytes. The JV-1010 never needs one: every block is small and the manual
# makes us send and request fixed blocks. This guards that, so a future change can't quietly add a message the owner's interface can't carry.

from jv_studio.core import params, patch

INTERFACE_LIMIT = 256
FRAMING = 11  # F0 41 dev 6A cmd + 4 address bytes + checksum + F7


def test_every_block_fits_in_one_message_either_way():
    for block in params.load_table().blocks.values():
        assert block.size + FRAMING <= INTERFACE_LIMIT, block.key  # the unit's reply (a DT1 carrying the whole block)


def test_the_largest_block_is_a_patch_tone_of_140_bytes_on_the_wire():
    largest = max(params.load_table().blocks.values(), key=lambda b: b.size)
    assert (largest.key, largest.size + FRAMING) == ("patch_tone", 140)


def test_the_messages_we_send_are_never_larger_than_139_bytes():
    sizes = [len(m) for m in sample().to_messages(patch.user_base(0))]
    assert max(sizes) == 139 and all(s <= INTERFACE_LIMIT for s in sizes)  # a 128-byte packet; the 74-byte common block is 85


def test_a_request_is_a_fixed_size_message():
    assert {len(m) for m in patch.Patch.requests(patch.TEMPORARY_BASE)} == {15}


def sample():
    p = patch.Patch.blank()
    for tone in p.tones:
        for i in range(len(tone)):
            tone[i] = i % 100
    return p
