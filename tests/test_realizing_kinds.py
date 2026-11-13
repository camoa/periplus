"""An edge kind may declare that it realizes: its from end is a concrete form of its to end.

The map lists the realizing kinds it holds edges of, so a command that reads only the map knows
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
  - {kind: fn_of_box, from: [own.fn], to: [own.box]%s}
  - {kind: unused_of_box, from: [own.fn], to: [own.box], realizes: true}
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
    emits: [{edge: {kind: fn_of_box, from: this_node, to: enclosing_class}}]
    confidence: declared
"""


def _map(root: Path, realizes: str) -> tuple[dict[str, object], bytes]:
    plant(root, RULES % realizes, SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert check_map(root, {}, root / "map.json").exit_code == 0
    written = (root / "map.json").read_bytes()
    document: dict[str, object] = json.loads(written)
    return document, written


def test_the_map_lists_the_realizing_kinds_it_holds_edges_of(tmp_path: Path) -> None:
    document, _ = _map(tmp_path, ", realizes: true")

    assert document["realizing_kinds"] == ["fn_of_box"]


def test_a_map_without_a_realizing_edge_is_unchanged(tmp_path: Path) -> None:
    document, written = _map(tmp_path / "a", "")
    _, explicit = _map(tmp_path / "b", ", realizes: false")

    assert "realizing_kinds" not in document
    assert written == explicit


def test_validate_refuses_a_realizes_value_that_is_not_true_or_false(tmp_path: Path) -> None:
    plant(tmp_path, RULES % ', realizes: "yes"', SOURCE)
    printed = io.StringIO()
    with contextlib.chdir(tmp_path), contextlib.redirect_stdout(printed):
        code = main(["validate", "own"])

    assert code != 0
    assert "realizes" in printed.getvalue()
