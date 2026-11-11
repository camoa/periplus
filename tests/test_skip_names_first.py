"""skip_names is consulted before the written-name check of a reference rule's name child."""

import json
from pathlib import Path

from _own_pack import plant

from periplus import map as periplus_map
from periplus.map import MapReport
from periplus.preflight import check_runtime_dependencies

RULES = """
node_types:
  - {{name: own.function, id_namespace: own.function}}
  - {{name: own.method, id_namespace: own.method}}
edge_kinds:
  - {{kind: calls, from: [own.function], to: [own.method]}}
rules:
  - rule: find_function
    reads: file
    in: [source]
    match: {{declaration: function_definition, name_child: name, filetype: php}}
    id: {{from: qualified_name}}
    emits: [{{node: {{type: own.function}}}}]
    confidence: declared
  - rule: calls_static
    reads: file
    in: [source]
    match:
      reference: scoped_call_expression
      name_child: [scope, name]
      filetype: php
      skip_names: {skip}
    emits:
      - edge:
          kind: calls
          from: enclosing_declaration
          to: {{types: [own.method], separator: "::"}}
    confidence: declared
"""

# self, static and parent are relative_scope nodes in this grammar, not written names.
SOURCE = """<?php
function caller() {
    self::a();
    static::b();
    parent::c();
    Util::d();
}
"""


def _map(tmp_path: Path, skip: str) -> tuple[MapReport, dict]:
    plant(tmp_path, RULES.format(skip=skip), SOURCE)
    report = periplus_map.run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    return report, json.loads(Path(report.map_path).read_text())


def _rows(report: MapReport) -> list[tuple[int, str]]:
    return [(line, reason) for _, line, rule, reason in report.skipped if rule == "calls_static"]


def test_listed_names_that_are_not_written_names_make_no_row_and_no_fire(tmp_path):
    report, document = _map(tmp_path, "[self, static, parent]")
    assert _rows(report) == []
    assert [(e["from"], e["to"]) for e in document["edges"]] == [
        ("own.function::caller", "own.method::Util::d")
    ]
    assert ("own", "calls_static", 1) in report.executed


def test_an_unlisted_name_that_is_not_a_written_name_keeps_its_row(tmp_path):
    report, _ = _map(tmp_path, "[static]")
    assert _rows(report) == [
        (3, "scope is not a written name"),
        (5, "scope is not a written name"),
    ]
