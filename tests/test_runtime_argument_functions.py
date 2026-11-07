"""A variable route, service or entity type argument in a module-file function is marked."""

from pathlib import Path
from typing import Any

import pytest
from test_runtime_arguments import MODULE, ROUTING, _lines, _map, _marked

SOURCE = """<?php
use Drupal\\Core\\Url;

function mymod_cron() {
  $a = Url::fromRoute($hook_route);
  $b = \\Drupal::service($hook_service);
  $c = \\Drupal::entityQuery($hook_type);
  $d = Url::fromRoute('mymod.page');
  $e = \\Drupal::service('mymod.thing');
  $f = \\Drupal::entityQuery('node');
}

function mymod_helper($route, $service, $type) {
  $g = Url::fromRoute($route);
  $h = \\Drupal::service($service);
  $i = \\Drupal::entityQuery($type);
  $j = Url::fromRoute('mymod.page');
  $k = \\Drupal::service('mymod.thing');
  $l = \\Drupal::entityQuery('node');
}

class Holder {
  public function go($route, $service, $type) {
    $m = Url::fromRoute($route);
    $n = \\Drupal::service($service);
    $o = \\Drupal::entityQuery($type);
  }
}
"""

HOOK_VARIABLE = ("$hook_route", "$hook_service", "$hook_type")


def _plant(root: Path) -> None:
    (root / MODULE).mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (root / MODULE / "mymod.info.yml").write_text("name: My module\ntype: module\n")
    (root / MODULE / "mymod.routing.yml").write_text(ROUTING)
    (root / MODULE / "mymod.module").write_text(SOURCE)


def _line(needle: str, nth: int = 0) -> int:
    rows = [i for i, row in enumerate(SOURCE.splitlines(), 1) if needle in row]
    return rows[nth]


def _holder(document: dict[str, Any], kind: str, name: str) -> str:
    return next(
        n["id"] for n in document["nodes"] if n["type"] == kind and n["id"].endswith(f"::{name}")
    )


def _variable_lines() -> dict[str, list[int]]:
    return {
        "mymod_cron": [_line(t) for t in HOOK_VARIABLE],
        "mymod_helper": [
            _line("Url::fromRoute($route);"),
            _line("service($service);"),
            _line("entityQuery($type);"),
        ],
    }


@pytest.mark.criterion(id="c2")
def test_variable_arguments_in_hook_and_plain_function_are_marked_and_joined_c2(
    tmp_path: Path,
) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    for name, lines in _variable_lines().items():
        holder = _holder(document, "php.function", name)
        for line in lines:
            nodes = [n for n in _marked(document) if _lines(n["locations"]) == {line}]
            assert len(nodes) == 1, f"{name}: {len(nodes)} marked nodes at line {line}"
            node = nodes[0]
            assert any(
                e["kind"] == "has_call_site" and e["from"] == holder and e["to"] == node["id"]
                for e in document["edges"]
            )
            leaving = [e for e in document["edges"] if e["from"] == node["id"]]
            assert leaving and {e["kind"] for e in leaving} == {"call_site_in"}
            assert {e["to"] for e in leaving} == {holder}
    reached = {"links_to_route", "uses_service", "uses_entity_type"}
    flagged = {line for lines in _variable_lines().values() for line in lines}
    assert not [
        e for e in document["edges"] if e["kind"] in reached and _lines(e["locations"]) & flagged
    ]


@pytest.mark.criterion(id="c2")
def test_literal_siblings_and_class_method_keep_their_edges_c2(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    for name, first in (("mymod_cron", 0), ("mymod_helper", 1)):
        holder = _holder(document, "php.function", name)
        for kind, needle in (
            ("links_to_route", "Url::fromRoute('mymod.page')"),
            ("uses_service", "service('mymod.thing')"),
            ("uses_entity_type", "entityQuery('node')"),
        ):
            line = _line(needle, first)
            assert any(
                e["kind"] == kind and e["from"] == holder and line in _lines(e["locations"])
                for e in document["edges"]
            ), f"{name} lost its {kind} edge"
    method = _holder(document, "php.method", "go")
    method_lines = [_line("$m = "), _line("$n = "), _line("$o = ")]
    for line in method_lines:
        nodes = [n for n in _marked(document) if _lines(n["locations"]) == {line}]
        assert len(nodes) == 1, f"line {line}: {len(nodes)} marked nodes"
        leaving = [e for e in document["edges"] if e["from"] == nodes[0]["id"]]
        assert [(e["kind"], e["to"]) for e in leaving] == [("call_site_in", method)]
        assert any(
            e["kind"] == "has_call_site" and e["from"] == method and e["to"] == nodes[0]["id"]
            for e in document["edges"]
        )
