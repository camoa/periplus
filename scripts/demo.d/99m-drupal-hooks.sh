#!/usr/bin/env bash
# drupal_basic maps a procedural hook by its function's name: the first part of the file name, an
# underscore, then the hook. A planted site pins drupal_basic. In mymod.module, mymod_cron,
# mymod_form_alter and mymod_settings_submit give the hook nodes cron, form_alter and
# settings_submit, each at confidence inferred with an implements_hook edge from its function at
# confidence inferred; a form callback reads as a hook, a stated gap. helper_thing does not start
# with mymod_, so it makes no hook, no edge and no skipped row. In my_theme.theme,
# my_theme_preprocess_page gives the hook preprocess_page. In includes/content.theme,
# my_theme_preprocess_node gives preprocess_node by the theme's folder name, and other_helper
# gives nothing. In preprocess/html.preprocess.inc, my_theme_preprocess_html gives preprocess_html
# the same way. Each theme hook carries one provenance row. In mymod.post_update.php,
# mymod_post_update_fix_things gives the hook post_update_NAME, and in mymod.deploy.php,
# mymod_deploy_seed gives deploy_NAME. The include rules find no theme_name for my_theme.theme, so
# it leaves exactly one skipped row per include rule. No hook node has an empty id.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymod/mymod.module"
info="$site/web/themes/custom/my_theme/my_theme.info.yml"
theme="$site/web/themes/custom/my_theme/my_theme.theme"
content="$site/web/themes/custom/my_theme/includes/content.theme"
include="$site/web/themes/custom/my_theme/preprocess/html.preprocess.inc"
post_update="$site/web/modules/custom/mymod/mymod.post_update.php"
deploy="$site/web/modules/custom/mymod/mymod.deploy.php"
mkdir -p "$site/.periplus" "$(dirname "$module")" "$(dirname "$include")" "$(dirname "$content")"
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
printf 'name: My theme\ntype: theme\ncore_version_requirement: ^11\n' >"$info"
cat >"$theme" <<'PHP'
<?php

function my_theme_preprocess_page(&$variables) {
}
PHP
cat >"$content" <<'PHP'
<?php

function my_theme_preprocess_node(&$variables) {
}

function other_helper() {
}
PHP
cat >"$include" <<'PHP'
<?php

function my_theme_preprocess_html(&$variables) {
}
PHP
cat >"$post_update" <<'PHP'
<?php

function mymod_post_update_fix_things(&$sandbox) {
}
PHP
cat >"$deploy" <<'PHP'
<?php

function mymod_deploy_seed(&$sandbox) {
}
PHP

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" "$module" "$theme" "$content" "$include" "$post_update" "$deploy" <<'PY'
import json
import os
import sys

work, module, theme, content, include, post_update, deploy = sys.argv[1:]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert not report["problems"], report["problems"]
assert not report["not_executed"], report["not_executed"]
# The include-hook rules find no theme_name in the theme's own .theme file: one row each, no more.
skipped = sorted((row["file"], row["rule"], row["reason"]) for row in report["skipped"])
own = "web/themes/custom/my_theme/my_theme.theme"
assert skipped == [
    (own, "hook_from_theme_include", "the id source theme_name is absent"),
    (own, "theme_include_implements_hook", "the id source theme_name is absent"),
], skipped


def line(path, text):
    return next(n for n, found in enumerate(open(path).read().splitlines(), 1) if found == text)


def where(path):
    return os.path.relpath(path, os.path.join(work, "site"))


expected = {
    ("cron", where(module), line(module, "function mymod_cron() {"), ("inferred",)),
    ("form_alter", where(module), line(module, "function mymod_form_alter(&$form) {"), ("inferred",)),
    ("settings_submit", where(module), line(module, "function mymod_settings_submit($form) {"), ("inferred",)),
    ("preprocess_page", where(theme), line(theme, "function my_theme_preprocess_page(&$variables) {"), ("inferred",)),
    ("preprocess_node", where(content), line(content, "function my_theme_preprocess_node(&$variables) {"), ("inferred",)),
    ("preprocess_html", where(include), line(include, "function my_theme_preprocess_html(&$variables) {"), ("inferred",)),
    ("post_update_NAME", where(post_update), line(post_update, "function mymod_post_update_fix_things(&$sandbox) {"), ("inferred",)),
    ("deploy_NAME", where(deploy), line(deploy, "function mymod_deploy_seed(&$sandbox) {"), ("inferred",)),
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
# A post-update or deploy hook keeps the function's own name in the function's id, not the hook's.
function = {"post_update_NAME": "mymod_post_update_fix_things", "deploy_NAME": "mymod_deploy_seed"}
edges = sorted(
    (edge["kind"], edge["from"], edge["to"], [p["confidence"] for p in edge["provenance"]])
    for edge in document["edges"]
)
wanted = sorted(
    (
        "implements_hook",
        f"php.function::{function.get(hook) or prefix.get(hook, 'my_theme') + '_' + hook}",
        f"drupal.hook::{hook}",
        ["inferred"],
    )
    for hook, _, _, _ in expected
)
assert edges == wanted, edges
assert all("helper_thing" not in edge["from"] for edge in document["edges"]), edges
assert all("other_helper" not in edge["from"] for edge in document["edges"]), edges
assert all("other_helper" not in node["id"] for node in document["nodes"] if node["type"] == "drupal.hook")
PY
echo "drupal hooks ok"
