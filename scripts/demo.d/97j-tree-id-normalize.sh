#!/usr/bin/env bash
# A tree rule's id takes normalize, applied to the finished id. A planted rutter pins the php
# grammar. Its class rule's id is the qualified name with each backslash made a dot. Its method
# rule's id is '{enclosing_type}::{declared_name}{parameters}': the field parameters fills with the
# whole text of the parameter list, '(int $times, string $label)', and the normalize steps drop the
# variables, the space after each comma and each backslash, so the id is 'App.Thing::run(int,string)'.
# The contains edge from enclosing_class, the calls edge from enclosing_declaration and the marks
# edge from enclosing_method each start at those cleaned ids. The map exits 0 with no problems,
# nothing skipped, and is byte-identical across two runs, the report but for the map path it names.
# The same rutter without its normalize lines gives the raw text in each id.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/shapes@0.0.1"
mkdir -p "$pack/rules" "$site/src"
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
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\"
  - bound_first_segment
  - prefix_with: namespace
  attribute:
    node: attribute
    list: attribute_list
    arguments: parameters
    argument: argument
    argument_name: name
    literals: [string, encapsed_string]
    literal_content: string_content
YAML
cat >"$pack/rules/shapes.yaml" <<'YAML'
node_types:
- name: shapes.class
  id_namespace: shapes.class
- name: shapes.method
  id_namespace: shapes.method
- name: shapes.function
  id_namespace: shapes.function
- name: shapes.mark
  id_namespace: shapes.mark
edge_kinds:
- kind: contains
  from: shapes.class
  to: shapes.method
- kind: calls
  from: shapes.method
  to: shapes.function
- kind: marks
  from: shapes.method
  to: shapes.mark
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id:
    from: qualified_name
    normalize: [{replace: '\\', with: '.'}]
  emits: [{node: {type: shapes.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: &method_id
    from: [enclosing_type, declared_name, parameters]
    template: '{enclosing_type}::{declared_name}{parameters}'
    normalize: [{replace: ' ?\$\w+', with: ''}, {replace: ', ', with: ','}, {replace: '\\', with: '.'}]
  emits: [{node: {type: shapes.method}}]
  confidence: declared
- rule: contains_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: *method_id
  emits: [{edge: {kind: contains, from: enclosing_class, to: this_node}}]
  confidence: declared
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: shapes.function}}]
  confidence: declared
- rule: calls_function
  reads: file
  in: [source]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [shapes.function], on_miss: unresolved}}}]
  confidence: declared
- rule: marks_from_attribute
  reads: file
  in: [source]
  match: {attribute: App\Mark, filetype: php, where: [{applies_to: method_declaration}]}
  emits: [{edge: {kind: marks, from: enclosing_method, to: {from: {attribute_argument: '0'}}}}]
  confidence: declared
YAML
cat >"$site/src/Thing.php" <<'PHP'
<?php

namespace App;

class Thing
{
    #[Mark('tick')]
    public function run(int $times, string $label): void
    {
        helper();
    }
}

function helper()
{
}
PHP

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

sed -i '/normalize:/d' "$pack/rules/shapes.yaml"
[ "$(grep -c normalize "$pack/rules/shapes.yaml" || true)" = 0 ]
(cd "$site" && "$PERIPLUS" map --output "$work/raw.json" --format json >"$work/raw-report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]


def load(name):
    return json.load(open(os.path.join(work, name)))


def shape(document):
    # Only the attribute's argument is a node no rule declares; an edge end left raw would be another.
    referenced = [n["id"] for n in document["nodes"] if n["state"] == "referenced"]
    assert referenced == ["shapes.mark::tick"], referenced
    nodes = sorted(n["id"] for n in document["nodes"])
    edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
    return nodes, edges


report, again, raw_report = load("one-report.json"), load("two-report.json"), load("raw-report.json")
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
for one in (report, raw_report):
    assert not one["problems"], one["problems"]
    assert not one["skipped"], one["skipped"]

nodes, edges = shape(load("one.json"))
assert nodes == [
    "shapes.class::App.Thing",
    "shapes.function::App\\helper",
    "shapes.mark::tick",
    "shapes.method::App.Thing::run(int,string)",
], nodes
assert edges == [
    ("calls", "shapes.method::App.Thing::run(int,string)", "shapes.function::App\\helper"),
    ("contains", "shapes.class::App.Thing", "shapes.method::App.Thing::run(int,string)"),
    ("marks", "shapes.method::App.Thing::run(int,string)", "shapes.mark::tick"),
], edges

nodes, edges = shape(load("raw.json"))
method = "shapes.method::App\\Thing::run(int $times, string $label)"
assert nodes == [
    "shapes.class::App\\Thing",
    "shapes.function::App\\helper",
    "shapes.mark::tick",
    method,
], nodes
assert edges == [
    ("calls", method, "shapes.function::App\\helper"),
    ("contains", "shapes.class::App\\Thing", method),
    ("marks", method, "shapes.mark::tick"),
], edges
PY
echo "tree id normalize ok"
