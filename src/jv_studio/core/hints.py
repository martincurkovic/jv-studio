"""One-sentence explanations of patch parameters, for tooltips (Qt-free).

NOT from the Owner's Manual (its MIDI chapter lists ranges, not meanings) and NOT measured on a unit: they are general knowledge of how a JV-series
synthesizer works. Where one is wrong or too vague, correct it here. `tests/test_hints.py` checks every key exists in the parameter table.
"""

import re

COMMON = {
    "patch_name": "The patch's name: up to 12 characters.",
    "patch_category": "The category the unit files this patch under when you browse by category.",
    "patch_level": "Overall level of the patch.",
    "patch_pan": "Overall pan of the patch, from hard left to hard right.",
    "analog_feel": "Adds a small random instability to the pitch, like the oscillators of an analog synthesizer.",
    "patch_tempo": "The patch's tempo, used by tempo-synced effects and LFOs when the clock source is PATCH.",
    "clock_source": "Whether tempo-synced items follow this patch's tempo (PATCH) or the unit's system tempo (SYSTEM).",
    "octave_shift": "Shifts the whole patch up or down in octaves.",
    "stretch_tune_depth": "Stretches the tuning like an acoustic piano: low notes a little flat, high notes a little sharp. OFF is equal temperament.",
    "voice_priority": "Which notes are kept when the unit runs out of voices: the newest (LAST) or the loudest.",
    "bend_range_up": "How far the pitch bend lever raises the pitch, in semitones.",
    "bend_range_down": "How far the pitch bend lever lowers the pitch, in semitones.",
    "key_assign_mode": "POLY plays chords; SOLO plays one note at a time.",
    "solo_legato": "In SOLO mode, notes played legato do not retrigger the envelopes.",
    "portamento_switch": "Turns portamento (a glide between notes) on or off.",
    "portamento_mode": "NORMAL glides on every note; LEGATO only when notes overlap.",
    "portamento_type": "RATE: the glide speed is fixed. TIME: the glide always takes the same time.",
    "portamento_start": "Where the glide begins: from the current PITCH, or from the previous NOTE.",
    "portamento_time": "How long the glide takes (or how fast it is, depending on the type).",
    "velocity_range_switch": "When on, each tone only plays within its own velocity range.",
    "structure_type_1and2": "How tones 1 and 2 are connected: independent, stacked filters, a booster or a ring modulator. If one tone is off or out of range, the other plays as type 01.",
    "structure_type_3and4": "How tones 3 and 4 are connected: independent, stacked filters, a booster or a ring modulator. If one tone is off or out of range, the other plays as type 01.",
    "booster_1and2": "How hard the booster distorts tones 1 and 2. Only used by structure types 03 and 04.",
    "booster_3and4": "How hard the booster distorts tones 3 and 4. Only used by structure types 03 and 04.",
    "efx_type": "The effect inserted on this patch (40 types). Its parameters are the knobs below.",
    "efx_output_assign": "Where the effect's output goes. MIX is the normal stereo mix.",
    "efx_mix_out_send_level": "How much of the effect goes to the main mix.",
    "efx_chorus_send_level": "How much of the effect output is also sent to the chorus.",
    "efx_reverb_send_level": "How much of the effect output is also sent to the reverb.",
    "efx_control_source_1": "The controller that changes one of the effect's parameters in real time.",
    "efx_control_depth_1": "How strongly the controller changes that parameter.",
    "efx_control_source_2": "A second controller that changes an effect parameter in real time.",
    "efx_control_depth_2": "How strongly the second controller changes it.",
    "chorus_level": "Level of the chorus effect.",
    "chorus_rate": "Speed of the chorus's modulation.",
    "chorus_depth": "Depth of the chorus's modulation.",
    "chorus_pre_delay": "Delay before the chorus sound, which widens or thickens it.",
    "chorus_feedback": "How much of the chorus output is fed back into its input.",
    "chorus_output": "Where the chorus goes: the MIX, the reverb (REV) or both.",
    "reverb_type": "The kind of reverb: rooms, halls, gate reverb and delays.",
    "reverb_level": "Level of the reverb.",
    "reverb_time": "How long the reverb lasts.",
    "reverb_hf_damp": "How quickly the reverb's high frequencies die away: lower values keep it brighter.",
    "delay_feedback": "How many repeats the delay makes (the reverb type's delay modes).",
    "patch_control_source_2": "The MIDI controller that acts as Controller 2 for this patch's tones.",
    "patch_control_source_3": "The MIDI controller that acts as Controller 3 for this patch's tones.",
}

