#!/usr/bin/env bash
# drupal_basic maps a procedural hook by its function's name: the first part of the file name, an
# underscore, then the hook. A planted site pins drupal_basic. In mymod.module, mymod_cron,
# mymod_form_alter and mymod_settings_submit give the hook nodes cron, form_alter and
# settings_submit, each at confidence inferred with an implements_hook edge from its function at
# confidence inferred; a form callback reads as a hook, a stated gap. helper_thing does not start
# with mymod_, so it makes no hook, no edge and no skipped row. In mytheme.theme, mytheme_preprocess_node gives the hook
# preprocess_node. No hook node has an empty id.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymod/mymod.module"
theme="$site/web/themes/custom/mytheme/mytheme.theme"
mkdir -p "$site/.periplus" "$(dirname "$module")" "$(dirname "$theme")"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
cat >"$module" <<'PHP'
<?php

function mymod_cron() {
}

function mymod_form_alter(&$form) {
}

function mymod_settings_submit($form) {
}

function helper_thing() {
}
PHP
cat >"$theme" <<'PHP'
<?php

function mytheme_preprocess_node(&$variables) {
}
PHP

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$module" "$theme" <<'PY'
import json
import os
import sys

work, module, theme = sys.argv[1:]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]
# The include-hook rules read every PHP file under theme_root, and their theme_name path value
# fits .inc files only, so the plain .theme file leaves exactly these two skipped rows.
assert sorted((row["rule"], row["reason"]) for row in report["skipped"]) == [
    ("hook_from_theme_include", "the id source theme_name is absent"),
    ("theme_include_implements_hook", "the id source theme_name is absent"),
], report["skipped"]


def line(path, text):
    return next(n for n, found in enumerate(open(path).read().splitlines(), 1) if found == text)


def where(path):
    return os.path.relpath(path, os.path.join(work, "site"))


expected = {
    ("cron", where(module), line(module, "function mymod_cron() {"), ("inferred",)),
    ("form_alter", where(module), line(module, "function mymod_form_alter(&$form) {"), ("inferred",)),
    ("settings_submit", where(module), line(module, "function mymod_settings_submit($form) {"), ("inferred",)),
    ("preprocess_node", where(theme), line(theme, "function mytheme_preprocess_node(&$variables) {"), ("inferred",)),
}
hooks = {
    (
        node["id"].removeprefix("drupal.hook::"),
        place["file"],
        place["line"],
        tuple(p.get("confidence") for p in node["provenance"]),
    )
    for node in document["nodes"]
    if node["type"] == "drupal.hook"
    for place in node["locations"]
}
assert hooks == expected, sorted(hooks ^ expected)
assert all(node["id"] != "drupal.hook::" for node in document["nodes"]), "empty hook id"

prefix = {"cron": "mymod", "form_alter": "mymod", "settings_submit": "mymod"}
edges = sorted(
    (edge["kind"], edge["from"], edge["to"], [p["confidence"] for p in edge["provenance"]])
    for edge in document["edges"]
)
wanted = sorted(
    (
        "implements_hook",
        f"php.function::{prefix.get(hook, 'mytheme')}_{hook}",
        f"drupal.hook::{hook}",
        ["inferred"],
    )
    for hook, _, _, _ in expected
)
assert edges == wanted, edges
assert all("helper_thing" not in edge["from"] for edge in document["edges"]), edges
PY
echo "drupal hooks ok"
