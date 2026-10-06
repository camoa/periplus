#!/usr/bin/env bash
# A rule that finds things by a text pattern, in a rutter written in the project's own packs folder
# for an invented line format: one node per match, its id from a capture at the line of the match,
# an attribute from a capture, an edge to a captured name, and a captured name nothing defines as a
# node in state referenced. A file that is not UTF-8 text is an unreadable source.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
pack="$site/.periplus/packs/chores@0.0.1"
mkdir -p "$pack/rules" "$site/lists"
printf 'periplus_version: 0\npacks:\n  - chores@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: chores
version: 0.0.1
depends: []
folders:
  lists: ./lists
files:
  types:
    chores:
      endings: [chores]
      reader: text
YAML
cat >"$pack/rules/chores.yaml" <<'YAML'
node_types:
- name: chores.chore
  id_namespace: chores.chore
edge_kinds:
- kind: waits_for
  from: chores.chore
  to: chores.chore
rules:
- rule: chore
  reads: file
  in: [lists]
  match:
    file: '*'
    filetype: chores
    text: '(?m)^chore (?<name>\w+) by (?<who>\w+)(?: after (?<after>\w+))?$'
  id:
    from: {capture: name}
  emits:
  - node:
      type: chores.chore
  - attribute:
      name: owner
      from: {capture: who}
  confidence: declared
- rule: chore_waits
  reads: file
  in: [lists]
  match:
    file: '*'
    filetype: chores
    text: '(?m)^chore (?<name>\w+) by (?<who>\w+)(?: after (?<after>\w+))?$'
  id:
    from: {capture: name}
  emits:
  - edge:
      kind: waits_for
      from: this_node
      to:
        from: {capture: after}
  confidence: declared
YAML
cat >"$site/lists/home.chores" <<'TXT'
# the week
chore dishes by ana
chore laundry by ben after dishes

chore floors by ana after sweeping
TXT
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$site/lists/home.chores" <<'PY'
import json
import sys

document, lines = json.load(open(sys.argv[1])), open(sys.argv[2]).read().split("\n")
# Expected from the file itself: each "chore" line, its words split by spaces.
chores, waits = {}, set()
for number, line in enumerate(lines, 1):
    words = line.split(" ")
    if words[0] == "chore":
        chores[words[1]] = (number, words[3])
        if len(words) == 6:
            waits.add((words[1], words[5]))
assert len(chores) == 3 and len(waits) == 2
nodes = {node["id"]: node for node in document["nodes"]}
for name, (number, owner) in chores.items():
    node = nodes[f"chores.chore::{name}"]
    assert node["state"] != "referenced", node
    assert node["attributes"]["owner"] == owner, node
    assert [loc["line"] for loc in node["locations"]] == [number], node
edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
assert edges == {("waits_for", f"chores.chore::{a}", f"chores.chore::{b}") for a, b in waits}, edges
missing = [b for _, b in waits if b not in chores]
assert missing and all(nodes[f"chores.chore::{b}"]["state"] == "referenced" for b in missing)
PY

# A second run writes the same bytes, and the map holds to the map schema.
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
(cd "$site" && "$PERIPLUS" map --output "$work/again.json" --format json >/dev/null)
cmp "$work/map.json" "$work/again.json"
"$python" - "$work/map.json" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import json
import sys

from jsonschema import Draft202012Validator

Draft202012Validator(json.load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1])))
PY

# The same file with each line ending in a carriage return and a line feed gives the same map.
sed -i 's/$/\r/' "$site/lists/home.chores"
[ "$(grep -c $'\r$' "$site/lists/home.chores")" -eq "$(wc -l <"$site/lists/home.chores")" ]
(cd "$site" && "$PERIPLUS" map --output "$work/crlf.json" --format json >/dev/null)
cmp "$work/map.json" "$work/crlf.json"

# Bytes that are not UTF-8: the existing unreadable-source exit.
printf 'chore \xff by ana\n' >"$site/lists/bad.chores"
status=0
(cd "$site" && "$PERIPLUS" map --output "$work/bad.json" --format json >"$work/bad.report.json") \
    || status=$?
codes="$(python3 -c 'import json,sys; print(sorted({p["code"] for p in json.load(open(sys.argv[1]))["problems"]}))' "$work/bad.report.json")"
unreadable="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.SOURCE_UNREADABLE))')"
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/bad.json" ] && grep -q 'bad.chores' "$work/bad.report.json" \
    || { echo "a file that is not text was not refused: $status $codes"; exit 1; }
echo "text rules ok"
