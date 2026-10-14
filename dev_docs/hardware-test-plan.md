# Hardware test plan: the real JV-1010

Rewritten 2026-10-14 for **one dedicated session at the unit**. Everything below runs against `--demo` and in the tests (600+ of them); what is NOT known is whether the real unit agrees.
Each step has an ID (A1, B3...) and says what it is the **first proof of**, so a pass or a fail means something. Time estimates are guesses. A results sheet to fill in is at the end.

**Close DAWs and MIDI monitors first** (AGENTS.md, "Hardware safety"). Record results in AGENTS.md's findings log as `[hardware YYYY-MM-DD]` (a pass is worth one line too: it turns a `[guess]` into a
measurement). Keep `~/.jv-studio/jv-studio.log` from the session; if anything surprising happens, that file plus the macOS crash report is what to share.

## How to spend the time

| Tier | Time | What it buys | Needs |
| --- | --- | --- | --- |
| **A: essentials** | ~30 min | Reads work; the unit follows the app and the app follows the unit; one live write proven (the one everything else rests on) | nothing spare |
| **B: the writes** | ~60 min | System settings, scale tune, USER patch write, Unit Mode switch, performances, rhythm sets, master volume and GM, a third-party bank | a spare USER patch slot, performance slot and rhythm set; a tuner or a good ear |
| **C: if time is left** | ~20 min | Restore, small checks, what the app shows when something is wrong | the A0 backup |
| **D: optional** | n/a | Firmware | a different MIDI interface |

Do A completely. In B, go in the order given (each write path assumes the one before it). If a step fails, **stop that tier**, note the log line, and move to the next tier's read-only steps.

## Before you leave the desk (5 min, no hardware)

- [x] `uv run pytest` passes and `uv run jv-studio --demo` opens: the demo walks through every window below (it loads `~/.jv-studio/demo-backup.syx`, your own unit, when that file exists).
- [x] Decide your interface. The Midiplus 2x2 is proven for everything except messages over 256 bytes, which only the firmware update uses.
- [ ] Have headphones or speakers on the unit and, for B2, a tuner app or a reference pitch.
- [ ] Open the log folder (Help > Open Log Folder) so it is one click away.
- [ ] Settings > Appearance: "Middle C is" C3 (the default) names note 60 C3. The unit's own displays use Roland's names (60 = C4): when you compare a key range on the unit with the app, remember the one-octave difference, or switch the setting to C4 for the session.

---

## Tier A: essentials

### A0. Safe start (3 min)

