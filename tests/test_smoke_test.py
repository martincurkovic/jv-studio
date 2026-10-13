# The built-app smoke test (CI runs it against every build): it must pass from a source tree too, and must leave the user's settings alone.

from jv_studio import smoke_test
from jv_studio.core import app_config, debug_log
from jv_studio.main import main


def test_the_smoke_test_passes_and_reports_each_check(tmp_path):
    report = tmp_path / "smoke.txt"
    config, log = app_config.CONFIG_PATH, debug_log.LOG_PATH
    assert smoke_test.run(str(report)) == 0
    text = report.read_text()
    for name in ("stylesheets", "svg images", "parameter table", "wave names", "diagrams", "midi backend", "windows"):
        assert f"ok    {name}:" in text, text
    assert text.rstrip().endswith("smoke test passed") and "FAIL" not in text
    assert (app_config.CONFIG_PATH, debug_log.LOG_PATH) == (config, log)  # the scratch settings are put back


def test_the_flag_is_handled_before_the_normal_startup(tmp_path):
    report = tmp_path / "smoke.txt"
    assert main(["jv-studio", f"--smoke-test={report}"]) == 0 and report.exists()


def test_a_missing_data_file_is_reported_not_raised(tmp_path, monkeypatch):
    from jv_studio.core import params

    def broken():
        raise FileNotFoundError("parameters.json")

    monkeypatch.setattr(params, "load_table", broken)
    report = tmp_path / "smoke.txt"
    assert smoke_test.run(str(report)) == 1
    assert "FAIL  parameter table: FileNotFoundError" in report.read_text()
