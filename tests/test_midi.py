# MidiConnection over fake ports: queueing, reassembly, request/reply, closing.

import threading
import time

import pytest

from fakes import FakePorts, loopback, silent
from jv1010editor.core import midi, sysex


def open_connection(respond=None):
    ports = FakePorts(respond)
    return midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=ports.output_factory), ports


def test_a_sent_message_reaches_the_output_whole():
    conn, ports = open_connection()
    conn.send(sysex.IDENTITY_REQUEST)
    assert ports.sent == [sysex.IDENTITY_REQUEST]


def test_incoming_sysex_is_queued_and_everything_else_is_dropped():
    conn, ports = open_connection()
    ports.deliver([0x90, 60, 100])  # a note
    ports.deliver([0xB0, 7, 100])
    ports.deliver([0xF0, 1, 2, 3, 0xF7])
    assert conn.receive(0.1) == bytes([0xF0, 1, 2, 3, 0xF7])
    assert conn.receive(0.01) is None


def test_a_sysex_split_across_callbacks_is_reassembled():
    conn, ports = open_connection()
    ports.deliver([0xF0, 1, 2])
    ports.deliver([3, 4])
    ports.deliver([5, 0xF7])
    assert conn.receive(0.1) == bytes([0xF0, 1, 2, 3, 4, 5, 0xF7])


def test_a_stray_fragment_without_a_start_is_ignored():
    conn, ports = open_connection()
    ports.deliver([1, 2, 3, 0xF7])
    assert conn.receive(0.01) is None


def test_request_returns_the_first_matching_reply_and_ignores_the_rest():
    stray = bytes([0xF0, 0x42, 0xF7])
    wanted = bytes([0xF0, 0x41, 0xF7])
    conn, ports = open_connection(lambda m: [stray, wanted])
    assert conn.request(b"\xf0\x01\xf7", lambda r: r == wanted, timeout=0.5) == wanted


def test_request_gives_up_after_the_timeout_and_never_waits_forever():
    conn, _ = open_connection(silent)
    started = time.monotonic()
    assert conn.request(b"\xf0\x01\xf7", lambda r: True, timeout=0.1) is None
    assert time.monotonic() - started < 1.0


def test_a_stale_reply_is_not_taken_for_the_answer():
    conn, ports = open_connection(silent)
    ports.deliver([0xF0, 9, 9, 0xF7])  # left over from an earlier exchange
    assert conn.request(b"\xf0\x01\xf7", lambda r: True, timeout=0.05) is None


def test_the_pump_is_called_while_waiting():
    conn, _ = open_connection(silent)
    calls = []
    conn.receive(0.05, pump=lambda: calls.append(1))
    assert calls


def test_closing_closes_both_ports_and_further_sends_fail():
    conn, ports = open_connection()
    conn.close()
    assert sorted(ports.closed) == ["in", "out"] and not conn.is_open
    with pytest.raises(RuntimeError):
        conn.send(b"\xf0\xf7")


def test_close_waits_for_a_send_in_progress():
    # the AKAISDS crash: a port deleted while another thread was inside send_message. close() must take the same lock.
    ports = FakePorts()
    inside, release = threading.Event(), threading.Event()
    original = ports.output_factory

    class SlowOut:
        def __init__(self):
            self.base = original("out")

        def send_message(self, message):
            inside.set()
            release.wait(2)
            self.base.send_message(message)

        def close_port(self):
            self.base.close_port()

        def delete(self):
            pass

    conn = midi.MidiConnection("in", "out", input_factory=ports.input_factory, output_factory=lambda name: SlowOut())
    sender = threading.Thread(target=conn.send, args=(b"\xf0\x01\xf7",))
    sender.start()
    assert inside.wait(1)
    closer = threading.Thread(target=conn.close)
    closer.start()
    time.sleep(0.05)
    assert closer.is_alive()  # waiting for the send, not deleting the port under it
    release.set()
    sender.join(2)
    closer.join(2)
    assert not closer.is_alive() and not conn.is_open


def test_a_failed_open_closes_whatever_was_opened():
    ports = FakePorts()

    def bad_input(name):
        raise RuntimeError("no such port")

    with pytest.raises(RuntimeError):
        midi.MidiConnection("in", "out", input_factory=bad_input, output_factory=ports.output_factory)
    assert ports.closed == ["out"]


def test_listing_ports_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("CoreMIDI said no")

    monkeypatch.setattr(midi.rtmidi, "MidiIn", boom)
    monkeypatch.setattr(midi.rtmidi, "MidiOut", boom)
    assert midi.list_input_names() == [] and midi.list_output_names() == []
