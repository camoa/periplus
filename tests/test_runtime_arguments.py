"""A runtime-built argument is kept as a marked call site by the Drupal rutter."""

import json
from pathlib import Path
from typing import Any

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymod")
METHOD_ID = "php.method::Drupal\\mymod\\Controller\\LinkController::page"

ROUTING = (
    "mymod.page:\n"
    "  path: /my/path\n"
    "  defaults:\n"
    "    _controller: \\Drupal\\mymod\\Controller\\LinkController::page\n"
    "  requirements:\n"
    "    _access: 'TRUE'\n"
)

HEAD = (
    "<?php\n"
    "namespace Drupal\\mymod\\Controller;\n"
    "use Drupal\\Core\\Url;\n"
    "use Drupal\\Core\\Link;\n"
    "class LinkController {\n"
)


def _plant(root: Path, body: str) -> None:
    (root / MODULE / "src/Controller").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus/settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (root / MODULE / "mymod.info.yml").write_text("name: My module\ntype: module\n")
    (root / MODULE / "mymod.routing.yml").write_text(ROUTING)
    (root / MODULE / "mymod.module").write_text("<?php\n")
    (root / MODULE / "src/Controller/LinkController.php").write_text(HEAD + body + "}\n")


def _map(root: Path) -> dict[str, Any]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    return json.loads(Path(report.map_path).read_text())


def _lines(locations: list[dict[str, Any]]) -> set[int]:
    return {loc["line"] for loc in locations}


def _marked(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        n
        for n in document["nodes"]
        if n["type"] == "php.call_site" and n.get("attributes", {}).get("resolution") == "runtime"
    ]


def _line_of(source: str, needle: str) -> int:
    return next(i for i, t in enumerate(source.splitlines(), 1) if needle in t)


def _marked_lines(document: dict[str, Any]) -> list[int]:
    lines = []
    for node in _marked(document):
        found = _lines(node["locations"])
        assert len(found) == 1
        lines.append(found.pop())
    return sorted(lines)


def _edges(document: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e for e in document["edges"] if e["kind"] == kind]


def test_service_id_in_a_variable_is_marked_and_a_literal_keeps_its_edge_c3(tmp_path):
    body = (
        "  public function page($id) {\n"
        "    $a = \\Drupal::service($id);\n"
        "    $b = \\Drupal::service('mymod.thing');\n"
        "  }\n"
    )
    _plant(tmp_path, body)
    document = _map(tmp_path)
    source = HEAD + body
    runtime_line = _line_of(source, "service($id)")
    literal_line = _line_of(source, "service('mymod.thing')")

    assert _marked_lines(document) == [runtime_line]
    uses = [(e["to"], _lines(e["locations"])) for e in _edges(document, "uses_service")]
    assert uses == [("drupal.service::mymod.thing", {literal_line})]
    marked_ids = {n["id"] for n in _marked(document)}
    for edge in document["edges"]:
        if edge["from"] in marked_ids:
            assert edge["kind"] == "call_site_in"
            assert edge["to"] == METHOD_ID


def test_route_built_by_concatenation_is_marked_and_a_literal_keeps_its_edge_c3(tmp_path):
    body = (
        "  public function page($name) {\n"
        "    $a = Url::fromRoute('my.' . $name);\n"
        "    $b = Url::fromRoute('mymod.page');\n"
        "  }\n"
    )
    _plant(tmp_path, body)
    document = _map(tmp_path)
    source = HEAD + body
    runtime_line = _line_of(source, "'my.' . $name")
    literal_line = _line_of(source, "fromRoute('mymod.page')")

    marked = _marked(document)
    assert [_lines(n["locations"]) for n in marked] == [{runtime_line}]
    links = [(e["to"], _lines(e["locations"])) for e in _edges(document, "links_to_route")]
    assert links == [("drupal.route::mymod.page", {literal_line})]
    marked_id = marked[0]["id"]
    out = [e for e in document["edges"] if e["from"] == marked_id]
    assert [(e["kind"], e["to"]) for e in out] == [("call_site_in", METHOD_ID)]
    assert [e["from"] for e in _edges(document, "has_call_site") if e["to"] == marked_id] == [
        METHOD_ID
    ]


NINE = (
    "  public function page($v, $container, $storage) {\n"
    "    $r01 = Url::fromRoute($v);\n"
    "    $r02 = Link::createFromRoute(t('Go'), $v);\n"
    "    $r03 = $this->redirect($v);\n"
    "    $r04 = \\Drupal::service($v);\n"
    "    $r05 = $container->get($v);\n"
    "    $r06 = $container?->get($v);\n"
    "    $r07 = \\Drupal::entityQuery($v);\n"
    "    $r08 = \\Drupal::entityTypeManager()->getStorage($v);\n"
    "    $r09 = $this->entityTypeManager?->getStorage($v);\n"
    "    $l01 = Url::fromRoute('mymod.page');\n"
    "    $l02 = Link::createFromRoute($this->t('Go'), 'mymod.page');\n"
    "    $l03 = $this->redirect('mymod.page');\n"
    "    $l04 = \\Drupal::service('mymod.thing');\n"
    "    $l05 = $container->get('mymod.thing');\n"
    "    $l06 = $container?->get('mymod.thing');\n"
    "    $l07 = \\Drupal::entityQuery('node');\n"
    "    $l08 = \\Drupal::entityTypeManager()->getStorage('node');\n"
    "    $l09 = $this->entityTypeManager?->getStorage('node');\n"
    "    $c01 = Url::fromRoute(self::ROUTE);\n"
    "    $c02 = Link::createFromRoute(t('Go'), self::ROUTE);\n"
    "    $c03 = $this->redirect(self::ROUTE);\n"
    "    $c04 = \\Drupal::service(self::SERVICE);\n"
    "    $c05 = $container->get(self::SERVICE);\n"
    "    $c06 = $container?->get(self::SERVICE);\n"
    "    $c07 = \\Drupal::entityQuery(self::TYPE);\n"
    "    $c08 = \\Drupal::entityTypeManager()->getStorage(self::TYPE);\n"
    "    $c09 = $this->entityTypeManager?->getStorage(self::TYPE);\n"
    "  }\n"
)


def test_each_of_the_nine_twin_rules_fires_on_a_variable_only_c3(tmp_path):
    _plant(tmp_path, NINE)
    document = _map(tmp_path)
    source = HEAD + NINE
    expected = sorted(_line_of(source, f"$r{n:02d} =") for n in range(1, 10))

    assert _marked_lines(document) == expected
    in_edges = _edges(document, "call_site_in")
    assert len(in_edges) == 9
    assert {e["to"] for e in in_edges} == {METHOD_ID}
    marked_ids = {n["id"] for n in _marked(document)}
    leaving = [e for e in document["edges"] if e["from"] in marked_ids]
    assert [(e["kind"], e["to"]) for e in leaving] == [("call_site_in", METHOD_ID)] * 9
