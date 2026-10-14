"""Read a `.syx` file that may hold MANY patches, even one made by a tool that got something wrong (Qt-free). The sibling of `patch.parse_syx`, which is strict.

`parse_syx` keys a patch by its address, so a file whose patches all say "temporary patch" (a bank written by a librarian that sends every patch to the edit buffer) collapses to the
LAST one, and a single message with a wrong checksum makes it refuse the whole file. This reads the messages IN ORDER: a new patch starts when the address changes or when a block
that the current patch already has arrives again. A message with a bad checksum is still used (and counted: `FilePatch.repaired`) when it is a whole-or-part block of a patch with 7-bit
data, because the app rebuilds every message with correct checksums when it sends or saves; the patch is then checked against the manual's ranges, and one that is both repaired and out
of range is called `damaged` (a flipped bit, not a tool's slip) and not offered. Nothing here reads or writes the unit.
"""

from dataclasses import dataclass, field

from . import patch, sysex, validate


@dataclass
class FilePatch:
    patch: patch.Patch
    base: tuple  # the address the file put it at (the temporary patch, or a USER slot)
    index: int  # 1-based position among the patches of the file
    repaired: int = 0  # messages whose checksum was wrong (their data was used)
    problems: list = field(default_factory=list)  # validate.Problem: values outside the manual's ranges

    @property
    def damaged(self):
        """A bad checksum AND values outside the ranges: probably a real corruption, not a tool's slip."""
        return bool(self.repaired and self.problems)

    @property
    def blank(self):
        """The unit's own initial name: a slot nobody filled in."""
        return self.patch.name.strip() == "INIT PATCH"


@dataclass
class Collection:
    entries: list = field(default_factory=list)  # complete patches, in file order (damaged ones included: see `FilePatch.damaged`)
    incomplete: int = 0  # patches that were missing blocks (not offered)
    ignored: int = 0  # messages that were not patch data for this model
    unusable: int = 0  # patch messages that could not be used (an 8-bit byte, data outside a block)

    def offered(self, show_blank=False):
        return [e for e in self.entries if not e.damaged and (show_blank or not e.blank)]

    @property
    def damaged(self):
        return sum(1 for e in self.entries if e.damaged)

    @property
    def blank(self):
        return sum(1 for e in self.entries if e.blank and not e.damaged)

    @property
    def repaired(self):
        """How many of the patches that are offered (not blank, not damaged) had a wrong checksum."""
        return sum(1 for e in self.offered() if e.repaired)


def _base_of(address):
    if address[0] == 0x11 and address[1] < patch.USER_PATCH_COUNT:
        return (0x11, address[1], 0, 0)
    if address[0] == 0x03:
        return patch.TEMPORARY_BASE
    return None


def parse(stream):
    """The patches in `stream`, in order (see the module docstring)."""
    total = sum(len(buffer) for _, buffer in patch.Patch.blank().blocks())
    result = Collection()
    current = None  # [base, Patch, set of message offsets used, bytes received, repaired]

    def finish():
        nonlocal current
        if current is None:
            return
        base, built, _seen, received, repaired = current
        current = None
        if received != total:
            result.incomplete += 1
            return
        entry = FilePatch(built, base, len(result.entries) + 1, repaired, validate.out_of_range(built))
        result.entries.append(entry)

    for raw in sysex.split_messages(stream):
        repaired = False
        try:
            msg = sysex.parse(raw)
        except sysex.SysexError as e:
            if str(e) != "bad checksum":
                result.ignored += 1
                continue
            msg, repaired = sysex.parse(raw, check_checksum=False), True
        if not isinstance(msg, sysex.Message) or msg.command != sysex.CMD_DT1 or _base_of(msg.address) is None:
            result.ignored += 1
            continue
        base = _base_of(msg.address)
        rel = sysex.address_to_int(msg.address) - sysex.address_to_int(base)
        if current is not None and (current[0] != base or rel in current[2]):
            finish()  # the same block again, or another address: the next patch begins
        if current is None:
            current = [base, patch.Patch.blank(), set(), 0, 0]
        if not current[1].apply(msg, base):
            result.unusable += 1
            continue
        current[2].add(rel)
        current[3] += len(msg.data)
        current[4] += repaired
    finish()
    return result
