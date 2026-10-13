#!/usr/bin/env python3
"""Rebuild src/jv1010editor/data/parameters.json from the JV-1010 Owner's Manual.

The manual's "Parameter Address Map" (MIDI Implementation chapter) is a set of regular text tables. This reads the PDF with `pdftotext -layout`
(poppler: `brew install poppler`), parses them and writes the machine-readable table the editor uses. The PDF is Roland's and is NOT in the
repo (`/manual` is git-ignored); the JSON is the committed result. Run it again only if this parser changes.

    uv run python tools/extract_params.py [path/to/JV-1010_OM.pdf] [--check]

Every block is self-checked: the bytes its rows cover must be contiguous from 0 up to the manual's own "Total size" line, so a row the parser
missed or misread fails loudly instead of silently shifting an offset. `--check` parses and verifies without writing.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = ROOT / "manual" / "JV-1010_OM.pdf"
OUTPUT = ROOT / "src" / "jv1010editor" / "data" / "parameters.json"

# (block key, heading as printed in the manual, what a "name" row run collapses into)
BLOCKS = [
    ("system_common", "● 1-1-1.System Common"),
    ("scale_tune", "● 1-1-2.Scale Tune"),
    ("performance_common", "● 1-2-1.Performance Common"),
    ("performance_part", "● 1-2-2.Performance Part"),
    ("patch_common", "● 1-3-1.Patch Common"),
    ("patch_tone", "● 1-3-2.Patch Tone"),
    ("rhythm_common", "● 1-4-1.Rhythm Common"),
    ("rhythm_note", "● 1-4-2.Rhythm Note"),
]

# one row of a table: `|# 00 2C | 0000 aaaa | Patch Tempo     20 - 250 (...) *1 |`   (the # marks a value split into two 4-bit bytes)
ROW = re.compile(r"^\|(?P<nib>#?)\s+(?P<hi>[0-9A-F]{2}) (?P<lo>[0-9A-F]{2}) \|\s*(?P<bits>[01a-z ]{9})\s*\|\s*(?P<rest>.*)$")
CONTINUATION = re.compile(r"^\|\s+\|\s*(?P<bits>[01a-z ]{9})\s*\|\s*(?P<rest>.*)$")
TOTAL = re.compile(r"^\|Total size\s*\|\s*(?P<a>[0-9A-F]{2}) (?P<b>[0-9A-F]{2}) (?P<c>[0-9A-F]{2}) (?P<d>[0-9A-F]{2})")
# the description and its value range: "Patch Tempo     20 - 250", "Filter Envelope Velocity Curve 0 - 6 (1 - 7)"
DESCRIPTION = re.compile(r"^(?P<name>.+?)\s+(?P<min>\d+)\s*-\s*(?P<max>\d+)(?P<tail>.*)$")
FOOTNOTE = re.compile(r"^\*(?P<n>\d+)\s+(?P<text>.*)$")
SIDE_TABLE = re.compile(r"\s{3,}[+|].*$")  # a second table printed to the right of the first (the Wave Group / Patch Group tables)


def pdf_text(pdf):
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return out.replace("–", "-").replace("\r", "").split("\n")


def snake(name):
    name = re.sub(r"[^A-Za-z0-9]+", "_", name.replace("&", "and")).strip("_").lower()
    return name


def tail_parts(tail):
    """From what follows a row's range: the display text in (...), the *footnote and the -> side-table marker."""
    note = re.search(r"\*(\d+)", tail)
    paren = re.search(r"\((.*)\)", tail)
    return (paren.group(1).strip() if paren else None), (int(note.group(1)) if note else None), "->" in tail


def parse_display(text, lo, hi):
    """('1 - 40', range 0-39) -> a numeric display mapping; ('OFF,ON') -> labels; angle brackets mark values only the JV-1080 family uses."""
    if text is None:
        return {}
    result = {"display_text": text.strip()}
    inner = text.strip()
    if inner.startswith("<") and inner.endswith(">"):
        # "(<OFF,ON>)": the JV-1080/2080/XP meaning; the JV-1010 ignores the parameter's value (the manual's note at the top of the map)
        result["jv1080_only"] = True
        inner = inner[1:-1].strip()
    numeric = re.fullmatch(r"([+-]?\d+)\s*-\s*([+-]?\d+)", inner.replace("<", "").replace(">", "").strip())
    if numeric:
        a, b = int(numeric.group(1)), int(numeric.group(2))
        if abs(b - a) == hi - lo:  # display = display_min + (value - min) * (display_max - display_min) / (max - min); descending is allowed
            result["display_min"] = a
            result["display_max"] = b
        return result
    if "," in inner:
        labels = [x.strip() for x in inner.split(",")]
        if len(labels) == hi - lo + 1:
            result["labels"] = labels
    return result


