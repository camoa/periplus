#!/usr/bin/env bash
# PHP calls: php_basic's two reference rules on a planted project. Each plain call and each static
# call gives a calls edge from the function or method around it, by exact value: through a
# namespace alias, a full name, a used class, and to an unresolved end with its searched_for when
# the project holds no such function or method. A method call on an object, a call on self or
# static, and a call outside any function give nothing; the last two are listed under skipped. A
# function imported by `use function x as y` is not bound, so y() resolves under the namespace.
# The constructs isset($x) and empty($y), which the grammar parses as calls, and the builtin
# strlen('x') give no edge and no node: php_basic's calls_function lists them under skip_names.
# Every call sits past line 256. Then a planted rutter on php_basic narrows php_basic's source to
# src and reads an extra folder only with its reference rule: the call there is skipped and gets
# no phantom source. That rule writes its end in the one-type form, to: {type: ...}.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
mkdir -p "$site/.periplus" "$site/src/App" "$site/src/Lib"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
cat >"$site/src/Lib/Util.php" <<'EOF'
<?php

namespace App\Lib;

function helper()
{
}

class Util
{
    public static function make()
    {
        helper();
    }
}
EOF
main="$site/src/App/Main.php"
{
    printf '<?php\n\n'
    for i in $(seq 1 280); do printf '// padding line %s\n' "$i"; done
    cat <<'EOF'
namespace App;

use App\Lib\Util;
use App\Lib as L;
use function App\Lib\helper as h;

local();

function local()
{
}

function caller($obj)
{
    local();
    L\helper();
    \App\Lib\helper();
    Util::make();
    \Drupal::service('x');
    missing();
    strlen('x');
    h();
    isset($x);
    empty($y);
    $obj->m();
    $f = function () {
        local();
    };
}

class Main
{
    public function run()
    {
        local();
        $this->other();
        self::other();
        static::other();
        Util::make();
        Util::absent();
    }

    public function other()
    {
    }
}
EOF
} >"$main"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/again.json" --format json >/dev/null)
cmp "$work/map.json" "$work/again.json"
"$python" - "$work/map.json" "$ROOT/src/periplus/contract/schema/map.schema.json" <<'PY'
import json
import sys

from jsonschema import Draft202012Validator

Draft202012Validator(json.load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1])))
PY

python3 - "$work/map.json" "$work/report.json" "$main" "$site/src/Lib/Util.php" <<'PY'
import json
import re
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
lines = {f: open(p).read().splitlines() for f, p in (("main", sys.argv[3]), ("util", sys.argv[4]))}


def at(file, pattern):
    found = [n for n, s in enumerate(lines[file], 1) if re.fullmatch(pattern, s)]
    assert found, pattern
    return found


assert report["not_executed"] == [] and report["problems"] == [], report
F, M = "php.function::", "php.method::"
caller, run = F + "App\\caller", M + "App\\Main::run"
# The closure's local() is drawn from caller; the method's from run.
closure, method = at("main", r"        local\(\);")
expected = {  # (from, to): (lines, searched_for when unresolved)
    (caller, F + "App\\local"): (at("main", r"    local\(\);") + [closure], None),
    (caller, F + "App\\Lib\\helper"): (at("main", r"    L\\helper\(\);") + at("main", r"    \\App\\Lib\\helper\(\);"), None),
    (caller, M + "App\\Lib\\Util::make"): (at("main", r"    Util::make\(\);"), None),
    (caller, M + "Drupal::service"): (at("main", r"    \\Drupal::service\('x'\);"), "Drupal::service"),
    (caller, F + "App\\missing"): (at("main", r"    missing\(\);"), "App\\missing"),
    (caller, F + "App\\h"): (at("main", r"    h\(\);"), "App\\h"),
    (run, F + "App\\local"): ([method], None),
    (run, M + "App\\Lib\\Util::make"): (at("main", r"        Util::make\(\);"), None),
    (run, M + "App\\Lib\\Util::absent"): (at("main", r"        Util::absent\(\);"), "App\\Lib\\Util::absent"),
    (M + "App\\Lib\\Util::make", F + "App\\Lib\\helper"): (at("util", r"        helper\(\);"), None),
}
assert min(n for ls, _ in expected.values() for n in ls if n > 20) > 256

calls = [e for e in document["edges"] if e["kind"] == "calls"]
found = {(e["from"], e["to"]): sorted(loc["line"] for loc in e["locations"]) for e in calls}
assert len(found) == len(calls), calls
assert found == {k: sorted(ls) for k, (ls, _) in expected.items()}, (found, expected)
for e in calls:
    rule = "calls_static_method" if "::" in e["to"].split("::", 1)[1] else "calls_function"
    assert e["provenance"] == [{"confidence": "declared", "pack": "php_basic", "rule": rule}], e
