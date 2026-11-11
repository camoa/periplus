"""on_miss_name: fallback puts an end's on_miss mark under its fallback name, not its first."""

import json
from pathlib import Path

from _own_pack import plant

from periplus import map as periplus_map
from periplus.map import MapReport
from periplus.preflight import check_runtime_dependencies

CALLER = "App\\caller"

RULES = """
node_types:
  - {{name: own.function, id_namespace: own.function}}
edge_kinds:
  - {{kind: calls, from: [own.function], to: [own.function]}}
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
            {{types: [own.function], resolve: [prefix_with: namespace], fallback: [as_written],
             {end}}}
    confidence: declared
"""

MARKED = "on_miss: unresolved, on_miss_name: fallback"

CALL_ONLY = """<?php
namespace App;

function caller() {
    helper();
}
"""

NAMESPACED = CALL_ONLY + "\nfunction helper() {}\n"

GLOBAL_HELPER = "<?php\nfunction helper() {}\n"

TEXT_RULES = """
node_types:
  - {name: own.note, id_namespace: own.note}
  - {name: own.target, id_namespace: own.target}
edge_kinds:
  - {kind: names, from: [own.note], to: [own.target]}
rules:
  - rule: find_note
    reads: file
    in: [source]
    match: &note {file: '**', filetype: note, text: 'call (?<space>\\w+) (?<name>\\w+)'}
    id: {from: {capture: name}}
    emits: [{node: {type: own.note}}]
    confidence: declared
  - rule: note_names
    reads: file
    in: [source]
    match: *note
    id: {from: {capture: name}}
    emits:
      - edge:
          kind: names
          from: this_node
          to:
            from: {capture: name}
            types: [own.target]
            resolve: [prefix_with: space]
            separator: '.'
            fallback: [as_written]
            on_miss: unresolved
            on_miss_name: fallback
    confidence: declared
"""


def _run(tmp_path: Path) -> MapReport:
    return periplus_map.run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )


def _map(tmp_path: Path, source: str, end: str = MARKED, extra: str | None = None) -> MapReport:
    plant(tmp_path, RULES.format(end=end), source)
    if extra is not None:
        (tmp_path / "src" / "Global.php").write_text(extra)
    return _run(tmp_path)


def _document(report: MapReport) -> dict:
    assert report.problems == (), report.problems
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text())


def _targets(document: dict) -> list[str]:
    return [e["to"] for e in document["edges"] if e["from"] == f"own.function::{CALLER}"]


def _states(document: dict) -> dict[str, str]:
    return {n["id"]: n["state"] for n in document["nodes"]}


def test_neither_mapped_marks_the_fallback_name(tmp_path):
    document = _document(_map(tmp_path, CALL_ONLY))
    assert _targets(document) == ["own.function::helper"]
    states = _states(document)
    assert states["own.function::helper"] == "unresolved"
    assert "own.function::App\\helper" not in states
    detail = next(n for n in document["nodes"] if n["id"] == "own.function::helper")
    assert detail["unresolved_detail"]["searched_for"] == "helper"


def test_the_first_name_still_wins_when_mapped(tmp_path):
    document = _document(_map(tmp_path, NAMESPACED, extra=GLOBAL_HELPER))
    assert _targets(document) == ["own.function::App\\helper"]


def test_the_fallback_name_lands_mapped_when_only_it_is_declared(tmp_path):
    document = _document(_map(tmp_path, CALL_ONLY, extra=GLOBAL_HELPER))
    assert _targets(document) == ["own.function::helper"]
    assert _states(document)["own.function::helper"] == "mapped"


def test_a_text_rule_end_marks_the_fallback_name(tmp_path):
    plant(tmp_path, TEXT_RULES)
    (tmp_path / "src" / "a.txt").write_text("call app helper\n")
    document = _document(_run(tmp_path))
    edges = [(e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("own.note::helper", "own.target::helper")]
    assert _states(document)["own.target::helper"] == "unresolved"
    assert "own.target::app.helper" not in _states(document)


def _refused(report: MapReport) -> list[str]:
    assert [r for _, r, _ in report.executed if r == "calls_helper"] == []
    return [p.message for p in report.problems]


def test_on_miss_name_without_a_fallback_is_refused(tmp_path):
    end = "on_miss: unresolved, on_miss_name: fallback"
    rules = RULES.format(end=end).replace("fallback: [as_written],", "")
    plant(tmp_path, rules, CALL_ONLY)
    messages = _refused(_run(tmp_path))
    assert any("calls_helper" in m and "on_miss_name" in m for m in messages), messages


def test_on_miss_name_without_on_miss_is_refused(tmp_path):
    messages = _refused(_map(tmp_path, CALL_ONLY, end="on_miss_name: fallback"))
    assert any("calls_helper" in m and "on_miss_name" in m for m in messages), messages


def test_an_on_miss_name_other_than_fallback_is_refused(tmp_path):
    report = _map(tmp_path, CALL_ONLY, end="on_miss: unresolved, on_miss_name: first")
    messages = [p.message for p in report.problems]
    assert any("on_miss_name" in m for m in messages), messages
    assert report.map_path is None
