# JV1010Unit against the fake unit: reads, retries, verified writes, single-parameter edits, and the safety rules.

import pytest

from fakes import FakeJV1010, FakePorts
from jv_studio.core import midi, params, patch, sysex, unit, validate


def connect(fake, **kwargs):
    ports = FakePorts(fake)
    conn = midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory)
    clock = Clock()
    return unit.JV1010Unit(conn, timeout=0.05, clock=clock.now, sleep=clock.sleep, **kwargs), ports, clock


class Clock:
    """A fake clock so the 20 ms gaps are checked without waiting. Time moves only when something sleeps."""

    def __init__(self):
        self.t = 100.0
        self.slept = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        self.slept += seconds


def varied_patch(name="Edited"):
    p = patch.Patch.minimum()
    p.name = name
    p.set(patch.COMMON, "efx_type", 12)
    p.set(patch.COMMON, "patch_tempo", 133)
    for i in range(4):
        p.set(patch.TONE, "wave_number", 10 + i, tone=i)
        p.set(patch.TONE, "cutoff_frequency", 50 + i, tone=i)
        p.set(patch.TONE, "reverb_send_level", 90 - i, tone=i)  # the byte at data index 128
    return p


def test_read_block_returns_the_blocks_bytes():
    fake = FakeJV1010("Init")
    u, _, _ = connect(fake)
    data = u.read_block(patch.TEMPORARY_BASE, 0x4A)
    assert len(data) == 0x4A and data[:4] == b"Init"
    assert fake.requests == [(patch.TEMPORARY_BASE, 0x4A)]


def test_reading_a_whole_patch_makes_five_requests_one_at_a_time():
    fake = FakeJV1010()
    fake.temporary = varied_patch()
    u, _, _ = connect(fake)
    assert u.read_temporary_patch() == varied_patch()
    assert [a for a, _ in fake.requests] == [(3, 0, 0x00, 0), (3, 0, 0x10, 0), (3, 0, 0x12, 0), (3, 0, 0x14, 0), (3, 0, 0x16, 0)]
    assert [s for _, s in fake.requests] == [0x4A, 0x81, 0x81, 0x81, 0x81]


def test_a_user_patch_is_read_from_its_own_address():
    fake = FakeJV1010()
    fake.user[41] = varied_patch("User 42")
    u, _, _ = connect(fake)
    assert u.read_user_patch(41).name == "User 42"
    assert fake.requests[0][0] == (0x11, 41, 0, 0)


def test_a_dropped_reply_is_retried_once_then_succeeds():
    fake = FakeJV1010("Retry", drop_first_replies=1)
    u, _, _ = connect(fake)
    assert u.read_block(patch.TEMPORARY_BASE, 0x4A)[:5] == b"Retry" and len(fake.requests) == 2


def test_silence_raises_after_the_bounded_retries_and_never_floods():
    fake = FakeJV1010(gm_mode=True)
    u, ports, _ = connect(fake)
    with pytest.raises(unit.UnitError, match="GM mode"):
        u.read_block(patch.TEMPORARY_BASE, 0x4A)
    assert len(ports.sent) == 2  # the request and one retry: never more


def test_only_a_reply_naming_the_address_and_size_is_accepted():
    # a stray reply for a different block must not be taken for the answer
    fake = FakeJV1010("Right")
    u, ports, _ = connect(fake)
    original = fake.__call__
    stray = sysex.dt1((3, 0, 0x10, 0), bytes(0x81))
    ports.respond = lambda m: [stray] + original(m)
    assert u.read_block(patch.TEMPORARY_BASE, 0x4A)[:5] == b"Right"


def test_all_128_user_names_are_read_with_progress():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    seen = []
    names = u.read_user_patch_names(progress=lambda d, t: seen.append((d, t)))
    assert names[0] == "User 001" and names[127] == "User 128" and len(names) == 128
    assert seen[0] == (1, 128) and seen[-1] == (128, 128)
    assert all(size == 0x4A for _, size in fake.requests)  # the common block only: one request per patch


def test_reading_names_can_be_cancelled():
    u, _, _ = connect(FakeJV1010())
    count = {"n": 0}

    def cancelled():
        count["n"] += 1
        return count["n"] > 5

    assert len(u.read_user_patch_names(cancelled=cancelled)) == 5


