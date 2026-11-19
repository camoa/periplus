"""``periplus depth``: per direction, how far the walk by cause goes and how much it reaches."""

from __future__ import annotations

import argparse
import io
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


def test_one_start_prints_the_two_lines_alone(tmp_path: Path) -> None:
    report = depth.run(tmp_path, {}, ["x::n0"], _write(tmp_path))

    assert depth.render_text(report) == (
        "periplus depth x::n0\n"
        "sets off:     6 hops, 6 things; 33% within 2, 50% within 3, 83% within 5; 0 hubs stopped\n"
        "set off by:   1 hop, 1 thing; 0 hubs stopped\n"
    )


def test_several_starts_add_a_row_per_start_alone_in_the_order_given(tmp_path: Path) -> None:
    edges = [*CHAIN, ("links_to", "x::l1", "x::n0", 1)]
    lines = _lines(tmp_path, "x::n3", "x::n0", edges=edges)

    assert lines[1].startswith("sets off:     3 hops, 5 things;")
    assert lines[2] == "set off by:   2 hops, 3 things; 0 hubs stopped"
    assert lines[3:6] == [
        "each start alone:",
        "  x::n3  sets off 3 hops, 3 things, 0 hubs stopped;"
        " set off by 4 hops, 4 things, 0 hubs stopped",
        "  x::n0  sets off 6 hops, 6 things, 0 hubs stopped;"
        " set off by 1 hop, 1 thing, 0 hubs stopped",
    ]
    assert lines[6].startswith("touching:")


def test_a_row_counts_the_hubs_that_start_stopped_at(tmp_path: Path) -> None:
    edges = [("calls", "x::a", f"x::h{n}", 1) for n in range(4)]
    edges += [("calls", f"x::h{n}", f"x::h{n}::{m}", 2) for n in range(4) for m in range(3)]
    edges += [("calls", "x::b", "x::c", 3)]
    lines = _lines(tmp_path, "x::a", "x::b", edges=edges, hub=2)

    assert lines[4].startswith("  x::a  sets off 1 hop, 4 things, 4 hubs stopped;")
    assert lines[5].startswith("  x::b  sets off 1 hop, 1 thing, 0 hubs stopped;")


def test_the_json_holds_each_start_alone_for_one_start_or_several(tmp_path: Path) -> None:
    path = _write(tmp_path)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/depth"}]})
    one = json.loads(depth.render_json(depth.run(tmp_path, {}, ["x::n0"], path)))
    two = json.loads(depth.render_json(depth.run(tmp_path, {}, ["x::n3", "x::n0"], path)))

    assert one["each_start"] == [
        {
            "id": "x::n0",
            "sets_off": {"hops": 6, "things": 6, "hubs": []},
            "set_off_by": {"hops": 1, "things": 1, "hubs": []},
        }
    ]
    assert [(s["id"], s["set_off_by"]["hops"]) for s in two["each_start"]] == [
        ("x::n3", 4),
        ("x::n0", 1),
    ]
    assert list(validator.iter_errors(one)) == []
    assert list(validator.iter_errors(two)) == []
    del one["each_start"]
    assert list(validator.iter_errors(one)) != []


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


# x::e1 and x::e2 set off x::m, which sets off x::leaf; x::s has no edge.
SET = [
    ("calls", "x::e1", "x::m", 1),
    ("calls", "x::e2", "x::m", 2),
    ("calls", "x::m", "x::leaf", 3),
]
SET_IDS = ["x::e1", "x::e2", "x::m", "x::leaf", "x::s"]


