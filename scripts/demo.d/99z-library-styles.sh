#!/usr/bin/env bash
# A library links to the local stylesheets its definition lists. A module's library lists two local
# CSS files under two groups, one listed file that does not exist, and two remote addresses; each
# listed local path gets a library_includes_stylesheet edge to a css.file node, mapped when the file
# exists and referenced when it does not, and an address makes no node. A key from the Drupal root
# ends at the module's own stylesheet, or at a referenced node for a file outside the mapped
# folders; a library that lists only a URL gives one skipped row for library_stylesheet.
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
      /modules/custom/mymodule/css/root.css: {}
      /core/misc/dialog.theme.css: {}
remote:
  css:
    theme:
      https://example.com/cdn.css: {type: external}
YAML
printf '.form { color: red; }\n' >"$module/css/form.css"
printf '.root { color: blue; }\n' >"$module/css/root.css"
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
sheets = {f"css.file::{folder}/css/{name}" for name in ("form.css", "form-theme.css", "missing.css", "root.css")}
sheets.add("css.file::web/core/misc/dialog.theme.css")
edges = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "library_includes_stylesheet"}
assert edges == {("drupal.library::mymodule/form", sheet) for sheet in sheets}, edges
nodes = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "css.file"}
assert nodes == {
    sheet: "referenced" if sheet.endswith(("/missing.css", "/dialog.theme.css")) else "mapped"
    for sheet in sheets
}, nodes
assert not any("example.com" in n["id"] for n in document["nodes"]), document["nodes"]
skipped = sorted((s["rule"], s["file"]) for s in report["skipped"])
assert skipped == [("library_stylesheet", f"{folder}/mymodule.libraries.yml")], report["skipped"]
PY
echo "library styles ok"
