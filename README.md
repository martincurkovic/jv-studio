# JV Studio

[![Build](https://github.com/martincurkovic/jv-studio/actions/workflows/build.yml/badge.svg)](https://github.com/martincurkovic/jv-studio/actions/workflows/build.yml)
[![Tests](https://github.com/martincurkovic/jv-studio/actions/workflows/test.yml/badge.svg)](https://github.com/martincurkovic/jv-studio/actions/workflows/test.yml)
[![Downloads](https://img.shields.io/github/downloads/martincurkovic/jv-studio/total?label=downloads)](https://github.com/martincurkovic/AKAISDS/releases)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Qt 6.12 LTS](https://img.shields.io/badge/Qt-6.12%20LTS-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Platforms: macOS, Windows, Linux](https://img.shields.io/badge/platforms-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#download--installation)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

A free, open-source **editor and librarian for the Roland JV-1010** sound module.
Built with PySide6 (Qt) and python-rtmidi. GPL-3.0-or-later.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/patch-editor-dark.png">
    <img alt="JV Studio editing a patch: the USER patch list, the tone's filter with a draggable envelope, and knobs for every parameter" src="docs/screenshots/patch-editor-light.png" width="860">
  </picture>
</p>
<p align="center"><b>Three themes</b>: light mode, dark mode, or the Macintosh System 6 look.</p>
<table align="center">
  <tr>
    <td align="center"><img alt="JV Studio in the dark theme" src="src/jv_studio/ui/help/screenshots/main-window-dark.png" width="280"><br><sub>Dark</sub></td>
    <td align="center"><img alt="JV Studio in the light theme" src="src/jv_studio/ui/help/screenshots/main-window-light.png" width="280"><br><sub>Light</sub></td>
    <td align="center"><img alt="JV Studio in the Macintosh System 6 theme: black and white, a bitmap-style font, striped title bars, with a little colour only for states" src="src/jv_studio/ui/help/screenshots/main-window-system6.png" width="280"><br><sub>System 6</sub></td>
  </tr>
</table>

<p align="center"><b>What it edits</b></p>
<table align="center">
  <tr>
    <td align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/performance-dark.png"><img alt="The performance editor: the 16 parts as a mixer, each with its patch chosen by name" src="docs/screenshots/performance-light.png" width="420"></picture><br><sub>Performances</sub></td>
    <td align="center"><img alt="The rhythm set editor: a keyboard of drum keys and the chosen key's wave, filter and envelopes" src="src/jv_studio/ui/help/screenshots/rhythm-set.png" width="420"><br><sub>Rhythm sets</sub></td>
  </tr>
  <tr>
    <td align="center"><img alt="The audition keyboard along the bottom of the window, playing the unit and choosing its patches" src="src/jv_studio/ui/help/screenshots/audition-keyboard.png" width="420"><br><sub>Audition keyboard</sub></td>
    <td align="center"><img alt="System Settings: the unit's global settings, tuning and MIDI receive options" src="src/jv_studio/ui/help/screenshots/system-settings.png" width="420"><br><sub>System settings</sub></td>
  </tr>
</table>

> **Status: early development.**  **Back the unit up before
> writing to it** (File > Back Up Unit).
>
> **Hardware > Update Firmware... is unverified.** It checks Roland's System Update files and plays them to a unit in update mode the way a sequencer would, but it has never been tried on a real JV-1010, the unit sends no
> reply that could confirm it worked, and an interrupted or corrupted update may leave a unit unable to start. Use it at your own risk, and back the unit up first.

## Download & Installation

Builds for each release are on the [Releases](https://github.com/martincurkovic/jv-studio/releases) page. You need a MIDI interface cabled to the JV-1010 (MIDI OUT of the interface to the unit's MIDI IN, and back). Settings > Troubleshooting has a hardware test and cabling diagrams.

**macOS** (14 or newer, Apple Silicon or Intel): open the `.dmg` and drag JV-Studio to Applications. Or install with [Homebrew](https://brew.sh): `brew install --cask martincurkovic/tap/jv-studio`. The app is not code-signed or notarized, so Gatekeeper blocks it the first time: open System Settings > Privacy & Security and click "Open Anyway", or run `xattr -dr com.apple.quarantine /Applications/JV-Studio.app`.

**Windows**: run `JV-Studio-Setup.exe`. **Linux**: unzip `JV-Studio-linux.zip` and run the `.AppImage` (it needs ALSA, which basically every desktop distribution should have).

To build it yourself, see [`BUILDING.md`](BUILDING.md).

## User guide

See the [Quick Start Guide](src/jv_studio/ui/help/quickstart.md): MIDI setup, backing up, editing patches, performances and rhythm sets, the audition keyboard and System settings. The same guide is in the app under **Help > Quick Start Guide**.

## Credits and notes

- Protocol details were cross-checked against Lars Ahlzen's MIT-licensed [jv1010tool](https://github.com/Ahlzen/jv1010tool); no code was copied.
- Wave names come from the waveform lists on [GumiElectronic](https://gumielectronic.net/?p=2312); the group table is from Roland's Owner's Manual.
- The knob and envelope-graph widgets are adapted from [AKAISDS](https://github.com/martincurkovic/AKAISDS) (GPL-3.0).
- Roland and JV-1010 are trademarks of Roland Corporation. This project is not affiliated with or endorsed by Roland.
