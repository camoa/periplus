"""A printed slice adds the members of a container start and walks from them; it never walks
through a grouping edge.

An invented app. `in_box` is a grouping kind, so its cause is none: a member belongs to the box.
The other kinds set off their to end.

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
        "cause_from_kinds": ["calls", "needs", "uses"],
        "cause_none_kinds": ["in_box"],
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


def test_the_walk_never_goes_through_a_container(tmp_path: Path) -> None:
    report = _piece(tmp_path, C1)

    assert report.held == (C1, S, X)
    assert BOX not in report.held and R1 not in report.held


def test_naming_the_grouping_kind_walks_nothing_and_says_why(tmp_path: Path) -> None:
    report = _piece(tmp_path, C1, kinds=("in_box",))

    assert report.held == (C1,)
    assert (
        "the kind 'in_box' is listed under cause none, which the walk by cause does not follow;"
        " --raw follows it"
    ) in report.warnings


def test_a_container_start_lists_its_members_as_members_does_and_walks_from_them(
    tmp_path: Path,
) -> None:
    report = _piece(tmp_path, BOX, limit=0)
    (members,) = report.members
    lines = slicing.render_text(report).splitlines()

    assert members.by_type == (("t.class", 3), ("t.route", 2), ("t.service", 1))
    assert [row.id for row in members.rows] == [C1, C2, C3, R1, R2, S]
    assert lines[2] == (
        "members of app: 6 (t.class 3, t.route 2, t.service 1);"
        " all: periplus members app (--type T for one type)"
    )
    assert report.held == (BOX, C1, C2, C3, R1, R2, S, BASE, X, Y, Z)


def test_a_type_without_words_keeps_the_members_of_that_type(tmp_path: Path) -> None:
    report = _piece(tmp_path, BOX, types=("t.class",), limit=0)
    (members,) = report.members

    assert [row.id for row in members.rows] == [C1, C2, C3]
    assert report.held == (BOX, C1, C2, C3, BASE, S, X, Y, Z)


def test_the_json_slice_carries_members_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, BOX, limit=4)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/slice_piece"}]})
    assert list(validator.iter_errors(document)) == []
    assert document["members"] == [
        {"container": BOX, "total": 6, "by_type": {"t.class": 3, "t.route": 2, "t.service": 1}}
    ]
    assert [(r["walk"], r["hop"]) for r in document["rows"]["items"]] == [("members", 0)] * 4
