"""A URL written as a path string links to the route that serves that exact path."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymod")
ROUTING = """\
mymod.page:
  path: '/my/path'
  defaults:
    _controller: '\\Drupal\\mymod\\Controller\\LinkController::page'
mymod.item:
  path: '/my/item/{id}'
  defaults:
    _controller: '\\Drupal\\mymod\\Controller\\LinkController::page'
"""
CONTROLLER = """\
<?php

namespace Drupal\\mymod\\Controller;

use Drupal\\Core\\Url;
use Symfony\\Component\\HttpFoundation\\RedirectResponse;

class LinkController {
  public function page() {
    $a = Url::fromUserInput('/my/path?x=1');
    $b = Url::fromUri('internal:/my/path');
    $f = Url::fromUserInput('/my/path');
    $c = Url::fromUserInput('/no/route');
    $d = Url::fromUri('route:mymod.page');
    $e = Url::fromUserInput('/my/item/5');
    return new RedirectResponse('/my/path');
  }
}
"""
MODULE_FILE = """\
<?php

use Drupal\\Core\\Url;

function mymod_link() {
  return \\Drupal\\Core\\Url::fromUri('internal:/my/path');
}
"""
CLASS = "php.type::Drupal\\mymod\\Controller\\LinkController"


def _plant(root: Path) -> None:
    (root / MODULE / "src" / "Controller").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (root / MODULE / "mymod.info.yml").write_text("name: My module\ntype: module\n")
    (root / MODULE / "mymod.routing.yml").write_text(ROUTING)
    (root / MODULE / "mymod.module").write_text(MODULE_FILE)
    (root / MODULE / "src" / "Controller" / "LinkController.php").write_text(CONTROLLER)


def _map(root: Path) -> dict[str, list[dict[str, object]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    document: dict[str, list[dict[str, object]]] = json.loads(Path(report.map_path).read_text())
    return document


def test_a_path_url_links_to_the_path_node_the_route_serves(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    edges = sorted(
        (
            str(e["kind"]),
            str(e["from"]),
            str(e["to"]),
            tuple(sorted(str(p["rule"]) for p in e["provenance"])),
        )
        for e in document["edges"]
        if e["kind"] in ("links_to_path", "route_serves_path")
    )
    user, internal = "user_input_url_call", "internal_uri_url_call"
    route, item = "route_from_routing_file_edges", "drupal.url_path::/my/item/{id}"
    assert edges == [
        ("links_to_path", "php.function::mymod_link", "drupal.url_path::/my/path", (internal,)),
        ("links_to_path", CLASS, "drupal.url_path::/my/item/5", (user,)),
        ("links_to_path", CLASS, "drupal.url_path::/my/path", (internal, user)),
        ("links_to_path", CLASS, "drupal.url_path::/my/path?x=1", (user,)),
        ("links_to_path", CLASS, "drupal.url_path::/no/route", (user,)),
        ("route_serves_path", "drupal.route::mymod.item", item, (route,)),
        ("route_serves_path", "drupal.route::mymod.page", "drupal.url_path::/my/path", (route,)),
    ]
    assert nodes["drupal.url_path::/no/route"] == "referenced"
    assert nodes["drupal.url_path::/my/path?x=1"] == "referenced"
    assert nodes["drupal.url_path::/my/item/5"] == "referenced"
