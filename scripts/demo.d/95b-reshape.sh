#!/usr/bin/env bash
# A captured value reshaped, in a rutter written in the project's own packs folder for an invented
# format: a captured name with capitals and underscores gives an attribute in lower case with
# dashes, and the node's id, through a named value; an attribute from a template over values; an
# edge from an end built from a capture to this_node. Two planted cases: a text rule whose emits
# list an attribute before the node loads and runs, and an edge end whose capture is empty makes no
# edge and no node.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
pack="$site/.periplus/packs/grimoire@0.0.1"
mkdir -p "$pack/rules" "$site/book"
printf 'periplus_version: 0\npacks:\n  - grimoire@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: grimoire
version: 0.0.1
depends: []
folders:
  book: ./book
files:
  types:
    spells:
      endings: [spells]
      reader: text
YAML
cat >"$pack/rules/grimoire.yaml" <<'YAML'
node_types:
- name: grimoire.spell
  id_namespace: grimoire.spell
- name: grimoire.school
  id_namespace: grimoire.school
edge_kinds:
- kind: teaches
  from: grimoire.school
  to: grimoire.spell
rules:
- rule: spell
  reads: file
  in: [book]
  match: {file: '*', filetype: spells, text: '(?m)^spell (?<name>\w+) from (?<school>\w*)$'}
  values:
    slug:
      from: {capture: name}
      normalize: [{replace: '_', with: '-'}]
      case: lower
    label:
      template: '{slug}@{school}'
  id: {template: '{slug}'}
  emits:
  - attribute: {name: slug, from: {value: slug}}
  - attribute: {name: label, template: '[{label}]'}
  - node: {type: grimoire.spell}
  confidence: declared
- rule: school
  reads: file
  in: [book]
  match: {file: '*', filetype: spells, text: '(?m)^school (?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: grimoire.school}}]
  confidence: declared
- rule: school_teaches
  reads: file
  in: [book]
  match: {file: '*', filetype: spells, text: '(?m)^spell (?<name>\w+) from (?<school>\w*)$'}
  values:
    slug:
      from: {capture: name}
      normalize: [{replace: '_', with: '-'}]
      case: lower
  id: {template: '{slug}'}
  emits:
  - edge:
      kind: teaches
      from: {from: {capture: school}}
      to: this_node
  confidence: declared
YAML
# The last line's school is empty: a trailing space after "from".
printf 'school Flame\nspell Fire_Ball from Flame\nspell Ice_SHARD from Frost\nspell Lone_Word from \n' \
    >"$site/book/one.spells"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" "$site/book/one.spells" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert report["problems"] == [] and report["not_executed"] == [], report
nodes = {node["id"]: node for node in document["nodes"]}
edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
# Expected from the file: each "spell" line split on spaces, its name reshaped by hand.
spells = [line.split(" ") for line in open(sys.argv[3]).read().split("\n") if line.startswith("spell ")]
assert any(name != name.lower() and "_" in name for _, name, _, _ in spells), spells
for _, name, _, school in spells:
    slug = "".join("-" if c == "_" else c.lower() for c in name)
    node = nodes[f"grimoire.spell::{slug}"]
    assert node["attributes"] == {"slug": slug, "label": f"[{slug}@{school}]"}, node
    if school:
        assert ("teaches", f"grimoire.school::{school}", f"grimoire.spell::{slug}") in edges, name
    else:
        assert not [e for e in edges if e[2] == f"grimoire.spell::{slug}"], name
assert not [i for i in nodes if i.endswith("::")], sorted(nodes)
assert nodes["grimoire.school::Flame"]["state"] == "mapped"
assert nodes["grimoire.school::Frost"]["state"] == "referenced"
assert len(edges) == len([s for s in spells if s[3]]), edges
PY

# A value whose template names a value defined after it: the rule is not executed, and the reason
# names the later value.
later="$work/later"
mkdir -p "$later/.periplus/packs/grimoire@0.0.1/rules" "$later/book"
cp "$site/.periplus/settings.yml" "$later/.periplus/settings.yml"
cp "$pack/pack.yaml" "$later/.periplus/packs/grimoire@0.0.1/pack.yaml"
cat >"$later/.periplus/packs/grimoire@0.0.1/rules/grimoire.yaml" <<'YAML'
node_types:
- name: grimoire.spell
  id_namespace: grimoire.spell
rules:
- rule: spell
  reads: file
  in: [book]
  match: {file: '*', filetype: spells, text: '(?m)^spell (?<name>\w+)$'}
  values:
    early:
      template: '{tardy}!'
    tardy:
      from: {capture: name}
  id: {template: '{early}'}
  emits: [{node: {type: grimoire.spell}}]
  confidence: declared
YAML
printf 'spell Fire\n' >"$later/book/one.spells"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.RULE_NOT_EXECUTABLE))')"
status=0
(cd "$later" && "$PERIPLUS" map --output "$work/later.json" --format json >"$work/later.report.json") \
    || status=$?
[ "$status" -eq "$code" ] && [ ! -e "$work/later.json" ] \
    || { echo "later value: expected exit $code, got $status"; exit 1; }
python3 - "$work/later.report.json" "$code" "$later/.periplus/packs/grimoire@0.0.1/rules/grimoire.yaml" <<'PY'
import json
import re
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
# Expected from the planted rule: the first value, and the value its template names.
early, tardy = re.findall(r"(?m)^    (\w+):$", open(sys.argv[3]).read())
messages = [p["message"] for p in report["problems"] if p["code"] == code]
assert len(messages) == 1 and f"the value {early} names {tardy}," in messages[0], report["problems"]
PY
echo "reshape ok"
