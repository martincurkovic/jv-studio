"""Which card a parameter sits on in the patch editor (Qt-free). Rules by key prefix; the first match wins, and every shown parameter must match one
(`tests/test_groups.py`), so a new parameter in the table can't silently disappear from the editor."""

from . import params, patch

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

RULES = {patch.COMMON: _COMMON, patch.TONE: _TONE}

#: parameters the editor does not show as controls: a tone's wave is chosen BY NAME (the Wave card's Choose... button sets all three together), and the raw numbers stay
#: visible in the Raw Values tab and in the wave label when the group is not one we have names for
HIDDEN = {(patch.TONE, "wave_group_type"), (patch.TONE, "wave_group_id"), (patch.TONE, "wave_number")}
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
        if not param.jv1080_only and (block_key, param.key) not in HIDDEN:
            found[group_for(block_key, param.key)].append(param)
    return [(title, found[title]) for title in order + [OTHER] if found[title]]
