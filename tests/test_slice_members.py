"""A printed slice stops at the container end of a grouping edge, and lists a container's members.

An invented app. `in_box` is a grouping kind: a member belongs to the box.

    C1, C2, C3 (t.class), R1, R2 (t.route), S (t.service) -in_box-> BOX (t.box)
    X (t.method) -uses-> C1, -uses-> C2;  C1 -calls-> S;  Y and Z -use-> S and C3 (other files)
    BOX -needs-> BASE (t.box)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node
from jsonschema import Draft202012Validator

from periplus.navigate import slice as slicing

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

BOX = "t.box::app"
BASE = "t.box::base"
C1, C2, C3 = (f"t.class::app.C{n}" for n in (1, 2, 3))
R1, R2 = "t.route::app.r1", "t.route::app.r2"
S = "t.service::app.s"
X, Y, Z = "t.method::app.X::run", "t.method::app.Y::run", "t.method::app.Z::run"

NODES = [
    _node(BOX, "t.box", line=1, file="app.info"),
    _node(BASE, "t.box", line=1, file="base.info"),
    *(_node(c, "t.class", line=1, file=f"src/{c[-2:]}.php") for c in (C1, C2, C3)),
    _node(R1, "t.route", line=1, file="app.routing"),
    _node(R2, "t.route", line=5, file="app.routing"),
    _node(S, "t.service", line=1, file="app.services"),
    _node(X, "t.method", line=1, file="src/X.php"),
    _node(Y, "t.method", line=1, file="src/Y.php"),
    _node(Z, "t.method", line=1, file="src/Z.php"),
]
EDGES = [
    *(_edge("in_box", m, BOX, 1, file="app.info") for m in (C1, C2, C3, R1, R2, S)),
    _edge("uses", X, C1, 2, file="src/X.php"),
    _edge("uses", X, C2, 3, file="src/X.php"),
    _edge("calls", C1, S, 4, file="src/C1.php"),
    _edge("uses", Y, S, 2, file="src/Y.php"),
    _edge("uses", Z, S, 2, file="src/Z.php"),
    _edge("uses", Y, C3, 3, file="src/Y.php"),
    _edge("uses", Z, C3, 3, file="src/Z.php"),
    _edge("needs", BOX, BASE, 2, file="app.info"),
]


def _piece(root: Path, *ids: str, **kw: Any) -> slicing.SliceReport:
    (root / ".periplus").mkdir(parents=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "grouping_kinds": ["in_box"],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    args: dict[str, Any] = {
        "prefixes": (),
        "direction": "both",
        "depth": None,
        "kinds": (),
        "limit": None,
        "out": None,
        "map_path": None,
    }
    args.update(kw)
    return slicing.run(root, {}, ids, **args)


def test_the_walk_stops_at_a_container_and_marks_it(tmp_path: Path) -> None:
    report = _piece(tmp_path, C1)
    ids = [row.id for row in report.rows.items]

    assert [row.container for row in report.rows.items if row.id == BOX] == [True]
    assert R1 not in ids and BASE not in ids


def test_a_container_is_one_row_per_start(tmp_path: Path) -> None:
    report = _piece(tmp_path, X)

    assert [row.id for row in report.rows.items].count(BOX) == 1


def test_naming_the_grouping_kind_walks_through_the_container(tmp_path: Path) -> None:
    report = _piece(tmp_path, C1, kinds=("in_box",))

    assert C2 in [row.id for row in report.rows.items]


def test_a_container_start_lists_its_members_by_type_rarest_first(tmp_path: Path) -> None:
    report = _piece(tmp_path, BOX, limit=4)
    (members,) = report.members
    lines = slicing.render_text(report).splitlines()

    assert list(members.by_type.items()) == [("t.service", 1), ("t.route", 2), ("t.class", 3)]
    assert [row.id for row in members.rows] == [S, R1, C3, R2]
    assert f"list one type in full: periplus slice {BOX} --type T --limit 0" in lines
    assert "  t.class 3" in lines


def test_a_type_with_a_container_start_lists_that_type_alone_in_full(tmp_path: Path) -> None:
    report = _piece(tmp_path, BOX, types=("t.class",), limit=0)
    (members,) = report.members

    assert [row.id for row in members.rows] == [C3, C1, C2]
    assert report.rows.items == ()


def test_the_json_piece_carries_members_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, BOX, limit=4)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/slice_piece"}]})
    assert list(validator.iter_errors(document)) == []
    assert document["members"][0]["by_type"] == {"t.class": 3, "t.route": 2, "t.service": 1}


def test_a_container_start_walks_its_own_edges_but_not_its_members(tmp_path: Path) -> None:
    report = _piece(tmp_path, BOX, limit=0)

    assert [row.id for row in report.rows.items if row.hop == 1] == [BASE]
