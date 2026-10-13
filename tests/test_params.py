# The parameter table (generated from the manual) and reading/writing values in a block's bytes.

import json
from importlib import resources

import pytest

from jv_studio.core import params

# the sizes the manual prints on each "Total size" line
MANUAL_SIZES = {
    "system_common": 0x66,
    "scale_tune": 0x0C,
    "performance_common": 0x42,
    "performance_part": 0x19,
    "patch_common": 0x4A,
    "patch_tone": 0x81,
    "rhythm_common": 0x0C,
    "rhythm_note": 0x3A,
}


@pytest.fixture(scope="module")
def table():
    return params.load_table()


def test_the_table_has_every_block_with_the_manuals_size(table):
    assert {k: b.size for k, b in table.blocks.items()} == MANUAL_SIZES
    assert (table.model_id, table.device_id) == (0x6A, 0x10)


@pytest.mark.parametrize("key", list(MANUAL_SIZES))
def test_a_blocks_parameters_cover_every_byte_exactly_once(table, key):
    block = table.block(key)
    covered = sorted(i for p in block.params for i in range(p.offset, p.offset + p.size))
    assert covered == list(range(block.size))
    assert len({p.key for p in block.params}) == len(block.params)  # keys are unique within a block


def test_the_memory_map_has_the_start_addresses(table):
    by_name = {m.name: m.address for m in table.memory_map}
    assert by_name["System"] == (0, 0, 0, 0)
    assert by_name["Patch Mode Temporary Patch"] == (3, 0, 0, 0)
    assert by_name["User Patch USER:001"] == (0x11, 0, 0, 0)
    assert by_name["User Performance USER:01"] == (0x10, 0, 0, 0)


def test_spot_checks_against_the_manuals_patch_common(table):
    c = table.block("patch_common")
    name = c.param("patch_name")
    assert (name.offset, name.size, name.string) == (0, 12, True)
    assert (c.param("efx_type").offset, c.param("efx_type").max) == (0x0C, 39)
    tempo = c.param("patch_tempo")
    assert (tempo.offset, tempo.size, tempo.nibbled, tempo.min, tempo.max) == (0x2C, 2, True, 20, 250)
    assert (c.param("patch_level").offset, c.param("patch_category").offset) == (0x2E, 0x49)
    depth = c.param("efx_control_depth_1")
    assert (depth.min, depth.max) == (0, 126)  # the 2015 jv1010tool had 127: the manual says 126 (-63..+63)
    assert [x.label for x in c.param("reverb_type").choices] == ["ROOM1", "ROOM2", "STAGE1", "STAGE2", "HALL1", "HALL2", "DELAY", "PAN-DLY"]
    assert len(c.param("patch_category").choices) == 39  # 0-38 of a 0-127 range


def test_spot_checks_against_the_manuals_patch_tone(table):
    t = table.block("patch_tone")
    assert t.param("tone_switch").offset == 0
    wave = t.param("wave_number")
    assert (wave.offset, wave.size, wave.nibbled, wave.max) == (3, 2, True, 254)
    assert t.param("reverb_send_level").offset == 0x80  # data index 128: address +01 00
    assert (t.param("velocity_range_lower").min, t.param("velocity_range_upper").min) == (1, 1)  # 1-127, not 0-127
    assert t.param("tone_delay_mode").choices[4].label == "TAP-SYNC" and not t.param("tone_delay_mode").choices[4].jv1010


def test_every_parameters_range_is_sane(table):
    for block in table.blocks.values():
        for p in block.params:
            assert p.min <= p.max, (block.key, p.key)
            if p.choices:
                assert len(p.choices) <= p.max - p.min + 1
            if not p.string:
                assert p.max < (256 if p.nibbled else 128) or block.key == "system_common", (block.key, p.key, p.max)


def test_the_json_file_and_the_loader_agree_on_the_number_of_parameters(table):
    raw = json.loads(resources.files("jv_studio").joinpath("data/parameters.json").read_text(encoding="utf-8"))
    assert {k: len(v["params"]) for k, v in raw["blocks"].items()} == {k: len(b.params) for k, b in table.blocks.items()}


# -- values ---------------------------------------------------------------------------------------------------------------


