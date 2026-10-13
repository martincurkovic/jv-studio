"""The contents of the simulated JV-1010 that `jv-studio --demo` talks to (Qt-free), and the fake MIDI ports it answers on.

Nothing here is read from a real unit: the 128 USER patches have the factory names and voice counts from the manual's Patch List (two are renamed so the app has something
to highlight) and plausible settings, so every control shows a sensible value and the app can be explored, screenshotted and tested without hardware. The unit forgets
every write when the app quits.
"""

import time
from functools import lru_cache

from . import params, patch, performance, sysex
from .simulated_unit import SimulatedUnit

DEFAULT_LATENCY_S = 0.004  # a real unit answers a request in a few milliseconds: this makes progress bars (names, a backup of ~1,300 requests) visible

_RENAMED = {4: "My Lead", 76: "Warm Pad 2"}  # USER:005 and USER:077 differ from the factory list
_PERFORMANCE_NAMES = ["Live Rig", "Layer Pad", "Split Keys", "Studio Mix", "Str+Brass"]  # (a name is 12 characters at most)


# -- neutral blocks: every parameter at a harmless value (the middle of a -n..+n range, 0 where there is a 0, else the minimum) ------------------------------------------


def _neutral_value(param):
    if param.string:
        return ""
    if param.display_min is not None and param.display_max is not None and param.display_min < 0 < param.display_max and param.max != param.min:
        return round(param.min + (0 - param.display_min) * (param.max - param.min) / (param.display_max - param.display_min))
    if (param.display_text or "") in ("L64 - 63R", "L63 - 63R"):
        return 64
    labels = param.choice_labels()
    if "0" in labels:
        return param.min + labels.index("0")
    return param.min


def _neutral(block_key, buffer):
    for param in params.load_table().block(block_key).param_list():
        params.write(buffer, param, _neutral_value(param))
    return buffer


@lru_cache(maxsize=None)
def _neutral_patch():
    p = patch.Patch.blank()
    _neutral(patch.COMMON, p.common)
    for tone in p.tones:
        _neutral(patch.TONE, tone)
    return p


@lru_cache(maxsize=None)
def _neutral_performance():
    p = performance.Performance.blank()
    _neutral(performance.COMMON, p.common)
    for part in p.parts:
        _neutral(performance.PART, part)
    return p


@lru_cache(maxsize=None)
def _label(block_key, key, text):
    """The raw value of the option called `text` of a choice parameter."""
    param = params.load_table().block(block_key).param(key)
    return param.min + param.choice_labels().index(text)


# -- patches ------------------------------------------------------------------------------------------------------------------------------------------------------------


def demo_patch(index, name, voices, key_assign):
    """A playable patch: `voices` tones (1-4) on INT-A waves, a low-pass filter, a level envelope, a little reverb and chorus."""
    p = _neutral_patch().copy()  # (built once: 128 patches of ~600 values each would otherwise take seconds)
    p.name = name

    def common(key, value):
        p.set(patch.COMMON, key, value)

    common("patch_category", (index * 3) % 39)
    common("patch_tempo", 100 + index % 60)
    common("patch_level", 127)
    common("bend_range_up", 2)
    common("bend_range_down", 2)
    common("key_assign_mode", 1 if key_assign == "SOLO" else 0)
    common("clock_source", 0)
    common("efx_type", 23)  # REVERB (the unit's display counts from 1): its 12 parameters
    for n, value in enumerate((index % 6, 10, 0, 12, 15, 15, 40, 127), start=1):
        common(f"efx_parameter_{n}", value)
    common("efx_mix_out_send_level", 127)
    common("chorus_level", 40)
    common("chorus_rate", 30)
    common("chorus_depth", 40)
    common("chorus_pre_delay", 10)
    common("reverb_type", 4)  # HALL1
    common("reverb_level", 60)
    common("reverb_time", 70)
    common("reverb_hf_damp", 12)

    for t in range(4):
        def tone(key, value, t=t):
            p.set(patch.TONE, key, value, tone=t)

        tone("tone_switch", 1 if t < voices else 0)
        tone("wave_group_type", 0)
        tone("wave_group_id", 1)  # INT-A
        tone("wave_number", (index * 7 + t * 3) % 255)
        tone("wave_gain", 1)
        tone("velocity_range_lower", 1)
        tone("velocity_range_upper", 127)
        tone("keyboard_range_lower", 0)
        tone("keyboard_range_upper", 127)
        for key in ("volume_control_switch", "hold_1_control_switch", "pitch_bend_control_switch"):
            tone(key, 1)
        tone("pitch_keyfollow", _label(patch.TONE, "pitch_keyfollow", "+100"))
        tone("fine_tune", 50 + (t - 1) * 3 if t else 50)  # a touch of detune between the tones
        tone("filter_type", 1)  # LPF
        tone("cutoff_frequency", 50 + (index * 5 + t * 11) % 70)
        tone("resonance", 10 + (index * 3) % 40)
        tone("cutoff_keyfollow", _label(patch.TONE, "cutoff_keyfollow", "+30"))
        tone("filter_envelope_depth", 63 + 20)
        for n, (time_, level) in enumerate(((5, 127), (50, 90), (40, 70), (40, 0)), start=1):
            tone(f"filter_envelope_time_{n}", time_)
            tone(f"filter_envelope_level_{n}", level)
        tone("tone_level", 110)
        for n, time_ in enumerate((3, 40 + index % 30, 50, 30 + index % 40), start=1):
            tone(f"level_envelope_time_{n}", time_)
        for n, level in enumerate((127, 100, 90), start=1):
            tone(f"level_envelope_level_{n}", level)
        tone("tone_pan", 64 + (t - 1) * 12 if voices > 1 else 64)
        tone("mix_efx_send_level", 127)
        tone("chorus_send_level", 20)
        tone("reverb_send_level", 40)
    return p


