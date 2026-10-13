"""Roland's System Update files for the JV-1010: read, verify and play them (Qt-free).

**UNVERIFIED ON A UNIT. Nothing here has ever been sent to a real JV-1010.** The layout below was decoded from Roland's own "System Update 1.02" files
(AGENTS.md, findings log, 2026-10-14); how the unit behaves in its update mode is not documented anywhere we have. Playing an update is at the owner's risk.

What an update is: a set of Standard MIDI Files (format 0, one track), each carrying ONE 64 KB block of the unit's 2 MB program flash as Roland DT1 messages:

- message 1 (device ID 11H): the block's base address and 8 data bytes = one 7-bit group = `<checksum16 big-endian> 00 00 01 00 00` (the last three: the size, 0x010000);
- messages 2..: device ID 10H, up to 256 data bytes each (a message is at most 267 bytes with F0/F7), at consecutive addresses, `PACKED` as below;
- one message every 39 ticks (div 96, 240 bpm: 101.6 ms), and about 10 s of silence at the end of the file (the unit writing the block, presumably).

`PACKED`: Roland's 7-to-8 packing. Of every 8 bytes sent, byte 0 holds the high bits of the next 7 (bit j, LSB first, is the high bit of byte j). A block is 65,536 real bytes
in 292 x 224 + 128. Addresses count REAL bytes, folded into 7-bit bytes (+224 is `01 60`). Block n (1-14) sits at `06 40+4(n-1) 00 00`; the last file, block 32, at `07 3C 00 00`
(so the image is 32 x 64 KB; this update carries blocks 1-14 and 32). The block checksum is the sum of its 16-bit big-endian words, mod 65536. Block 32 is 0xFF except its
last two bytes, which hold the plain byte sum (mod 65536) of blocks 1-14: a whole-image marker, sent last.

`load()` reads a folder and never raises for a bad FILE: every problem becomes a `Finding`, and `FirmwareSet.ok` is False if any is an error. `play()` refuses a set that is not ok.
"""

import hashlib
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sysex
from .backup import Cancelled

BLOCK_BYTES = 0x10000
FIRST_BLOCK_ADDRESS = sysex.address_to_int((0x06, 0x40, 0x00, 0x00))
HEADER_DEVICE_ID = 0x11  # the first message of every file
DATA_DEVICE_ID = 0x10  # all the others: the unit's own ID
MAX_MESSAGE_BYTES = 267  # F0 + 41 10 6A 12 + 4 address + 256 data + checksum + F7: longer than the 256 some MIDI interfaces pass (see AGENTS.md)
MIDI_BYTES_PER_SECOND = 3125  # 31,250 baud, 10 bits a byte
#: extra silence between one file's end and the next file's first message, on top of the file's own tail (the manual way: a person starts the next file)
INTER_BLOCK_PAUSE = 2.0  # [guess] seconds; slower is the safe direction
MARKER_BYTES = 2
EXPECTED_FIRST_BYTES = b"RolandJV1010"  # block 1 starts with this; another model's update files must never be played to a JV-1010

