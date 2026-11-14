"""The short names and owners a printed slice uses, each table built once a run."""

from __future__ import annotations

from _navigate import _node

from periplus.navigate.mapfile import MapIndex
from periplus.navigate.slice import _Names

NODES = [
    _node("t.class::app.Box", "t.class", "referenced"),
    _node("u.class::app.Box", "u.class", line=1),
    _node("v.class::app.Box", "v.class", line=1),
    _node("t.method::app.Box::open", "t.method", line=2),
    _node("t.method::app.Bin::open", "t.method", line=3),
    _node("t.method::lib-x.y_z::go", "t.method", line=4),
    _node("w.x::a..b", "w.x", line=5),
    _node("w.x::c-b", "w.x", line=6),
]


def _names() -> _Names:
    return _Names(MapIndex({"nodes": NODES, "edges": []}))


def test_an_owner_is_the_mapped_node_of_that_name_with_the_smallest_id() -> None:
    names = _names()

    assert names.owner("t.method::app.Box::open") == "u.class::app.Box"
    assert names.owner("t.method::app.Bin::open") is None
    assert names.owner("t.class::app.Box") is None


def test_a_short_name_is_the_shortest_unique_tail_after_a_separator() -> None:
    names = _names()

    assert names.short("t.method::app.Box::open") == "Box::open"
    assert names.short("t.method::lib-x.y_z::go") == "go"
    assert names.short("u.class::app.Box") == "u.class::app.Box"
    assert names.short("w.x::a..b") == "a..b"
