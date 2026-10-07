#!/usr/bin/env bash
# The bundled drush_basic pack, pinned beside drupal_basic@0.3.0. In a command class below the
# module's src folder, a method with Drush's Command attribute, one with the Consolidation Command
# attribute it extends, and one with a @command tag in its docblock each make the command named by
# its name, with a command_method edge to the method and a command_class edge to its class. The
# tag's edges name the class from the file's path. An attribute with no named argument name makes
# no command and is listed under skipped. The map and the report are byte-identical across two
# runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
commands="$module/src/Drush/Commands"
mkdir -p "$site/.periplus" "$commands"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$commands/MyCommands.php" <<'EOF'
<?php

namespace Drupal\mymodule\Drush\Commands;

use Drush\Attributes as CLI;
use Drush\Commands\DrushCommands;

final class MyCommands extends DrushCommands {

  #[CLI\Command(name: 'mymodule:sync')]
  public function sync(): void {
  }

  /**
   * Runs the old way.
   *
   * @command mymodule:old
   */
  public function old(): void {
  }

  #[CLI\Command('mymodule:positional')]
  public function positional(): void {
  }

}
EOF
cat >"$commands/OtherCommands.php" <<'EOF'
<?php

namespace Drupal\mymodule\Drush\Commands;

use Consolidation\AnnotatedCommand\Attributes\Command;

final class OtherCommands {

  #[Command(name: 'mymodule:other')]
  public function other(): void {
  }

}
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drush_basic@0.0.1\n' \
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
folder = "web/modules/custom/mymodule/src/Drush/Commands"
mine, other = f"{folder}/MyCommands.php", f"{folder}/OtherCommands.php"
my_class = "php.type::Drupal\\mymodule\\Drush\\Commands\\MyCommands"
other_class = "php.type::Drupal\\mymodule\\Drush\\Commands\\OtherCommands"
my_method = "php.method::Drupal\\mymodule\\Drush\\Commands\\MyCommands::"
other_method = "php.method::Drupal\\mymodule\\Drush\\Commands\\OtherCommands::other"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip().lstrip("* ") == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drush.command::mymodule:old": ("drush.command", "mapped"),
    "drush.command::mymodule:other": ("drush.command", "mapped"),
    "drush.command::mymodule:sync": ("drush.command", "mapped"),
    my_method + "old": ("php.method", "mapped"),
    my_method + "positional": ("php.method", "mapped"),
    my_method + "sync": ("php.method", "mapped"),
    other_method: ("php.method", "mapped"),
    my_class: ("php.class", "mapped"),
    other_class: ("php.class", "mapped"),
    "php.type::Drush\\Commands\\DrushCommands": ("php.class_like", "referenced"),
}, nodes

sync = [(mine, line(mine, "#[CLI\\Command(name: 'mymodule:sync')]"))]
old = [(mine, line(mine, "@command mymodule:old"))]
other_at = [(other, line(other, "#[Command(name: 'mymodule:other')]"))]
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("command_method", "drush.command::mymodule:sync", my_method + "sync", sync),
    ("command_class", "drush.command::mymodule:sync", my_class, sync),
    ("command_method", "drush.command::mymodule:old", my_method + "old", old),
    ("command_class", "drush.command::mymodule:old", my_class, old),
    ("command_method", "drush.command::mymodule:other", other_method, other_at),
    ("command_class", "drush.command::mymodule:other", other_class, other_at),
    ("contains", my_class, my_method + "sync",
     [(mine, line(mine, "public function sync(): void {"))]),
    ("contains", my_class, my_method + "old", [(mine, line(mine, "public function old(): void {"))]),
    ("contains", my_class, my_method + "positional",
     [(mine, line(mine, "public function positional(): void {"))]),
    ("contains", other_class, other_method,
     [(other, line(other, "public function other(): void {"))]),
    ("inherits", my_class, "php.type::Drush\\Commands\\DrushCommands",
     [(mine, line(mine, "final class MyCommands extends DrushCommands {"))]),
]), edges

skipped = sorted((row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"])
assert skipped == [
    (mine, line(mine, "#[CLI\\Command('mymodule:positional')]"), "command_from_attribute",
     "argument name is missing"),
], skipped
PY
echo "drush pack ok"
