from jv_studio.core import friendly, groups, params, patch, performance, rhythm, system


def shown_choice_params():
    for block in (patch.COMMON, patch.TONE, performance.COMMON, performance.PART, system.COMMON, rhythm.NOTE):
        for _, members in groups.groups(block):
            for param in members:
                if param.has_choices():
                    yield param


def test_the_examples_from_the_owner():
    assert friendly.label("reverb_type", "HALL1") == "Hall 1" and friendly.label("reverb_type", "ROOM2") == "Room 2"
    assert friendly.label("lfo1_waveform", "TRI") == "Triangle" and friendly.label("lfo2_waveform", "S&H") == "Sample & Hold"
    assert friendly.label("filter_type", "LPF") == "Low-Pass" and friendly.label("controller_1_destination_1", "CUT") == "Cutoff"


def test_effect_type_names():
    names = {t: friendly.label("efx_type", t) for t in params.load_table().block("patch_common").param("efx_type").labels}
    assert names["STEREO-EQ"] == "Stereo EQ" and names["HEXA-CHORUS"] == "Hexa Chorus" and names["2VOICE-PITCH-SHIFTER"] == "2-Voice Pitch Shifter"
    assert names["OVERDRIVE→CHORUS (serial)"] == "Overdrive → Chorus (serial)" and names["CHORUS/DELAY (parallel)"] == "Chorus / Delay (parallel)"
    assert names["REVERB"] == "Reverb" and names["TIME-CONTROL-DELAY"] == "Time Control Delay"
    assert len(set(names.values())) == 40


def test_on_off_and_unknown_labels_fall_back_sensibly():
    assert friendly.label("solo_legato", "OFF") == "Off" and friendly.label("solo_legato", "ON") == "On"
    assert friendly.label("voice_priority", "LOUDEST") == "Loudest" and friendly.label("patch_category", "NO ASSIGN") == "No Assign"
    assert friendly.label("anything", "-100") == "-100" and friendly.label("anything", "Mixed Case") == "Mixed Case"


def test_every_option_of_every_shown_list_has_a_readable_and_distinct_name():
    for param in shown_choice_params():
        labels = param.choice_labels()
        names = [friendly.label(param.key, text) for text in labels]
        assert len(set(names)) == len(names), (param.key, [n for n in names if names.count(n) > 1])
        for text, name in zip(labels, names):
            # nothing is left shouting: an all-caps word (other than the genuine abbreviations) means a missing entry
            words = [w for w in name.replace("→", " ").replace("/", " ").split() if w.isalpha() and w.isupper() and len(w) > 2]
            assert not [w for w in words if w not in {"LFO", "SAX", "VOX", "EFX", "MIDI"}], (param.key, text, name)


def test_performance_option_names():
    assert friendly.label("efx_source", "PERFORM") == "Performance" and friendly.label("efx_source", "PART 11") == "Part 11"
    assert friendly.label("clock_source", "PERFORMANCE") == "Performance" and friendly.label("output_assign", "PATCH") == "Patch"
