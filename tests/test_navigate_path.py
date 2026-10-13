"""``periplus path``: every shortest chain, the exact count, the limit, no path and the CLI tie."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import path

PROV = [{"pack": "p", "rule": "r", "sets": []}]


def _node(id: str) -> dict[str, Any]:
    return {"id": id, "type": "t.x", "state": "mapped", "locations": [], "provenance": PROV}


def _edge(kind: str, source: str, target: str) -> dict[str, Any]:
    return {"kind": kind, "from": source, "to": target, "locations": [], "provenance": PROV}


# a->b->d, a->c->d, a->b->d via two kinds (calls, uses), a->d is absent; d->e; z is isolated.
EDGES = [
    ("calls", "x::a", "x::b"),
    ("calls", "x::a", "x::c"),
    ("calls", "x::b", "x::d"),
    ("uses", "x::b", "x::d"),
    ("calls", "x::c", "x::d"),
    ("calls", "x::d", "x::e"),
    ("calls", "x::d", "x::a"),
]


def _map(root: Path) -> Path:
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "p", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": [_node(f"x::{c}") for c in "abcdez"],
        "edges": [_edge(*e) for e in sorted(EDGES)],
    }
    target = root / "map.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_every_shortest_chain_is_listed_in_order_and_the_total_is_exact(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::d", [], 10, _map(tmp_path))

    assert report.chains.total == 3
    assert report.chains.items == (
        [("x::a", "calls", "x::b"), ("x::b", "calls", "x::d")],
        [("x::a", "calls", "x::b"), ("x::b", "uses", "x::d")],
        [("x::a", "calls", "x::c"), ("x::c", "calls", "x::d")],
    )


def test_the_limit_cuts_the_chains_but_the_total_counts_them_all(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::d", [], 2, _map(tmp_path))

    assert (report.chains.shown, report.chains.total) == (2, 3)
    assert "showing 2 of 3" in path.render_text(report)


def test_a_limit_of_zero_lists_all(tmp_path: Path) -> None:
    assert path.run(tmp_path, {}, "x::a", "x::d", [], 0, _map(tmp_path)).chains.shown == 3


def test_kind_restricts_the_steps(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::d", ["uses", "calls"], 10, _map(tmp_path))
    only_uses = path.run(tmp_path, {}, "x::a", "x::d", ["uses"], 10, _map(tmp_path))

    assert report.chains.total == 3
    assert only_uses.chains.total == 0


def test_longer_chains_are_not_listed_beside_shorter_ones(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::e", [], 10, _map(tmp_path))

    assert report.chains.total == 3
    assert all(len(chain) == 3 for chain in report.chains.items)


def test_the_direction_is_respected(tmp_path: Path) -> None:
    assert path.run(tmp_path, {}, "x::e", "x::a", [], 10, _map(tmp_path)).chains.total == 0


def test_no_chain_is_an_empty_listing_a_line_saying_so_and_exit_zero(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::z", [], 10, _map(tmp_path))

    assert report.exit_code == ExitCode.OK
    assert report.chains.total == 0 and report.chains.items == ()
    assert "no path" in path.render_text(report)


def test_the_same_item_is_one_chain_of_no_steps(tmp_path: Path) -> None:
    report = path.run(tmp_path, {}, "x::a", "x::a", [], 10, _map(tmp_path))

    assert report.chains.items == ([],)
    assert report.chains.total == 1


def test_a_cycle_does_not_hang_the_search(tmp_path: Path) -> None:
    assert path.run(tmp_path, {}, "x::d", "x::c", [], 10, _map(tmp_path)).chains.total == 1


def test_an_unknown_id_on_either_end_is_node_not_found(tmp_path: Path) -> None:
    where = _map(tmp_path)

    assert (
        path.run(tmp_path, {}, "x::q", "x::a", [], 10, where).exit_code == ExitCode.NODE_NOT_FOUND
    )
    assert (
        path.run(tmp_path, {}, "x::a", "x::q", [], 10, where).exit_code == ExitCode.NODE_NOT_FOUND
    )


def test_the_output_is_the_same_every_run(tmp_path: Path) -> None:
    where = _map(tmp_path)
    first = path.render_json(path.run(tmp_path, {}, "x::a", "x::d", [], 10, where))

    assert first == path.render_json(path.run(tmp_path, {}, "x::a", "x::d", [], 10, where))
    assert json.loads(first)["chains"]["items"][0][0] == {
        "from": "x::a",
        "kind": "calls",
        "to": "x::b",
    }


def test_the_format_choices_are_exactly_the_path_renderers() -> None:
    subcommands = next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["path"]._actions if a.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(path.RENDERERS)
    assert fmt.default == next(iter(path.RENDERERS))


def test_the_command_exits_with_the_report_code(tmp_path: Path) -> None:
    where = _map(tmp_path)

    assert main(["path", "x::a", "x::d", "--map", str(where)]) == 0
    assert main(["path", "x::a", "x::z", "--map", str(where)]) == 0
    assert main(["path", "x::a", "nope", "--map", str(where)]) == int(ExitCode.NODE_NOT_FOUND)
