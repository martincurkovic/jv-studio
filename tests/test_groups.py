from jv1010editor.core import groups, params, patch


def test_every_shown_parameter_has_a_real_card():
    for block in (patch.COMMON, patch.TONE):
        shown = [p for _, ps in groups.groups(block) for p in ps]
        assert groups.OTHER not in [t for t, _ in groups.groups(block)], [p.key for p in dict(groups.groups(block)).get(groups.OTHER, [])]
        assert len({p.key for p in shown}) == len(shown)  # nobody on two cards
        assert {p.key for p in shown} == {p.key for p in params.load_table().block(block).param_list() if not p.jv1080_only}


def test_a_few_placements():
    assert groups.group_for(patch.TONE, "pitch_lfo1_depth") == "Pitch"
    assert groups.group_for(patch.TONE, "pan_lfo2_depth") == "Pan"
    assert groups.group_for(patch.TONE, "pan_control_switch") == "Controllers"
    assert groups.group_for(patch.TONE, "tone_delay_time") == "Wave"
    assert groups.group_for(patch.TONE, "chorus_send_level") == "Output"
    assert groups.group_for(patch.COMMON, "efx_chorus_send_level") == "EFX"
    assert groups.group_for(patch.COMMON, "chorus_depth") == "Chorus"
