#!/usr/bin/env bash
# Simple configuration links to the module that provides it. A module holds one simple config
# file (no top-level uuid), one config entity file (a uuid) and one file of another module: the
# simple files each have one config_provided_by edge, the entity file none, and the owner that is
# not mapped ends at a referenced node.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$site/config/sync" "$module"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'limit: 5\n' >"$site/config/sync/mymodule.settings.yml"
printf 'limit: 6\n' >"$site/config/sync/othermodule.settings.yml"
printf 'uuid: 11111111-1111-1111-1111-111111111111\nid: one\n' >"$site/config/sync/mymodule.thing.one.yml"

printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [], report
owned = sorted((e["from"], e["to"]) for e in document["edges"] if e["kind"] == "config_provided_by")
assert owned == [
    ("drupal.config::mymodule.settings", "drupal.module::mymodule"),
    ("drupal.config::othermodule.settings", "drupal.module::othermodule"),
], owned
states = {n["id"]: n["state"] for n in document["nodes"]}
assert states["drupal.module::othermodule"] == "referenced", states
PY
echo "config owner ok"
