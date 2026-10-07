"""A boundary name with a classification: a first-party class whose ancestry reaches it, through
mapped classes only, takes the classified type with an inferred provenance row from the listing
pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.map import MapReport, render_text, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: [yaml_basic]
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
  resolve: [full_if_prefixed: "\\\\", prefix_with: namespace]
boundary:
  framework:
    type: own.class_like
    ancestry: [inherits]
    names:
      "Fw\\\\Base": {classifies}
"""

RULES = """\
node_types:
- {name: own.class_like, id_namespace: own.type}
- {name: own.class, parent: own.class_like}
- {name: own.form, parent: own.class}
- {name: own.other, parent: own.class_like}
edge_kinds:
- {kind: inherits, from: own.class_like, to: own.class_like}
rules:
- rule: find_class
  reads: file
  in: [code]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: inherits
  reads: file
  in: [code]
  match: {declaration: base_clause, filetype: php}
  emits: [{edge: {kind: inherits, from: enclosing_class, to: {from: qualified_name}}}]
  confidence: declared
- rule: listed_base
  reads: file
  in: [code]
  match: {file: '*', filetype: yaml}
  id: {from: file_stem}
  emits: [{edge: {kind: inherits, from: this_node, to: {from: {key: base}}}}]
  confidence: declared
"""

#: B and A descend from the listed base through mapped classes. Mid.yml draws an edge from Mid to
#: the base, and no rule maps Mid, so it stays referenced and C's walk stops there. Lone has no
#: boundary ancestor.
SOURCE = """\
<?php

namespace App;

class B extends \\Fw\\Base {}

class A extends B {}

class C extends \\Mid {}

class Lone {}
"""


def _run(root: Path, classifies: str = "own.form") -> MapReport:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(MANIFEST.format(classifies=classifies))
    (pack / "rules" / "own.yaml").write_text(RULES)
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [own@0.0.1, yaml_basic@0.1.0]\n"
    )
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(SOURCE)
    (root / "src" / "Mid.yml").write_text("base: Fw\\Base\n")
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _nodes(root: Path) -> dict[str, dict[str, Any]]:
    document = json.loads((root / "map.json").read_text())
    return {node["id"]: node for node in document["nodes"]}


INFERRED = {"pack": "own", "rule": "boundary.framework", "confidence": "inferred", "sets": ["type"]}
FOUND = {"pack": "own", "rule": "find_class", "confidence": "declared", "sets": ["id", "type"]}


def test_a_chain_to_a_classifying_base_classifies_every_class_on_it(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == () and report.skipped == (), report
    nodes = _nodes(tmp_path)
    for name in ("App\\B", "App\\A"):
        node = nodes[f"own.type::{name}"]
        assert node["type"] == "own.form", node
        assert node["provenance"] == [FOUND, INFERRED], node


def test_a_class_with_no_boundary_ancestor_is_untouched(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == (), report
    node = _nodes(tmp_path)["own.type::App\\Lone"]
    assert node["type"] == "own.class", node
    assert node["provenance"] == [FOUND], node


def test_a_referenced_class_between_stops_the_walk(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == (), report
    nodes = _nodes(tmp_path)
    # The planted path exists: C inherits Mid, Mid inherits the base, and no rule maps Mid.
    document = json.loads((tmp_path / "map.json").read_text())
    pairs = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "inherits"}
    assert ("own.type::App\\C", "own.type::Mid") in pairs, pairs
    assert ("own.type::Mid", "own.type::Fw\\Base") in pairs, pairs
    assert nodes["own.type::Mid"]["state"] == "referenced", nodes["own.type::Mid"]
    node = nodes["own.type::App\\C"]
    assert node["type"] == "own.class", node
    assert node["provenance"] == [FOUND], node


def test_a_type_off_the_classifications_chain_is_kept_and_reported(tmp_path: Path) -> None:
    """own.other and own.class are siblings: neither descends from the other."""
    report = _run(tmp_path, classifies="own.other")
    assert report.problems == (), report
    nodes = _nodes(tmp_path)
    for name in ("App\\B", "App\\A"):
        node = nodes[f"own.type::{name}"]
        assert node["type"] == "own.class", node
        assert node["provenance"] == [FOUND], node
    for name, line in (("App\\B", 5), ("App\\A", 7)):
        reason = (
            f"own.type::{name}: classification own.other from own.type::Fw\\Base "
            "does not descend from own.class"
        )
        rows = [row for row in report.skipped if row[3] == reason]
        assert rows == [("src/a.php", line, "boundary.framework", reason)], report.skipped
    assert len(report.skipped) == 2, report.skipped
    # The report text escapes a backslash.
    assert "classification own.other from own.type::Fw\\\\Base" in render_text(report)


def test_two_runs_give_byte_equal_documents(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    assert _run(first).problems == ()
    assert _run(second).problems == ()
    assert (first / "map.json").read_bytes() == (second / "map.json").read_bytes()
