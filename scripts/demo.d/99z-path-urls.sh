#!/usr/bin/env bash
# A URL written as a path string links to the path node the route serves. Url::fromUserInput and
# Url::fromUri('internal:...') of /my/path each link to drupal.url_path::/my/path, which the route
# mymod.page serves.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymod"
mkdir -p "$site/.periplus" "$module/src/Controller"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymod.info.yml"
cat >"$module/mymod.routing.yml" <<'EOF2'
mymod.page:
  path: '/my/path'
  defaults:
    _controller: '\Drupal\mymod\Controller\LinkController::page'
EOF2
cat >"$module/src/Controller/LinkController.php" <<'EOF2'
<?php

namespace Drupal\mymod\Controller;

use Drupal\Core\Url;

class LinkController {

  public function page() {
    $a = Url::fromUserInput('/my/path');
    $b = Url::fromUri('internal:/my/path');
    return [$a, $b];
  }

}
EOF2
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

controller = "php.type::Drupal\\mymod\\Controller\\LinkController"
path = "drupal.url_path::/my/path"
links = sorted(
    (e["from"], e["to"], tuple(sorted(p["rule"] for p in e["provenance"])))
    for e in document["edges"]
    if e["kind"] == "links_to_path"
)
assert links == [(controller, path, ("internal_uri_url_call", "user_input_url_call"))], links
serves = sorted((e["from"], e["to"]) for e in document["edges"] if e["kind"] == "route_serves_path")
assert serves == [("drupal.route::mymod.page", path)], serves
PY
echo "path urls ok"
