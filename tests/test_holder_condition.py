"""A declaration rule can name the node type its enclosing holder must be."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _own_pack import plant

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

SOURCE = """<?php
function outer() {
    plain_call();
    if ($a) {
        if_call();
    }
    foreach ($xs as $x) {
        loop_call();
    }
}
class Box {
    public function run() {
        method_call();
    }
}
top_call();
"""

HOLDER_RULE = """
  - rule: fn_holder
    reads: file
    in: [source]
    match: {declaration: function_definition, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.fn}}]
    confidence: declared
"""

HEAD = """
node_types:
  - {name: own.fn, id_namespace: fn}
  - {name: own.callsite, id_namespace: callsite}
edge_kinds:
  - {kind: calls, from: [own.fn], to: [own.fn]}
rules:
"""

METHOD_HOLDER_RULE = """
  - rule: method_holder
    reads: file
    in: [source]
    match: {declaration: method_declaration, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.fn}}]
    confidence: declared
"""

KEYED_CALL = """
  - rule: call_in_function
    reads: file
    in: [source]
    match:
      {declaration: function_call_expression, name_child: function, filetype: php,
       holder: function_definition}
    id: {from: [enclosing_type, declared_name], template: "{enclosing_type}::{declared_name}"}
    emits: [{node: {type: own.callsite}}]
    confidence: declared
"""

PLAIN_CALL = """
  - rule: call_anywhere
    reads: file
    in: [source]
    match: {declaration: function_call_expression, name_child: function, filetype: php}
    id: {from: declared_name}
    emits: [{node: {type: own.callsite}}]
    confidence: declared
"""

REFERENCE_KEYED = """
  - rule: ref_keyed
    reads: file
    in: [source]
    match:
      {reference: function_call_expression, name_child: function, filetype: php,
       holder: function_definition}
    emits: [{edge: {kind: calls, from: enclosing_class, to: enclosing_class}}]
    confidence: declared
"""


def _map(tmp_path: Path, rules: str) -> MapReport:
    plant(tmp_path, rules, SOURCE)
    return run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _callsite_ids(report: MapReport) -> list[str]:
    assert report.map_path is not None
    document = json.loads(Path(report.map_path).read_text())
    return sorted(n["id"] for n in document["nodes"] if n["type"] == "own.callsite")


@pytest.mark.criterion(id="wo3")
def test_holder_rule_fires_only_inside_a_plain_function_wo3(tmp_path: Path) -> None:
    report = _map(tmp_path, HEAD + HOLDER_RULE + METHOD_HOLDER_RULE + KEYED_CALL)
    assert report.problems == ()
    ids = _callsite_ids(report)
    names = sorted(i.rsplit("::", 1)[-1] for i in ids)
    assert names == ["if_call", "loop_call", "plain_call"]
    assert all("outer" in i for i in ids)


@pytest.mark.criterion(id="wo3")
def test_rule_without_holder_key_fires_in_all_places_wo3(tmp_path: Path) -> None:
    report = _map(tmp_path, HEAD + HOLDER_RULE + PLAIN_CALL)
    assert report.problems == ()
    names = sorted(i.rsplit(":", 1)[-1] for i in _callsite_ids(report))
    assert names == ["if_call", "loop_call", "method_call", "plain_call", "top_call"]


@pytest.mark.criterion(id="wo3")
def test_holder_key_on_a_reference_rule_is_refused_at_load_wo3(tmp_path: Path) -> None:
    report = _map(tmp_path, HEAD + HOLDER_RULE + REFERENCE_KEYED)
    assert "ref_keyed" not in [rule for _, rule, _ in report.executed]
    refused = [p.message for p in report.problems if "ref_keyed" in p.message]
    assert refused
    assert all("holder" in m for m in refused)
