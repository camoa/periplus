"""A declaration rule's name_child path may have one step or more than two."""

import json
from pathlib import Path

from _own_pack import plant

from periplus import map as periplus_map
from periplus.map import MapReport
from periplus.preflight import check_runtime_dependencies

RULES = """
node_types:
  - {{name: own.name, id_namespace: own.name}}
rules:
  - rule: find_name
    reads: file
    in: [source]
    match: {{declaration: {declaration}, name_child: {path}, filetype: php}}
    id: {{from: declared_name}}
    emits: [{{node: {{type: own.name}}}}]
    confidence: declared
"""

# A const_element's name is a child with no field name.
SOURCE = """<?php
class Thing {
    const A = 'a',
        B = 'b';
    const C = 'c';
}

function run($first, $second) {}
"""

REFERENCE = """
node_types:
  - {name: own.function, id_namespace: own.function}
edge_kinds:
  - {kind: calls, from: [own.function], to: [own.function]}
rules:
  - rule: find_function
    reads: file
    in: [source]
    match: {declaration: function_definition, name_child: name, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.function}}]
    confidence: declared
  - rule: calls_function
    reads: file
    in: [source]
    match: {reference: function_call_expression, name_child: [function, name, name], filetype: php}
    emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [own.function]}}}]
    confidence: declared
"""


def _run(tmp_path: Path) -> MapReport:
    return periplus_map.run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )


def _names(tmp_path: Path, declaration: str, path: str) -> list[tuple[str, int]]:
    plant(tmp_path, RULES.format(declaration=declaration, path=path), SOURCE)
    report = _run(tmp_path)
    assert report.problems == (), report.problems
    assert report.map_path is not None
    document = json.loads(Path(report.map_path).read_text())
    return sorted((n["id"], n["locations"][0]["line"]) for n in document["nodes"])


def test_a_one_step_path_reads_a_name_with_no_field_once_per_element(tmp_path):
    assert _names(tmp_path, "const_element", "[name]") == [
        ("own.name::A", 3),
        ("own.name::B", 4),
        ("own.name::C", 5),
    ]


def test_a_three_step_path_reads_the_leaf(tmp_path):
    names = _names(tmp_path, "function_definition", "[parameters, simple_parameter, name]")
    assert names == [("own.name::$first", 8)]


def test_an_empty_path_is_refused(tmp_path):
    plant(tmp_path, RULES.format(declaration="const_element", path="[]"), SOURCE)
    report = _run(tmp_path)
    assert any("name_child" in p.message for p in report.problems), report.problems
    assert report.map_path is None


def test_a_reference_name_child_of_three_fields_is_refused(tmp_path):
    plant(tmp_path, REFERENCE, "<?php\nfunction run() { go(); }\n")
    report = _run(tmp_path)
    assert [r for _, r, _ in report.executed if r == "calls_function"] == []
    messages = [p.message for p in report.problems]
    assert any("calls_function" in m and "name_child" in m for m in messages), messages
