"""``periplus depth``: per direction, how far the walk by cause goes and how much it reaches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import build_parser, main
from periplus.navigate import depth

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"
CAUSES = {"from": ["calls"], "to": ["implements_hook"], "none": ["contains"], "touch": ["links_to"]}

# n0 -calls-> n1 -> ... -> n6, six hops; p -calls-> n0, one hop the other way.
CHAIN = [("calls", f"x::n{i}", f"x::n{i + 1}", i + 1) for i in range(6)]
CHAIN += [("calls", "x::p", "x::n0", 9)]


def _write(root: Path, edges: list[tuple[Any, ...]] = CHAIN, causes: Any = CAUSES) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], causes)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _lines(
    root: Path, *ids: str, edges: Any = CHAIN, causes: Any = CAUSES, **opt: Any
) -> list[str]:
    report = depth.run(root, {}, list(ids), _write(root, edges, causes), **opt)
    return depth.render_text(report).splitlines()


def test_each_direction_prints_hops_things_and_the_shares_that_add_something(
    tmp_path: Path,
) -> None:
    lines = _lines(tmp_path, "x::n0")

    assert lines[0] == "periplus depth x::n0"
    assert lines[1] == (
        "sets off:     6 hops, 6 things; 33% within 2, 50% within 3, 83% within 5; 0 hubs stopped"
    )


def test_a_share_the_walk_ends_before_is_left_out(tmp_path: Path) -> None:
    assert _lines(tmp_path, "x::n0")[2] == "set off by:   1 hop, 1 thing; 0 hubs stopped"


def test_the_hubs_stopped_at_are_counted_and_up_to_three_named(tmp_path: Path) -> None:
    edges = [("calls", "x::a", f"x::h{n}", 1) for n in range(4)]
    edges += [("calls", f"x::h{n}", f"x::h{n}::{m}", 2) for n in range(4) for m in range(3)]
    line = _lines(tmp_path, "x::a", edges=edges, hub=2)[1]

    assert line == "sets off:     1 hop, 4 things; 4 hubs stopped (x::h0, x::h1, x::h2, +1)"


def test_through_walks_a_hub(tmp_path: Path) -> None:
    edges = [("calls", "x::a", "x::h", 1)] + [("calls", "x::h", f"x::k{m}", 2) for m in range(3)]
    line = _lines(tmp_path, "x::a", edges=edges, hub=2, through=["x::h"])[1]

    assert line.startswith("sets off:     2 hops, 4 things;")


def test_the_touching_line_counts_what_points_at_the_start_by_kind(tmp_path: Path) -> None:
    edges = [*CHAIN, ("links_to", "x::l1", "x::n0", 1), ("links_to", "x::l2", "x::n0", 2)]
    lines = _lines(tmp_path, "x::n0", edges=edges)

    assert lines[3] == (
        "touching:   2 things point at it (links_to 2); see periplus affected x::n0 --touch"
        f" --map {tmp_path / 'map.json'}"
    )


def test_no_touching_line_when_nothing_touches(tmp_path: Path) -> None:
    assert not any(line.startswith("touching:") for line in _lines(tmp_path, "x::n0"))


def test_kinds_walked_undeclared_are_named(tmp_path: Path) -> None:
    edges = [*CHAIN, ("uses_x", "x::n0", "x::u", 1)]

    assert _lines(tmp_path, "x::n0", edges=edges)[-1] == (
        "undeclared kinds, walked by raw direction: uses_x"
    )


def test_a_map_with_no_cause_lists_says_so(tmp_path: Path) -> None:
    assert _lines(tmp_path, "x::n0", causes=None)[-1] == (
        "the map declares no cause directions; every kind was walked by raw direction"
    )


def test_several_starts_are_one_set(tmp_path: Path) -> None:
    lines = _lines(tmp_path, "x::n0", "x::n3")

    assert lines[0] == "periplus depth x::n0 x::n3"
    assert lines[1].startswith("sets off:     3 hops, 5 things;")


def test_the_json_counts_each_hop_and_matches_the_schema(tmp_path: Path) -> None:
    report = depth.run(tmp_path, {}, ["x::n0"], _write(tmp_path))
    document = json.loads(depth.render_json(report))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/depth"}]})

    assert list(validator.iter_errors(document)) == []
    assert document["sets_off"]["per_hop"] == [1, 1, 1, 1, 1, 1]
    assert document["set_off_by"]["things"] == 1


def test_the_command_exits_with_the_report_code(tmp_path: Path) -> None:
    path = _write(tmp_path)

    assert main(["depth", "x::n0", "--map", str(path)]) == 0
    assert main(["depth", "nope", "--map", str(path)]) == 31


def test_the_format_choices_are_exactly_the_depth_renderers() -> None:
    subcommands = next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    )
    fmt = next(a for a in subcommands.choices["depth"]._actions if a.dest == "format")

    assert tuple(fmt.choices or ()) == tuple(depth.RENDERERS)
