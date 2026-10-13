"""Back up and restore the unit's whole user memory (Qt-free).

A backup is an ordinary `.syx` file: one DT1 message per block of `memory.plan()`, exactly the bytes the unit sent for each RQ1 (so any SysEx tool can
read it, and `patch.parse_syx` can still pull a single patch out of it). Restore is the reverse and is deliberately careful:

- it checks, BEFORE writing anything, that the backup holds every block of every chosen section (an incomplete backup raises `BackupError`);
- it writes block by block (packets of <= 128 bytes, >= 20 ms apart) and reads each block back to compare; the first mismatch stops it;
- the SYSTEM section (master tune, MIDI channels, sound mode...) is written last and only if asked for: a restore of USER memory must never change how the
  unit is reachable;
- `cancelled()` is polled between blocks, so cancelling leaves the unit with some sections restored and the rest as they were. `restore` says how far it got.
"""

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import memory, sysex


class BackupError(RuntimeError):
    """A backup that cannot be used (incomplete, or not a backup at all)."""


class Cancelled(RuntimeError):
    """The user cancelled a backup or restore."""


@dataclass
class _Slot:
    block: memory.MemBlock
    data: bytearray
    have: bytearray  # 1 where a byte has arrived

    def complete(self):
        return all(self.have)


@dataclass
class Backup:
    slots: dict = field(default_factory=dict)  # block start -> _Slot (every block of the full plan, empty until filled)
    unknown_messages: int = 0  # DT1s that belong to no block of the user memory (ignored)

    def __post_init__(self):
        if not self.slots:
            for block in memory.plan():
                self.slots[block.start] = _Slot(block, bytearray(block.size), bytearray(block.size))
        self._starts = sorted(self.slots)

    def put(self, address, data):
        """Store `data` starting at `address` (a whole block, or one packet of it). Returns False if it lies in no block (ignored)."""
        start = sysex.address_to_int(address)
        index = bisect.bisect_right(self._starts, start) - 1
        slot = self.slots[self._starts[index]] if index >= 0 else None
        if slot is None or start + len(data) > slot.block.end:
            self.unknown_messages += 1
            return False
        offset = start - slot.block.start
        slot.data[offset : offset + len(data)] = data
        slot.have[offset : offset + len(data)] = b"\x01" * len(data)
        return True

    def blocks(self, sections=memory.SECTIONS):
        return [self.slots[b.start] for b in memory.plan(sections)]

    def data(self, block):
        return bytes(self.slots[block.start].data)

    def complete(self, block):
        return self.slots[block.start].complete()

    def summary(self):
        """{section: (blocks present, blocks expected)}."""
        result = {}
        for section in memory.SECTIONS:
            slots = self.blocks([section])
            result[section] = (sum(s.complete() for s in slots), len(slots))
        return result

    def is_complete(self, sections=memory.SECTIONS):
        return all(s.complete() for s in self.blocks(sections))

    def to_syx(self, sections=memory.SECTIONS):
        """The backup as .syx bytes: one DT1 per complete block, in memory order, each as the unit sent it (a tone is one 129-byte message)."""
        return b"".join(sysex.dt1(s.block.address, bytes(s.data)) for s in self.blocks(sections) if s.complete())


def parse_backup(stream):
    """Read a backup (or any .syx holding user-memory DT1s). Messages from other models, other command types and addresses outside the user memory are
    counted and ignored; a corrupt message (bad checksum) raises `sysex.SysexError`."""
    backup = Backup()
    for raw in sysex.split_messages(stream):
        message = sysex.parse(raw)
        if isinstance(message, sysex.Message) and message.command == sysex.CMD_DT1:
            backup.put(message.address, message.data)
    return backup


def read_backup(unit, sections=memory.SECTIONS, progress=None, cancelled=None):
    """Read the chosen sections from the unit: one request per block, one at a time. `progress(done, total)` after each block; raises `Cancelled`."""
    backup = Backup()
    blocks = memory.plan(sections)
    for done, block in enumerate(blocks):
        if cancelled is not None and cancelled():
            raise Cancelled("backup cancelled")
        backup.put(block.address, unit.read_block(block.address, block.size))
        if progress is not None:
            progress(done + 1, len(blocks))
    return backup


def missing_blocks(backup, sections):
    return [s.block for s in backup.blocks(sections) if not s.complete()]


def restore(unit, backup, sections, progress=None, cancelled=None, verify=True):
    """Write the chosen sections of `backup` to the unit. Returns how many blocks were written. See the module docstring for the safety rules."""
    sections = [s for s in memory.SECTIONS if s in sections]
    missing = missing_blocks(backup, sections)
    if missing:
        raise BackupError(f"this backup is missing {len(missing)} block(s) of the chosen sections (first: {missing[0].label}); nothing was written")
    # the system settings last, so a failure part way through never leaves the unit with changed MIDI settings but old patches
    ordered = [s for s in sections if s != memory.SYSTEM] + [s for s in sections if s == memory.SYSTEM]
    blocks = [b for section in ordered for b in memory.plan([section])]
    for done, block in enumerate(blocks):
        if cancelled is not None and cancelled():
            raise Cancelled(f"restore cancelled after {done} of {len(blocks)} blocks")
        unit.write_block(block.address, backup.data(block), verify=verify)
        if progress is not None:
            progress(done + 1, len(blocks))
    return len(blocks)


def default_backup_name(now=None):
    return f"jv1010-backup-{(now or datetime.now()):%Y%m%d-%H%M%S}.syx"


def write_file(path, data):
    """Write bytes atomically (a temp file renamed over the target), so a failed write never leaves half a backup under the real name."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_bytes(data)
    temp.replace(path)
    return path


def user_performance_backup_path(directory, number, now=None):
    """Where the backup of USER performance `number` (0-based) goes: `<directory>/PERF-07-20261013-090507.syx`."""
    return Path(directory) / f"PERF-{number + 1:02d}-{(now or datetime.now()):%Y%m%d-%H%M%S}.syx"


def system_backup_path(directory, now=None):
    """Where the backup of the System settings goes before they are changed: `<directory>/SYSTEM-20261013-090507.syx`."""
    return Path(directory) / f"SYSTEM-{(now or datetime.now()):%Y%m%d-%H%M%S}.syx"


def user_patch_backup_path(directory, number, now=None):
    """Where the backup of USER patch `number` (0-based) goes: `<directory>/USER-007-20261013-090507.syx`."""
    return Path(directory) / f"USER-{number + 1:03d}-{(now or datetime.now()):%Y%m%d-%H%M%S}.syx"
