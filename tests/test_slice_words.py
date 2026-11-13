"""periplus slice without --out: start from words or ids, print the connected piece as rows.

An invented shop. Edges, files in brackets:

    Checkout -defines-> Checkout::pay [Checkout.php:5]
    Checkout::pay -calls-> Bank::charge (unresolved) [7], -holds-> pay@9 [9],
        -instantiates-> Mailer [8]
    pay@9 -calls-> Mailer::send [9];  Mailer -defines-> Mailer::send [Mailer.php:3]
    Card::charge, mapped, with no edges
    pay::mail@8, whose two edges both join it to Checkout::pay: a satellite of it
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from _navigate import _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate import slice as slicing
from periplus.navigate.source import source_line

SCHEMA = (
    Path(__file__).resolve().parent.parent / "src/periplus/contract/schema/navigation.schema.json"
)

CHECKOUT = "t.class::shop.Checkout"
PAY = "t.method::shop.Checkout::pay"
SITE = "t.site::shop.Checkout::pay@9"
MAILER = "t.class::shop.Mailer"
SEND = "t.method::shop.Mailer::send"
BANK = "t.method::shop.Bank::charge"
CARD = "t.method::shop.Card::charge"
SATELLITE = "t.site::shop.Checkout::pay::mail@8"
CO = "src/Checkout.php"
MA = "src/Mailer.php"

CHECKOUT_PHP = [
    "<?php",
    "namespace shop;",
    "class Checkout {",
    "",
    "  public function pay() {",
    "    $x = 1;",
    "    $this->gateway->charge();",
    "    $m = new Mailer();",
    "    $m->send();",
    "  }",
    "}",
]
MAILER_PHP = ["<?php", "class Mailer {", "  public function send() {}", "}"]

NODES = [
    _node(
        CHECKOUT, "t.class", line=3, file=CO, attributes={"summary": "Takes payment for an order"}
    ),
    _node(PAY, "t.method", line=5, file=CO),
    _node(SITE, "t.site", line=9, file=CO),
    _node(MAILER, "t.class", line=2, file=MA),
    _node(SEND, "t.method", line=3, file=MA),
    _node(BANK, "t.method", state="unresolved"),
    _node(CARD, "t.method", line=1, file="src/Card.php"),
    _node(SATELLITE, "t.site", line=8, file=CO),
]
EDGES = [
    _edge("defines", CHECKOUT, PAY, 5, file=CO),
    _edge("calls", PAY, BANK, 7, file=CO),
    _edge("holds", PAY, SITE, 9, file=CO),
    _edge("instantiates", PAY, MAILER, 8, file=CO),
    _edge("calls", SITE, SEND, 9, file=CO),
    _edge("defines", MAILER, SEND, 3, file=MA),
    _edge("has_site", PAY, SATELLITE, 8, file=CO),
    _edge("site_in", SATELLITE, PAY, 8, file=CO),
]


def _site(root: Path) -> Path:
    (root / ".periplus").mkdir(parents=True)
    (root / "src").mkdir()
    (root / CO).write_text("\n".join(CHECKOUT_PHP) + "\n", encoding="utf-8")
    (root / MA).write_text("\n".join(MAILER_PHP) + "\n", encoding="utf-8")
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "0.1.0"}],
        "roots": ["."],
        "type_hierarchy": [{"type": t, "parent": None} for t in ("t.class", "t.method", "t.site")],
        "nodes": sorted(NODES, key=lambda n: n["id"]),
        "edges": EDGES,
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    (root / ".periplus" / "descriptions.yaml").write_text(
        f"nodes:\n  {PAY}:\n    text: Charges the card and mails a receipt\n"
        f"    file: {CO}\n    line: 5\n",
        encoding="utf-8",
    )
    return root


def _piece(root: Path, *words: str, **kw: Any) -> slicing.SliceReport:
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
    return slicing.run(_site(root), {}, words, **args)


def test_an_id_starts_the_piece_and_each_node_names_its_links(tmp_path: Path) -> None:
    report = _piece(tmp_path, "pay")

    assert report.exit_code is ExitCode.OK
    assert slicing.render_text(report).splitlines() == [
        "periplus slice",
        "start pay  t.method  (given as 'pay')",
        "paths under: src/",
        "",
        "piece 1 of 1: 6 things, starts: pay",
        "",
        "Checkout.php",
        "  :3  Checkout  t.class",
        "      | class Checkout {",
        "      defines -> pay",
        "  :5  pay  t.method",
        "      | public function pay() {",
        "      # Charges the card and mails a receipt",
        "      calls -> (+1 outside the project: Bank::charge)",
        "      holds -> 9",
        "      instantiates -> Mailer",
        "  :9  9  t.site",
        "      | $m->send();",
        "      calls -> send",
        "",
        "Mailer.php",
        "  :2  Mailer  t.class",
        "      | class Mailer {",
        "      defines -> send",
        "      instantiates <- pay",
        "  :3  send  t.method",
        "      | public function send() {}",
        "      calls <- 9",
        "",
        "inventory: 6 nodes",
        "  t.class 2: Checkout, Mailer",
        "  t.site 1: 9",
        "  t.method 3: Bank::charge, pay, send",
        "folded into the node above, all their edges joining it: t.site 1",
        f"warning: resolved 'pay' to {PAY}",
    ]


def test_words_are_searched_as_find_searches_and_say_where_they_matched(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, "takes payment", depth=1))

    assert text.splitlines()[1] == (
        "start Checkout  t.class  (words: 'takes payment' in attribute summary,"
        " 'takes' in attribute summary, 'payment' in attribute summary)"
    )
    assert "      defines -> pay" in text.splitlines()


def test_a_text_that_fails_whole_falls_back_to_its_words_and_says_so(tmp_path: Path) -> None:
    report = _piece(tmp_path, "mail charge")

    assert {query for start in report.starts for query, _, _ in start.words} == {"mail", "charge"}
    assert slicing.render_text(report).splitlines()[1] == (
        "no node matches 'mail charge' as a whole; started from its words"
    )


def test_the_cut_keeps_a_node_several_starts_reach_first(tmp_path: Path) -> None:
    report = _piece(tmp_path, MAILER, PAY, limit=1)

    assert [(row.id, row.again) for row in report.rows.items] == [(SITE, False)]


def test_the_cut_then_keeps_a_node_the_words_match(tmp_path: Path) -> None:
    report = _piece(tmp_path, PAY, "charge", starts=1, limit=1)

    assert [(row.id, row.again) for row in report.rows.items] == [(BANK, False)]


def test_starts_type_and_path_narrow_the_word_matches(tmp_path: Path) -> None:
    assert [s.row.id for s in _piece(tmp_path / "a", "shop", starts=2).starts] == [MAILER, CHECKOUT]
    typed = _piece(tmp_path / "b", "shop", types=("t.method",))
    assert [s.row.id for s in typed.starts] == [SEND, CARD, PAY, BANK]
    placed = _piece(tmp_path / "c", "shop", prefixes=(MA,))
    assert [s.row.id for s in placed.starts] == [MAILER, SEND]


def test_words_that_match_nothing_say_so_and_exit_0(tmp_path: Path) -> None:
    report = _piece(tmp_path, "zzz qqq")

    assert report.exit_code is ExitCode.OK
    assert report.rows.items == ()
    assert slicing.render_text(report).splitlines() == ["periplus slice", "no matches"]


def test_the_row_cap_says_what_it_left_out(tmp_path: Path) -> None:
    report = _piece(tmp_path, "pay", limit=3)
    lines = slicing.render_text(report).splitlines()

    assert [row.id for row in report.rows.items] == [CHECKOUT, SITE, MAILER]
    assert lines[-7:-1] == [
        "folded into the node above, all their edges joining it: t.site 1",
        "showing 3 of 6 rows",
        "left out by hop: 1: 1, 2: 2",
        "left out by kind: calls 2, defines 1",
        "narrow with --kind K (kinds here: calls, defines, holds, instantiates),"
        " --direction out, --direction in or --depth 1",
        "show all with --limit 0",
    ]
    again = _piece(tmp_path / "again", "pay", limit=3)
    assert slicing.render_text(again) == slicing.render_text(report)


def test_a_piece_that_reaches_further_says_how_to_go_deeper(tmp_path: Path) -> None:
    lines = slicing.render_text(_piece(tmp_path, "Checkout", depth=1)).splitlines()

    assert "go deeper with --depth 2" in lines


def test_json_carries_the_same_piece_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, "pay", limit=5)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/slice_piece"}]})
    assert list(validator.iter_errors(document)) == []
    assert document["starts"][0]["id"] == PAY
    assert document["starts"][0]["given"] == "pay"
    assert [
        (r["from"], r["kind"], r["direction"], r["id"], r["again"])
        for r in document["rows"]["items"]
    ][-2:] == [
        (PAY, "instantiates", "out", MAILER, False),
        (SITE, "calls", "out", SEND, False),
    ]
    assert document["left_out"] == {"by_hop": {"2": 1}, "by_kind": {"defines": 1}}


def test_the_cli_prints_the_piece_and_refuses_word_flags_with_out(tmp_path: Path) -> None:
    root = _site(tmp_path)
    printed = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(printed):
        code = main(["slice", "takes", "payment", "--depth", "1"])
    assert code == 0
    assert printed.getvalue().splitlines()[1].startswith("start Checkout  t.class  (words:")

    refused = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(refused):
        code = main(["slice", "pay", "--type", "t.class", "--out", str(tmp_path / "s.json")])
    assert code == ExitCode.USAGE
    assert not (tmp_path / "s.json").exists()


def test_a_source_line_with_under_two_word_characters_is_not_printed() -> None:
    assert (source_line("{#"), source_line("}"), source_line("x = 1")) == (
        [],
        [],
        ["      | x = 1"],
    )


def test_the_cut_takes_full_rows_before_back_references(tmp_path: Path) -> None:
    report = _piece(tmp_path, MAILER, PAY, limit=3)

    assert [(row.id, row.again) for row in report.rows.items] == [
        (SEND, False),
        (CHECKOUT, False),
        (SITE, False),
    ]


def test_the_cut_counts_starts_of_one_word_apart(tmp_path: Path) -> None:
    report = _piece(tmp_path, "shop", starts=2, limit=1)

    assert [(row.id, row.again) for row in report.rows.items] == [(PAY, False)]


def test_the_cut_prefers_a_node_more_other_files_depend_on(tmp_path: Path) -> None:
    report = _piece(tmp_path, "pay", limit=1)

    assert [row.id for row in report.rows.items] == [MAILER]
