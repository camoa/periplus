"""The printed slice as pieces: the words gather nodes, edges join some of them, and the output
says which are joined and which stand alone.

An invented app; `in_box` is a grouping kind, and the other kinds set off their to end. Every
start holds the word "token":

    TokenForm -checks-> TokenCheck                 [site/app/src/]
    TokenRule -calls-> Util::h1 .. Util::h6        [site/app/src/]
    token_js                                       [site/app/js/]
    look_token_alter                               [site/look/look.theme]
    TokenForm, TokenCheck, TokenRule, token_js -in_box-> app;  look_token_alter -in_box-> look
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

FORM = "t.form::app.TokenForm"
CHECK = "t.check::app.TokenCheck"
RULE = "t.rule::app.TokenRule"
SCRIPT = "t.script::app.token_js"
ALTER = "t.function::look_token_alter"
BOX = "t.box::app"
LOOK = "t.box::look"
HELPERS = [f"t.method::app.Util::h{n}" for n in range(1, 7)]
SRC = "site/app/src"

NODES = [
    _node(FORM, "t.form", line=3, file=f"{SRC}/TokenForm.php"),
    _node(CHECK, "t.check", line=2, file=f"{SRC}/TokenCheck.php"),
    _node(RULE, "t.rule", line=4, file=f"{SRC}/TokenRule.php"),
    _node(SCRIPT, "t.script", line=1, file="site/app/js/token.js"),
    _node(ALTER, "t.function", line=5, file="site/look/look.theme"),
    _node(BOX, "t.box", line=1, file="site/app/app.info"),
    _node(LOOK, "t.box", line=1, file="site/look/look.info"),
    *(_node(h, "t.method", line=n, file=f"{SRC}/Util.php") for n, h in enumerate(HELPERS, 1)),
]
EDGES = [
    _edge("checks", FORM, CHECK, 5, file=f"{SRC}/TokenForm.php"),
    *(_edge("calls", RULE, h, 6, file=f"{SRC}/TokenRule.php") for h in HELPERS),
    *(_edge("in_box", n, BOX, 1, file="site/app/app.info") for n in (FORM, CHECK, RULE, SCRIPT)),
    _edge("in_box", ALTER, LOOK, 1, file="site/look/look.info"),
]


def _site(root: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Path:
    (root / ".periplus").mkdir(parents=True)
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "own", "version": "0.1.0"}],
        "roots": ["."],
        "grouping_kinds": ["in_box"],
        "cause_from_kinds": ["calls", "checks", "to"],
        "cause_none_kinds": ["in_box"],
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": edges,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _run(root: Path, *words: str, **kw: Any) -> slicing.SliceReport:
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
    return slicing.run(root, {}, words, **args)


def _piece(root: Path, *words: str, **kw: Any) -> slicing.SliceReport:
    return _run(_site(root, NODES, EDGES), *words, **kw)


def _lines(report: slicing.SliceReport) -> list[str]:
    return slicing.render_text(report).splitlines()


def test_linked_starts_share_a_piece_and_a_grouping_edge_joins_none(tmp_path: Path) -> None:
    lines = _lines(_piece(tmp_path, "token"))

    assert [line for line in lines if line.startswith("piece ")] == [
        "piece 1 of 4: 3 things, starts: TokenCheck, TokenForm",
        "piece 2 of 4: 7 things, starts: TokenRule",
        "piece 3 of 4: 2 things, starts: look_token_alter",
        "piece 4 of 4: 1 thing, starts: token_js",
    ]


def test_each_piece_prints_its_own_files_under_its_header(tmp_path: Path) -> None:
    lines = _lines(_piece(tmp_path, "token"))
    second = lines.index("piece 2 of 4: 7 things, starts: TokenRule")
    third = lines.index("piece 3 of 4: 2 things, starts: look_token_alter")

    assert "app/src/TokenRule.php  in app" in lines[second:third]
    assert "app/src/TokenForm.php  in app" in lines[:second]
    assert "app/src/TokenForm.php  in app" not in lines[second:]


def test_the_last_piece_ends_with_the_absence_of_a_mapped_link_and_the_path_command(
    tmp_path: Path,
) -> None:
    lines = _lines(_piece(tmp_path, "token"))

    assert (
        "no edge of the map joins these 4 pieces as printed; they may still meet through nodes"
        " not printed, or relate in ways the map does not hold; test two with"
        " periplus path TokenCheck TokenRule"
    ) in lines
    assert lines.index("piece 4 of 4: 1 thing, starts: token_js") < lines.index(
        "inventory: 13 nodes"
    )


def test_one_piece_has_no_closing_line(tmp_path: Path) -> None:
    lines = _lines(_piece(tmp_path, FORM, depth=1))

    assert "piece 1 of 1: 3 things, starts: TokenForm" in lines
    assert not any(line.startswith("no edge of the map joins") for line in lines)
    assert "  t.check 1: TokenCheck" in lines


def test_pieces_go_by_summed_word_score_then_size_then_smallest_start_id(tmp_path: Path) -> None:
    report = _piece(tmp_path, "token")

    assert [piece.starts for piece in report.pieces] == [
        (CHECK, FORM),
        (RULE,),
        (ALTER,),
        (SCRIPT,),
    ]


def test_paths_print_under_the_folder_all_files_share(tmp_path: Path) -> None:
    lines = _lines(_piece(tmp_path, "token"))
    first = next(i for i, line in enumerate(lines) if line.startswith("piece "))

    assert "paths under: site/" in lines[:first]
    assert "look/look.theme  in look" in lines
    assert not any(line.startswith("site/") for line in lines)


def test_the_inventory_names_the_piece_of_each_node(tmp_path: Path) -> None:
    lines = _lines(_piece(tmp_path, "token"))
    at = lines.index("inventory: 13 nodes")

    assert "  t.box 2: app [1], look [3]" in lines[at:]
    assert "  t.check 1: TokenCheck [1]" in lines[at:]


def test_every_start_walks_the_same_depth(tmp_path: Path) -> None:
    words = [f"t.note::n.word{k:02}" for k in range(10)]
    nodes = [_node(w, "t.note", line=1, file=f"n/{k}.txt") for k, w in enumerate(words)]
    nodes += [_node(f"t.x::mid{k}", "t.x", line=1, file=f"n/{k}.txt") for k in range(10)]
    nodes += [_node(f"t.x::far{k}", "t.x", line=2, file=f"n/{k}.txt") for k in range(10)]
    edges = [_edge("to", w, f"t.x::mid{k}", 1, file=f"n/{k}.txt") for k, w in enumerate(words)]
    edges += [_edge("to", f"t.x::mid{k}", f"t.x::far{k}", 2, file=f"n/{k}.txt") for k in range(10)]

    report = _run(_site(tmp_path / "a", nodes, edges), "word", depth=slicing.PRINT_DEPTH, limit=0)
    assert len(report.starts) == 10 and len(report.pieces) == 10
    assert all(
        {r.hop for r in report.rows.items if r.start == s.row.id} == {1, 2} for s in report.starts
    )
    one = _run(_site(tmp_path / "b", nodes, edges), "word", depth=1, limit=0)
    assert {r.hop for r in one.rows.items} == {1}
    assert len(_run(_site(tmp_path / "c", nodes, edges), "word", starts=3).starts) == 3


def test_a_tight_budget_lowers_detail_then_cuts_the_farthest_things_and_keeps_every_start(
    tmp_path: Path,
) -> None:
    many = [f"t.method::app.Util::m{n}" for n in range(1, 31)]
    nodes = [
        *NODES,
        *(_node(m, "t.method", line=n, file=f"{SRC}/Util.php") for n, m in enumerate(many, 10)),
    ]
    edges = [*EDGES, *(_edge("calls", RULE, m, 7, file=f"{SRC}/TokenRule.php") for m in many)]
    root = _site(tmp_path, nodes, edges)
    full = _run(root, "token", limit=0)
    kept = slicing.BYTE_LIMIT
    try:
        slicing.BYTE_LIMIT = 3000
        report = _run(root, "token")
        tight = _lines(report)
    finally:
        slicing.BYTE_LIMIT = kept

    ids = [r.id for r in report.rows.items]
    assert 0 < len(ids) < len(full.rows.items)
    assert ids == [r.id for r in full.rows.items][: len(ids)]
    for start in ("TokenForm", "TokenCheck", "TokenRule", "token_js", "look_token_alter"):
        assert any(line.startswith("  :") and f"  {start}  " in line for line in tight)
    assert any(line.startswith("inventory: ") for line in tight)
    (cut,) = report.cuts
    assert cut.startswith(
        "cut to fit 3000 bytes: the +N more links lines dropped, at most 1 names per link,"
    )
    assert f"{len(full.rows.items) - len(ids)} things left out, farthest hop first" in cut


def test_json_carries_the_pieces_and_a_piece_per_node(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, "token")))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/slice_piece"}]})
    assert list(validator.iter_errors(document)) == []
    assert [(p["piece"], p["starts"], p["things"]) for p in document["pieces"]] == [
        (1, [CHECK, FORM], 3),
        (2, [RULE], 7),
        (3, [ALTER], 2),
        (4, [SCRIPT], 1),
    ]
    assert {s["id"]: s["piece"] for s in document["starts"]} == {
        CHECK: 1,
        FORM: 1,
        RULE: 2,
        ALTER: 3,
        SCRIPT: 4,
    }
    assert {r["piece"] for r in document["rows"]["items"] if r["id"] in HELPERS} == {2}


def test_json_gives_a_piece_to_a_row_whose_node_the_text_does_not_name(tmp_path: Path) -> None:
    far = [f"t.method::vendor.Lib::f{n}" for n in range(5)]
    nodes = [*NODES, *(_node(f, "t.method", state="unresolved") for f in far)]
    edges = [*EDGES, *(_edge("calls", RULE, f, 8, file=f"{SRC}/TokenRule.php") for f in far)]
    document = json.loads(slicing.render_json(_run(_site(tmp_path, nodes, edges), "token")))

    assert {r["piece"] for r in document["rows"]["items"] if r["id"] in far} == {2}
