#!/usr/bin/env bash
# The worked examples of a condition on a second child, of an id pattern and of a declared end,
# run from the text of docs/rutter-author-guide-abilities.md. Each fenced block after `<!-- example <name>: <path> -->`
# is written to that path in a new project for that example. The example's rutter is validated
# and the project mapped. The block after `<!-- example <name> map -->` states, line by line, the
# nodes of each type it names, the edges of each kind it names, the skipped rows, and the fires of
# each rule of the rutter; the map and the report must hold exactly those. GUIDE names the file read, the repository's by default.
set -euo pipefail
guide="${GUIDE:-$ROOT/docs/rutter-author-guide-abilities.md}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"

python3 - "$guide" "$work" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
work = Path(sys.argv[2])
blocks = re.compile(
    r"^<!-- example (?P<name>\w+)(?:: (?P<path>\S+)| map) -->\n```[^\n]*\n(?P<body>.*?)^```$",
    re.M | re.S,
)
found = list(blocks.finditer(text))
markers = re.findall(r"^<!-- example \w+", text, re.M)
assert len(found) == len(markers), f"{len(markers)} markers, {len(found)} followed by a fenced block"
names = sorted({m["name"] for m in found})
assert names == ["declared", "facade", "prefix"], names
for name in names:
    site = work / name
    maps = [m["body"] for m in found if m["name"] == name and not m["path"]]
    assert len(maps) == 1, f"{name}: {len(maps)} map blocks"
    for m in found:
        if m["name"] == name and m["path"]:
            target = site / m["path"]
            assert site in target.parents and ".." not in Path(m["path"]).parts, m["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(m["body"], encoding="utf-8")
    (work / f"{name}.expected").write_text(maps[0], encoding="utf-8")
(work / "names.txt").write_text(" ".join(names), encoding="utf-8")
PY

for name in $(cat "$work/names.txt"); do
    site="$work/$name"
    packs=("$site"/.periplus/packs/*@*)
    [ "${#packs[@]}" -eq 1 ] || { echo "$name: ${#packs[@]} rutters in the example"; exit 1; }
    pack="$(basename "${packs[0]}")"
    pack="${pack%@*}"
    (cd "$site" && "$PERIPLUS" validate "$pack" >"$work/$name-validate.txt") \
        || { cat "$work/$name-validate.txt"; echo "$name: the guide's rutter does not validate"; exit 1; }
    (cd "$site" && "$PERIPLUS" map --output "$work/$name.json" --format json >"$work/$name-report.json")
    python3 - "$work/$name.json" "$work/$name-report.json" "$work/$name.expected" "$pack" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
pack = sys.argv[4]
for key in ("problems", "not_executed", "parse_errors"):
    assert report[key] == [], (pack, key, report[key])


def places(item):
    return tuple(sorted(f"{loc['file']}:{loc['line']}" for loc in item["locations"]))


# Each line: `node <id> <state> [<file>:<line> ...]`, `edge <from> <kind> <to> [<file>:<line> ...]`,
# `skipped <file>:<line> <rule> <reason>` or `fires <rule> <count>`.
expected, types, kinds, fires, skipped = set(), set(), set(), {}, set()
for line in open(sys.argv[3]).read().splitlines():
    words = line.split()
    if words and words[0] == "node":
        expected.add(("node", words[1], words[2], tuple(sorted(words[3:]))))
        types.add(words[1].split("::", 1)[0])
    elif words and words[0] == "edge":
        expected.add(("edge", words[1], words[2], words[3], tuple(sorted(words[4:]))))
        kinds.add(words[2])
    elif words and words[0] == "skipped" and len(words) > 3:
        file, _, at = words[1].rpartition(":")
        skipped.add((file, int(at), words[2], " ".join(words[3:])))
    elif words and words[0] == "fires" and len(words) == 3:
        fires[words[1]] = int(words[2])
    else:
        raise AssertionError(f"not a node, edge, skipped or fires line in the guide's result: {line!r}")
assert fires, f"{pack}: the guide states no fires"
actual = {
    ("node", n["id"], n["state"], places(n))
    for n in document["nodes"]
    if n["id"].split("::", 1)[0] in types
}
actual |= {
    ("edge", e["from"], e["kind"], e["to"], places(e))
    for e in document["edges"]
    if e["kind"] in kinds
}
assert actual == expected, {"in the map only": sorted(actual - expected), "in the guide only": sorted(expected - actual)}
rows = {(r["file"], r["line"], r["rule"], r["reason"]) for r in report["skipped"]}
assert rows == skipped, {"in the report only": sorted(rows - skipped), "in the guide only": sorted(skipped - rows)}
ran = {r["rule"]: r["fires"] for r in report["executed"] if r["pack"] == pack}
assert ran == fires, {"report": ran, "guide": fires}
print(f"guide example {pack} ok: {len(expected)} entries, fires {fires}")
PY
done
