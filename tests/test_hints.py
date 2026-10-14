
from jv_studio.core import groups, hints, params, patch, rhythm


def test_every_hint_names_a_real_parameter():
    table = params.load_table()
    for block, mapping in (("patch_common", hints.COMMON), ("patch_tone", hints.TONE), ("performance_common", hints.PERFORMANCE_COMMON), ("performance_part", hints.PERFORMANCE_PART), ("rhythm_note", hints.RHYTHM_NOTE)):
        missing = [key for key in mapping if key not in table.block(block)]
        assert not missing, missing


def test_hints_are_one_short_sentence():
    for text in [*hints.COMMON.values(), *hints.TONE.values(), *hints.PERFORMANCE_COMMON.values(), *hints.PERFORMANCE_PART.values(), *hints.RHYTHM_NOTE.values()]:
        assert text.endswith(".") and len(text) <= 170 and "\n" not in text, text


def test_most_shown_parameters_have_an_explanation():
    for block in (patch.COMMON, patch.TONE, rhythm.NOTE):
        shown = [p.key for _, members in groups.groups(block) for p in members]
        explained = [k for k in shown if hints.hint(block, k)]
        assert len(explained) >= 0.85 * len(shown), [k for k in shown if k not in explained]


def test_the_envelope_and_controller_patterns():
    assert "stage 4" in hints.hint("patch_tone", "filter_envelope_time_4") and "release" in hints.hint("patch_tone", "filter_envelope_time_4")
    assert "sustain" in hints.hint("patch_tone", "level_envelope_level_3")
    assert "controller 2" in hints.hint("patch_tone", "controller_2_depth_1")
    assert hints.hint("patch_common", "efx_parameter_5").startswith("A parameter of the chosen effect")
    assert hints.hint("patch_tone", "no_such_key") is None


def test_performance_parameters_have_explanations_too():
    from jv_studio.core import groups, performance

    for block in (performance.COMMON, performance.PART):
        shown = [p.key for _, members in groups.groups(block) for p in members]
        missing = [k for k in shown if not hints.hint(block, k)]
        assert len(missing) <= 0.1 * len(shown), (block, missing)
    assert hints.hint("performance_common", "reverb_time") == hints.COMMON["reverb_time"]  # the effects are the patch's own
    assert "64 voices" in hints.hint("performance_common", "voice_reserve_3")
