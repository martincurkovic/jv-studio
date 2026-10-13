# JV Studio

A free, open-source **editor and librarian for the Roland JV-1010** sound module, in the spirit of [AKAISDS](https://github.com/martincurkovic/AKAISDS).
Built with PySide6 (Qt) and python-rtmidi. GPL-3.0-or-later.

> **Status: early development.** You can read the unit's patches, edit any patch parameter on knobs and draggable envelope graphs (heard live on the unit's temporary patch, with undo), write to USER
> slots, edit performances (16 parts, effects, the patch each part plays), open and save `.syx` files, and back up and restore the whole unit. It has been tried on one JV-1010 (its author's); the performance editor has not been tried on a unit yet. **Back the unit up before
> writing to it** (File > Back Up Unit). The rhythm setups and a fuller librarian are still to come: see [`dev_docs/roadmap.md`](dev_docs/roadmap.md).

## Goals

- Edit the JV-1010's patches visually: knobs, draggable envelope graphs, every parameter in the manual's MIDI Implementation.
- Read and write the 128 user patches, load and save `.syx` files, and back up / restore the whole unit.
- Be careful with the hardware: edits go to the temporary patch first, every USER write saves the old patch to a file first, and nothing is written without a read-back.

## Download & Installation

Builds for each release are on the [Releases](https://github.com/martincurkovic/jv-studio/releases) page. You need a MIDI interface cabled to the JV-1010 (MIDI OUT of the interface to the unit's MIDI IN, and back); Settings > Troubleshooting has a hardware test and cabling diagrams.

**macOS** (14 or newer, Apple Silicon or Intel): open the `.dmg` and drag JV-Studio to Applications. Or install with [Homebrew](https://brew.sh): `brew install --cask martincurkovic/tap/jv-studio`. The app is not code-signed or notarized, so Gatekeeper blocks it the first time: open System Settings > Privacy & Security and click "Open Anyway", or run `xattr -dr com.apple.quarantine /Applications/JV-Studio.app`.

**Windows**: run `JV-Studio-Setup.exe`. **Linux**: unzip `JV-Studio-linux.zip` and run the `.AppImage` (it needs ALSA, which every desktop distribution has).

To build it yourself, see [`BUILDING.md`](BUILDING.md).

## Running it

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
uv sync
uv run jv-studio      # the app: pick your MIDI ports in Settings, then Settings > Troubleshooting
uv run pytest            # the tests
```

## The parameter table

`src/jv_studio/data/parameters.json` is generated from the JV-1010 Owner's Manual by `tools/extract_params.py` (needs `pdftotext` from
poppler). The manual is Roland's and is not in this repository; put your copy at `manual/JV-1010_OM.pdf` (git-ignored) to regenerate.

## Credits and notes

- Protocol details were cross-checked against Lars Ahlzen's MIT-licensed [jv1010tool](https://github.com/Ahlzen/jv1010tool); no code was copied.
- Wave names come from the waveform lists on [GumiElectronic](https://gumielectronic.net/?p=2312); the group table they hang on is from Roland's Owner's Manual.
- The knob and envelope-graph widgets are adapted from [AKAISDS](https://github.com/martincurkovic/AKAISDS) (same author, GPL-3.0).
- Roland and JV-1010 are trademarks of Roland Corporation. This project is not affiliated with or endorsed by Roland.
