"""A literal call and a variable-argument call to one callee in one method keep separate nodes."""

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymod")
METHOD_SUFFIX = "::page"

SOURCE = """<?php
namespace Drupal\\mymod\\Controller;

class SiblingController {
  public function page($type, $service) {
    $a = $this->entityTypeManager->getStorage('node');
    $b = $this->entityTypeManager->getStorage($type);
    $c = $this->container->get('mymod.thing');
    $d = $this->container->get($service);
    return [$a, $b, $c, $d];
  }
}
"""


def _plant(root: Path) -> None:
    controller = root / MODULE / "src" / "Controller"
    controller.mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (root / MODULE / "mymod.info.yml").write_text("name: My module\ntype: module\n")
    (root / MODULE / "mymod.module").write_text("<?php\n")
    (controller / "SiblingController.php").write_text(SOURCE)


def _map(root: Path) -> dict[str, Any]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    return json.loads(Path(report.map_path).read_text())


def _line_of(needle: str) -> int:
    return next(i for i, row in enumerate(SOURCE.splitlines(), 1) if needle in row)


def _lines(node: dict[str, Any]) -> set[int]:
    return {loc["line"] for loc in node["locations"]}


def _is_marked(node: dict[str, Any]) -> bool:
    return node.get("attributes", {}).get("resolution") == "runtime"


def _check_pair(document: dict[str, Any], literal: int, variable: int, kind: str) -> None:
    method = next(
        n["id"]
        for n in document["nodes"]
        if n["type"] == "php.method" and n["id"].endswith(METHOD_SUFFIX)
    )
    sites = [n for n in document["nodes"] if n["type"] == "php.call_site"]
    plain = [n for n in sites if literal in _lines(n)]
    assert len(plain) == 1, f"{kind}: literal line {literal} sits on {len(plain)} nodes"
    assert not _is_marked(plain[0])
    assert {literal, variable} <= _lines(plain[0])
    marked = [n for n in sites if _is_marked(n) and variable in _lines(n)]
    assert len(marked) == 1, f"{kind}: variable line {variable} sits on {len(marked)} marked nodes"
    assert _lines(marked[0]) == {variable}
    leaving = [e for e in document["edges"] if e["from"] == marked[0]["id"]]
    assert leaving and {e["kind"] for e in leaving} == {"call_site_in"}
    assert any(
        e["kind"] == kind and e["from"] == method and literal in _lines(e)
        for e in document["edges"]
    ), f"the method lost its {kind} edge"


@pytest.mark.criterion(id="c1")
def test_literal_and_variable_storage_and_container_get_keep_separate_nodes_c1(
    tmp_path: Path,
) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    _check_pair(
        document,
        _line_of("getStorage('node')"),
        _line_of("getStorage($type)"),
        "uses_entity_type",
    )
    _check_pair(
        document,
        _line_of("get('mymod.thing')"),
        _line_of("get($service)"),
        "uses_service",
    )
