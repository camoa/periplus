#!/usr/bin/env bash
# A third party gets the same file links as the bundled rutters. A project-local pack writes the
# library -> script rule with the list-form key filter (each, with not_matches) and the
# script -> behavior rule with the enclosing_file end, using no engine code. The planted module is mapped with the bundled js packs and again with that pack; the
# nodes and edges are identical, and they hold the library, script, behavior and function links (js_basic's own).
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
pack="$site/.periplus/packs/localjs@0.0.1"
mkdir -p "$site/.periplus" "$module/js" "$pack/rules"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/mymodule.libraries.yml" <<'YAML'
form:
  js:
    js/form.js: {}
    https://example.com/remote.js: {type: external}
    //cdn.example.com/other.js: {}
YAML
cat >"$module/js/form.js" <<'JS'
function helper() {}
const arrow = () => {};
Drupal.behaviors.mymoduleForm = {
  attach() {},
};
JS

cat >"$pack/pack.yaml" <<'YAML'
pack: localjs
version: 0.0.1
depends: [js_basic, drupal_basic]
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
      path_values:
        libraries_dir:
          pattern: '^(?<dir>.+)/[^/]+$'
          template: '{dir}'
YAML
cat >"$pack/rules/links.yaml" <<'YAML'
node_types:
- name: drupal.js_behavior
  id_namespace: drupal.js_behavior
edge_kinds:
- kind: library_includes_script
  from: drupal.library
  to: js.file
- kind: script_declares_behavior
  from: js.file
  to: drupal.js_behavior
rules:
- rule: local_behavior
  reads: file
  in: [js_source]
  match: {declaration: assignment_expression, name_child: left, body_child: object, filetype: javascript, where: [{has_child: object}]}
  id: {from: declared_name, pattern: '^Drupal\.behaviors\.(?<behavior>[A-Za-z_$][\w$]*)$', template: '{behavior}'}
  emits: [{node: {type: drupal.js_behavior}}]
  confidence: declared
- rule: local_behavior_in_file
  reads: file
  in: [js_source]
  match: {declaration: assignment_expression, name_child: left, body_child: object, filetype: javascript, where: [{has_child: object}]}
  id: {from: declared_name, pattern: '^Drupal\.behaviors\.(?<behavior>[A-Za-z_$][\w$]*)$', template: '{behavior}'}
  emits: [{edge: {kind: script_declares_behavior, from: enclosing_file, to: this_node}}]
  confidence: declared
- rule: local_library_script
  reads: file
  in: [module_root, theme_root]
  match: {file: '*.libraries', filetype: yml, each: '*'}
  id:
    from: [file_stem, key]
    template: '{file_stem}/{key}'
    normalize: [{replace: '\.libraries/', with: /}]
  emits:
  - edge:
      kind: library_includes_script
      from: this_node
      to:
        from: [{each: js.*}]
        template: '{libraries_dir}/{key}'
        where: [{not_matches: '//*'}, {not_matches: 'http:*'}, {not_matches: 'https:*'}]
  confidence: declared
YAML
map_with() {
    printf 'periplus_version: 0\npacks:\n%s\n' "$1" >"$site/.periplus/settings.yml"
    (cd "$site" && "$PERIPLUS" map --output "$work/$2.json" --format json >"$work/$2-report.json")
}
map_with '  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - drupal_js_basic@0.0.1' bundled
map_with '  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - localjs@0.0.1' local

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]


def load(name):
    document = json.load(open(os.path.join(work, name + ".json")))
    report = json.load(open(os.path.join(work, name + "-report.json")))
    assert report["problems"] == [] and report["not_executed"] == [], (name, report)
    nodes = sorted((n["id"], n["state"]) for n in document["nodes"])
    edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
    return nodes, edges


bundled = load("bundled")
local = load("local")
assert local == bundled, (local, bundled)
edges = bundled[1]
folder = "web/modules/custom/mymodule"
script = f"js.file::{folder}/js/form.js"
for kind, end in (
    ("library_includes_script", script),
    ("script_declares_behavior", "drupal.js_behavior::mymoduleForm"),
    ("script_declares_function", f"js.function::{folder}/js/form.js:helper"),
):
    assert any(e[0] == kind and e[2] == end for e in edges), (kind, edges)
assert not any("example.com" in e[2] for e in edges), edges
PY
echo "third-party file links ok"
