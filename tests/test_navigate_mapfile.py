"""Loading a written map, indexing it, and the cut-list envelope."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate.listing import cut, footer, payload
from periplus.navigate.mapfile import MapNotFound, NodeNotFound, NotAMap, load_map

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


def write_map(root: Path, document: Any = DOCUMENT) -> Path:
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    path = root / ".periplus" / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_the_default_map_is_read_from_the_project_root_found_above_the_start(
    tmp_path: Path,
) -> None:
    write_map(tmp_path)
    (tmp_path / "deep" / "er").mkdir(parents=True)

    index = load_map(tmp_path / "deep" / "er", {}, None)

    assert sorted(index.nodes) == sorted(n["id"] for n in DOCUMENT["nodes"])


def test_a_named_map_is_read_instead_of_the_default(tmp_path: Path) -> None:
    write_map(tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({**DOCUMENT, "nodes": [_node("php.type::Only", "php.type")]}))

    assert list(load_map(tmp_path, {}, other).nodes) == ["php.type::Only"]


def test_no_project_above_the_start_is_map_not_found(tmp_path: Path) -> None:
    with pytest.raises(MapNotFound) as raised:
        load_map(tmp_path, {}, None)

    assert raised.value.problem().code is ExitCode.MAP_NOT_FOUND


def test_a_project_with_no_map_file_names_the_path(tmp_path: Path) -> None:
    (tmp_path / ".periplus").mkdir()

    with pytest.raises(MapNotFound) as raised:
        load_map(tmp_path, {}, None)

    assert str(tmp_path / ".periplus" / "map.json") in str(raised.value)


def test_a_named_map_that_does_not_exist_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(MapNotFound) as raised:
        load_map(tmp_path, {}, tmp_path / "absent.json")

    assert str(tmp_path / "absent.json") in str(raised.value)


def test_a_file_that_is_not_json_is_not_a_map_and_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text("{not json")

    with pytest.raises(NotAMap) as raised:
        load_map(tmp_path, {}, path)

    assert str(path) in str(raised.value)
    assert raised.value.problem().code is ExitCode.NOT_A_MAP


def test_json_that_fails_the_map_schema_is_not_a_map_and_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"nodes": []}))

    with pytest.raises(NotAMap) as raised:
        load_map(tmp_path, {}, path)

    assert str(path) in str(raised.value)


def test_the_three_new_exit_codes_are_distinct_from_every_existing_one() -> None:
    new = {ExitCode.MAP_NOT_FOUND, ExitCode.NOT_A_MAP, ExitCode.NODE_NOT_FOUND}

    assert len(new) == 3
    assert {int(code) for code in new} == {29, 30, 31}
    assert len({int(code) for code in ExitCode}) == len(list(ExitCode))


def test_edges_come_back_in_map_order_by_either_end(tmp_path: Path) -> None:
    index = load_map(tmp_path, {}, write_map(tmp_path))

    assert [e["to"] for e in index.outgoing("php.type::Foo")] == [
        "php.method::Foo::bar",
        "php.method::Foo::baz",
    ]
    assert [e["kind"] for e in index.incoming("php.method::Foo::baz")] == ["calls", "defines"]
    assert index.outgoing("php.type::Foo::none") == []


def test_parent_and_subtypes_come_from_the_type_hierarchy(tmp_path: Path) -> None:
    index = load_map(tmp_path, {}, write_map(tmp_path))

    assert index.parent("php.method") == "php.symbol"
    assert index.parent("php.symbol") is None
    assert index.subtypes("php.symbol") == ["php.method", "php.type"]
    assert index.subtypes("php.method") == []


def test_an_unknown_id_names_itself_lists_close_ids_and_suggests_find(tmp_path: Path) -> None:
    index = load_map(tmp_path, {}, write_map(tmp_path))

    with pytest.raises(NodeNotFound) as raised:
        index.node("php.method::Foo::bar2")

    message = str(raised.value)
    assert "php.method::Foo::bar2" in message
    assert "php.method::Foo::bar" in message
    assert "periplus find" in message
    assert raised.value.problem().code is ExitCode.NODE_NOT_FOUND


def test_an_unknown_id_with_nothing_close_lists_no_ids(tmp_path: Path) -> None:
    index = load_map(tmp_path, {}, write_map(tmp_path))

    with pytest.raises(NodeNotFound) as raised:
        index.node("zzzzzzzz")

    assert "close ids" not in str(raised.value)
    assert "periplus find" in str(raised.value)


def test_a_known_id_returns_its_node(tmp_path: Path) -> None:
    index = load_map(tmp_path, {}, write_map(tmp_path))

    assert index.node("php.type::Foo")["type"] == "php.type"


def test_a_cut_below_the_item_count_reports_total_shown_and_truncated() -> None:
    listing = cut(["a", "b", "c"], 2)

    assert payload(listing) == {"items": ["a", "b"], "total": 3, "shown": 2, "truncated": True}
    assert footer(listing) == "showing 2 of 3"


def test_a_limit_of_zero_keeps_every_item_and_prints_no_footer() -> None:
    listing = cut(["a", "b", "c"], 0)

    assert listing.items == ("a", "b", "c")
    assert (listing.total, listing.shown, listing.truncated) == (3, 3, False)
    assert footer(listing) is None


def test_a_limit_at_or_above_the_count_is_not_a_cut() -> None:
    listing = cut(["a", "b"], 2)

    assert listing.truncated is False
    assert footer(listing) is None


def test_a_negative_limit_is_refused_by_cut() -> None:
    with pytest.raises(ValueError, match="limit"):
        cut(["a", "b", "c"], -1)


@pytest.mark.parametrize(
    "argv",
    [
        ["find", "Foo"],
        ["show", "php.type::Foo"],
        ["neighbors", "php.type::Foo"],
        ["affected", "php.method::Foo::bar"],
        ["path", "php.type::Foo", "php.method::Foo::baz"],
    ],
)
def test_a_negative_limit_is_refused_as_a_bad_depth_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    path = write_map(tmp_path)
    with pytest.raises(SystemExit) as bad_depth:
        main(["neighbors", "php.type::Foo", "--depth", "0", "--map", str(path)])
    capsys.readouterr()

    with pytest.raises(SystemExit) as bad_limit:
        main([*argv, "--limit", "-1", "--map", str(path)])

    captured = capsys.readouterr()
    assert bad_limit.value.code == bad_depth.value.code == 2
    assert "--limit" in captured.err
    assert captured.out == ""
