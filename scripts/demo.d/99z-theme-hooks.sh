#!/usr/bin/env bash
# PHP that renders a template links to it. A class renders the theme hook its render array names;
# hook_theme declares that hook, and a template key links it to a template at declared
# confidence while a hook with none links to its default name (underscores to dashes) at inferred
# confidence. node--article--teaser links to the bundle node.article; node--full and node--12
# link to no bundle.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$module/src/Controller" "$module/templates" "$module/config/install"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/src/Controller/CardController.php" <<'EOF2'
<?php

namespace Drupal\mymodule\Controller;

final class CardController {

  public function page(): array {
    return ['#theme' => 'my_card', '#title' => 'x'];
  }

  public function plain(): array {
    return ['#theme' => 'plain_box'];
  }

  public function ghost(): array {
    return ['#theme' => 'ghost_box'];
  }

}
EOF2
cat >"$module/mymodule.module" <<'EOF2'
<?php

function mymodule_theme($existing, $type, $theme, $path): array {
  return [
    'my_card' => [
      'variables' => ['title' => NULL, 'items' => ['a' => [1]]],
      'template' => 'my-card-alt',
    ],
    'plain_box' => [
      'variables' => ['title' => NULL],
    ],
    'lone_hook' => [
      'variables' => ['link' => ['path' => NULL]],
    ],
  ];
}
EOF2
for name in my-card-alt plain-box node--article--teaser node--full node--12; do
    printf '{# A comment first. #}\n<p></p>\n' >"$module/templates/$name.html.twig"
done
printf 'type: article\nname: Article\n' >"$module/config/install/node.type.article.yml"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [], report


def edges(kind):
    return sorted(
        (e["from"], e["to"], e["provenance"][0]["confidence"])
        for e in document["edges"]
        if e["kind"] == kind
    )


controller = "php.type::Drupal\\mymodule\\Controller\\CardController"
assert edges("renders_theme_hook") == [
    (controller, "drupal.theme_hook::ghost_box", "declared"),
    (controller, "drupal.theme_hook::my_card", "declared"),
    (controller, "drupal.theme_hook::plain_box", "declared"),
], edges("renders_theme_hook")
assert edges("theme_hook_template") == [
    ("drupal.theme_hook::lone_hook", "drupal.template::lone-hook", "inferred"),
    ("drupal.theme_hook::my_card", "drupal.template::my-card-alt", "declared"),
    ("drupal.theme_hook::plain_box", "drupal.template::plain-box", "inferred"),
], edges("theme_hook_template")
states = {n["id"]: n["state"] for n in document["nodes"]}
assert states["drupal.theme_hook::ghost_box"] == "referenced", states
assert states["drupal.template::lone-hook"] == "referenced", states
assert "drupal.theme_hook::link" not in states, states
assert edges("suggests_bundle") == [
    ("drupal.template::node--article--teaser", "drupal.bundle::node.article", "inferred"),
], edges("suggests_bundle")
PY
echo "theme hooks ok"
