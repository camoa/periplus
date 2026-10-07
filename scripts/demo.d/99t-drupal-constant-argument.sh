#!/usr/bin/env bash
# A class constant as a call argument in the Drupal pack. A planted controller imports MyType and
# calls $this->entityTypeManager->getStorage(MyType::ENTITY_TYPE); MyType declares
# ENTITY_TYPE = 'my_type' in a file that sorts after the controller's. The storage_call rule gives
# an inferred uses_entity_type edge to drupal.entity_type::my_type and leaves no skipped row. Two
# runs give the same bytes.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src/Controller" "$module/src/Entity"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
main="$module/src/Controller/ThingController.php"
declared="$module/src/Entity/MyType.php"
cat >"$main" <<'EOF'
<?php

namespace Drupal\my_module\Controller;

use Drupal\my_module\Entity\MyType;

class ThingController {

  public function run() {
    $this->entityTypeManager->getStorage(MyType::ENTITY_TYPE);
  }

}
EOF
cat >"$declared" <<'EOF'
<?php

namespace Drupal\my_module\Entity;

class MyType {

  const ENTITY_TYPE = 'my_type';

}
EOF
[[ "$main" < "$declared" ]] || { echo "the declaring file must sort after its use" >&2; exit 1; }
(cd "$site" && "$PERIPLUS" map --output "$work/first.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/second.json" --format json >/dev/null)
cmp "$work/first.json" "$work/second.json"
python3 - "$work/first.json" "$work/report.json" "$main" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()
assert report["not_executed"] == [] and report["problems"] == [], report
at = next(n for n, written in enumerate(lines, 1) if "getStorage(MyType::ENTITY_TYPE)" in written)
run = "php.method::Drupal\\my_module\\Controller\\ThingController::run"
found = {
    (e["from"], e["to"], place["line"], p["rule"], p["confidence"])
    for e in document["edges"]
    if e["kind"] == "uses_entity_type"
    for place in e["locations"]
    for p in e["provenance"]
}
expected = {(run, "drupal.entity_type::my_type", at, "storage_call", "inferred")}
assert found == expected, sorted(found ^ expected)
rows = [row for row in report["skipped"] if row["rule"] == "storage_call"]
assert rows == [], rows
print("drupal constant argument: getStorage(MyType::ENTITY_TYPE) to my_type, no skipped row")
PY
echo "drupal constant argument ok"
