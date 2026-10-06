#!/usr/bin/env bash
# A rutter declares its file types. The longest ending wins: a.html.twig is the type that claims
# html.twig and b.twig the type that claims twig. A file named Makefile is selected by a type
# declared by whole file name and mapped by a rule of that type. A rule file whose applies_to names
# an arbitrary tree node, not one from a fixed list, passes periplus validate.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
pack="$site/.periplus/packs/kinds@0.0.1"
mkdir -p "$pack/rules" "$site/src"
printf 'periplus_version: 0\npacks:\n  - kinds@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: kinds
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    page:
      endings: [.html.twig]
      reader: text
    piece:
      endings: [twig]
      reader: text
    build:
      names: [Makefile]
      reader: text
YAML
cat >"$pack/rules/kinds.yaml" <<'YAML'
node_types:
- name: kinds.page
  id_namespace: kinds.page
- name: kinds.piece
  id_namespace: kinds.piece
- name: kinds.build
  id_namespace: kinds.build
rules:
- rule: page_file
  reads: file
  in: [src]
  match: {file: '*', filetype: page}
  id: {from: file_stem}
  emits: [{node: {type: kinds.page}}]
  confidence: declared
- rule: piece_file
  reads: file
  in: [src]
  match: {file: '*', filetype: piece}
  id: {from: file_stem}
  emits: [{node: {type: kinds.piece}}]
  confidence: declared
- rule: build_file
  reads: file
  in: [src]
  match: {file: '*', filetype: build}
  id: {from: file_stem}
  emits: [{node: {type: kinds.build}}]
  confidence: declared
YAML
printf '<p>a</p>\n' >"$site/src/a.html.twig"
printf '<p>b</p>\n' >"$site/src/b.twig"
printf 'all:\n\ttrue\n' >"$site/src/Makefile"
printf 'not claimed\n' >"$site/src/c.txt"

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$site/src" <<'PY'
import json
import os
import sys

document, src = json.load(open(sys.argv[1])), sys.argv[2]
found = {(node["type"], node["id"]) for node in document["nodes"]}
# Expected from the files: the longest ending each name ends with, or the whole name.
endings = {"html.twig": "page", "twig": "piece"}
expected = set()
for name in sorted(os.listdir(src)):
    if name == "Makefile":
        expected.add(("kinds.build", "kinds.build::Makefile"))
        continue
    claims = [e for e in endings if name.endswith("." + e)]
    if claims:
        ending = max(claims, key=len)
        kind = endings[ending]
        expected.add((f"kinds.{kind}", f"kinds.{kind}::{name[: -len(ending) - 1]}"))
assert ("kinds.page", "kinds.page::a") in expected and ("kinds.piece", "kinds.piece::b") in expected
assert found == expected, (sorted(found), sorted(expected))
PY

# applies_to names any tree node: a rule file naming one that no fixed list would hold.
mkdir -p "$work/any/.periplus/packs/anynode@0.0.1/rules"
printf 'periplus_version: 0\npacks:\n  - anynode@0.0.1\n' >"$work/any/.periplus/settings.yml"
printf 'pack: anynode\nversion: 0.0.1\ndepends: []\nfolders:\n  src: ./src\n' \
    >"$work/any/.periplus/packs/anynode@0.0.1/pack.yaml"
rulefile="$work/any/.periplus/packs/anynode@0.0.1/rules/tagged.yaml"
cat >"$rulefile" <<'YAML'
node_types:
- name: anynode.tagged
  id_namespace: anynode.tagged
rules:
- rule: tagged_item
  reads: file
  in: [src]
  match:
    attribute: Tagged
    filetype: src
    where:
    - applies_to: struct_item
  id:
    from: {attribute_argument: name}
  emits:
  - node:
      type: anynode.tagged
  confidence: declared
YAML
(cd "$work/any" && "$PERIPLUS" validate anynode >/dev/null)
# A short-form list that shares an ending with the bundled YAML rutter's list loads, as it did
# before file types: [yml] beside [yml, yaml]. In the same rutter, a type read as text holds a file
# that is not valid YAML, and a rule that reads its content maps it.
other="$work/other"
extra="$other/.periplus/packs/extra@0.0.1"
mkdir -p "$extra/rules" "$other/data"
printf 'periplus_version: 0\npacks:\n  - extra@0.0.1\n' >"$other/.periplus/settings.yml"
cat >"$extra/pack.yaml" <<'YAML'
pack: extra
version: 0.0.1
depends: [yaml_basic]
folders:
  data: ./data
files:
  extensions: [yml]
  types:
    piece:
      endings: [twig]
      reader: text
YAML
cat >"$extra/rules/extra.yaml" <<'YAML'
node_types:
- name: extra.note
  id_namespace: extra.note
- name: extra.block
  id_namespace: extra.block
rules:
- rule: note_file
  reads: file
  in: [data]
  match: {file: '*', filetype: yml}
  id: {from: file_stem}
  emits: [{node: {type: extra.note}}]
  confidence: declared
- rule: block
  reads: file
  in: [data]
  match: {file: '*', filetype: piece, text: '\{% block (?<name>\w+) %\}'}
  id: {from: {capture: name}}
  emits: [{node: {type: extra.block}}]
  confidence: declared
YAML
printf 'name: a\n' >"$other/data/a.yml"
printf '{%% block main %%}: [\n' >"$other/data/b.twig"
"$python" - "$other/data/b.twig" <<'PY'
import sys

from ruamel.yaml import YAML

try:
    YAML(typ="safe", pure=True).load(open(sys.argv[1]))
except Exception:
    pass
else:
    raise SystemExit("b.twig is valid YAML, so it proves nothing about the text reader")
PY
(cd "$other" && "$PERIPLUS" map --output "$work/other.json" --format json >"$work/other.report.json")
python3 - "$work/other.json" <<'PY'
import json
import sys

found = {(node["type"], node["id"]) for node in json.load(open(sys.argv[1]))["nodes"]}
assert found == {("extra.note", "extra.note::a"), ("extra.block", "extra.block::main")}, found
PY
echo "file types ok"
