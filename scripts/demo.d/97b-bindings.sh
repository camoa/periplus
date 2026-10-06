#!/usr/bin/env bash
# Names bound by a text rule and resolved by declared steps, in a rutter written in the project's
# own packs folder for an invented format. Each call's end is the meaning its written name has: a
# name with the full prefix is full without it; a name whose first segment an import binds, under
# its alias, under its last segment, or as a member of a grouped import, takes the bound path in
# place of that segment; any other name takes the module the file's path gives. A binding rule's
# fires are the bindings it gave, and a later binding of a name wins. Expectations are computed
# from the files; the map validates and two runs are byte-identical.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
pack="$site/.periplus/packs/mods@0.0.1"
mkdir -p "$pack/rules" "$site/src/app" "$site/src/tools"
printf 'periplus_version: 0\npacks:\n  - mods@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: mods
version: 0.0.1
depends: []
folders:
  src: ./src/**
files:
  types:
    mod:
      endings: [mod]
      reader: text
      path_values:
        module:
          pattern: '(?<package>\w+)/(?<file>\w+)\.mod$'
          template: '{package}.{file}'
      resolve:
      - full_if_prefixed: '~'
      - bound_first_segment
      - prefix_with: module
      separator: '.'
YAML
cat >"$pack/rules/mods.yaml" <<'YAML'
node_types:
- name: mods.module
  id_namespace: mods.module
- name: mods.function
  id_namespace: mods.function
edge_kinds:
- kind: calls
  from: mods.module
  to: mods.function
rules:
- rule: module
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '\A'}
  id: {template: '{module}'}
  emits: [{node: {type: mods.module}}]
  confidence: declared
- rule: function
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^def (?<name>\w+)$'}
  id: {from: {capture: name}, resolve: [{prefix_with: module}], separator: '.'}
  emits: [{node: {type: mods.function}}]
  confidence: declared
- rule: call
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^call (?<name>[~\w.]+)$'}
  id: {template: '{module}'}
  emits:
  - edge: {kind: calls, from: this_node, to: {from: {capture: name}, on_miss: unresolved}}
  confidence: declared
- rule: call_as_written
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^extern (?<name>[\w.]+)$'}
  id: {template: '{module}'}
  emits:
  - edge:
      kind: calls
      from: this_node
      to: {from: {capture: name}, resolve: [as_written]}
  confidence: declared
- rule: import_alias
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^import (?<path>[\w.]+) as (?<alias>\w+)$'}
  emits: [{binding: {name: '{alias}', target: '{path}'}}]
  confidence: declared
- rule: import_plain
  reads: file
  in: [src]
  match: {file: '*', filetype: mod, text: '(?m)^import (?<path>(?:\w+\.)*(?<last>\w+))$'}
  emits: [{binding: {name: '{last}', target: '{path}'}}]
  confidence: declared
- rule: import_group
  reads: file
  in: [src]
  match:
    file: '*'
    filetype: mod
    text: '(?m)(?<member>\b\w+)(?=(?:, \w+)*\} from (?<prefix>[\w.]+)$)'
  emits: [{binding: {name: '{member}', target: '{prefix}.{member}'}}]
  confidence: declared
YAML
cat >"$site/src/tools/paint.mod" <<'TXT'
def brush
def roller
TXT
cat >"$site/src/app/shop.mod" <<'TXT'
import tools.hammer as h
import tools.file
import tools.saw
import {brush, roller} from tools.paint
import tools.drill as saw
def local
call h.strike
call file.read
call saw.cut
call brush
call roller.spin
call ~lib.glue
call local
call nowhere.thing
extern h.strike
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
python3 - "$work/one.json" "$work/report.json" "$site/src/app/shop.mod" <<'PY'
import json
import re
import sys

document = json.load(open(sys.argv[1]))
report = json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()
module = "app.shop"

# The bindings, read from the file in order; a later one of a name wins.
bound, counts = {}, {"import_alias": 0, "import_plain": 0, "import_group": 0}
for line in lines:
    words = line.split()
    if line.startswith("import {"):
        members, prefix = re.fullmatch(r"import \{(.*)\} from (\S+)", line).groups()
        for member in members.split(", "):
            bound[member] = f"{prefix}.{member}"
            counts["import_group"] += 1
    elif words[0] == "import" and len(words) == 4:
        bound[words[3]] = words[1]
        counts["import_alias"] += 1
    elif words[0] == "import":
        bound[words[1].rsplit(".", 1)[-1]] = words[1]
        counts["import_plain"] += 1
assert bound["saw"] == "tools.drill", bound


def meaning(name):
    if name.startswith("~"):
        return name[1:]
    first, _, rest = name.partition(".")
    if first in bound:
        return ".".join(p for p in (bound[first], rest) if p)
    return f"{module}.{name}"


calls = [line.split()[1] for line in lines if line.startswith("call ")]
# Each call's end, keyed by the line it is written on, so two swapped ends cannot pass.
expected = set()
for number, line in enumerate(lines, 1):
    if line.startswith(("call ", "extern ")):
        name = line.split()[1]
        expected.add((number, meaning(name) if line.startswith("call ") else name))
expected = {(number, f"mods.function::{name}") for number, name in expected}
found = {
    (place["line"], edge["to"])
    for edge in document["edges"]
    if edge["kind"] == "calls" and edge["from"] == f"mods.module::{module}"
    for place in edge["locations"]
    if place["file"] == "src/app/shop.mod"
}
assert found == expected, sorted(found ^ expected)
# Each case the steps cover gives its meaning.
for written, full in {
    "h.strike": "tools.hammer.strike",
    "file.read": "tools.file.read",
    "saw.cut": "tools.drill.cut",
    "brush": "tools.paint.brush",
    "roller.spin": "tools.paint.roller.spin",
    "~lib.glue": "lib.glue",
    "local": "app.shop.local",
    "nowhere.thing": "app.shop.nowhere.thing",
}.items():
    assert meaning(written) == full and written in calls, written
nodes = {node["id"]: node for node in document["nodes"]}
assert nodes["mods.function::app.shop.local"]["state"] == "mapped"
assert nodes["mods.function::tools.paint.brush"]["state"] == "mapped"
assert nodes["mods.function::lib.glue"]["state"] == "unresolved"
assert nodes["mods.function::h.strike"]["state"] == "referenced"
fires = {row["rule"]: row["fires"] for row in report["executed"]}
for rule, count in counts.items():
    assert fires[rule] == count and count, (rule, fires)
PY
echo "bindings ok"
