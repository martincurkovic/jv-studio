from jv_studio.core import groups, params, patch


def test_every_shown_parameter_has_a_real_card():
    for block in (patch.COMMON, patch.TONE):
        shown = [p for _, ps in groups.groups(block) for p in ps]
        assert groups.OTHER not in [t for t, _ in groups.groups(block)], [p.key for p in dict(groups.groups(block)).get(groups.OTHER, [])]
        assert len({p.key for p in shown}) == len(shown)  # nobody on two cards
        wanted = {p.key for p in params.load_table().block(block).param_list() if not p.jv1080_only and (block, p.key) not in groups.HIDDEN}
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
