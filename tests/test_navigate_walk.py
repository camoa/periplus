"""``periplus neighbors`` and ``affected``: depth, kinds, cycles, escaped ids, the CLI tie."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from periplus.cli import build_parser, main
from periplus.errors import ExitCode
from periplus.navigate import walk


def _node(id: str) -> dict[str, Any]:
    return {
        "id": id,
        "type": "t.x",
        "state": "mapped",
        "locations": [{"file": "a.php", "line": 1}],
        "provenance": [{"pack": "p", "rule": "r", "sets": []}],
    }


def _edge(kind: str, source: str, target: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "from": source,
        "to": target,
        "locations": [],
        "provenance": [{"pack": "p", "rule": "r", "sets": []}],
    }


# a -calls-> b -calls-> c -calls-> a (a cycle); a -uses-> c; c -calls-> d; weird\n -calls-> a
NAMES = ["x::a", "x::b", "x::c", "x::d", "x::e\n"]
EDGES = [
    ("calls", "x::a", "x::b"),
    ("calls", "x::b", "x::c"),
    ("calls", "x::c", "x::a"),
    ("uses", "x::a", "x::c"),
    ("calls", "x::c", "x::d"),
    ("calls", "x::e\n", "x::a"),
]


def _map(root: Path) -> Path:
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "p", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": [_node(n) for n in sorted(NAMES)],
        "edges": [_edge(*e) for e in sorted(EDGES, key=lambda e: (e[0], e[1], e[2]))],
    }
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _ids(report: walk.WalkReport) -> list[tuple[str, int, str, str]]:
    return [(r["id"], r["depth"], r["kind"], r["via"]) for r in report.rows.items]


def test_neighbors_at_depth_one_lists_direct_targets_with_the_edge_that_reached_them(
    tmp_path: Path,
) -> None:
    report = walk.run(tmp_path, {}, "x::a", "out", 1, [], 50, _map(tmp_path))

    assert _ids(report) == [("x::b", 1, "calls", "x::a"), ("x::c", 1, "uses", "x::a")]


def test_depth_goes_further_and_each_item_appears_once_at_its_nearest_depth(
    tmp_path: Path,
) -> None:
    report = walk.run(tmp_path, {}, "x::a", "out", 5, [], 50, _map(tmp_path))

    assert _ids(report) == [
        ("x::b", 1, "calls", "x::a"),
        ("x::c", 1, "uses", "x::a"),
        ("x::d", 2, "calls", "x::c"),
    ]


def test_a_cycle_back_to_the_start_never_lists_the_start(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::b", "out", 9, [], 50, _map(tmp_path))

    assert [r["id"] for r in report.rows.items] == ["x::c", "x::a", "x::d"]


def test_kind_keeps_only_the_named_edge_kinds(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::a", "out", 5, ["uses"], 50, _map(tmp_path))

    assert _ids(report) == [("x::c", 1, "uses", "x::a")]


def test_a_kind_the_map_lacks_is_a_warning_not_an_error(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::a", "out", 1, ["nope"], 50, _map(tmp_path))

    assert report.exit_code == ExitCode.OK
    assert report.rows.total == 0
    assert "nope" in report.warnings[0]


def test_affected_follows_edges_backwards(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::a", "in", 2, [], 50, _map(tmp_path))

    assert _ids(report) == [
        ("x::c", 1, "calls", "x::a"),
        ("x::e\n", 1, "calls", "x::a"),
        ("x::b", 2, "calls", "x::c"),
    ]


def test_the_limit_cuts_the_rows_and_the_total_stays_exact(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::a", "out", 5, [], 1, _map(tmp_path))

    assert (report.rows.shown, report.rows.total) == (1, 3)
    assert "showing 1 of 3" in walk.render_text(report)


def test_an_id_copied_from_text_output_with_doubled_backslashes_resolves(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::e\\n", "out", 1, [], 50, _map(tmp_path))

    assert report.exit_code == ExitCode.OK
    assert report.start == "x::e\n"
    assert "\\n" in walk.render_text(report) and "\n  " in walk.render_text(report)


def test_an_unknown_id_is_node_not_found(tmp_path: Path) -> None:
    report = walk.run(tmp_path, {}, "x::gone", "out", 1, [], 50, _map(tmp_path))

    assert report.exit_code == ExitCode.NODE_NOT_FOUND
    assert "x::gone" in report.problems[0].message


def test_the_json_carries_the_rows_in_the_listing_envelope(tmp_path: Path) -> None:
    document = json.loads(
        walk.render_json(walk.run(tmp_path, {}, "x::a", "out", 1, [], 50, _map(tmp_path)))
    )

    assert document["rows"]["total"] == 2
    assert document["rows"]["items"][0]["via"] == "x::a"


def test_the_format_choices_are_exactly_the_walk_renderers() -> None:
    subcommands = next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    )
    for name in ("neighbors", "affected"):
        fmt = next(a for a in subcommands.choices[name]._actions if a.dest == "format")
        assert tuple(fmt.choices or ()) == tuple(walk.RENDERERS)
        assert fmt.default == next(iter(walk.RENDERERS))


def test_the_commands_exit_with_the_report_code(tmp_path: Path) -> None:
    path = _map(tmp_path)

    assert main(["neighbors", "x::a", "--map", str(path)]) == 0
    assert main(["affected", "x::a", "--depth", "2", "--kind", "calls", "--map", str(path)]) == 0
    assert main(["neighbors", "nope", "--map", str(path)]) == int(ExitCode.NODE_NOT_FOUND)