#: sha256 of each block's messages (F0..F7, concatenated, container and timing left out) for Roland's System Update 1.02, from the files the owner downloaded
KNOWN_RELEASES = {
    "Roland JV-1010 System Update 1.02": {
        1: "1a3af770f3dffff933b6c78c7cd0af56aa314395d8af0d8677c41bf7516b4b61",
        2: "c5178089965aad54c3db3134a90c9300b6003d8b8f66b15b3c47e28f069484a2",
        3: "1750195599b37ac849127d3208fe6019b10af89b6151cfb82bcd02b67e434d03",
        4: "7b853faadb3f910ff422d908e955d457f7b1ed6d6e777ae1fb58318ee1a7e422",
        5: "f28b10598d1f00595e814503b64fb76c9021cb99bf3fe4189b089ef9d85a8ffa",
        6: "ba64805735ffda29b59473c54ffff5d8cff47e0645b2d3e66b3d0b27b2410ad1",
        7: "b09a308408360816439b4d12e60c5c3850a12c15c1d9dbdda5cca428547d3a28",
        8: "87c947205bda667128a91f48871d2b25d42c33ae197b902e595a978f101f3ba9",
        9: "6ed4cc8d36a473a0a4a5d2d802fa5a77859d1cebbd2b514707620a52ae592f84",
        10: "11c3b7f0286f11800ddcaff50fb9bf96c244f76c4db980494e65d30003f0ddeb",
        11: "2b02f66b52a7d5c9277685ea512c2aad1491dbffe9cb55167581915c8b85c714",
        12: "dda6e741d55525d108e2f04129d90cbf49cdcb84d650cb19484a4d9eb7f3b920",
        13: "723fa4936f4da88d68345530d228368c789b075d1b9e9cfed7f8d6cd2b69edad",
        14: "d58162611589f51fe5af596c412f334faa142cf647923d067f6d91452d7c0e0b",
        32: "132902cc5c7fba6b05f3e075be6e301de72d2dff8bd72ae513c39e5581bb7883",
    }
}

WARNING_TEXT = (
    "UNVERIFIED: this has never been tried on a real JV-1010. Roland's update files are decoded and checked here, and they are sent the way a sequencer would play them, "
    "but how the unit reacts is not documented. An interrupted or corrupted update may leave the unit unable to start, and Roland's service centre would be the only way back. "
    "Use it at your own risk."
)


class FirmwareError(RuntimeError):
    """The update could not be played (not verified, or the MIDI output failed)."""


@dataclass(frozen=True)
class Finding:
    level: str  # "error" (the set cannot be played), "warning" or "info"
    where: str  # a file name, or "" for the set as a whole
    text: str

    def __str__(self):
        return f"{self.where}: {self.text}" if self.where else self.text


@dataclass
class Block:
    number: int
    path: str
    base: int  # address, as sysex.address_to_int
    frames: list  # complete messages, F0..F7, exactly as the file holds them
    delays: list  # seconds to wait BEFORE each frame
    tail: float  # seconds after the last frame
    data: bytes  # the 65,536 real bytes
    declared_checksum: int
    computed_checksum: int

    @property
    def name(self):
        return Path(self.path).name

    @property
    def fingerprint(self):
        return hashlib.sha256(b"".join(self.frames)).hexdigest()

    @property
    def duration(self):
        return sum(self.delays) + self.tail


@dataclass
class FirmwareSet:
    folder: str
    blocks: list = field(default_factory=list)  # sorted by block number: the order they are played in
    findings: list = field(default_factory=list)
    release: str = ""  # the known release these files are, or ""

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def ok(self):
        return bool(self.blocks) and not self.errors

    @property
    def total_frames(self):
        return sum(len(b.frames) for b in self.blocks)

    @property
    def duration(self):
        """Seconds the whole update takes to play."""
        return sum(b.duration for b in self.blocks) + INTER_BLOCK_PAUSE * max(len(self.blocks) - 1, 0)


# -- the 7-bit packing ----------------------------------------------------------------------------------------------------


def unpack(packed):
    """Roland's 7-to-8 unpacking: every 8 bytes (the last group may be shorter) become 7 real bytes. See the module docstring."""
    out = bytearray()
    for i in range(0, len(packed), 8):
        group = packed[i : i + 8]
        high = group[0]
        for j, byte in enumerate(group[1:]):
            out.append(byte | (((high >> j) & 1) << 7))
    return bytes(out)


def packed_to_real(count):
    """How many real bytes `count` packed bytes carry."""
    return count // 8 * 7 + max(count % 8 - 1, 0)


def word_sum(data):
    """The block checksum: the sum of the big-endian 16-bit words, mod 65536."""
    return sum(struct.unpack(f">{len(data) // 2}H", data)) & 0xFFFF


def byte_sum(data):
    return sum(data) & 0xFFFF


# -- reading a Standard MIDI File -----------------------------------------------------------------------------------------


