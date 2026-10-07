#!/usr/bin/env bash
# The bundled webform_basic pack, pinned beside drupal_basic@0.3.0. A handler class in the module's
# src/Plugin/WebformHandler folder with a WebformHandler annotation makes the plugin named by its
# id, joined to its class by plugin_class. An annotation whose id is not quoted text makes no
# plugin and is listed under skipped, and the same annotation on a class outside that folder makes
# nothing. A webform's config file makes the bundle webform_submission.<id> with its label read
# from the key title, a configured_by edge to its config file and a bundle_of edge to the entity
# type webform_submission, which no file declares and so stays referenced. The map and the report
# are byte-identical across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
handlers="$module/src/Plugin/WebformHandler"
mkdir -p "$site/.periplus" "$site/config/sync" "$handlers" "$module/src/Other"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
printf 'id: my_type\ntitle: My form\nelements: ""\n' >"$site/config/sync/webform.webform.my_type.yml"
cat >"$handlers/MyHandler.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\WebformHandler;

use Drupal\webform\Plugin\WebformHandlerBase;

/**
 * @WebformHandler(
 *   id = "my_handler",
 *   label = @Translation("My handler"),
 * )
 */
class MyHandler extends WebformHandlerBase {
}
EOF
cat >"$handlers/ComputedHandler.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\WebformHandler;

use Drupal\webform\Plugin\WebformHandlerBase;

/**
 * @WebformHandler(
 *   id = self::ID,
 *   label = @Translation("Computed"),
 * )
 */
class ComputedHandler extends WebformHandlerBase {
  const ID = 'computed';
}
EOF
cat >"$module/src/Other/NotAHandler.php" <<'EOF'
<?php

namespace Drupal\mymodule\Other;

/**
 * @WebformHandler(
 *   id = "outside",
 * )
 */
class NotAHandler {
}
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - webform_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$site" <<'PY'
import json
import os
import sys

work, site = sys.argv[1], sys.argv[2]
src = "web/modules/custom/mymodule/src"
my_handler = f"{src}/Plugin/WebformHandler/MyHandler.php"
computed = f"{src}/Plugin/WebformHandler/ComputedHandler.php"
outside = f"{src}/Other/NotAHandler.php"
config = "config/sync/webform.webform.my_type.yml"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip().lstrip("* ") == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report

nodes = {n["id"]: (n["state"], n.get("attributes", {}).get("label")) for n in document["nodes"]}
assert nodes == {
    "drupal.bundle::webform_submission.my_type": ("mapped", "My form"),
    "drupal.config::webform.webform.my_type": ("mapped", None),
    "drupal.entity_type::webform_submission": ("referenced", None),
    "drupal.module::mymodule": ("mapped", None),
    "drupal.plugin.webform_handler::my_handler": ("mapped", None),
    "php.type::Drupal\\mymodule\\Other\\NotAHandler": ("mapped", None),
    "php.type::Drupal\\mymodule\\Plugin\\WebformHandler\\ComputedHandler": ("mapped", None),
    "php.type::Drupal\\mymodule\\Plugin\\WebformHandler\\MyHandler": ("mapped", None),
    "php.type::Drupal\\webform\\Plugin\\WebformHandlerBase": ("referenced", None),
}, nodes
kinds = {n["id"]: n["type"] for n in document["nodes"]}
assert kinds["drupal.plugin.webform_handler::my_handler"] == "drupal.webform_handler", kinds

base = "php.type::Drupal\\webform\\Plugin\\WebformHandlerBase"
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("bundle_of", "drupal.bundle::webform_submission.my_type",
     "drupal.entity_type::webform_submission", [(config, 1)]),
    ("configured_by", "drupal.bundle::webform_submission.my_type",
     "drupal.config::webform.webform.my_type", [(config, 1)]),
    ("plugin_class", "drupal.plugin.webform_handler::my_handler",
     "php.type::Drupal\\mymodule\\Plugin\\WebformHandler\\MyHandler",
     [(my_handler, line(my_handler, "@WebformHandler("))]),
    ("inherits", "php.type::Drupal\\mymodule\\Plugin\\WebformHandler\\MyHandler", base,
     [(my_handler, line(my_handler, "class MyHandler extends WebformHandlerBase {"))]),
    ("inherits", "php.type::Drupal\\mymodule\\Plugin\\WebformHandler\\ComputedHandler", base,
     [(computed, line(computed, "class ComputedHandler extends WebformHandlerBase {"))]),
]), edges

skipped = sorted((row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"])
assert skipped == [
    (computed, line(computed, "@WebformHandler("), "webform_handler_from_annotation",
     "key id is not quoted text"),
], skipped
PY
echo "webform pack ok"