# -- performances -----------------------------------------------------------------------------------------------------------------------------------------------------


def demo_performance(index):
    """A performance with eight parts on MIDI channels 1-8, each playing a preset patch."""
    p = _neutral_performance().copy()
    p.name = _PERFORMANCE_NAMES[index] if index < len(_PERFORMANCE_NAMES) else f"Demo Perf {index + 1:02d}"
    p.set(performance.COMMON, "performance_tempo", 100 + index * 4)
    p.set(performance.COMMON, "efx_type", 23)
    p.set(performance.COMMON, "efx_parameter_2", 10)
    p.set(performance.COMMON, "efx_parameter_7", 40)
    p.set(performance.COMMON, "efx_parameter_8", 127)
    p.set(performance.COMMON, "reverb_type", 4)
    p.set(performance.COMMON, "reverb_level", 60)
    p.set(performance.COMMON, "reverb_time", 70)
    p.set(performance.COMMON, "chorus_level", 40)
    for part in range(performance.PART_COUNT):
        on = part < 8
        p.set(performance.PART, "receive_switch", 1 if on else 0, part=part)
        p.set(performance.PART, "midi_channel", part, part=part)
        p.set(performance.PART, "patch_group_type", 0, part=part)
        p.set(performance.PART, "patch_group_id", 3 + (part + index) % 5, part=part)  # PR-A .. PR-E
        p.set(performance.PART, "patch_number", (part * 13 + index * 5) % 128, part=part)
        p.set(performance.PART, "part_level", 100 if on else 0, part=part)
        p.set(performance.PART, "part_pan", 64 + (part - 4) * 8, part=part)
        p.set(performance.PART, "keyboard_range_lower", 0, part=part)
        p.set(performance.PART, "keyboard_range_upper", 127, part=part)
        p.set(performance.PART, "mix_efx_send_level", 127, part=part)
        p.set(performance.PART, "chorus_send_level", 20, part=part)
        p.set(performance.PART, "reverb_send_level", 40, part=part)
        p.set(performance.PART, "receive_program_change_switch", 1, part=part)
        p.set(performance.PART, "receive_volume_switch", 1, part=part)
        p.set(performance.PART, "receive_hold_1_switch", 1, part=part)
        if part < 8:
            p.set(performance.COMMON, f"voice_reserve_{part + 1}", 4)
    return p


# -- the unit -------------------------------------------------------------------------------------------------------------------------------------------------------------


def make_demo_unit(**options):
    """A simulated JV-1010 holding the factory USER patch names, 32 performances and a temporary patch and performance. `options` are `SimulatedUnit`'s."""
    unit = SimulatedUnit(**options)
    factory = params.load_table().factory_user_patches
    for i, entry in enumerate(factory):
        unit.user[i] = demo_patch(i, _RENAMED.get(i, entry.name), entry.voices, entry.key_assign)
    unit.temporary = unit.user[1].copy()  # "St.Concert": the patch the owner's own unit had selected
    unit.user_performances = [demo_performance(i) for i in range(performance.USER_PERFORMANCE_COUNT)]
    unit.temp_performance = unit.user_performances[0].copy()
    return unit


# -- the fake MIDI ports ----------------------------------------------------------------------------------------------------------------------------------------------


class DemoPorts:
    """One input/output pair over a simulated unit, for `MidiConnection`'s `input_factory` / `output_factory`. Each request waits `latency` seconds before the reply arrives."""

    def __init__(self, unit, latency=DEFAULT_LATENCY_S):
        self.unit = unit
        self.latency = latency
        self._callback = None

    def input_factory(self, name):
        return _In(self)

    def output_factory(self, name):
        return _Out(self)

    def deliver(self, message):
        if self._callback is not None:
            self._callback((list(message), 0.0), None)


class _In:
    def __init__(self, ports):
        self._ports = ports

    def set_callback(self, callback):
        self._ports._callback = callback

    def close_port(self):
        self._ports._callback = None

    def delete(self):
        pass


class _Out:
    def __init__(self, ports):
        self._ports = ports

    def send_message(self, message):
        data = bytes(message)
        if self._ports.latency and len(data) > 4 and data[4] == sysex.CMD_RQ1:
            time.sleep(self._ports.latency)
        for reply in self._ports.unit(data) or []:
            self._ports.deliver(reply)

    def close_port(self):
        pass

    def delete(self):
        pass
