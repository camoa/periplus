#!/usr/bin/env bash
# Library attachments and drupalSettings keys in a .module file, in the bracket form and in the
# array form. Each attachment and each key starts at the function around it, and a class under src
# provides its array-form key, whether its value is a bare array, a ternary, a call, a cast, a list,
# old array( ) or an array on the next line. A library or a key named by a variable or a subscript,
# and a key nested below a first-level key, at any depth, whatever wraps the array, and with
# drupalSettings again later in the statement, give nothing. A behavior that reads a key meets the node the PHP side made.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/js" "$module/src/Controller"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n  - drupal_js_basic@0.0.1\n' >"$site/.periplus/settings.yml"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/mymodule.libraries.yml" <<'YAML'
one:
  js:
    js/one.js: {}
two: {}
YAML
cat >"$module/mymodule.module" <<'PHP'
<?php

function mymodule_preprocess_page(array &$variables) {
  $variables['#attached']['library'][] = 'mymodule/one';
  $variables['#attached']['drupalSettings']['bracketKey'] = 1;
  $lib = 'mymodule/' . 'hidden';
  $variables['#attached']['library'][] = $lib;
}

function mymodule_build_thing() {
  $key = 'varKey';
  return [
    '#attached' => [
      'library' => ['mymodule/two'],
      'drupalSettings' => [
        'arrayKey' => ['nestedKey' => 1],
        $key => 2,
        $other => ['belowVar' => 1],
        'deepKey' => ['a' => ['b' => ['c' => ['d' => 1]]]],
        'ternKey' => $flag ? ['ternInner' => 1] : [],
        'callKey' => foo(['callInner' => 1]),
        'oldKey' => array('oldInnerA' => 1, 'oldInnerB' => 2),
        'castKey' => (array) ['castInner' => 1],
        'listKey' => ['x', ['listInner' => 1]],
        $var['subKey'] => ['subInner' => 1],
        'nextKey' =>
          ['nextInner' => 1],
      ],
    ],
  ];
}

function mymodule_two_lists() {
  return ['one' => ['#attached' => ['drupalSettings' => ['k1' => ['n' => 1]]]], 'two' => ['#attached' => ['drupalSettings' => ['k2' => 1]]]];
}
PHP
cat >"$module/src/Controller/Page.php" <<'PHP'
<?php

namespace Drupal\mymodule\Controller;

class Page {
  public function view() {
    return ['#attached' => ['drupalSettings' => ['classKey' => ['w' => ['x' => ['y' => ['z' => 1]]]]]]];
  }
}
PHP
cat >"$module/js/one.js" <<'JS'
Drupal.behaviors.mymoduleOne = {
  attach(context) {
    const value = drupalSettings.arrayKey;
  },
};
JS

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
nodes = sorted(n["id"] for n in document["nodes"])
preprocess = "php.function::mymodule_preprocess_page"
build = "php.function::mymodule_build_thing"
page = "php.type::Drupal\\mymodule\\Controller\\Page"
libraries = sorted(e[1:] for e in edges if e[0] == "attaches_library")
assert libraries == [
    (build, "drupal.library::mymodule/two"),
    (preprocess, "drupal.library::mymodule/one"),
], libraries
assert not any("hidden" in n for n in nodes), nodes
two = "php.function::mymodule_two_lists"
settings = [n for n in nodes if n.startswith("drupal.js_setting::")]
assert settings == [
    "drupal.js_setting::arrayKey",
    "drupal.js_setting::bracketKey",
    "drupal.js_setting::callKey",
    "drupal.js_setting::castKey",
    "drupal.js_setting::classKey",
    "drupal.js_setting::deepKey",
    "drupal.js_setting::k1",
    "drupal.js_setting::k2",
    "drupal.js_setting::listKey",
    "drupal.js_setting::nextKey",
    "drupal.js_setting::oldKey",
    "drupal.js_setting::ternKey",
], settings
assert not any("Inner" in n or "subKey" in n for n in nodes), nodes
provides = sorted(e[1:] for e in edges if e[0] == "provides_setting")
assert provides == [
    (build, "drupal.js_setting::arrayKey"),
    (build, "drupal.js_setting::callKey"),
    (build, "drupal.js_setting::castKey"),
    (build, "drupal.js_setting::deepKey"),
    (build, "drupal.js_setting::listKey"),
    (build, "drupal.js_setting::nextKey"),
    (build, "drupal.js_setting::oldKey"),
    (build, "drupal.js_setting::ternKey"),
    (preprocess, "drupal.js_setting::bracketKey"),
    (two, "drupal.js_setting::k1"),
    (two, "drupal.js_setting::k2"),
    (page, "drupal.js_setting::classKey"),
], provides
reads = [e[1:] for e in edges if e[0] == "reads_setting"]
assert reads == [("drupal.js_behavior::mymoduleOne", "drupal.js_setting::arrayKey")], reads
PY
echo "js module attachments ok"
