#!/usr/bin/env bash
# Files no rule read, in a rutter written in the project's own packs folder for an invented format:
# the run report lists under unread each file below the rules' folders, at any depth, after
# excludes, that no executed rule selected, as sorted paths in JSON, and in text as a count, the
# count per ending, most first, and the paths. A file an exclude removes is not listed, nor is a
# file a rule read. A folder ending in one star selects its direct children only; a file two levels
# down is unread.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
pack="$site/.periplus/packs/drawer@0.0.1"
mkdir -p "$pack/rules" "$site/drawer/inner" "$site/shelf/alpha/sub"
printf 'periplus_version: 0\npacks:\n  - drawer@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: drawer
version: 0.0.1
depends: []
folders:
  drawer: ./drawer/**
  shelf: ./shelf/*
files:
  exclude: ['**/*.skip']
  types:
    sock:
      endings: [sock]
      reader: text
YAML
cat >"$pack/rules/drawer.yaml" <<'YAML'
node_types:
- name: drawer.sock
  id_namespace: drawer.sock
rules:
- rule: sock
  reads: file
  in: [drawer, shelf]
  match: {file: '*', filetype: sock, text: '(?m)^(?<colour>\w+)$'}
  id: {from: {capture: colour}}
  emits: [{node: {type: drawer.sock}}]
  confidence: declared
YAML
printf 'red\n' >"$site/drawer/left.sock"
printf 'blue\n' >"$site/drawer/inner/right.sock"
for name in coin.button lint.button key.ring note; do printf 'x\n' >"$site/drawer/$name"; done
printf 'x\n' >"$site/drawer/inner/old.button"
printf 'x\n' >"$site/drawer/hole.skip"
printf 'x\n' >"$site/outside.button"
printf 'green\n' >"$site/shelf/alpha/top.sock"
printf 'x\n' >"$site/shelf/alpha/sub/deep.button"
printf 'grey\n' >"$site/shelf/alpha/sub/low.sock"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" >"$work/report.txt")
python3 - "$work/report.json" "$work/report.txt" "$site" <<'PY'
import collections
import json
import os
import sys

report, text, site = json.load(open(sys.argv[1])), open(sys.argv[2]).read(), sys.argv[3]
assert report["problems"] == [], report["problems"]
# Expected from the planted tree: every file below drawer, less the read ending and the excluded.
expected = sorted(
    os.path.relpath(os.path.join(folder, name), site)
    for folder, _, names in os.walk(f"{site}/drawer")
    for name in names
    if not name.endswith((".sock", ".skip"))
)
# Below shelf/alpha, which ./shelf/* resolves: the two files of shelf/alpha/sub, the sock included,
# since one star selects direct children only.
expected = sorted(expected + ["shelf/alpha/sub/deep.button", "shelf/alpha/sub/low.sock"])
assert len(expected) == 7, expected
assert report["unread"] == expected, (report["unread"], expected)
lines = text.split("\n")
assert f"  unread    {len(expected)}" in lines, text
counts = collections.Counter(os.path.splitext(path)[1].lstrip(".") or "none" for path in expected)
start = lines.index("Files no rule read, by ending:")
rows = [line.strip() for line in lines[start + 1 : start + 1 + len(counts)]]
assert rows == [
    f"{ending} {n}" for ending, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
], rows
assert rows[0] == "button 4", rows
start = lines.index("Files no rule read:")
assert [line.strip() for line in lines[start + 1 : start + 1 + len(expected)]] == expected, text
assert lines[start + 1 + len(expected)] == "", text
PY

# Twenty-three unread files: the text report shows twenty paths, then a closing line with the rest.
many="$work/many"
mkdir -p "$many/.periplus/packs/drawer@0.0.1/rules" "$many/drawer" "$many/shelf"
cp "$site/.periplus/settings.yml" "$many/.periplus/settings.yml"
cp "$pack/pack.yaml" "$many/.periplus/packs/drawer@0.0.1/pack.yaml"
cp "$pack/rules/drawer.yaml" "$many/.periplus/packs/drawer@0.0.1/rules/drawer.yaml"
for n in $(seq -w 1 23); do printf 'x\n' >"$many/drawer/coin$n.button"; done
(cd "$many" && "$PERIPLUS" map --output "$work/many.json" >"$work/many.txt")
python3 - "$work/many.txt" "$many" <<'PY'
import os
import sys

text, site = open(sys.argv[1]).read(), sys.argv[2]
planted = sorted(f"drawer/{name}" for name in os.listdir(f"{site}/drawer"))
assert len(planted) == 23, planted
lines = text.split("\n")
start = lines.index("Files no rule read:")
assert [line.strip() for line in lines[start + 1 : start + 21]] == planted[:20], text
closing = lines[start + 21].strip()
assert closing == f"and {len(planted) - 20} more; the JSON report lists them all", closing
assert "3" in closing.split() and lines[start + 22] == "", text
PY
echo "unread files ok"
