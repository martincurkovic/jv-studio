# JV-1080 support: findings and feasibility (2026-10-15)

Source: the JV-1080 Owner's Manual (`rolandjv-1080ownersmanual.pdf`, a scan, and an OCR'd `_text` copy), MIDI Implementation chapter (printed pp.149-155) and the Bank Select / list pages. Nothing here was tried on a unit (the owner has only a JV-1010).

**How it was checked:** the key pages (150-155) were read as images; the OCR text was used for the rest. About 40 offsets were spot-checked against `parameters.json`. **No full parameter-by-parameter diff was done**: the OCR text is too noisy to compare automatically (ranges and names are mangled). Tags as in AGENTS.md: `[manual]`, `[guess]`.

## Verdict

The protocol is almost the same, and our table is effectively a superset of the 1080's: each 1080 block is the START of the matching 1010 block with the same offsets, and the 1010 adds parameters at the end. Support is a moderate job (a "model profile" threaded through the core), not a rewrite. Without hardware it can only be checked against the manual and a simulation, so ship it read-only and experimental first.

## Identical `[manual]`

- Roland SysEx framing and checksum; **Model ID 6AH** (same as the JV-1010); RQ1 = 11H, DT1 = 12H.
- Address map: System `00 00 00 00`; temporary performance `01 00 00 00`; performance-mode temporary patches `02 0n 00 00`; temporary rhythm setup `02 09 00 00`; temporary patch `03 00 00 00`; USER performances `10 00..1F`; USER rhythm sets `10 40/41`; USER patches `11 00..7F`.
- Block sizes where they overlap: patch tone 129 (`00 00 01 01`), rhythm common 12, rhythm note 58, scale tune 12 (17 blocks).
- Spot-checked offsets that match our table: tone envelopes, LFOs, filter, `tone_level` 0x65, `output_assign` 0x7D, `reverb_send_level` at 128 (a second packet, as on the 1010); patch common effects and reverb (`reverb_type` 0x27, patch tempo 0x2C, pan 0x2F, structure 0x44-0x47); performance common (`reverb_type` 0x28, tempo 0x2D, key range switch 0x2F, voice reserve 0x30-0x3F); performance part 0x00-0x12; System 0x00-0x27 including the sound mode, master tune (0x06), source and receive-switch bytes.

## Differences

### 1. Shorter blocks (RQ1 needs the block's exact size)

| Block | JV-1080 | JV-1010 | What the 1010 adds at the end |
|---|---|---|---|
| System common | 40 (0x28) | 102 | transmit, pedal, C1/C2, bank select groups... (the JV-2080/XP `<...>` items) |
| Patch common | 72 (0x48) | 74 | `clock_source`, `patch_category` |
| Performance common | 64 (0x40) | 66 | `keyboard_mode`, `clock_source` |
| Performance part | 19 (0x13) | 25 | octave shift, local, transmit switches, transmit bank select group, transmit volume |

The unit answers only a block's own address and size (1010 rule; `[guess]` the same on the 1080), so every read, write, backup plan, parse and validation needs per-model sizes. Writing a 1010-sized patch common to a 1080 would be wrong.

### 2. Device ID is a setting

`Dev = unit number - 1`, unit numbers 17-32 (device ID 0x10-0x1F). The default (17) is 0x10, the value we hardcode. A 1080 mode needs a device ID setting. The unit also has a **Receive System Exclusive ("Rx.Exc") switch** that must be ON.

### 3. No Identity Reply

The manual does not mention one (the unit predates it), so Detect cannot rely on the Identity Request. It would have to use the one read-only RQ1 of the temporary patch's common block (its name) on the chosen device ID: harmless, but it sends into possible silence, which AGENTS.md's Detect rule forbids, so that rule needs a documented exception. The 1080 manual mentions a GM System On message (p.77). The Universal Master Volume and GM System Off messages were NOT checked for the 1080.

### 4. Parameters the 1010 ignores are real on the 1080

System Receive Control Change / Modulation / Volume / Hold-1 / Bender / Aftertouch switches (0x16-0x1B) and Rhythm Edit Source (0x1E) are at the same offsets we flag `jv1080_only`. A 1080 mode would show them. Choices flagged `jv1010: false` (patch group type PCM, CARD in the performance number list) matter too.

### 5. Memory and media

- Banks `[manual, Bank Select table]`: User 80/0; **Preset A, B, C = 81/0, 81/1, 81/2; Preset D (General MIDI) = 81/3** (the 1010 has A-E); **Data Card 82**; **PCM Card 83**; **Expansion A-D = 84/0-7** (each board is two LSBs of 128). Rhythm sets use the same MSBs (User 2, each Preset 2, Card 2...).
- **Data Card areas** `[manual p.150]`: performances `20 00..1F 00`, rhythm sets `20 40/41`, patches `21 00..7F` (backed up and restored the way USER is, if wanted).
- No built-in Session board (the 1010's XP-A), no INT-B, **no patch categories** (so no category browsing on a 1080).
- Wave groups: INT, PCM card and EXP boards. The manual's wave list covers "Internal A" only; wave names for PCM cards and expansion boards would be unknown ("no name known"), as for any board we cannot name today.

### 6. Data tables would have to be re-extracted

The manual has the USER and Preset A-C patch lists, the performance lists, the rhythm set list and the Internal A wave list, but the OCR text is badly mangled ("Svniphonique", "Ac Pianol A"). It needs a better OCR pass or hand cleanup before a `tools/extract_params.py`-style import (with a count check like the 1010's). `[guess]` the Internal A waves equal the 1010's INT-A; not compared.

## What a "model profile" would carry

Device ID (and its setting), per-block sizes (a table truncated per model), which parameters and choices exist, bank/group tables, the patch / performance / rhythm / wave lists, categories on/off, the memory plan for backup and restore, the detection method, and the Data Card areas.

Touch points (everything that assumes one model today): `core/params.py` / `parameters.json` (sizes, hidden flags), `patch.py`, `performance.py`, `rhythm.py`, `system.py`, `memory.py` (plan), `backup.py`, `unit.py` (device ID), `midi_diagnostics.py` (detect), `validate.py`, `stock.py`, `patch_groups.py` / `audition.py` (banks), `groups.py` and `friendly.py` (which cards and options), `core/simulated_unit.py` and `tests/fakes.py` (a 1080 profile so tests can cover it), the Settings dialog (model and device ID).

## Risks without a unit

Only the manual and a simulation can check it. Unknown on a real 1080 `[guess]`: whether a 1010-sized request is refused; whether it takes a 129-byte tone in one packet and the 20 ms spacing (the 1080 manual does not state the 1010's <= 128-byte, >= 20 ms rule); what Rx.Exc OFF looks like (silence); the universal messages. The app's own writes are still unproven on the 1010, so the recommendation is: **read-only and flagged experimental first**, then find a JV-1080 owner to run `dev_docs/hardware-test-plan.md` before any write path is enabled.

## Suggested order

1. A `ModelProfile` with the JV-1010 as the only profile (no behaviour change; tests stay green).
2. A JV-1080 profile: sizes, device ID setting, detection by RQ1, hidden/shown parameters, banks. A 1080 `SimulatedUnit`.
3. Read paths and backup (read-only), checked against the simulation.
4. Data lists (after a good OCR) and the Data Card areas.
5. Writes, after a 1080 owner has run the hardware test plan.
