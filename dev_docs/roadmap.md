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
- [ ] **Hardware:** read the temporary performance, edit live in Performance mode, write a USER performance and read it back. Check what part 10 plays (the rhythm setup?).
- [ ] Rename, copy and swap USER performances; the rhythm setups (USER:1-2, 64 notes each); the temporary patches of the parts (`02 0n 00 00`).

## Phase 6 - Polish and release

- [ ] A fake JV-1010 over fake MIDI ports for demos and tests (as AKAISDS does for the S1000/A4000/S950).
- [ ] Packaging (Nuitka, as AKAISDS), CI (GitHub Actions), screenshots, the manual.

## Open questions

- Does the unit accept a single 129-byte DT1 for a tone, or only the manual's 128-byte packets? (The 2015 `jv1010tool` sends one message.)
- How soon after an RQ1 does the unit answer, and in what order/spacing do the five blocks of a patch arrive?
- Does a DT1 to the temporary patch change the sound immediately while a performance is selected? (Patch mode vs performance mode.)
