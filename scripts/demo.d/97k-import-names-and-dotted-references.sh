#!/usr/bin/env bash
# Import names from the whole path, and dotted references that end only on a bound name. A planted
# rutter pins the php grammar and reads PHP the way a language with slashed import paths reads:
# each file's namespace is its folder, from a path value, and an import is a call such as
# import('App/Util/Strings_v2') or import(W: 'App/Text/Words'). Its import rule takes the argument
# as the import's own node and the string as the clause, so the alias W is a field of the import's
# node and not of the clause. bind.name tries the alias, then path, the whole written path, and
# bind.normalize cuts that to its last slashed segment less a version suffix, so the path, written
# with another separator than the grammar's backslash, binds Strings. The alias _ is listed in
# unbound_aliases and binds no name. The grammar resolves bound_first_segment, then
# prefix_bare_with the namespace. The call rule sets whole_written, and lists the chained call's
# node type as a written name so that only whole_written refuses it. So Strings\up() and W\tally()
# end on the functions under the full paths and local() on the caller's namespace; Missing\thing(),
# _\hide() and Hidden\hide() have no step that holds, and Strings::make()() is not wholly written:
# each adds no edge, no node and no fire, and is listed under skipped with its reason. The map and
# the report are byte-identical across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/porter@0.0.1"
mkdir -p "$pack/rules" "$pack/imports" "$site/src/App/Main" "$site/src/App/Util/Strings_v2" \
    "$site/src/App/Text/Words" "$site/src/App/Hidden"
printf 'periplus_version: 0\npacks:\n  - porter@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: porter
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
      path_values:
        pkg:
          pattern: '^src/(?<dir>.+)/[^/]+$'
          template: '{dir}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {path_value: pkg}
  written_names: [name, qualified_name, namespace_name, string_content, scoped_call_expression]
  resolve:
  - bound_first_segment
  - prefix_bare_with: namespace
YAML
cat >"$pack/imports/imports.yaml" <<'YAML'
imports:
- ast: argument
  clause: string
  facts: {alias: name}
  bind:
    name: [alias, path]
    normalize: [{replace: '^.*/', with: ''}, {replace: '_v\d+$', with: ''}]
    unbound_aliases: [_]
YAML
cat >"$pack/rules/porter.yaml" <<'YAML'
node_types:
- name: porter.function
  id_namespace: porter.function
edge_kinds:
- kind: calls
  from: porter.function
  to: porter.function
rules:
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: porter.function}}]
  confidence: declared
- rule: call
  reads: file
  in: [source]
  match:
    reference: function_call_expression
    name_child: function
    filetype: code
    whole_written: true
    skip_names: [import]
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [porter.function], on_miss: unresolved}}}]
  confidence: declared
YAML
printf '<?php\n\nfunction up()\n{\n}\n' >"$site/src/App/Util/Strings_v2/lib.php"
printf '<?php\n\nfunction tally()\n{\n}\n' >"$site/src/App/Text/Words/lib.php"
printf '<?php\n\nfunction hide()\n{\n}\n' >"$site/src/App/Hidden/lib.php"
main="$site/src/App/Main/main.php"
cat >"$main" <<'PHP'
<?php

import('App/Util/Strings_v2');
import(W: 'App/Text/Words');
import(_: 'App/Hidden');

function run()
{
    Strings\up();
    W\tally();
    local();
    Missing\thing();
    Strings::make()();
    _\hide();
    Hidden\hide();
}

function local()
{
}
PHP

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$main" <<'PY'
import json
import os
import sys

work, main = sys.argv[1], sys.argv[2]
lines = open(main).read().splitlines()


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(text):
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]

nodes = {node["id"]: node["state"] for node in document["nodes"]}
assert nodes == {
    f"porter.function::{name}": "mapped"
    for name in (
        "App/Main\\run", "App/Main\\local", "App/Util/Strings_v2\\up", "App/Text/Words\\tally",
        "App/Hidden\\hide",
    )
}, nodes
run = "porter.function::App/Main\\run"
found = {
    (edge["kind"], edge["from"], edge["to"], place["line"])
    for edge in document["edges"]
    for place in edge["locations"]
}
expected = {
    ("calls", run, "porter.function::App/Util/Strings_v2\\up", line("Strings\\up();")),
    ("calls", run, "porter.function::App/Text/Words\\tally", line("W\\tally();")),
    ("calls", run, "porter.function::App/Main\\local", line("local();")),
}
assert found == expected, sorted(found ^ expected)

skipped = sorted((row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"])
file = "src/App/Main/main.php"
none_holds = "no resolution step holds for function"
assert skipped == sorted([
    (file, line("Missing\\thing();"), "call", none_holds),
    (file, line("Strings::make()();"), "call", "function is not a written name"),
    (file, line("_\\hide();"), "call", none_holds),
    (file, line("Hidden\\hide();"), "call", none_holds),
]), skipped
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("porter", "call")] == 3, fires
PY
echo "import names and dotted references ok"
