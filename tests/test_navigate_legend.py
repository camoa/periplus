"""``periplus legend``: what each edge kind and node type of the map means, most frequent first."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import legend

DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "php.symbol", "parent": None},
        {"type": "php.method", "parent": "php.symbol"},
        {"type": "php.type", "parent": "php.symbol"},
    ],
    "legend": {
        "edge_kinds": {"defines": "the class declares that method"},
        "node_types": {"php.method": "a method of a class"},
    },
    "nodes": [
        _node("php.method::Foo::bar", "php.method"),
        _node("php.method::Foo::baz", "php.method"),
        _node("php.type::Foo", "php.type"),
    ],
    "edges": [
        _edge("calls", "php.method::Foo::bar", "php.method::Foo::baz"),
        _edge("defines", "php.type::Foo", "php.method::Foo::bar"),
        _edge("defines", "php.type::Foo", "php.method::Foo::baz"),
    ],
}


def write_map(root: Path, document: dict[str, Any] = DOCUMENT) -> Path:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    path = root / ".periplus" / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _report(root: Path, **given: Any) -> legend.LegendReport:
    return legend.run(root, {}, write_map(root), **given)


def test_kinds_and_types_come_most_frequent_first_with_their_text(tmp_path: Path) -> None:
    report = _report(tmp_path)

    assert [(r.kind, r.count, r.description) for r in report.edge_kinds] == [
        ("defines", 2, "the class declares that method"),
        ("calls", 1, None),
    ]
    assert report.edge_kinds[0].from_types == (("php.type", 2),)
    assert report.edge_kinds[0].to_types == (("php.method", 2),)
    assert [(r.type, r.count, r.description) for r in report.node_types] == [
        ("php.method", 2, "a method of a class"),
        ("php.type", 1, None),
    ]


def test_text_prints_each_kind_with_its_ends_and_its_text(tmp_path: Path) -> None:
    text = legend.render_text(_report(tmp_path))

    assert "defines  2  php.type -> php.method\n      the class declares that method" in text
    assert "php.method  2  parent: php.symbol\n      a method of a class" in text
    assert text.index("Edge kinds") < text.index("Node types")


def test_one_end_shows_two_types_and_counts_the_rest(tmp_path: Path) -> None:
    nodes = [_node(f"t.{n}::x", f"t.{n}") for n in "abcd"]
    edges = [_edge("uses", f"t.{n}::x", "t.a::x") for n in "abcd"]
    path = write_map(tmp_path, {**DOCUMENT, "nodes": nodes, "edges": edges})
    report = legend.run(tmp_path, {}, path)

    assert "uses  4  t.a, t.b +2 -> t.a" in legend.render_text(report)


def test_the_default_text_stays_within_its_bytes_and_counts_what_it_left_out(
    tmp_path: Path,
) -> None:
    nodes = [_node(f"t.k{i}::x", f"t.k{i}") for i in range(80)]
    edges = [
        _edge(f"kind_{i:02}", f"t.k{i}::x", f"t.k{j}::x")
        for i in range(80)
        for j in range(i % 5 + 1)
    ]
    texts = {f"kind_{i:02}": f"the thing number {i} reaches that other thing" for i in range(80)}
    document = {**DOCUMENT, "nodes": nodes, "edges": edges, "legend": {"edge_kinds": texts}}
    report = legend.run(tmp_path, {}, write_map(tmp_path, document))
    text = legend.render_text(report)

    assert len(text.encode()) <= legend.BYTE_LIMIT
    assert report.left_out > 0
    assert f"{report.left_out} left out" in text
    assert "--all" in text
    # The most frequent kinds stay.
    assert "kind_04  5" in text
    whole = legend.run(tmp_path, {}, write_map(tmp_path, document), everything=True)
    assert whole.left_out == 0
    assert len(whole.edge_kinds) == 80


def test_one_kind_prints_in_full(tmp_path: Path) -> None:
    report = _report(tmp_path, kinds=["defines"])
    text = legend.render_text(report)

    assert [r.kind for r in report.edge_kinds] == ["defines"]
    assert report.node_types == ()
    assert "from: php.type 2" in text
    assert "to: php.method 2" in text


def test_one_type_prints_in_full_with_its_kinds(tmp_path: Path) -> None:
    text = legend.render_text(_report(tmp_path, types=["php.method"]))

    assert "php.method  2  parent: php.symbol" in text
    assert "out: calls 1" in text
    assert "in: defines 2, calls 1" in text


def test_a_kind_the_map_lacks_is_a_warning(tmp_path: Path) -> None:
    report = _report(tmp_path, kinds=["nope"], types=["t.none"])

    assert report.warnings == (
        "the map holds no edge of kind 'nope'",
        "the map holds no node of type 't.none'",
    )


def test_json_carries_the_rows(tmp_path: Path) -> None:
    document = json.loads(legend.render_json(_report(tmp_path)))

    assert document["edge_kinds"][0] == {
        "kind": "defines",
        "count": 2,
        "from": {"php.type": 2},
        "to": {"php.method": 2},
        "description": "the class declares that method",
    }
    assert document["node_types"][1] == {
        "type": "php.type",
        "count": 1,
        "parent": "php.symbol",
        "description": None,
        "out": {"defines": 2},
        "in": {},
    }
    assert document["left_out"] == 0


def test_a_missing_map_is_a_problem(tmp_path: Path) -> None:
    report = legend.run(tmp_path, {}, None)

    assert report.exit_code is ExitCode.MAP_NOT_FOUND


def test_main_prints_the_legend_and_the_choices_are_the_renderers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_map(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["legend", "--kind", "defines", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["edge_kinds"][0]["kind"] == "defines"
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["legend"]._actions if a.dest == "format")
    assert tuple(fmt.choices or ()) == tuple(legend.RENDERERS)
