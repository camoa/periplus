#!/usr/bin/env bash
# The README's example rutter, run from the README's own text. Each fenced block after a marker
# `<!-- example: <path> -->` is written to that path in a new project; the pack is validated and
# mapped twice, the two maps are byte-identical, and the map holds exactly the nodes and edges the
# block after `<!-- example-map -->` states, with their states and locations. README names the file
# read, the repository's by default, so a broken copy can be run.
set -euo pipefail
readme="${README:-$ROOT/README.md}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"
site="$work/site"
mkdir "$site"

python3 - "$readme" "$site" "$work/expected.txt" "$work/pack.txt" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
site = Path(sys.argv[2])
blocks = re.compile(
    r"^<!-- (?:example: (?P<path>\S+)|example-map) -->\n```[^\n]*\n(?P<body>.*?)^```$", re.M | re.S
)
found = list(blocks.finditer(text))
markers = re.findall(r"<!-- example(?::|-map)", text)
assert len(found) == len(markers), f"{len(markers)} markers, {len(found)} followed by a fenced block"
files = {m["path"]: m["body"] for m in found if m["path"]}
results = [m["body"] for m in found if not m["path"]]
assert len(results) == 1, f"{len(results)} example-map blocks"
packs = [p for p in files if re.fullmatch(r"\.periplus/packs/[^/]+@[^/]+/pack\.yaml", p)]
assert {".periplus/settings.yml"} <= set(files) and len(packs) == 1 and len(files) >= 4, sorted(files)
for path, body in files.items():
    target = site / path
    assert site in target.parents and ".." not in Path(path).parts, path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
Path(sys.argv[3]).write_text(results[0], encoding="utf-8")
Path(sys.argv[4]).write_text(packs[0].split("/")[2].split("@")[0], encoding="utf-8")
PY

pack="$(cat "$work/pack.txt")"
(cd "$site" && "$PERIPLUS" validate "$pack" >"$work/validate.txt") \
    || { cat "$work/validate.txt"; echo "the README's example rutter does not validate"; exit 1; }
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/again.json" --format json >/dev/null)
cmp "$work/map.json" "$work/again.json"

python3 - "$work/map.json" "$work/report.json" "$work/expected.txt" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for key in ("problems", "not_executed", "skipped", "unread", "parse_errors"):
    assert report[key] == [], (key, report[key])


def places(item):
    return tuple(sorted(f"{loc['file']}:{loc['line']}" for loc in item["locations"]))


actual = {("node", n["id"], n["state"], places(n)) for n in document["nodes"]}
actual |= {("edge", e["from"], e["kind"], e["to"], places(e)) for e in document["edges"]}
# Each line of the README's result: `node <id> <state> [<file>:<line> ...]` or
# `edge <from> <kind> <to> [<file>:<line> ...]`.
expected = set()
for line in open(sys.argv[3]).read().splitlines():
    words = line.split()
    if words and words[0] == "node":
        expected.add(("node", words[1], words[2], tuple(sorted(words[3:]))))
    elif words and words[0] == "edge":
        expected.add(("edge", words[1], words[2], words[3], tuple(sorted(words[4:]))))
    else:
        raise AssertionError(f"not a node or edge line in the README's result: {line!r}")
kinds = {item[0] for item in expected}
assert kinds == {"node", "edge"}, kinds
assert actual == expected, {"in the map only": sorted(actual - expected), "in the README only": sorted(expected - actual)}
print(f"readme example ok: {len(document['nodes'])} nodes, {len(document['edges'])} edges")
PY
