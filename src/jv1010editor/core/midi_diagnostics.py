"""The two checks in Settings > Troubleshooting (Qt-free; they take a `MidiConnection` and a `pump` callable so a dialog can stay responsive):

- the LOOPBACK test: with the interface's own MIDI OUT cabled to its own MIDI IN, send SysEx messages of growing size and check each comes
  back intact. It tells a bad interface or cable from a bad setup.
- HARDWARE detection: send an Identity Request and, if a JV-1010 answers, read its temporary patch's name (one RQ1). It sends nothing else
  and never writes. If nothing answers it stops: never send into silence.
"""

from dataclasses import dataclass, field

from . import patch, sysex

LOOPBACK_SIZES = [8, 32, 64, 127, 256, 512, 1024, 1536, 2048, 2560, 3072]
RECEIVE_TIMEOUT = 1.5  # seconds to wait for each reply


def loopback_one(connection, byte_count, timeout=None, pump=None):
    """Send ONE SysEx message of `byte_count` data bytes and check it comes back unchanged. Returns (passed, detail)."""
    timeout = RECEIVE_TIMEOUT if timeout is None else timeout  # read at call time, so tests can shorten it
    expected = [i % 128 for i in range(byte_count)]  # a predictable pattern, so dropped or corrupted data is obvious
    message = bytes([0xF0, *expected, 0xF7])
    received = connection.request(message, accept=lambda reply: True, timeout=timeout, pump=pump)
    if received is None:
        return False, "no response (timed out) - likely dropped entirely"
    got = list(received[1:-1])
    if got == expected:
        return True, "OK"
    mismatch = next((i for i, (a, b) in enumerate(zip(expected, got)) if a != b), min(len(expected), len(got)))
    return False, f"corrupted - sent {len(expected)} bytes, got {len(got)} back, first mismatch at byte {mismatch}"


def run_loopback(connection, sizes=LOOPBACK_SIZES, timeout=None, pump=None, progress=None):
    """The loopback test over `sizes`: a list of (size, passed, detail). `progress(size)` is called before each size."""
    results = []
    for size in sizes:
        if progress is not None:
            progress(size)
        passed, detail = loopback_one(connection, size, timeout, pump)
        results.append((size, passed, detail))
    return results


# -- hardware detection ------------------------------------------------------------------------------------------------------

JV1010 = "jv1010"
OTHER_ROLAND = "other_roland"
OTHER_DEVICE = "other_device"
NO_REPLY = "no_reply"


@dataclass
class HardwareResult:
    status: str
    message: str  # what to show the user (a few short lines)
    reply: sysex.IdentityReply | None = None
    patch_name: str | None = None  # the temporary patch's name, when the unit answered the read
    read_ok: bool | None = None  # None: not tried
    log_lines: list = field(default_factory=list)

    @property
    def found(self):
        return self.status == JV1010


def _identity_reply(raw):
    try:
        parsed = sysex.parse(raw)
    except sysex.SysexError:
        return None
    return parsed if isinstance(parsed, sysex.IdentityReply) else None


def _is_identity_reply(raw):
    return _identity_reply(raw) is not None


def _is_common_block(raw):
    try:
        parsed = sysex.parse(raw)
    except sysex.SysexError:
        return False
    return isinstance(parsed, sysex.Message) and parsed.command == sysex.CMD_DT1 and parsed.address == patch.TEMPORARY_BASE


def detect_hardware(connection, timeout=None, pump=None, read_patch=True):
    """Look for a JV-1010 on the connection. See the module docstring for what is (and is not) sent."""
    timeout = RECEIVE_TIMEOUT if timeout is None else timeout
    raw = connection.request(sysex.identity_request(), _is_identity_reply, timeout, pump)
    if raw is None:
        return HardwareResult(
            NO_REPLY,
            "No reply. Check the cables, that the JV-1010 is on, that the right ports are selected, "
            "and that no other program is using the MIDI interface.",
        )
    reply = _identity_reply(raw)
    log = [f"identity reply: {raw.hex(' ')}"]
    if not reply.is_roland():
        return HardwareResult(
            OTHER_DEVICE,
            f"A MIDI device answered, but it isn't a Roland (manufacturer ID {reply.manufacturer.hex(' ').upper()}). Check the port selection.",
            reply,
            log_lines=log,
        )
    if not reply.is_jv1010():
        return HardwareResult(
            OTHER_ROLAND,
            f"A Roland device answered, but it isn't a JV-1010 (family {reply.family:02X}, number {reply.family_number:02X}). Check the port selection.",
            reply,
            log_lines=log,
        )
    lines = ["Roland JV-1010 found.", f"Device ID: {reply.device_id} ({reply.device_id:02X}H)", f"Software revision: {reply.revision.hex(' ').upper()}"]
    name, read_ok = None, None
    if read_patch:
        # one read-only request: the temporary patch's common block, whose first 12 bytes are the patch name
        block = connection.request(patch.Patch.requests(patch.TEMPORARY_BASE)[0], _is_common_block, timeout, pump)
        read_ok = block is not None
        if read_ok:
            data = sysex.parse(block).data
            name = "".join(chr(b) if 32 <= b <= 125 else " " for b in data[:12]).rstrip()
            lines.append(f'Temporary patch: "{name}"')
        else:
            lines.append("It did not answer a data request. (The unit ignores them in GM mode.)")
        log.append(f"temporary patch read: {'ok, name ' + repr(name) if read_ok else 'no reply'}")
    return HardwareResult(JV1010, "\n".join(lines), reply, name, read_ok, log)
