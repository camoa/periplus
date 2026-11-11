"""A route name in a PHP call links the class or function around it to the route."""

import json
from pathlib import Path

import pytest

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymod")
METHOD_ID = "php.method::Drupal\\mymod\\Controller\\LinkController::page"
FUNCTION_ID = "php.function::mymod_link"

ROUTING = (
    "mymod.page:\n"
    "  path: /my/path\n"
    "  defaults:\n"
    "    _controller: \\Drupal\\mymod\\Controller\\LinkController::page\n"
)

CONTROLLER_HEAD = (
    "<?php\n"
    "namespace Drupal\\mymod\\Controller;\n"
    "use Drupal\\Core\\Url;\n"
    "use Drupal\\Core\\Link;\n"
    "class LinkController {\n"
)


def _plant(root: Path, controller_body: str, module_body: str = "") -> None:
    (root / MODULE / "src" / "Controller").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (root / MODULE / "mymod.info.yml").write_text("name: My module\ntype: module\n")
    (root / MODULE / "mymod.routing.yml").write_text(ROUTING)
    (root / MODULE / "mymod.module").write_text("<?php\n" + module_body)
    (root / MODULE / "src" / "Controller" / "LinkController.php").write_text(
        CONTROLLER_HEAD + controller_body + "}\n"
    )


def _map(root: Path):
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    document = json.loads(Path(report.map_path).read_text())
    edges = sorted(
        (
            e["from"],
            e["to"],
            tuple(sorted(p["confidence"] for p in e["provenance"])),
        )
        for e in document["edges"]
        if e["kind"] == "links_to_route"
    )
    nodes = {n["id"]: n["state"] for n in document["nodes"]}
    return report, edges, nodes


@pytest.mark.criterion(id="c1")
def test_static_route_calls_link_method_and_function_to_route_c1(tmp_path):
    _plant(
        tmp_path,
        "  public function page() { return Url::fromRoute('mymod.page'); }\n",
        "function mymod_link() {\n"
        "  return \\Drupal\\Core\\Link::createFromRoute('Text', 'mymod.page');\n"
        "}\n",
    )
    _, edges, _ = _map(tmp_path)
    assert edges == [
        (FUNCTION_ID, "drupal.route::mymod.page", ("declared",)),
        (METHOD_ID, "drupal.route::mymod.page", ("declared",)),
    ]


@pytest.mark.criterion(id="c2")
def test_redirect_call_links_method_to_route_inferred_c2(tmp_path):
    _plant(
        tmp_path,
        "  public function page() { return $this->redirect('mymod.page'); }\n",
    )
    _, edges, _ = _map(tmp_path)
    assert edges == [(METHOD_ID, "drupal.route::mymod.page", ("inferred",))]


@pytest.mark.criterion(id="c3")
def test_variable_name_is_skipped_and_undeclared_route_is_referenced_c3(tmp_path):
    _plant(
        tmp_path,
        "  public function page($name) {\n"
        "    $a = Url::fromRoute($name);\n"
        "    return Url::fromRoute('other.route');\n"
        "  }\n",
    )
    report, edges, nodes = _map(tmp_path)
    assert edges == [(METHOD_ID, "drupal.route::other.route", ("declared",))]
    assert nodes.get("drupal.route::other.route") == "referenced"
    assert [
        (row[3], row[2].endswith("route_call_from_url")) for row in report.skipped
    ] == [("argument 0 is not a text literal", True)]


def test_a_route_call_in_a_trait_links_from_the_trait_method(tmp_path):
    _plant(tmp_path, "")
    (tmp_path / MODULE / "src" / "LinkTrait.php").write_text(
        "<?php\n"
        "namespace Drupal\\mymod;\n"
        "use Drupal\\Core\\Url;\n"
        "trait LinkTrait {\n"
        "  public function back() { return Url::fromRoute('mymod.page'); }\n"
        "}\n"
    )
    report, edges, _ = _map(tmp_path)
    trait_method = "php.method::Drupal\\mymod\\LinkTrait::back"
    assert edges == [(trait_method, "drupal.route::mymod.page", ("declared",))]
    assert not [row for row in report.skipped if row[2].endswith("route_call_from_url")]
