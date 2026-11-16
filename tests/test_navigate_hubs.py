"""``periplus hubs``: the hubs the walk by cause from some ids stops at."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import hubs

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"
CAUSES = {"from": ["calls"]}

# a -> h, h -> h0 h1 h2 (h is a hub at --hub 2); a -> b -> g, g -> g0 g1 g2 (a hub at hop 2);
# c0 c1 c2 -> b, so walking by, b has 4 setters and is a hub.
EDGES = [
    ("calls", "x::a", "x::h", 1),
    *(("calls", "x::h", f"x::h{n}", 2) for n in range(3)),
    ("calls", "x::a", "x::b", 3),
    ("calls", "x::b", "x::g", 4),
    *(("calls", "x::g", f"x::g{n}", 5) for n in range(3)),
    *(("calls", f"x::c{n}", "x::b", 6) for n in range(3)),
]


def _write(root: Path, edges: list[tuple[Any, ...]] = EDGES) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], CAUSES)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _found(root: Path, toward: str = "off", depth: int | None = None) -> list[Any]:
    report = hubs.run(root, {}, ["x::a"], toward, depth, 2, _write(root))
    return [(r.id, r.hop, r.hub) for r in report.hubs]


def test_each_hub_the_walk_stops_at_is_listed_with_its_hop_and_fan(tmp_path: Path) -> None:
    assert _found(tmp_path) == [("x::h", 1, 3), ("x::g", 2, 3)]


def test_depth_keeps_the_hubs_within_it(tmp_path: Path) -> None:
    assert _found(tmp_path, depth=1) == [("x::h", 1, 3)]


def test_by_walks_what_sets_the_ids_off(tmp_path: Path) -> None:
    report = hubs.run(tmp_path, {}, ["x::g"], "by", None, 2, _write(tmp_path))

    assert [(r.id, r.hop, r.hub) for r in report.hubs] == [("x::b", 1, 4)]


def test_the_hub_limit_decides_what_is_a_hub(tmp_path: Path) -> None:
    report = hubs.run(tmp_path, {}, ["x::a"], "off", None, 3, _write(tmp_path))

    assert report.hubs == ()


def test_a_hub_line_is_name_type_hop_and_fan(tmp_path: Path) -> None:
    text = hubs.render_text(hubs.run(tmp_path, {}, ["x::a"], "off", None, 2, _write(tmp_path)))

    assert text.splitlines()[1:] == [
        "sets off: 2 hubs (more than 2 links to follow)",
        "  h  t.x  hop 1  fan 3",
        "  g  t.x  hop 2  fan 3",
    ]


def test_a_hub_row_ends_with_its_marks(tmp_path: Path) -> None:
    path = _write(tmp_path)
    document = json.loads(path.read_text())
    document["marks"] = {"installed": "not installed"}
    next(n for n in document["nodes"] if n["id"] == "x::h")["attributes"] = {"installed": "no"}
    path.write_text(json.dumps(document))
    text = hubs.render_text(hubs.run(tmp_path, {}, ["x::a"], "off", 1, 2, path))

    assert text.splitlines()[2] == "  h  t.x  hop 1  fan 3  [not installed]"


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    report = hubs.run(tmp_path, {}, ["x::a"], "off", None, 2, _write(tmp_path))
    document = json.loads(hubs.render_json(report))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert document["hubs"][0] == {
        "id": "x::h",
        "type": "t.x",
        "hop": 1,
        "fan": 3,
        "marks": [],
        "supporting": False,
    }
    assert list(Draft202012Validator(schema).iter_errors(document)) == []


def test_the_command_line_takes_direction_depth_and_hub(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path)
    argv = ["hubs", "x::a", "--hub", "2", "--depth", "1", "--ids", "--map", str(path)]

    assert main(argv) == 0
    assert capsys.readouterr().out == "x::h\n"
    assert (
        main(["hubs", "x::g", "--direction", "by", "--hub", "2", "--ids", "--map", str(path)]) == 0
    )
    assert capsys.readouterr().out == "x::b\n"
