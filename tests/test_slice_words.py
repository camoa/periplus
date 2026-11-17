"""periplus slice without --out: start from words or ids, print what the walks by cause reach.

An invented shop. Edges, files in brackets; `defines`, `has_site` and `site_in` are structure,
the other kinds set off their to end:

    Checkout -defines-> Checkout::pay [Checkout.php:5]
    Checkout::pay -calls-> Bank::charge (unresolved) [7], -holds-> pay@9 [9],
        -instantiates-> Mailer [8]
    pay@9 -calls-> Mailer::send [9];  Mailer -defines-> Mailer::send [Mailer.php:3]
    Card::charge, mapped, with no edges
    pay::mail@8, joined to Checkout::pay by structure alone
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
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
        "cause_from_kinds": ["calls", "holds", "instantiates"],
        "cause_none_kinds": ["defines", "has_site", "site_in"],
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


def test_an_id_starts_the_slice_and_each_thing_names_its_links(tmp_path: Path) -> None:
    report = _piece(tmp_path, "pay")

    assert report.exit_code is ExitCode.OK
    assert slicing.render_text(report).splitlines() == [
        "periplus slice",
        "start pay  t.method  (given as 'pay')",
        "sets off:     2 hops, 4 things; 0 hubs stopped",
        "set off by:   0 hops, 0 things; 0 hubs stopped",
        "paths under: src/",
        "",
        "piece 1 of 1: 5 things, starts: pay",
        "",
        "Checkout.php",
        "  :5  pay  t.method",
        "      | public function pay() {",
        "      # Charges the card and mails a receipt",
        "      calls -> (+1 outside the project: Bank::charge)",
        "      holds -> 9",
        "      instantiates -> Mailer",
        "      +3 more links: defines <- 1, has_site -> 1, site_in <- 1;"
        " see periplus show pay --limit 0",
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
        "inventory: 5 nodes",
        "  t.class 1: Mailer",
        "  t.site 1: 9",
        "  t.method 3: Bank::charge, pay, send",
        f"warning: resolved 'pay' to {PAY}",
    ]


def test_words_are_searched_as_find_searches_and_say_where_they_matched(tmp_path: Path) -> None:
    text = slicing.render_text(_piece(tmp_path, "takes payment", depth=1))

    assert text.splitlines()[1] == (
        "start Checkout  t.class  (words: 'takes payment' in attribute summary,"
        " 'takes' in attribute summary, 'payment' in attribute summary)"
    )
    assert "      +1 more link: defines -> 1; see periplus show Checkout --limit 0" in (
        text.splitlines()
    )


def test_a_text_that_fails_whole_falls_back_to_its_words_and_says_so(tmp_path: Path) -> None:
    report = _piece(tmp_path, "mail charge")

    assert {query for start in report.starts for query, _, _ in start.words} == {"mail", "charge"}
    assert slicing.render_text(report).splitlines()[1] == (
        "no node matches 'mail charge' as a whole; started from its words"
    )


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


def test_the_cap_leaves_out_the_farthest_hop_first_and_says_what_it_left_out(
    tmp_path: Path,
) -> None:
    report = _piece(tmp_path, "pay", limit=2)
    lines = slicing.render_text(report).splitlines()

    assert [row.id for row in report.rows.items] == [MAILER, BANK]
    assert lines[-8:-1] == [
        "showing 2 of 4 things past the starts",
        "left out by hop: 1: 1, 2: 1",
        "left out by kind: calls 1, holds 1",
        "narrow with --kind K (kinds here: calls, holds, instantiates),"
        " --direction off, --direction by or --depth 1",
        "in full, each part this slice holds:",
        "  sets off: periplus neighbors pay --depth all --limit 0",
        "  set off by: periplus affected pay --depth all --limit 0",
    ]
    again = _piece(tmp_path / "again", "pay", limit=2)
    assert slicing.render_text(again) == slicing.render_text(report)


def test_a_walk_past_the_depth_names_the_command_that_prints_it_all(tmp_path: Path) -> None:
    lines = slicing.render_text(_piece(tmp_path, "pay", depth=1)).splitlines()

    assert lines[2] == (
        "sets off:     2 hops, 4 things; 0 hubs stopped; this slice holds hop 1: 3;"
        " all: periplus neighbors pay --depth all --limit 0"
    )
    assert "set off by:   0 hops, 0 things; 0 hubs stopped" in lines


def test_json_carries_the_same_slice_and_fits_the_schema(tmp_path: Path) -> None:
    document = json.loads(slicing.render_json(_piece(tmp_path, "pay", limit=3)))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/slice_piece"}]})
    assert list(validator.iter_errors(document)) == []
    assert document["starts"][0]["id"] == PAY
    assert document["starts"][0]["given"] == "pay"
    assert [
        (r["from"], r["kind"], r["direction"], r["walk"], r["id"], r["hop"])
        for r in document["rows"]["items"]
    ] == [
        (PAY, "instantiates", "out", "off", MAILER, 1),
        (PAY, "calls", "out", "off", BANK, 1),
        (PAY, "holds", "out", "off", SITE, 1),
    ]
    assert document["left_out"] == {"by_hop": {"2": 1}, "by_kind": {"calls": 1}}
    assert document["held"] == 5
    assert [(w["direction"], w["total"], w["held"]) for w in document["walks"]] == [
        ("off", 4, 4),
        ("by", 0, 0),
    ]


def test_the_cli_prints_the_slice_and_writes_one_from_words(tmp_path: Path) -> None:
    root = _site(tmp_path)
    printed = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(printed):
        code = main(["slice", "takes", "payment", "--depth", "1"])
    assert code == 0
    assert printed.getvalue().splitlines()[1].startswith("start Checkout  t.class  (words:")

    with contextlib.chdir(root), contextlib.redirect_stdout(io.StringIO()):
        code = main(["slice", "pay", "--type", "t.method", "--out", str(tmp_path / "s.json")])
    assert code == 0
    written = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert sorted(n["id"] for n in written["nodes"]) == sorted([PAY, MAILER, BANK, SITE, SEND])


def test_a_raw_direction_exits_2_and_names_the_values_that_replace_it(tmp_path: Path) -> None:
    root = _site(tmp_path)
    said = io.StringIO()
    with (
        contextlib.chdir(root),
        contextlib.redirect_stderr(said),
        pytest.raises(SystemExit) as stopped,
    ):
        main(["slice", "pay", "--direction", "out"])

    assert stopped.value.code == ExitCode.USAGE
    assert "--direction off for what the starts set off, by for what sets them off" in (
        said.getvalue()
    )


def test_a_source_line_with_under_two_word_characters_is_not_printed() -> None:
    assert (source_line("{#"), source_line("}"), source_line("x = 1")) == (
        [],
        [],
        ["      | x = 1"],
    )
