#!/usr/bin/env bash
# A tree rule's id from a path value and from a field of the matched node. A planted rutter pins the
# php grammar and gives its file type the path value dir, the folder under src/. Its class rule's
# id is '{dir}.{declared_name}': two classes named Thing in two folders are two nodes, and a file
# outside src/<dir>/ gives no node and one skipped row, though it holds two classes. Its function
# rule's id names the fields name and return_type: a function without a return type gives no node
# and one skipped row. The grammar's full name is built from the parts [dir, declared_name], so a
# rule whose id is the qualified name gives one id per class in a folder and, for the file outside,
# one skipped row naming dir. The map and the report are byte-identical across two runs. With the
# field return_type misspelt in the function rule's id, the map is refused at load with exit 19,
# naming the rule, the template and the name.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/shapes@0.0.1"
mkdir -p "$pack/rules" "$site/src/alpha" "$site/src/beta"
printf 'periplus_version: 0\npacks:\n  - shapes@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: shapes
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
          pattern: '^src/(?<d>[^/]+)/[^/]+$'
          template: '{d}'
identity:
  qualified_name: {parts: [dir, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
YAML
cat >"$pack/rules/shapes.yaml" <<'YAML'
node_types:
- name: shapes.class
  id_namespace: shapes.class
- name: shapes.function
  id_namespace: shapes.function
- name: shapes.qualified
  id_namespace: shapes.qualified
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [dir, declared_name], template: '{dir}.{declared_name}'}
  emits: [{node: {type: shapes.class}}]
  confidence: declared
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, filetype: code}
  id: {from: [dir, name, return_type], template: '{dir}.{name}:{return_type}'}
  emits: [{node: {type: shapes.function}}]
  confidence: declared
- rule: find_qualified
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: shapes.qualified}}]
  confidence: declared
YAML
cat >"$site/src/alpha/Thing.php" <<'PHP'
<?php

class Thing extends Base
{
}

class Other
{
}

function count(): int
{
}

function loose()
{
}
PHP
cat >"$site/src/beta/Thing.php" <<'PHP'
<?php

class Thing
{
}
PHP
cat >"$site/Root.php" <<'PHP'
<?php

class Loose
{
}

class Lost
{
}
PHP

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

sed -i 's/return_type/retrun_type/g' "$pack/rules/shapes.yaml"
[ "$(grep -c retrun_type "$pack/rules/shapes.yaml")" = 1 ]
code=0
(cd "$site" && "$PERIPLUS" map --output "$work/typo.json" --format json >"$work/typo-report.json") \
    || code=$?

python3 - "$work/one.json" "$work/one-report.json" "$work/two-report.json" "$work" "$code" <<'PY'
import json
import os
import sys

document, report, again = (json.load(open(path)) for path in sys.argv[1:4])
work, code = sys.argv[4], int(sys.argv[5])
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
nodes = {n["id"]: n for n in document["nodes"]}
assert sorted(nodes) == [
    "shapes.class::alpha.Other",
    "shapes.class::alpha.Thing",
    "shapes.class::beta.Thing",
    "shapes.function::alpha.count:int",
    "shapes.qualified::alpha\\Other",
    "shapes.qualified::alpha\\Thing",
    "shapes.qualified::beta\\Thing",
], sorted(nodes)
assert [loc["file"] for loc in nodes["shapes.class::alpha.Thing"]["locations"]] == [
    "src/alpha/Thing.php"
], nodes["shapes.class::alpha.Thing"]
assert [loc["file"] for loc in nodes["shapes.class::beta.Thing"]["locations"]] == [
    "src/beta/Thing.php"
], nodes["shapes.class::beta.Thing"]
assert report["skipped"] == [
    {"file": "Root.php", "line": 3, "rule": "find_class", "reason": "the id source dir is absent"},
    {
        "file": "Root.php",
        "line": 3,
        "rule": "find_qualified",
        "reason": "the id source dir is absent",
    },
    {
        "file": "src/alpha/Thing.php",
        "line": 15,
        "rule": "find_function",
        "reason": "the id source return_type is absent",
    },
], report["skipped"]
assert not report["problems"], report["problems"]

assert code == 19, code
assert not os.path.exists(os.path.join(work, "typo.json"))
messages = [p["message"] for p in json.load(open(os.path.join(work, "typo-report.json")))["problems"]]
assert messages == [
    "shapes/rules/shapes.yaml: the rule find_function has the id template "
    "{dir}.{name}:{retrun_type}, which names retrun_type, no field of the php grammar, path value "
    "or settings value"
], messages
PY
echo "tree id sources ok"