TONE = {
    "tone_switch": "Turns this tone on or off.",
    "wave_gain": "Boosts the level of the wave: -6, 0, +6 or +12 dB.",
    "fxm_switch": "FXM (frequency cross modulation) adds a harsher, more metallic harmonic character.",
    "fxm_color": "The character of the FXM modulation.",
    "fxm_depth": "How strongly FXM modulates the tone.",
    "tone_delay_mode": "How the start of the tone is delayed (or held back) after the key is pressed.",
    "tone_delay_time": "How long the start of the tone is delayed.",
    "velocity_cross_fade": "Fades smoothly between tones whose velocity ranges meet, instead of switching.",
    "velocity_range_lower": "The softest key velocity this tone plays at (when Velocity Range Switch is on).",
    "velocity_range_upper": "The hardest key velocity this tone plays at (when Velocity Range Switch is on).",
    "keyboard_range_lower": "The lowest key this tone plays.",
    "keyboard_range_upper": "The highest key this tone plays.",
    "volume_control_switch": "Whether this tone follows MIDI Volume (CC 7).",
    "hold_1_control_switch": "Whether this tone follows the sustain pedal (Hold-1, CC 64).",
    "pitch_bend_control_switch": "Whether this tone follows the pitch bend lever.",
    "pan_control_switch": "Whether this tone follows MIDI Pan (CC 10): continuously, or only when a key is pressed.",
    "lfo1_waveform": "The shape of LFO 1: triangle, sine, saw, square, trapezoid, sample and hold, random or chaos.",
    "lfo1_key_sync": "When on, LFO 1 restarts at each key press.",
    "lfo1_rate": "The speed of LFO 1.",
    "lfo1_offset": "Raises or lowers LFO 1's wave so it swings more one way than the other.",
    "lfo1_delay_time": "How long after the key press LFO 1 starts.",
    "lfo1_fade_mode": "Whether LFO 1 fades in or out, and whether the fade starts at key-on or key-off.",
    "lfo1_fade_time": "How long LFO 1's fade takes.",
    "lfo1_external_sync": "Locks LFO 1 to an external clock or tapped tempo.",
    "lfo2_waveform": "The shape of LFO 2: triangle, sine, saw, square, trapezoid, sample and hold, random or chaos.",
    "lfo2_key_sync": "When on, LFO 2 restarts at each key press.",
    "lfo2_rate": "The speed of LFO 2.",
    "lfo2_offset": "Raises or lowers LFO 2's wave so it swings more one way than the other.",
    "lfo2_delay_time": "How long after the key press LFO 2 starts.",
    "lfo2_fade_mode": "Whether LFO 2 fades in or out, and whether the fade starts at key-on or key-off.",
    "lfo2_fade_time": "How long LFO 2's fade takes.",
    "lfo2_external_sync": "Locks LFO 2 to an external clock or tapped tempo.",
    "coarse_tune": "Tunes the tone in semitones.",
    "fine_tune": "Tunes the tone in cents (hundredths of a semitone).",
    "random_pitch_depth": "A small random pitch change for every note, in cents.",
    "pitch_keyfollow": "How much the pitch follows the keyboard: +100 is normal, 0 plays every key at the same pitch.",
    "pitch_envelope_depth": "How far the pitch envelope moves the pitch.",
    "pitch_envelope_velocity_sens": "How much key velocity changes the depth of the pitch envelope.",
    "pitch_envelope_velocity_time1": "How much key velocity changes the time of the pitch envelope's first stage.",
    "pitch_envelope_velocity_time4": "How much key velocity changes the time of the pitch envelope's last stage (the release).",
    "pitch_envelope_time_keyfollow": "How much the keyboard position shortens or lengthens the pitch envelope's times.",
    "pitch_lfo1_depth": "How much LFO 1 modulates the pitch (vibrato).",
    "pitch_lfo2_depth": "How much LFO 2 modulates the pitch (vibrato).",
    "filter_type": "OFF, low-pass (LPF), band-pass (BPF), high-pass (HPF) or peaking (PKG).",
    "cutoff_frequency": "The filter's cutoff: for a low-pass filter, sounds above it are cut.",
    "cutoff_keyfollow": "How much the cutoff follows the keyboard: higher notes open the filter more.",
    "resonance": "Emphasizes the frequencies around the cutoff.",
    "resonance_velocity_sens": "How much key velocity changes the resonance.",
    "filter_envelope_depth": "How far the filter envelope moves the cutoff.",
    "filter_envelope_velocity_curve": "The curve that maps key velocity to the filter envelope's depth.",
    "filter_envelope_velocity_sens": "How much key velocity changes the depth of the filter envelope.",
    "filter_envelope_velocity_time1": "How much key velocity changes the time of the filter envelope's first stage.",
    "filter_envelope_velocity_time4": "How much key velocity changes the time of the filter envelope's last stage (the release).",
    "filter_envelope_time_keyfollow": "How much the keyboard position shortens or lengthens the filter envelope's times.",
    "filter_lfo1_depth": "How much LFO 1 modulates the cutoff (wah).",
    "filter_lfo2_depth": "How much LFO 2 modulates the cutoff (wah).",
    "tone_level": "The level of this tone.",
    "bias_direction": "Which side of the bias position gets quieter.",
    "bias_position": "The key where the bias takes effect.",
    "bias_level": "How much quieter the notes beyond the bias position are.",
    "level_envelope_velocity_curve": "The curve that maps key velocity to the tone's level.",
    "level_envelope_velocity_sens": "How much key velocity changes the tone's level.",
    "level_envelope_velocity_time1": "How much key velocity changes the time of the level envelope's first stage.",
    "level_envelope_velocity_time4": "How much key velocity changes the time of the level envelope's last stage (the release).",
    "level_envelope_time_keyfollow": "How much the keyboard position shortens or lengthens the level envelope's times.",
    "level_lfo1_depth": "How much LFO 1 modulates the level (tremolo).",
    "level_lfo2_depth": "How much LFO 2 modulates the level (tremolo).",
    "tone_pan": "Where the tone sits in the stereo field.",
    "pan_keyfollow": "How much the pan follows the keyboard: positive values spread low notes left and high notes right.",
    "random_pan_depth": "A random pan position for every note.",
    "alternate_pan_depth": "Alternates the pan left and right with each note.",
    "pan_lfo1_depth": "How much LFO 1 moves the pan (auto-pan).",
    "pan_lfo2_depth": "How much LFO 2 moves the pan (auto-pan).",
    "output_assign": "Where the tone goes: MIX (the normal stereo mix) or EFX (through the patch's effect).",
    "mix_efx_send_level": "How much of the tone goes to the main mix or effect.",
    "chorus_send_level": "How much of the tone is sent to the chorus.",
    "reverb_send_level": "How much of the tone is sent to the reverb.",
}

