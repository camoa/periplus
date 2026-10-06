#!/usr/bin/env bash
# A rutter carrying a key the schemas accept and nothing executes is reported with the key and the
# file named, in the list and with the exit of a rule the engine cannot execute: a key in a pack
# file, a key in the manifest, and a key inside a rule, by map and by status. Without the keys, the
# same rutter maps.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.RULE_NOT_EXECUTABLE))')"
site="$work/site"
pack="$site/.periplus/packs/idlekeys@0.0.1"
mkdir -p "$pack/rules" "$site/data"
printf 'periplus_version: 0\npacks:\n  - idlekeys@0.0.1\n' >"$site/.periplus/settings.yml"
printf 'name: one\n' >"$site/data/one.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: idlekeys
version: 0.0.1
depends: [yaml_basic]
folders:
  data: ./data
YAML
cat >"$pack/rules/item.yaml" <<'YAML'
node_types:
- name: idlekeys.item
  id_namespace: idlekeys.item
rules:
- rule: item_file
  reads: file
  in: [data]
  match: {file: '*', filetype: yml}
  id: {from: file_stem}
  emits: [{node: {type: idlekeys.item}}]
  confidence: declared
YAML
(cd "$site" && "$PERIPLUS" map --output "$work/clean.json" >/dev/null)

# Every key path the schemas accept and nothing executes, taken from the engine's own set: each one
# with no reported path above it is planted in a document the schemas accept, a manifest key in
# pack.yaml, a pack-file key in rules/planted.yaml, and a rule key in a rule of its own there.
"$python" - "$pack" "$ROOT/src/periplus/contract/schema" "$work/expected.json" <<'PY'
import copy
import json
import sys

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from periplus.engine.packload import UNEXECUTED_KEYS

pack, schemas, out = sys.argv[1:4]
RULE = "file.rules.*."
schema = {
    name: json.load(open(f"{schemas}/pack-{name}.schema.json")) for name in ("manifest", "file")
}


def deref(node, defs):
    while "$ref" in node:
        node = defs[node["$ref"].rsplit("/", 1)[-1]]
    return node


def holder(node, segment, defs):
    """The schema node, or the branch of it, that holds the key or the item directly."""
    node = deref(node, defs)
    held = node.get("items") or node.get("additionalProperties")
    if (isinstance(held, dict) if segment == "*" else segment in node.get("properties", {})):
        return node
    for branch in node.get("oneOf", []) + node.get("anyOf", []):
        found = holder(branch, segment, defs)
        if found is not None:
            return found
    return None


def sub(node, segment, defs):
    node = holder(node, segment, defs)
    if segment == "*":
        return node.get("items") or node.get("additionalProperties")
    return node["properties"][segment]


def leaf(node, defs):
    node = deref(node, defs)
    if "enum" in node:
        return node["enum"][0]
    if "oneOf" in node:
        return leaf(node["oneOf"][0], defs)
    kind = node.get("type")
    kind = "string" if isinstance(kind, list) else kind
    if kind == "string":
        return "idlekeys.item" if "\\." in node.get("pattern", "") else "x"
    return {"boolean": True, "integer": 0, "array": [], "object": {}}[kind]


