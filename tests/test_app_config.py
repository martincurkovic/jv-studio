import json

from jv_studio.core import app_config


def test_nothing_saved_reads_as_defaults():
    assert app_config.get_saved_ports() == (None, None)
    assert app_config.get_saved_theme() == "system"
    assert app_config.get_collapsed_cards() == []


def test_ports_and_theme_round_trip():
    app_config.save_ports("IAC In", "IAC Out")
    app_config.save_theme("dark")
    assert app_config.get_saved_ports() == ("IAC In", "IAC Out") and app_config.get_saved_theme() == "dark"
    assert json.loads(app_config.CONFIG_PATH.read_text())["midi_input_port"] == "IAC In"


def test_an_unknown_theme_reads_as_system_and_is_never_saved():
    app_config.save_theme("neon")
    assert app_config.get_saved_theme() == "system"
    app_config.CONFIG_PATH.write_text(json.dumps({"theme": 5}))
    assert app_config.get_saved_theme() == "system"


def test_a_corrupt_file_reads_as_nothing_saved():
    app_config.CONFIG_PATH.write_text("{not json")
    assert app_config.load_config() == {} and app_config.get_saved_ports() == (None, None)
    app_config.CONFIG_PATH.write_text("[1, 2]")
    assert app_config.load_config() == {}


def test_defaults_are_written_without_overwriting_what_is_there():
    app_config.save_ports("A", "B")
    app_config.ensure_defaults_saved()
    config = app_config.load_config()
    assert config["theme"] == "system" and config["midi_input_port"] == "A"


def test_collapsed_cards_ignore_junk():
    app_config.CONFIG_PATH.write_text(json.dumps({"collapsed_cards": ["a/b", 5, None]}))
    assert app_config.get_collapsed_cards() == ["a/b"]
    app_config.CONFIG_PATH.write_text(json.dumps({"collapsed_cards": "a"}))
    assert app_config.get_collapsed_cards() == []
