#!/usr/bin/env bash
# A tree declaration rule's id takes a pattern. A planted rutter pins the php grammar and reads
# .module files, each with the path value module, its name. Its hook rule's id is the capture hook
# of '^{module}_(?<hook>\w+)$' over the declared name, {module} filled with the path value as
# literal text. In mymod.module, mymod_cron gives the one hook node, hooks.hook::cron; helper,
# othermod_cron and build_callback do not fit, so they make no node, no skipped row and no fire.
# Its callback rule's pattern has no template and no value: it only filters, so build_callback
# keeps its name as its id. periplus validate and periplus spec accept the rutter.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/hooks@0.0.1"
mkdir -p "$pack/rules" "$site/src"
printf 'periplus_version: 0\npacks:\n  - hooks@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: hooks
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
    module_file:
      endings: [module]
      reader: tree
      path_values:
        module:
          pattern: '^(?:.*/)?(?<name>[^/]+)\.module$'
          template: '{name}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
YAML
cat >"$pack/rules/hooks.yaml" <<'YAML'
node_types:
- name: hooks.hook
  id_namespace: hooks.hook
- name: hooks.callback
  id_namespace: hooks.callback
rules:
- rule: find_hook
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: module_file}
  id: {from: declared_name, pattern: '^{module}_(?<hook>\w+)$', template: '{hook}'}
  emits: [{node: {type: hooks.hook}}]
  confidence: declared
- rule: find_callback
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: module_file}
  id: {from: declared_name, pattern: '_callback$'}
  emits: [{node: {type: hooks.callback}}]
  confidence: declared
YAML
main="$site/src/mymod.module"
cat >"$main" <<'PHP'
<?php

function mymod_cron()
{
}

function helper()
{
}

function othermod_cron()
{
}

function build_callback()
{
}
PHP

(cd "$site" && "$PERIPLUS" validate hooks >/dev/null && "$PERIPLUS" spec hooks >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$main" <<'PY'
import json
import os
import sys

work, main = sys.argv[1], sys.argv[2]
lines = open(main).read().splitlines()
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]

found = {(node["id"], place["line"]) for node in document["nodes"] for place in node["locations"]}
cron = next(n for n, text in enumerate(lines, 1) if text == "function mymod_cron()")
callback = next(n for n, text in enumerate(lines, 1) if text == "function build_callback()")
expected = {("hooks.hook::cron", cron), ("hooks.callback::build_callback", callback)}
assert found == expected, sorted(found ^ expected)
assert document["edges"] == [], document["edges"]
assert report["skipped"] == [], report["skipped"]
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("hooks", "find_hook")] == 1, fires
assert fires[("hooks", "find_callback")] == 1, fires
PY
echo "id pattern ok"
