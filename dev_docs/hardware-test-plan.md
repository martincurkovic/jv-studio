# First session on the real JV-1010: a test plan

Written 2026-10-13, for the owner's unit. Everything below runs fine against `--demo`; what is NOT known is whether the real unit agrees. Go in order: each step is safe only
if the one before it passed. **Close DAWs and MIDI monitors first** (AGENTS.md, "Hardware safety"). Record each result in AGENTS.md's findings log as `[hardware YYYY-MM-DD]`.

Keep the log (`~/.jv-studio/jv-studio.log`) from the session. If anything surprising happens, that file plus the macOS crash report is what to share.

## 0. Before touching anything
- [ ] File > **Back Up Unit...** and keep the `.syx` somewhere outside the app's folders (a cloud folder, a second drive). It is read-only on the unit and takes about half a minute.
- [ ] Hardware > **Detect JV-1010**: found, device ID 16 (10H). (This part is already confirmed.)
- [ ] The unit is in **Patch mode**, not GM mode (the unit ignores RQ1/DT1 in GM mode: the app says so in its error).

## 1. Reading (nothing is written)
- [ ] **Read Temporary Patch**: the name matches the unit's display and no "values outside the manual's ranges" line appears. If one does, the log lists which parameter: that is a bug in the table, not the unit.
- [ ] **Read Patch Names**: 128 names; the status bar says how many differ from the factory list (the owner thinks "basically stock").
- [ ] Open a few USER patches (double-click); check names and a couple of obvious values (level, tempo) against the unit's display.
- [ ] Switch to **Performances > Read Performance Names** (32) and **Read Temporary Performance**: the part-to-patch assignments should match the unit's PERFORM display.
  Open one with USER patch names read first, and check a part's patch name is right (this verifies the group IDs: USER = 1, PR-A = 3 ... PR-E = 7, Session = 2/9).

## 2. Writing to the temporary patch (heard, not stored)
- [ ] Edit one parameter of the temporary patch with **live edit** on (Pitch/Filter cutoff is easy to hear): the sound changes on the unit. **This is the first proof that a single-parameter DT1 on a patch parameter works.**
  If a warning says the unit did not take the edit, live sending switches itself off: note which parameter and the message.
- [ ] Drag an envelope handle: one release, one change; Esc cancels. Undo (Cmd+Z) puts it back on the unit too.
- [ ] **Send to Temporary Patch** with a USER patch open: it plays on the unit.

## 3. Writing a USER patch (stored)
- [ ] Pick a slot you can spare. **Write to USER...**: a backup file appears in `~/.jv-studio/backups/`, the status bar says "read back", and the unit's display shows the new name.
- [ ] **Power-cycle the unit** and read the slot again: it kept the write (the battery-backed memory).
- [ ] Rename, then Copy To... and Swap With... on spare slots (all three write whole patches with a backup first).

## 4. Performance mode
- [ ] Put the unit in Performance mode. **Read Temporary Performance**; edit a part's level live and hear it. **First proof of `01 00 00 00` and single-parameter writes on performance parameters.**
- [ ] Change a part's patch with **Choose Patch...** and hear the part change.
- [ ] Open a USER performance, **Send to Temporary Performance**, then **Write to USER...** a spare performance slot; power-cycle and re-read.
- [ ] What does part 10 play? (Likely the rhythm setup; this is unknown.) Note what the unit shows.

## 5. Backup / restore (the scary one: last)
- [ ] Restore only **USER patches** from the backup made in step 0 after changing a patch: the patch comes back. Then the other sections.
- [ ] Restore **System settings** only if you really want to: it changes master tune, MIDI channels and the sound mode. It is off by default on purpose.

## 6. Small things to look at
- [ ] Wave and effect names in the editor match what the unit's display shows for a few patches (INT-A / INT-B / Session waves; effect types).
- [ ] Structure types 1-10 and the Booster greying: pick type 03 or 04 and check the booster is the only thing that changes the sound with it.
- [ ] Do the patch's apostrophe names (e.g. "Player's EP") read back exactly? (The manual prints typographic quotes; the unit stores ASCII.)
- [ ] The identity reply's software revision is `00 00 00 00`; if the unit's service-mode version display is ever checked, note it.

## 6a. System settings (a write, but a small one)
- [ ] Hardware > System Settings...: it reads; the line at the top matches the unit's display (mode and patch). The values match the unit's SYSTEM menu (master tune, receive channel).
- [ ] Change **Master Tune** by one step and **Apply**: the confirmation lists it, `~/.jv-studio/backups/SYSTEM-*.syx` appears, the status bar says "read back", and the unit's tuning screen agrees. Then change it back.
- [ ] Optional: Receive Program Change off and on again, and check the audition bar's patch box stops and starts working. Never try GM mode from here (it is refused: the unit would stop answering).

## 6b. Audition keyboard (reads and plain notes, nothing stored)
- [ ] Open the bar (View > Audition Keyboard, Cmd+K). **From Unit**: the channel fills in and the note says Patch mode (or what is wrong).
- [ ] Click a key and type A S D F: the unit plays; C/V change how hard. Panic silences a hung note.
- [ ] Choose a patch in the box (and the arrows): the unit's display follows. Then **Read Temporary Patch**: it is the patch you just chose.

## 7. Firmware (optional, and the riskiest thing in the app: NEVER TRIED)
Hardware > Update Firmware... exists, but nobody has run it on a unit. You do not have to. If you decide to: first note the unit's current version (service test mode shows it; the identity reply does not), back the unit up, run the loopback test in Settings
with a MIDI cable from OUT to IN and see the **265-byte** row pass (the Midiplus 2x2 stopped at 256, so probably use a different interface), close everything else, then follow the dialog. Keep the log. Afterwards: Factory Reset, restore the backup.

## If something goes wrong
Stop, don't retry blindly, and keep the log. Nothing in the app can brick the unit apart from Update Firmware (step 7), but a failed write to a USER slot is why every write
saves the old contents first: they are the `.syx` files in `~/.jv-studio/backups/`, and File > Open Patch .syx (or Restore Unit) puts them back.
