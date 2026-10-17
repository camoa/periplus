#!/usr/bin/env bash
# A reference rule whose to end is a template, with no receiver condition. The rutter's rule fires
# on $this->mailer->send(): one name_matches condition on each of its two name children captures
# member from the object and method from the name, and the end {enclosing_type}::${member}::{method}
# writes the id. $other->send() fails the object's pattern and makes nothing.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/own@0.0.1"
mkdir -p "$pack/rules" "$site/src"
printf 'periplus_version: 0\npacks: [own@0.0.1]\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: own
version: 0.0.1
depends: [php_basic]
folders:
  source: ./src
files:
  extends: php_basic
YAML
cat >"$pack/rules/calls.yaml" <<'YAML'
node_types:
- {name: own.member_call, id_namespace: own.member_call}
edge_kinds:
- {kind: calls_member, from: php.method, to: own.member_call}
rules:
- rule: member_call
  reads: file
  in: [source]
  match:
    reference: member_call_expression
    name_child: [object, name]
    filetype: php
    where:
    - name_matches: {child: object, pattern: '\$this->(?<member>\w+)'}
    - name_matches: {child: name, pattern: '(?<method>\w+)'}
  emits:
  - edge:
      kind: calls_member
      from: enclosing_declaration
      to: {template: '{enclosing_type}::${member}::{method}', types: [own.member_call], on_miss: unresolved}
  confidence: inferred
YAML
page="$site/src/Page.php"
cat >"$page" <<'PHP'
<?php

namespace App\Web;

class Page
{
    public function run(): void
    {
        $this->mailer->send();
        $other->send();
    }
}
PHP

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$page" <<'PY'
import json
import os
import sys

work, page = sys.argv[1], sys.argv[2]
lines = open(page).read().splitlines()
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]
line = lines.index("        $this->mailer->send();") + 1
edges = [
    (edge["from"], edge["to"], [place["line"] for place in edge["locations"]])
    for edge in document["edges"]
    if edge["kind"] == "calls_member"
]
assert edges == [
    ("php.method::App\\Web\\Page::run", "own.member_call::App\\Web\\Page::$mailer::send", [line])
], edges
skipped = [row for row in report["skipped"] if "member_call" in json.dumps(row)]
assert skipped == [], skipped
PY
echo "reference template ends ok"