def test_reads_never_write():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    u.read_temporary_patch()
    u.read_user_patch_names()
    assert fake.writes == []


# -- writing ----------------------------------------------------------------------------------------------------------------


def test_a_written_patch_lands_in_the_unit_and_is_verified_by_a_read_back():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    new = varied_patch()
    u.write_patch(patch.TEMPORARY_BASE, new)
    assert fake.temporary == new
    assert len(fake.requests) == 5  # the read-back


def test_writes_are_packets_of_at_most_128_bytes_at_least_20_ms_apart():
    fake = FakeJV1010()
    u, ports, clock = connect(fake)
    times = []
    original = u.connection.send

    def stamped(message):
        times.append(clock.now())
        original(message)

    u.connection.send = stamped
    u.write_patch(patch.TEMPORARY_BASE, varied_patch(), verify=False)
    assert [len(w.data) for w in fake.writes] == [74, 128, 1, 128, 1, 128, 1, 128, 1]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 0.0199 for g in gaps)


def test_a_write_the_unit_does_not_keep_is_reported_by_the_read_back():
    fake = FakeJV1010(ignore_writes=True)
    u, _, _ = connect(fake)
    with pytest.raises(unit.UnitError, match="read-back"):
        u.write_patch(patch.TEMPORARY_BASE, varied_patch())


def test_a_write_to_a_user_patch_does_not_touch_the_others():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    u.write_patch(patch.user_base(7), varied_patch("Seven"))
    assert fake.user[7].name == "Seven" and fake.user[6].name == "User 007" and fake.user[8].name == "User 009"
    assert fake.temporary.name == "Warm Pad"


def test_one_parameter_is_one_small_dt1_at_its_own_address():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    assert u.write_param(patch.TEMPORARY_BASE, patch.COMMON, "efx_type", 25) == 25
    (w,) = fake.writes
    assert (w.address, w.data) == ((3, 0, 0, 0x0C), bytes([25])) and fake.temporary.get(patch.COMMON, "efx_type") == 25


def test_a_tone_parameter_goes_to_its_tone_and_a_value_is_clamped():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    assert u.write_param(patch.TEMPORARY_BASE, patch.TONE, "cutoff_frequency", 999, tone=2) == 127
    (w,) = fake.writes
    assert w.address == (3, 0, 0x14, 0x51)  # Tone 3 at 14 00, cutoff at offset 0x51
    assert fake.temporary.get(patch.TONE, "cutoff_frequency", tone=2) == 127 and fake.temporary.get(patch.TONE, "cutoff_frequency", tone=1) == 0


def test_the_parameter_past_the_first_128_bytes_carries_into_the_next_address_byte():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    u.write_param(patch.TEMPORARY_BASE, patch.TONE, "reverb_send_level", 77, tone=0)
    (w,) = fake.writes
    assert w.address == (3, 0, 0x11, 0x00) and fake.temporary.get(patch.TONE, "reverb_send_level", tone=0) == 77


def test_a_nibbled_parameter_is_sent_as_two_bytes():
    fake = FakeJV1010()
    u, _, _ = connect(fake)
    u.write_param(patch.TEMPORARY_BASE, patch.COMMON, "patch_tempo", 171)
    (w,) = fake.writes
    assert (w.address, w.data) == ((3, 0, 0, 0x2C), bytes([0x0A, 0x0B])) and fake.temporary.get(patch.COMMON, "patch_tempo") == 171


def test_a_tone_parameter_needs_a_tone():
    u, _, _ = connect(FakeJV1010())
    with pytest.raises(ValueError):
        u.write_param(patch.TEMPORARY_BASE, patch.TONE, "cutoff_frequency", 5)


# -- validation ----------------------------------------------------------------------------------------------------------------


def test_a_healthy_patch_has_no_problems():
    assert validate.out_of_range(varied_patch()) == []
    assert validate.out_of_range(patch.Patch.minimum()) == []
    assert patch.Patch.minimum().name == "INIT PATCH"
    assert validate.out_of_range(patch.Patch.blank())  # all-zero bytes are NOT a valid patch: no name characters, a tempo of 0


