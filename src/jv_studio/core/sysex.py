"""Roland exclusive messages for the JV-1010 (Qt-free).

Everything here is from the Owner's Manual's MIDI Implementation chapter (see AGENTS.md for the page numbers):

    RQ1   F0 41 dev 6A 11  aa bb cc dd  ss tt uu vv  sum F7        request a block (fixed start address AND size per block)
    DT1   F0 41 dev 6A 12  aa bb cc dd  data...      sum F7        set data (more than 128 bytes must be split, >= 20 ms apart)

Addresses and sizes are four 7-bit bytes. The device ID of a JV-1010 is fixed at 10H.
"""

from dataclasses import dataclass

ROLAND_ID = 0x41
MODEL_ID = 0x6A
DEVICE_ID = 0x10
CMD_RQ1 = 0x11
CMD_DT1 = 0x12

#: DT1 data over this many bytes must be split into packets of at most this size (manual, "Data Set 1")
MAX_PACKET = 128
#: successive DT1 messages need at least this long between them (milliseconds)
PACKET_GAP_MS = 20

Address = tuple[int, int, int, int]


class SysexError(ValueError):
    """A malformed or corrupt message (bad framing, wrong model, short, checksum mismatch)."""


# -- numbers in 7-bit bytes ---------------------------------------------------------------------------------------------


def address_to_int(address):
    """(aa, bb, cc, dd) -> the address as one integer, 7 bits per byte (the unit the manual's offsets add up in)."""
    a, b, c, d = address
    return (a << 21) | (b << 14) | (c << 7) | d


def int_to_address(value):
    if not 0 <= value < 1 << 28:
        raise ValueError(f"address {value:#x} doesn't fit four 7-bit bytes")
    return ((value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F)


def add_to_address(address, offset):
    """Start address + a DATA offset, carrying across the 7-bit bytes (index 128 of a block is address +01 00)."""
    return int_to_address(address_to_int(address) + offset)


size_to_bytes = int_to_address  # a size uses the same four 7-bit bytes


def checksum(data):
    """Roland checksum: the value that makes the low 7 bits of (address + data + checksum) zero."""
    return (128 - (sum(data) % 128)) % 128


# -- building ------------------------------------------------------------------------------------------------------------


def _frame(command, body, device_id):
    payload = bytes(body)
    return bytes([0xF0, ROLAND_ID, device_id, MODEL_ID, command]) + payload + bytes([checksum(payload), 0xF7])


def rq1(address, size, device_id=DEVICE_ID):
    """Request `size` bytes at `address`. Use a block's own start address and size: the unit answers nothing else."""
    return _frame(CMD_RQ1, [*address, *size_to_bytes(size)], device_id)


def dt1(address, data, device_id=DEVICE_ID):
    """Set `data` at `address`. Not for more than MAX_PACKET bytes: see `dt1_packets`."""
    if any(b > 0x7F for b in data):
        raise ValueError("sysex data bytes are 7-bit")
    return _frame(CMD_DT1, [*address, *data], device_id)


def dt1_packets(address, data, device_id=DEVICE_ID):
    """The DT1 messages for `data` at `address`, split into packets of at most MAX_PACKET bytes (send them PACKET_GAP_MS apart)."""
    data = bytes(data)
    return [dt1(add_to_address(address, i), data[i : i + MAX_PACKET], device_id) for i in range(0, max(len(data), 1), MAX_PACKET)]


IDENTITY_REQUEST = bytes([0xF0, 0x7E, DEVICE_ID, 0x06, 0x01, 0xF7])


def identity_request(device_id=DEVICE_ID):
    return bytes([0xF0, 0x7E, device_id, 0x06, 0x01, 0xF7])


# -- parsing -------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    command: int  # CMD_RQ1 or CMD_DT1
    address: Address
    data: bytes = b""  # DT1: the data
    size: int = 0  # RQ1: the requested size
    device_id: int = DEVICE_ID


@dataclass(frozen=True)
class IdentityReply:
    device_id: int
    manufacturer: bytes  # 41 for Roland; 00 xx xx for the extended IDs
    family: int  # 2 bytes, LSB first: 6A 00 on a JV-1010
    family_number: int  # 05 00 on a JV-1010
    revision: bytes  # 4 bytes, "Software revision level"

    def is_roland(self):
        return self.manufacturer == bytes([ROLAND_ID])

    def is_jv1010(self):
        return self.is_roland() and self.family == MODEL_ID and self.family_number == 0x05


def parse(message):
    """Parse one complete message (F0 ... F7). Returns a `Message` (RQ1/DT1 for the JV-1010) or an `IdentityReply`.
    Raises `SysexError` for anything malformed, for another model, and for a bad checksum; `None` for valid sysex we don't handle."""
    message = bytes(message)
    if len(message) < 3 or message[0] != 0xF0 or message[-1] != 0xF7:
        raise SysexError("not a complete sysex message")
    body = message[1:-1]
    if body[0] == 0x7E:
        return _parse_universal(body)
    if body[0] != ROLAND_ID:
        return None
    if len(body) < 5 or body[2] != MODEL_ID:
        raise SysexError("another Roland model")
    device_id, command, payload = body[1], body[3], body[4:]
    if len(payload) < 5:
        raise SysexError("message too short")
    *content, received = payload
    if checksum(content) != received:
        raise SysexError("bad checksum")
    address = tuple(content[:4])
    if command == CMD_DT1:
        return Message(CMD_DT1, address, bytes(content[4:]), device_id=device_id)
    if command == CMD_RQ1:
        if len(content) != 8:
            raise SysexError("RQ1 must be 4 address + 4 size bytes")
        return Message(CMD_RQ1, address, size=address_to_int(tuple(content[4:])), device_id=device_id)
    return None


def _parse_universal(body):
    # 7E dev 06 02 mfr(1 or 3) fam(2) num(2) rev(4)
    if len(body) < 13 or body[2] != 0x06 or body[3] != 0x02:
        return None
    width = 3 if body[4] == 0x00 else 1  # a manufacturer ID starting 00 is the 3-byte form
    if len(body) != 4 + width + 8:
        return None
    i = 4 + width
    return IdentityReply(
        device_id=body[1],
        manufacturer=bytes(body[4:i]),
        family=body[i] | (body[i + 1] << 7),
        family_number=body[i + 2] | (body[i + 3] << 7),
        revision=bytes(body[i + 4 : i + 8]),
    )


def split_messages(stream):
    """Split bytes that may hold several F0..F7 messages (a .syx file) into complete messages. A trailing partial message is dropped."""
    messages, start = [], None
    for i, b in enumerate(stream):
        if b == 0xF0:
            start = i
        elif b == 0xF7 and start is not None:
            messages.append(bytes(stream[start : i + 1]))
            start = None
    return messages
