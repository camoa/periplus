#!/usr/bin/env bash
# A library links to the local scripts its definition lists, and a script links to the behaviors
# it declares. A module holds a libraries file with two local scripts and a remote one; each
# script declares a behavior. Each local script is a js.file node reached by a
# library_includes_script edge from the library, and has a script_declares_behavior edge to its
# behavior. The remote script makes no node and no edge. The library, its dependency edge and a library
# attached from PHP are all still mapped, none of them referenced.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/js" "$module/src/Controller"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/mymodule.libraries.yml" <<'YAML'
form:
  js:
    js/form.js: {}
    js/extra.js: {}
    https://example.com/remote.js: {type: external}
  dependencies:
    - core/drupal
YAML
printf 'Drupal.behaviors.mymoduleForm = {\n  attach() {},\n};\n' >"$module/js/form.js"
printf 'Drupal.behaviors.mymoduleExtra = {\n  attach() {},\n};\n' >"$module/js/extra.js"
cat >"$module/src/Controller/FormController.php" <<'EOF2'
<?php

namespace Drupal\mymodule\Controller;

final class FormController {

  public function page(): array {
    $build['#attached']['library'][] = 'mymodule/form';
    return $build;
  }

}
EOF2
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
folder = "web/modules/custom/mymodule"
library = "drupal.library::mymodule/form"
nodes = {n["id"]: n["state"] for n in document["nodes"]}
assert nodes[library] == "mapped", nodes
assert nodes["drupal.library::core/drupal"] == "referenced", nodes
assert f"js.file::{folder}/https://example.com/remote.js" not in nodes, nodes
for name in ("form", "extra"):
    assert nodes[f"js.file::{folder}/js/{name}.js"] == "mapped", nodes
edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
assert edges == sorted([
    ("depends_on_library", library, "drupal.library::core/drupal"),
    ("library_includes_script", library, f"js.file::{folder}/js/form.js"),
    ("library_includes_script", library, f"js.file::{folder}/js/extra.js"),
    ("script_declares_behavior", f"js.file::{folder}/js/form.js",
     "drupal.js_behavior::mymoduleForm"),
    ("script_declares_behavior", f"js.file::{folder}/js/extra.js",
     "drupal.js_behavior::mymoduleExtra"),
    ("attaches_library", "php.type::Drupal\\mymodule\\Controller\\FormController", library),
    ("contains", "php.type::Drupal\\mymodule\\Controller\\FormController",
     "php.method::Drupal\\mymodule\\Controller\\FormController::page"),
]), edges
PY
echo "library scripts ok"
