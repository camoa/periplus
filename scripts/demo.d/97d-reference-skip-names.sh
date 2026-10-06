#!/usr/bin/env bash
# A reference rule's skip list. A planted pack reads PHP with its own grammar block, states each
# function and each call, and lists isset and empty under match.skip_names. A function holding
# isset($a), empty($b) and f() gives exactly one calls edge, to f; no node is named isset or empty,
# no skipped row names them, and the rule fires once. An isset($z) at file top level, outside any
# function, adds no skipped row either: the skip runs before the enclosing declaration is sought.
# The key is one the engine executes. The map validates and two runs are byte-identical.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"

"$python" -c 'from periplus.engine.packload import EXECUTED_KEYS as k; assert "file.rules.*.match.skip_names" in k'

site="$work/site"
pack="$site/.periplus/packs/skips@0.0.1"
mkdir -p "$pack/rules" "$site/src"
printf 'periplus_version: 0\npacks:\n  - skips@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: skips
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src/**
files:
  extensions: [php]
identity:
  qualified_name:
    parts: [namespace, declared_name]
    separator: "\\"
  namespace:
    declaration: namespace_definition
    name_child: name
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\"
  - bound_first_segment
  - prefix_with: namespace
YAML
cat >"$pack/rules/skips.yaml" <<'YAML'
node_types:
- name: skips.function
  id_namespace: skips.function
edge_kinds:
- kind: calls
  from: skips.function
  to: skips.function
rules:
- rule: function
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: skips.function}}]
  confidence: declared
- rule: call
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php, skip_names: [isset, empty]}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [skips.function], on_miss: unresolved}}}]
  confidence: declared
YAML
cat >"$site/src/run.php" <<'PHP'
<?php

namespace App;

function f()
{
}

function run($a, $b)
{
    isset($a);
    empty($b);
    f();
}

isset($z);
PHP
(cd "$site" && "$PERIPLUS" map --output "$work/one.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/two.json" >/dev/null)
cmp "$work/one.json" "$work/two.json"
"$python" - "$work/one.json" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import json
import sys

from jsonschema import Draft202012Validator

Draft202012Validator(json.load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1])))
PY
python3 - "$work/one.json" "$work/report.json" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
report = json.load(open(sys.argv[2]))
calls = [(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "calls"]
assert calls == [("skips.function::App\\run", "skips.function::App\\f")], calls
named = [n["id"] for n in document["nodes"] if n["id"].rsplit("\\", 1)[-1] in ("isset", "empty")]
assert not named, named
assert not report["skipped"], report["skipped"]
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("skips", "call")] == 1, fires
assert not report["not_executed"], report["not_executed"]
PY
echo "reference skip names ok"
