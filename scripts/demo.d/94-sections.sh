#!/usr/bin/env bash
# Sections a text rule does not read, in a rutter written in the project's own packs folder for an
# invented format: a match that starts inside a declared section gives nothing, and the same words
# before and after it give nodes; a section opened by one of two markers ends at the same marker
# only; a section never closed runs to the end of the file; a rule that names a section under
# reads_sections matches inside it.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
pack="$site/.periplus/packs/scrolls@0.0.1"
mkdir -p "$pack/rules" "$site/scrolls"
printf 'periplus_version: 0\npacks:\n  - scrolls@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: scrolls
version: 0.0.1
depends: []
folders:
  scrolls: ./scrolls
files:
  types:
    scroll:
      endings: [scroll]
      reader: text
      sections:
      - name: remark
        open: '#\['
        close: '\]#'
      - name: quote
        open: '(?<mark>["''])'
        close: '{mark}'
YAML
cat >"$pack/rules/scrolls.yaml" <<'YAML'
node_types:
- name: scrolls.item
  id_namespace: scrolls.item
- name: scrolls.quoted
  id_namespace: scrolls.quoted
rules:
- rule: item
  reads: file
  in: [scrolls]
  match: {file: '*', filetype: scroll, text: 'item (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: scrolls.item}}]
  confidence: declared
- rule: quoted
  reads: file
  in: [scrolls]
  match: {file: '*', filetype: scroll, text: 'item (?<name>\w+)', reads_sections: [quote]}
  id: {from: {capture: name}}
  emits: [{node: {type: scrolls.quoted}}]
  confidence: declared
YAML
cat >"$site/scrolls/one.scroll" <<'TXT'
item alpha
#[ item remarked ]# item beta
" it's item doubled " item gamma
' say "item singled" ' item delta
#[ item unclosed
item after
TXT
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" "$site/scrolls/one.scroll" <<'PY'
import json
import re
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert report["problems"] == [] and report["not_executed"] == [], report
text = open(sys.argv[3]).read()

# A reading of its own: walk the text, and at each place outside a span open one where a marker
# starts; a remark ends after its closer, a quote at the next copy of its own mark.
spans, at = [], 0
while at < len(text):
    if text.startswith("#[", at):
        close = text.find("]#", at + 2)
        kind, end = "remark", (close + 2 if close >= 0 else len(text))
    elif text[at] in "\"'":
        close = text.find(text[at], at + 1)
        kind, end = "quote", (close + 1 if close >= 0 else len(text))
    else:
        at += 1
        continue
    spans.append((kind, at, end))
    at = end
words = [(m.start(), m.group(1)) for m in re.finditer(r"item (\w+)", text)]


def outside(start, reads):
    return all(not (b <= start < e) or kind in reads for kind, b, e in spans)


expected = {
    "scrolls.item": {name for start, name in words if outside(start, ())},
    "scrolls.quoted": {name for start, name in words if outside(start, ("quote",))},
}
found = {
    kind: {n["id"].split("::")[1] for n in document["nodes"] if n["type"] == kind}
    for kind in expected
}
assert found == expected, (found, expected)
# The planted file holds each case: before, between and after sections, inside each kind.
assert {"alpha", "beta", "gamma", "delta"} <= found["scrolls.item"], found
assert not {"remarked", "doubled", "singled", "unclosed", "after"} & found["scrolls.item"], found
assert {"doubled", "singled"} <= found["scrolls.quoted"], found
assert not {"remarked", "unclosed", "after"} & found["scrolls.quoted"], found
PY
echo "sections ok"
