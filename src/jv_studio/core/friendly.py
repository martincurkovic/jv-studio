"""Readable names for the options of a drop-down (Qt-free).

The parameter table keeps the manual's labels, which are what the unit's own display shows (`TRI`, `HALL1`, `PCH`): the Raw Values tab and the log use them, and a combo's
tooltip says what the unit calls an option. The drop-downs show these friendlier names instead (Triangle, Hall 1, Pitch). A label with no entry here falls back to
`fallback()` (an all-caps word becomes Title Case), so a new table entry never shows up broken; `tests/test_friendly.py` checks every shown list has an entry for every
option and that no two options of one list end up with the same name.
"""

import re

_ON_OFF = {"OFF": "Off", "ON": "On"}

_CONTROL_SOURCES = {
    "SYS-CTRL1": "System Control 1",
    "SYS-CTRL2": "System Control 2",
    "MODULATION": "Modulation",
    "BREATH": "Breath",
    "FOOT": "Foot",
    "VOLUME": "Volume",
    "PAN": "Pan",
    "EXPRESSION": "Expression",
    "PITCH BEND": "Pitch Bend",
    "AFTERTOUCH": "Aftertouch",
    "LFO1": "LFO 1",
    "LFO2": "LFO 2",
    "VELOCITY": "Velocity",
    "KEYFOLLOW": "Key Follow",
    "PLAYMATE": "Playmate",
}

_CATEGORY = {
    "NO ASSIGN": "No Assign",
    "AC.PIANO": "Acoustic Piano",
    "EL.PIANO": "Electric Piano",
    "KEYBOARDS": "Keyboards",
    "AC.GUITAR": "Acoustic Guitar",
    "EL.GUITAR": "Electric Guitar",
    "DIST.GUITAR": "Distortion Guitar",
    "AC.BRASS": "Acoustic Brass",
    "HIT&STAB": "Hit & Stab",
    "BEAT&GROOVE": "Beat & Groove",
    "SOUND FX": "Sound FX",
    "SYNTH FX": "Synth FX",
}

_EFX_TYPES = {
    "STEREO-EQ": "Stereo EQ",
    "AUTO-WAH": "Auto-Wah",
    "SPACE-D": "Space-D",
    "2VOICE-PITCH-SHIFTER": "2-Voice Pitch Shifter",
    "FBK-PITCH-SHIFTER": "Feedback Pitch Shifter",
}

_DESTINATIONS = {
    "PCH": "Pitch",
    "CUT": "Cutoff",
    "RES": "Resonance",
    "LEV": "Level",
    "PAN": "Pan",
    "MIX": "Mix Send",
    "CHO": "Chorus Send",
    "REV": "Reverb Send",
    "PL1": "Pitch LFO 1 Depth",
    "PL2": "Pitch LFO 2 Depth",
    "FL1": "Filter LFO 1 Depth",
    "FL2": "Filter LFO 2 Depth",
    "AL1": "Level LFO 1 Depth",
    "AL2": "Level LFO 2 Depth",
    "pL1": "Pan LFO 1 Depth",
    "pL2": "Pan LFO 2 Depth",
    "L1R": "LFO 1 Rate",
    "L2R": "LFO 2 Rate",
}

#: the ten structure types: how the two tones of a pair (1 & 2, 3 & 4) are connected. Names and descriptions are from Roland's JV-1080 Software Synthesizer Owner's
#: Manual ("Structure", the same engine as the JV-1010; the JV-1010 Owner's Manual does not describe them), put in our own words.
_STRUCTURE = {
    "TYPE 01": ("01 Independent", "The two tones are completely independent: each has its own filter and amplifier."),
    "TYPE 02": ("02 Stacked Filters", "Tone 1 feeds on into Tone 2's filter, so its sound passes through both filters. Tone 1's amplifier sets the balance between the tones."),
    "TYPE 03": ("03 Mix → Filter → Booster", "The two tones are mixed, filtered, and then driven through the booster to distort the waveform."),
    "TYPE 04": ("04 Booster → Filters", "The booster distorts the signal first, then both filters are applied. Tone 1's amplifier sets the balance and the booster level."),
    "TYPE 05": ("05 Ring Mod → Filters", "A ring modulator combines the two tones into new overtones, then both filters are applied. Tone 1's amplifier sets the ring modulation depth."),
    "TYPE 06": ("06 Ring Mod + Tone 2 → Filters", "As type 05, with Tone 2's own sound mixed in as well. Tone 1's amplifier sets how much of the ring-modulated sound is heard."),
    "TYPE 07": ("07 Filter → Ring Mod", "Tone 1 is filtered and then ring-modulated with Tone 2."),
    "TYPE 08": ("08 Filter → Ring Mod + Tone 2", "The filtered Tone 1 and Tone 2 go through the ring modulator, Tone 2 is mixed back in, and the result is filtered."),
    "TYPE 09": ("09 Filters → Ring Mod", "Each tone is filtered, then both go through the ring modulator. Tone 1's amplifier sets the balance and the ring modulation depth."),
    "TYPE 10": ("10 Filters → Ring Mod + Tone 2", "As type 09, with Tone 2's sound mixed in as well. Tone 1's amplifier sets how much of the ring-modulated sound is heard."),
}

_HF_DAMP = {"1000": "1 kHz", "1250": "1.25 kHz", "1600": "1.6 kHz", "2000": "2 kHz", "2500": "2.5 kHz", "3150": "3.15 kHz", "4000": "4 kHz", "5000": "5 kHz", "6300": "6.3 kHz", "8000": "8 kHz"}

