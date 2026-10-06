#!/usr/bin/env bash
# A where condition names the child it tests. A planted pack depending on php_basic maps a member
# call to a cache store only when its receiver is $cache and its method is store, each tested by
# name_matches {child, pattern}. Of three calls, the one where both parts fit gives the one edge;
# the one where only the receiver fits and the one where only the method fits make nothing, leave
# no skipped row and are not fires. periplus validate and periplus spec accept the pack.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/cache@0.0.1"
mkdir -p "$pack/rules"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n  - cache@0.0.1\n' \
    >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: cache
version: 0.0.1
depends: [php_basic]
YAML
cat >"$pack/rules/cache.yaml" <<'YAML'
node_types:
- name: cache.store
  id_namespace: cache.store
edge_kinds:
- kind: uses_store
  from: php.function
  to: cache.store
rules:
- rule: store_call
  reads: file
  in: [source]
  match:
    reference: member_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: object, pattern: '\$cache'}
    - name_matches: {child: name, pattern: store}
  emits:
  - edge:
      kind: uses_store
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [cache.store], on_miss: unresolved}
  confidence: declared
YAML
main="$site/warm.php"
cat >"$main" <<'PHP'
<?php
namespace App;

function warm()
{
    $cache->store('daily');
    $cache->forget('weekly');
    $queue->store('hourly');
}
PHP

(cd "$site" && "$PERIPLUS" validate cache >/dev/null && "$PERIPLUS" spec cache >/dev/null)
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

found = {
    (edge["from"], edge["to"], place["line"])
    for edge in document["edges"]
    if edge["kind"] == "uses_store"
    for place in edge["locations"]
}
first = next(n for n, text in enumerate(lines, 1) if text.strip() == "$cache->store('daily');")
expected = {("php.function::App\\warm", "cache.store::daily", first)}
assert found == expected, sorted(found ^ expected)
rows = [row for row in report["skipped"] if row["rule"] == "store_call"]
assert rows == [], rows
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("cache", "store_call")] == 1, fires
PY
echo "where second part ok"
