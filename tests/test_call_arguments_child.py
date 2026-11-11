"""A call node that holds its arguments in a child with no field name: {argument: N} reads them
by the child of the node type identity.call_arguments names."""

import json
from pathlib import Path

from _own_pack import MANIFEST, plant

from periplus import map as periplus_map
from periplus.map import MapReport
from periplus.preflight import check_runtime_dependencies

# The own pack's grammar with call keys; call_arguments names a field and a node type at once.
CALL_KEYS = """  call_arguments: arguments
  call_argument: argument
  call_argument_name: name
  call_literals: [string, encapsed_string]
  call_literal_content: [string_content]
"""

RULES = """
node_types:
  - {name: own.function, id_namespace: own.function}
  - {name: own.made, id_namespace: own.made}
edge_kinds:
  - {kind: makes, from: [own.function], to: [own.made]}
rules:
  - rule: find_function
    reads: file
    in: [source]
    match: {declaration: function_definition, name_child: name, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.function}}]
    confidence: declared
  - rule: made_by_creation
    reads: file
    in: [source]
    match: {declaration: object_creation_expression, filetype: php}
    id: {from: {argument: 0}}
    emits: [{node: {type: own.made}}]
    confidence: declared
  - rule: made_by_call
    reads: file
    in: [source]
    match: {declaration: function_call_expression, filetype: php}
    id: {from: {argument: 0}}
    emits: [{node: {type: own.made}}]
    confidence: declared
  - rule: makes
    reads: file
    in: [source]
    match: {reference: object_creation_expression, name_child: name, filetype: php}
    emits: [{edge: {kind: makes, from: enclosing_declaration, to: {from: {argument: 1}}}}]
    confidence: declared
"""

# In this grammar, a function call holds its arguments in the field arguments; an object creation
# holds them in a child of node type arguments with no field name.
SOURCE = """<?php
function run() {
    $a = new Filter('price', 'money');
    $b = make('total');
}
"""


def _map(tmp_path: Path) -> tuple[MapReport, dict]:
    plant(tmp_path, RULES, SOURCE)
    manifest = tmp_path / ".periplus/packs/own@0.0.1/pack.yaml"
    manifest.write_text(MANIFEST + CALL_KEYS)
    report = periplus_map.run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=tmp_path / "map.json",
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    return report, json.loads(Path(report.map_path).read_text())


def test_an_id_reads_the_argument_of_a_node_whose_arguments_have_no_field(tmp_path):
    report, document = _map(tmp_path)
    made = sorted(
        (n["id"], n["provenance"][0]["rule"]) for n in document["nodes"] if "made" in n["type"]
    )
    assert made == [
        ("own.made::money", "makes"),
        ("own.made::price", "made_by_creation"),
        ("own.made::total", "made_by_call"),
    ]
    assert [row for row in report.skipped if row[2] != "find_function"] == []


def test_a_reference_end_reads_the_argument_of_such_a_node(tmp_path):
    _, document = _map(tmp_path)
    edges = [(e["kind"], e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("makes", "own.function::run", "own.made::money")]
