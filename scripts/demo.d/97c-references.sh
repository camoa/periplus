#!/usr/bin/env bash
# References and candidate types. (a) An invented text format whose edge end lists two types: a
# name mapped under the second type lands there, one mapped under the first lands there, and an
# unknown name is an unresolved node of the first type, listing both types tried. (b) A planted
# rutter that depends on php_basic states each function and static call as an edge from the
# enclosing function or method to the full name the file's namespace and imports give it; a call
# outside any declaration makes nothing and is listed as skipped. The PHP file runs past line 300,
# so the tree is read above line 256. Each map validates and two runs are byte-identical.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
validate() {
    "$python" - "$1" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import json
import sys

from jsonschema import Draft202012Validator

Draft202012Validator(json.load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1])))
PY
}

# (a) Candidate types on a text end.
site="$work/text"
pack="$site/.periplus/packs/links@0.0.1"
mkdir -p "$pack/rules" "$site/pages"
printf 'periplus_version: 0\npacks:\n  - links@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: links
version: 0.0.1
depends: []
folders:
  pages: ./pages/**
files:
  types:
    lnk:
      endings: [lnk]
      reader: text
      path_values:
        page:
          pattern: '(?<page>\w+)\.lnk$'
          template: '{page}'
YAML
cat >"$pack/rules/links.yaml" <<'YAML'
node_types:
- name: links.page
  id_namespace: links.page
- name: links.widget
  id_namespace: links.widget
- name: links.gadget
  id_namespace: links.gadget
edge_kinds:
- kind: uses
  from: links.page
  to: [links.widget, links.gadget]
rules:
- rule: page
  reads: file
  in: [pages]
  match: {file: '*', filetype: lnk, text: '\A'}
  id: {template: '{page}'}
  emits: [{node: {type: links.page}}]
  confidence: declared
- rule: widget
  reads: file
  in: [pages]
  match: {file: '*', filetype: lnk, text: '(?m)^widget (?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: links.widget}}]
  confidence: declared
- rule: gadget
  reads: file
  in: [pages]
  match: {file: '*', filetype: lnk, text: '(?m)^gadget (?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: links.gadget}}]
  confidence: declared
- rule: use
  reads: file
  in: [pages]
  match: {file: '*', filetype: lnk, text: '(?m)^use (?<name>\w+)$'}
  id: {template: '{page}'}
  emits:
  - edge:
      kind: uses
      from: this_node
      to: {from: {capture: name}, types: [links.widget, links.gadget], on_miss: unresolved}
  confidence: declared
YAML
printf 'gadget knob\nwidget dial\nuse knob\nuse dial\nuse ghost\n' >"$site/pages/home.lnk"
(cd "$site" && "$PERIPLUS" map --output "$work/a1.json" >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/a2.json" >/dev/null)
cmp "$work/a1.json" "$work/a2.json"
validate "$work/a1.json"
python3 - "$work/a1.json" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
nodes = {node["id"]: node for node in document["nodes"]}
found = {
    (edge["to"], place["line"])
    for edge in document["edges"]
    if edge["kind"] == "uses" and edge["from"] == "links.page::home"
    for place in edge["locations"]
}
expected = {
    ("links.gadget::knob", 3),
    ("links.widget::dial", 4),
    ("links.widget::ghost", 5),
}
assert found == expected, sorted(found ^ expected)
assert nodes["links.gadget::knob"]["state"] == "mapped"
assert "links.widget::knob" not in nodes
assert nodes["links.widget::dial"]["state"] == "mapped"
ghost = nodes["links.widget::ghost"]
assert ghost["state"] == "unresolved" and ghost["type"] == "links.widget", ghost
assert ghost["unresolved_detail"] == {
    "rule": "links/use",
    "searched_for": "ghost",
    "found": "no mapped node of this name",
    "types_tried": ["links.widget", "links.gadget"],
}, ghost
assert "links.gadget::ghost" not in nodes
PY

# (b) Tree references in a planted PHP project.
site="$work/php"
pack="$site/.periplus/packs/calls@0.0.1"
mkdir -p "$pack/rules" "$site/src/App" "$site/src/Lib"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - calls@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: calls
version: 0.0.1
depends: [php_basic]
folders:
  code: ./src/**
YAML
cat >"$pack/rules/calls.yaml" <<'YAML'
edge_kinds:
- kind: calls_planted
  from: php.callable
  to: [php.function, php.method]
rules:
- rule: call_function
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits:
  - edge:
      kind: calls_planted
      from: enclosing_declaration
      to: {types: [php.function], on_miss: unresolved}
  confidence: declared
- rule: call_static
  reads: file
  in: [code]
  match: {reference: scoped_call_expression, name_child: [scope, name], filetype: php}
  emits:
  - edge:
      kind: calls_planted
      from: enclosing_declaration
      to: {types: [php.method], separator: '::', on_miss: unresolved}
  confidence: declared
YAML
cat >"$site/src/Lib/Util.php" <<'PHP'
<?php

namespace App\Lib;

class Util
{
    public static function make()
    {
    }
}

function helper()
{
}
PHP
main="$site/src/App/Main.php"
{
    printf '<?php\n\nnamespace App;\n\nuse App\\Lib\\Util;\nuse App\\Lib as L;\n\n'
    for i in $(seq 1 300); do printf '// filler %s\n' "$i"; done
    cat <<'PHP'
function run()
{
    local();
    L\helper();
    Util::make();
    missing();
}

class Runner
{
    public function go()
    {
        local();
    }
}

function local()
{
}

local();
PHP
} >"$main"
[ "$(wc -l <"$main")" -gt 300 ]
(cd "$site" && "$PERIPLUS" map --output "$work/b1.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/b2.json" >/dev/null)
cmp "$work/b1.json" "$work/b2.json"
validate "$work/b1.json"
python3 - "$work/b1.json" "$work/report.json" "$main" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
report = json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()


def line(text, after=0):
    """The 1-based line of the first line after ``after`` that is exactly ``text``, stripped."""
    return next(n for n, written in enumerate(lines, 1) if n > after and written.strip() == text)


run, go = "php.function::App\\run", "php.method::App\\Runner::go"
expected = {
    (run, "php.function::App\\local", line("local();")),
    (run, "php.function::App\\Lib\\helper", line("L\\helper();")),
    (run, "php.method::App\\Lib\\Util::make", line("Util::make();")),
    (run, "php.function::App\\missing", line("missing();")),
    (go, "php.function::App\\local", line("local();", line("public function go()"))),
}
found = {
    (edge["from"], edge["to"], place["line"])
    for edge in document["edges"]
    if edge["kind"] == "calls_planted"
    for place in edge["locations"]
}
assert found == expected, sorted(found ^ expected)
assert min(n for _, _, n in expected) > 256, expected
nodes = {node["id"]: node for node in document["nodes"]}
for end in ("App\\local", "App\\Lib\\helper"):
    assert nodes[f"php.function::{end}"]["state"] == "mapped", end
assert nodes["php.method::App\\Lib\\Util::make"]["state"] == "mapped"
missing = nodes["php.function::App\\missing"]
assert missing["state"] == "unresolved" and missing["type"] == "php.function", missing
assert missing["unresolved_detail"] == {
    "rule": "calls/call_function",
    "searched_for": "App\\missing",
    "found": "no mapped node of this name",
    "types_tried": ["php.function"],
}, missing
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("calls", "call_function")] == 4 and fires[("calls", "call_static")] == 1, fires
top = len(lines) - next(n for n, w in enumerate(reversed(lines)) if w == "local();")
skipped = [(row["file"], row["line"], row["rule"]) for row in report["skipped"]]
# php_basic states calls too, so its own rule skips the
# top-level call beside the planted rule's; both rows name the same line and nothing else.
assert {(f, l) for f, l, _ in skipped} == {("src/App/Main.php", top)}, (skipped, top)
assert {r for _, _, r in skipped} == {"call_function", "calls_function"}, skipped
assert not report["not_executed"], report["not_executed"]
PY
echo "references ok"
