"""The macOS DMG is laid out by build_macos.sh (dmgbuild) and CI uploads what it makes."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SCRIPTS = {"build_macos.sh": (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")}


WORKFLOW_TEXT = WORKFLOW.read_text(encoding="utf-8")


def job_text(name: str) -> str:
    """The text of one job in build.yml (the project has no YAML parser among its dependencies)."""
    return WORKFLOW_TEXT.split(f"\n  {name}:")[1].split("\n\n  ")[0]


# ------------------------------------------------------------------- the macOS DMG
def test_the_macos_script_builds_the_dmg_the_workflows_upload():
    script = SCRIPTS["build_macos.sh"]
    assert 'DMG_NAME="$APP_NAME-macos-$DMG_ARCH.dmg"' in script and "dmgbuild" in script
    assert "scripts/dmg_settings.py" in script and "assets/dmg/dmg_background.tiff" in script
    for arch in ("arm", "intel"):
        job = job_text(f"build-macos-{arch}")
        assert "hdiutil" not in job, "the DMG is built by build_macos.sh (a bare hdiutil one has no window layout)"
        assert f"path: ${{{{ env.APP_NAME }}}}-macos-{arch}.dmg" in job  # (the script's DMG_ARCH names it the same way)


def test_the_macos_script_sets_the_minimum_system_version_and_signs_again():
    script = SCRIPTS["build_macos.sh"]
    assert 'plutil -replace LSMinimumSystemVersion -string "$MIN_MACOS"' in script and 'MIN_MACOS="14.0"' in script
    assert script.index("codesign") > script.index("plutil") and script.index("dmgbuild") > script.index("codesign")  # (sign, then wrap in a DMG)


def test_the_dmg_window_matches_the_background_picture_drawn_for_it():
    settings = {"defines": {"app": "X.app", "background": "bg.tiff"}}
    exec((ROOT / "scripts" / "dmg_settings.py").read_text(encoding="utf-8"), settings)
    generator = (ROOT / "assets" / "dmg" / "create_dmg_background.py").read_text(encoding="utf-8")
    width, height = map(int, re.search(r"WIDTH, HEIGHT = (\d+), (\d+)", generator).groups())
    app_x, applications_x, icon_y = map(int, re.search(r"APP_ICON_X, APPLICATIONS_ICON_X, ICON_Y = (\d+), (\d+), (\d+)", generator).groups())
    assert settings["window_rect"][1] == (width, height)
    assert settings["icon_locations"] == {"X.app": (app_x, icon_y), "Applications": (applications_x, icon_y)}
    background = (ROOT / "assets" / "dmg" / "dmg_background.tiff").read_bytes()
    assert background[:4] in (b"MM\x00*", b"II*\x00") and len(background) > 10_000


def test_dmgbuild_is_a_build_dependency():
    assert re.search(r"^build = \[.*\"dmgbuild", (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
