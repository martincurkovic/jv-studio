"""Build src/jv_studio/data/waves.json from the waveform lists on https://gumielectronic.net/?p=2312 ("Roland JV-1010 Waveform Lists").

The Owner's Manual has the wave-group table (which group is which Group Type / Group ID) but NOT the names of the waves; this page lists them for the JV-1010's
two internal groups (INT-A, INT-B) and two expansion boards (SR-JV80-09 Session, SR-JV80-04 Vintage Synth). It is a third-party compilation of facts (names and
numbers), recorded here with its source. Usage:

    curl -sL 'https://gumielectronic.net/index.php?rest_route=/wp/v2/posts/2312' -o waves.json     # (the page itself refuses some clients)
    uv run python tools/import_wave_names.py waves.json

The page numbers the internal groups from 000 and the boards from 001. This script stores NAMES IN ORDER: position 0 is raw Wave Number 0, which the unit's display
calls 001 (the manual: "0 - 254 (001 - 255)"). It fails unless the counts match the manual's ranges.
"""

import html
import json
import re
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "jv_studio" / "data" / "waves.json"

# heading on the page -> (key, title, Wave Group Type, Wave Group ID, expected count). The first three are the manual's table (p.78: INT-A type 0 id 1, 0-254;
# INT-B type 0 id 2, 0-192; XP-A "Session" type 2 id 9, 0-205). The Vintage Synth board's ID is NOT in the manual (None): its names are kept, never looked up.
GROUPS = [
    ("INT-A Waveforms", "int_a", "INT-A", 0, 1, 255),
    ("INT-B Waveforms", "int_b", "INT-B", 0, 2, 193),
    ("Session SR-JV80-09 Waveforms", "session", "SR-JV80-09 Session", 2, 9, 206),
    ("Vintage Synth SR-JV80-04 Waveforms", "vintage", "SR-JV80-04 Vintage Synth", 2, None, 255),
]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    content = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["content"]["rendered"]
    text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(br|/p|/div|/h\d|/li|/tr)[^>]*>", "\n", content)))
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    groups = []
    for index, (heading, key, title, group_type, group_id, count) in enumerate(GROUPS):
        start = lines.index(heading)
        end = lines.index(GROUPS[index + 1][0]) if index + 1 < len(GROUPS) else len(lines)
        names = [m[2].strip() for l in lines[start:end] if (m := re.match(r"^(\d{3})\s+(.+)$", l))]
        if len(names) != count:
            sys.exit(f"{title}: expected {count} waves, found {len(names)}")
        groups.append({"key": key, "title": title, "type": group_type, "id": group_id, "names": names})
    data = {
        "source": "https://gumielectronic.net/?p=2312 (Roland JV-1010 Waveform Lists), group types and IDs from the JV-1010 Owner's Manual, MIDI Implementation, Patch Tone",
        "notes": ["names[i] is raw Wave Number i; the unit's display calls it i + 1", "id null: the manual does not give the board's Group ID, so it is never looked up"],
        "groups": groups,
    }
    OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({sum(len(g['names']) for g in groups)} names)")


if __name__ == "__main__":
    main()
