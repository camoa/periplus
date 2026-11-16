"""``periplus only``: the things the ids set off that nothing else sets off."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import only

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"
CAUSES = {"from": ["calls"], "to": ["implements_hook"], "none": ["contains"]}


def _write(root: Path, edges: list[tuple[Any, ...]]) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], CAUSES)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _only(root: Path, edges: list[tuple[Any, ...]], *starts: str) -> list[str]:
    report = only.run(root, {}, list(starts), _write(root, edges))
    return [t.row.id for t in report.things]


def test_a_thing_only_the_start_sets_off_is_kept(tmp_path: Path) -> None:
    assert _only(tmp_path, [("calls", "x::s", "x::a", 1)], "x::s") == ["x::a"]


def test_a_thing_something_else_also_sets_off_is_left_out(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::y", "x::a", 2)]

    assert _only(tmp_path, edges, "x::s") == []


def test_what_a_left_out_thing_sets_off_is_left_out_too(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::y", "x::a", 2)]
    edges += [("calls", "x::a", "x::b", 3)]

    assert _only(tmp_path, edges, "x::s") == []


def test_a_loop_the_start_alone_feeds_is_kept(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::a", "x::b", 2)]
    edges += [("calls", "x::b", "x::a", 3)]

    assert _only(tmp_path, edges, "x::s") == ["x::a", "x::b"]


def test_several_starts_count_as_one_set(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::t", "x::a", 2)]

    assert _only(tmp_path, edges, "x::s") == []
    assert _only(tmp_path, edges, "x::s", "x::t") == ["x::a"]


def test_a_to_kind_sets_off_its_from_end(tmp_path: Path) -> None:
    edges = [("implements_hook", "x::f", "x::h", 1), ("calls", "x::y", "x::g", 2)]

    assert _only(tmp_path, edges, "x::h") == ["x::f"]


def test_a_none_kind_does_not_set_off(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("contains", "x::m", "x::a", 2)]

    assert _only(tmp_path, edges, "x::s") == ["x::a"]


def test_the_text_counts_and_lists_each_thing(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::s", "x::b", 2)]
    edges += [("calls", "x::y", "x::b", 3)]
    text = only.render_text(only.run(tmp_path, {}, ["x::s"], _write(tmp_path, edges)))

    assert text.splitlines()[2:] == [
        "only through the starts: 1 of 2",
        "  a  t.x  mapped  hop 1  src/a.php:1",
    ]


def test_a_row_ends_with_its_marks_and_supporting_code(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::a", 1), ("calls", "x::s", "x::b", 2)]
    names = ["x::a", "x::b", "x::s"]
    nodes = [_node(n, line=1, file="tests/t.php" if n == "x::b" else "src/a.php") for n in names]
    nodes[0]["attributes"] = {"installed": "no"}
    document = _document(nodes, [_edge(*e) for e in edges], CAUSES)
    document |= {"marks": {"installed": "not installed"}, "supporting_paths": ["tests/**"]}
    path = tmp_path / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    text = only.render_text(only.run(tmp_path, {}, ["x::s"], path))

    assert text.splitlines()[3:] == [
        "  a  t.x  mapped  hop 1  src/a.php:1  [not installed]",
        "  b  t.x  mapped  hop 1  tests/t.php:1  [supporting code]",
    ]


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    report = only.run(tmp_path, {}, ["x::s"], _write(tmp_path, [("calls", "x::s", "x::a", 1)]))
    document = json.loads(only.render_json(report))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert document["only"][0]["id"] == "x::a"
    assert list(Draft202012Validator(schema).iter_errors(document)) == []


def test_the_command_line_runs_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, [("calls", "x::s", "x::a", 1)])

    assert main(["only", "x::s", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out == "x::a\n"
