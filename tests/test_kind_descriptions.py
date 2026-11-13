"""A node type and an edge kind may carry a one-line description, and the map carries the
descriptions of the types and kinds it holds under ``legend``.

A third-party pack declares one exactly as a bundled pack does.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from _own_pack import PACK, plant

from periplus.checkmap import run as check_map
from periplus.cli import main
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

SOURCE = "<?php\nclass Box {\n  function alpha() {}\n}\n"

RULES = """
node_types:
  - {name: own.fn, id_namespace: fn%s}
  - {name: own.box, id_namespace: box}
  - {name: own.unused, id_namespace: unused, description: "a type no node has"}
edge_kinds:
  - {kind: fn_in_box, from: [own.fn], to: [own.box]%s}
  - {kind: unused_in_box, from: [own.fn], to: [own.box], description: "no edge has it"}
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

FN = ', description: "a method of the box"'
KIND = ', description: "the method is written inside that box"'


def _map(root: Path, fn: str, kind: str) -> tuple[dict[str, object], str]:
    plant(root, RULES % (fn, kind), SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert check_map(root, {}, root / "map.json").exit_code == 0
    text = (root / "map.json").read_text()
    document: dict[str, object] = json.loads(text)
    return document, text


def _validate(root: Path) -> tuple[int, str]:
    printed = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(printed):
        code = main(["validate", "own"])
    return code, printed.getvalue()


def test_the_map_carries_the_descriptions_of_the_types_and_kinds_it_holds(tmp_path: Path) -> None:
    document, _ = _map(tmp_path, FN, KIND)

    assert document["legend"] == {
        "edge_kinds": {"fn_in_box": "the method is written inside that box"},
        "node_types": {"own.fn": "a method of the box"},
    }


def test_a_map_from_packs_without_descriptions_has_no_legend(tmp_path: Path) -> None:
    plain = RULES.replace(', description: "a type no node has"', "").replace(
        ', description: "no edge has it"', ""
    )
    plant(tmp_path, plain % ("", ""), SOURCE)
    run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((tmp_path / "map.json").read_text())

    assert "legend" not in document


def test_a_held_kind_without_description_leaves_its_section_out(tmp_path: Path) -> None:
    document, _ = _map(tmp_path, FN, "")

    assert document["legend"] == {"node_types": {"own.fn": "a method of the box"}}


def test_validate_refuses_a_description_over_the_length(tmp_path: Path) -> None:
    plant(tmp_path, RULES % (FN, f', description: "{"x" * 201}"'), SOURCE)
    code, printed = _validate(tmp_path)

    assert code != 0
    assert "description" in printed
    assert "maxLength" in printed


def test_validate_refuses_a_description_on_two_lines(tmp_path: Path) -> None:
    plant(tmp_path, RULES % (FN, ', description: "one line\\ntwo lines"'), SOURCE)
    code, printed = _validate(tmp_path)

    assert code != 0
    assert "description" in printed
    assert "one line" in printed


def test_validate_refuses_two_different_descriptions_of_one_kind(tmp_path: Path) -> None:
    plant(tmp_path, RULES % (FN, KIND), SOURCE)
    other = "edge_kinds:\n  - {kind: fn_in_box, from: [own.fn], to: [own.box], %s}\n"
    (tmp_path / PACK / "rules" / "other.yaml").write_text(other % 'description: "another text"')
    code, printed = _validate(tmp_path)

    assert code != 0
    assert "fn_in_box" in printed
    assert "description" in printed


def test_a_declaration_without_description_agrees_with_one_that_has_it(tmp_path: Path) -> None:
    plant(tmp_path, RULES % (FN, KIND), SOURCE)
    other = "edge_kinds:\n  - {kind: fn_in_box, from: [own.fn], to: [own.box]}\n"
    (tmp_path / PACK / "rules" / "other.yaml").write_text(other)
    code, _ = _validate(tmp_path)

    assert code == 0
