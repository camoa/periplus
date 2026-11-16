"""An edge kind may declare which end sets off the other: ``cause: from | to | none | touch``.

The map lists each kind it holds edges of under the direction it resolves to, so a command that
reads only the map tells a forward kind from a backward one, a structural one, one that only
points, and an undeclared one. A third-party pack declares one exactly as a bundled pack does.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest
from _own_pack import PACK, plant

from periplus.checkmap import run as check_map
from periplus.cli import main
from periplus.map import run
from periplus.navigate import legend
from periplus.navigate.mapfile import MapIndex
from periplus.preflight import check_runtime_dependencies

SOURCE = "<?php\nclass Box {\n  function alpha() {}\n  function beta() {}\n}\n"

RULES = """
node_types:
  - {name: own.fn, id_namespace: fn}
  - {name: own.box, id_namespace: box}
edge_kinds:
  - {kind: fn_in_box, from: [own.fn], to: [own.box]%s}
  - {kind: unused_in_box, from: [own.fn], to: [own.box], cause: to}
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

LISTS = ("cause_from_kinds", "cause_to_kinds", "cause_none_kinds", "cause_touch_kinds")


def _map(root: Path, declared: str) -> dict[str, object]:
    plant(root, RULES % declared, SOURCE)
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


def _lists(document: dict[str, object]) -> dict[str, object]:
    return {name: document[name] for name in LISTS if name in document}


def _validate(root: Path) -> tuple[int, str]:
    printed = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(printed):
        code = main(["validate", "own"])
    return code, printed.getvalue()


@pytest.mark.parametrize(
    ("declared", "listed"),
    [
        (", cause: from", "cause_from_kinds"),
        (", cause: to", "cause_to_kinds"),
        (", cause: none", "cause_none_kinds"),
        (", cause: touch", "cause_touch_kinds"),
        (", groups: true", "cause_none_kinds"),
        (", realizes: true", "cause_to_kinds"),
        (", realizes: to", "cause_from_kinds"),
        (", groups: true, cause: none", "cause_none_kinds"),
        (", realizes: true, cause: from", "cause_from_kinds"),
    ],
)
def test_the_map_lists_each_kind_it_holds_edges_of_under_its_cause(
    tmp_path: Path, declared: str, listed: str
) -> None:
    assert _lists(_map(tmp_path, declared)) == {listed: ["fn_in_box"]}


def test_an_undeclared_kind_is_in_no_list(tmp_path: Path) -> None:
    assert _lists(_map(tmp_path, "")) == {}


def test_validate_refuses_a_cause_that_is_not_from_to_or_none(tmp_path: Path) -> None:
    plant(tmp_path, RULES % ", cause: backward", SOURCE)
    code, printed = _validate(tmp_path)

    assert code != 0
    assert "cause" in printed


@pytest.mark.parametrize("cause", ["from", "to", "touch"])
def test_validate_refuses_a_cause_a_grouping_kind_cannot_have(tmp_path: Path, cause: str) -> None:
    plant(tmp_path, RULES % f", groups: true, cause: {cause}", SOURCE)
    code, printed = _validate(tmp_path)

    assert code == 19
    assert f"the edge kind fn_in_box declares cause: {cause}" in printed
    assert "groups: true" in printed


def test_two_files_that_give_one_kind_different_causes_are_refused(tmp_path: Path) -> None:
    plant(tmp_path, RULES % ", cause: from", SOURCE)
    other = tmp_path / PACK / "rules" / "other.yaml"
    other.write_text(
        "edge_kinds:\n  - {kind: fn_in_box, from: [own.fn], to: [own.box], cause: to}\n"
    )
    code, printed = _validate(tmp_path)

    assert code == 19
    assert "the edge kind fn_in_box is declared with different" in printed
    assert "cause" in printed


def test_the_index_gives_each_kinds_cause_and_none_for_an_undeclared_kind() -> None:
    index = MapIndex(
        {
            "nodes": [],
            "edges": [],
            "cause_from_kinds": ["calls"],
            "cause_to_kinds": ["implements_hook"],
            "cause_none_kinds": ["in_module"],
            "cause_touch_kinds": ["links_to"],
        }
    )

    kinds = ("calls", "implements_hook", "in_module", "links_to", "other")
    assert [index.cause(k) for k in kinds] == ["from", "to", "none", "touch", None]


def test_the_index_of_a_map_without_the_lists_gives_none_for_every_kind() -> None:
    index = MapIndex({"nodes": [], "edges": [], "grouping_kinds": ["in_module"]})

    assert index.cause("in_module") is None


def test_legend_names_a_declared_cause_and_leaves_an_undeclared_row_alone(
    tmp_path: Path,
) -> None:
    _map(tmp_path, ", cause: to")
    document = json.loads((tmp_path / "map.json").read_text())
    document["edges"].append({**document["edges"][0], "kind": "loose"})
    (tmp_path / "map.json").write_text(json.dumps(document))

    report = legend.run(tmp_path, {}, tmp_path / "map.json")
    text = legend.render_text(report)

    assert [(r.kind, r.cause) for r in report.edge_kinds] == [("fn_in_box", "to"), ("loose", None)]
    assert "  fn_in_box  2  own.fn -> own.box  cause: to\n" in text
    assert "  loose  1  own.fn -> own.box\n" in text
    assert '"cause": "to"' in legend.render_json(report)
