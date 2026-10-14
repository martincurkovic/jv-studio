# Hardware test plan: the real JV-1010

Last reorganised 2026-10-14 for **limited time at the unit**. Everything below runs fine against `--demo` and in the tests; what is NOT known is whether the real unit agrees.
Each step says what it is the **first proof of**, so you can see what a pass or a fail means. Time estimates are guesses.

**Close DAWs and MIDI monitors first** (AGENTS.md, "Hardware safety"). Record results in AGENTS.md's findings log as `[hardware YYYY-MM-DD]` (a pass is worth one line too:
it turns a `[guess]` into a measurement). Keep `~/.jv-studio/jv-studio.log` from the session; if anything surprising happens, that file plus the macOS crash report is what to share.

## How to spend the time

| Tier | Time | What it buys | Needs |
|---|---|---|---|
| **A: essentials** | ~20 min | Reads work; one write path proven (the one everything else rests on); the keyboard plays | nothing spare |
| **B: the new writes** | ~40 min | System settings, scale tune, USER patch write, performances, rhythm sets | a spare USER slot, performance slot and rhythm set; a tuner or a good ear |
| **C: if time is left** | ~15 min | Restore, small checks | the step-0 backup |
| **D: optional** | n/a | Firmware | a different MIDI interface, see step 7 |

Do A completely. In B, go in the order given (each write path assumes the one before it). If a step fails, **stop that tier**, note the log line, and move to the next tier's read-only steps instead.

## Before you leave the desk (5 min, no hardware)
- [ ] `uv run pytest` passes (500 tests at the time of writing) and `uv run jv-studio --demo` opens: the demo walks through every window below.
- [ ] Decide your interface. The Midiplus 2x2 is proven for everything except messages over 256 bytes, which only the firmware update uses (step 7).
- [ ] Have something to hear it with (headphones are fine) and, for step B3, a tuner app or a reference pitch.
- [ ] Open the log folder (Help > Open Log Folder) so it is one click away.

---

## Tier A: essentials

### A0. Safe start (2 min)
- [ ] File > **Back Up Unit...**: keep the `.syx` outside the app's folders (cloud folder, second drive). Read-only, about half a minute. **Do this first, always.**
  *First proof of:* whole-unit backup on the real unit (1,300 requests, no reply is dropped).
- [ ] The unit is in **Patch mode**, not GM mode (the app says so in its error if it is in GM mode: RQ1/DT1 are ignored there).
- [ ] Open the audition bar (View > Audition Keyboard, Cmd+K: it starts closed, and while open it takes the computer keyboard, so close it with Cmd+K before typing anywhere) and press **From Unit**: the channel fills in and the note says "Patch mode" (or what is wrong).
  *First proof of:* the System block parses (`sound_mode`, channel, receive switches) and the table's offsets are right.

