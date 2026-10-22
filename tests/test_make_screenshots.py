# tools/make_screenshots.py: every picture the guide shows has a recipe, and every recipe's picture is in the repo.

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

GUIDE = REPO / "src" / "jv_studio" / "ui" / "help" / "quickstart.md"
GUIDE_PICTURES = REPO / "src" / "jv_studio" / "ui" / "help" / "screenshots"
README_PICTURES = REPO / "docs" / "screenshots"


def recipes():
    import screenshot_recipes  # (importing it pulls in no Qt and no app module: the recipes import those only when run)

    return screenshot_recipes.SHOTS


def test_every_picture_the_guide_mentions_has_a_recipe():
    mentioned = set(re.findall(r"screenshots/([\w-]+)\.png", GUIDE.read_text(encoding="utf-8")))
    assert mentioned, "found no screenshots in quickstart.md"
    missing = sorted(n for n in mentioned if n not in recipes() or recipes()[n].folder != "guide")
    assert missing == [], f"quickstart.md uses pictures tools/make_screenshots.py can't make: {missing}"


def test_every_recipe_has_its_picture_in_the_repo():
    missing = [f"{s.folder}/{n}.png" for n, s in recipes().items() if not ((GUIDE_PICTURES if s.folder == "guide" else README_PICTURES) / f"{n}.png").is_file()]
    assert missing == []


def test_the_guide_does_not_carry_pictures_nothing_names():
    named = set(re.findall(r"screenshots/([\w-]+)\.png", GUIDE.read_text(encoding="utf-8")))
    on_disk = {p.stem for p in GUIDE_PICTURES.glob("*.png")}
    assert on_disk == named, f"unused: {sorted(on_disk - named)}, missing: {sorted(named - on_disk)}"
