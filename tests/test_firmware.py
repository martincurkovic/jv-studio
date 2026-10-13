# Roland's System Update files: reading, verifying and playing them (the sets here are made up with the real structure; nothing touches a unit).

import pytest

from firmware_files import FakeClock, block_data, messages_for, pack, smf, write_set
from jv_studio.core import firmware
from jv_studio.core.backup import Cancelled


@pytest.fixture
def good(tmp_path):
    return firmware.load(write_set(tmp_path / "fw"))


def errors(result):
    return [str(f) for f in result.errors]


def test_the_packing_round_trips_and_counts_real_bytes():
    real = bytes(range(256)) * 3
    assert firmware.unpack(pack(real)) == real
    assert firmware.packed_to_real(256) == 224 and firmware.packed_to_real(147) == 128 and firmware.packed_to_real(8) == 7 and firmware.packed_to_real(1) == 0


def test_a_good_set_loads_in_block_order_and_is_ok(good):
    assert good.ok and [b.number for b in good.blocks] == [1, 2, 32]
    assert good.total_frames == 3 * 294 and all(len(b.data) == 65536 for b in good.blocks)
    assert abs(good.blocks[0].delays[0] - 0.1015625) < 1e-9 and abs(good.blocks[0].tail - 10.0) < 1e-6
    assert good.blocks[0].declared_checksum == good.blocks[0].computed_checksum
    assert max(len(f) for b in good.blocks for f in b.frames) == firmware.MAX_MESSAGE_BYTES


def test_an_unknown_but_consistent_set_is_ok_with_a_warning(good):
    assert good.release == ""
    assert [f.level for f in good.findings] == ["warning"] and "not a release" in good.findings[0].text


def test_a_known_release_is_recognised_by_content_not_name(tmp_path, monkeypatch):
    folder = write_set(tmp_path / "fw")
    plain = firmware.load(folder)
    monkeypatch.setitem(firmware.KNOWN_RELEASES, "Test Release", {b.number: b.fingerprint for b in plain.blocks})
    for path in folder.iterdir():
        path.rename(folder / f"renamed-{path.name}")
    again = firmware.load(folder)
    assert again.ok and again.release == "Test Release" and again.findings[0].level == "info"


def test_a_corrupted_block_fails_its_checksum(tmp_path):
    result = firmware.load(write_set(tmp_path / "fw", corrupt=2))
    assert not result.ok and any("adds up to checksum" in e for e in errors(result))


def test_a_flipped_byte_inside_a_message_fails_the_roland_checksum(tmp_path):
    folder = write_set(tmp_path / "fw")
    path = folder / "_0000002.mid"
    raw = bytearray(path.read_bytes())
    raw[raw.index(b"\xf0", 100) + 20] ^= 0x01  # inside the first message's data
    path.write_bytes(raw)
    result = firmware.load(folder)
    assert not result.ok and any("bad checksum" in e for e in errors(result))


def test_another_models_update_is_refused(tmp_path):
    result = firmware.load(write_set(tmp_path / "fw", wrong_model=True))
    assert not result.ok and any("not for a JV-1010" in e for e in errors(result))


def test_a_missing_block_one_a_bad_marker_and_a_lone_block_are_refused(tmp_path):
    assert any("Block 1 is missing" in e for e in errors(firmware.load(write_set(tmp_path / "a", no_block_one=True))))
    assert any("incomplete or mixes versions" in e for e in errors(firmware.load(write_set(tmp_path / "b", wrong_marker=True))))
    assert any("single block" in e for e in errors(firmware.load(write_set(tmp_path / "c", numbers=(1,)))))


def test_a_missing_marker_block_is_caught_by_the_marker(tmp_path):
    # blocks 1 and 2 only, the last being treated as the marker block: its data is not 0xFF fill + a matching sum
    folder = write_set(tmp_path / "fw", skip=(32,))
    assert not firmware.load(folder).ok


def test_an_empty_or_missing_folder_is_an_error(tmp_path):
    assert errors(firmware.load(tmp_path / "nothing")) and errors(firmware.load(tmp_path))


def test_a_file_that_is_not_midi_is_reported_by_name(tmp_path):
    folder = write_set(tmp_path / "fw")
    (folder / "junk.mid").write_bytes(b"not midi at all")
    result = firmware.load(folder)
    assert not result.ok and any(e.startswith("junk.mid: not a Standard MIDI File") for e in errors(result))


def test_the_same_block_twice_is_an_error(tmp_path):
    folder = write_set(tmp_path / "fw")
    (folder / "copy.mid").write_bytes((folder / "_0000002.mid").read_bytes())
    assert any("block 2 is in both" in e for e in errors(firmware.load(folder)))


def test_the_text_events_must_agree_with_the_data(tmp_path):
    folder = tmp_path / "fw"
    write_set(folder)
    data = block_data(2)
    declared = firmware.word_sum(bytes(data))
    (folder / "_0000002.mid").write_bytes(smf(messages_for(2, data, declared), f"CHECKSUM = {declared ^ 1:04X}", "BLOCK02 LOADING"))
    assert any("CHECKSUM text" in e for e in errors(firmware.load(folder)))
    (folder / "_0000002.mid").write_bytes(smf(messages_for(2, data, declared), f"CHECKSUM = {declared:04X}", "BLOCK07 LOADING"))
    assert any("says BLOCK07" in e for e in errors(firmware.load(folder)))