def parse_footnote_choices(text, lo, hi):
    """A footnote like 'ROOM1, ROOM2, <DIRECT-1>' as a list of {label, jv1010} when it has exactly one entry per value of the range."""
    if "," not in text:
        return None
    count = hi - lo + 1
    counted = re.search(r"\s*\((\d+)\s*-\s*(\d+)\)\s*$", text)
    if counted:  # the list says how many of the values it names, e.g. Patch Category "(0-38)" of a 0-127 range
        count = int(counted.group(2)) - int(counted.group(1)) + 1
        text = text[: counted.start()]
    items = [x.strip() for x in re.split(r",\s*", text) if x.strip()]
    if len(items) != count:
        return None
    return [{"label": x.strip("<>"), "jv1010": not x.startswith("<")} for x in items]


def parse_block(lines, start):
    """Parse the table whose heading is at lines[start]; returns (params, size, footnotes)."""
    rows, size, footnotes, i = [], None, {}, start + 1
    current_note = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("● ") and i != start:
            break
        m = ROW.match(line)
        if m:
            rest = SIDE_TABLE.sub("", m["rest"]).rstrip().rstrip("|").rstrip()
            rows.append({"nib": bool(m["nib"]), "offset": int(m["hi"], 16) * 128 + int(m["lo"], 16), "bits": m["bits"].strip(), "rest": rest, "extra": []})
        elif rows and rows[-1]["nib"] and not rows[-1]["extra"] and (c := CONTINUATION.match(line)):
            rows[-1]["extra"].append(c["bits"].strip())
        else:
            t = TOTAL.match(line)
            if t:
                size = (int(t["a"], 16) << 21) | (int(t["b"], 16) << 14) | (int(t["c"], 16) << 7) | int(t["d"], 16)
            elif size is not None:
                f = FOOTNOTE.match(line.strip()) if not line.startswith(" " * 40) else None
                if f:
                    current_note = int(f["n"])
                    footnotes[current_note] = SIDE_TABLE.sub("", f["text"]).strip()
                elif re.match(r"^\s*(\d+|MIDI Implementation|Appendices|Reference)\s*$", line):
                    pass  # a page number or running header between table pages
                elif current_note is not None and re.match(r"^\s{4,}\S", line) and not line.strip().startswith("|"):
                    footnotes[current_note] += " " + SIDE_TABLE.sub("", line.strip()).strip()
                elif line.strip() == "":
                    pass
                elif not re.match(r"^\s*(\d+|MIDI Implementation|Appendices|Reference)\s*$", line) and not line.startswith("+"):
                    current_note = None
        i += 1
    return rows, size, footnotes


def build_params(rows, footnotes, block):
    params, unparsed = [], []
    used_keys = {}
    for row in rows:
        m = DESCRIPTION.match(row["rest"])
        if not m:
            unparsed.append(row)
            continue
        name, lo, hi, tail = m["name"].strip(), int(m["min"]), int(m["max"]), m["tail"]
        paren, note, side = tail_parts(tail)
        p = {"name": name, "offset": row["offset"], "bytes": 2 if row["nib"] else 1, "min": lo, "max": hi, "bits": row["bits"]}
        if row["nib"]:
            p["nibbled"] = True
        p.update(parse_display(paren, lo, hi))
        if note is not None:
            p["footnote"] = note
            if "display_text" not in p and re.fullmatch(r"C-1-Upper|Lower-G9", footnotes.get(note, "")):
                p["display_text"] = "C-1 - G9"  # a keyboard range end: the footnote only says which other end bounds it, but the values are notes
            choices = parse_footnote_choices(footnotes.get(note, ""), lo, hi)
            if choices:
                p["choices"] = choices
        if side:
            p["side_table"] = True
        key = snake(name)
        used_keys[key] = used_keys.get(key, 0) + 1
        p["key"] = key if used_keys[key] == 1 else f"{key}_{used_keys[key]}"
        params.append(p)
    return collapse_names(params), unparsed


def collapse_names(params):
    """'Patch Name 1'..'Patch Name 12' (one ASCII character each, 32-127) -> one 12-character string parameter."""
    out, i = [], 0
    while i < len(params):
        p = params[i]
        m = re.fullmatch(r"(.+?) 1", p["name"])
        if m and p["min"] == 32 and p["max"] == 127:
            base, n = m[1], 1
            while i + n < len(params) and params[i + n]["name"] == f"{base} {n + 1}" and params[i + n]["offset"] == p["offset"] + n:
                n += 1
            if n > 1:
                out.append({"key": snake(base), "name": base, "offset": p["offset"], "bytes": n, "min": 32, "max": 127, "bits": p["bits"], "string": True})
                i += n
                continue
        out.append(p)
        i += 1
    return out


