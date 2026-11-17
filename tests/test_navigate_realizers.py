"""A walk that reaches the to end of a realizing edge adds its from ends at the same hop.

An invented app. `implements_method` and `overrides` are realizing kinds: the from end is a
concrete form of the to end.

    RUN -calls-> PORT (an interface method)
    BASE, OTHER -implements_method-> PORT;  BASE -calls-> HOOK (an abstract method)
    ONE, TWO -overrides-> HOOK
    WIDE: twelve methods W00..W11 -implements_method-> WIDE
    LOOSE (outside the project) <-implements_method- ONE;  USER -calls-> LOOSE
    `handled_by` realizes the other way: its to end is the concrete one.
    PAGE -handled_by-> SHOW;  LINK -links_to-> PAGE
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node
from jsonschema import Draft202012Validator

from periplus.navigate import show, walk
from periplus.navigate import slice as slicing

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

RUN = "t.method::app.Runner::run"
PORT = "t.method::app.Port::send"
BASE = "t.method::app.Base::send"
OTHER = "t.method::app.Other::send"
HOOK = "t.method::app.Base::deliver"
ONE = "t.method::app.One::deliver"
TWO = "t.method::app.Two::deliver"
WIDE = "t.method::app.Wide::go"
WIDES = [f"t.method::app.W{n:02}::go" for n in range(12)]
LOOSE = "t.method::lib.Loose::deliver"
USER = "t.method::app.User::go"
PAGE = "t.route::app.page"
SHOW = "t.method::app.PageController::show"
LINK = "t.link::app.menu"

NODES = [
    _node(RUN, "t.method", line=3, file="src/Runner.php"),
    _node(PORT, "t.method", line=5, file="src/Port.php"),
    _node(BASE, "t.method", line=7, file="src/Base.php"),
    _node(HOOK, "t.method", line=9, file="src/Base.php"),
    _node(OTHER, "t.method", line=4, file="src/Other.php"),
    _node(ONE, "t.method", line=4, file="src/One.php"),
    _node(TWO, "t.method", line=4, file="src/Two.php"),
    _node(WIDE, "t.method", line=2, file="src/Wide.php"),
    *(_node(w, "t.method", line=2, file=f"src/W{n:02}.php") for n, w in enumerate(WIDES)),
    _node(LOOSE, "t.method", "referenced"),
    _node(USER, "t.method", line=2, file="src/User.php"),
    _node(PAGE, "t.route", line=1, file="app.routing.yml"),
    _node(SHOW, "t.method", line=8, file="src/PageController.php"),
    _node(LINK, "t.link", line=1, file="app.links.yml"),
]
EDGES = [
    _edge("calls", RUN, PORT, 4, file="src/Runner.php"),
    _edge("implements_method", BASE, PORT, 7, file="src/Base.php"),
    _edge("implements_method", OTHER, PORT, 4, file="src/Other.php"),
    _edge("calls", BASE, HOOK, 8, file="src/Base.php"),
    _edge("overrides", ONE, HOOK, 4, file="src/One.php"),
    _edge("overrides", TWO, HOOK, 4, file="src/Two.php"),
    _edge("calls", RUN, WIDE, 5, file="src/Runner.php"),
    *(_edge("implements_method", w, WIDE, 2, file=f"src/W{n:02}.php") for n, w in enumerate(WIDES)),
    _edge("implements_method", ONE, LOOSE, 4, file="src/One.php"),
    _edge("calls", USER, LOOSE, 3, file="src/User.php"),
    _edge("handled_by", PAGE, SHOW, 2, file="app.routing.yml"),
    _edge("links_to", LINK, PAGE, 2, file="app.links.yml"),
]


def _map(root: Path, realizing: bool = True) -> Path:
    document: dict[str, Any] = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    if realizing:
        document["realizing_kinds"] = ["implements_method", "overrides"]
        document["realizing_to_kinds"] = ["handled_by"]
    (root / ".periplus").mkdir(parents=True, exist_ok=True)
    path = root / ".periplus" / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _walk(root: Path, node: str, direction: str = "out", depth: int = 1, **kw: Any) -> Any:
    return walk.run(root, {}, node, direction, depth, kw.get("kinds", []), 0, _map(root))


def _rows(report: walk.WalkReport) -> list[tuple[str, int]]:
    return [(row.id, row.depth) for row in report.rows.items]


def test_neighbors_add_the_methods_behind_a_declaration_at_the_same_depth(tmp_path: Path) -> None:
    report = _walk(tmp_path, RUN, kinds=["calls"])

    assert (BASE, 1) in _rows(report) and (OTHER, 1) in _rows(report)


def test_the_rule_chains_hop_by_hop_to_the_overrides(tmp_path: Path) -> None:
    report = _walk(tmp_path, RUN, depth=2, kinds=["calls"])

    assert {(HOOK, 2), (ONE, 2), (TWO, 2)} <= set(_rows(report))


def test_a_map_without_realizing_kinds_walks_as_before(tmp_path: Path) -> None:
    _map(tmp_path, realizing=False)
    report = walk.run(tmp_path, {}, RUN, "out", 1, [], 0, tmp_path / ".periplus" / "map.json")

    assert _rows(report) == [(PORT, 1), (WIDE, 1)]


def test_a_declaration_reached_from_one_of_its_forms_does_not_add_the_others(
    tmp_path: Path,
) -> None:
    report = _walk(tmp_path, BASE)

    assert OTHER not in [row.id for row in report.rows.items]


def test_a_declaration_outside_the_project_adds_nothing(tmp_path: Path) -> None:
    assert _rows(_walk(tmp_path, USER)) == [(LOOSE, 1)]
    assert (LOOSE, 0) not in _rows(_walk(tmp_path, ONE, direction="in"))


def test_a_start_that_declares_lists_its_forms_at_depth_zero(tmp_path: Path) -> None:
    report = _walk(tmp_path, PORT)

    assert (BASE, 0) in _rows(report) and (HOOK, 1) in _rows(report)


def test_affected_adds_the_declaration_a_form_stands_for(tmp_path: Path) -> None:
    report = _walk(tmp_path, ONE, direction="in")

    assert (HOOK, 0) in _rows(report) and (BASE, 1) in _rows(report)


def test_the_forms_of_one_node_are_capped_with_a_count_line(tmp_path: Path) -> None:
    report = _walk(tmp_path, RUN)
    lines = walk.render_text(report).splitlines()

    assert len([w for w in WIDES if w in [row.id for row in report.rows.items]]) == 8
    assert WIDES[:8] == [row.id for row in report.rows.items if row.via == WIDE]
    assert (
        f"  +4 more stand for {WIDE}, past the first 8; see periplus show {WIDE}"
        f" --map {tmp_path / '.periplus' / 'map.json'}"
    ) in lines


def test_a_form_row_names_the_relation(tmp_path: Path) -> None:
    lines = walk.render_text(_walk(tmp_path, RUN, kinds=["calls"])).splitlines()

    assert any(
        f"{BASE}  t.method  mapped  realizes {PORT} by implements_method" in x for x in lines
    )


def test_walk_json_marks_a_form_row_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(walk.render_json(_walk(tmp_path, PORT)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/neighbors"}]})
    assert list(validator.iter_errors(document)) == []
    assert [i["id"] for i in document["rows"]["items"] if i["stands_for"]] == [
        BASE,
        OTHER,
        ONE,
        TWO,
    ]


def test_show_lists_the_forms_in_a_short_section(tmp_path: Path) -> None:
    report = show.run(tmp_path, {}, PORT, 50, _map(tmp_path))
    lines = show.render_text(report).splitlines()

    at = lines.index("Realized by (2):")
    assert lines[at + 1 : at + 3] == [
        f"  {BASE}  t.method  by implements_method",
        f"  {OTHER}  t.method  by implements_method",
    ]


def test_show_prints_no_section_for_a_node_without_forms(tmp_path: Path) -> None:
    lines = show.render_text(show.run(tmp_path, {}, RUN, 50, _map(tmp_path))).splitlines()

    assert not any(line.startswith("Realized by") for line in lines)


def _piece(root: Path, *ids: str, **kw: Any) -> slicing.SliceReport:
    _map(root)
    args: dict[str, Any] = {
        "prefixes": (),
        "direction": "both",
        "depth": None,
        "kinds": (),
        "limit": 0,
        "out": None,
        "map_path": None,
    }
    args.update(kw)
    return slicing.run(root, {}, ids, **args)


def test_a_printed_slice_reaches_the_overrides_within_two_hops(tmp_path: Path) -> None:
    report = _piece(tmp_path, RUN)
    reached = {row.id: row.hop for row in report.rows.items}

    assert reached[BASE] == 1 and reached[ONE] == 2 and reached[TWO] == 2


def test_a_printed_slice_says_realized_by(tmp_path: Path) -> None:
    lines = slicing.render_text(_piece(tmp_path, RUN)).splitlines()

    assert "      realized by (implements_method) -> Base::send, Other::send" in lines
    assert "      realized by (overrides) -> One::deliver, Two::deliver" in lines


def test_a_written_slice_holds_the_forms(tmp_path: Path) -> None:
    report = _piece(tmp_path, RUN, out=Path("piece.json"), limit=None)
    written = json.loads((tmp_path / "piece.json").read_text(encoding="utf-8"))

    assert report.problems == ()
    assert {BASE, OTHER} <= {node["id"] for node in written["nodes"]}


def test_a_kind_whose_to_end_is_concrete_adds_the_to_end_at_the_same_hop(
    tmp_path: Path,
) -> None:
    report = _walk(tmp_path, LINK)

    assert (PAGE, 1) in _rows(report) and (SHOW, 1) in _rows(report)
    assert any(row.stands_for and row.id == SHOW for row in report.rows.items)


def test_affected_adds_what_a_concrete_to_end_carries_out(tmp_path: Path) -> None:
    report = _walk(tmp_path, SHOW, direction="in")

    assert (PAGE, 0) in _rows(report) and (LINK, 1) in _rows(report)


def test_show_lists_a_concrete_to_end(tmp_path: Path) -> None:
    lines = show.render_text(show.run(tmp_path, {}, PAGE, 50, _map(tmp_path))).splitlines()

    assert lines[lines.index("Realized by (1):") + 1] == f"  {SHOW}  t.method  by handled_by"


def test_a_printed_slice_says_realized_by_for_a_concrete_to_end(tmp_path: Path) -> None:
    lines = slicing.render_text(_piece(tmp_path, LINK)).splitlines()

    assert "      realized by (handled_by) -> show" in lines
