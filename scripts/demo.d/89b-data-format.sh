#!/usr/bin/env bash
# A declared data type names its format, in a rutter written in the project's own packs folder for
# an invented format. A box type declared with format yaml gives the map the short form gives, and
# a node per entry of each planted file. A format the engine has no reader for is a pack problem
# naming the rutter, the type and the format, before any file is read: the planted file is not
# YAML, and reading it would end the run with another code. A data type with no format, and a text
# type with one, fail the manifest schema; periplus validate accepts format yaml and refuses no
# format.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code() { "$python" -c "from periplus.errors import ExitCode; print(int(ExitCode.$1))"; }
site="$work/site"
pack="$site/.periplus/packs/crate@0.0.1"
mkdir -p "$pack/rules" "$site/hold"
printf 'periplus_version: 0\npacks:\n  - crate@0.0.1\n' >"$site/.periplus/settings.yml"
plant() {
    printf 'pack: crate\nversion: 0.0.1\ndepends: []\nfolders:\n  hold: ./hold\nfiles:\n%s\n' "$1" \
        >"$pack/pack.yaml"
}
cat >"$pack/rules/crate.yaml" <<'YAML'
node_types:
- name: crate.item
  id_namespace: crate.item
rules:
- rule: item
  reads: file
  in: [hold]
  match: {file: '*', filetype: box, each: 'items.*'}
  id: {template: '{key}'}
  emits: [{node: {type: crate.item}}]
  confidence: declared
YAML
printf 'items:\n  hammer: 1\n  saw: 2\n' >"$site/hold/tools.box"
printf 'items:\n  rope: 3\n' >"$site/hold/ties.box"

plant '  extensions: [box]'
(cd "$site" && "$PERIPLUS" map --output "$work/short.json" --format json >"$work/short.report.json")
plant $'  types:\n    box:\n      endings: [box]\n      reader: data\n      format: yaml'
(cd "$site" && "$PERIPLUS" map --output "$work/declared.json" --format json >"$work/declared.report.json")
(cd "$site" && "$PERIPLUS" validate crate >/dev/null) || { echo "validate refused format yaml"; exit 1; }
cmp "$work/short.json" "$work/declared.json" || { echo "format yaml changed the map"; exit 1; }
python3 - "$work/declared.json" "$work/declared.report.json" "$site/hold" <<'PY'
import json
import os
import sys

document, report, hold = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
assert report["problems"] == [] and report["not_executed"] == [], report
# Expected from the planted files: each indented key under items.
expected = sorted(
    f"crate.item::{line.strip().split(':')[0]}"
    for name in os.listdir(hold)
    for line in open(os.path.join(hold, name))
    if line.startswith("  ")
)
assert len(expected) == 3, expected
assert sorted(node["id"] for node in document["nodes"]) == expected, document["nodes"]
PY

# A format nobody reads, beside a box file that is not YAML.
printf 'items: [unclosed\n' >"$site/hold/torn.box"
plant $'  types:\n    box:\n      endings: [box]\n      reader: data\n      format: inkblot'
unreadable="$(code PACK_RULES_UNREADABLE)"
status=0
(cd "$site" && "$PERIPLUS" map --output "$work/ink.json" --format json >"$work/ink.report.json") \
    || status=$?
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/ink.json" ] \
    || { echo "format inkblot: expected exit $unreadable, got $status"; exit 1; }
python3 - "$work/ink.report.json" "$unreadable" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
named = [
    p for p in report["problems"]
    if p["code"] == code and "crate/" in p["message"] and "box" in p["message"]
    and "inkblot" in p["message"]
]
assert named and all(p["code"] == code for p in report["problems"]), report["problems"]
PY

# The schema: a data type with no format, and a text type with one.
schema="$(code SCHEMA_INVALID)"
for types in $'    box:\n      endings: [box]\n      reader: data' \
    $'    box:\n      endings: [box]\n      reader: text\n      format: yaml'; do
    plant $'  types:\n'"$types"
    status=0
    (cd "$site" && "$PERIPLUS" map --output "$work/bad.json" --format json >"$work/bad.report.json") \
        || status=$?
    [ "$status" -eq "$schema" ] && [ ! -e "$work/bad.json" ] \
        || { echo "schema case: expected exit $schema, got $status"; cat "$work/bad.report.json"; exit 1; }
    grep -q format "$work/bad.report.json" || { cat "$work/bad.report.json"; exit 1; }
done

# periplus validate refuses the data type with no format by the same schema.
plant $'  types:\n    box:\n      endings: [box]\n      reader: data'
status=0
(cd "$site" && "$PERIPLUS" validate crate >"$work/validate.txt") || status=$?
[ "$status" -eq "$schema" ] && grep -q format "$work/validate.txt" \
    || { echo "validate, no format: expected exit $schema, got $status"; cat "$work/validate.txt"; exit 1; }
echo "data format ok"
