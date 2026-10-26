"""Download the bitmap-style font the Macintosh System 6 theme uses and put it where the app looks for it (src/jv_studio/ui/fonts/ChiKareGo2.ttf).

    uv run --with fonttools python tools/fetch_system6_font.py

ChiKareGo2 is Giles Booth's recreation of Chicago 12, packaged as a .woff by https://github.com/sakofchit/system.css (MIT for the CSS and icons; the font
files carry no licence text of their own). The owner confirmed 2026-10-26 that it is Creative Commons Attribution (credit in ui/fonts/README.txt), so the
result IS committed and bundled (the build scripts' DATA_ARGS); this script only re-creates it. Without the file the theme falls back to Geneva / Monaco / any monospace font.
"""

import io
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/sakofchit/system.css/main/fonts/ChiKareGo2.woff"
TARGET = Path(__file__).resolve().parent.parent / "src" / "jv_studio" / "ui" / "fonts" / "ChiKareGo2.ttf"


def main():
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        sys.exit("needs fontTools: uv run --with fonttools python tools/fetch_system6_font.py")
    data = urllib.request.urlopen(URL, timeout=20).read()
    font = TTFont(io.BytesIO(data))
    font.flavor = None  # woff -> plain TrueType, which Qt loads everywhere
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    font.save(TARGET)
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
