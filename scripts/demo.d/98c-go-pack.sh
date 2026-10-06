#!/usr/bin/env bash
# The bundled Go pack. The project root is a Go module's root, with three packages:
# example.com/app at the root, example.com/app/util, and example.com/app/internal/deep two down.
# Its settings pin go_basic@0.0.3 and give values.module. The map exits 0 with no problems and
# nothing not executed, and holds exactly the function, the method on a pointer receiver under its
# receiver type, the struct and the interface, each under its package's import path. A plain call
# f() in a function or a method is a calls edge to the function of that name in the same package.
# util.Help(), through the plain import "example.com/app/util", and dg.Dig(), through the aliased
# import dg "example.com/app/internal/deep", end on those packages' function nodes. A call into a
# package outside the fixture ends on an unresolved function named by import path and function:
# fmt.Println, github.com/spf13/cobra/v2.Execute after the /v2 path, gopkg.in/yaml.v3.Marshal after
# the .v3 path. The blank import _ "embed" binds nothing, so _.Help(), which Go refuses and which is
# written only to show it, makes nothing, and so does unicode.IsUpper() after the dot import
# . "unicode". "example.com/app/api/v1" binds v1, since only /v2 and up is a version suffix. A bare
# call fmt() of a parameter named fmt ends at example.com/app.fmt, not in the package fmt.
# A method call on a value, s.Serve(), and the chained call
# strings.NewReader("x").Len() add no edge and no node and are listed under skipped with a reason;
# the chained call's inner call is a call of its own. A builtin call makes no node and no edge, a
# method on a generic receiver drops its type parameters, and a test, testdata or vendor file makes
# no node. The map and the report are byte-identical across two runs, the report but for the map
# path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
mkdir -p "$site/.periplus" "$site/util" "$site/internal/deep" "$site/api/v1"
cat >"$site/main.go" <<'EOF'
package main

import (
	_ "embed"
	"fmt"
	. "unicode"
	"strings"

	"example.com/app/api/v1"
	"example.com/app/util"
	dg "example.com/app/internal/deep"
	"github.com/spf13/cobra/v2"
	"gopkg.in/yaml.v3"
)

type Server struct{ name string }

type Handler interface{ Serve() }

func (s *Server) Serve() { helper() }

func helper() {}

func paint(fmt func()) { fmt() }

func main() {
	s := &Server{}
	s.Serve()
	util.Help()
	dg.Dig()
	fmt.Println("x")
	cobra.Execute()
	yaml.Marshal(nil)
	_.Help()
	unicode.IsUpper('a')
	v1.F()
	strings.NewReader("x").Len()
	helper()
}
EOF
cat >"$site/util/util.go" <<'EOF'
package util

func Help() { inner() }

func inner() {}
EOF
printf 'package deep\n\nfunc Dig() {}\n' >"$site/internal/deep/d.go"
printf 'package v1\n\nfunc F() {}\n' >"$site/api/v1/v1.go"
cat >"$site/stack.go" <<'EOF'
package main

type Stack[T any] struct{ items []T }

func (s *Stack[T]) Push(v T) { s.items = append(s.items, v); _ = len(s.items) }

func fresh() []int { return make([]int, 0) }
EOF
# Go builds none of these into the module's packages, so none makes a node.
mkdir -p "$site/testdata" "$site/vendor/github.com/x/y"
printf 'package main\n\nfunc TestMain() {}\n' >"$site/main_test.go"
printf 'package fixture\n\nfunc Fixture() {}\n' >"$site/testdata/f.go"
printf 'package y\n\nfunc Vendored() {}\n' >"$site/vendor/github.com/x/y/z.go"
printf 'periplus_version: 0\npacks:\n  - go_basic@0.0.3\nvalues:\n  module: example.com/app\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$site/main.go" <<'PY'
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
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report

nodes = {n["id"]: n["state"] for n in document["nodes"]}
# No node for append, len or make, for the test, testdata or vendor file; Push drops [T].
mapped = sorted(node for node, state in nodes.items() if state == "mapped")
assert mapped == [
    "go.function::example.com/app.fresh",
    "go.function::example.com/app.helper",
    "go.function::example.com/app.main",
    "go.function::example.com/app.paint",
    "go.function::example.com/app/api/v1.F",
    "go.function::example.com/app/internal/deep.Dig",
    "go.function::example.com/app/util.Help",
    "go.function::example.com/app/util.inner",
    "go.interface::example.com/app.Handler",
    "go.method::example.com/app.Server.Serve",
    "go.method::example.com/app.Stack.Push",
    "go.struct::example.com/app.Server",
    "go.struct::example.com/app.Stack",
], mapped
unresolved = sorted(node for node, state in nodes.items() if state == "unresolved")
assert unresolved == [
    "go.function::example.com/app.fmt",
    "go.function::fmt.Println",
    "go.function::github.com/spf13/cobra/v2.Execute",
    "go.function::gopkg.in/yaml.v3.Marshal",
    "go.function::strings.NewReader",
], unresolved
assert len(nodes) == len(mapped) + len(unresolved), nodes

main_fn = "go.function::example.com/app.main"
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("calls", main_fn, "go.function::example.com/app.helper", [("main.go", line("helper()"))]),
    ("calls", main_fn, "go.function::example.com/app/util.Help", [("main.go", line("util.Help()"))]),
    ("calls", main_fn, "go.function::example.com/app/internal/deep.Dig",
     [("main.go", line("dg.Dig()"))]),
    ("calls", main_fn, "go.function::fmt.Println", [("main.go", line('fmt.Println("x")'))]),
    ("calls", main_fn, "go.function::example.com/app/api/v1.F", [("main.go", line("v1.F()"))]),
    ("calls", "go.function::example.com/app.paint", "go.function::example.com/app.fmt",
     [("main.go", line("func paint(fmt func()) { fmt() }"))]),
    ("calls", main_fn, "go.function::github.com/spf13/cobra/v2.Execute",
     [("main.go", line("cobra.Execute()"))]),
    ("calls", main_fn, "go.function::gopkg.in/yaml.v3.Marshal",
     [("main.go", line("yaml.Marshal(nil)"))]),
    ("calls", main_fn, "go.function::strings.NewReader",
     [("main.go", line('strings.NewReader("x").Len()'))]),
    ("calls", "go.function::example.com/app/util.Help", "go.function::example.com/app/util.inner",
     [("util/util.go", 3)]),
    ("calls", "go.method::example.com/app.Server.Serve", "go.function::example.com/app.helper",
     [("main.go", line("func (s *Server) Serve() { helper() }"))]),
]), edges

# s.Serve(), _.Help() and unicode.IsUpper(): no import binds s, _ or unicode. The chained call is
# not a written name.
none_holds = "no resolution step holds for function"
skipped = sorted((row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"])
assert skipped == sorted([
    ("main.go", line("s.Serve()"), "calls", none_holds),
    ("main.go", line("_.Help()"), "calls", none_holds),
    ("main.go", line("unicode.IsUpper('a')"), "calls", none_holds),
    ("main.go", line('strings.NewReader("x").Len()'), "calls", "function is not a written name"),
]), skipped
PY
echo "go pack ok"
