"""The walk by cause behind ``neighbors`` (what the starts set off) and ``affected`` (what sets
them off), and the tree those commands print."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus import cli
from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import walk
from periplus.navigate.mapfile import MapIndex

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

CAUSES = {
    "from": ["calls"],
    "to": ["implements_hook"],
    "none": ["contains"],
    "touch": ["links_to"],
}

# a -calls-> b -calls-> d; c -implements_hook-> a; x -calls-> a; m -contains-> a;
# l -links_to-> a; a -uses_x-> u (undeclared).
EDGES = [
    ("calls", "x::a", "x::b", 3),
    ("calls", "x::b", "x::d", 4),
    ("implements_hook", "x::c", "x::a", 5),
    ("calls", "x::x", "x::a", 6),
    ("contains", "x::m", "x::a", 7),
    ("links_to", "x::l", "x::a", 8),
    ("uses_x", "x::a", "x::u", 9),
]


def _index(edges: list[tuple[Any, ...]] = EDGES, causes: Any = CAUSES) -> MapIndex:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    return MapIndex(
        _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], causes)
    )


def _write(root: Path, edges: list[tuple[Any, ...]] = EDGES, causes: Any = CAUSES) -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], causes)
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _reached(index: MapIndex, start: str, toward: str, **options: Any) -> list[Any]:
    found = walk.cause_walk(index, [start], toward, **options)
    return [(r.id, r.hop, r.kind, r.backward) for r in found.rows]


# --- the walk -------------------------------------------------------------------------------


def test_off_follows_a_from_kind_forward() -> None:
    assert ("x::b", 1, "calls", False) in _reached(_index(), "x::a", "off")


def test_off_follows_a_to_kind_backward() -> None:
    assert ("x::c", 1, "implements_hook", True) in _reached(_index(), "x::a", "off")


def test_by_follows_a_from_kind_backward() -> None:
    assert ("x::x", 1, "calls", True) in _reached(_index(), "x::a", "by")


def test_by_follows_a_to_kind_forward() -> None:
    assert _reached(_index(), "x::c", "by") == [("x::a", 1, "implements_hook", False)] + [
        ("x::x", 2, "calls", True)
    ]


def test_a_none_kind_is_never_walked_either_way() -> None:
    index = _index()

    assert "x::m" not in [r[0] for r in _reached(index, "x::a", "by")]
    assert _reached(index, "x::m", "off") == []


def test_a_touch_kind_is_not_walked() -> None:
    index = _index()

    assert "x::l" not in [r[0] for r in _reached(index, "x::a", "by")]
    assert _reached(index, "x::l", "off") == []


def test_an_undeclared_kind_is_walked_by_raw_direction_and_named() -> None:
    index = _index()

    assert ("x::u", 1, "uses_x", False) in _reached(index, "x::a", "off")
    assert _reached(index, "x::u", "by")[0] == ("x::a", 1, "uses_x", True)
    assert walk.cause_walk(index, ["x::a"], "off").undeclared == ("uses_x",)


def test_off_goes_on_hop_by_hop_and_each_node_comes_once_at_its_nearest_hop() -> None:
    edges = [*EDGES, ("calls", "x::a", "x::d", 2)]

    assert [r[:2] for r in _reached(_index(edges), "x::a", "off")] == [
        ("x::b", 1),
        ("x::c", 1),
        ("x::d", 1),
        ("x::u", 1),
    ]


def test_a_tie_goes_to_the_parent_with_the_smaller_id() -> None:
    edges = [("calls", "x::s", "x::p2", 1), ("calls", "x::s", "x::p1", 1)]
    edges += [("calls", "x::p2", "x::z", 2), ("calls", "x::p1", "x::z", 3)]
    found = walk.cause_walk(_index(edges), ["x::s"], "off")

    assert next(r.via for r in found.rows if r.id == "x::z") == "x::p1"


HUB_EDGES = [
    ("calls", "x::a", "x::h", 1),
    ("calls", "x::h", "x::h1", 2),
    ("calls", "x::h", "x::h2", 3),
    ("calls", "x::h", "x::h3", 4),
]


def test_a_node_whose_fan_is_over_the_hub_limit_is_listed_but_not_walked_from() -> None:
    found = walk.cause_walk(_index(HUB_EDGES), ["x::a"], "off", hub=2)

    assert [(r.id, r.hub) for r in found.rows] == [("x::h", 3)]


def test_hub_zero_walks_through_every_hub() -> None:
    found = walk.cause_walk(_index(HUB_EDGES), ["x::a"], "off", hub=0)

    assert [r.id for r in found.rows] == ["x::h", "x::h1", "x::h2", "x::h3"]
    assert all(r.hub is None for r in found.rows)


def test_through_walks_one_named_hub() -> None:
    found = walk.cause_walk(_index(HUB_EDGES), ["x::a"], "off", hub=2, through=["x::h"])

    assert len(found.rows) == 4


def test_a_start_is_walked_from_whatever_its_fan() -> None:
    found = walk.cause_walk(_index(HUB_EDGES), ["x::h"], "off", hub=2)

    assert [r.id for r in found.rows] == ["x::h1", "x::h2", "x::h3"]


def test_the_fan_counts_only_the_edges_this_walk_would_follow() -> None:
    edges = [*HUB_EDGES[1:], ("calls", "x::a", "x::g", 1), ("calls", "x::g", "x::h", 1)]
    edges += [("calls", f"x::g{n}", "x::g", 1) for n in range(5)]
    found = walk.cause_walk(_index(edges), ["x::a"], "off", hub=2)

    assert [(r.id, r.hub) for r in found.rows if r.id in ("x::g", "x::h")] == [
        ("x::g", None),
        ("x::h", 3),
    ]


def test_several_starts_walk_as_one_set() -> None:
    found = walk.cause_walk(_index(), ["x::b", "x::c"], "by")

    assert [r.id for r in found.rows] == ["x::a", "x::x"]


# --- the commands ---------------------------------------------------------------------------


def _text(root: Path, *argv: str, edges: Any = EDGES, causes: Any = CAUSES) -> str:
    path = _write(root, edges, causes)
    report = walk.run_cause(
        root,
        {},
        list(argv[:1]),
        "off" if "--by" not in argv else "by",
        int(argv[argv.index("--depth") + 1]) if "--depth" in argv else 1,
        [],
        int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None,
        path,
        touch="--touch" in argv,
        full=True,
    )
    return walk.render_text(report)


CHAIN = [("calls", f"x::n{i}", f"x::n{i + 1}", i + 1) for i in range(4)]


def test_a_row_prints_id_type_state_kind_and_file_line_indented_by_hop(tmp_path: Path) -> None:
    lines = _text(tmp_path, "x::n0", "--depth", "2", edges=CHAIN).splitlines()

    assert "  x::n1  t.x  mapped  calls  src/a.php:1" in lines
    assert "    x::n2  t.x  mapped  calls  src/a.php:2" in lines


def test_a_row_reached_backward_says_rev(tmp_path: Path) -> None:
    assert "  x::c  t.x  mapped  implements_hook (rev)  src/a.php:5" in _text(
        tmp_path, "x::a"
    ).splitlines()


def test_a_child_prints_under_the_node_it_was_reached_from(tmp_path: Path) -> None:
    edges = [("calls", "x::s", "x::p1", 1), ("calls", "x::s", "x::p2", 2)]
    edges += [("calls", "x::p1", "x::q1", 3), ("calls", "x::p2", "x::q2", 4)]
    lines = _text(tmp_path, "x::s", "--depth", "2", edges=edges).splitlines()
    ids = [line.split()[0] for line in lines if line.startswith("  ")]

    assert ids == ["x::p1", "x::q1", "x::p2", "x::q2"]


def test_a_row_prints_no_source_line(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.php").write_text("<?php\nfoo();\nbar();\n", encoding="utf-8")

    assert "|" not in _text(tmp_path, "x::n0", edges=CHAIN)


def test_the_first_line_says_what_the_depth_left_out_and_the_command_for_all(
    tmp_path: Path,
) -> None:
    first = _text(tmp_path, "x::n0", "--depth", "2", edges=CHAIN).splitlines()[0]

    assert first == (
        f"showing 2 of 4 (hops 1-2 of 4); all: periplus neighbors x::n0 --depth all --limit 0"
        f" --full --map {tmp_path / 'map.json'}"
    )


def test_a_whole_walk_has_no_showing_line(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", "--depth", "4", edges=CHAIN)

    assert text.splitlines()[0] == "periplus neighbors x::n0"
    assert "showing" not in text


def test_each_hop_not_shown_prints_one_count_line_by_type(tmp_path: Path) -> None:
    lines = _text(tmp_path, "x::n0", "--depth", "2", edges=CHAIN).splitlines()

    assert "hop 3: 1 thing (t.x 1)" in lines
    assert "hop 4: 1 thing (t.x 1)" in lines


def test_over_the_budget_the_farthest_hops_become_count_lines_and_hop_one_stays(
    tmp_path: Path,
) -> None:
    lines = _text(tmp_path, "x::n0", "--depth", "4", "--limit", "10", edges=CHAIN).splitlines()

    assert lines[0].startswith("showing 1 of 4 (hops 1-1 of 4); all: ")
    assert "  x::n1  t.x  mapped  calls  src/a.php:1" in lines
    assert [line for line in lines if line.startswith("hop ")] == [
        f"hop {n}: 1 thing (t.x 1)" for n in (2, 3, 4)
    ]


def test_limit_zero_has_no_budget(tmp_path: Path) -> None:
    text = _text(tmp_path, "x::n0", "--depth", "4", "--limit", "0", edges=CHAIN)

    assert "showing" not in text


def test_a_hub_row_says_how_many_links_were_not_walked(tmp_path: Path) -> None:
    path = _write(tmp_path, HUB_EDGES)
    report = walk.run_cause(tmp_path, {}, ["x::a"], "off", 3, [], None, path, hub=2, full=True)

    assert "  x::h  t.x  mapped  calls  src/a.php:1  [hub: 3 links not walked]" in (
        walk.render_text(report).splitlines()
    )


def test_touch_adds_what_a_reached_node_points_at_one_hop_out_marked(tmp_path: Path) -> None:
    edges = [("calls", "x::a", "x::b", 1), ("links_to", "x::b", "x::t", 2)]
    edges += [("links_to", "x::t", "x::far", 3)]
    lines = _text(tmp_path, "x::a", "--touch", edges=edges).splitlines()

    assert "    x::t  t.x  mapped  links_to  src/a.php:2  [touch]" in lines
    assert not any("x::far" in line for line in lines)


def test_without_touch_no_touching_row_prints(tmp_path: Path) -> None:
    edges = [("calls", "x::a", "x::b", 1), ("links_to", "x::b", "x::t", 2)]

    assert "x::t" not in _text(tmp_path, "x::a", edges=edges)


def test_the_walk_names_the_kinds_it_walked_undeclared(tmp_path: Path) -> None:
    assert "undeclared kinds, walked by raw direction: uses_x" in _text(
        tmp_path, "x::a"
    ).splitlines()


def test_an_old_map_with_no_cause_lists_walks_as_before_and_says_so(tmp_path: Path) -> None:
    path = _write(tmp_path, causes=None)
    new = walk.run_cause(tmp_path, {}, ["x::a"], "off", 1, [], None, path)
    old = walk.run(tmp_path, {}, "x::a", "out", 1, [], 50, path)
    note = "warning: the map declares no cause directions; walked by raw direction, as --raw does"

    assert walk.render_text(new) == walk.render_text(old) + f"{note}\n"


def test_the_json_rows_carry_hop_kind_direction_and_the_node_reached_from(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path)
    report = walk.run_cause(tmp_path, {}, ["x::a"], "off", 1, [], None, path)
    document = json.loads(walk.render_json(report))
    row = next(r for r in document["rows"] if r["id"] == "x::c")

    assert {k: row[k] for k in ("hop", "via_kind", "via_direction", "from", "file", "line")} == {
        "hop": 1,
        "via_kind": "implements_hook",
        "via_direction": "backward",
        "from": "x::a",
        "file": "src/a.php",
        "line": 5,
    }


def test_the_json_counts_every_hop_and_lists_the_hubs(tmp_path: Path) -> None:
    path = _write(tmp_path, HUB_EDGES)
    report = walk.run_cause(tmp_path, {}, ["x::a"], "off", 1, [], None, path, hub=2)
    document = json.loads(walk.render_json(report))

    assert document["hops"] == [{"hop": 1, "things": 1, "by_type": {"t.x": 1}}]
    assert document["hubs"] == [{"id": "x::h", "hop": 1, "fan": 3}]


def test_the_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    path = _write(tmp_path)
    report = walk.run_cause(tmp_path, {}, ["x::a"], "by", 2, [], None, path, touch=True)
    document = json.loads(walk.render_json(report))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/affected"}]})

    assert list(validator.iter_errors(document)) == []


# --- the command line -----------------------------------------------------------------------


def test_raw_keeps_the_old_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path)
    old = walk.render_text(walk.run(tmp_path, {}, "x::a", "in", 2, [], 50, path))

    assert main(["affected", "x::a", "--raw", "--depth", "2", "--map", str(path)]) == 0
    assert capsys.readouterr().out == old


def test_depth_all_walks_to_the_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, CHAIN)

    assert main(["neighbors", "x::n0", "--depth", "all", "--full", "--map", str(path)]) == 0
    assert "x::n4" in capsys.readouterr().out


def test_hub_and_through_reach_the_walk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, HUB_EDGES)
    argv = ["neighbors", "x::a", "--depth", "all", "--hub", "2", "--full", "--map", str(path)]

    assert main(argv) == 0
    assert "x::h1" not in capsys.readouterr().out
    assert main([*argv, "--through", "x::h"]) == 0
    assert "x::h1" in capsys.readouterr().out


def test_raw_with_a_cause_option_is_a_usage_error(tmp_path: Path) -> None:
    path = _write(tmp_path)

    with pytest.raises(SystemExit) as raised:
        main(["neighbors", "x::a", "--raw", "--touch", "--map", str(path)])
    assert raised.value.code == int(ExitCode.USAGE)


def test_the_help_states_the_walk_defaults() -> None:
    assert (cli.BUDGET, cli.HUB) == (walk.BUDGET, walk.HUB)
