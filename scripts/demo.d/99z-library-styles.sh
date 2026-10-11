#!/usr/bin/env bash
# A library links to the local stylesheets its definition lists. A module's library lists two local
# CSS files under two groups, one listed file that does not exist, and two remote addresses; each
# listed local path gets a library_includes_stylesheet edge to a css.file node, mapped when the file
# exists and referenced when it does not, and an address makes no node.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
folder="web/modules/custom/mymodule"
module="$site/$folder"
mkdir -p "$site/.periplus" "$module/css"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n  - drupal_js_basic@0.0.1\n' >"$site/.periplus/settings.yml"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/mymodule.libraries.yml" <<'YAML'
form:
  css:
    component:
      css/form.css: {}
      https://example.com/remote.css: {type: external}
    theme:
      css/form-theme.css: {}
      //cdn.example.com/other.css: {}
      css/missing.css: {}
YAML
printf '.form { color: red; }\n' >"$module/css/form.css"
printf '.form { margin: 0; }\n' >"$module/css/form-theme.css"

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$folder" <<'PY'
import json
import os
import sys

work, folder = sys.argv[1], sys.argv[2]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
sheets = {f"css.file::{folder}/css/{name}" for name in ("form.css", "form-theme.css", "missing.css")}
edges = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "library_includes_stylesheet"}
assert edges == {("drupal.library::mymodule/form", sheet) for sheet in sheets}, edges
nodes = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "css.file"}
assert nodes == {sheet: "referenced" if sheet.endswith("/missing.css") else "mapped" for sheet in sheets}, nodes
assert not any("example.com" in n["id"] for n in document["nodes"]), document["nodes"]
PY
echo "library styles ok"
