#!/usr/bin/env bash
# The bundled JavaScript packs, js_basic and drupal_js_basic, pinned beside drupal_basic@0.3.0.
# A module holds a libraries file, a script with two named functions and two behaviors, a
# controller and a template. The functions are js.function nodes named by script path and name.
# Each behavior is a node; the one whose attach calls the other's attach has an attaches_behavior
# edge to it, and its read of drupalSettings.mymoduleColor is a reads_setting edge. The controller
# attaches a library by assignment and by array, each an attaches_library edge from its class,
# and attaches the setting, a provides_setting edge. The template's attach_library() is a
# template_attaches_library edge. The map and the report are byte-identical across two runs, the
# report but for the map path it names.
# The grammar is the extra js. Without it, periplus map stops with a problem naming the pin, and
# this check fails.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/js" "$module/src/Controller" "$module/templates"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'widget:\n  js:\n    js/widget.js: {}\n' >"$module/mymodule.libraries.yml"
cat >"$module/js/widget.js" <<'EOF'
(function (Drupal, drupalSettings) {
  function format(value) {
    return value;
  }

  const shout = (value) => value.toUpperCase();

  Drupal.behaviors.mymoduleWidget = {
    attach(context) {
      const color = drupalSettings.mymoduleColor;
      Drupal.behaviors.mymoduleOther.attach(context);
    },
  };

  Drupal.behaviors.mymoduleOther = {
    attach() {},
  };
})(Drupal, drupalSettings);
EOF
cat >"$module/src/Controller/WidgetController.php" <<'EOF'
<?php

namespace Drupal\mymodule\Controller;

final class WidgetController {

  public function page(): array {
    $build['#attached']['library'][] = 'mymodule/widget';
    $build['#attached']['drupalSettings']['mymoduleColor'] = 'red';
    return $build;
  }

  public function card(): array {
    return [
      '#attached' => ['library' => ['mymodule/card']],
    ];
  }

}
EOF
printf "<div>{{ attach_library('mymodule/widget') }}</div>\n" \
    >"$module/templates/mymodule-widget.html.twig"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$module" <<'PY'
import json
import os
import sys

work, module = sys.argv[1], sys.argv[2]
folder = "web/modules/custom/mymodule"
script, php = f"{folder}/js/widget.js", f"{folder}/src/Controller/WidgetController.php"
template = f"{folder}/templates/mymodule-widget.html.twig"
controller = "php.type::Drupal\\mymodule\\Controller\\WidgetController"
method = "php.method::Drupal\\mymodule\\Controller\\WidgetController::"
widget, other = "drupal.js_behavior::mymoduleWidget", "drupal.js_behavior::mymoduleOther"
setting = "drupal.js_setting::mymoduleColor"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(module, path.removeprefix(folder + "/"))).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip() == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report
assert report["skipped"] == [], report["skipped"]

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    f"js.function::{script}:format": ("js.function", "mapped"),
    f"js.function::{script}:shout": ("js.function", "mapped"),
    widget: ("drupal.js_behavior", "mapped"),
    other: ("drupal.js_behavior", "mapped"),
    setting: ("drupal.js_setting", "mapped"),
    "drupal.library::mymodule/widget": ("drupal.library", "mapped"),
    "drupal.library::mymodule/card": ("drupal.library", "referenced"),
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drupal.template::mymodule-widget": ("drupal.template", "mapped"),
    controller: ("php.class", "mapped"),
    method + "page": ("php.method", "mapped"),
    method + "card": ("php.method", "mapped"),
}, nodes

edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("attaches_behavior", widget, other,
     [(script, line(script, "Drupal.behaviors.mymoduleOther.attach(context);"))]),
    ("reads_setting", widget, setting,
     [(script, line(script, "const color = drupalSettings.mymoduleColor;"))]),
    ("attaches_library", controller, "drupal.library::mymodule/widget",
     [(php, line(php, "$build['#attached']['library'][] = 'mymodule/widget';"))]),
    ("attaches_library", controller, "drupal.library::mymodule/card",
     [(php, line(php, "'#attached' => ['library' => ['mymodule/card']],"))]),
    ("provides_setting", controller, setting,
     [(php, line(php, "$build['#attached']['drupalSettings']['mymoduleColor'] = 'red';"))]),
    ("template_attaches_library", "drupal.template::mymodule-widget",
     "drupal.library::mymodule/widget", [(template, 1)]),
    ("contains", controller, method + "page",
     [(php, line(php, "public function page(): array {"))]),
    ("contains", controller, method + "card",
     [(php, line(php, "public function card(): array {"))]),
]), edges
PY
echo "js packs ok"
