#!/usr/bin/env bash
# Settings values in templates. The project settings give values: {module: example.com/app}. A
# planted rutter's path value pkg reads '{module}/{path}', path being the folder of the file, and
# a normalize drops the trailing slash a file in the root folder leaves, so the root shape is
# '{module}' and the subfolder shape '{module}/<folder>'. Its grammar takes the namespace from the
# path value pkg. One class rule's id is the template '{pkg}.{declared_name}', the other's is the
# qualified name built from that namespace; both give the same ids, for a root file and a subfolder
# file, and periplus status accepts the pack too. A third rule names the setting in its own id,
# '{module}/{dir}.{declared_name}', dir being the subfolder path value, so the root file gives a
# skipped row naming dir. With the setting removed, the map is refused at load with exit 19, naming
# the path value's template and the value, and the third rule's template and the value; with a
# setting named pkg, it is refused naming the setting, its settings file and the path value. The
# map and the report are byte-identical across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/modules@0.0.1"
mkdir -p "$pack/rules" "$site/sub/inner"
cat >"$pack/pack.yaml" <<'YAML'
pack: modules
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        pkg:
          pattern: '^(?<path>(?:.*/)?)[^/]+$'
          template: '{module}/{path}'
          normalize: [{replace: '/$', with: ''}]
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: '{d}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "."}
  namespace: {path_value: pkg}
  written_names: [name]
YAML
cat >"$pack/rules/modules.yaml" <<'YAML'
node_types:
- name: modules.class
  id_namespace: modules.class
- name: modules.qualified
  id_namespace: modules.qualified
- name: modules.literal
  id_namespace: modules.literal
rules:
- rule: by_template
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [pkg, declared_name], template: '{pkg}.{declared_name}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
- rule: by_qualified_name
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: qualified_name}
  emits: [{node: {type: modules.qualified}}]
  confidence: declared
- rule: by_setting
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [module, dir, declared_name], template: '{module}/{dir}.{declared_name}'}
  emits: [{node: {type: modules.literal}}]
  confidence: declared
YAML
printf '<?php\n\nclass Root\n{\n}\n' >"$site/Root.php"
printf '<?php\n\nclass Leaf\n{\n}\n' >"$site/sub/inner/Leaf.php"

settings() {
    printf 'periplus_version: 0\npacks:\n  - modules@0.0.1\n%s' "$1" >"$site/.periplus/settings.yml"
}

settings $'values:\n  module: example.com/app\n'
for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"
# status runs the same load checks as map, and must be given the same values.
(cd "$site" && "$PERIPLUS" status --format json >"$work/status.json")

settings ''
code=0
(cd "$site" && "$PERIPLUS" map --output "$work/none.json" --format json >"$work/none-report.json") \
    || code=$?
settings $'values:\n  module: example.com/app\n  pkg: example.com/other\n'
clash=0
(cd "$site" && "$PERIPLUS" map --output "$work/clash.json" --format json >"$work/clash-report.json") \
    || clash=$?

python3 - "$work" "$code" "$clash" "$site" <<'PY'
import json
import os
import sys

work, code, clash, site = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]


def load(name):
    return json.load(open(os.path.join(work, name)))


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
ids = sorted(n["id"] for n in document["nodes"])
assert ids == [
    "modules.class::example.com/app.Root",
    "modules.class::example.com/app/sub/inner.Leaf",
    "modules.literal::example.com/app/sub/inner.Leaf",
    "modules.qualified::example.com/app.Root",
    "modules.qualified::example.com/app/sub/inner.Leaf",
], ids
assert report["skipped"] == [
    {"file": "Root.php", "line": 3, "rule": "by_setting", "reason": "the id source dir is absent"}
], report["skipped"]
assert not report["problems"], report["problems"]

assert code == 19, code
assert not os.path.exists(os.path.join(work, "none.json"))
messages = [p["message"] for p in load("none-report.json")["problems"]]
assert messages == [
    "modules/pack.yaml: the path value pkg of the file type code has the template "
    "{module}/{path}, which names module, no capture of its pattern and no settings value",
    "modules/rules/modules.yaml: the rule by_setting has the id template "
    "{module}/{dir}.{declared_name}, which names module, no field of the php grammar, path value "
    "or settings value",
], messages

assert clash == 19, clash
assert not os.path.exists(os.path.join(work, "clash.json"))
messages = [p["message"] for p in load("clash-report.json")["problems"]]
assert messages == [
    "modules/pack.yaml: the path value pkg of the file type code has the name of the settings "
    f"value pkg of {os.path.join(site, '.periplus', 'settings.yml')}"
], messages
PY
echo "settings values ok"
