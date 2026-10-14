"""Demo mode (`jv-studio --demo`): a MIDI session over a simulated JV-1010, so the app can be explored with no hardware and no MIDI ports."""

import os

from jv_studio.core import app_config, demo_unit, midi
from jv_studio.ui.midi_session import MidiSession

PORT_IN = "Demo JV-1010 (in)"
PORT_OUT = "Demo JV-1010 (out)"


def wanted(argv):
    """True when the app was started with `--demo` or JV_STUDIO_DEMO set (to anything but 0, false, no or off)."""
    return "--demo" in argv[1:] or os.environ.get("JV_STUDIO_DEMO", "").strip().lower() not in ("", "0", "false", "no", "off")


def latency():
    """Seconds per request. JV_STUDIO_DEMO_INSTANT=1 answers at once (tests, screenshots)."""
    instant = os.environ.get("JV_STUDIO_DEMO_INSTANT", "").strip().lower() not in ("", "0", "false", "no", "off")
    return 0.0 if instant else demo_unit.DEFAULT_LATENCY_S


def build_demo(request_latency=None, use_backup=True):
    """(an open MidiSession, the simulated unit it talks to). The unit holds the owner's own backup when `~/.jv-studio/demo-backup.syx` exists (`use_backup`), else the built-in contents."""
    unit = demo_unit.make_demo_unit(app_config.demo_backup_path() if use_backup else None)
    ports = demo_unit.DemoPorts(unit, latency() if request_latency is None else request_latency)
    session = MidiSession(lambda i, o: midi.MidiConnection(i, o, input_factory=ports.input_factory, output_factory=ports.output_factory))
    session.open(PORT_IN, PORT_OUT)
    return session, unit
