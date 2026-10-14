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


def test_groups_have_readable_titles_and_every_one_is_explained():
    assert [g.title for g in pg.GROUPS] == ["USER", "Preset A", "Preset B", "Preset C", "Preset D (GM)", "Preset E", "Session"]
    assert set(pg.GROUP_HELP) == {g.key for g in pg.GROUPS} and all(text.endswith(".") for text in pg.GROUP_HELP.values())


def test_the_category_list_covers_the_factory_sounds_and_every_entry_can_be_chosen_by_program_change():
    from jv_studio.core import audition

    entries = {c: pg.category_entries(c) for c in pg.CATEGORIES}
    assert {c: len(e) for c, e in entries.items()} == {"PIANO": 59, "KEY&ORGAN": 116, "GUITAR/BASS": 151, "ORCH/BRASS": 162, "SYNTH/PAD": 355, "ETHNIC": 27, "RHYTHM&SFX": 25}
    every = [(e.group.key, e.number) for c in entries.values() for e in c]
    assert len(every) == len(set(every)) == 640 + 255  # every factory patch: Presets A-E and Session
    for group, number in every:
        audition.patch_select(0, group, number)  # raises for a patch with no Bank Select / Program Change
    for category, found in entries.items():
        for e in found:
            assert e.name == pg.name_of(e.group.type, e.group.id, e.number)  # the same patch, by the Patch List's own spelling
    piano = entries["PIANO"]
    assert [e.no for e in piano] == list(range(1, 60)) and (piano[7].no, piano[7].name, piano[7].group.key, piano[7].number) == (8, "Bright Piano", "PR-A", 1)  # the manual's own example: PIANO 008
    synth = {e.no: e for e in entries["SYNTH/PAD"]}
    assert list(synth) == list(range(1, 356))  # whole numbering, no hole
    # the manual prints "054 DanceStack 8" and no 055; a Max for Live editor lists 054 DanceStack 7 and 055 DanceStack 8 (unconfirmed on a unit), which is what is used
    assert [(synth[n].name, synth[n].group.key, synth[n].number) for n in (53, 54, 55, 56)] == [("DanceStack 6", "XP-A", 148), ("DanceStack 7", "XP-A", 149), ("DanceStack 8", "XP-A", 150), ("Big BPF", "PR-C", 102)]
