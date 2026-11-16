"""``periplus count``: how many things a set of ids names, by type and state, and the edges among
them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import count

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

NODES = [
    _node("f::a", "t.function", line=1),
    _node("f::b", "t.function", line=2),
    _node("c::B", "t.class", "referenced"),
    _node("f::out", "t.function", line=3),
    _node("g::run", "t.method", line=4),
    _node("h::run", "t.method", line=5),
]
EDGES = [
    _edge("calls", "f::a", "f::b", 1),
    _edge("calls", "f::b", "c::B", 2),
    _edge("uses", "f::a", "c::B", 3),
    _edge("calls", "f::out", "f::a", 4),
]


def _write(root: Path) -> Path:
    path = root / "map.json"
    path.write_text(json.dumps(_document(NODES, EDGES)), encoding="utf-8")
    return path


def _count(root: Path, *ids: str) -> count.CountReport:
    return count.run(root, {}, list(ids), _write(root))


def test_it_counts_the_things_by_type_most_first(tmp_path: Path) -> None:
    assert _count(tmp_path, "f::a", "f::b", "c::B").by_type == (("t.function", 2), ("t.class", 1))


def test_it_counts_the_things_by_state(tmp_path: Path) -> None:
    assert _count(tmp_path, "f::a", "c::B").by_state == (("mapped", 1), ("referenced", 1))


def test_it_counts_only_the_edges_whose_two_ends_are_in_the_set_by_kind(tmp_path: Path) -> None:
    assert _count(tmp_path, "f::a", "f::b", "c::B").edges == (("calls", 2), ("uses", 1))


def test_an_id_that_names_no_node_is_listed_not_a_problem(tmp_path: Path) -> None:
    report = _count(tmp_path, "f::a", "nope")

    assert (report.things, report.missing, report.problems) == (1, (("nope", 0),), ())


def test_a_short_name_that_fits_several_is_listed_with_how_many(tmp_path: Path) -> None:
    assert _count(tmp_path, "run").missing == (("run", 2),)


def test_a_thing_named_twice_counts_once_and_is_said(tmp_path: Path) -> None:
    report = _count(tmp_path, "f::a", "a")

    assert (report.given, report.things, report.repeated, report.short) == (2, 1, 1, 1)


def test_the_text_says_each_count_on_a_line(tmp_path: Path) -> None:
    text = count.render_text(_count(tmp_path, "f::a", "f::b", "nope"))

    assert text.splitlines() == [
        "periplus count",
        "3 ids given: 2 things in the map, 1 not",
        "by type: t.function 2",
        "by state: mapped 2",
        "edges among them: 1 (calls 1)",
        "not in the map:",
        "  nope",
    ]


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    document = json.loads(count.render_json(_count(tmp_path, "f::a", "run")))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert document["not_found"] == [{"id": "run", "fits": 2}]
    assert list(Draft202012Validator(schema).iter_errors(document)) == []


def test_the_command_line_reads_ids_from_standard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("f::a\n\nf::b\n"))

    assert main(["count", "-", "--map", str(path)]) == 0
    assert capsys.readouterr().out.splitlines()[1] == "2 ids given: 2 things in the map"
