#!/usr/bin/env bash
# A call's argument read on a second grammar, whose arguments field holds the expressions with no
# wrapper node and whose strings come in two literal types. A planted pack depending on go_basic
# maps http.HandleFunc("/x", h) to a route node named by argument 0, and Redirect("/x") inside a
# function to a redirects edge from the function to the route that argument names, unresolved
# when no route has that name. An interpreted and a raw string each give a node and an edge; a
# comment before the argument is not one. A variable, a missing and an empty argument each leave
# a row under skipped and no node or edge. RedirectAll("/x") and mux.HandleFunc("/z", h) fail the
# name filter, which matches the whole name, and leave nothing. The map is
# byte-identical across two runs, and the report equal as parsed JSON but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
pack="$site/.periplus/packs/shop@0.0.1"
mkdir -p "$pack/rules"
printf 'periplus_version: 0\npacks:\n  - go_basic@0.0.3\n  - shop@0.0.1\nvalues:\n  module: example.com/app\n' \
    >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: shop
version: 0.0.1
depends: [go_basic]
YAML
cat >"$pack/rules/shop.yaml" <<'YAML'
node_types:
- name: shop.route
  id_namespace: shop.route
edge_kinds:
- kind: redirects
  from: go.function
  to: shop.route
rules:
- rule: route
  reads: file
  in: [source]
  match:
    declaration: call_expression
    name_child: function
    filetype: go
    where: [{name_matches: 'http\.HandleFunc'}]
  id: {from: {argument: 0}}
  emits: [{node: {type: shop.route}}]
  confidence: declared
- rule: redirect
  reads: file
  in: [source]
  match:
    reference: call_expression
    name_child: function
    filetype: go
    where: [{name_matches: Redirect}]
  emits:
  - edge:
      kind: redirects
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [shop.route], on_miss: unresolved}
  confidence: declared
YAML
main="$site/main.go"
cat >"$main" <<'GO'
package main

func main() {
	http.HandleFunc("/x", h)
	http.HandleFunc(`/raw`, h)
	http.HandleFunc(p, h)
	http.HandleFunc()
	http.HandleFunc("", h)
	mux.HandleFunc("/z", h)
}

func send() {
	Redirect("/x")
	Redirect(`/gone`)
	Redirect(/* to */ "/raw")
	Redirect(path)
	Redirect()
	Redirect("")
	RedirectAll("/x")
}
GO

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$main" <<'PY'
import json
import os
import sys

work, main = sys.argv[1], sys.argv[2]
lines = open(main).read().splitlines()


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(text):
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
# Each report names the map it wrote, and the two runs wrote two maps.
assert {**report, "map": ""} == {**again, "map": ""}
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]

routes = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "shop.route"}
assert routes == {
    "shop.route::/x": "mapped",
    "shop.route::/raw": "mapped",
    "shop.route::/gone": "unresolved",
}, routes
send = "go.function::example.com/app.send"
found = {
    (edge["from"], edge["to"], place["line"])
    for edge in document["edges"]
    if edge["kind"] == "redirects"
    for place in edge["locations"]
}
expected = {
    (send, "shop.route::/x", line('Redirect("/x")')),
    (send, "shop.route::/gone", line("Redirect(`/gone`)")),
    (send, "shop.route::/raw", line('Redirect(/* to */ "/raw")')),
}
assert found == expected, sorted(found ^ expected)

skipped = sorted(
    (row["line"], row["rule"], row["reason"])
    for row in report["skipped"]
    if row["rule"] in ("route", "redirect")
)
assert skipped == sorted([
    (line("http.HandleFunc(p, h)"), "route", "argument 0 is not a text literal"),
    (line("http.HandleFunc()"), "route", "argument 0 is missing"),
    (line('http.HandleFunc("", h)'), "route", "argument 0 is empty"),
    (line("Redirect(path)"), "redirect", "argument 0 is not a text literal"),
    (line("Redirect()"), "redirect", "argument 0 is missing"),
    (line('Redirect("")'), "redirect", "argument 0 is empty"),
]), skipped
fires = {(row["pack"], row["rule"]): row["fires"] for row in report["executed"]}
assert fires[("shop", "route")] == 2 and fires[("shop", "redirect")] == 3, fires
PY
echo "call arguments on a second grammar ok"
