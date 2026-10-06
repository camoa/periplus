#!/usr/bin/env bash
# An edge end {declared: <type>} takes the id of the node of that type another rule declares at
# the same match. A planted rutter tagger depends on php_basic and reads .module files. Its rule
# task declares tag.task from a function name that fits '^mymod_(?<task>.+)$'; its rule runs, on
# every function, emits runs_task from {declared: php.function}, which php_basic's find_function
# declares, to {declared: tag.task}. In mymod.module, mymod_cron gives the one edge
# php.function::mymod_cron -> tag.task::cron; helper declares no task, so it makes no edge and
# leaves one skipped row that names the end. periplus validate and periplus spec accept the rutter.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/tagger@0.0.1"
mkdir -p "$pack/rules"
printf 'periplus_version: 0\npacks:\n  - tagger@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: tagger
version: 0.0.1
depends: [php_basic]
folders:
  code: ./**
files:
  extends: php_basic
  add_extensions: [module]
YAML
cat >"$pack/rules/tag.yaml" <<'YAML'
node_types:
- name: tag.task
  id_namespace: tag.task
edge_kinds:
- kind: runs_task
  from: php.function
  to: tag.task
rules:
- rule: task
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^mymod_(?<task>.+)$', template: '{task}'}
  emits: [{node: {type: tag.task}}]
  confidence: declared
- rule: runs
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  emits: [{edge: {kind: runs_task, from: {declared: php.function}, to: {declared: tag.task}}}]
  confidence: declared
YAML
main="$site/mymod.module"
cat >"$main" <<'PHP'
<?php

function mymod_cron()
{
}

function helper()
{
}
PHP

(cd "$site" && "$PERIPLUS" validate tagger >/dev/null && "$PERIPLUS" spec tagger >/dev/null)
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

cron = next(n for n, text in enumerate(lines, 1) if text == "function mymod_cron()")
helper = next(n for n, text in enumerate(lines, 1) if text == "function helper()")
edges = [(edge["kind"], edge["from"], edge["to"]) for edge in document["edges"]]
assert edges == [("runs_task", "php.function::mymod_cron", "tag.task::cron")], edges
states = {node["id"]: (node["type"], node["state"]) for node in document["nodes"]}
assert states["php.function::mymod_cron"] == ("php.function", "mapped"), states
assert states["tag.task::cron"] == ("tag.task", "mapped"), states
skipped = [(row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"]]
reason = "edge runs_task: no value for {declared: tag.task}"
assert skipped == [("mymod.module", helper, "runs", reason)], skipped
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("tagger", "runs")] == 2, fires
at = [place["line"] for edge in document["edges"] for place in edge["locations"]]
assert at == [cron], at
PY
echo "declared end ok"
