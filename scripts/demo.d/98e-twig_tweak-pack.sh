#!/usr/bin/env bash
# The bundled twig_tweak_basic pack, pinned beside drupal_basic@0.3.0. A template that calls a Twig
# Tweak function with a quoted first argument gets one edge per call: drupal_block to the block
# plugin, drupal_menu to the config object system.menu.<name>, drupal_entity and
# drupal_entity_form to the entity type, and drupal_field to the config object
# field.storage.<entity type>.<field>; each end stays referenced. Templates are read in a module
# and in a theme. A call whose name is a variable, and a call inside a Twig comment, make nothing.
# The map and the report are byte-identical across two runs, the report but for the map path it
# names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
theme="$site/web/themes/custom/mytheme"
mkdir -p "$site/.periplus" "$module/templates" "$theme/templates"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'name: My theme\ntype: theme\ncore_version_requirement: ^10\n' >"$theme/mytheme.info.yml"
cat >"$module/templates/my-template.html.twig" <<'EOF'
<div class="my-template">
  {{ drupal_block('my_block', {label: 'Mine'}) }}
  {{ drupal_entity('node', 1) }}
  {{ drupal_entity_form("node", null, 'default') }}
  {{ drupal_field('field_my_field', 'node', 1) }}
  {{ drupal_block(block_id) }}
  {# drupal_menu('footer') #}
</div>
EOF
printf '<nav>{{ drupal_menu('"'"'main'"'"') }}</nav>\n' >"$theme/templates/page.html.twig"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - twig_tweak_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$site" <<'PY'
import json
import os
import sys

work, site = sys.argv[1], sys.argv[2]
mine = "web/modules/custom/mymodule/templates/my-template.html.twig"
page = "web/themes/custom/mytheme/templates/page.html.twig"
template = "drupal.template::my-template"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip() == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report
assert report["skipped"] == [], report["skipped"]

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    "drupal.config::field.storage.node.field_my_field": ("drupal.field_storage", "referenced"),
    "drupal.config::system.menu.main": ("drupal.config_object", "referenced"),
    "drupal.entity_type::node": ("drupal.entity_type", "referenced"),
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drupal.plugin.block::my_block": ("drupal.block_plugin", "referenced"),
    template: ("drupal.template", "mapped"),
    "drupal.template::page": ("drupal.template", "mapped"),
    "drupal.theme::mytheme": ("drupal.theme", "mapped"),
}, nodes

edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("renders_block", template, "drupal.plugin.block::my_block",
     [(mine, line(mine, "{{ drupal_block('my_block', {label: 'Mine'}) }}"))]),
    ("renders_entity_type", template, "drupal.entity_type::node",
     [(mine, line(mine, "{{ drupal_entity('node', 1) }}"))]),
    ("renders_entity_form", template, "drupal.entity_type::node",
     [(mine, line(mine, "{{ drupal_entity_form(\"node\", null, 'default') }}"))]),
    ("renders_field", template, "drupal.config::field.storage.node.field_my_field",
     [(mine, line(mine, "{{ drupal_field('field_my_field', 'node', 1) }}"))]),
    ("renders_menu", "drupal.template::page", "drupal.config::system.menu.main", [(page, 1)]),
]), edges
PY
echo "twig_tweak pack ok"
