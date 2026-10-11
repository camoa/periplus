#!/usr/bin/env bash
# A template links to the templates it includes, extends, embeds or imports, and to the
# components it includes as theme:name. One page template names each kind once, a template that
# no file holds, a component no folder holds, and a call inside a Twig comment. Each name gives
# one edge; the comment gives none; the two names nothing holds end at referenced nodes.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
theme="$site/web/themes/custom/mytheme"
mkdir -p "$site/.periplus" "$theme/templates" "$theme/components/button"
printf 'name: My theme\ntype: theme\nbase theme: false\n' >"$theme/mytheme.info.yml"
cat >"$theme/templates/page.html.twig" <<'TWIG'
{% extends '@mytheme/base.html.twig' %}
{% include 'header.html.twig' %}
{{ include('@mytheme/partials/footer.html.twig') }}
{% embed 'card.html.twig' %}{% endembed %}
{% import 'macros.html.twig' as m %}
{% include 'mytheme:button' %}
{{ include('mytheme:alert') }}
{% include 'missing.html.twig' %}
{# {% include 'commented.html.twig' %} #}
TWIG
for name in base header footer card macros commented; do
    printf '<p></p>\n' >"$theme/templates/$name.html.twig"
done
printf 'name: Button\n' >"$theme/components/button/button.component.yml"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
nodes = {n["id"]: n["state"] for n in document["nodes"]}
edges = sorted(
    (e["kind"], e["to"]) for e in document["edges"]
    if e["from"] == "drupal.template::page" and e["kind"].startswith("template_includes")
)
assert edges == [
    ("template_includes", "drupal.template::base"),
    ("template_includes", "drupal.template::card"),
    ("template_includes", "drupal.template::footer"),
    ("template_includes", "drupal.template::header"),
    ("template_includes", "drupal.template::macros"),
    ("template_includes", "drupal.template::missing"),
    ("template_includes_component", "drupal.component::alert"),
    ("template_includes_component", "drupal.component::button"),
], edges
assert nodes["drupal.component::button"] == "mapped", nodes
assert nodes["drupal.template::missing"] == "referenced", nodes
assert nodes["drupal.component::alert"] == "referenced", nodes
PY
echo "twig relations ok"
