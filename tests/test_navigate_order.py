"""``periplus order``: a set, each thing after what it calls or uses, loops kept together."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import order

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

PLACES = {
    "a": "z.py:1",
    "b": "a.py:5",
    "c": "a.py:2",
    "d": "b.py:9",
    "e": "b.py:1",
    "f": "c.py:1",
    "g": "c.py:2",
    "h": "c.py:3",
    "x": "d.py:1",
    "y": "d.py:2",
    "out": "e.py:1",
}
NODES = [
    _node(f"fn::{n}", "t.f", line=int(at.split(":")[1]), file=at.split(":")[0])
    for n, at in PLACES.items()
]
EDGES = [
    _edge("calls", "fn::a", "fn::b"),
    _edge("calls", "fn::b", "fn::c"),
    _edge("calls", "fn::c", "fn::b"),
    _edge("calls", "fn::a", "fn::out"),
    _edge("calls", "fn::a", "fn::a"),
    _edge("registered_on", "fn::d", "fn::e"),
    _edge("contains", "fn::f", "fn::g"),
    _edge("mentions", "fn::h", "fn::a"),
    _edge("weird", "fn::x", "fn::y"),
]
CAUSES = {"from": ["calls"], "to": ["registered_on"], "none": ["contains"], "touch": ["mentions"]}
SET = [f"fn::{n}" for n in "abcdefghxy"]


def _write(root: Path, causes: dict[str, list[str]] | None = CAUSES, **header: object) -> Path:
    path = root / "map.json"
    path.write_text(json.dumps(_document(NODES, EDGES, causes, **header)), encoding="utf-8")
    return path


def test_each_thing_comes_after_what_it_uses_ties_by_place(tmp_path: Path) -> None:
    report = order.run(tmp_path, {}, SET, _write(tmp_path))

    assert order.render_text(report).splitlines() == [
        "periplus order",
        "10 things, 1 loop; each after what it calls or uses",
        "  c  t.f  mapped  a.py:2  [loop 1]",
        "  b  t.f  mapped  :5  [loop 1]",
        "  d  t.f  mapped  b.py:9",
        "  e  t.f  mapped  :1",
        "  f  t.f  mapped  c.py:1",
        "  g  t.f  mapped  :2",
        "  h  t.f  mapped  :3",
        "  y  t.f  mapped  d.py:2",
        "  x  t.f  mapped  :1",
        "  a  t.f  mapped  z.py:1",
        "warning: kinds under no cause list, ordered by their raw direction: weird",
    ]


def test_the_order_does_not_depend_on_the_order_given(tmp_path: Path) -> None:
    path = _write(tmp_path)

    assert order.listed(order.run(tmp_path, {}, SET[::-1], path)) == order.listed(
        order.run(tmp_path, {}, SET, path)
    )


def test_a_map_without_causes_orders_by_raw_direction_and_skips_grouping(tmp_path: Path) -> None:
    path = _write(tmp_path, None, grouping_kinds=["contains"])
    report = order.run(tmp_path, {}, ["fn::f", "fn::g", "fn::d", "fn::e"], path)

    assert order.listed(report) == ("fn::e", "fn::d", "fn::f", "fn::g")
    assert report.warnings == (order.NO_CAUSES,)


def test_the_json_marks_loops_and_matches_the_schema(tmp_path: Path) -> None:
    text = order.render_json(order.run(tmp_path, {}, SET, _write(tmp_path)))

    assert (
        list(Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(json.loads(text)))
        == []
    )
    assert [(t["id"], t["loop"]) for t in json.loads(text)["things"][:3]] == [
        ("fn::c", 1),
        ("fn::b", 1),
        ("fn::d", None),
    ]


def test_the_command_line_prints_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path)

    assert main(["order", "fn::a", "fn::b", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out == "fn::b\nfn::a\n"