def _write_set(root: Path, edges: list[tuple[Any, ...]] = SET, name: str = "map.json") -> Path:
    names = sorted({e[1] for e in edges} | {e[2] for e in edges} | {"x::s"})
    document = _document([_node(n, line=1) for n in names], [_edge(*e) for e in edges], CAUSES)
    path = root / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _main(capsys: Any, *argv: str) -> tuple[int, str, str]:
    code = main(["depth", *argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_entrances_prints_only_the_ids_nothing_sets_off_with_their_rows(
    tmp_path: Path, capsys: Any
) -> None:
    path = _write_set(tmp_path)
    code, out, _ = _main(capsys, *SET_IDS, "--entrances", "--map", str(path))

    assert code == 0
    assert out == (
        "2 of 5 ids are entrances\n"
        "  x::e1  sets off 2 hops, 2 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "  x::e2  sets off 2 hops, 2 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "1 separate piece, nothing either way: x::s\n"
    )


def test_a_middle_thing_and_a_leaf_are_not_entrances(tmp_path: Path) -> None:
    report = depth.run(tmp_path, {}, ["x::m", "x::leaf"], _write_set(tmp_path), entrances=True)

    assert depth.render_text(report) == (
        "0 of 2 ids are entrances\n0 separate pieces, nothing either way\n"
    )


def test_one_id_is_or_is_not_an_entrance(tmp_path: Path) -> None:
    path = _write_set(tmp_path)
    one = depth.render_text(depth.run(tmp_path, {}, ["x::e1"], path, entrances=True))
    other = depth.render_text(depth.run(tmp_path, {}, ["x::m"], path, entrances=True))

    assert one.splitlines()[0] == "1 of 1 id is an entrance"
    assert other.splitlines()[0] == "0 of 1 id are entrances"


def test_separate_pieces_past_three_are_counted(tmp_path: Path) -> None:
    edges = [*SET, ("contains", "x::s1", "x::s2", 4), ("contains", "x::s3", "x::s4", 5)]
    ids = ["x::s", "x::s1", "x::s2", "x::s3", "x::s4"]
    report = depth.run(tmp_path, {}, ids, _write_set(tmp_path, edges), entrances=True)

    assert depth.render_text(report).splitlines()[-1] == (
        "5 separate pieces, nothing either way: x::s, x::s1, x::s2, +2"
    )


def test_entrances_ids_prints_only_the_entrance_ids(tmp_path: Path, capsys: Any) -> None:
    path = _write_set(tmp_path)
    code, out, err = _main(capsys, *SET_IDS, "--entrances", "--ids", "--map", str(path))

    assert code == 0
    assert out == "x::e1\nx::e2\n"
    assert err == "2 ids\n"


def test_ids_without_entrances_is_a_usage_error(tmp_path: Path, capsys: Any) -> None:
    path = _write_set(tmp_path)
    try:
        main(["depth", "x::e1", "--ids", "--map", str(path)])
    except SystemExit as stop:
        assert stop.code == 2
    else:
        raise AssertionError("depth --ids without --entrances ran")
    assert "--entrances" in capsys.readouterr().err


def test_entrances_json_holds_both_lists_and_matches_the_schema(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/depth"}]})
    report = depth.run(tmp_path, {}, SET_IDS, _write_set(tmp_path), entrances=True)
    document = json.loads(depth.render_json(report))

    assert document["entrances"] == ["x::e1", "x::e2"]
    assert document["separate_pieces"] == ["x::s"]
    assert list(validator.iter_errors(document)) == []
    document["entrances"] = [1]
    assert list(validator.iter_errors(document)) != []


def test_in_a_slice_file_a_thing_set_off_only_outside_it_is_an_entrance(
    tmp_path: Path, capsys: Any
) -> None:
    full = _write_set(tmp_path, [("calls", "x::p", "x::e1", 9), *SET], "full.json")
    part = _write_set(tmp_path, SET, "part.json")

    assert _main(capsys, "x::e1", "--entrances", "--ids", "--map", str(full))[1] == ""
    assert _main(capsys, "x::e1", "--entrances", "--ids", "--map", str(part))[1] == "x::e1\n"


def test_without_entrances_the_output_is_as_before(tmp_path: Path, capsys: Any) -> None:
    path = _write_set(tmp_path)
    text = _main(capsys, *SET_IDS, "--map", str(path))[1]
    document = json.loads(_main(capsys, *SET_IDS, "--map", str(path), "--format", "json")[1])

    assert text == (
        "periplus depth x::e1 x::e2 x::m +2 more\n"
        "sets off:     0 hops, 0 things; 0 hubs stopped\n"
        "set off by:   0 hops, 0 things; 0 hubs stopped\n"
        "each start alone:\n"
        "  x::e1    sets off 2 hops, 2 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "  x::e2    sets off 2 hops, 2 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "  x::m     sets off 1 hop, 1 thing, 0 hubs stopped;"
        " set off by 1 hop, 2 things, 0 hubs stopped\n"
        "  x::leaf  sets off 0 hops, 0 things, 0 hubs stopped;"
        " set off by 2 hops, 3 things, 0 hubs stopped\n"
        "  x::s     sets off 0 hops, 0 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
    )
    assert sorted(document) == [
        "declares_causes",
        "each_start",
        "problems",
        "set_off_by",
        "sets_off",
        "starts",
        "touching",
        "undeclared",
        "warnings",
    ]


# x::loop calls only itself; x::a sets off x::h, a hub at --hub 2 over the x::k things, which x::g
# sets off too; x::t is only pointed at (touch) and x::c only holds x::d (none); x::j sets off
# x::i by a to kind; x::s has no edge.
SORT = [
    ("calls", "x::loop", "x::loop", 1),
    ("calls", "x::a", "x::h", 2),
    *[("calls", "x::h", f"x::k{m}", 3) for m in range(3)],
    *[("calls", "x::g", f"x::k{m}", 4) for m in range(3)],
    ("links_to", "x::l", "x::t", 5),
    ("contains", "x::c", "x::d", 6),
    ("implements_hook", "x::i", "x::j", 7),
]
SORT_IDS = ["x::loop", "x::a", "x::h", "x::g", "x::k0", "x::l", "x::t", "x::c", "x::d"]
SORT_IDS += ["x::i", "x::j", "x::s"]


def test_entrances_sorts_each_id_as_the_full_walk_of_every_id_does(tmp_path: Path) -> None:
    path = _write_set(tmp_path, SORT)
    walked = depth.run(tmp_path, {}, SORT_IDS, path, hub=2)
    found = depth.run(tmp_path, {}, SORT_IDS, path, hub=2, entrances=True)

    assert depth.entrances(found) == depth.entrances(walked)
    assert depth.entrances(found) == (
        ("x::a", "x::g", "x::j"),
        ("x::loop", "x::l", "x::t", "x::c", "x::d", "x::s"),
    )


def test_entrances_walks_an_entrance_up_to_a_hub_and_from_a_hub_start(
    tmp_path: Path, capsys: Any
) -> None:
    path = _write_set(tmp_path, SORT)
    ids = ["x::a", "x::h", "x::g", "x::k0"]
    code, out, _ = _main(capsys, *ids, "--entrances", "--hub", "2", "--map", str(path))

    assert code == 0
    assert out == (
        "2 of 4 ids are entrances\n"
        "  x::a  sets off 1 hop, 1 thing, 1 hub stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "  x::g  sets off 1 hop, 3 things, 0 hubs stopped;"
        " set off by 0 hops, 0 things, 0 hubs stopped\n"
        "0 separate pieces, nothing either way\n"
    )


def test_entrances_json_each_start_holds_the_entrances_and_the_separate_pieces(
    tmp_path: Path,
) -> None:
    report = depth.run(tmp_path, {}, SET_IDS, _write_set(tmp_path), entrances=True)
    document = json.loads(depth.render_json(report))

    assert [entry["id"] for entry in document["each_start"]] == ["x::e1", "x::e2", "x::s"]


def test_entrances_with_an_unknown_id_keeps_the_entrances_form(tmp_path: Path) -> None:
    report = depth.run(tmp_path, {}, ["x::e1", "x::nope"], _write_set(tmp_path), entrances=True)
    document = json.loads(depth.render_json(report))

    assert report.exit_code == 31
    assert depth.render_text(report).splitlines()[0] == "0 of 0 ids are entrances"
    assert (document["entrances"], document["separate_pieces"]) == ([], [])


def test_entrances_reads_the_ids_from_standard_input(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    path = _write_set(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(SET_IDS) + "\n"))

    code, out, _ = _main(capsys, "-", "--entrances", "--ids", "--map", str(path))

    assert (code, out) == (0, "x::e1\nx::e2\n")
