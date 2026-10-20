#!/usr/bin/env bash
# A single-directory component's <name>.twig that calls attach_library gives a
# component_attaches_library edge from drupal.component::<name>, and no template node of that
# name. A <name>.html.twig template beside it that calls attach_library keeps its one
# template_attaches_library edge, with one provenance row.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/components/card" "$module/templates"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'card:\n  js:\n    js/card.js: {}\n' >"$module/mymodule.libraries.yml"
printf 'name: Card\n' >"$module/components/card/card.component.yml"
printf "<div>{{ attach_library('mymodule/card') }}</div>\n" >"$module/components/card/card.twig"
printf "<div>{{ attach_library('mymodule/card') }}</div>\n" \
    >"$module/templates/mymodule-page.html.twig"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
library = "drupal.library::mymodule/card"
nodes = {n["id"]: n["state"] for n in document["nodes"]}
assert nodes["drupal.component::card"] == "mapped", nodes
assert "drupal.template::card" not in nodes, nodes
attaches = [e for e in document["edges"] if e["to"] == library and "attaches" in e["kind"]]
assert sorted((e["kind"], e["from"]) for e in attaches) == [
    ("component_attaches_library", "drupal.component::card"),
    ("template_attaches_library", "drupal.template::mymodule-page"),
], attaches
template = next(e for e in attaches if e["kind"] == "template_attaches_library")
assert [row["rule"] for row in template["provenance"]] == ["library_attached_in_template"], template
PY
echo "component template ok"
