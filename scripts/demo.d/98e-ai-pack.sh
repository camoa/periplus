#!/usr/bin/env bash
# The bundled ai_basic pack, pinned beside drupal_basic@0.3.0. A class in the module's
# src/Plugin/AiAgent folder with the AiAgent attribute makes the agent named by its id, and a class
# in src/Plugin/AiFunctionCall with the FunctionCall attribute makes the function call named by its
# id; each is joined to its class by plugin_class. A FunctionCall attribute whose id is a class
# constant declared as text makes the plugin that text names. The map and the report are byte-identical
# across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/src/Plugin/AiAgent" "$module/src/Plugin/AiFunctionCall"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/src/Plugin/AiAgent/MyAgent.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AiAgent;

use Drupal\ai_agents\Attribute\AiAgent;
use Drupal\ai_agents\PluginBase\AiAgentBase;
use Drupal\Core\StringTranslation\TranslatableMarkup;

#[AiAgent(
  id: 'my_agent',
  label: new TranslatableMarkup('My agent'),
)]
class MyAgent extends AiAgentBase {
}
EOF
cat >"$module/src/Plugin/AiFunctionCall/MyFunction.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AiFunctionCall;

use Drupal\ai\Attribute\FunctionCall;
use Drupal\ai\Base\FunctionCallBase;
use Drupal\Core\StringTranslation\TranslatableMarkup;

#[FunctionCall(
  id: 'mymodule:my_function',
  function_name: 'my_function',
  name: new TranslatableMarkup('My function'),
)]
class MyFunction extends FunctionCallBase {
}
EOF
cat >"$module/src/Plugin/AiFunctionCall/ComputedFunction.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AiFunctionCall;

use Drupal\ai\Attribute\FunctionCall;
use Drupal\ai\Base\FunctionCallBase;

#[FunctionCall(
  id: self::ID,
)]
class ComputedFunction extends FunctionCallBase {
  const ID = 'computed';
}
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - ai_basic@0.0.1\n' \
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
plugins = "web/modules/custom/mymodule/src/Plugin"
agent = f"{plugins}/AiAgent/MyAgent.php"
function = f"{plugins}/AiFunctionCall/MyFunction.php"
computed = f"{plugins}/AiFunctionCall/ComputedFunction.php"
cls = "php.type::Drupal\\mymodule\\Plugin\\"
agent_base = "php.type::Drupal\\ai_agents\\PluginBase\\AiAgentBase"
function_base = "php.type::Drupal\\ai\\Base\\FunctionCallBase"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip() == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drupal.plugin.ai_agent::my_agent": ("drupal.ai_agent", "mapped"),
    "drupal.plugin.ai_function_call::mymodule:my_function": ("drupal.ai_function_call", "mapped"),
    agent_base: ("php.class_like", "referenced"),
    function_base: ("php.class_like", "referenced"),
    cls + "AiAgent\\MyAgent": ("php.class", "mapped"),
    "drupal.plugin.ai_function_call::computed": ("drupal.ai_function_call", "mapped"),
    cls + "AiFunctionCall\\ComputedFunction": ("php.class", "mapped"),
    cls + "AiFunctionCall\\MyFunction": ("php.class", "mapped"),
}, nodes

edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("plugin_class", "drupal.plugin.ai_agent::my_agent", cls + "AiAgent\\MyAgent",
     [(agent, line(agent, "#[AiAgent("))]),
    ("plugin_class", "drupal.plugin.ai_function_call::mymodule:my_function",
     cls + "AiFunctionCall\\MyFunction", [(function, line(function, "#[FunctionCall("))]),
    ("plugin_class", "drupal.plugin.ai_function_call::computed",
     cls + "AiFunctionCall\\ComputedFunction", [(computed, line(computed, "#[FunctionCall("))]),
    ("inherits", cls + "AiAgent\\MyAgent", agent_base,
     [(agent, line(agent, "class MyAgent extends AiAgentBase {"))]),
    ("inherits", cls + "AiFunctionCall\\MyFunction", function_base,
     [(function, line(function, "class MyFunction extends FunctionCallBase {"))]),
    ("inherits", cls + "AiFunctionCall\\ComputedFunction", function_base,
     [(computed, line(computed, "class ComputedFunction extends FunctionCallBase {"))]),
]), edges

assert report["skipped"] == [], report["skipped"]
PY
echo "ai pack ok"
