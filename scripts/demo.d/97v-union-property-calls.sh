#!/usr/bin/env bash
# A call through a property whose declared type is a union. Page declares $a typed Helper|null, $b
# null|Helper, $d Helper|false|null, $e string|Helper and $c Helper|Other, and its constructor
# promotes $f typed Helper|null. $g is typed Helper | null and the promoted $h null | Helper, with
# spaces. Page::run calls a method on each through $this. php_basic's union
# rules mint one php.property_type node ending in App\Service\Helper for each union of one class
# name, and calls_through_typed_property gives calls edges from run to Helper's methods, at the
# calls' lines, at inferred. Helper|Other names two classes: no node, no calls edge, no skipped row.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
mkdir -p "$site/.periplus" "$site/src/Service" "$site/src/Web"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
cat >"$site/src/Service/Helper.php" <<'PHP'
<?php

namespace App\Service;

class Helper
{
    public function a() {}
    public function b() {}
    public function c() {}
    public function d() {}
    public function e() {}
    public function f() {}
    public function g() {}
    public function h() {}
}
PHP
cat >"$site/src/Service/Other.php" <<'PHP'
<?php

namespace App\Service;

class Other
{
    public function c() {}
}
PHP
page="$site/src/Web/Page.php"
cat >"$page" <<'PHP'
<?php

namespace App\Web;

use App\Service\Helper;
use App\Service\Other;

class Page
{
    private Helper|null $a;

    private null|Helper $b;

    private Helper|Other $c;

    private Helper|false|null $d;

    private string|Helper $e;

    private Helper | null $g;

    public function __construct(private Helper|null $f, private null | Helper $h)
    {
    }

    public function run(): void
    {
        $this->a->a();
        $this->b->b();
        $this->c->c();
        $this->d->d();
        $this->e->e();
        $this->f->f();
        $this->g->g();
        $this->h->h();
    }
}
PHP

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$page" <<'PY'
import json
import os
import sys

work, page = sys.argv[1], sys.argv[2]
lines = open(page).read().splitlines()
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]
names = "abcdefgh"
line = {name: lines.index(f"        $this->{name}->{name}();") + 1 for name in names}

run = "php.method::App\\Web\\Page::run"
calls = sorted(
    (edge["to"], [place["line"] for place in edge["locations"]],
     [(row["rule"], row["confidence"]) for row in edge["provenance"]])
    for edge in document["edges"]
    if edge["kind"] == "calls" and edge["from"] == run
)
made = [("calls_through_typed_property", "inferred")]
assert calls == [(f"php.method::App\\Service\\Helper::{name}", [line[name]], made) for name in "abdefgh"], calls

types = sorted(node["id"] for node in document["nodes"] if node["type"] == "php.property_type")
assert types == [f"php.property_type::App\\Web\\Page::${name}::App\\Service\\Helper" for name in "abdefgh"], types

site = "php.call_site::App\\Web\\Page::run::$this->c->c"
sites = {node["id"]: node["state"] for node in document["nodes"] if node["type"] == "php.call_site"}
assert sites.get(site) == "mapped", sites
skipped = [row for row in report["skipped"] if "Page.php" in json.dumps(row)]
assert skipped == [], skipped
PY
echo "union property calls ok"
