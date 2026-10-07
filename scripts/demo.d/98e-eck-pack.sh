#!/usr/bin/env bash
# The bundled eck_basic pack, pinned beside drupal_basic@0.3.0. An ECK entity type's config file
# makes a content entity type named by its id, with its label. An ECK bundle's config file
# eck.eck_type.<entity type>.<bundle> makes the bundle <entity type>.<bundle> with its label read
# from the key name, a configured_by edge to its config file and a bundle_of edge to the entity
# type, read from the file name. One bundle sits in the site's exported config, one in a module's
# install config. The map and the report are byte-identical across two runs, the report but for
# the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
sync="$site/config/sync"
mkdir -p "$site/.periplus" "$sync" "$module/config/install"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'id: my_entity\nlabel: My entity\nuid: true\n' >"$sync/eck.eck_entity_type.my_entity.yml"
printf 'name: My type\ntype: my_type\ndescription: ""\n' >"$sync/eck.eck_type.my_entity.my_type.yml"
printf 'name: My other type\ntype: my_other_type\n' \
    >"$module/config/install/eck.eck_type.my_entity.my_other_type.yml"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - eck_basic@0.0.1\n' \
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
    "drupal.bundle::my_entity.my_other_type": ("mapped", "My other type"),
    "drupal.bundle::my_entity.my_type": ("mapped", "My type"),
    "drupal.config::eck.eck_entity_type.my_entity": ("mapped", None),
    "drupal.config::eck.eck_type.my_entity.my_other_type": ("mapped", None),
    "drupal.config::eck.eck_type.my_entity.my_type": ("mapped", None),
    "drupal.entity_type::my_entity": ("mapped", "My entity"),
    "drupal.module::mymodule": ("mapped", None),
}, nodes
kinds = {n["id"]: n["type"] for n in document["nodes"]}
assert kinds["drupal.entity_type::my_entity"] == "drupal.content_entity_type", kinds

bundle = "config/sync/eck.eck_type.my_entity.my_type.yml"
install = "web/modules/custom/mymodule/config/install/eck.eck_type.my_entity.my_other_type.yml"
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("bundle_of", "drupal.bundle::my_entity.my_type", "drupal.entity_type::my_entity",
     [(bundle, 2)]),
    ("configured_by", "drupal.bundle::my_entity.my_type",
     "drupal.config::eck.eck_type.my_entity.my_type", [(bundle, 2)]),
    ("bundle_of", "drupal.bundle::my_entity.my_other_type", "drupal.entity_type::my_entity",
     [(install, 2)]),
    ("configured_by", "drupal.bundle::my_entity.my_other_type",
     "drupal.config::eck.eck_type.my_entity.my_other_type", [(install, 2)]),
]), edges
PY
echo "eck pack ok"
