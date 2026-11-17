"""The printed slice in its dense form: nodes grouped by file, links as short clauses, folds,
the nodes left unwalked, an inventory, and a byte budget.

An invented shop, with files in brackets; `in_box` is a grouping kind, `calls` sets off its to
end and `contains` is structure:

    Cart [src/Cart.php:2] -contains-> add [:4], total [:8];  Cart, Mailer -in_box-> shop
    add -calls-> total, Mailer::send, ::hello, ::bye [src/Mailer.php], vendor Log::write
        (unresolved), Dbg::dump (referenced)
    Mailer::send -calls-> Far::deep [src/Far.php:1] -calls-> Far::deeper [:3]
    A::run and B::run share the name run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus.navigate import slice as slicing
from periplus.navigate.ids import resolve
from periplus.navigate.mapfile import MapIndex
from periplus.navigate.names import Names

CART = "t.class::shop.Cart"
ADD = "t.method::shop.Cart::add"
TOTAL = "t.method::shop.Cart::total"
MAILER = "t.class::shop.Mailer"
SEND = "t.method::shop.Mailer::send"
HELLO = "t.method::shop.Mailer::hello"
BYE = "t.method::shop.Mailer::bye"
LOG = "t.method::vendor.Log::write"
DUMP = "t.method::vendor.Dbg::dump"
BOX = "t.box::shop"
DEEP = "t.method::shop.Far::deep"
DEEPER = "t.method::shop.Far::deeper"
RUN_A = "t.method::shop.A::run"
RUN_B = "t.method::shop.B::run"
# The tail q::z of ALIAS is unique, and it is QZ's full id, so ALIAS cannot use it.
QZ = "q::z"
ALIAS = "t.ref::q::z"

FILES = {
    "src/Cart.php": [
        "<?php",
        "class Cart {",
        "",
        "  public function add() {",
        "    $this->total();",
        "  }",
        "",
        "  public function total() {",
        "  }",
        "}",
    ],
    "src/Mailer.php": [
        "<?php",
        "class Mailer {",
        "  public function send() {}",
        "",
        "  public function hello() {}",
        "",
        "  public function bye() {}",
        "}",
    ],
    "src/Far.php": ["function deep() {}", "", "function deeper() {}"],
}

NODES = [
    _node(CART, "t.class", line=2, file="src/Cart.php"),
    _node(ADD, "t.method", line=4, file="src/Cart.php"),
    _node(TOTAL, "t.method", line=8, file="src/Cart.php"),
    _node(MAILER, "t.class", line=2, file="src/Mailer.php"),
    _node(SEND, "t.method", line=3, file="src/Mailer.php"),
    _node(HELLO, "t.method", line=5, file="src/Mailer.php"),
    _node(BYE, "t.method", line=7, file="src/Mailer.php"),
    _node(LOG, "t.method", state="unresolved"),
    _node(DUMP, "t.method", state="referenced"),
    _node(BOX, "t.zone", line=1, file="shop.info"),
    _node(DEEP, "t.method", line=1, file="src/Far.php"),
    _node(DEEPER, "t.method", line=3, file="src/Far.php"),
    _node(RUN_A, "t.method", line=1, file="src/A.php"),
    _node(RUN_B, "t.method", line=1, file="src/B.php"),
    _node(QZ, "t.q", line=1, file="src/q.php"),
    _node(ALIAS, "t.ref", line=1, file="src/ref.php"),
]
EDGES = [
    _edge("contains", CART, ADD, 4, file="src/Cart.php"),
    _edge("contains", CART, TOTAL, 8, file="src/Cart.php"),
    _edge("calls", ADD, TOTAL, 5, file="src/Cart.php"),
    *(_edge("calls", ADD, m, 5, file="src/Cart.php") for m in (SEND, HELLO, BYE, LOG, DUMP)),
    _edge("in_box", CART, BOX, 1, file="shop.info"),
    _edge("in_box", MAILER, BOX, 1, file="shop.info"),
    _edge("calls", SEND, DEEP, 3, file="src/Mailer.php"),
    _edge("calls", DEEP, DEEPER, 1, file="src/Far.php"),
]


def _site(root: Path) -> Path:
    (root / ".periplus").mkdir(parents=True)
    for name, lines in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "grouping_kinds": ["in_box"],
        "cause_from_kinds": ["calls"],
        "cause_none_kinds": ["contains", "in_box"],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _piece(root: Path, *ids: str, **kw: Any) -> slicing.SliceReport:
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
    return slicing.run(_site(root), {}, ids, **args)


def _text(report: slicing.SliceReport) -> list[str]:
    return slicing.render_text(report).splitlines()


def test_each_file_is_a_header_once_with_its_container_and_nodes_in_line_order(
    tmp_path: Path,
) -> None:
    lines = _text(_piece(tmp_path, ADD))

    assert lines.count("Cart.php  in shop") == 1
    assert "Mailer.php  in shop" in lines
    nodes = [line for line in lines if line.startswith("  :")]
    assert nodes[:3] == ["  :4  add  t.method", "  :8  total  t.method", "  :3  send  t.method"]


def test_every_short_name_resolves_back_to_its_node(tmp_path: Path) -> None:
    site = _site(tmp_path)
    names = Names(MapIndex(json.loads((site / ".periplus/map.json").read_text())))

    assert [names.short(i) for i in (ADD, RUN_A, RUN_B, BOX)] == ["add", "A::run", "B::run", "shop"]
    for node_id in (ADD, RUN_A, RUN_B, BOX, CART, QZ, ALIAS):
        assert resolve(names.index, names.short(node_id))[0] == node_id


def test_a_subject_prints_one_source_line(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD))
    at = lines.index("  :4  add  t.method")

    assert lines[at + 1] == "      | public function add() {"
    assert lines.count("      | public function add() {") == 1


def test_a_start_is_one_compact_line(tmp_path: Path) -> None:
    assert (
        _text(_piece(tmp_path, ADD))[1]
        == "start add  t.method  (given as 't.method::shop.Cart::add')"
    )


def test_links_fold_outside_ends_and_members_of_one_owner(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD))

    assert "      calls -> Mailer (3), total (+2 outside the project: dump, write)" in lines


def test_an_edge_inside_one_file_prints_once_at_its_from_end(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD))
    cart = lines[lines.index("Cart.php  in shop") : lines.index("Mailer.php  in shop")]

    assert "      calls -> Mailer (3), total (+2 outside the project: dump, write)" in cart
    assert "      calls <- add" not in cart
    assert "      calls <- add" in lines


def test_a_node_with_links_the_piece_does_not_show_says_how_many(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD, depth=1))

    assert "      +1 more link: calls -> 1; see periplus show send --limit 0" in lines


def test_the_inventory_names_every_node_by_type_rarest_first(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD))
    at = lines.index("inventory: 11 nodes")

    assert lines[at + 1 : at + 4] == [
        "  t.zone 1: shop",
        "  t.class 1: Mailer",
        "  t.method 9: add, bye, deep, deeper, dump, hello, send, total, write",
    ]


def test_the_default_piece_fits_the_byte_budget_and_says_what_it_cut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(slicing, "ROW_FLOOR", 0)
    slicing.BYTE_LIMIT, kept = 1000, slicing.BYTE_LIMIT
    try:
        report = _piece(tmp_path / "a", ADD)
        text = slicing.render_text(report)
        given = slicing.render_text(_piece(tmp_path / "b", ADD, limit=50))
    finally:
        slicing.BYTE_LIMIT = kept

    assert len(text.encode()) <= 1000 < len(given.encode())
    assert "inventory:" in text
    assert not any(" -> (+" in line or " <- (+" in line for line in text.splitlines())
    assert any(line.startswith("cut to fit 1000 bytes:") for line in text.splitlines())


def test_the_footer_names_the_kinds_with_most_rows_left_out_and_counts_the_rest(
    tmp_path: Path,
) -> None:
    (tmp_path / ".periplus").mkdir()
    ends = [f"t.method::far{k}" for k in range(8)]
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "nodes": [
            _node(i, "t.method", line=1, file="f.php")
            for i in ["t.method::hub", "t.method::far8", *ends]
        ],
        "edges": [
            *(_edge(f"kind{k}", "t.method::hub", e, 1, file="f.php") for k, e in enumerate(ends)),
            _edge("kind7", "t.method::hub", "t.method::far8", 2, file="f.php"),
        ],
    }
    (tmp_path / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    report = slicing.run(tmp_path, {}, ["hub"], (), "both", 1, (), 1, None, None)
    lines = _text(report)

    assert (
        "left out by kind: kind7 2, kind1 1, kind2 1, kind3 1, kind4 1, kind5 1, and 1 more kind"
        in lines
    )