#: parameter key -> {the manual's label: the readable one}. A key not listed uses only the shared words (Off, On) and `fallback`.
BY_KEY = {
    "patch_category": _CATEGORY,
    "booster_1and2": {"0": "0 dB", "+6": "+6 dB", "+12": "+12 dB", "+18": "+18 dB"},
    "booster_3and4": {"0": "0 dB", "+6": "+6 dB", "+12": "+12 dB", "+18": "+18 dB"},
    "patch_control_source_2": _CONTROL_SOURCES,
    "patch_control_source_3": _CONTROL_SOURCES,
    "efx_control_source_1": _CONTROL_SOURCES,
    "efx_control_source_2": _CONTROL_SOURCES,
    "chorus_output": {"MIX": "Mix", "REV": "Reverb", "MIX+REV": "Mix + Reverb"},
    "reverb_type": {"ROOM1": "Room 1", "ROOM2": "Room 2", "STAGE1": "Stage 1", "STAGE2": "Stage 2", "HALL1": "Hall 1", "HALL2": "Hall 2", "DELAY": "Delay", "PAN-DLY": "Pan Delay"},
    "reverb_hf_damp": {**{n: f"{n} Hz" for n in ("200", "250", "315", "400", "500", "630", "800")}, **_HF_DAMP, "BYPASS": "Bypass"},
    "wave_gain": {"-6": "-6 dB", "0": "0 dB", "+6": "+6 dB", "+12": "+12 dB"},
    "tone_delay_mode": {"CLOCK-SYNC": "Clock Sync", "TAP-SYNC": "Tap Sync", "KEY-OFF-N": "Key-Off Normal", "KEY-OFF-D": "Key-Off Decay", "TEMPO-SYNC": "Tempo Sync"},
    "pan_control_switch": {"KEY-ON": "Key-On"},
    "filter_type": {"LPF": "Low-Pass", "BPF": "Band-Pass", "HPF": "High-Pass", "PKG": "Peaking"},
    "bias_direction": {"LOWER&UPPER": "Lower & Upper"},
    "output_assign": {"EFX": "Effect"},
    "efx_output_assign": {},
    "efx_source": {"PERFORM": "Performance"},
    "structure_type_1and2": {k: v[0] for k, v in _STRUCTURE.items()},
    "structure_type_3and4": {k: v[0] for k, v in _STRUCTURE.items()},
}
BY_KEY["sound_mode"] = {"PERFORMANCE": "Performance", "PATCH": "Patch", "GM": "General MIDI"}
BY_KEY["clock_source"] = {"INT": "Internal", "MIDI": "MIDI"}
BY_KEY["volume_control_source"] = {"VOLUME": "Volume", "VOLUME&EXPRESSION": "Volume & Expression"}
BY_KEY["aftertouch_source"] = {"CHANNEL": "Channel", "POLY": "Polyphonic", "CH&POLY": "Channel & Polyphonic"}
for _key in ("tap_control_source", "hold_control_source", "peak_control_source"):
    BY_KEY[_key] = {"HOLD-1": "Hold-1", "HOLD-2": "Hold-2"}
for _n in (1, 2, 3):
    for _m in (1, 2, 3, 4):
        BY_KEY[f"controller_{_n}_destination_{_m}"] = _DESTINATIONS
for _n in (1, 2):
    BY_KEY[f"lfo{_n}_waveform"] = {"TRI": "Triangle", "SIN": "Sine", "SAW": "Saw", "SQR": "Square", "TRP": "Trapezoid", "S&H": "Sample & Hold", "RND": "Random", "CHS": "Chaos"}
    BY_KEY[f"lfo{_n}_fade_mode"] = {"KEY-ON-IN": "Key-On In", "KEY-ON-OUT": "Key-On Out", "KEY-OFF-IN": "Key-Off In", "KEY-OFF-OUT": "Key-Off Out"}


def fallback(label):
    """An all-caps label becomes Title Case ("LAST" -> "Last", "NO ASSIGN" -> "No Assign"); anything else (numbers, mixed case) is left as it is."""
    if label.isupper() and re.search("[A-Z]", label):
        return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), label)
    return label


def _efx_type(text):
    """"OVERDRIVE→CHORUS (serial)" -> "Overdrive → Chorus (serial)", "CHORUS/DELAY (parallel)" -> "Chorus / Delay (parallel)", "HEXA-CHORUS" -> "Hexa Chorus"."""
    if text in _EFX_TYPES:
        return _EFX_TYPES[text]
    suffix = ""
    if m := re.search(r"\s*\((serial|parallel)\)$", text):
        suffix, text = f" ({m[1]})", text[: m.start()]
    if "→" in text:
        return " → ".join(_efx_word(part) for part in text.split("→")) + suffix
    if "/" in text:
        return " / ".join(_efx_word(part) for part in text.split("/")) + suffix
    return _efx_word(text) + suffix


def _efx_word(text):
    return _EFX_TYPES.get(text, fallback(text.replace("-", " ")))


def description(key, text):
    """A sentence explaining option `text` of parameter `key` (the structure types), or None."""
    if key in ("structure_type_1and2", "structure_type_3and4"):
        return _STRUCTURE.get(text, (None, None))[1]
    return None


def label(key, text):
    """The readable name of option `text` of parameter `key`."""
    if key == "efx_type":
        return _efx_type(text)
    return BY_KEY.get(key, {}).get(text) or _ON_OFF.get(text) or fallback(text)
