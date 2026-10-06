#!/usr/bin/env bash
# where: [{has_child: <tree node type>}] on a tree declaration rule. A planted rutter has two rules
# on class_declaration: one for every class, and one with has_child: base_clause, which fires only
# on a class that extends another. A class that only implements an interface has no base_clause
# child, and a class whose only base_clause sits deeper, in an anonymous class in its method body,
# has none either. Both class rules hold a body, and a method rule's member_of edge must end at the
# node the rule that fired on the class made: kinds.derived for a class that extends, kinds.class
# for one that does not. The ids are exact, each rule's fires are counted, and the map and the
# report are byte-identical across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/kinds@0.0.1"
mkdir -p "$pack/rules" "$site/src"
printf 'periplus_version: 0\npacks:\n  - kinds@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: kinds
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./src/**
files:
  types:
    code:
      endings: [php]
      reader: tree
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
YAML
cat >"$pack/rules/kinds.yaml" <<'YAML'
node_types:
- name: kinds.class
  id_namespace: kinds.class
- name: kinds.derived
  parent: kinds.class
  id_namespace: kinds.derived
- name: kinds.method
  id_namespace: kinds.method
edge_kinds:
- kind: member_of
  from: kinds.method
  to: kinds.class
rules:
- rule: every_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: kinds.class}}]
  confidence: declared
- rule: derived_class
  reads: file
  in: [source]
  match:
    declaration: class_declaration
    name_child: name
    body_child: declaration_list
    filetype: code
    where: [{has_child: base_clause}]
  id: {from: qualified_name}
  emits: [{node: {type: kinds.derived}}]
  confidence: declared
- rule: method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: code}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}.{declared_name}'}
  emits: [{node: {type: kinds.method}}]
  confidence: declared
- rule: method_of
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: code}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}.{declared_name}'}
  emits: [{edge: {kind: member_of, from: this_node, to: enclosing_class}}]
  confidence: declared
YAML
cat >"$site/src/Shapes.php" <<'PHP'
<?php

namespace App;

class Base
{
}

class Kid extends Base
{
    public function run()
    {
    }
}

class Lone implements Shown
{
    public function run()
    {
    }
}

class Plain
{
    public function make()
    {
        return new class extends Base {};
    }
}

class Grand extends Kid implements Shown
{
}
PHP

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work/one.json" "$work/one-report.json" "$work/two-report.json" <<'PY'
import json
import sys

document, report, again = (json.load(open(path)) for path in sys.argv[1:4])
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
ids = sorted(n["id"] for n in document["nodes"])
assert ids == [
    "kinds.class::App\\Base",
    "kinds.class::App\\Grand",
    "kinds.class::App\\Kid",
    "kinds.class::App\\Lone",
    "kinds.class::App\\Plain",
    "kinds.derived::App\\Grand",
    "kinds.derived::App\\Kid",
    "kinds.method::App\\Kid.run",
    "kinds.method::App\\Lone.run",
    "kinds.method::App\\Plain.make",
], ids
edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
assert edges == [
    ("member_of", "kinds.method::App\\Kid.run", "kinds.derived::App\\Kid"),
    ("member_of", "kinds.method::App\\Lone.run", "kinds.class::App\\Lone"),
    ("member_of", "kinds.method::App\\Plain.make", "kinds.class::App\\Plain"),
], edges
fires = {(r["pack"], r["rule"]): r["fires"] for r in report["executed"]}
assert fires == {
    ("kinds", "every_class"): 5,
    ("kinds", "derived_class"): 2,
    ("kinds", "method"): 3,
    ("kinds", "method_of"): 3,
}, fires
assert not report["not_executed"], report["not_executed"]
assert not report["problems"], report["problems"]
PY
echo "has_child ok"
