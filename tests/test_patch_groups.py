from jv_studio.core import params, patch_groups as pg


def test_the_preset_lists_are_complete():
    presets = params.load_table().preset_patches
    assert {k: len(v) for k, v in presets.items()} == {"PR-A": 128, "PR-B": 128, "PR-C": 128, "PR-D": 128, "PR-E": 128, "XP-A": 255}
    assert presets["PR-A"][0].name == "64voicePiano" and presets["PR-B"][3].key_assign == "SOLO" and presets["XP-A"][0].name == "St.Concert"
    assert all(p.name for group in presets.values() for p in group)


def test_groups_follow_the_manuals_table():
    assert [(g.key, g.type, g.id, g.count) for g in pg.GROUPS][:3] == [("USER", 0, 1, 128), ("PR-A", 0, 3, 128), ("PR-B", 0, 4, 128)]
    assert pg.group_for(0, 6).key == "PR-D" and pg.group_for(2, 9).key == "XP-A" and pg.group_for(0, 2) is None and pg.group_for(1, 5) is None


def test_describing_an_assignment():
    assert pg.describe(0, 3, 0) == "PR-A 001  64voicePiano"
    assert pg.describe(2, 9, 0) == "XP-A 001  St.Concert"
    assert pg.describe(0, 1, 4) == "USER 005"  # no USER names read yet: just the number
    assert pg.describe(0, 1, 4, ["a", "b", "c", "d", "Viola"]) == "USER 005  Viola"
    assert pg.describe(2, 4, 6) == "Group type 2, ID 4, patch 007"
    assert pg.describe(0, 3, 999) == "PR-A 1000"  # outside the group: the number, never a wrong name