def check_coverage(key, params, size):
    covered = []
    for p in params:
        covered.extend(range(p["offset"], p["offset"] + p["bytes"]))
    expected = list(range(size))
    # the Patch Tone's last parameter lives at address 01 00 (data index 128): addresses are 7-bit, sizes are counted in the same notation
    missing = sorted(set(expected) - set(covered))
    extra = sorted(set(covered) - set(expected))
    dup = sorted({x for x in covered if covered.count(x) > 1})
    return missing, extra, dup


def memory_map(lines):
    """The top-level start addresses ('11 00 00 00 | User Patch USER:001') as printed at the head of the map."""
    entries = []
    pat = re.compile(r"^\|\s+([0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2})\s+\|\s+(\S.*?)\s+(\d-\d)?\s*\|$")
    start = next(i for i, l in enumerate(lines) if l.startswith("3. Parameter Address Map"))
    for line in lines[start : start + 60]:
        m = pat.match(line)
        if m:
            entries.append({"address": m[1], "name": m[2].strip(), "section": m[3]})
    return entries


def factory_user_patches(lines):
    """The factory USER bank from the manual's Patch List: [{number, name, voices, key_assign}] for USER 001-128. The list is printed in columns
    (USER 001-064, USER 065-128, then the preset groups beside them): only the first two matches on a row are USER. Fails loudly unless all 128 are found."""
    start = next(i for i, l in enumerate(lines) if l.startswith("USER (User Group)"))
    row = re.compile(r"(\d{3}) {2,3}(.{12}) (\d) +(POLY|SOLO)")
    found = {}
    for line in lines[start + 1 : start + 80]:
        for m in list(row.finditer(line))[:2]:
            number = int(m[1])
            if 1 <= number <= 128 and number not in found:
                name = m[2].rstrip().replace("\u2019", "'").replace("\u2018", "'")  # the manual prints typographic quotes; the unit's ASCII has '
                found[number] = {"number": number, "name": name, "voices": int(m[3]), "key_assign": m[4]}
    missing = [n for n in range(1, 129) if n not in found]
    if missing:
        sys.exit(f"factory USER patch list: missing {missing[:10]}")
    return [found[n] for n in range(1, 129)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf = Path(args[0]) if args else DEFAULT_PDF
    check_only = "--check" in sys.argv
    if not pdf.exists():
        sys.exit(f"manual not found: {pdf}")
    lines = pdf_text(pdf)
    data = {
        "model_id": "6A",
        "device_id": "10",
        "source": "Roland JV-1010 Owner's Manual (2002), MIDI Implementation > Parameter Address Map, JV-1010 (Model ID=6AH)",
        "notes": [
            "Offsets are DATA indexes (the 7-bit address bytes folded: 01 00 = 128), sizes in bytes.",
            "'nibbled' values are split over two bytes, high nibble first (ABH is sent as 0AH 0BH).",
            "'jv1080_only' marks values the manual puts in angle brackets: for the JV-1080/2080/XP, ignored by the JV-1010.",
        ],
        "memory_map": memory_map(lines),
        "factory_user_patches": factory_user_patches(lines),
        "blocks": {},
    }
    problems = 0
    for key, heading in BLOCKS:
        # the heading is printed once in the map (and once in an index): the one followed by a table is the right one
        starts = [i for i, l in enumerate(lines) if l.strip() == heading]
        start = next((i for i in starts if any(ROW.match(l) for l in lines[i : i + 12])), None)
        if start is None:
            print(f"!! {key}: heading not found")
            problems += 1
            continue
        rows, size, footnotes = parse_block(lines, start)
        params, unparsed = build_params(rows, footnotes, key)
        missing, extra, dup = check_coverage(key, params, size)
        status = "ok" if not (unparsed or missing or extra or dup) else "PROBLEM"
        print(f"{key:20s} size {size:#06x} ({size:3d}) params {len(params):3d}  {status}")
        for r in unparsed:
            print(f"    unparsed row @ {r['offset']:#06x}: {r['rest'][:70]!r}")
        if missing or extra or dup:
            print(f"    missing {missing[:10]} extra {extra[:10]} duplicate {dup[:10]}")
        problems += bool(unparsed or missing or extra or dup)
        data["blocks"][key] = {
            "section": re.search(r"\d-\d-\d", heading)[0],
            "size": size,
            "footnotes": {str(k): v for k, v in sorted(footnotes.items())},
            "params": params,
        }
    if problems:
        sys.exit(f"{problems} block(s) failed their self-check: not writing")
    if check_only:
        print("check passed (nothing written)")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
