#!/usr/bin/env bash
# A path written whole as a Twig attribute value or a JS string links to the path node the route
# serves. data-endpoint="/x/y" in a template and "/x/y" in a script each link to
# drupal.url_path::/x/y, which the route mymod.xy serves. A value that does not start with / or
# that holds a space links nowhere, and so does a path joined with + on either side at any distance,
# across a line break or through a parenthesis, such as '/x/joined/' + id or base + '/api/x', and
# so does one in a comment or a Twig set statement. A whole path in an assignment, a list, a ternary
# branch or a call argument on its own line links.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymod"
mkdir -p "$site/.periplus" "$module/templates" "$module/js"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymod.info.yml"
cat >"$module/mymod.routing.yml" <<'EOF'
mymod.xy:
  path: '/x/y'
  defaults:
    _controller: '\Drupal\mymod\Controller\XyController::page'
EOF
cat >"$module/templates/xy-button.html.twig" <<'EOF'
<button data-endpoint="/x/y" data-relative="x/y" title="/x y">Go</button>
{# <a href="/x/commented">no</a> #}
{% set url = '/x/set' %}
EOF
cat >"$module/js/xy.js" <<'EOF'
(function () {
  let endpoint = "/x/y";
  let relative = 'x/y';
  let label = '/x y';
  let joined = fetch('/x/joined/' + endpoint);
  let after = base + '/api/x';
  let before = '/api/y/' + id;
  let across = base +
    '/api/n';
  let spaced = base +   '/api/s';
  let tight = base+'/api/t';
  let paren = base + ('/api/p');
  x = '/x/y';
  let list = ['/x/y'];
  let pick = flag ? '/x/y' : other;
  fetch(
    '/x/y'
  );
  // fetch('/x/commented');
  fetch(endpoint);
})();
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n' >"$site/.periplus/settings.yml"
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [], report

path = "drupal.url_path::/x/y"
links = sorted(
    (e["kind"], e["from"], e["to"])
    for e in document["edges"]
    if e["kind"] in ("links_to_path", "script_links_to_path")
)
assert links == [
    ("links_to_path", "drupal.template::xy-button", path),
    ("script_links_to_path", "js.file::web/modules/custom/mymod/js/xy.js", path),
], links
script_lines = sorted(
    location["line"]
    for e in document["edges"]
    if e["kind"] == "script_links_to_path"
    for location in e["locations"]
)
assert script_lines == [2, 13, 14, 15, 17], script_lines
serves = sorted((e["from"], e["to"]) for e in document["edges"] if e["kind"] == "route_serves_path")
assert serves == [("drupal.route::mymod.xy", path)], serves
paths = sorted(n["id"] for n in document["nodes"] if n["type"] == "drupal.url_path")
assert paths == [path], paths
PY
echo "path strings ok"
