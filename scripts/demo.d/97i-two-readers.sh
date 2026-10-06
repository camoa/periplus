#!/usr/bin/env bash
# Two readers on one ending. A planted text rutter, notes, declares its own file type php_notes on
# the ending php, read as text, and makes one node per '// @owner <name>' line, its id from its own
# path value dir. Loaded beside php_basic, which reads php as a tree, both packs' rules run: the
# joint map holds php_basic's map alone, node for node and edge for edge, plus one notes node per
# owner line at that line, and the joint map is byte-identical across two runs. Each rule reads with
# its own file type's path values and sections: beside a planted tree rutter, modules, whose type
# code also declares a path value dir and a section over block comments, the class ids take code's
# dir, the notes ids take php_notes' dir, and an owner line inside a block comment is still a note.
# A text type on yml, the ending of yaml_basic's short-form data type, loads too, and a data rule
# and a text rule on it both fire. A text rule on code, a type read only as a tree, is not executed. Two types of one ending read
# the same way are still refused with exit 19, naming the ending, the reader and both types.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
notes="$site/.periplus/packs/notes@0.0.1"
modules="$site/.periplus/packs/modules@0.0.1"
mkdir -p "$notes/rules" "$modules/rules" "$site/src/App" "$site/src/Lib"
manifest() {
    cat >"$notes/pack.yaml" <<YAML
pack: notes
version: 0.0.1
depends: []
folders:
  notes: ./**
files:
  types:
    php_notes:
      endings: [php]
      reader: text
      path_values:
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: 'notes:{d}'
$1
YAML
}
manifest ''
cat >"$notes/rules/notes.yaml" <<'YAML'
node_types:
- name: notes.owner
  id_namespace: notes.owner
rules:
- rule: owner
  reads: file
  in: [notes]
  match: {file: '*', filetype: php_notes, text: '(?m)^[ \t]*// @owner (?<owner>\w+)[ \t]*$'}
  id: {template: '{dir}/{owner}'}
  emits: [{node: {type: notes.owner}}]
  confidence: declared
YAML
cat >"$modules/pack.yaml" <<'YAML'
pack: modules
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: '{d}'
      sections:
      - {name: block, open: '/\*', close: '\*/'}
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name]
YAML
cat >"$modules/rules/modules.yaml" <<'YAML'
node_types:
- name: modules.class
  id_namespace: modules.class
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [dir, declared_name], template: '{dir}.{declared_name}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
YAML
cat >"$site/src/App/Main.php" <<'EOF'
<?php

namespace App;

// @owner ana
class Main
{
    // @owner ben
    public function run()
    {
    }
}
EOF
cat >"$site/src/Lib/Util.php" <<'EOF'
<?php

namespace App\Lib;

/*
// @owner carl
*/
class Util extends \App\Main
{
}
EOF

map() {
    printf 'periplus_version: 0\npacks:\n%s' "$1" >"$site/.periplus/settings.yml"
    (cd "$site" && "$PERIPLUS" map --output "$work/$2.json" --format json >"$work/$2-report.json")
}
map $'  - php_basic@0.1.0\n' alone
map $'  - php_basic@0.1.0\n  - notes@0.0.1\n' one
map $'  - php_basic@0.1.0\n  - notes@0.0.1\n' two
cmp "$work/one.json" "$work/two.json"
map $'  - modules@0.0.1\n  - notes@0.0.1\n' own
ledger="$site/.periplus/packs/ledger@0.0.1"
mkdir -p "$ledger/rules" "$site/stock"
cat >"$ledger/pack.yaml" <<'YAML'
pack: ledger
version: 0.0.1
depends: [yaml_basic]
folders:
  stock: ./stock
files:
  types:
    yml_notes:
      endings: [yml]
      reader: text
YAML
cat >"$ledger/rules/ledger.yaml" <<'YAML'
node_types:
- name: ledger.item
  id_namespace: ledger.item
- name: ledger.owner
  id_namespace: ledger.owner
rules:
- rule: item
  reads: file
  in: [stock]
  match: {file: '*', filetype: yaml, each: '*'}
  id: {from: key}
  emits: [{node: {type: ledger.item}}]
  confidence: declared
- rule: owner
  reads: file
  in: [stock]
  match: {file: '*', filetype: yml_notes, text: '(?m)^# @owner (?<owner>\w+)$'}
  id: {template: '{owner}'}
  emits: [{node: {type: ledger.owner}}]
  confidence: declared
