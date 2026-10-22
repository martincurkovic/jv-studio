"""Saved settings (`~/.jv-studio/config.json`): the MIDI ports, the theme, which section cards are collapsed, and whether the audition bar is open (Qt-free)."""

import json
from pathlib import Path

from . import debug_log

CONFIG_PATH = Path.home() / ".jv-studio" / "config.json"

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SYSTEM6 = "system6"  # a monochrome Macintosh System 6 look (a demo skin)
THEME_VALUES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK, THEME_SYSTEM6)

_DEFAULTS = {"theme": THEME_SYSTEM}


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        # a corrupt file silently reading as "nothing saved" is indistinguishable from a first launch when someone reports it
        debug_log.get_logger().error(f"app_config: couldn't read {CONFIG_PATH} - using defaults", exc_info=True)
        return {}


def save_config(config):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        debug_log.get_logger().info(f"app_config: saved {config!r}")
    except OSError:
        debug_log.get_logger().error(f"app_config: couldn't save config to {CONFIG_PATH}", exc_info=True)


def ensure_defaults_saved():
    """Write any default key that is missing, so a hand-editing user can see it exists."""
    config = load_config()
    missing = {k: v for k, v in _DEFAULTS.items() if k not in config}
    if missing:
        config.update(missing)
        save_config(config)


# -- MIDI ports -----------------------------------------------------------------------------------------------------------


def get_saved_ports():
    """(input name, output name), each None when nothing was saved."""
    config = load_config()
    return config.get("midi_input_port"), config.get("midi_output_port")


def save_ports(input_name, output_name):
    config = load_config()
    config["midi_input_port"] = input_name
    config["midi_output_port"] = output_name
    save_config(config)


# -- theme ----------------------------------------------------------------------------------------------------------------


def get_saved_theme():
    theme = load_config().get("theme", THEME_SYSTEM)
    return theme if theme in THEME_VALUES else THEME_SYSTEM  # an unknown (hand-edited or newer) value reads as "system"


def save_theme(theme):
    config = load_config()
    config["theme"] = theme if theme in THEME_VALUES else THEME_SYSTEM
    save_config(config)


# -- collapsed section cards (ui/section_card.py) ---------------------------------------------------------------------------


def get_collapsed_cards():
    cards = load_config().get("collapsed_cards", [])
    return [c for c in cards if isinstance(c, str)] if isinstance(cards, list) else []


def save_collapsed_cards(keys):
    config = load_config()
    config["collapsed_cards"] = sorted(set(keys))
    save_config(config)


# -- update check -----------------------------------------------------------------------------------------------------------


def get_last_update_check():
    """Unix time of the last successful update check, or 0 if there has not been one."""
    value = load_config().get("last_update_check", 0)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def save_last_update_check(timestamp):
    config = load_config()
    config["last_update_check"] = timestamp
    save_config(config)


def get_skipped_update_version():
    """The version the user chose "Skip This Version" for (the start-up check stays quiet about it), or None."""
    value = load_config().get("skipped_update_version")
    return value if isinstance(value, str) else None


def save_skipped_update_version(version):
    config = load_config()
    config["skipped_update_version"] = version
    save_config(config)


# -- backups ----------------------------------------------------------------------------------------------------------------


def get_middle_c():
    """Which octave note 60 is named in: 3 (Ableton, Yamaha: the default) or 4 (Roland's own, the manual and the unit)."""
    return 4 if load_config().get("middle_c") == 4 else 3


def save_middle_c(octave):
    config = load_config()
    config["middle_c"] = 4 if octave == 4 else 3
    save_config(config)


def get_show_raw_values():
    """Whether the Raw Values tabs (every value as the unit holds it: a developer's view) are shown. Off unless asked for."""
    return load_config().get("show_raw_values") is True


def save_show_raw_values(shown):
    config = load_config()
    config["show_raw_values"] = bool(shown)
    save_config(config)


def demo_backup_path():
    """Where `--demo` looks for a whole-unit backup (`.syx` from File > Back Up Unit) to fill the simulated unit with: the owner's own unit, for realism. It stays on the machine (it is
    Roland's factory sounds plus whatever the owner stored), never in the repo or an app bundle. Absent = the built-in demo contents. Read at call time so tests can redirect it."""
    return CONFIG_PATH.parent / "demo-backup.syx"


def backups_dir():
    """Where the app puts the automatic `.syx` backup of a USER patch before overwriting it (next to the config; read at call time so tests can redirect it)."""
    return CONFIG_PATH.parent / "backups"
