#!/usr/bin/env bash
# Entity type manager calls joined by the receiver's declared type. A planted class holds a property
# $etm typed EntityTypeManagerInterface, a promoted constructor parameter $em typed
# EntityTypeManager, an untyped property $mgr and a property $entityTypeManager typed
# EntityTypeManagerInterface. getStorage, getViewBuilder and ?->getListBuilder on the typed ones give
# uses_entity_type from the method around the call at inferred, by entity_call_through_typed_manager;
# the untyped $mgr gives none. $this->entityTypeManager->getStorage('e') gives one edge with two
# provenance rows, storage_call and entity_call_through_typed_manager. The map rule fires four
# times and nothing goes unexecuted. Each entity type ends at a referenced node, as storage_call's
# does. periplus validate accepts drupal_basic.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
main="$module/src/Typed.php"
cat >"$main" <<'EOF2'
<?php

namespace Drupal\my_module;

use Drupal\Core\Entity\EntityTypeManager;
use Drupal\Core\Entity\EntityTypeManagerInterface;

class Typed {

  protected EntityTypeManagerInterface $etm;

  protected $mgr;

  protected EntityTypeManagerInterface $entityTypeManager;

  public function __construct(protected EntityTypeManager $em) {
  }

  public function run() {
    $a = $this->etm->getStorage('a');
    $b = $this->em->getViewBuilder('b');
    $c = $this->etm?->getListBuilder('c');
    $d = $this->mgr->getStorage('d');
    $e = $this->entityTypeManager->getStorage('e');
  }

}
EOF2
(cd "$site" && "$PERIPLUS" validate drupal_basic >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" "$main" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()
assert report["not_executed"] == [] and report["problems"] == [], report


def line(text):
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


run = "php.method::Drupal\\my_module\\Typed::run"
edges = [e for e in document["edges"] if e["kind"] == "uses_entity_type"]
found = {(e["from"], e["to"], place["line"]) for e in edges for place in e["locations"]}
assert found == {
    (run, "drupal.entity_type::a", line("$a = $this->etm->getStorage('a');")),
    (run, "drupal.entity_type::b", line("$b = $this->em->getViewBuilder('b');")),
    (run, "drupal.entity_type::c", line("$c = $this->etm?->getListBuilder('c');")),
    (run, "drupal.entity_type::e", line("$e = $this->entityTypeManager->getStorage('e');")),
}, sorted(found)
provenance = {e["to"]: sorted((p["rule"], p["confidence"]) for p in e["provenance"]) for e in edges}
typed = ("entity_call_through_typed_manager", "inferred")
assert provenance == {
    "drupal.entity_type::a": [typed],
    "drupal.entity_type::b": [typed],
    "drupal.entity_type::c": [typed],
    "drupal.entity_type::e": sorted([typed, ("storage_call", "inferred")]),
}, provenance
states = {n["id"]: n["state"] for n in document["nodes"] if n["id"] in provenance}
assert states == {entity: "referenced" for entity in provenance}, states
fires = [
    f["fires"]
    for p in report["map_passes"]
    for f in p["fired"]
    if f["rule"] == "entity_call_through_typed_manager"
]
assert sum(fires) == 4, report["map_passes"]
print("typed manager: four entity type uses at inferred, none for the untyped property")
PY
echo "drupal typed manager ok"