def plant(doc, segments, node, defs):
    """The document with the key path set, every step kept as the schemas accept it."""
    if not segments:
        return leaf(node, defs)
    head, rest = segments[0], segments[1:]
    child, node = sub(node, head, defs), holder(node, head, defs)
    if head == "*" and isinstance(node.get("additionalProperties"), dict):
        doc = doc if isinstance(doc, dict) else {}
        name = next(iter(doc), "x")
        doc[name] = plant(doc.get(name), rest, child, defs)
        return doc
    if head == "*":
        doc = doc if isinstance(doc, list) else []
        item = deref(child, defs)
        holders = [i for i, entry in enumerate(doc) if isinstance(entry, dict) and rest[0] in entry]
        if not holders and doc and "maxProperties" not in item and isinstance(doc[0], dict):
            holders = [0]
        if holders:
            doc[holders[0]] = plant(doc[holders[0]], rest, child, defs)
        else:
            doc.append(plant({}, rest, child, defs))
        while len(doc) < node.get("minItems", 0):
            doc.append(copy.deepcopy(doc[0]))
        return doc
    doc = doc if isinstance(doc, dict) else {}
    alone = [b["required"][0] for b in node.get("oneOf", []) if list(b) in (["required"], ["required", "not"])]
    if head in alone:
        doc = {k: v for k, v in doc.items() if k not in alone}
    doc[head] = plant(doc.get(head), rest, child, defs)
    for branch in node.get("anyOf", [])[:1]:
        if not any(set(b.get("required", [])) <= set(doc) for b in node["anyOf"]):
            name = branch["required"][0]
            doc[name] = leaf(node["properties"][name], defs)
    return doc


load = YAML(typ="safe", pure=True).load
manifest = load(open(f"{pack}/pack.yaml"))
planted = {
    "node_types": [{"name": "idlekeys.other", "id_namespace": "idlekeys.other"}],
    "edge_kinds": [{"kind": "links", "from": "idlekeys.item", "to": "idlekeys.item"}],
    "imports": [{"ast": "x", "facts": {}}],
    "rules": [],
}
base = {
    "reads": "file",
    "in": ["data"],
    "match": {"file": "*", "filetype": "yml"},
    "id": {"from": "file_stem"},
    "confidence": "declared",
}
node_emits = [{"node": {"type": "idlekeys.item"}}, {"attribute": {"name": "a", "from": "x"}}]
edge_emits = [{"edge": {"kind": "links", "from": "this_node", "to": {"from": {"key": "name"}}}}]
top = [p for p in UNEXECUTED_KEYS if not any(p.startswith(f"{q}.") for q in UNEXECUTED_KEYS)]
expected = []
for number, path in enumerate(top):
    if path.startswith(RULE):
        segments = path.removeprefix(RULE).split(".")
        emits = edge_emits if "edge" in segments else node_emits
        rule = {"rule": f"planted_{number}", **copy.deepcopy(base), "emits": copy.deepcopy(emits)}
        rule_schema = schema["file"]["$defs"]["rule"]
        planted["rules"].append(plant(rule, segments, rule_schema, schema["file"]["$defs"]))
        expected.append(["rules/planted.yaml", f"the rule planted_{number} ", path.removeprefix(RULE)])
    else:
        name, rest = path.split(".", 1)
        target = manifest if name == "manifest" else planted
        target.update(plant(target, rest.split("."), schema[name], schema[name].get("$defs", {})))
        expected.append(["pack.yaml" if name == "manifest" else "rules/planted.yaml", "", rest])
for name, document in (("manifest", manifest), ("file", planted)):
    errors = list(Draft202012Validator(schema[name]).iter_errors(document))
    assert not errors, [(list(e.path), e.message) for e in errors]
json.dump(manifest, open(f"{pack}/pack.yaml", "w"))
json.dump(planted, open(f"{pack}/rules/planted.yaml", "w"))
json.dump(expected, open(out, "w"))
assert len(expected) == len(top) > 3
PY
status=0
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json" \
    2>"$work/map.err") || status=$?
[ "$status" -eq "$code" ] || { echo "expected exit $code, got $status"; cat "$work/map.err"; exit 1; }
[ ! -e "$work/map.json" ] && ! grep -q Traceback "$work/map.err"
status=0
(cd "$site" && "$PERIPLUS" status --format json >"$work/status.json" 2>"$work/status.err") \
    || status=$?
[ "$status" -eq "$code" ] || { echo "status: expected exit $code, got $status"; exit 1; }
! grep -q Traceback "$work/status.err"
for reported in "$work/report.json" "$work/status.json"; do
python3 - "$reported" "$code" "$work/expected.json" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
messages = [p["message"] for p in report["problems"] if p["code"] == code]
for file, rule, key in json.load(open(sys.argv[3])):
    named = [m for m in messages if f"idlekeys/{file}" in m and rule in m and f" {key}" in m]
    assert named, (file, rule, key, messages)