### A1. Reading (5 min, nothing is written)
- [ ] **Startup auto-load:** with the unit on and the saved ports, opening the app alone fills the temporary patch, the 128 patch names, the 32 performance names and the temporary performance (the status bar walks through them). One error and the rest stop: note which read failed (the temporary performance in Patch mode is the likely one, `01 00 00 00` is unproven). The buttons below are then refreshes. **Front-panel changes:** turn the unit's VALUE knob to another patch, then **Ctrl/Cmd+R** (Read Temporary): the window shows that patch, and **Ctrl/Cmd+Shift+R** also moves the audition bar's bank and patch boxes to it (this relies on the System block's selection changing as you turn the knob: if the boxes stay put, tell me). Change a name on the unit and Store it, then **Ctrl/Cmd+Shift+R** (Refresh All): the USER list shows the new name.
- [ ] **Read Temporary Patch**: the name matches the unit's display and no "values outside the manual's ranges" line appears. If one does, the log lists which parameter: a bug in the table, not the unit.
- [ ] **Read Patch Names**: 128 names; the status bar says how many differ from the factory list (you think "basically stock").
- [ ] Open two or three USER patches (double-click) and compare names, level and tempo with the unit's display.
- [ ] Hardware > **System Settings...**: it reads (settings and scale tune together). The line at the top names the unit's mode and patch correctly, and Master Tune / receive channel match the unit's SYSTEM menu. **Two things the 2026-10-13 backup showed:** Master Tune should read 437.6 Hz (raw 51; if the unit's display says something else, the Hz mapping is off), and the EFX / Chorus / Reverb switches are all OFF (is the unit really dry? that is a System setting you may want back ON).
- [ ] Performances > **Read Performance Names** (32) and **Read Temporary Performance**: part-to-patch assignments match the unit's PERFORM display; with USER names read first, a part's patch name is right (group IDs: USER = 1, PR-A..E = 3-7, Session = 2/9).

### A2. Audition keyboard (3 min, plain notes: nothing is stored)
- [ ] Click keys and type A S D F: the unit plays on the channel shown. C/V change how hard. **Panic** silences a hung note.
  *First proof of:* notes and velocity reach the unit; the channel default.
- [ ] Choose patches in the Patch box and with the arrows (or `,` `.` for the previous / next patch and `[` `]` for the previous / next bank while the bar is open): the unit's display follows each one. Then pick "Piano (category)" and 008: the unit shows Bright Piano (bank PrA, number 002) and the same sound as the bank route. **One extra look:** on the unit turn CATEGORY to SYNTH/PAD and VALUE to 053-056: the manual prints 053 DanceStack 6, 054 DanceStack 8, (nothing at 055), 056 Big BPF, but the app lists 054 DanceStack 7 and 055 DanceStack 8 (from a Max for Live editor; unconfirmed). Note what the unit shows at 054, 055 and 056 and tell me if it differs. Then **Read Temporary Patch**: it is the patch you just chose.
  *First proof of:* Bank Select + Program Change (the manual's bank table: User 80/0, PR-A..E 81/0-4, Session 84/0-1).

### A3. The one write everything rests on (5 min, heard, not stored)
- [ ] With the temporary patch read and **Live edits** on, turn Filter Cutoff (or Pitch): the sound changes on the unit.
  **First proof that a single-parameter DT1 on a patch parameter works.** If a warning says the unit did not take the edit, live sending switches itself off: note which parameter and the message.
- [ ] Drag an envelope handle (one release, one change; Esc cancels). **Undo** (Cmd+Z) puts it back on the unit too.
- [ ] **Send to Temporary Patch** with a USER patch open: it plays on the unit (this one is a whole-patch write with a read-back).

**If A3 passes, the editor is proven. If it fails, nothing below that edits live is worth trying: report the log line.**

---

## Tier B: the new writes

Every write below saves what it replaces to `~/.jv-studio/backups/` first and reads back; the first change of a session also offers a whole-unit backup (say yes if step A0 was not done).

### B1. System settings (5 min: a small write)
- [ ] System Settings > Settings: change **Master Tune** by one step (440.0 to 440.2 Hz) and **Apply to Unit...**. The confirmation lists it; `SYSTEM-<time>.syx` appears in the backups folder; the status bar says "read back"; the unit's tuning screen agrees. **Change it back and apply again.**
  *First proof of:* single-parameter DT1 in the System area, and that the backup file is a real 18-block System section.
- [ ] Optional, 1 min: turn **Receive Program Change** off, Apply, and check the audition bar's patch box stops working; turn it back on, Apply, and it works again.
- [ ] **Never** try GM mode from here: it is refused (the unit would stop answering).

### B2. Scale tune (8 min: the biggest unknown here; 17 small blocks)
Open System Settings > **Scale Tune**. Patch mode is selected first. These go in this order because each step needs the one before it:
- [ ] **Read check:** all 12 knobs show 0 for every target (the factory state is every byte 64). Anything else: note it, it is how the unit really is.
- [ ] **Write check:** pick the **Arabian-type Scale** preset, Set, Apply. The confirmation lists the changes and **warns that Scale Tune Switch is OFF** (if it is). The status bar says "read back", and reopening the tab (Read from Unit) shows the same values.
  *First proof of:* a 12-byte DT1 at `00 00 20 00` and the Patch Mode scale tune block.
- [ ] **Hear it:** in Settings > Tuning & Clock switch **Scale Tune Switch** ON and Apply. Play C then C# on the audition keyboard: C# (+45 cents) is almost a quarter-tone above equal. Switch it OFF again: back to normal.
  *First proof of:* the switch really gates it, and that the cents/raw maths (64 = 0) is right by ear. A tuner agrees: C should read about -6 cents, E about -51.
- [ ] **Which block does Patch mode use?** The manual says scale tune for any part is also recognised in Patch mode, and that is ambiguous. Set **Part 1** to a strong tuning (a single note at +50 cents), leave Patch mode at equal, switch the switch ON, and play that note on **channel 1** in Patch mode. Does it sound off? Then do the same with the Patch mode block instead. Record which one the unit obeys.
  *This is a real unknown; either answer is useful.*
- [ ] **Power-cycle** the unit and reopen System Settings: does the scale tune survive (battery-backed memory) or reset? Record it.
- [ ] **Put it back:** Equal Temperament preset, **Copy to All**, Apply (writes every block that differs, up to 16 here: the first multi-block write; the status bar says how many changed), switch OFF if it was off, Apply.

### B3. USER patch writes (6 min: stored)
- [ ] Pick a slot you can spare. **Write to USER...**: a backup appears, the status bar says "read back", and the unit's display shows the new name.
- [ ] **Power-cycle** the unit and read the slot again: it kept the write.
- [ ] Rename, then Copy To... and Swap With... on spare slots (all three write whole patches with a backup first).
  *First proof of:* the 129-byte tone as 128 + 1 packets, and the 20 ms gap, on a real unit.

### B4. Performance mode (6 min)
- [ ] Put the unit in Performance mode. **Read Temporary Performance**; edit a part's level live and hear it. **First proof of `01 00 00 00` and single-parameter writes on performance parameters.**
- [ ] Change a part's patch with **Choose Patch...** and hear the part change.
- [ ] Open a USER performance, **Send to Temporary Performance**, then **Write to USER...** a spare slot; power-cycle and re-read.
- [ ] What does **part 10** play? (Likely the rhythm setup.) Note what the unit shows.

### B5. Rhythm sets (8 min; needs a spare USER rhythm set: 1 or 2)
Open the **Rhythm Sets** mode. Keep the unit in **Performance mode** (or Rhythm mode) and set the audition **Part 10 channel** to what the unit uses (10 by default).
- [ ] **Read:** right-click USER set 1 > **Choose on Unit (Part 10)** (Bank Select 80/0 + Program Change 0): the unit's display shows the set. Then **Read Temporary**: the name and the keys match the unit. A line "outside the manual's ranges" is a table bug. *First proof of:* RQ1 at `02 09 00 00` and the 65-block read (it may be refused in Patch mode: note which mode you were in).
- [ ] **Hear a key:** click a key on the mini keyboard (Play on click): the unit plays that drum on Part 10. If silent: is Part 10's receive switch on and its channel what you set?
- [ ] **Live edit:** with Live edits on, change the chosen key's Tone Level, Coarse Tune or Filter Cutoff and click the key again: it sounds different. *First proof of* a single DT1 into the temporary rhythm set. Drag a level-envelope handle (decay): hear the key shorten.
- [ ] **A whole key:** Copy Key To... (e.g. the snare to a spare key) and click both: identical. Undo: the spare key is back. *First proof of* a 58-byte block write at `02 09 kk 00`.
- [ ] **Does it last?** Choose another rhythm set on the unit, then back: are your live edits gone (the unit re-reads the stored set) or kept? Record it.
- [ ] **Store it:** Send to Temporary, then **Write to USER...** the spare set (a backup `RHYTHM-n-<time>.syx` appears, the status bar says "read back"), power-cycle, choose that set on the unit, Read Temporary: the edits are there. *First proof of* 65 DT1s at the 20 ms gap into `10 40/41 00 00`.
- [ ] Restore it from the backup file (File > Open Rhythm Set .syx, then Write to USER) or leave the spare as it is.

### B6. Universal SysEx: master volume and GM mode (4 min; plain MIDI messages, nothing is stored)
- [ ] **Master volume:** open the audition bar (Cmd+K) and drag **Master** down to about 60 and let go: the unit gets quieter (play a note, or hold VOLUME for the phrase preview). Drag it back to 127. *First proof of* the Master Volume message `F0 7F 7F 04 01 00 mm F7`. Power-cycle the unit: it should be back at full whatever the slider says (`[guess]`: note whether it is).
- [ ] **GM System On:** Hardware > **GM System On...** (it asks first). The unit should show its GM indicator and sound as General MIDI (Piano 1 on the parts). Then press Read Temporary Patch: the app must say the unit ignores data requests in GM mode (that is the expected result). *First proof of* the GM On message and of "GM mode ignores RQ1".
- [ ] **GM System Off:** Hardware > **GM System Off**: the manual says the unit returns to Performance mode (which indicator lights?). Then Refresh All from Unit (Ctrl/Cmd+Shift+R): the reads work again. If GM On does not come back off, press the unit's VALUE knob until a mode other than GM shows.
- [ ] Is the Master slider ignored while the unit is in GM mode, as the manual says?

---

## Tier C: if time is left

### C1. Restore (the scary one: last, and only with the A0 backup)
- [ ] Change a USER patch, then Restore only **USER patches** from the A0 backup: the patch comes back.
- [ ] Restore the **System settings** section from a `SYSTEM-<time>.syx` the app wrote in B1/B2 (it is a full 18-block section): the master tune / scale tune come back. This is off by default on purpose: it changes master tune and MIDI channels.

### C2. Small things to look at
- [ ] Wave and effect names in the editor match the unit's display for a few patches (INT-A / INT-B / Session waves; effect types).
- [ ] Structure types 1-10 and the Booster greying: with type 03 or 04 the booster is the only thing that changes the sound.
- [ ] Apostrophe names (e.g. "Player's EP") read back exactly (the manual prints typographic quotes; the unit stores ASCII).
- [ ] The identity reply's software revision is `00 00 00 00`. If the service test mode is ever used, note the real version (that tells you whether the unit is already on 1.02).
- [ ] Preview notes: System Settings > Preview: change a note, Apply, press the unit's Phrase Preview: it plays the new note.

---

## Tier D (optional): firmware. NEVER TRIED: the riskiest thing in the app
Hardware > Update Firmware... exists, but nobody has run it on a unit. You do not have to. If you decide to:
1. Note the unit's current version first (service test mode shows it; the identity reply does not). If it is already 1.02 there is nothing to gain.
2. Back the unit up (A0).
3. Run the loopback test in Settings with a MIDI cable from OUT to IN and see the **265-byte** row pass. The Midiplus 2x2 stopped at 256, so probably use a different interface.
4. Close everything else, then follow the dialog. Keep the log. Afterwards: Factory Reset, restore the backup.

## When the session is over (5 min at the desk)
- [ ] `grep -E "WARNING|ERROR" ~/.jv-studio/jv-studio.log`: every "outside the table's ranges" line is a table bug or a manual error; every "did not take" line is a write the unit refused.
- [ ] Add one line per step to AGENTS.md's findings log (`[hardware date] ...`), and change the matching `[guess]`/"NOT tried" notes: the sections "System settings editor", "The audition bar" and "Firmware update player" each end with what is unknown.
- [ ] Tick the matching lines in `dev_docs/roadmap.md`.

## What is proven, and what each step proves

| Thing | Status | First proved by |
|---|---|---|
| Identity, RQ1/DT1 framing, checksum, device ID 10H | **proven** 2026-10-13 | Detect JV-1010 |
| Patch reads (temporary and USER) | **proven** (owner: reads "seem to work") | A1 |
| Whole-unit backup | untested | A0 |
| Notes / Program Change / Bank Select | untested | A2 |
| Single-parameter DT1 on a patch parameter (live edit) | untested | A3 |
| Whole-patch write with read-back (Send to Temporary Patch) | owner: "seems to work", no detail | A3 |
| System block parse and single-parameter DT1 | untested | A1, B1 |
| Scale tune blocks, 12-byte DT1, which block Patch mode obeys | untested | B2 |
| USER patch write, 129-byte tone as 128 + 1, 20 ms gap | untested | B3 |
| Performance reads, writes, `01 00 00 00` | untested | A1, B4 |
| Rhythm sets: read, live edit at `02 09 00 00`, whole-key write, USER write | untested | B5 |
| Universal SysEx (Master Volume, GM On/Off) | untested | B6 |
| Restore | untested | C1 |
| Firmware update | untested, optional | D |

## If something goes wrong
Stop, don't retry blindly, and keep the log. Nothing in the app can brick the unit apart from Update Firmware (Tier D). A failed write is why every write saves the old contents first:
they are the `.syx` files in `~/.jv-studio/backups/`, and File > Open Patch .syx (or Restore Unit, which also reads the `SYSTEM-<time>.syx` files) puts them back.
If the unit stops answering after a System change, power-cycle it; if it is still silent to SysEx, check its mode: GM mode ignores RQ1/DT1 (the front panel changes it back).