YAML
printf '# @owner dora\nnails: 3\nscrews: 5\n' >"$site/stock/shelf.yml"
map $'  - yaml_basic@0.1.0\n  - ledger@0.0.1\n' ledger
cat >>"$modules/rules/modules.yaml" <<'YAML'
- rule: owner_as_text
  reads: file
  in: [source]
  match: {file: '*', filetype: code, text: '(?m)^[ \t]*// @owner (?<owner>\w+)'}
  id: {template: '{owner}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
YAML
limit=0
map $'  - modules@0.0.1\n  - notes@0.0.1\n' limit || limit=$?

manifest $'    php_more:\n      endings: [php]\n      reader: text'
code=0
map $'  - php_basic@0.1.0\n  - notes@0.0.1\n' same || code=$?

python3 - "$work" "$code" "$site" "$limit" <<'PY'
import json
import os
import re
import sys

work, code, site, limit = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])


def load(name):
    return json.load(open(os.path.join(work, name)))


# Expected from the files: each owner line, its folder and its line number.
expected = {}
for folder in ("src/App", "src/Lib"):
    for name in sorted(os.listdir(os.path.join(site, folder))):
        lines = open(os.path.join(site, folder, name)).read().split("\n")
        for number, line in enumerate(lines, 1):
            if m := re.fullmatch(r"\s*// @owner (\w+)\s*", line):
                expected[f"notes.owner::notes:{folder}/{m[1]}"] = (f"{folder}/{name}", number)
assert len(expected) == 3, expected


def notes(document):
    found = {n["id"]: n for n in document["nodes"] if n["type"] == "notes.owner"}
    return {i: [(loc["file"], loc["line"]) for loc in n["locations"]] for i, n in found.items()}


alone, joint = load("alone.json"), load("one.json")
assert alone["nodes"] and alone["edges"], alone
assert [n for n in joint["nodes"] if n["type"] != "notes.owner"] == alone["nodes"]
assert joint["edges"] == alone["edges"]
assert notes(joint) == {i: [where] for i, where in expected.items()}, notes(joint)

report, single = load("one-report.json"), load("alone-report.json")
assert report["not_executed"] == [] and report["problems"] == [], report
fires = {(r["pack"], r["rule"]): r["fires"] for r in report["executed"]}
assert fires[("notes", "owner")] == 3 and fires[("php_basic", "find_class")] == 2, fires
assert {k: v for k, v in fires.items() if k[0] == "php_basic"} == {
    (r["pack"], r["rule"]): r["fires"] for r in single["executed"]
}

own, own_report = load("own.json"), load("own-report.json")
classes = sorted(n["id"] for n in own["nodes"] if n["type"] == "modules.class")
assert classes == ["modules.class::src/App.Main", "modules.class::src/Lib.Util"], classes
assert notes(own) == {i: [where] for i, where in expected.items()}, notes(own)
assert own_report["not_executed"] == [] and own_report["problems"] == [], own_report

# A data type and a text type on one ending: both rules run.
ledger, ledger_report = load("ledger.json"), load("ledger-report.json")
assert ledger_report["not_executed"] == [] and ledger_report["problems"] == [], ledger_report
fires = {(r["pack"], r["rule"]): r["fires"] for r in ledger_report["executed"]}
assert fires == {("ledger", "item"): 2, ("ledger", "owner"): 1}, fires
assert sorted(n["id"] for n in ledger["nodes"] if n["type"].startswith("ledger.")) == [
    "ledger.item::nails", "ledger.item::screws", "ledger.owner::dora"
], ledger["nodes"]

# One rule, one reader: a text rule on the tree type code is not executed, and refuses the map.
assert limit == 26, limit
assert not os.path.exists(os.path.join(work, "limit.json"))
messages = [p["message"] for p in load("limit-report.json")["problems"]]
assert messages == [
    "modules/rules/modules.yaml: the rule owner_as_text cannot be executed: the rule reads text, "
    "and the file type code is read as tree"
], messages

assert code == 19, code
assert not os.path.exists(os.path.join(work, "same.json"))
messages = [p["message"] for p in load("same-report.json")["problems"]]
assert messages == [
    "the file ending php is claimed for different file types read as text: "
    "php_more in notes/pack.yaml; php_notes in notes/pack.yaml"
], messages
PY
echo "two readers ok"