PY
done

# A rule that emits a node of a type its pack declares abstract is refused, naming the rule and
# the type. Nothing matches an abstract type directly; its descendants do.
abstract="$work/abstract"
mkdir -p "$abstract/.periplus/packs/shapes@0.0.1/rules" "$abstract/data"
printf 'periplus_version: 0\npacks:\n  - shapes@0.0.1\n' >"$abstract/.periplus/settings.yml"
printf 'pack: shapes\nversion: 0.0.1\ndepends: [yaml_basic]\nfolders:\n  data: ./data\n' \
    >"$abstract/.periplus/packs/shapes@0.0.1/pack.yaml"
cat >"$abstract/.periplus/packs/shapes@0.0.1/rules/shape.yaml" <<'YAML'
node_types:
- name: shapes.shape
  id_namespace: shapes.shape
  abstract: true
rules:
- rule: shape_file
  reads: file
  in: [data]
  match: {file: '*', filetype: yml}
  id: {from: file_stem}
  emits: [{node: {type: shapes.shape}}]
  confidence: declared
YAML
printf 'name: one\n' >"$abstract/data/one.yml"
unreadable="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.PACK_RULES_UNREADABLE))')"
status=0
(cd "$abstract" && "$PERIPLUS" map --output "$work/abstract.json" --format json \
    >"$work/abstract.report.json") || status=$?
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/abstract.json" ] \
    || { echo "expected exit $unreadable, got $status"; exit 1; }
python3 - "$work/abstract.report.json" "$unreadable" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
assert any(
    p["code"] == code and "shape_file" in p["message"] and "abstract type shapes.shape" in p["message"]
    for p in report["problems"]
), report["problems"]
PY

# The rule sits in another rutter than the one declaring the type abstract: the refusal names the
# rutter and file of the rule, and the rutter that declares the type.
across="$work/across"
mkdir -p "$across/.periplus/packs/shapes@0.0.1/rules" "$across/.periplus/packs/circles@0.0.1/rules" \
    "$across/data"
printf 'periplus_version: 0\npacks:\n  - shapes@0.0.1\n  - circles@0.0.1\n' \
    >"$across/.periplus/settings.yml"
printf 'pack: shapes\nversion: 0.0.1\ndepends: []\n' >"$across/.periplus/packs/shapes@0.0.1/pack.yaml"
printf 'node_types:\n- name: shapes.shape\n  id_namespace: shapes.shape\n  abstract: true\n' \
    >"$across/.periplus/packs/shapes@0.0.1/rules/shape.yaml"
printf 'pack: circles\nversion: 0.0.1\ndepends: [shapes, yaml_basic]\nfolders:\n  data: ./data\n' \
    >"$across/.periplus/packs/circles@0.0.1/pack.yaml"
cat >"$across/.periplus/packs/circles@0.0.1/rules/circle.yaml" <<'YAML'
rules:
- rule: circle_file
  reads: file
  in: [data]
  match: {file: '*', filetype: yml}
  id: {from: file_stem}
  emits: [{node: {type: shapes.shape}}]
  confidence: declared
YAML
printf 'name: one\n' >"$across/data/one.yml"
status=0
(cd "$across" && "$PERIPLUS" map --output "$work/across.json" --format json \
    >"$work/across.report.json") || status=$?
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/across.json" ] \
    || { echo "across: expected exit $unreadable, got $status"; exit 1; }
python3 - "$work/across.report.json" "$unreadable" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
refused = [p["message"] for p in report["problems"] if p["code"] == code and "circle_file" in p["message"]]
assert len(refused) == 1, report["problems"]
message = refused[0]
assert message.startswith("circles/rules/circle.yaml: ") and "abstract type shapes.shape" in message, message
assert "shapes declares" in message, message
PY
echo "unexecuted keys ok"
