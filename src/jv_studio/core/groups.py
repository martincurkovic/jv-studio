"""Which card a parameter sits on in the patch editor (Qt-free). Rules by key prefix; the first match wins, and every shown parameter must match one
(`tests/test_groups.py`), so a new parameter in the table can't silently disappear from the editor."""

from . import params, patch, performance, system

_COMMON = [
    ("Patch", ("patch_name", "patch_category", "patch_level", "patch_pan", "analog_feel", "patch_tempo", "clock_source", "octave_shift", "stretch_tune_depth", "voice_priority")),
    ("Play", ("bend_range_", "key_assign_mode", "solo_legato", "portamento_", "velocity_range_switch")),
    ("Structure", ("structure_type_", "booster_")),
    ("Controllers", ("patch_control_source_", "efx_control_hold_peak", "control_")),
    ("EFX", ("efx_",)),
    ("Chorus", ("chorus_",)),
    ("Reverb & Delay", ("reverb_", "delay_")),
]

_TONE = [
    ("Wave", ("tone_switch", "wave_", "fxm_", "tone_delay_")),
    ("Ranges", ("velocity_cross_fade", "velocity_range_", "keyboard_range_")),
    ("Controllers", ("redamper_", "volume_control", "hold_1_", "pitch_bend_control", "pan_control", "controller_")),
    ("LFO 1", ("lfo1_",)),
    ("LFO 2", ("lfo2_",)),
    ("Pitch", ("coarse_tune", "fine_tune", "random_pitch_depth", "pitch_")),
    ("Filter", ("filter_", "cutoff_", "resonance")),
    ("Level", ("tone_level", "bias_", "level_")),
    ("Pan", ("tone_pan", "pan_", "random_pan_depth", "alternate_pan_depth")),
    ("Output", ("output_assign", "mix_efx_send_level", "chorus_send_level", "reverb_send_level")),
]

_PERFORMANCE_COMMON = [
    ("Performance", ("performance_name", "performance_tempo", "clock_source", "keyboard_mode", "keyboard_range_switch")),
    ("Voice Reserve", ("voice_reserve_",)),
    ("EFX", ("efx_",)),
    ("Chorus", ("chorus_",)),
    ("Reverb & Delay", ("reverb_", "delay_")),
]

_PERFORMANCE_PART = [
    ("Part", ("receive_", "midi_channel")),
    ("Mix", ("part_", "output_assign", "mix_efx_send_level", "chorus_send_level", "reverb_send_level")),
    ("Keyboard", ("keyboard_range_",)),
]

_SYSTEM = [
    ("Sound", ("sound_mode", "patch_remain")),
    ("Tuning & Clock", ("master_tune", "scale_tune_switch", "clock_source", "system_tempo")),
    ("Effects", ("efx_switch", "chorus_switch", "reverb_switch")),
    ("MIDI Receive", ("receive_", "control_channel", "patch_receive_channel", "aftertouch_source", "volume_control_source")),
    ("Controllers", ("tap_control_source", "hold_control_source", "peak_control_source", "system_control_source_")),
    ("Preview", ("preview_",)),
]

RULES = {
    patch.COMMON: _COMMON,
    patch.TONE: _TONE,
    performance.COMMON: _PERFORMANCE_COMMON,
    performance.PART: _PERFORMANCE_PART,
    system.COMMON: _SYSTEM,
}

#: parameters the editor does not show as controls: a tone's wave is chosen BY NAME (the Wave card's Choose... button sets all three together), and the raw numbers stay
#: visible in the Raw Values tab and in the wave label when the group is not one we have names for
HIDDEN = {
    (patch.TONE, "wave_group_type"),
    (patch.TONE, "wave_group_id"),
    (patch.TONE, "wave_number"),
    # a part's patch is chosen BY NAME too (the part's Choose... button sets all three together)
    (performance.PART, "patch_group_type"),
    (performance.PART, "patch_group_id"),
    (performance.PART, "patch_number"),
    # the MIDI transmit settings follow the JV-1080-family-only ones (<Local Switch>, <Transmit Switch>) in the manual; the JV-1010 has no keyboard to transmit from
    (performance.PART, "transmit_bank_select_group"),
    (performance.PART, "transmit_volume"),
    # what the unit has selected right now (mode, patch, performance) is shown as one line of text, not as controls: choosing a patch or a performance is what the unit's own
    # dials, a Program Change (the audition bar) or a performance part do
    (system.COMMON, "performance_number"),
    (system.COMMON, "patch_group_type"),
    (system.COMMON, "patch_group_id"),
    (system.COMMON, "patch_number"),
    (system.COMMON, "arpeggio_octave_range"),
}

#: parameters that are shown nowhere AND not checked against their range: the JV-1010 has no arpeggiator, and this is the one Arpeggio parameter the manual forgot to put in
#: angle brackets [guess]
UNUSED = {(system.COMMON, "arpeggio_octave_range")}


def supported(param):
    """False for a parameter the JV-1010 doesn't have: the manual marks it with <> (a JV-1080-family value the unit ignores), either on the whole parameter or on EVERY one of its choices."""
    if param.jv1080_only:
        return False
    return not (param.choices and not any(c.jv1010 for c in param.choices))
OTHER = "Other"


def group_for(block_key, param_key):
    for title, prefixes in RULES[block_key]:
        if any(param_key.startswith(p) for p in prefixes):
            return title
    return OTHER


def groups(block_key):
    """[(card title, [Param])] for a patch block, in the editor's order. JV-1080-only parameters (the JV-1010 ignores them) are left out."""
    table = params.load_table().block(block_key)
    order = [title for title, _ in RULES[block_key]]
    found = {title: [] for title in order}
    found[OTHER] = []
    for param in table.param_list():
        if supported(param) and (block_key, param.key) not in HIDDEN:
            found[group_for(block_key, param.key)].append(param)
    return [(title, found[title]) for title in order + [OTHER] if found[title]]
