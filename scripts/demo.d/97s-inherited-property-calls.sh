#!/usr/bin/env bash
# A call through a property that a parent class assigns. BaseController's constructor assigns
# $this->mailer from a parameter typed Mailer, a short name imported from another namespace, and
# $this->helper from \Drupal::service('my_module.helper'), whose services file names Helper.
# ChildController::notify calls $this->mailer->send(), $this->helper->run() and $this->other->go(),
# where other is assigned from an untyped parameter. The map rules of php_basic and drupal_basic
# give calls edges from notify to Mailer::send and Helper::run, at the calls' lines, in the first
# map pass; go() keeps its call site and gets no calls edge. The call sites take their method
# through enclosing_method and the parameter its type through {qualified: type}: without either,
# no edge is made. No node of the parts' types is unresolved.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src/Mail" "$module/src/Controller"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
cat >"$module/my_module.services.yml" <<'YAML'
services:
  my_module.helper:
    class: Drupal\my_module\Helper
YAML
cat >"$module/src/Helper.php" <<'PHP'
<?php

namespace Drupal\my_module;

class Helper
{
    public function run()
    {
    }
}
PHP
cat >"$module/src/Mail/Mailer.php" <<'PHP'
<?php

namespace Drupal\my_module\Mail;

class Mailer
{
    public function send()
    {
    }
}
PHP
cat >"$module/src/Controller/BaseController.php" <<'PHP'
<?php

namespace Drupal\my_module\Controller;

use Drupal\my_module\Mail\Mailer;

class BaseController
{
    protected $mailer;

    protected $helper;

    protected $other;

    public function __construct(Mailer $mailer, $other)
    {
        $this->mailer = $mailer;
        $this->helper = \Drupal::service('my_module.helper');
        $this->other = $other;
    }
}
PHP
child="$module/src/Controller/ChildController.php"
cat >"$child" <<'PHP'
<?php

namespace Drupal\my_module\Controller;

class ChildController extends BaseController
{
    public function notify()
    {
        $this->mailer->send();
        $this->helper->run();
        $this->other->go();
    }
}
PHP

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$child" <<'PY'
import json
import os
import sys

work, child = sys.argv[1], sys.argv[2]
lines = open(child).read().splitlines()
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]

line = {call: lines.index(f"        $this->{call}();") + 1 for call in ("mailer->send", "helper->run", "other->go")}
notify = "php.method::Drupal\\my_module\\Controller\\ChildController::notify"
calls = sorted(
    (edge["to"], [place["line"] for place in edge["locations"]], [row["rule"] for row in edge["provenance"]])
    for edge in document["edges"]
    if edge["kind"] == "calls" and edge["from"] == notify
)
assert calls == [
    ("php.method::Drupal\\my_module\\Helper::run", [line["helper->run"]], ["calls_through_service_property"]),
    ("php.method::Drupal\\my_module\\Mail\\Mailer::send", [line["mailer->send"]], ["calls_through_assigned_property"]),
], calls

sites = {node["id"]: node["state"] for node in document["nodes"] if node["type"] == "php.call_site"}
site = "php.call_site::Drupal\\my_module\\Controller\\ChildController::notify::$this->{}"
assert sites == {site.format(call): "mapped" for call in line}, sites
edges = {(edge["kind"], edge["from"], edge["to"]) for edge in document["edges"]}
untyped = site.format("other->go")
assert ("has_call_site", notify, untyped) in edges and ("call_site_in", untyped, notify) in edges, edges
typed = (
    "parameter_typed_as",
    "php.parameter::Drupal\\my_module\\Controller\\BaseController::__construct::$mailer",
    "php.parameter_type::Drupal\\my_module\\Controller\\BaseController::$mailer::Drupal\\my_module\\Mail\\Mailer",
)
assert typed in edges, edges

parts = {"php.property", "php.parameter", "php.parameter_type", "php.member_assignment",
         "php.member_assignment_value", "php.call_site"}
states = {(node["type"], node["state"]) for node in document["nodes"] if node["type"] in parts}
assert states == {(kind, "mapped") for kind in parts}, states

passes = [(row["pass"], sorted((fired["pack"], fired["rule"], fired["fires"]) for fired in row["fired"]))
          for row in report["map_passes"]]
assert passes == [
    (1, [("drupal_basic", "calls_through_service_property", 1), ("php_basic", "calls_through_assigned_property", 1)]),
    (2, []),
], passes
PY
echo "inherited property calls ok"
