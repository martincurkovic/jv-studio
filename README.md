# JV Studio

A free, open-source patch editor for the **Roland JV-1010** sound module, in the spirit of [AKAISDS](https://github.com/martincurkovic/AKAISDS).
Built with PySide6 (Qt) and python-rtmidi. GPL-3.0-or-later.

> **Status: early development.** The sysex layer, the parameter table, the patch model and the app shell (theme, Settings, hardware and MIDI-interface
> tests) exist and are tested against fake ports. The patch editor itself is next. Nothing here has been tried on a real JV-1010 yet.
> See [`dev_docs/roadmap.md`](dev_docs/roadmap.md).

## Goals

- Edit the JV-1010's patches visually: knobs, draggable envelope graphs, every parameter in the manual's MIDI Implementation.
- Read and write the 128 user patches, load and save `.syx` files, and back up / restore the whole unit.
- Be careful with the hardware: edits go to the temporary patch first, every USER write saves the old patch to a file first, and nothing is written without a read-back.

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
- Roland and JV-1010 are trademarks of Roland Corporation. This project is not affiliated with or endorsed by Roland.
