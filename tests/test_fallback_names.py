"""A fallback resolution on an edge end: the second name is tried after the first."""

import json
from pathlib import Path

import pytest
from _own_pack import plant

from periplus import map as periplus_map
from periplus.preflight import check_runtime_dependencies

CALLER = "App\\caller"
FALLBACK = "[as_written]"

RULES = """
node_types:
  - {{name: own.function, id_namespace: own.function}}
  - {{name: own.class, id_namespace: own.class}}
edge_kinds:
  - {{kind: calls, from: [own.function, own.class], to: [own.function]}}
rules:
  - rule: find_function
    reads: file
    in: [source]
    match: {{declaration: function_definition, name_child: name, filetype: php}}
    id: {{from: qualified_name}}
    emits: [{{node: {{type: own.function}}}}]
    confidence: declared
  - rule: calls_helper
    reads: file
    in: [source]
    match: {{reference: function_call_expression, name_child: function, filetype: php}}
    emits:
      - edge:
          kind: calls
          from: enclosing_declaration
          to:
            types: [own.function]
            resolve: [prefix_with: namespace]
{fallback}            on_miss: unresolved
    confidence: declared
"""

NAMESPACED = """<?php
namespace App;

function helper() {}

function caller() {
    helper();
}
"""

CALL_ONLY = """<?php
namespace App;

function caller() {
    helper();
}
"""

GLOBAL_HELPER = """<?php
function helper() {}
"""


def _calls_from_caller(tmp_path: Path, source: str, fallback: str, extra: str | None = None):
    rules = RULES.format(fallback=f"            fallback: {fallback}\n" if fallback else "")
    plant(tmp_path, rules, source)
    if extra is not None:
        (tmp_path / "src" / "Global.php").write_text(extra)
    return periplus_map.run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )


def _targets(report) -> list[str]:
    if report.map_path is None:
        return []
    document = json.loads(Path(report.map_path).read_text())
    return [
        edge["to"]
        for edge in document["edges"]
        if edge["kind"] == "calls" and edge["from"].endswith(CALLER)
    ]


@pytest.mark.criterion(id="c1")
def test_namespaced_function_wins_over_the_fallback_c1(tmp_path):
    report = _calls_from_caller(tmp_path, NAMESPACED, FALLBACK, GLOBAL_HELPER)
    assert _targets(report) == ["own.function::App\\helper"]


@pytest.mark.criterion(id="c1")
def test_edge_lands_on_the_global_when_only_it_is_declared_c1(tmp_path):
    report = _calls_from_caller(tmp_path, CALL_ONLY, FALLBACK, GLOBAL_HELPER)
    assert _targets(report) == ["own.function::helper"]


@pytest.mark.criterion(id="c1")
def test_neither_declared_ends_unresolved_under_the_first_name_c1(tmp_path):
    report = _calls_from_caller(tmp_path, CALL_ONLY, FALLBACK)
    targets = _targets(report)
    assert targets == ["own.function::App\\helper"]
    document = json.loads(Path(report.map_path).read_text()) if report.map_path else {"nodes": []}
    ids = {n["id"] for n in document["nodes"]}
    assert "own.function::App\\helper" in ids
    assert "own.function::helper" not in ids


@pytest.mark.criterion(id="c1")
def test_fallback_that_is_not_a_list_of_steps_refuses_the_rule_c1(tmp_path):
    report = _calls_from_caller(tmp_path, CALL_ONLY, "as_written")
    assert [r for _, r, _ in report.executed if r == "calls_helper"] == []
    reasons = [m.message for m in report.problems]
    assert any("calls_helper" in m and "fallback" in m for m in reasons)


@pytest.mark.criterion(id="c1")
def test_end_without_fallback_ignores_the_global_c1(tmp_path):
    report = _calls_from_caller(tmp_path, CALL_ONLY, "", GLOBAL_HELPER)
    assert _targets(report) == ["own.function::App\\helper"]
    document = json.loads(Path(report.map_path).read_text())
    ends = [n for n in document["nodes"] if n["id"] == "own.function::App\\helper"]
    assert len(ends) == 1
    assert ends[0]["state"] == "unresolved"
    detail = ends[0]["unresolved_detail"]
    assert detail["types_tried"] == ["own.function"]
    assert detail["searched_for"] == "App\\helper"
