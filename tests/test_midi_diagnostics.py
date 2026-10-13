# The loopback test and hardware detection, against fake ports.


from fakes import FakeJV1010, FakePorts, corrupting_loopback, loopback, silent
from jv_studio.core import loopback_report, midi, midi_diagnostics as diag, patch


def connect(respond):
    ports = FakePorts(respond)
    return midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory), ports


def test_a_good_loopback_passes_every_size():
    conn, _ = connect(loopback)
    results = diag.run_loopback(conn, sizes=[8, 127, 3072], timeout=0.5)
    assert [(s, p) for s, p, _ in results] == [(8, True), (127, True), (3072, True)]


def test_a_corrupting_interface_is_reported_with_where_it_went_wrong():
    conn, _ = connect(corrupting_loopback)
    (size, passed, detail), = diag.run_loopback(conn, sizes=[64], timeout=0.5)
    assert not passed and "corrupted" in detail and "first mismatch at byte" in detail


def test_a_missing_cable_times_out():
    conn, _ = connect(silent)
    (size, passed, detail), = diag.run_loopback(conn, sizes=[8], timeout=0.05)
    assert not passed and "timed out" in detail


def test_a_truncating_interface_is_reported():
    conn, _ = connect(lambda m: [m[: len(m) // 2] + bytes([0xF7])])
    (_, passed, detail), = diag.run_loopback(conn, sizes=[256], timeout=0.5)
    assert not passed and "sent 256 bytes" in detail


def test_progress_is_reported_before_each_size():
    conn, _ = connect(loopback)
    seen = []
    diag.run_loopback(conn, sizes=[8, 32], timeout=0.5, progress=seen.append)
    assert seen == [8, 32]


def test_the_default_sizes_cover_a_patch_tone_and_larger():
    assert 127 in diag.LOOPBACK_SIZES and 129 not in diag.LOOPBACK_SIZES and max(diag.LOOPBACK_SIZES) >= 3072


# -- hardware ------------------------------------------------------------------------------------------------------------


def test_a_jv1010_is_found_and_its_temporary_patch_name_is_read():
    unit = FakeJV1010("Warm Pad")
    conn, ports = connect(unit)
    result = diag.detect_hardware(conn, timeout=0.5)
    assert result.found and result.patch_name == "Warm Pad" and result.read_ok
    assert "Roland JV-1010 found" in result.message and 'Temporary patch: "Warm Pad"' in result.message and "Device ID: 16" in result.message
    assert unit.requests == [(patch.TEMPORARY_BASE, 0x4A)]  # exactly one read, of the common block


def test_it_sends_only_an_identity_request_and_one_read_never_a_write():
    conn, ports = connect(FakeJV1010())
    diag.detect_hardware(conn, timeout=0.5)
    commands = [m[4] if m[0] == 0xF0 and m[1] == 0x41 else None for m in ports.sent]
    assert len(ports.sent) == 2 and commands == [None, 0x11]  # the universal request, then one RQ1
    assert all(m[4] != 0x12 for m in ports.sent if m[1] == 0x41)  # no DT1


def test_a_unit_in_gm_mode_is_found_but_does_not_answer_the_read():
    conn, _ = connect(FakeJV1010(gm_mode=True))
    result = diag.detect_hardware(conn, timeout=0.05)
    assert result.found and result.read_ok is False and result.patch_name is None and "GM mode" in result.message


def test_silence_stops_after_the_identity_request():
    conn, ports = connect(silent)
    result = diag.detect_hardware(conn, timeout=0.05)
    assert result.status == diag.NO_REPLY and not result.found and len(ports.sent) == 1  # never sends into silence
    assert "No reply" in result.message


def test_another_roland_is_not_taken_for_a_jv1010():
    other = bytes.fromhex("F0 7E 10 06 02 41 6A 00 06 00 00 00 00 00 F7")
    conn, ports = connect(FakeJV1010(identity=other))
    result = diag.detect_hardware(conn, timeout=0.5)
    assert result.status == diag.OTHER_ROLAND and "isn't a JV-1010" in result.message and len(ports.sent) == 1


def test_a_different_manufacturer_is_reported():
    other = bytes.fromhex("F0 7E 00 06 02 00 20 32 21 00 09 00 01 02 03 04 F7")
    conn, _ = connect(FakeJV1010(identity=other))
    result = diag.detect_hardware(conn, timeout=0.5)
    assert result.status == diag.OTHER_DEVICE and "isn't a Roland" in result.message


def test_the_read_can_be_skipped():
    conn, ports = connect(FakeJV1010())
    result = diag.detect_hardware(conn, timeout=0.5, read_patch=False)
    assert result.found and result.read_ok is None and len(ports.sent) == 1


# -- the report -------------------------------------------------------------------------------------------------------------


def test_the_report_names_the_interface_and_says_what_failed():
    results = [(8, True, "OK"), (1024, False, "no response")]
    text = loopback_report.report_text(results, "USB MIDI", "USB MIDI", "macOS 26", "0.1.0")
    assert "MIDI interface: USB MIDI" in text and "1024 bytes: FAIL - no response" in text and "starts failing around 1024" in text
    assert "MIDI input: A" in loopback_report.report_text(results, "A", "B", "x", "1")
    assert loopback_report.verdict([(8, True, "OK")]) == "All sizes tested passed cleanly."


def test_sharing_on_github_is_off_until_there_is_a_repository(monkeypatch):
    assert loopback_report.issue_url([(8, True, "OK")], "A", "A", "x", "1") is None
    monkeypatch.setattr(loopback_report, "ISSUES_URL", "https://example.test/issues/new")
    assert loopback_report.issue_url([(8, True, "OK")], "A", "A", "x", "1").startswith("https://example.test/issues/new?title=")
