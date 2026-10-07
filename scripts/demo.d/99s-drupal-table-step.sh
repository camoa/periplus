#!/usr/bin/env bash
# Table steps in the Drupal pack. A planted controller imports User and calls \Drupal::logger('x')
# and User::load(1). The shortcut gives an inferred uses_service edge to logger.factory, the name
# the table shortcut_services gives for logger; the load gives an inferred uses_entity_type edge to
# user, the name the table entity_classes gives for User. Both ends are referenced. Two runs give
# the same bytes. periplus validate accepts drupal_basic, and a rutter whose step names a table no
# pack declares is refused when mapping, by a message that names the tables key.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src/Controller"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
main="$module/src/Controller/ThingController.php"
cat >"$main" <<'EOF'
<?php

namespace Drupal\my_module\Controller;

use Drupal\user\Entity\User;

class ThingController {

  public function run() {
    \Drupal::logger('x')->notice('y');
    $account = User::load(1);
  }

}
EOF
(cd "$site" && "$PERIPLUS" validate drupal_basic >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/first.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/second.json" --format json >/dev/null)
cmp "$work/first.json" "$work/second.json"
python3 - "$work/first.json" "$work/report.json" "$main" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()
assert report["not_executed"] == [] and report["problems"] == [], report


def line(text):
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


run = "php.method::Drupal\\my_module\\Controller\\ThingController::run"
found = {
    (e["kind"], e["from"], e["to"], place["line"], p["rule"], p["confidence"])
    for e in document["edges"]
    if e["kind"] in ("uses_service", "uses_entity_type")
    for place in e["locations"]
    for p in e["provenance"]
}
expected = {
    ("uses_service", run, "drupal.service::logger.factory",
     line("\\Drupal::logger('x')->notice('y');"), "drupal_shortcut_call", "inferred"),
    ("uses_entity_type", run, "drupal.entity_type::user",
     line("$account = User::load(1);"), "entity_class_static_call", "inferred"),
}
assert found == expected, sorted(found ^ expected)
nodes = {n["id"]: n for n in document["nodes"]}
for target in ("drupal.service::logger.factory", "drupal.entity_type::user"):
    assert nodes[target]["state"] == "referenced", nodes[target]
print("drupal table steps: logger.factory and user, inferred, referenced")
PY

bad="$work/bad"
mkdir -p "$bad/.periplus/packs/own@0.0.1/rules" "$bad/src"
printf 'periplus_version: 0\npacks:\n  - own@0.0.1\n' >"$bad/.periplus/settings.yml"
printf 'pack: own\nversion: 0.0.1\ndepends: [drupal_basic]\n' >"$bad/.periplus/packs/own@0.0.1/pack.yaml"
cat >"$bad/.periplus/packs/own@0.0.1/rules/own.yaml" <<'EOF'
rules:
- rule: unknown_table
  reads: file
  in: [source]
  match:
    reference: scoped_call_expression
    name_child: [scope, name]
    filetype: php
  emits:
  - edge:
      kind: uses_service
      from: enclosing_declaration
      to: {resolve: [lookup_last_segment_in: no_such_table], types: [drupal.service]}
  confidence: inferred
EOF
status=0
(cd "$bad" && "$PERIPLUS" map --output "$work/bad.json" >"$work/bad.txt") || status=$?
[ "$status" -eq 26 ] || { echo "expected exit 26, got $status" >&2; exit 1; }
grep -qF "the rule unknown_table cannot be executed: the resolution step lookup_last_segment_in names no_such_table, which no tables key of the pack or a pack it depends on declares" "$work/bad.txt"
echo "drupal table step ok"