- [x] File > **Back Up Unit...** (done 2026-10-13: 1,300 requests, no block missing, every value inside the manual's ranges: see AGENTS.md). **Do it again before this session** and keep the file outside the app's folders.
- [ ] The unit is in **Patch mode** and shows a USER patch (not GM mode: RQ1/DT1 are ignored there).
- [ ] Launch the app with the unit on. The status pill (top right) should go green and say **JV-1010 · Patch mode**. If it says "Ports open" and stays grey, or "No answer from the unit" (red), note it: that is the first read failing.

### A1. Reading (6 min, nothing is written)

- [ ] **Start-up chain:** the temporary patch appears, then the 128 USER names fill the list one by one (a progress bar runs). One error stops the rest: note which read failed. *First proof of:* the start-up reads on the real unit, and of the progress/appearing-names feedback.
- [ ] The patch header says **Temporary patch · \<the name on the unit's display\>** and no "values outside the manual's ranges" line shows. The row of the patch the unit is playing is **bold with a dot** in the list (from the System block's selection).
- [ ] The list says how many differ from the factory list (you think "basically stock"; the 2026-10-13 backup had 1: USER 084).
- [ ] Open two or three USER patches (double-click) and compare name, level and tempo with the unit's display.
- [ ] Hardware > **System Settings...**: it reads (settings and scale tune together). The line at the top names the mode and patch correctly. **Two things the 2026-10-13 backup showed:** Master Tune should read **437.6 Hz** (raw 51; if the unit's own display says something else, the Hz mapping is off), and the **EFX / Chorus / Reverb switches are all OFF** (is the unit really dry? you may want them back ON: that is B1).
- [ ] **Performances tab** (loads when first opened, with a progress bar: temporary performance, then 32 names): part-to-patch assignments match the unit's PERFORM display. **Rhythm Sets tab** (same): the two names (the backup had HouseDrumSet and JazzDrumSet1) and the temporary rhythm set. *First proof of* the reads at `01 00 00 00` and `02 09 00 00` in Patch mode (they may be refused there: note it and which mode you were in).
- [ ] The **filter box** above the list narrows it as you type (try "pad" and a number).
- [ ] **Detect** is now Hardware > Detect JV-1010 (Ctrl+D): it should report the unit and its temporary patch.

### A2. The unit and the app follow each other (6 min, nothing is written)

- [ ] Turn the unit's **VALUE knob** to another patch, then **Ctrl/Cmd+R** (Read Temporary Patch): the app shows that patch. Then turn the knob again and press **Ctrl/Cmd+Shift+R** (Refresh All): the bold dot in the list and the audition bar's bank and patch boxes move to it. *This relies on the System block's selection changing as you turn the knob `[guess]`: if the dot and the boxes stay put, tell me, and I will match the patch by its name instead.*
- [ ] Rename a USER patch **on the unit** and Store it, then Refresh All: the list shows the new name.
- [ ] With the unit in Patch mode, change the **PART knob** (the Patch Receive Channel) and Refresh All: the audition bar's channel follows on the Patches tab.

### A3. Audition keyboard (8 min, plain MIDI: nothing is stored)

- [ ] Cmd+K opens the bar (it starts closed; while open it takes the computer keyboard). Click keys and type A S D F: the unit plays on the channel shown. C/V change how hard (snapping to multiples of 10). Z/X move the octave; the blue bar under the keys and "Octave: ..." follow. **Panic** silences a hung note. *First proof of:* notes and velocity reach the unit, and that note names match what you expect (60 = C3 by default).
- [ ] Choose patches in the Patch box, with the arrows, and with `,` `.` (previous/next patch) and `[` `]` (previous/next bank): the unit's display follows each one. *First proof of* Bank Select + Program Change (User 80/0, PR-A..E 81/0-4, Session 84/0-1). Holding `.` should scrub through patches smoothly: note if the unit chokes.
- [ ] **The editor follows the bar:** stop on a patch and, about a third of a second later, the editor shows it (header "Temporary patch"). Note if it ever shows the previous patch (too early: tell me and I will lengthen the wait). With unsent edits in the editor, choose another patch: your edits must stay, with a status message.
- [ ] **Double-click a USER patch:** the unit switches to it (display and sound), the bar's boxes move, and the status bar says "... is playing on the unit: your edits are heard as you make them". If it says "the unit is not playing it", note why (mode, Receive Program Change, channel) and whether the unit really changed patch. *First proof of* "Program Change loads the stored patch into the temporary patch EXACTLY" (the app compares all five blocks).
- [ ] **Categories:** pick "Piano (category)" and 008: the unit shows Bright Piano (bank PrA, number 002) and the same sound as the bank route. On the unit turn CATEGORY to SYNTH/PAD and VALUE to **053-056**: the manual prints 053 DanceStack 6, 054 DanceStack 8, (nothing at 055), 056 Big BPF, but the app lists 054 DanceStack 7 and 055 DanceStack 8 (from a Max for Live editor; unconfirmed). **Tell me what the unit shows at 054, 055 and 056.**
- [ ] **Master slider** to about 60 and let go: the unit gets quieter (this is B7's first step; do it here if the bar is open). Back to 127.

### A4. The one write everything rests on (6 min, heard, not stored)

- [ ] With the temporary patch showing and **Live edits** on, turn Filter Cutoff (or Pitch): the sound changes on the unit. **First proof that a single-parameter DT1 on a patch parameter works.** If a warning says the unit did not take the edit, live sending switches itself off: note which parameter and the message.
- [ ] Switch a tone on or off with the **check box in the Wave heading** and turn a **Tone Mixer** knob on the Common tab: you hear the tone appear/disappear and its level change; the tone's tab dot (● on, ○ off) follows.
- [ ] Drag an envelope handle (one release, one change; Esc cancels). **Undo** (Cmd+Z) puts it back on the unit too.
- [ ] **Send to Temporary Patch** with a USER patch open (a file or a slot you did not double-click): it plays on the unit (a whole-patch write with a read-back).

**If A4 passes, the editor is proven. If it fails, nothing below that edits live is worth trying: report the log line.**

---

## Tier B: the writes

Every write below saves what it replaces to `~/.jv-studio/backups/` first and reads back; the first change of a session also offers a whole-unit backup.

### B1. System settings (6 min: a small write)

- [ ] System Settings > Settings: change **Master Tune** by one step (440.0 to 440.2 Hz) and **Apply to Unit...**. The confirmation lists it; `SYSTEM-<time>.syx` appears in the backups folder; the status bar says "read back"; the unit's tuning screen agrees. **Change it back and apply again.**
  *First proof of:* single-parameter DT1 in the System area, and that the backup file is a real 18-block System section.
- [ ] Check boxes and two-button toggles in this window (Effects, MIDI Receive, Clock Source...) show the unit's values correctly. If the three effect switches really are OFF, turn them ON and Apply: the patches now have reverb and chorus.
- [ ] Optional, 1 min: turn **Receive Program Change** off, Apply, and check the audition bar's patch box stops working; turn it back on, Apply, and it works again.
- [ ] The Sound Mode toggle offers only Performance | Patch (GM is refused here on purpose).

### B2. Scale tune (8 min: the biggest unknown here; 17 small blocks)

Open System Settings > **Scale Tune**. Patch mode is selected first. In this order, each step needs the one before it:

- [ ] **Read check:** all 12 knobs show 0 for every target (the factory state is every byte 64). Anything else: note it, it is how the unit really is.
- [ ] **Write check:** pick the **Arabian-type Scale** preset, Set, Apply. The confirmation lists the changes and **warns that Scale Tune Switch is OFF** (if it is). The status bar says "read back", and reopening the tab (Read from Unit) shows the same values. *First proof of:* a 12-byte DT1 at `00 00 20 00`.
- [ ] **Hear it:** in Settings > Tuning & Clock tick **Scale Tune** and Apply. Play C then C# on the audition keyboard: C# (+45 cents) is almost a quarter-tone above equal. Untick it: back to normal. A tuner agrees: C reads about -6 cents, E about -51. *First proof of* the switch gating it and the cents/raw maths (64 = 0).
- [ ] **Which block does Patch mode use?** Set **Part 1** to a strong tuning (a single note at +50 cents), leave Patch mode at equal, switch on, and play that note on **channel 1** in Patch mode. Does it sound off? Then do the same with the Patch mode block instead. Record which one the unit obeys. *A real unknown; either answer is useful.*
- [ ] **Power-cycle** and reopen System Settings: does the scale tune survive (battery-backed) or reset? Record it.
- [ ] **Put it back:** Equal Temperament preset, **Copy to All**, Apply (the first multi-block write; the status bar says how many changed), untick the switch if it was off, Apply.

### B3. USER patch writes (7 min: stored)

- [ ] Pick a slot you can spare. **Write to USER...** (the button takes the accent colour while the patch has unsent edits): a backup appears, the status bar says "read back", and the unit's display shows the new name.
- [ ] **Power-cycle** the unit and read the slot again: it kept the write.
- [ ] Rename, then Copy To... and Swap With... on spare slots (all three write whole patches with a backup first). *First proof of:* the 129-byte tone as 128 + 1 packets, and the 20 ms gap.

### B4. Unit Mode switch (5 min: a one-byte System write)

- [ ] Hardware > **Unit Mode** shows the unit's current mode ticked. Choose the other (Performance): the status bar says it is saving the System settings, then "The unit is in Performance mode now". **The unit's own display/indicator changes to PERFORM.** Note how long it takes and whether the unit applies it at once or needs a moment. *First proof of* writing Sound Mode live, and of the one-byte DT1 at `00 00 00 00`.
- [ ] Open the **Patches** tab: the status pill turns amber and says "JV-1010 is in Performance mode · click to switch to Patch". **Click it**: the unit goes back to Patch mode and the pill goes green.
- [ ] **Power-cycle** with the unit in Performance mode: does it start in Performance mode (it is stored)? Switch it back to Patch mode afterwards.
- [ ] With the unit in Performance mode, **Hardware > GM System On...**: the pill goes amber "GM mode" and Unit Mode items grey out. **GM System Off** brings it back (B7 covers this).

### B5. Performances (10 min)

- [ ] Put the unit in Performance mode (B4). **Read Temporary Performance**; edit a part's level live and hear it. **First proof of `01 00 00 00` and single-parameter writes on performance parameters.**
- [ ] On the **Part** tab choose Part 2: the audition bar's **channel becomes Part 2's** and its **patch boxes show Part 2's patch**; play a key and Part 2 sounds (Part 2 must receive on that channel and be on). Choose Part 5: the bar follows.
- [ ] Change a part's patch with **Choose Patch...** (try a category: "Piano (category)") and hear the part change.
- [ ] **A patch from the bar for a part:** with a part shown, choose a patch in the audition bar: the unit's part takes it, and about a third of a second later the performance editor shows the new patch for that part. *First proof of* "Program Change in Performance mode sets the part's patch" and of reading it back.
- [ ] Open a USER performance, **Send to Temporary Performance**, then **Write to USER...** a spare slot; power-cycle and re-read.
- [ ] What does **part 10** play? (The rhythm set.) Note what the unit shows.

### B6. Rhythm sets (10 min; needs a spare USER rhythm set: 1 or 2)

Keep the unit in **Performance mode**. Open the **Rhythm Sets** tab: the audition bar's **channel goes to Part 10's** (10, or what the performance says) and its patch boxes grey out (a patch chosen on Part 10 would replace the rhythm set).

- [ ] **Choose a set on the unit:** right-click USER set 1 > **Choose on Unit (Part 10)** (Bank Select 80/0 + Program Change 0): the unit's display shows the set. Then **Read Temporary**: the name and keys match the unit. A line "outside the manual's ranges" is a table bug. *First proof of* RQ1 at `02 09 00 00` and the 65-block read.
- [ ] **Hear a key:** click a key on the mini keyboard (Play on click): the unit plays that drum on Part 10. If silent: Part 10's receive switch and channel; the unit's mode.
- [ ] **Live edit:** change the chosen key's Tone Level, Coarse Tune or Filter Cutoff and click the key again: it sounds different. *First proof of* a single DT1 into the temporary rhythm set. Drag a level-envelope handle (decay): hear the key shorten.
- [ ] **A whole key:** Copy Key To... (the snare to a spare key) and click both: identical. Undo: the spare key is back. *First proof of* a 58-byte block write at `02 09 kk 00`.
- [ ] **Does it last?** Choose another rhythm set on the unit, then back: are your live edits gone (the unit re-reads the stored set) or kept? Record it.
- [ ] **Store it:** Send to Temporary, then **Write to USER...** the spare set (a backup `RHYTHM-n-<time>.syx` appears, "read back"), power-cycle, choose that set on the unit, Read Temporary: the edits are there. *First proof of* 65 DT1s at the 20 ms gap into `10 40/41 00 00`.
- [ ] Restore it from the backup file (File > Open Rhythm Set .syx, then Write to USER) or leave the spare as it is.

### B7. Universal SysEx: master volume and GM mode (5 min; plain MIDI, nothing is stored)

- [ ] **Master volume:** drag **Master** down to about 60 and let go: the unit gets quieter. Back to 127. *First proof of* `F0 7F 7F 04 01 00 mm F7`. Power-cycle: it should be back at full whatever the slider says `[guess]`: note whether it is.
- [ ] **GM System On:** Hardware > **GM System On...** (it asks first). The unit shows its GM indicator and sounds as General MIDI (Piano 1 on the parts); the pill says "GM mode: the unit ignores this app". Press Read Temporary Patch: the app says the unit ignores data requests in GM mode (the expected result). *First proof of* GM On and of "GM mode ignores RQ1".
- [ ] **GM System Off:** the manual says the unit returns to Performance mode (which indicator lights?). Refresh All from Unit (Ctrl/Cmd+Shift+R): the reads work again and the pill shows the real mode. If GM does not come back off, press the unit's VALUE knob until another mode shows.
- [ ] Is the Master slider ignored in GM mode, as the manual says?

### B8. A third-party bank (6 min; "JV-1010 Pads Galore" by Xavier Radix, in your Downloads)

- [ ] File > **Open Patch .syx...**: a list of **15 patches** (Big Ol' Pad ... The End) appears; the blank "INIT PATCH" slots are hidden behind a check box; the note says 11 had wrong checksums (a tool slip in the file; the values are in range). Open one: it shows in the editor.
- [ ] **Send to Temporary Patch** and play it on the unit: it should sound like a pad. Try one from the first five (valid checksums in the file) and one from 6-16 (repaired): do both sound right? If one sounds wrong, the file or our reading of it is at fault: tell me which.
- [ ] If you like one, **Write to USER...** a spare slot. (Your comment-thread check for other users' trouble with the file: the wrong tone checksums and the single temporary-patch address are the likely cause.)

---

## Tier C: if time is left

### C1. Restore (the scary one: last, and only with the A0 backup)

- [ ] Change a USER patch, then Restore only **USER patches** from the A0 backup: the patch comes back.
- [ ] Restore the **System settings** section from a `SYSTEM-<time>.syx` the app wrote in B1/B2/B4 (a full 18-block section): the master tune / scale tune / mode come back. This is off by default on purpose: it changes master tune and MIDI channels.

### C2. Small things to look at

- [ ] Wave and effect names in the editor match the unit's display for a few patches (INT-A / INT-B / Session waves; effect types).
- [ ] Structure types 1-10 and the Booster greying: with type 03 or 04 the booster is the only thing that changes the sound.
- [ ] Apostrophe names (e.g. "Player's EP") read back exactly (the manual prints typographic quotes; the unit stores ASCII).
- [ ] The identity reply's software revision is `00 00 00 00`. If the service test mode is ever used, note the real version (that tells you whether the unit is already on 1.02).
- [ ] Preview notes: System Settings > Preview: change a note, Apply, press the unit's Phrase Preview: it plays the new note.
- [ ] **What the app shows when something is wrong:** switch the unit off and press Refresh All: the pill should go red "No answer from the unit" and the status bar says it could not read; switch it on and Refresh All: green again. Unplug the MIDI cable and do the same.
- [ ] Light theme (Settings > Appearance) once over the Patch, Performance and Rhythm pages: check boxes, toggles, the pill and the bold "playing" row read well.
- [ ] Narrow the window below about 1170 px: the audition keyboard scrolls sideways instead of squeezing its keys; Z/X scroll the played octave into view.

---

## Tier D (optional): firmware. NEVER TRIED: the riskiest thing in the app

Hardware > Update Firmware... exists, but nobody has run it on a unit. You do not have to. If you decide to:

1. Note the unit's current version first (service test mode shows it; the identity reply does not). If it is already 1.02 there is nothing to gain.
2. Back the unit up (A0).
3. Run the loopback test in Settings with a MIDI cable from OUT to IN and see the **265-byte** row pass. The Midiplus 2x2 stopped at 256, so probably use a different interface.
4. Close everything else, then follow the dialog. Keep the log. Afterwards: Factory Reset, restore the backup.

## When the session is over (5 min at the desk)

- [ ] `grep -E "WARNING|ERROR" ~/.jv-studio/jv-studio.log`: every "outside the table's ranges" line is a table bug or a manual error; every "did not take" line is a write the unit refused.
- [ ] Add one line per step to AGENTS.md's findings log (`[hardware date] ...`), and change the matching `[guess]`/"NOT tried" notes: the sections "System settings editor", "The audition bar", "The rhythm set editor", "Universal SysEx" and "Firmware update player" each end with what is unknown.
- [ ] Tick the matching lines in `dev_docs/roadmap.md`.

## What is proven, and what each step proves

| Thing | Status | First proved by |
| --- | --- | --- |
| Identity, RQ1/DT1 framing, checksum, device ID 10H | **proven** 2026-10-13 | Detect JV-1010 |
| Patch reads (temporary and USER), the table's ranges | **proven** 2026-10-13 (a whole-unit backup validates with zero out-of-range values) | A1 |
| Whole-unit backup | **proven** 2026-10-13 | A0 |
| The start-up chain, progress bars, names appearing one by one | untested | A1 |
| Temporary performance / rhythm set reads in Patch mode | untested | A1 |
| The System block's selection follows the front panel | untested `[guess]` | A2 |
| Notes / Program Change / Bank Select; categories; the DanceStack 7 / 8 numbering | untested | A3 |
| Program Change loads the stored patch EXACTLY (the follow check) | untested | A3 |
| Single-parameter DT1 on a patch parameter (live edit) | untested | A4 |
| Whole-patch write with read-back (Send to Temporary Patch) | owner: "seems to work", no detail | A4 |
| System block single-parameter DT1 | untested | B1 |
| Scale tune blocks, 12-byte DT1, which block Patch mode obeys | untested | B2 |
| USER patch write, 129-byte tone as 128 + 1, 20 ms gap | untested | B3 |
| Unit Mode switch (Sound Mode live, stored) | untested | B4 |
| Performance writes, `01 00 00 00`, a part's patch by Program Change | untested | B5 |
| Rhythm sets: live edit at `02 09 00 00`, whole-key write, USER write | untested | B6 |
| Universal SysEx (Master Volume, GM On/Off) | untested | B7 |
| The third-party bank | untested | B8 |
| Restore | untested | C1 |
| Firmware update | untested, optional | D |

## Results sheet

Copy this, and fill it in as you go (pass / fail / what you saw).

| Step | Result | Notes |
| --- | --- | --- |
| A0 start, pill green | | |
| A1 start-up chain + names + System view + tabs | | |
| A2 follows the front panel | | |
| A3 notes, patch choice, follow, double-click, categories | | |
| A4 live edit, tone switch, mixer, Send | | |
| B1 System write | | |
| B2 scale tune (and which block Patch mode obeys) | | |
| B3 USER patch write | | |
| B4 Unit Mode switch | | |
| B5 performances | | |
| B6 rhythm sets | | |
| B7 master volume + GM | | |
| B8 third-party bank | | |
| C restore / small checks / failure states | | |

## If something goes wrong

Stop, don't retry blindly, and keep the log. Nothing in the app can brick the unit apart from Update Firmware (Tier D). A failed write is why every write saves the old contents first:
they are the `.syx` files in `~/.jv-studio/backups/`, and File > Open Patch .syx (or Restore Unit, which also reads the `SYSTEM-<time>.syx` files) puts them back.
If the unit stops answering after a System change, power-cycle it; if it is still silent to SysEx, check its mode: GM mode ignores RQ1/DT1 (Hardware > GM System Off, or the front panel, changes it back).