def _vlq(data, i):
    value = 0
    while True:
        if i >= len(data):
            raise FirmwareError("the file ends in the middle of an event")
        byte = data[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i


def _read_smf(raw):
    """(sysex_events, texts) of a one-track SMF: sysex_events = [(seconds_since_previous_event, message F0..F7)] and the seconds from the last one to the end of the track;
    texts = every text/track-name meta event. Anything but sysex and meta events is an error: a firmware file holds nothing else."""
    if raw[:4] != b"MThd" or len(raw) < 14:
        raise FirmwareError("not a Standard MIDI File")
    _fmt, tracks, division = struct.unpack(">HHH", raw[8:14])
    if division & 0x8000:
        raise FirmwareError("SMPTE timing is not supported")
    if tracks != 1:
        raise FirmwareError(f"{tracks} tracks (a firmware file has exactly one)")
    i = 14
    if raw[i : i + 4] != b"MTrk":
        raise FirmwareError("no track")
    end = min(i + 8 + struct.unpack(">I", raw[i + 4 : i + 8])[0], len(raw))
    i += 8
    tempo = 500000
    events, texts, since_last = [], [], 0.0
    while i < end:
        delta, i = _vlq(raw, i)
        since_last += delta * tempo / 1e6 / division
        if i >= end:
            raise FirmwareError("the file ends in the middle of an event")
        status = raw[i]
        if status == 0xFF:
            kind = raw[i + 1]
            length, j = _vlq(raw, i + 2)
            body = raw[j : j + length]
            i = j + length
            if kind == 0x51 and length == 3:
                tempo = int.from_bytes(body, "big")
            elif kind in (0x01, 0x03):
                texts.append(body.decode("latin-1"))
            elif kind == 0x2F:
                return events, texts, since_last
        elif status == 0xF0:
            length, j = _vlq(raw, i + 1)
            message = b"\xf0" + raw[j : j + length]
            i = j + length
            events.append((since_last, message))
            since_last = 0.0
        else:
            raise FirmwareError(f"an event that is not SysEx or a meta event (status {status:02X})")
    raise FirmwareError("the track has no end-of-track event")


def _read_block(path):
    """One file -> (Block or None, [Finding]). A block is returned only when it is whole enough to be worth listing."""
    name = Path(path).name
    findings = []

    def error(text):
        findings.append(Finding("error", name, text))

    def warn(text):
        findings.append(Finding("warning", name, text))

    try:
        events, texts, tail = _read_smf(Path(path).read_bytes())
    except (OSError, FirmwareError, struct.error) as e:
        error(str(e))
        return None, findings
    if len(events) < 3:
        error(f"{len(events)} SysEx messages: too few to be a block")
        return None, findings

    text_block = text_checksum = None
    for text in texts:
        if m := re.fullmatch(r"\s*BLOCK\s*(\d+)\b.*", text):
            text_block = int(m.group(1))
        elif m := re.fullmatch(r"\s*CHECKSUM\s*=\s*([0-9A-Fa-f]{4})\s*", text):
            text_checksum = int(m.group(1), 16)

    messages = []
    for index, (delay, message) in enumerate(events):
        try:
            parsed = sysex.parse(message)
        except sysex.SysexError as e:
            error(f"message {index + 1}: {e}")
            return None, findings
        if parsed is None or parsed.command != sysex.CMD_DT1:
            error(f"message {index + 1} is not a Roland DT1 message")
            return None, findings
        if len(message) > MAX_MESSAGE_BYTES:
            error(f"message {index + 1} is {len(message)} bytes (more than the {MAX_MESSAGE_BYTES} an update message ever is)")
            return None, findings
        messages.append((delay, message, parsed))

    # the header
    _, header_message, header = messages[0]
    if header.device_id != HEADER_DEVICE_ID:
        error(f"the first message has device ID {header.device_id:02X}H, not {HEADER_DEVICE_ID:02X}H")
    if len(header.data) != 8:
        error(f"the first message holds {len(header.data)} data bytes, not 8")
        return None, findings
    head = unpack(header.data)
    declared = int.from_bytes(head[0:2], "big")
    if head[2:7] != bytes([0, 0, 1, 0, 0]):
        error(f"the header's size field is {head[2:7].hex(' ')}, not 00 00 01 00 00 (64 KB)")
    base = sysex.address_to_int(header.address)
    offset = base - FIRST_BLOCK_ADDRESS
    if offset < 0 or offset % BLOCK_BYTES:
        error(f"the block address {bytes(header.address).hex(' ')} is not on a 64 KB boundary from 06 40 00 00")
        return None, findings
    number = offset // BLOCK_BYTES + 1
    if text_block is not None and text_block != number:
        error(f"the file says BLOCK{text_block:02d} but its address is block {number}")
    if text_block is None:
        warn("no BLOCKnn text in the file")

    # the data
    data = bytearray()
    expected = base
    for index, (_, message, parsed) in enumerate(messages[1:], start=2):
        if parsed.device_id != DATA_DEVICE_ID:
            error(f"message {index} has device ID {parsed.device_id:02X}H, not {DATA_DEVICE_ID:02X}H")
        if sysex.address_to_int(parsed.address) != expected:
            error(f"message {index} is at {bytes(parsed.address).hex(' ')}, not the next address")
            return None, findings
        real = unpack(parsed.data)
        if len(real) != packed_to_real(len(parsed.data)):
            error(f"message {index} has a data length that doesn't unpack evenly")
            return None, findings
        data += real
        expected += len(real)
    if len(data) != BLOCK_BYTES:
        error(f"the block holds {len(data)} bytes, not {BLOCK_BYTES}")
        return None, findings

    computed = word_sum(bytes(data))
    if computed != declared:
        error(f"the data adds up to checksum {computed:04X} but the header says {declared:04X}")
    if text_checksum is None:
        warn("no CHECKSUM text in the file")
    elif text_checksum != declared:
        error(f"the file's CHECKSUM text ({text_checksum:04X}) differs from the header ({declared:04X})")

    # timing: never faster than the wire allows
    delays = [d for d, _, _ in messages]
    for previous, (delay, message, _) in zip(messages, messages[1:]):
        wire = len(previous[1]) / MIDI_BYTES_PER_SECOND
        if delay < wire:
            warn(f"messages are {delay * 1000:.0f} ms apart, but one takes {wire * 1000:.0f} ms to send")
            break
    if tail < 1.0:
        warn(f"only {tail:.1f} s after the last message: the unit probably needs time to write the block")

    block = Block(number, str(path), base, [m for _, m, _ in messages], delays, tail, bytes(data), declared, computed)
    return block, findings


def load(folder):
    """Read every `.mid` file of `folder` and check the set. Returns a `FirmwareSet`; look at `.ok` and `.findings`."""
    folder = Path(folder)
    result = FirmwareSet(str(folder))

    def add(level, text, where=""):
        result.findings.append(Finding(level, where, text))

    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".mid", ".midi") and p.is_file()) if folder.is_dir() else []
    if not files:
        add("error", "There are no .mid files in that folder.")
        return result
    seen = {}
    for path in files:
        block, findings = _read_block(path)
        result.findings.extend(findings)
        if block is None:
            continue
        if block.number in seen:
            add("error", f"block {block.number} is in both {seen[block.number].name} and {block.name}", block.name)
            continue
        seen[block.number] = block
    result.blocks = [seen[n] for n in sorted(seen)]
    if not result.blocks:
        return result
    _check_set(result)
    return result