def test_a_header_with_the_wrong_device_id_or_size_is_an_error(tmp_path):
    folder = tmp_path / "fw"
    write_set(folder)
    data = block_data(2)
    declared = firmware.word_sum(bytes(data))
    (folder / "_0000002.mid").write_bytes(smf(messages_for(2, data, declared, header_device=0x10), f"CHECKSUM = {declared:04X}", "BLOCK02 LOADING"))
    assert any("device ID 10H, not 11H" in e for e in errors(firmware.load(folder)))
    (folder / "_0000002.mid").write_bytes(smf(messages_for(2, data, declared, size_field=b"\x00\x00\x02\x00\x00"), f"CHECKSUM = {declared:04X}", "BLOCK02 LOADING"))
    assert any("size field" in e for e in errors(firmware.load(folder)))


def test_a_dropped_message_is_an_error(tmp_path):
    folder = tmp_path / "fw"
    write_set(folder)
    data = block_data(2)
    declared = firmware.word_sum(bytes(data))
    messages = messages_for(2, data, declared)
    del messages[5]
    (folder / "_0000002.mid").write_bytes(smf(messages, f"CHECKSUM = {declared:04X}", "BLOCK02 LOADING"))
    assert any("not the next address" in e for e in errors(firmware.load(folder)))


def test_a_channel_event_in_a_firmware_file_is_an_error(tmp_path):
    folder = tmp_path / "fw"
    write_set(folder)
    data = block_data(2)
    declared = firmware.word_sum(bytes(data))
    (folder / "_0000002.mid").write_bytes(smf(messages_for(2, data, declared), f"CHECKSUM = {declared:04X}", "BLOCK02 LOADING", extra_events=b"\x00\x90\x3c\x40"))
    assert any("not SysEx or a meta event" in e for e in errors(firmware.load(folder)))


# -- playing -------------------------------------------------------------------------------------------------------------


class Out:
    def __init__(self, clock, fail_after=None):
        self.clock, self.sent, self.fail_after = clock, [], fail_after

    def send(self, message):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise OSError("the port went away")
        self.sent.append((self.clock.now, bytes(message)))


def play(result, out, clock, **kw):
    return firmware.play(out, result, sleep=clock.sleep, clock=clock.clock, **kw)


def test_play_sends_every_message_in_order_never_faster_than_the_files(good):
    clock = FakeClock()
    out = Out(clock)
    result = play(good, out, clock)
    assert [m for _, m in out.sent] == [f for b in good.blocks for f in b.frames]
    assert result.blocks == 3 and result.messages == 3 * 294
    gaps = [b - a for (a, _), (b, _) in zip(out.sent, out.sent[1:])]
    assert all(g >= 0.1015625 - 1e-9 for g in gaps)
    # between the last message of a block and the first of the next: the file's 10 s tail, the pause, and the next file's own first delay
    long_gaps = [g for g in gaps if g > 1]
    assert len(long_gaps) == 2 and all(g >= 10.0 + firmware.INTER_BLOCK_PAUSE for g in long_gaps)


def test_play_reports_progress_up_to_the_planned_total_and_names_each_block(good):
    clock = FakeClock()
    progress, status = [], []
    play(good, Out(clock), clock, progress=lambda d, t: progress.append((d, t)), status=status.append)
    assert progress[-1][0] == progress[-1][1] and all(a[0] <= b[0] for a, b in zip(progress, progress[1:]))
    assert len(status) == 3 and status[0].startswith("Firmware: block 1 of 3") and "_0000032.mid" in status[2]


def test_play_refuses_a_set_that_failed_verification_and_sends_nothing(tmp_path):
    bad = firmware.load(write_set(tmp_path / "fw", corrupt=2))
    clock = FakeClock()
    out = Out(clock)
    with pytest.raises(firmware.FirmwareError, match="did not pass verification"):
        play(bad, out, clock)
    assert out.sent == []


def test_cancel_stops_between_messages_and_says_where(good):
    clock = FakeClock()
    out = Out(clock)
    with pytest.raises(Cancelled, match=r"in block 1 \(1 of 3\), after 10 of 882 messages.*play the update again from the first block"):
        play(good, out, clock, cancelled=lambda: len(out.sent) >= 10)
    assert len(out.sent) == 10


def test_a_failing_output_stops_the_update_and_says_how_far_it_got(good):
    clock = FakeClock()
    out = Out(clock, fail_after=300)  # into block 2
    with pytest.raises(firmware.FirmwareError, match=r"MIDI output failed in block 2 \(2 of 3\), after 300 of 882 messages"):
        play(good, out, clock)
    assert len(out.sent) == 300


def test_the_playing_time_is_the_files_plus_the_pauses(good):
    expected = 3 * (294 * 0.1015625 + 10.0) + 2 * firmware.INTER_BLOCK_PAUSE
    assert abs(good.duration - expected) < 0.01