_ENVELOPE = re.compile(r"^(pitch|filter|level)_envelope_(time|level)_(\d)$")
_CONTROLLER = re.compile(r"^controller_(\d)_(destination|depth)_(\d)$")
_ENVELOPE_NAMES = {"pitch": "pitch", "filter": "filter", "level": "level"}


def hint(block_key, key):
    """The one-sentence explanation for a parameter, or None."""
    table = COMMON if block_key == "patch_common" else TONE if block_key == "patch_tone" else {}
    if key in table:
        return table[key]
    if block_key == "patch_tone":
        if m := _ENVELOPE.match(key):
            kind, what, stage = m[1], m[2], int(m[3])
            if what == "time":
                return f"How long stage {stage} of the {kind} envelope takes" + (" (the release, after the key is released)." if stage == 4 else ".")
            if kind == "level" and stage == 3:
                return "The sustain level of the level envelope: held while the key is down."
            if stage == 3:
                return f"The {kind} envelope's sustain level: held while the key is down."
            return f"The {kind} envelope's level at the end of stage {stage}." if stage < 4 else f"Where the {kind} envelope ends after the key is released."
        if m := _CONTROLLER.match(key):
            if m[2] == "destination":
                return f"What controller {m[1]} changes (its destination {m[3]} of 4): pitch, cutoff, level, pan, effect sends and LFO settings."
            return f"How strongly controller {m[1]} changes its destination {m[3]}; negative values reverse the direction."
    if block_key == "patch_common":
        if m := re.match(r"^efx_parameter_(\d+)$", key):
            return "A parameter of the chosen effect type: its name changes with the type."
    return None