def _check_set(result):
    blocks = result.blocks
    add = lambda level, text: result.findings.append(Finding(level, "", text))  # noqa: E731
    first = next((b for b in blocks if b.number == 1), None)
    if first is None:
        add("error", "Block 1 is missing: an update always starts there.")
    elif not first.data.startswith(EXPECTED_FIRST_BYTES):
        add("error", f"Block 1 doesn't start with {EXPECTED_FIRST_BYTES.decode()!r}: these files are not for a JV-1010.")
    last = blocks[-1]
    if len(blocks) < 2:
        add("error", "A single block can't be a complete update (the last block carries the image marker).")
    else:
        marker = int.from_bytes(last.data[-MARKER_BYTES:], "big")
        total = byte_sum(b"".join(b.data for b in blocks[:-1]))
        if marker != total:
            add("error", f"The last block (block {last.number}) ends with {marker:04X}, but blocks 1-{blocks[-2].number} add up to {total:04X}: the set is incomplete or mixes versions.")
        elif last.data[:-MARKER_BYTES].count(0xFF) != len(last.data) - MARKER_BYTES:
            add("warning", f"Block {last.number} holds more than the image marker.")
    for name, fingerprints in KNOWN_RELEASES.items():
        if {b.number: b.fingerprint for b in blocks} == fingerprints:
            result.release = name
    if result.release:
        add("info", f"Recognised: {result.release} ({len(blocks)} files, every block identical to Roland's).")
    elif not result.errors:
        add("warning", "These files are internally consistent but are not a release this app knows. Only play files you got from Roland.")


