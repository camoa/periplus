#!/usr/bin/env bash
# An edge end that names nothing mapped, in a rutter written in the project's own packs folder for
# an invented format: declared on_miss unresolved it is a node in state unresolved recording the
# rule, the name searched for and what was found; found, it is an ordinary edge; without on_miss it
# is a node in state referenced, as before; reached also by an edge without on_miss it stays
# unresolved. The map validates against map.schema.json, and two runs are byte-identical.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
pack="$site/.periplus/packs/bench@0.0.1"
mkdir -p "$pack/rules" "$site/plans"
printf 'periplus_version: 0\npacks:\n  - bench@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: bench
version: 0.0.1
depends: []
folders:
  plans: ./plans
files:
  types:
    bench:
      endings: [bench]
      reader: text
YAML
cat >"$pack/rules/bench.yaml" <<'YAML'
node_types:
- name: bench.tool
  id_namespace: bench.tool
- name: bench.task
  id_namespace: bench.task
- name: bench.note
  id_namespace: bench.note
edge_kinds:
- kind: uses
  from: bench.task
  to: bench.tool
- kind: mentions
  from: bench.note
  to: bench.tool
rules:
- rule: tool
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^tool (?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: bench.tool}}]
  confidence: declared
- rule: task
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^task (?<name>\w+) uses (?<tool>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: bench.task}}]
  confidence: declared
- rule: task_uses
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^task (?<name>\w+) uses (?<tool>\w+)$'}
  id: {from: {capture: name}}
  emits:
  - edge:
      kind: uses
      from: this_node
      to: {from: {capture: tool}, on_miss: unresolved}
  confidence: declared
- rule: note
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^note (?<tool>\w+)$'}
  id: {from: {capture: tool}}
  emits: [{node: {type: bench.note}}]
  confidence: declared
- rule: note_mentions
  reads: file
  in: [plans]
  match: {file: '*', filetype: bench, text: '(?m)^note (?<tool>\w+)$'}
  id: {from: {capture: tool}}
  emits:
  - edge:
      kind: mentions
      from: this_node
      to: {from: {capture: tool}}
  confidence: declared
YAML
cat >"$site/plans/shed.bench" <<'TXT'
tool hammer
task build uses hammer
task paint uses brush
note brush
note chisel
TXT
(cd "$site" && "$PERIPLUS" map --output "$work/one.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/two.json" >/dev/null)
cmp "$work/one.json" "$work/two.json"
"$python" - "$work/one.json" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import json
import sys

from jsonschema import Draft202012Validator

Draft202012Validator(json.load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1])))
PY
python3 - "$work/one.json" "$site/plans/shed.bench" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
nodes = {node["id"]: node for node in document["nodes"]}
edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
# Expected from the file: each line split by spaces.
lines = [line.split() for line in open(sys.argv[2]).read().split("\n") if line]
tools = {words[1] for words in lines if words[0] == "tool"}
used = {words[3] for words in lines if words[0] == "task"}
noted = {words[1] for words in lines if words[0] == "note"}
assert used - tools and used & tools and noted - used - tools, (tools, used, noted)
for words in lines:
    if words[0] == "task":
        assert ("uses", f"bench.task::{words[1]}", f"bench.tool::{words[3]}") in edges, words
for tool in tools:
    assert nodes[f"bench.tool::{tool}"]["state"] == "mapped", tool
    assert "unresolved_detail" not in nodes[f"bench.tool::{tool}"]
for tool in used - tools:
    node = nodes[f"bench.tool::{tool}"]
    assert node["state"] == "unresolved" and node["locations"] == [], node
    assert node["type"] == "bench.tool", node
    assert node["unresolved_detail"] == {
        "rule": "bench/task_uses",
        "searched_for": tool,
        "found": "no mapped node of this name",
        "types_tried": ["bench.tool"],
    }, node
    # A rule without on_miss reaches it too, and it stays unresolved.
    assert ("mentions", f"bench.note::{tool}", f"bench.tool::{tool}") in edges, tool
for tool in noted - used - tools:
    node = nodes[f"bench.tool::{tool}"]
    assert node["state"] == "referenced" and "unresolved_detail" not in node, node
assert document["counts"]["nodes_by_state"]["unresolved"] == len(used - tools)
PY
echo "unresolved ends ok"
