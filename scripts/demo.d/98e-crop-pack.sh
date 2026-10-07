#!/usr/bin/env bash
# The bundled crop_basic pack, pinned beside drupal_basic@0.3.0. A crop type in the
# site's exported config and one in a module's install config each make the bundle
# crop.<id> with its label, a configured_by edge to its config file and a bundle_of edge to
# the entity type crop, which no file declares and so stays referenced. A crop
# settings file is not a type and makes no bundle. The map and the report are byte-identical across
# two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$site/config/sync" "$module/config/install"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'id: my_type\nlabel: My type\n' >"$site/config/sync/crop.type.my_type.yml"
printf 'id: my_other_type\nlabel: My other type\n' \
    >"$module/config/install/crop.type.my_other_type.yml"
printf 'langcode: en\n' >"$site/config/sync/crop.settings.yml"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - crop_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]


def load(name):
    return json.load(open(os.path.join(work, name)))


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report
assert report["skipped"] == [], report["skipped"]

nodes = {n["id"]: (n["state"], n.get("attributes", {}).get("label")) for n in document["nodes"]}
assert nodes == {
    "drupal.bundle::crop.my_other_type": ("mapped", "My other type"),
    "drupal.bundle::crop.my_type": ("mapped", "My type"),
    "drupal.config::crop.settings": ("mapped", None),
    "drupal.config::crop.type.my_other_type": ("mapped", None),
    "drupal.config::crop.type.my_type": ("mapped", None),
    "drupal.entity_type::crop": ("referenced", None),
    "drupal.module::mymodule": ("mapped", None),
}, nodes

sync = "config/sync/crop.type.my_type.yml"
install = "web/modules/custom/mymodule/config/install/crop.type.my_other_type.yml"
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("bundle_of", "drupal.bundle::crop.my_type", "drupal.entity_type::crop",
     [(sync, 1)]),
    ("configured_by", "drupal.bundle::crop.my_type",
     "drupal.config::crop.type.my_type", [(sync, 1)]),
    ("bundle_of", "drupal.bundle::crop.my_other_type", "drupal.entity_type::crop",
     [(install, 1)]),
    ("configured_by", "drupal.bundle::crop.my_other_type",
     "drupal.config::crop.type.my_other_type", [(install, 1)]),
]), edges
PY
echo "crop pack ok"