# -- playing ---------------------------------------------------------------------------------------------------------------


@dataclass
class PlayResult:
    blocks: int
    messages: int
    seconds: float


def _wait(seconds, cancelled, sleep, clock, tick=None):
    """Wait `seconds` (by `clock`), polling `cancelled` about every 20 ms. `tick(elapsed)` is called about once a second for long waits."""
    start = clock()
    deadline = start + seconds
    next_tick = start + 1.0
    while (remaining := deadline - clock()) > 0:
        if cancelled():
            raise Cancelled("cancelled")
        if tick is not None and clock() >= next_tick:
            tick(clock() - start)
            next_tick += 1.0
        sleep(min(remaining, 0.02))


def play(connection, firmware, *, progress=None, status=None, cancelled=lambda: False, sleep=time.sleep, clock=time.monotonic, block_pause=INTER_BLOCK_PAUSE):
    """Send the update, block by block, the way a sequencer would play the files: each message after its own delay (never sooner than the file says), then the
    file's silent tail and `block_pause` before the next file. Output only: nothing is read back (the unit does not answer in update mode as far as the manual says).

    `progress(done, total)` is in tenths of a second of the planned playing time; `status(text)` says which block is being sent. Raises `Cancelled` (between messages),
    or `FirmwareError` if the set is not ok or the MIDI output fails. Both say how far it got."""
    if not firmware.ok:
        raise FirmwareError("The firmware files did not pass verification; nothing was sent.")
    total_blocks = len(firmware.blocks)
    done = 0.0  # seconds of the planned playing time
    sent = 0
    started = clock()

    def where():
        return f"in block {block.number} ({index} of {total_blocks}), after {sent} of {firmware.total_frames} messages"

    def report(extra=0.0):
        if progress is not None:
            progress(round(min(done + extra, firmware.duration) * 10), round(firmware.duration * 10))

    try:
        for index, block in enumerate(firmware.blocks, start=1):
            if status is not None:
                status(f"Firmware: block {index} of {total_blocks} ({block.name})")
            if index > 1:
                _wait(block_pause, cancelled, sleep, clock)
                done += block_pause
            for frame, delay in zip(block.frames, block.delays):
                _wait(delay, cancelled, sleep, clock)
                try:
                    connection.send(frame)
                except Exception as e:
                    raise FirmwareError(f"The MIDI output failed {where()}: {e}") from e
                sent += 1
                done += delay
                report()
            _wait(block.tail, cancelled, sleep, clock, tick=report)
            done += block.tail
            report()
    except Cancelled as e:
        raise Cancelled(
            f"Firmware update stopped {where()}. The unit may be part-way through an update: don't switch it off; play the update again from the first block."
        ) from e
    return PlayResult(total_blocks, sent, clock() - started)
