"""An edge kind may declare that it groups: its from end belongs to the container at its to end.

The map lists the grouping kinds it holds edges of, so a command that reads only the map knows
them. A third-party pack declares one exactly as a bundled pack does.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from _own_pack import plant

from periplus.checkmap import run as check_map
from periplus.cli import main
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

SOURCE = "<?php\nclass Box {\n  function alpha() {}\n  function beta() {}\n}\n"

RULES = """
node_types:
  - {name: own.fn, id_namespace: fn}
  - {name: own.box, id_namespace: box}
edge_kinds:
  - {kind: fn_in_box, from: [own.fn], to: [own.box]%s}
  - {kind: unused_in_box, from: [own.fn], to: [own.box], groups: true}
  - {kind: calls, from: [own.fn], to: [own.fn]}
rules:
  - rule: box
    reads: file
    in: [source]
    match: {declaration: class_declaration, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.box}}]
    confidence: declared
  - rule: fn
    reads: file
    in: [source]
    match: {declaration: method_declaration, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{node: {type: own.fn}}]
    confidence: declared
  - rule: fn_box
    reads: file
    in: [source]
    match: {declaration: method_declaration, name_child: name, body_child: body, filetype: php}
    id: {from: qualified_name}
    emits: [{edge: {kind: fn_in_box, from: this_node, to: enclosing_class}}]
    confidence: declared
"""


def _map(root: Path, groups: str) -> dict[str, object]:
    plant(root, RULES % groups, SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert check_map(root, {}, root / "map.json").exit_code == 0
    document: dict[str, object] = json.loads((root / "map.json").read_text())
    return document


def test_the_map_lists_the_grouping_kinds_it_holds_edges_of(tmp_path: Path) -> None:
    document = _map(tmp_path, ", groups: true")

    assert document["grouping_kinds"] == ["fn_in_box"]


def test_a_map_without_a_grouping_edge_has_no_list(tmp_path: Path) -> None:
    assert "grouping_kinds" not in _map(tmp_path, "")


def test_validate_refuses_a_groups_value_that_is_not_true_or_false(tmp_path: Path) -> None:
    plant(tmp_path, RULES % ', groups: "yes"', SOURCE)
    printed = io.StringIO()
    with contextlib.chdir(tmp_path), contextlib.redirect_stdout(printed):
        code = main(["validate", "own"])

    assert code != 0
    assert "groups" in printed.getvalue()
