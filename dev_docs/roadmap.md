# Roadmap

Status as of the first commit. Each phase ends with something runnable and tested. "Hardware" items need a real JV-1010 and are done by the owner;
record what they find in `AGENTS.md` (measured vs. guessed, dated).

## Phase 0 - Foundation (done)

- [x] Project scaffold (uv, PySide6 6.12, Mido, python-rtmidi, pytest, GPL-3.0).
- [x] `tools/extract_params.py`: the manual's Parameter Address Map -> `data/parameters.json`, self-checked byte for byte against the manual's own sizes.
- [x] `core/sysex.py`: RQ1/DT1 framing, checksum, 7-bit address maths, 128-byte packet splitting, identity request/reply. Tested with the manual's worked examples.
- [x] `core/params.py`: the table, reading/writing values (nibbled, strings), display formatting.
- [x] `core/patch.py`: a patch as common + 4 tones, to/from sysex messages and `.syx` files.

## Phase 1 - App shell (done, untried on hardware)

- [x] Theme (dark/light/system) and QSS, adapted from AKAISDS.
- [x] Main window (connection card, Detect JV-1010), About dialog, Help > Open Log Folder. (A quick-start guide waits for a real editor.)
- [x] Config (`~/.jv-studio/config.json`), debug log (`~/.jv-studio/jv-studio.log`), crash handlers, dialog logging.
- [x] Settings window: MIDI input/output port, theme.
- [x] Diagnostics in Settings: **loopback test** (cables, ports) and **hardware detection** (Identity Request, then one read of the temporary patch's name).
- [x] MIDI transport with SysEx in/out (`core/midi.py`): thread-safe close, split-SysEx reassembly, one request at a time.
- [ ] Reply matching tolerant of stray replies (AKAISDS `core/reply_matching.py`): needed once the editor reads blocks in bulk; decide with the first hardware logs.
- [x] Hardware (2026-10-13): hardware test passed on the owner's JV-1010 via a MIDI 2x2 (identity answered, device ID 16, temporary patch name read). The loopback test on that interface fails above 256 bytes, which the JV-1010 never needs (see `AGENTS.md`).

## Phase 2 - Talking to the unit (hardware)

- [x] Read the temporary patch (5 x RQ1) and show every parameter, flagging values outside the manual's ranges (read-only viewer; **try it on the unit**).
- [x] Read the 128 USER patch names and any one USER patch (a persistent worker thread, one request outstanding at a time).
- [x] Core: write a patch (DT1, tones split 128 + 1, >= 20 ms apart) with a read-back that must match (`JV1010Unit.write_patch`, tested against a fake). Wired to *Write to USER...* and *Send to Temporary Patch*.
- [x] Core: single-parameter DT1 for live edits (`JV1010Unit.write_param`). The manual's own example does this for a performance parameter: **confirm for patch parameters on the unit.**
- [x] Wire writing into the UI: "Send to Temporary Patch" with the read-back, then a confirmed "Write to USER:nnn" with a `.syx` backup of the slot (aborts if the backup fails).
- [x] Whole-unit Back Up / Restore (`core/memory.py`, `core/backup.py`): one `.syx`, selectable sections on restore, system settings last and off by default, read-back per block.
- [x] Stock check: the USER patch names/key assign against the manual's factory list (a hint, not proof).
- [ ] **Hardware, in this order:** (1) Back Up Unit and keep the file; (2) read the names, look at the stock check; (3) Send to Temporary Patch; (4) Write to USER on a slot you can spare, power-cycle, read it back; (5) Restore of USER patches only; (6) only then, System settings. Record each result in AGENTS.md.
- [ ] Verify on hardware (the full ordered checklist is `hardware-test-plan.md`): the 129-byte tone as 128 + 1; the 20 ms gap; what happens in GM mode (the unit ignores RQ1/DT1 there); the identity reply's revision bytes.
- [x] Backup before every USER write (`~/.jv-studio/backups/`), and an offer of a whole-unit backup before the first change of a session.

## Phase 3 - Patch editor

- [x] Working copy: edits are local until sent/written, Revert Edits, a discard prompt. [x] Undo. [x] The USER list opens a slot (double-click or Enter).
- [x] Patch Common page (table-driven cards: Patch, Play, Structure, Controllers, EFX, Chorus, Reverb & Delay). Still plain controls: no knobs yet.
- [x] Tone pages x4, table-driven (Wave, Ranges, Controllers, LFO 1/2, Pitch, Filter, Level, Pan, Output). [x] Draggable pitch / filter / level envelope graphs.
- [x] EFX parameter names and ranges for the 40 types (extracted). [ ] Display mapping (the manual gives raw ranges only) and chorus/reverb pages beyond the plain knobs.
- [x] Wave names and a picker for INT-A, INT-B and the SR-JV80-09 Session board (names from a third-party list; the Owner's Manual only has the group table). [ ] The Vintage Synth board's Group ID: measure it on a unit with that board.
- [x] Live edit: each edit goes to the temporary patch on release, verified, when the shown patch is the one the unit is playing. [ ] Confirm single-parameter DT1 on patch parameters on the unit.

## Phase 4 - Library

- [ ] Open/save `.syx` (one patch, a bank of 128).
- [x] Rename, copy and swap USER patches (backup first, read back). [ ] Initialise a slot; categories; open/save a bank of 128.
- [x] Undo/Redo. [ ] Compare a patch with the unit's.

## Phase 5 - Performance mode

- [x] Performance model, reads and verified writes (`core/performance.py`, `unit.read_performance` / `write_performance` / `write_performance_param`), USER performance names, backup before a USER write.
- [x] Performance editor: a 16-part mixer, one part in detail, effects, setup (name, tempo, voice reserve), patches chosen by name (USER, PR-A to PR-E, Session), undo, live edit to the temporary performance, `.syx` open and save.
- [x] **Hardware:** read the temporary performance, edit live in Performance mode, write a USER performance and read it back. Check what part 10 plays (the rhythm setup?).
- [x] Rename, copy and swap USER performances; the rhythm setups (USER:1-2, 64 notes each); the temporary patches of the parts (`02 0n 00 00`).

## Phase 6 - Polish and release

- [x] A fake JV-1010 over fake MIDI ports for demos and tests (as AKAISDS does for the S1000/A4000/S950).
- [ ] Packaging (Nuitka, as AKAISDS), CI (GitHub Actions), screenshots, the manual.

## Phase 7 - Firmware and the rest of the manual (surveyed 2026-10-14)

Found by reading the Owner's Manual's MIDI Implementation chapter against what the app exposes. None of it needs new protocol knowledge unless noted.

- [x] **Firmware update player** (`core/firmware.py`, `ui/firmware_dialog.py`, Hardware > Update Firmware...): reads Roland's System Update 1.02 SMFs, verifies them (Roland checksums, addresses, block checksums, the whole-image
  marker, "RolandJV1010", and a content fingerprint of the known release), then plays them as a sequencer would. **Written without a unit: UNVERIFIED, at the owner's risk**, and the dialog says so. Output only.
- [ ] **Hardware, firmware (only if the owner decides to try it):** check the unit's current version first (service test mode); back up; check the interface passes a 265-byte loopback (the Midiplus 2x2 stops at 256, so it will probably NOT);
  play the set; Factory Reset; restore. Record everything in AGENTS.md. Open: does the unit answer in update mode, what does it do with the header message, does it check the block checksums and the `F0 3D` marker.
- [x] **Audition from the app** (no new write path; `ui/audition_bar.py`, Cmd+K): a note keyboard (mouse and computer keys, velocity, channel, Panic) and a patch browser using Bank Select + Program Change (the manual's bank table), plus Play on Unit in the USER list. **Hardware:** play a note, choose a patch, check the unit follows; try From Unit.
- [x] **System settings editor** (`ui/system_dialog.py`, Hardware > System Settings...): the 31 settings the JV-1010 has (the rest of the ~100 are the JV-1080 family's), applied as a diff with a backup, only the changed parameters sent, read back. **Hardware:** try it, starting with a harmless one (Master Tune, then back).
- [x] **Scale tune** (the Scale Tune tab of System Settings: 12 notes in cents for Patch mode and each part, the manual's three tunings on any tonic, Copy to All). **Hardware:** test plan B2 (which block Patch mode obeys, power-cycle persistence).
- [x] **Rhythm set editor** (2 USER sets x 64 keys: key grid, per-key tone editor, copy/swap keys, live edits to the temporary rhythm set, write to USER). Built 2026-10-14, NOT tried on a unit: see `dev_docs/hardware-test-plan.md` B5. Not done: the factory rhythm sets (read-only on the unit), copy/swap of whole sets.
- [ ] **Library**: open/save a bank of 128 `.syx`, initialise a slot, edit USER patches in place from the list, compare a patch with the unit's; rename/copy/swap performances.
- [ ] Smaller: Universal SysEx (master volume, GM On/Off), the unit's own Data Transfer (performance dump), per-effect display mapping, an interface check ("can this port pass a 265-byte message?") before any long write.

## Open questions

- Firmware: see the hardware item above. Nothing about update mode is documented beyond Roland's README (message formats were decoded from the files, 2026-10-14; AGENTS.md).

- Does the unit accept a single 129-byte DT1 for a tone, or only the manual's 128-byte packets? (The 2015 `jv1010tool` sends one message.)
- How soon after an RQ1 does the unit answer, and in what order/spacing do the five blocks of a patch arrive?
- Does a DT1 to the temporary patch change the sound immediately while a performance is selected? (Patch mode vs performance mode.)
