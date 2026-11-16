"""``periplus pieces``: a set of ids split into the groups that edges among them join."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import pieces

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

# a -calls-> b, c -contains-> d, b -calls-> x -calls-> c (x outside the set), e alone.
EDGES = [
    ("calls", "x::a", "x::b", 1),
    ("contains", "x::c", "x::d", 2),
    ("calls", "x::b", "x::x", 3),
    ("calls", "x::x", "x::c", 4),
]
NAMES = ["x::a", "x::b", "x::c", "x::d", "x::e", "x::x"]


def _write(root: Path, edges: list[tuple[Any, ...]] = EDGES) -> Path:
    document = _document([_node(n, line=1) for n in NAMES], [_edge(*e) for e in edges])
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _pieces(root: Path, *ids: str) -> list[list[str]]:
    report = pieces.run(root, {}, list(ids), _write(root))
    return [[t.id for t in piece] for piece in report.pieces]


def test_an_edge_of_any_kind_joins_two_ids(tmp_path: Path) -> None:
    assert _pieces(tmp_path, "x::c", "x::d") == [["x::c", "x::d"]]


def test_a_thing_outside_the_set_joins_nothing(tmp_path: Path) -> None:
    assert _pieces(tmp_path, "x::b", "x::c") == [["x::b"], ["x::c"]]


def test_a_chain_through_the_set_joins_its_ends(tmp_path: Path) -> None:
    assert _pieces(tmp_path, "x::a", "x::b", "x::x", "x::c") == [["x::a", "x::b", "x::c", "x::x"]]


def test_pieces_go_largest_first_then_by_smallest_id(tmp_path: Path) -> None:
    assert _pieces(tmp_path, "x::e", "x::c", "x::d", "x::b") == [
        ["x::c", "x::d"],
        ["x::b"],
        ["x::e"],
    ]


def test_the_text_heads_each_piece_with_its_size(tmp_path: Path) -> None:
    text = pieces.render_text(pieces.run(tmp_path, {}, ["x::c", "x::d", "x::e"], _write(tmp_path)))

    assert text.splitlines() == [
        "periplus pieces",
        "3 things in 2 pieces",
        "piece 1: 2 things",
        "  c  t.x  mapped  src/a.php:1",
        "  d  t.x  mapped  :1",
        "piece 2: 1 thing",
        "  e  t.x  mapped  src/a.php:1",
    ]


def test_ids_puts_a_blank_line_between_pieces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path)

    assert main(["pieces", "x::c", "x::d", "x::e", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out == "x::c\nx::d\n\nx::e\n"


def test_a_row_ends_with_its_marks(tmp_path: Path) -> None:
    path = _write(tmp_path)
    document = json.loads(path.read_text())
    document["marks"] = {"installed": "not installed"}
    document["nodes"][4]["attributes"] = {"installed": "no"}
    path.write_text(json.dumps(document))
    text = pieces.render_text(pieces.run(tmp_path, {}, ["x::e"], path))

    assert text.splitlines()[3] == "  e  t.x  mapped  src/a.php:1  [not installed]"


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    report = pieces.run(tmp_path, {}, ["x::c", "x::d", "x::e"], _write(tmp_path))
    document = json.loads(pieces.render_json(report))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert [[t["id"] for t in p] for p in document["pieces"]] == [["x::c", "x::d"], ["x::e"]]
    assert list(Draft202012Validator(schema).iter_errors(document)) == []