def test_an_out_of_range_value_is_flagged_with_where_and_what():
    p = varied_patch()
    p.common[0x0C] = 40  # EFX type max is 39
    p.tones[2][0x05] = 9  # wave gain max is 3
    p.common[0] = 7  # a control character in the name
    problems = {(x.block, x.tone, x.key) for x in validate.out_of_range(p)}
    assert ("patch_common", None, "efx_type") in problems and ("patch_tone", 2, "wave_gain") in problems and ("patch_common", None, "patch_name") in problems
    assert any("tone 3" in str(x) and "wave_gain" not in str(x) and "Wave Gain" in str(x) for x in validate.out_of_range(p))


def test_a_value_past_the_named_choices_is_flagged():
    p = patch.Patch.minimum()
    p.common[0x49] = 100  # patch category has 39 named values (0-38) of a 0-127 range
    assert [x.key for x in validate.out_of_range(p)] == ["patch_category"]


def test_summaries_carry_name_and_key_assign():
    fake = FakeJV1010()
    fake.user[1].set(patch.COMMON, "key_assign_mode", 1)
    u, _, _ = connect(fake)
    got = u.read_user_patch_summaries()
    assert len(got) == 128 and got[0] == unit.PatchSummary("User 001", "POLY") and got[1].key_assign == "SOLO"


def test_write_param_verify_reads_the_block_back_and_catches_a_unit_that_ignored_it():
    fake = FakeJV1010()
    u, ports, _ = connect(fake)
    assert u.write_param(patch.TEMPORARY_BASE, patch.TONE, "cutoff_frequency", 77, tone=1, verify=True) == 77
    assert fake.temporary.get(patch.TONE, "cutoff_frequency", tone=1) == 77
    assert fake.requests[-1][1] == 129  # one request: that tone's block
    stubborn = FakeJV1010(ignore_writes=True)
    u2, _, _ = connect(stubborn)
    with pytest.raises(unit.UnitError):
        u2.write_param(patch.TEMPORARY_BASE, patch.COMMON, "patch_tempo", 150, verify=True)


# -- performances ----------------------------------------------------------------------------------------------------------------


def test_a_performance_is_read_in_17_requests_one_at_a_time():
    from jv_studio.core import performance

    fake = FakeJV1010()
    fake.temp_performance.set(performance.PART, "part_level", 99, part=6)
    u, ports, _ = connect(fake)
    got = u.read_temporary_performance()
    assert got == fake.temp_performance and got.get(performance.PART, "part_level", part=6) == 99
    assert len(fake.requests) == 17 and [size for _, size in fake.requests] == [66] + [25] * 16


def test_the_32_user_performance_names():
    from jv_studio.core import performance

    u, _, _ = connect(FakeJV1010())
    seen = []
    names = u.read_user_performance_names(progress=lambda d, t: seen.append((d, t)))
    assert len(names) == 32 and names[0] == "Perf 01" and names[31] == "Perf 32" and seen[-1] == (32, 32)
    assert len(u.read_user_performance_names(cancelled=lambda: True)) == 0


def test_writing_a_performance_is_verified_by_a_read_back():
    from jv_studio.core import performance

    fake = FakeJV1010()
    u, _, _ = connect(fake)
    new = performance.Performance.minimum()
    new.name = "Written"
    new.set(performance.PART, "part_pan", 100, part=15)
    u.write_performance(performance.user_base(7), new)
    assert fake.user_performances[7] == new
    stubborn = FakeJV1010(ignore_writes=True)
    u2, _, _ = connect(stubborn)
    with pytest.raises(unit.UnitError):
        u2.write_performance(performance.user_base(7), new)


def test_one_performance_parameter_can_be_set_and_checked():
    from jv_studio.core import performance

    fake = FakeJV1010()
    u, _, _ = connect(fake)
    assert u.write_performance_param(performance.TEMPORARY_BASE, performance.PART, "midi_channel", 9, part=9, verify=True) == 9
    assert fake.temp_performance.get(performance.PART, "midi_channel", part=9) == 9 and fake.temp_performance.get(performance.PART, "midi_channel", part=8) == 0
    assert u.write_performance_param(performance.TEMPORARY_BASE, performance.COMMON, "performance_tempo", 150) == 150
    with pytest.raises(ValueError):
        u.write_performance_param(performance.TEMPORARY_BASE, performance.PART, "part_level", 1)
    stubborn = FakeJV1010(ignore_writes=True)
    u2, _, _ = connect(stubborn)
    with pytest.raises(unit.UnitError):
        u2.write_performance_param(performance.TEMPORARY_BASE, performance.COMMON, "performance_tempo", 150, verify=True)
