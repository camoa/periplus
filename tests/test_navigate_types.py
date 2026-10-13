"""``periplus types``: the counts, the parents, both formats, the exit codes and the CLI tie."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import types

PROV = {"pack": "php", "rule": "r", "sets": []}


def _node(id: str, type: str) -> dict[str, Any]:
    return {"id": id, "type": type, "state": "mapped", "locations": [], "provenance": [PROV]}


def _edge(kind: str, source: str, target: str) -> dict[str, Any]:
    return {"kind": kind, "from": source, "to": target, "locations": [], "provenance": [PROV]}


DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "php.symbol", "parent": None},
        {"type": "php.method", "parent": "php.symbol"},
        {"type": "php.type", "parent": "php.symbol"},
    ],
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


def write_map(root: Path) -> Path:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    path = root / ".periplus" / "map.json"
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    return path


def _report(root: Path) -> types.TypesReport:
    return types.run(root, {}, write_map(root))


def test_every_type_and_kind_present_is_counted_with_its_parent(tmp_path: Path) -> None:
    report = _report(tmp_path)

    assert report.node_types == (
        ("php.method", 2, "php.symbol"),
        ("php.type", 1, "php.symbol"),
    )
    assert report.edge_kinds == (("calls", 1), ("defines", 2))
    assert report.exit_code is ExitCode.OK


def test_a_type_absent_from_the_map_is_not_listed(tmp_path: Path) -> None:
    # php.symbol is in the hierarchy but no node has it.
    report = _report(tmp_path)

    assert "php.symbol" not in [t for t, _, _ in report.node_types]
    assert json.loads(types.render_json(report))["node_types"][0]["type"] == "php.method"


def test_json_carries_the_same_rows_sorted_with_a_trailing_newline(tmp_path: Path) -> None:
    text = types.render_json(_report(tmp_path))

    assert text.endswith("}\n")
    assert json.loads(text)["node_types"] == [
        {"type": "php.method", "count": 2, "parent": "php.symbol"},
        {"type": "php.type", "count": 1, "parent": "php.symbol"},
    ]
    assert json.loads(text)["edge_kinds"] == [
        {"kind": "calls", "count": 1},
        {"kind": "defines", "count": 2},
    ]


def test_text_lists_each_type_with_its_count_and_parent(tmp_path: Path) -> None:
    text = types.render_text(_report(tmp_path))

    assert "php.method  2  parent: php.symbol" in text
    assert "defines  2" in text


def test_a_missing_map_is_a_problem_report_with_its_exit_code(tmp_path: Path) -> None:
    report = types.run(tmp_path, {}, None)

    assert report.exit_code is ExitCode.MAP_NOT_FOUND
    assert "map" in types.render_text(report)
    assert json.loads(types.render_json(report))["problems"][0]["code"] == 29


def test_the_format_choices_are_exactly_the_types_renderers() -> None:
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["types"]._actions if a.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(types.RENDERERS)
    assert fmt.default == next(iter(types.RENDERERS))


def test_main_reads_the_default_map_and_the_named_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_map(tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({**DOCUMENT, "edges": []}))
    monkeypatch.chdir(tmp_path)

    assert main(["types", "--format", "json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["edge_kinds"]) == 2
    assert main(["types", "--format", "json", "--map", str(other)]) == 0
    assert json.loads(capsys.readouterr().out)["edge_kinds"] == []


def test_main_exits_with_the_codes_for_no_map_and_a_bad_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["types"]) == int(ExitCode.MAP_NOT_FOUND)
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert main(["types", "--map", str(bad)]) == int(ExitCode.NOT_A_MAP)
    assert str(bad) in capsys.readouterr().out
