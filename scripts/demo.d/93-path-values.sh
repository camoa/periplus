#!/usr/bin/env bash
# Values from a file's path, in a rutter written in the project's own packs folder for invented
# formats: two files of one name in two folders give two nodes named by their paths, each with one
# location; a node per data file named by its path with the ending dropped, the separators replaced
# and the case raised; a data file gives a node named by its parent folder; a text match gives a node
# named by a path value joined with a capture, and an edge end built the same way reaches that node.
# An edge end whose template names an empty capture makes no edge and no node.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
pack="$site/.periplus/packs/decks@0.0.1"
mkdir -p "$pack/rules" "$site/shelf/alpha" "$site/shelf/beta"
printf 'periplus_version: 0\npacks:\n  - decks@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: decks
version: 0.0.1
depends: []
folders:
  shelf: ./shelf/*
files:
  types:
    box:
      endings: [box]
      reader: data
      format: yaml
      path_values:
        place:
          pattern: '^shelf/(?<folder>[^/]+)/[^/]+$'
          template: '{folder}'
        where:
          pattern: '^(?<path>.+)\.box$'
          template: '{path}'
          normalize: [{replace: '/', with: '.'}]
          case: upper
    cards:
      endings: [cards]
      reader: text
      path_values:
        deck:
          pattern: '/(?<folder>[^/]+)/[^/]+$'
          template: '{folder}'
YAML
cat >"$pack/rules/decks.yaml" <<'YAML'
node_types:
- name: decks.box
  id_namespace: decks.box
- name: decks.place
  id_namespace: decks.place
- name: decks.crate
  id_namespace: decks.crate
- name: decks.card
  id_namespace: decks.card
edge_kinds:
- kind: needs
  from: decks.card
  to: decks.card
rules:
- rule: box_file
  reads: file
  in: [shelf]
  match: {file: '*', filetype: box}
  id: {from: file_stem, template: '{place}/{file_stem}'}
  emits: [{node: {type: decks.box}}]
  confidence: declared
- rule: box_place
  reads: file
  in: [shelf]
  match: {file: '*', filetype: box}
  id: {template: '{place}'}
  emits: [{node: {type: decks.place}}]
  confidence: declared
- rule: box_path
  reads: file
  in: [shelf]
  match: {file: '*', filetype: box}
  id: {template: '{where}'}
  emits: [{node: {type: decks.crate}}]
  confidence: declared
- rule: card
  reads: file
  in: [shelf]
  match:
    file: '*'
    filetype: cards
    text: '(?m)^card (?<name>\w+)(?: needs (?<needs>\w*))?$'
  id: {template: '{deck}.{name}'}
  emits: [{node: {type: decks.card}}]
  confidence: declared
- rule: card_needs
  reads: file
  in: [shelf]
  match:
    file: '*'
    filetype: cards
    text: '(?m)^card (?<name>\w+)(?: needs (?<needs>\w*))?$'
  id: {template: '{deck}.{name}'}
  emits:
  - edge:
      kind: needs
      from: this_node
      to: {template: '{deck}.{needs}'}
  confidence: declared
YAML
printf 'size: 1\n' >"$site/shelf/alpha/crate.box"
printf 'size: 2\n' >"$site/shelf/beta/crate.box"
# The last card's "needs" is empty: a trailing space after it.
printf 'card ace\ncard king needs ace\ncard queen needs \n' >"$site/shelf/alpha/hand.cards"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" "$site" <<'PY'
import json
import os
import re
import sys

document, report, site = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
assert report["problems"] == [] and report["not_executed"] == [], report
nodes = {node["id"]: node for node in document["nodes"]}

# Expected from the planted files: each box file by folder and stem, each folder once.
boxes = sorted(
    (folder, name.removesuffix(".box"))
    for folder in os.listdir(f"{site}/shelf")
    for name in os.listdir(f"{site}/shelf/{folder}")
    if name.endswith(".box")
)
assert len(boxes) == 2 and boxes[0][1] == boxes[1][1], boxes
for folder, stem in boxes:
    node = nodes[f"decks.box::{folder}/{stem}"]
    assert node["locations"] == [{"file": f"shelf/{folder}/{stem}.box", "line": 1}], node
for folder in {folder for folder, _ in boxes}:
    assert nodes[f"decks.place::{folder}"]["state"] == "mapped", folder
assert not [i for i in nodes if i.startswith("decks.box::") and i.count("/") != 1], nodes
# Each box file by its path from the project folder, ending dropped, "/" made ".", upper case.
crates = {"decks.crate::" + f"shelf/{folder}/{stem}".replace("/", ".").upper() for folder, stem in boxes}
assert {i for i in nodes if i.startswith("decks.crate::")} == crates, sorted(nodes)

# Each card line gives its folder joined with its name; a "needs" word gives an edge to the card.
cards, needs = {}, []
for number, line in enumerate(open(f"{site}/shelf/alpha/hand.cards").read().split("\n"), 1):
    words = line.split()
    if words[:1] == ["card"]:
        cards[f"decks.card::alpha.{words[1]}"] = number
        if len(words) == 4:
            needs.append((f"decks.card::alpha.{words[1]}", f"decks.card::alpha.{words[3]}"))
for card, number in cards.items():
    assert nodes[card]["locations"] == [{"file": "shelf/alpha/hand.cards", "line": number}], card
edges = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "needs"}
assert edges == set(needs) and needs, (edges, needs)
for _, target in needs:
    assert nodes[target]["state"] == "mapped", nodes[target]
assert not [i for i in nodes if i.endswith(".")], sorted(nodes)
PY

# A path value named like a value the engine fills is a pack problem naming the pack, the file and
# the name, with the exit of an unreadable rule file.
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.PACK_RULES_UNREADABLE))')"
sed -i 's/^        place:$/        file_stem:/; s/{place}/{file_stem}/g' "$pack/pack.yaml" "$pack/rules/decks.yaml"
status=0
(cd "$site" && "$PERIPLUS" map --output "$work/clash.json" --format json >"$work/clash.report.json") \
    || status=$?
[ "$status" -eq "$code" ] && [ ! -e "$work/clash.json" ] || { echo "expected exit $code, got $status"; exit 1; }
python3 - "$work/clash.report.json" "$code" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
assert any(
    p["code"] == code and p["detail"] == {"pack": "decks", "file": "pack.yaml", "name": "file_stem"}
    for p in report["problems"]
), report["problems"]
PY
echo "path values ok"
