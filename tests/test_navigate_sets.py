"""``periplus extract``, ``join``, ``common``, ``minus`` and ``diff``: map files as sets."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import diff, extract, sets
from periplus.navigate.slice import run as run_slice

ROOT = Path(__file__).parents[1] / "src/periplus/contract/schema"
NAV = json.loads((ROOT / "navigation.schema.json").read_text(encoding="utf-8"))
MAP = json.loads((ROOT / "map.schema.json").read_text(encoding="utf-8"))

NODES = [
    _node("f::a", "t.function", line=1),
    _node("f::b", "t.function", line=2),
    _node("c::B", "t.class", "referenced"),
    _node("f::c", "t.function", line=3),
]
EDGES = [
    _edge("calls", "f::a", "f::b", 1),
    _edge("calls", "f::b", "c::B", 2),
    _edge("uses", "f::a", "c::B", 3),
    _edge("calls", "f::c", "f::a", 4),
]
HIERARCHY = [
    {"type": "t.callable", "parent": None},
    {"type": "t.class", "parent": None},
    {"type": "t.function", "parent": "t.callable"},
]


def _write(
    path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], **header: Any
) -> Path:
    document = _document(nodes, edges, type_hierarchy=HIERARCHY, **header)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _whole(root: Path) -> Path:
    return _write(
        root / "map.json",
        NODES,
        EDGES,
        generated_by="periplus 0.8.0",
        legend={"edge_kinds": {"calls": "runs it", "uses": "names it"}},
    )


def _map_errors(path: Path) -> list[Any]:
    return list(Draft202012Validator(MAP).iter_errors(json.loads(path.read_text("utf-8"))))


def _ids(path: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return (
        [n["id"] for n in document["nodes"]],
        [(e["kind"], e["from"], e["to"]) for e in document["edges"]],
    )


# extract


def test_extract_writes_exactly_the_things_and_the_edges_among_them(tmp_path: Path) -> None:
    report = extract.run(tmp_path, {}, ["f::a", "c::B"], Path("out.json"), _whole(tmp_path))

    assert report.problems == ()
    assert _ids(tmp_path / "out.json") == (["f::a", "c::B"], [("uses", "f::a", "c::B")])


def test_extract_writes_what_slice_writes_for_the_same_things(tmp_path: Path) -> None:
    whole = _whole(tmp_path)
    run_slice(tmp_path, {}, ["f::a"], [], "both", 1, [], 0, Path("slice.json"), whole)
    held = _ids(tmp_path / "slice.json")[0]

    extract.run(tmp_path, {}, held, Path("out.json"), whole)

    assert (tmp_path / "out.json").read_bytes() == (tmp_path / "slice.json").read_bytes()


def test_extract_writes_a_map_valid_against_the_map_schema(tmp_path: Path) -> None:
    extract.run(tmp_path, {}, ["f::a", "f::b"], Path("out.json"), _whole(tmp_path))

    assert _map_errors(tmp_path / "out.json") == []


def test_extract_refuses_an_id_that_names_no_node_and_writes_nothing(tmp_path: Path) -> None:
    report = extract.run(tmp_path, {}, ["f::a", "nope"], Path("out.json"), _whole(tmp_path))

    assert (report.exit_code, (tmp_path / "out.json").exists()) == (31, False)


def test_extract_refuses_to_write_over_the_map_it_reads(tmp_path: Path) -> None:
    whole = _whole(tmp_path)
    before = whole.read_bytes()

    report = extract.run(tmp_path, {}, ["f::a"], Path("map.json"), whole)

    assert (report.exit_code, whole.read_bytes()) == (27, before)


def test_extract_reads_ids_from_standard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    whole = _whole(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("f::a\nf::b\n"))

    assert main(["extract", "-", "--out", "out.json", "--map", str(whole)]) == 0
    assert capsys.readouterr().out.splitlines()[1] == f"wrote {tmp_path}/out.json: 2 nodes, 1 edge"


def test_extract_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    report = extract.run(tmp_path, {}, ["f::a"], Path("out.json"), _whole(tmp_path))

    assert (
        list(Draft202012Validator(NAV).iter_errors(json.loads(extract.render_json(report)))) == []
    )


# join, common, minus


def _two(root: Path) -> tuple[Path, Path]:
    """A holds a, b, B; B holds b, B, c. They share b, B and the edge b calls B."""
    whole = _whole(root)
    extract.run(root, {}, ["f::a", "f::b", "c::B"], Path("a.json"), whole)
    extract.run(root, {}, ["f::b", "c::B", "f::c"], Path("b.json"), whole)
    return root / "a.json", root / "b.json"


def test_join_holds_the_things_and_edges_of_any_input(tmp_path: Path) -> None:
    a, b = _two(tmp_path)

    report = sets.run(tmp_path, {}, "join", [a, b], Path("out.json"))

    assert report.problems == ()
    assert _ids(tmp_path / "out.json") == (
        ["c::B", "f::a", "f::b", "f::c"],
        [("calls", "f::a", "f::b"), ("calls", "f::b", "c::B"), ("uses", "f::a", "c::B")],
    )


def test_join_out_creates_the_missing_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = _two(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["join", str(a), str(b), "--out", "a/b/x.map.json"]) == 0
    assert _map_errors(tmp_path / "a" / "b" / "x.map.json") == []


def test_common_holds_the_things_and_edges_of_every_input(tmp_path: Path) -> None:
    a, b = _two(tmp_path)

    sets.run(tmp_path, {}, "common", [a, b], Path("out.json"))

    assert _ids(tmp_path / "out.json") == (["c::B", "f::b"], [("calls", "f::b", "c::B")])


def test_common_leaves_out_an_edge_one_input_lacks_between_shared_things(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.json", NODES[:2], EDGES[:1])
    b = _write(tmp_path / "b.json", NODES[:2], [])

    report = sets.run(tmp_path, {}, "common", [a, b], None)

    assert (report.things, report.edges) == (2, 0)


def test_minus_holds_the_first_inputs_things_no_other_holds(tmp_path: Path) -> None:
    a, b = _two(tmp_path)

    sets.run(tmp_path, {}, "minus", [a, b], Path("out.json"))

    assert _ids(tmp_path / "out.json") == (["f::a"], [])


def test_minus_keeps_the_edges_among_the_things_it_keeps(tmp_path: Path) -> None:
    whole = _whole(tmp_path)
    b = _write(tmp_path / "b.json", [NODES[2]], [])

    sets.run(tmp_path, {}, "minus", [whole, b], Path("out.json"))

    assert _ids(tmp_path / "out.json")[1] == [("calls", "f::a", "f::b"), ("calls", "f::c", "f::a")]


@pytest.mark.parametrize("command", ["join", "common", "minus"])
def test_every_result_is_a_valid_map_another_command_reads(tmp_path: Path, command: str) -> None:
    a, b = _two(tmp_path)

    sets.run(tmp_path, {}, command, [a, b], Path("out.json"))

    assert _map_errors(tmp_path / "out.json") == []
    assert sets.run(tmp_path, {}, "join", [tmp_path / "out.json", a], None).problems == ()


@pytest.mark.parametrize("command", ["join", "common"])
def test_the_order_of_the_inputs_changes_no_byte(tmp_path: Path, command: str) -> None:
    a, b = _two(tmp_path)
    c = _write(tmp_path / "c.json", NODES[1:2], [], generated_by="periplus 0.9.0")

    first = sets.run(tmp_path, {}, command, [a, b, c], Path("one.json"))
    second = sets.run(tmp_path, {}, command, [c, b, a], Path("two.json"))

    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    assert sets.render_text(first).splitlines()[:-1] == sets.render_text(second).splitlines()[:-1]


def test_a_thing_whose_copies_differ_is_kept_once_and_counted(tmp_path: Path) -> None:
    moved = {**NODES[0], "locations": [{"file": "src/a.php", "line": 9}]}
    a = _write(tmp_path / "a.json", [NODES[0]], [])
    b = _write(tmp_path / "b.json", [moved], [])

    c = _write(tmp_path / "c.json", [moved], [])
    d = _write(tmp_path / "d.json", [NODES[0]], [])

    one = sets.run(tmp_path, {}, "join", [a, b], Path("one.json"))
    sets.run(tmp_path, {}, "join", [c, d], Path("two.json"))

    assert one.things == 1
    assert one.warnings[0].startswith("1 thing and 0 edges differ between the maps, as f::a;")
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()


def test_the_header_merges_packs_and_builds_and_keeps_the_held_legend(tmp_path: Path) -> None:
    a, _ = _two(tmp_path)
    c = _write(
        tmp_path / "c.json",
        [NODES[3]],
        [],
        generated_by="periplus 0.9.0",
        packs=[{"pack": "go", "version": "1.0.0"}],
    )

    sets.run(tmp_path, {}, "join", [a, c], Path("out.json"))
    document = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))

    assert document["generated_by"] == "periplus 0.8.0; periplus 0.9.0"
    assert document["packs"] == [
        {"pack": "go", "version": "1.0.0"},
        {"pack": "php", "version": "0.1.0"},
    ]
    assert document["legend"] == {"edge_kinds": {"calls": "runs it", "uses": "names it"}}
    assert document["counts"]["nodes"] == 4
    assert document["type_hierarchy"] == HIERARCHY


def test_without_out_it_counts_and_writes_nothing(tmp_path: Path) -> None:
    a, b = _two(tmp_path)

    text = sets.render_text(sets.run(tmp_path, {}, "join", [a, b], None))

    assert text.splitlines() == [
        "periplus join",
        f"inputs: {a} (3 things, 3 edges), {b} (3 things, 1 edge)",
        "result: 4 things, 3 edges",
        "by type: t.function 3, t.class 1",
        "by state: mapped 3, referenced 1",
        "edges by kind: calls 2, uses 1",
    ]
    assert not (tmp_path / "out.json").exists()


def test_ids_prints_the_result_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = _two(tmp_path)

    assert main(["common", str(a), str(b), "--ids"]) == 0
    assert capsys.readouterr().out == "c::B\nf::b\n"


def test_a_file_that_is_not_a_map_is_refused(tmp_path: Path) -> None:
    a, _ = _two(tmp_path)
    (tmp_path / "x.json").write_text('{"nodes": []}', encoding="utf-8")

    report = sets.run(tmp_path, {}, "join", [a, tmp_path / "x.json"], Path("out.json"))

    assert (report.exit_code, (tmp_path / "out.json").exists()) == (30, False)


def test_a_map_with_a_malformed_node_is_refused(tmp_path: Path) -> None:
    a, _ = _two(tmp_path)
    bad = _write(tmp_path / "bad.json", [{"type": "t.x"}], [])

    assert sets.run(tmp_path, {}, "join", [a, bad], None).exit_code == 30


def test_maps_of_different_versions_are_refused(tmp_path: Path) -> None:
    a, _ = _two(tmp_path)
    b = _write(tmp_path / "b1.json", NODES[:1], [], periplus_map_version=1)

    assert sets.run(tmp_path, {}, "join", [a, b], None).exit_code == 2


def test_one_input_is_refused(tmp_path: Path) -> None:
    a, _ = _two(tmp_path)

    assert sets.run(tmp_path, {}, "join", [a], None).exit_code == 2


def test_out_on_an_input_is_refused(tmp_path: Path) -> None:
    a, b = _two(tmp_path)
    before = a.read_bytes()

    report = sets.run(tmp_path, {}, "join", [a, b], Path("a.json"))

    assert (report.exit_code, a.read_bytes()) == (27, before)


def test_sets_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    a, b = _two(tmp_path)
    document = json.loads(sets.render_json(sets.run(tmp_path, {}, "minus", [a, b], None)))

    assert document["by_kind"] == {}
    assert list(Draft202012Validator(NAV).iter_errors(document)) == []


# diff


def _old_new(root: Path) -> tuple[Path, Path]:
    """New drops f::c and its edge, adds f::d, moves f::a, adds a call to f::d, and counts one
    more occurrence of a calls b."""
    old = _write(root / "old.json", NODES, EDGES)
    moved = {**NODES[0], "locations": [{"file": "src/a.php", "line": 7}]}
    more = {**EDGES[0], "occurrences": 3}
    new = _write(
        root / "new.json",
        [moved, *NODES[1:3], _node("f::d", "t.function", line=5)],
        [more, *EDGES[1:3], _edge("calls", "f::b", "f::d", 6)],
        generated_by="periplus 0.9.0",
    )
    return old, new


def test_diff_lists_things_added_removed_and_changed_with_the_fields(tmp_path: Path) -> None:
    report = diff.run(tmp_path, {}, *_old_new(tmp_path))
    assert report.things is not None

    assert {
        c: [(r.id, r.type, r.fields) for r in report.things[c].items] for c in diff.CHANGES
    } == {
        "added": [("f::d", "t.function", ())],
        "removed": [("f::c", "t.function", ())],
        "changed": [("f::a", "t.function", ("locations",))],
    }


def test_diff_lists_edges_added_removed_and_changed(tmp_path: Path) -> None:
    report = diff.run(tmp_path, {}, *_old_new(tmp_path))
    assert report.edges is not None

    assert {
        c: [(r.kind, r.source, r.target, r.fields) for r in report.edges[c].items]
        for c in diff.CHANGES
    } == {
        "added": [("calls", "f::b", "f::d", ())],
        "removed": [("calls", "f::c", "f::a", ())],
        "changed": [("calls", "f::a", "f::b", ("occurrences",))],
    }


def test_diff_text_gives_the_counts_first_then_the_lists(tmp_path: Path) -> None:
    old, new = _old_new(tmp_path)

    text = diff.render_text(diff.run(tmp_path, {}, old, new))

    assert text.splitlines() == [
        "periplus diff",
        f"old: {old} (4 things, 4 edges)",
        f"new: {new} (4 things, 4 edges)",
        "header: generated_by",
        "things: 1 added, 1 removed, 1 changed",
        "  added by type: t.function 1",
        "  removed by type: t.function 1",
        "  changed by type: t.function 1",
        "edges: 1 added, 1 removed, 1 changed",
        "  added by kind: calls 1",
        "  removed by kind: calls 1",
        "  changed by kind: calls 1",
        "things added:",
        "  f::d  t.function",
        "things removed:",
        "  f::c  t.function",
        "things changed:",
        "  f::a  t.function  (locations)",
        "edges added:",
        "  calls  f::b -> f::d",
        "edges removed:",
        "  calls  f::c -> f::a",
        "edges changed:",
        "  calls  f::a -> f::b  (occurrences)",
    ]


def test_a_cut_list_says_how_many_it_shows_and_names_the_option_for_all(tmp_path: Path) -> None:
    old = _write(tmp_path / "old.json", [], [])
    new = _write(tmp_path / "new.json", NODES[:3], [])

    lines = diff.render_text(diff.run(tmp_path, {}, old, new, limit=2)).splitlines()

    assert lines[-5:] == [
        "things added:",
        "  c::B  t.class",
        "  f::a  t.function",
        "  showing 2 of 3",
        "--limit 0 prints every row",
    ]


def test_a_map_against_itself_has_no_change(tmp_path: Path) -> None:
    whole = _whole(tmp_path)

    lines = diff.render_text(diff.run(tmp_path, {}, whole, whole)).splitlines()

    assert lines[3:] == [
        "header: same",
        "things: 0 added, 0 removed, 0 changed",
        "edges: 0 added, 0 removed, 0 changed",
    ]


def test_diff_ids_picks_the_changes_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old, new = _old_new(tmp_path)

    assert (
        main(["diff", str(old), str(new), "--ids", "--change", "removed", "--change", "changed"])
        == 0
    )
    assert capsys.readouterr().out == "f::a\nf::c\n"
    assert main(["diff", str(old), str(new), "--ids"]) == 0
    assert capsys.readouterr().out == "f::a\nf::c\nf::d\n"


def test_diff_of_a_whole_map_and_a_join_of_its_slices_is_what_they_left_out(
    tmp_path: Path,
) -> None:
    a, b = _two(tmp_path)
    sets.run(tmp_path, {}, "join", [a, b], Path("joined.json"))

    report = diff.run(tmp_path, {}, tmp_path / "map.json", tmp_path / "joined.json")
    assert report.edges is not None and report.things is not None

    assert [r.target for r in report.edges["removed"].items] == ["f::a"]
    assert report.things["changed"].items == ()


def test_diff_refuses_a_file_that_is_not_a_map(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text("not json", encoding="utf-8")

    assert diff.run(tmp_path, {}, _whole(tmp_path), tmp_path / "x.json").exit_code == 30


def test_diff_json_matches_the_navigation_schema(tmp_path: Path) -> None:
    document = json.loads(diff.render_json(diff.run(tmp_path, {}, *_old_new(tmp_path), limit=1)))

    assert document["things"]["added"]["items"] == [
        {"id": "f::d", "type": "t.function", "fields": []}
    ]
    assert list(Draft202012Validator(NAV).iter_errors(document)) == []
