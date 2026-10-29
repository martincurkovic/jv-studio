# Third-party notices

JV Studio is released under the GNU General Public License, version 3 or later (see the LICENSE file). It includes, or was helped by, the following.

## ChiKareGo2 (the Macintosh System 6 theme's font)

The "Macintosh System 6" theme (Settings > Appearance) draws its text in **ChiKareGo2** by Giles Booth, a recreation of the Chicago 12 bitmap
font, released under the Creative Commons Attribution licence (CC BY). It was obtained as a `.woff` from
[system.css](https://github.com/sakofchit/system.css) and converted to `.ttf` by `tools/fetch_system6_font.py`; the file is
`src/jv_studio/ui/fonts/ChiKareGo2.ttf`. The theme is a homage and is not affiliated with Apple: Chicago itself is Apple's and is not shipped.

## system.css

[system.css](https://github.com/sakofchit/system.css) (MIT) inspired the theme and is where the font above came from. None of its CSS is used: Qt
style sheets are a different, smaller language, and the theme's rules are written from scratch.

## AKAISDS

The knob, envelope graph, section card, stylesheet and theme code, the Settings dialog's shape and the update checker are adapted from
[AKAISDS](https://github.com/martincurkovic/AKAISDS), by the same author and also released under the GNU General Public License, version 3 or later,
so no further notice text is needed here.

## jv1010tool

Protocol details were cross-checked against Lars Ahlzen's MIT-licensed [jv1010tool](https://github.com/Ahlzen/jv1010tool). No code was copied.

## Waveform names

The names of the JV-1010's waveforms (`src/jv_studio/data/waves.json`) come from the waveform lists on
[GumiElectronic](https://gumielectronic.net/?p=2312), a third-party compilation of facts about the unit. The group table is from Roland's Owner's
Manual.

## Roland

The parameter table is generated from Roland's JV-1010 Owner's Manual. Roland and JV-1010 are trademarks of Roland Corporation. This project is not
affiliated with Roland, and the Owner's Manual itself is not part of this repository.
