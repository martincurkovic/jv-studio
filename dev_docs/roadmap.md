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
- [x] Config (`~/.jv1010editor/config.json`), debug log (`~/.jv1010editor/jv1010editor.log`), crash handlers, dialog logging.
- [x] Settings window: MIDI input/output port, theme.
- [x] Diagnostics in Settings: **loopback test** (cables, ports) and **hardware detection** (Identity Request, then one read of the temporary patch's name).
- [x] MIDI transport with SysEx in/out (`core/midi.py`): thread-safe close, split-SysEx reassembly, one request at a time.
- [ ] Reply matching tolerant of stray replies (AKAISDS `core/reply_matching.py`): needed once the editor reads blocks in bulk; decide with the first hardware logs.
- [x] Hardware (2026-10-13): hardware test passed on the owner's JV-1010 via a MIDI 2x2 (identity answered, device ID 16, temporary patch name read). The loopback test on that interface fails above 256 bytes, which the JV-1010 never needs (see `AGENTS.md`).

## Phase 2 - Talking to the unit (hardware)

- [x] Read the temporary patch (5 x RQ1) and show every parameter, flagging values outside the manual's ranges (read-only viewer; **try it on the unit**).
- [x] Read the 128 USER patch names and any one USER patch (a persistent worker thread, one request outstanding at a time).
- [x] Core: write a patch (DT1, tones split 128 + 1, >= 20 ms apart) with a read-back that must match (`JV1010Unit.write_patch`, tested against a fake). **Not wired to any button yet.**
- [x] Core: single-parameter DT1 for live edits (`JV1010Unit.write_param`). The manual's own example does this for a performance parameter: **confirm for patch parameters on the unit.**
- [ ] Wire writing into the UI: "Send to Temporary Patch" with the read-back, then a confirmed "Write to USER:nnn" with a `.syx` backup.
- [ ] Verify on hardware: the 129-byte tone as 128 + 1; the 20 ms gap; what happens in GM mode (the unit ignores RQ1/DT1 there); the identity reply's revision bytes.
- [ ] Backup before the first write of a session (`~/.jv1010editor/backups/`).

## Phase 3 - Patch editor

- [ ] Patch list (USER 001-128 with names) with a working-copy model like AKAISDS: edits are local until sent.
- [ ] Patch Common page: name, level/pan/analog feel, bend range, key assign/portamento, structure types, category.
- [ ] Tone pages x4: wave (group/number/gain), FXM, delay, ranges, controller matrix, LFO 1/2, pitch / filter / level envelopes (draggable graphs), pan.
- [ ] EFX / chorus / reverb pages. **Needs the 40 EFX types' parameter tables** (the manual prints prm1-prm12 names and ranges per type; extend the extractor).
- [ ] Wave names: the manual's waveform list (INT-A/INT-B, expansion boards) for the wave selector.
- [ ] Live edit: a changed knob goes to the temporary patch on release (owner's rule from AKAISDS: live UI, MIDI on release).

## Phase 4 - Library

- [ ] Open/save `.syx` (one patch, a bank of 128).
- [ ] Copy/swap/rename/initialise patches; categories.
- [ ] Compare a patch with the unit's; undo.

## Phase 5 - Performance mode

- [ ] Performance common + 16 parts, temporary and user performances, rhythm setups.

## Phase 6 - Polish and release

- [ ] A fake JV-1010 over fake MIDI ports for demos and tests (as AKAISDS does for the S1000/A4000/S950).
- [ ] Packaging (Nuitka, as AKAISDS), CI (GitHub Actions), screenshots, the manual.

## Open questions

- Does the unit accept a single 129-byte DT1 for a tone, or only the manual's 128-byte packets? (The 2015 `jv1010tool` sends one message.)
- How soon after an RQ1 does the unit answer, and in what order/spacing do the five blocks of a patch arrive?
- Does a DT1 to the temporary patch change the sound immediately while a performance is selected? (Patch mode vs performance mode.)
