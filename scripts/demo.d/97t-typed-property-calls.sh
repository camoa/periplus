#!/usr/bin/env bash
# A call through a property whose type the class declares. Page declares $mailer typed Mailer,
# $clock as a promoted constructor parameter typed Clock, $box with a @var Box docblock where Box
# is an alias of Store, and $plain with no type. Page::run calls a method on each through $this.
# php_basic's map rule calls_through_typed_property gives calls edges from run to Mailer::send,
# Clock::now and Store::get, at the calls' lines, at inferred; plain->go() keeps its call site and
# gets no calls edge and no skipped row.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
mkdir -p "$site/.periplus" "$site/src/Service" "$site/src/Web"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
for pair in Mailer:send Clock:now Store:get; do
    cat >"$site/src/Service/${pair%%:*}.php" <<PHP
<?php

namespace App\\Service;

class ${pair%%:*}
{
    public function ${pair##*:}()
    {
    }
}
PHP
done
page="$site/src/Web/Page.php"
cat >"$page" <<'PHP'
<?php

namespace App\Web;

use App\Service\Mailer;
use App\Service\{Clock, Store as Box};

class Page
{
    private Mailer $mailer;

    /** @var Box */
    protected $box;

    protected $plain;

    public function __construct(private readonly Clock $clock)
    {
    }

    public function run(): void
    {
        $this->mailer->send();
        $this->clock->now();
        $this->box->get();
        $this->plain->go();
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
for call in ("mailer->send", "clock->now", "box->get", "plain->go"):
    assert f"        $this->{call}();" in lines, call
line = {call: lines.index(f"        $this->{call}();") + 1 for call in ("mailer->send", "clock->now", "box->get", "plain->go")}

run = "php.method::App\\Web\\Page::run"
calls = sorted(
    (edge["to"], [place["line"] for place in edge["locations"]],
     [(row["rule"], row["confidence"]) for row in edge["provenance"]])
    for edge in document["edges"]
    if edge["kind"] == "calls" and edge["from"] == run
)
made = [("calls_through_typed_property", "inferred")]
assert calls == [
    ("php.method::App\\Service\\Clock::now", [line["clock->now"]], made),
    ("php.method::App\\Service\\Mailer::send", [line["mailer->send"]], made),
    ("php.method::App\\Service\\Store::get", [line["box->get"]], made),
], calls

untyped = "php.call_site::App\\Web\\Page::run::$this->plain->go"
sites = {node["id"]: node["state"] for node in document["nodes"] if node["type"] == "php.call_site"}
assert sites.get(untyped) == "mapped", sites
skipped = [row for row in report["skipped"] if "Page.php" in json.dumps(row)]
assert skipped == [], skipped

passes = [(row["pass"], sorted((fired["pack"], fired["rule"], fired["fires"]) for fired in row["fired"]))
          for row in report["map_passes"]]
assert passes[0] == (1, [("php_basic", "calls_through_typed_property", 3)]), passes
PY
echo "typed property calls ok"