nodes = {n["id"]: n for n in document["nodes"]}
for (_, end), (_, searched) in expected.items():
    node = nodes[end]
    if searched is None:
        assert node["state"] == "mapped", node
    else:
        assert node["state"] == "unresolved" and node["type"] == end.split("::")[0], node
        assert node["unresolved_detail"]["searched_for"] == searched, node
unresolved = sum(s is not None for _, s in expected.values())
constructs = at("main", r"    isset\(\$x\);") + at("main", r"    empty\(\$y\);") + at("main", r"    strlen\('x'\);")
assert not [e for e in calls if any(loc["line"] in constructs for loc in e["locations"])]
assert not [n for n in nodes if n.rsplit("\\", 1)[-1] in ("isset", "empty", "strlen")], sorted(nodes)
# A method call on an object gives nothing: no edge sits on its line.
objects = at("main", r"    \$obj->m\(\);") + at("main", r"        \$this->other\(\);")
assert not [e for e in calls if any(loc["line"] in objects for loc in e["locations"])]
skipped = sorted((s["file"], s["line"], s["rule"], s["reason"]) for s in report["skipped"])
assert skipped == [
    ("src/App/Main.php", at("main", r"local\(\);")[0], "calls_function", "no enclosing declaration is mapped"),
    ("src/App/Main.php", at("main", r"        self::other\(\);")[0], "calls_static_method", "scope is not a written name"),
    ("src/App/Main.php", at("main", r"        static::other\(\);")[0], "calls_static_method", "scope is not a written name"),
], skipped
print(f"php calls: {len(calls)} edges, {unresolved} unresolved ends")
PY

# The planted rutter: php_basic's source narrowed to src, an extra folder read only by its
# reference rule, and the end in the one-type form.
pack="$site/.periplus/packs/calls@0.0.1"
mkdir -p "$pack/rules" "$site/extra"
printf 'periplus_version: 0\npacks:\n  - calls@0.0.1\n' >"$site/.periplus/settings.yml"
cat >"$pack/pack.yaml" <<'YAML'
pack: calls
version: 0.0.1
depends: [php_basic]
folders:
  code: ./src/**
  extra: ./extra/**
  # php_basic's source, narrowed so its declaration rules do not read extra.
  source: ./src/**
YAML
cat >"$pack/rules/calls.yaml" <<'YAML'
edge_kinds:
- kind: calls_planted
  from: [php.function, php.method]
  to: [php.function, php.method]
rules:
- rule: call_function
  reads: file
  in: [code, extra]
  match: {reference: function_call_expression, name_child: function, filetype: php, skip_names: [isset, empty, strlen]}
  emits:
  - edge:
      kind: calls_planted
      from: enclosing_declaration
      to: {type: php.function, on_miss: unresolved}
  confidence: declared
YAML
printf '<?php\n\nfunction side()\n{\n    local();\n}\n' >"$site/extra/Side.php"
(cd "$site" && "$PERIPLUS" map --output "$work/planted.json" --format json >"$work/planted.report.json")
python3 - "$work/planted.json" "$work/planted.report.json" "$work/map.json" <<'PY'
import json
import sys

document, report, plain = (json.load(open(f)) for f in sys.argv[1:4])
assert report["not_executed"] == [] and report["problems"] == [], report
planted = {(e["from"], e["to"]): sorted(loc["line"] for loc in e["locations"])
           for e in document["edges"] if e["kind"] == "calls_planted"}
# The same plain calls as php_basic's calls_function, from the same sources.
want = {(e["from"], e["to"]): sorted(loc["line"] for loc in e["locations"])
        for e in plain["edges"] if e["kind"] == "calls" and e["provenance"][0]["rule"] == "calls_function"}
assert planted == want, (planted, want)
assert document["nodes"] and next(n for n in document["nodes"] if n["id"] == "php.function::App\\missing")["type"] == "php.function"
assert not any(n["id"].endswith("::side") for n in document["nodes"]), "phantom source"
assert all("extra/" not in place["file"] for e in document["edges"] for place in e["locations"])
assert ("extra/Side.php", 5, "call_function") in {(s["file"], s["line"], s["rule"]) for s in report["skipped"]}
print("planted rutter: narrowed source skipped, one-type end ok")
PY
echo "php calls ok"
