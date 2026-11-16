"""``periplus members``: what a container holds, by the map's grouping kinds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import members

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

NODES = [
    _node("mod::m", "t.module", line=1, file="m/m.info"),
    _node("fn::f2", "t.function", line=9, file="m/a.php"),
    _node("fn::f1", "t.function", line=10, file="m/a.php"),
    _node("cls::C", "t.class", line=3, file="m/C.php"),
    _node("cls::C::run", "t.method", line=4, file="m/C.php"),
    _node("fn::other", "t.function", line=1, file="n/b.php"),
]
EDGES = [
    _edge("function_in_module", "fn::f2", "mod::m", 9),
    _edge("function_in_module", "fn::f1", "mod::m", 10),
    _edge("class_in_module", "cls::C", "mod::m", 3),
    _edge("class_in_module", "cls::C", "mod::m", 3),
    _edge("calls", "fn::other", "mod::m", 1),
    _edge("contains", "cls::C", "cls::C::run", 4),
]


def _write(root: Path) -> Path:
    document = _document(
        NODES,
        EDGES,
        grouping_kinds=["class_in_module", "function_in_module"],
        type_hierarchy=[
            {"type": "t.function", "parent": None},
            {"type": "t.class", "parent": None},
        ],
    )
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _report(root: Path, types: list[str] | None = None) -> members.MembersReport:
    return members.run(root, {}, ["mod::m"], types or [], _write(root))


def test_members_are_the_from_ends_of_grouping_edges_each_once(tmp_path: Path) -> None:
    held = _report(tmp_path).held[0]

    assert sorted(m.id for m in held.members) == ["cls::C", "fn::f1", "fn::f2"]


def test_counts_by_type_come_most_first(tmp_path: Path) -> None:
    assert _report(tmp_path).held[0].by_type == (("t.function", 2), ("t.class", 1))


def test_members_list_by_type_then_place(tmp_path: Path) -> None:
    held = _report(tmp_path).held[0]

    assert [m.id for m in held.members] == ["fn::f2", "fn::f1", "cls::C"]


def test_type_keeps_one_type(tmp_path: Path) -> None:
    held = _report(tmp_path, ["t.class"]).held[0]

    assert [m.id for m in held.members] == ["cls::C"]


def test_the_text_has_the_count_line_then_a_row_a_member(tmp_path: Path) -> None:
    text = members.render_text(_report(tmp_path))

    assert text.splitlines() == [
        "periplus members",
        "members of m: 3 (t.function 2, t.class 1)",
        "  f2  t.function  mapped  m/a.php:9",
        "  f1  t.function  mapped  :10",
        "  C  t.class  mapped  m/C.php:3",
    ]


def test_a_thing_with_no_members_says_zero(tmp_path: Path) -> None:
    report = members.run(tmp_path, {}, ["fn::other"], [], _write(tmp_path))

    assert members.render_text(report).splitlines()[1] == "members of other: 0"


def test_a_row_ends_with_its_marks_and_supporting_code(tmp_path: Path) -> None:
    path = _write(tmp_path)
    document = json.loads(path.read_text())
    document |= {"marks": {"installed": "not installed"}, "supporting_paths": ["m/C.php"]}
    document["nodes"][1]["attributes"] = {"installed": "no"}
    path.write_text(json.dumps(document))
    lines = members.render_text(members.run(tmp_path, {}, ["mod::m"], [], path)).splitlines()

    assert lines[2:] == [
        "  f2  t.function  mapped  m/a.php:9  [not installed]",
        "  f1  t.function  mapped  :10",
        "  C  t.class  mapped  m/C.php:3  [supporting code]",
    ]


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    document = json.loads(members.render_json(_report(tmp_path)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert document["containers"][0]["by_type"] == {"t.class": 1, "t.function": 2}
    assert list(Draft202012Validator(schema).iter_errors(document)) == []


def test_the_command_line_prints_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path)

    assert main(["members", "mod::m", "--type", "t.function", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out == "fn::f2\nfn::f1\n"
