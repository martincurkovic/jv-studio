"""Make small, valid JV-1010 System Update file sets for the tests (nothing here is Roland's data): the same structure as the real files, with made-up contents."""

import random
from pathlib import Path

from jv_studio.core import firmware, sysex

TICKS = 39  # between messages, at division 96 and 240 bpm: 101.6 ms
TAIL_TICKS = 3840  # 10 s


def pack(real):
    """The inverse of firmware.unpack."""
    out = bytearray()
    for i in range(0, len(real), 7):
        group = real[i : i + 7]
        out.append(sum(((byte >> 7) & 1) << j for j, byte in enumerate(group)))
        out.extend(byte & 0x7F for byte in group)
    return bytes(out)


def vlq(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def block_data(number, seed=0):
    """65,536 made-up bytes; block 1 starts with the model name, like the real one."""
    rng = random.Random(number * 1000 + seed)
    data = bytearray(rng.randbytes(firmware.BLOCK_BYTES))
    if number == 1:
        data[: len(firmware.EXPECTED_FIRST_BYTES)] = firmware.EXPECTED_FIRST_BYTES
    return data


def messages_for(number, data, declared=None, size_field=b"\x00\x00\x01\x00\x00", header_device=0x11):
    """The DT1 messages of one block: a header, then 224 real bytes (256 sent) at a time."""
    base = firmware.FIRST_BLOCK_ADDRESS + (number - 1) * firmware.BLOCK_BYTES
    declared = firmware.word_sum(bytes(data)) if declared is None else declared
    out = [sysex.dt1(sysex.int_to_address(base), pack(declared.to_bytes(2, "big") + size_field), device_id=header_device)]
    for i in range(0, len(data), 224):
        out.append(sysex.dt1(sysex.int_to_address(base + i), pack(bytes(data[i : i + 224])), device_id=0x10))
    return out


def smf(messages, checksum_text, block_text, tail_ticks=TAIL_TICKS, extra_events=b""):
    track = bytearray()
    track += vlq(0) + b"\xff\x58\x04\x04\x02\x18\x08" + vlq(0) + b"\xff\x51\x03\x03\xd0\x90"
    track += vlq(0) + b"\xff\x03" + vlq(len(checksum_text)) + checksum_text.encode()
    track += vlq(0) + b"\xff\x01" + vlq(len(block_text)) + block_text.encode()
    for message in messages:
        body = message[1:]  # after F0, up to and including F7
        track += vlq(TICKS) + b"\xf0" + vlq(len(body)) + body
    track += extra_events
    track += vlq(tail_ticks) + b"\xff\x2f\x00"
    return b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + (96).to_bytes(2, "big") + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)


def write_set(folder, numbers=(1, 2, 32), *, corrupt=None, wrong_marker=False, wrong_model=False, no_block_one=False, skip=()):
    """Write a set of files named like Roland's. `corrupt` = a block number whose data changes after its checksum was declared."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    datas = {n: block_data(n) for n in numbers}
    if wrong_model and 1 in datas:
        datas[1][: len(firmware.EXPECTED_FIRST_BYTES)] = b"RolandJV1080"
    last = max(numbers)
    marker = firmware.byte_sum(b"".join(bytes(datas[n]) for n in numbers if n != last))
    datas[last] = bytearray(b"\xff" * firmware.BLOCK_BYTES)
    datas[last][-2:] = ((marker + (1 if wrong_marker else 0)) & 0xFFFF).to_bytes(2, "big")
    for n in numbers:
        if n in skip or (no_block_one and n == 1):
            continue
        data = datas[n]
        declared = firmware.word_sum(bytes(data))
        if corrupt == n:
            data = bytearray(data)
            data[100] ^= 0x55
        (folder / f"_{n:07d}.mid").write_bytes(smf(messages_for(n, data, declared=declared), f"CHECKSUM = {declared:04X}", f"BLOCK{n:02d} LOADING"))
    return folder


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self):
        self.now = 1000.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
