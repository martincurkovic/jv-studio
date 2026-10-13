from jv_studio.core import groups, params, patch, performance


def test_every_shown_parameter_has_a_real_card():
    for block in (patch.COMMON, patch.TONE):
        shown = [p for _, ps in groups.groups(block) for p in ps]
        assert groups.OTHER not in [t for t, _ in groups.groups(block)], [p.key for p in dict(groups.groups(block)).get(groups.OTHER, [])]
        assert len({p.key for p in shown}) == len(shown)  # nobody on two cards
        wanted = {p.key for p in params.load_table().block(block).param_list() if groups.supported(p) and (block, p.key) not in groups.HIDDEN}
        assert {p.key for p in shown} == wanted


def test_a_few_placements():
    assert groups.group_for(patch.TONE, "pitch_lfo1_depth") == "Pitch"
    assert groups.group_for(patch.TONE, "pan_lfo2_depth") == "Pan"
    assert groups.group_for(patch.TONE, "pan_control_switch") == "Controllers"
    assert groups.group_for(patch.TONE, "tone_delay_time") == "Wave"
    assert groups.group_for(patch.TONE, "chorus_send_level") == "Output"
    assert groups.group_for(patch.COMMON, "efx_chorus_send_level") == "EFX"
    assert groups.group_for(patch.COMMON, "chorus_depth") == "Chorus"


def test_the_wave_numbers_are_not_controls_because_the_picker_sets_them():
    keys = {p.key for _, members in groups.groups(patch.TONE) for p in members}
    assert not keys & {"wave_group_type", "wave_group_id", "wave_number"} and "wave_gain" in keys


def test_every_shown_performance_parameter_has_a_card():
    for block in (performance.COMMON, performance.PART):
        cards = groups.groups(block)
        assert groups.OTHER not in [t for t, _ in cards], [p.key for p in dict(cards).get(groups.OTHER, [])]
        shown = {p.key for _, members in cards for p in members}
        assert shown == {p.key for p in params.load_table().block(block).param_list() if groups.supported(p) and (block, p.key) not in groups.HIDDEN}


def test_what_the_jv1010_does_not_have_is_not_shown():
    common = {p.key for _, members in groups.groups(performance.COMMON) for p in members}
    part = {p.key for _, members in groups.groups(performance.PART) for p in members}
    assert "keyboard_mode" not in common  # <LAYER, SINGLE>: every choice is JV-1080 only
    assert not part & {"octave_shift", "local_switch", "transmit_switch", "transmit_bank_select_group", "transmit_volume", "patch_number", "patch_group_id"}
    assert {"receive_switch", "midi_channel", "part_level", "part_pan", "output_assign", "keyboard_range_lower"} <= part
    assert {"performance_name", "performance_tempo", "voice_reserve_1", "efx_source", "reverb_type"} <= common
