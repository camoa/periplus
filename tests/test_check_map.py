"""The outline-only map load and ``periplus check-map``, which runs the full map schema check."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_navigate_mapfile import DOCUMENT, write_map

from periplus.checkmap import run
from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import find, show, types, walk
from periplus.navigate import path as path_command
from periplus.navigate.mapfile import NotAMap, load_map


def _deep_error() -> dict[str, Any]:
    """The fixture map with a node missing its type: the outline holds, the schema fails."""
    document = copy.deepcopy(DOCUMENT)
    del document["nodes"][0]["type"]
    return document


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"nodes": [], "edges": []},
        {"periplus_map_version": "0", "nodes": [], "edges": []},
        {"periplus_map_version": -1, "nodes": [], "edges": []},
        {"periplus_map_version": True, "nodes": [], "edges": []},
        {"periplus_map_version": 0, "nodes": {}, "edges": []},
        {"periplus_map_version": 0, "nodes": [], "edges": None},
        {"periplus_map_version": 0, "nodes": []},
    ],
)
def test_load_map_refuses_json_without_the_map_outline_and_names_the_path(
    tmp_path: Path, document: Any
) -> None:
    path = write_map(tmp_path, document)

    with pytest.raises(NotAMap) as raised:
        load_map(tmp_path, {}, None)

    assert str(path) in str(raised.value)


def test_load_map_reads_a_map_with_the_outline_and_a_deep_schema_error(tmp_path: Path) -> None:
    write_map(tmp_path, _deep_error())

    index = load_map(tmp_path, {}, None)

    assert len(index.nodes) == len(DOCUMENT["nodes"])


def test_check_map_passes_a_valid_map(tmp_path: Path) -> None:
    path = write_map(tmp_path)

    report = run(tmp_path, {}, None)

    assert report.exit_code is ExitCode.OK
    assert report.map_path == str(path)
    assert report.problems == ()


def test_check_map_names_the_path_and_the_first_error_in_map_order(tmp_path: Path) -> None:
    document = _deep_error()
    del document["edges"][0]["kind"]
    path = write_map(tmp_path, document)

    report = run(tmp_path, {}, None)

    assert report.exit_code is ExitCode.NOT_A_MAP
    (problem,) = report.problems
    assert str(path) in problem.message
    # Sorted by the path into the document, edges before nodes, as periplus map sorts them.
    assert "'kind' is a required property" in problem.message


def test_check_map_reports_no_map_and_a_file_that_is_not_json(tmp_path: Path) -> None:
    assert run(tmp_path, {}, None).exit_code is ExitCode.MAP_NOT_FOUND
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")

    report = run(tmp_path, {}, bad)

    assert report.exit_code is ExitCode.NOT_A_MAP
    assert report.map_path == str(bad)


def test_main_check_map_exits_with_each_code_in_text_and_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["check-map"]) == int(ExitCode.MAP_NOT_FOUND)
    capsys.readouterr()

    path = write_map(tmp_path)
    assert main(["check-map"]) == int(ExitCode.OK)
    assert capsys.readouterr().out == f"{path} matches the map schema\n"

    other = tmp_path / "other.json"
    other.write_text(json.dumps(_deep_error()))
    assert main(["check-map", "--map", str(other), "--format", "json"]) == int(ExitCode.NOT_A_MAP)
    payload = json.loads(capsys.readouterr().out)
    assert payload["map"] == str(other)
    assert payload["valid"] is False
    assert payload["problems"][0]["code"] == int(ExitCode.NOT_A_MAP)
    assert "'type' is a required property" in payload["problems"][0]["message"]


_BAR, _BAZ, _FOO = "php.method::Foo::bar", "php.method::Foo::baz", "php.type::Foo"


def _damaged(name: str) -> dict[str, Any]:
    """The fixture map with one deep defect; the outline holds, so ``load_map`` accepts it."""
    document = copy.deepcopy(DOCUMENT)
    if name == "node without type":
        del document["nodes"][0]["type"]
    elif name == "edge without kind":
        del document["edges"][0]["kind"]
    elif name == "node type is an int":
        document["nodes"][0]["type"] = 5
    elif name == "node ids mix int and str":
        document["nodes"][0]["id"] = 5
    else:
        document["edges"][0]["to"] = "nowhere"
    return document


# One case per command, and every kind of damage at least once. Each command wraps its own field
# reads, so each needs a case; a second case on the same command and wrapper reaches the same
# branch. Each case names ids that make its command read the damaged field.
_DAMAGED_CASES = [
    ("node without type", ["types"]),
    ("node type is an int", ["find", "Foo"]),
    ("edge without kind", ["show", _BAR]),
    ("edge end names no node", ["neighbors", _BAR]),
    ("node ids mix int and str", ["affected", "nope"]),
    ("edge without kind", ["path", _BAR, _BAZ]),
]


# The error a report names for each damage: the exception kind, and the field or value it names.
_DAMAGE_NAMED = {
    "node without type": ("KeyError", "type"),
    "edge without kind": ("KeyError", "kind"),
    "node type is an int": ("TypeError", "int"),
    "node ids mix int and str": ("TypeError", "int"),
    "edge end names no node": ("KeyError", "nowhere"),
}


@pytest.mark.parametrize(("name", "argv"), _DAMAGED_CASES)
def test_a_navigation_command_refuses_a_damaged_map_with_not_a_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, argv: list[str]
) -> None:
    path = tmp_path / "damaged.json"
    path.write_text(json.dumps(_damaged(name)), encoding="utf-8")

    status = main([*argv, "--map", str(path)])

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert status == int(ExitCode.NOT_A_MAP)
    assert str(path) in output
    assert "check-map" in output
    assert "Traceback" not in output


def _run_library(argv: list[str], start: Path, map_path: Path) -> Any:
    """The library ``run`` behind the navigation command ``argv``, with its default options."""
    command, *ids = argv
    if command == "types":
        return types.run(start, {}, map_path)
    if command == "find":
        return find.run(start, {}, ids[0], None, 50, map_path)
    if command == "show":
        return show.run(start, {}, ids[0], 50, map_path)
    if command in ("neighbors", "affected"):
        direction = "out" if command == "neighbors" else "in"
        return walk.run(start, {}, ids[0], direction, 1, [], 50, map_path)
    return path_command.run(start, {}, ids[0], ids[1], [], 10, map_path)


@pytest.mark.parametrize(("name", "argv"), _DAMAGED_CASES)
def test_a_navigation_library_run_returns_not_a_map_for_a_damaged_map(
    tmp_path: Path, name: str, argv: list[str]
) -> None:
    map_path = tmp_path / "damaged.json"
    map_path.write_text(json.dumps(_damaged(name)), encoding="utf-8")

    report = _run_library(argv, tmp_path, map_path)

    assert report.exit_code == ExitCode.NOT_A_MAP
    (problem,) = report.problems
    kind, field = _DAMAGE_NAMED[name]
    assert str(map_path) in problem.message
    assert f"{kind}:" in problem.message and field in problem.message, problem.message
    assert "check-map" in problem.message
