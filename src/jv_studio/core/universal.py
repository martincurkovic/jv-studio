"""The three Universal SysEx messages the JV-1010 receives (Qt-free): Master Volume, GM System On and GM System Off. `[manual, MIDI Implementation: Universal Non-realtime and Realtime
System Exclusive Messages]`. All are plain MIDI messages (the standard ones every synth takes), not Roland DT1s: nothing is stored by them and there is no reply.

- **GM System On** (`F0 7E 7F 09 01 F7`) resets the internal settings to the GM initial state and puts the unit in GM mode. **In GM mode the unit ignores RQ1/DT1**, so JV Studio can neither
  read nor write it until GM System Off.
- **GM System Off** (`F0 7E 7F 09 02 F7`) makes the unit return to Performance mode.
- **Master Volume** (`F0 7F 7F 04 01 ll mm F7`, 7-bit value in `mm`; the manual says the LSB `ll` is processed as 00): the overall level. Not received in GM mode. The unit cannot be asked what
  it is now, and by the MIDI standard it is back at full after a power-on `[guess]`.
"""

GM_SYSTEM_ON = bytes([0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7])
GM_SYSTEM_OFF = bytes([0xF0, 0x7E, 0x7F, 0x09, 0x02, 0xF7])
MASTER_VOLUME_FULL = 127


def master_volume(level):
    """The Master Volume message for `level` 0-127 (the 7-bit MSB; the LSB is sent as 00)."""
    if not 0 <= level <= 127:
        raise ValueError(f"master volume {level} is outside 0-127")
    return bytes([0xF0, 0x7F, 0x7F, 0x04, 0x01, 0x00, level, 0xF7])


def classify(message):
    """What a message is, for the simulated unit and the log: "gm_on", "gm_off", ("master_volume", level), or None."""
    message = bytes(message)
    if message == GM_SYSTEM_ON:
        return "gm_on"
    if message == GM_SYSTEM_OFF:
        return "gm_off"
    if len(message) == 8 and message[:6] == bytes([0xF0, 0x7F, 0x7F, 0x04, 0x01, 0x00]) and message[-1] == 0xF7 and message[6] <= 0x7F:
        return ("master_volume", message[6])
    return None
