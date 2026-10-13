"""``periplus find``: the order, the type filter, the empty cases, the cut and the CLI tie."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import find

PROV = {"pack": "php", "rule": "r", "sets": []}


def _node(id: str, type: str, line: int | None = None) -> dict[str, Any]:
    where = [{"file": "src/a.php", "line": line}] if line else []
    return {"id": id, "type": type, "state": "mapped", "locations": where, "provenance": [PROV]}


DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "type_hierarchy": [
        {"type": "php.symbol", "parent": None},
        {"type": "php.method", "parent": "php.symbol"},
        {"type": "php.type", "parent": "php.symbol"},
        {"type": "yaml.key", "parent": None},
    ],
    "nodes": [
        _node("php.method::Foo::cache", "php.method", 3),
        _node("php.type::Cache", "php.type", 1),
        _node("php.type::CacheBackend", "php.type", 9),
        _node("php.type::MyCache", "php.type"),
        _node("php.type::Cache::Zed", "php.type"),
        _node("yaml.key::cache", "yaml.key", 2),
    ],
    "edges": [],
}


def _map(root: Path) -> Path:
    path = root / "map.json"
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    return path


def _ids(report: find.FindReport) -> list[str]:
    return [row["id"] for row in report.matches.items]


def test_matches_are_closest_first_with_ties_broken_by_id(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "CACHE", None, 50, _map(tmp_path))

    assert _ids(report) == [
        "php.method::Foo::cache",  # name equals the text, id order
        "php.type::Cache",
        "yaml.key::cache",
        "php.type::CacheBackend",  # name starts with it
        "php.type::MyCache",  # name holds it
        "php.type::Cache::Zed",  # only the id holds it
    ]
    assert find.run(tmp_path, {}, "CACHE", None, 50, _map(tmp_path)) == report


def test_a_row_carries_type_state_and_first_location(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "CacheBackend", None, 50, _map(tmp_path))

    assert report.matches.items == (
        {
            "id": "php.type::CacheBackend",
            "type": "php.type",
            "state": "mapped",
            "location": "src/a.php:9",
        },
    )
    assert (
        find.run(tmp_path, {}, "MyCache", None, 50, _map(tmp_path)).matches.items[0]["location"]
        is None
    )


def test_the_whole_id_ranks_first(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "yaml.key::cache", None, 50, _map(tmp_path))

    assert _ids(report)[0] == "yaml.key::cache"


def test_type_keeps_the_type_and_its_subtypes(tmp_path: Path) -> None:
    path = _map(tmp_path)

    assert set(_ids(find.run(tmp_path, {}, "cache", "php.symbol", 50, path))) == {
        "php.method::Foo::cache",
        "php.type::Cache",
        "php.type::CacheBackend",
        "php.type::MyCache",
        "php.type::Cache::Zed",
    }
    assert _ids(find.run(tmp_path, {}, "cache", "php.method", 50, path)) == [
        "php.method::Foo::cache"
    ]


def test_an_unknown_type_is_an_empty_listing_with_a_warning_and_exit_0(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "cache", "nope.type", 50, _map(tmp_path))

    assert report.matches.total == 0
    assert "nope.type" in report.warnings[0]
    assert report.exit_code is ExitCode.OK


def test_a_known_type_with_no_match_gives_no_warning(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "zzz", "php.type", 50, _map(tmp_path))

    assert report.warnings == ()


def test_text_matching_nothing_is_empty_with_total_0_and_exit_0(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "zzz", None, 50, _map(tmp_path))

    assert (report.matches.items, report.matches.total, report.exit_code) == ((), 0, ExitCode.OK)
    assert json.loads(find.render_json(report))["total"] == 0
    assert "no matches" in find.render_text(report)


def test_limit_cuts_the_list_and_says_so(tmp_path: Path) -> None:
    path = _map(tmp_path)
    report = find.run(tmp_path, {}, "cache", None, 2, path)

    assert (report.matches.shown, report.matches.total, report.matches.truncated) == (2, 6, True)
    assert "showing 2 of 6" in find.render_text(report)
    assert find.run(tmp_path, {}, "cache", None, 0, path).matches.shown == 6


def test_a_missing_map_is_a_problem_with_its_exit_code(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "x", None, 50, None)

    assert report.exit_code is ExitCode.MAP_NOT_FOUND


def test_the_format_choices_are_exactly_the_find_renderers() -> None:
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["find"]._actions if a.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(find.RENDERERS)
    assert fmt.default == next(iter(find.RENDERERS))


def test_main_prints_the_json_listing_and_two_runs_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _map(tmp_path)
    monkeypatch.chdir(tmp_path)
    argv = ["find", "cache", "--type", "php.type", "--limit", "2", "--map", str(path)]

    assert main([*argv, "--format", "json"]) == 0
    first = capsys.readouterr().out
    assert main([*argv, "--format", "json"]) == 0
    assert capsys.readouterr().out == first
    document = json.loads(first)
    assert [row["id"] for row in document["items"]] == ["php.type::Cache", "php.type::CacheBackend"]
    assert document["truncated"] is True