def test_plain_values_clamp_to_the_range(table):
    buf = table.block("patch_common").new_buffer()
    p = table.block("patch_common").param("efx_type")
    assert params.write(buf, p, 17) == 17 and params.read(buf, p) == 17 and buf[0x0C] == 17
    assert params.write(buf, p, 500) == 39 and params.write(buf, p, -4) == 0


def test_nibbled_values_are_split_over_two_bytes_high_nibble_first(table):
    buf = table.block("patch_common").new_buffer()
    tempo = table.block("patch_common").param("patch_tempo")
    params.write(buf, tempo, 0xAB)  # 171
    assert buf[0x2C:0x2E] == bytes([0x0A, 0x0B]) and params.read(buf, tempo) == 0xAB  # the manual's own example: ABH is sent as 0AH 0BH
    assert params.write(buf, tempo, 10) == 20  # clamped to the 20-250 range
    wave = table.block("patch_tone").param("wave_number")
    tone = table.block("patch_tone").new_buffer()
    params.write(tone, wave, 254)
    assert tone[3:5] == bytes([0x0F, 0x0E]) and params.read(tone, wave) == 254


def test_names_are_padded_trimmed_and_limited_to_the_characters_the_unit_has(table):
    buf = table.block("patch_common").new_buffer()
    name = table.block("patch_common").param("patch_name")
    params.write(buf, name, "Warm Pad")
    assert bytes(buf[:12]) == b"Warm Pad    " and params.read(buf, name) == "Warm Pad"
    params.write(buf, name, "A very long patch name")
    assert params.read(buf, name) == "A very long "[:12].rstrip() and bytes(buf[12:13]) == b"\x00"  # nothing written past 12 characters
    params.write(buf, name, "café~")
    assert params.read(buf, name) == "caf"  # characters outside the unit's ASCII range become spaces


def test_values_are_shown_the_way_the_panel_shows_them(table):
    c, t = table.block("patch_common"), table.block("patch_tone")
    fmt = params.format_value
    assert fmt(c.param("efx_type"), 0) == "STEREO-EQ" and fmt(c.param("efx_type"), 39) == "CHORUS/FLANGER (parallel)"  # (it is named; the unit shows 1-40)
    assert fmt(c.param("efx_control_depth_1"), 0) == "-63" and fmt(c.param("efx_control_depth_1"), 63) == "0" and fmt(c.param("efx_control_depth_1"), 126) == "+63"
    assert fmt(c.param("reverb_type"), 6) == "DELAY"
    assert fmt(c.param("patch_pan"), 0) == "L64" and fmt(c.param("patch_pan"), 64) == "0" and fmt(c.param("patch_pan"), 127) == "63R"
    assert fmt(c.param("octave_shift"), 3) == "0" and fmt(c.param("octave_shift"), 6) == "+3"
    assert fmt(c.param("stretch_tune_depth"), 0) == "OFF" and fmt(c.param("stretch_tune_depth"), 2) == "2"
    assert fmt(c.param("key_assign_mode"), 1) == "SOLO"
    assert fmt(c.param("bend_range_down"), 12) == "-12" and fmt(c.param("bend_range_up"), 12) == "12"
    sysc = table.block("system_common")
    assert fmt(sysc.param("preview_note_set_1"), 60) == "C4" and fmt(sysc.param("preview_note_set_1"), 0) == "C-1"


def test_the_forty_efx_types_come_with_their_parameter_names():
    table = params.load_table()
    assert len(table.efx_types) == 40 and [t.number for t in table.efx_types] == list(range(1, 41))
    reverb = table.efx_type(23)  # the EFX Type value is number - 1
    assert reverb.name == "REVERB" and reverb.param(1).name == "Reverb Type" and (reverb.param(1).min, reverb.param(1).max) == (0, 5)
    assert table.efx_type(25).param(6).name is None  # OVERDRIVE->CHORUS: "(not used)"
    assert table.efx_type(0).param(12).name is None  # STEREO-EQ has 11 parameters
    assert table.efx_type(40) is None and table.efx_type(-1) is None
    assert all(len(t.params) in range(5, 13) for t in table.efx_types)


def test_the_efx_type_parameter_is_a_named_list_in_both_blocks():
    table = params.load_table()
    for block in ("patch_common", "performance_common"):
        efx = table.block(block).param("efx_type")
        assert efx.labels[0] == "STEREO-EQ" and len(efx.labels) == 40
        assert params.format_value(efx, 23) == "REVERB"
