"""A name several ids end in: the one main thing among them is meant; the refusal prints the
name as rows print an id."""

from __future__ import annotations

import json
from pathlib import Path

from _navigate import _node

from periplus.errors import ExitCode
from periplus.navigate import show, slice

BILLING = "php.type::Acme\\Billing\\Account"
USER = "php.type::Acme\\User\\Account"
OLD = "php.type::Old\\Billing\\Account"
TYPED = "php.parameter_type::Acme\\Billing\\Invoicer::$account::Acme\\Billing\\Account"
CHARGE = "php.parameter::Acme\\Billing\\Invoicer::charge::$account"
REFUND = "php.parameter::Acme\\Billing\\Invoicer::refund::$account"


def _root(root: Path, *extra: str) -> Path:
    """A project whose map holds the two account classes, the parts and the ``extra`` classes."""
    (root / ".periplus").mkdir()
    nodes = [_node(i, "php.class", line=4) for i in (BILLING, USER, *extra)]
    nodes += [_node(TYPED, "php.parameter_type", line=7)]
    nodes += [_node(i, "php.parameter", line=7) for i in (CHARGE, REFUND)]
    document = {
        "periplus_map_version": 0,
        "packs": [{"pack": "php", "version": "0.1.0"}],
        "roots": ["."],
        "part_types": {"php.parameter": 100, "php.parameter_type": 100},
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": [],
    }
    (root / ".periplus" / "map.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def test_the_refusal_prints_the_name_as_rows_print_an_id(tmp_path: Path) -> None:
    report = show.run(_root(tmp_path, OLD), {}, "Billing\\Account", 50, None)

    assert report.exit_code == ExitCode.NODE_NOT_FOUND
    assert report.problems[0].message == "'Billing\\Account' matches 3 nodes; give one of these ids"
    assert show.render_text(report).splitlines()[1:3] == [
        "31 'Billing\\\\Account' matches 3 nodes; give one of these ids",
        f"  {TYPED}  php.parameter_type  src/a.php:7".replace("\\", "\\\\"),
    ]


def test_the_one_main_thing_a_name_matches_is_meant(tmp_path: Path) -> None:
    report = show.run(_root(tmp_path), {}, "Acme\\Billing\\Account", 50, None)

    assert (report.id, report.problems) == (BILLING, ())
    assert [w.startswith("resolved ") and w.endswith(BILLING) for w in report.warnings] == [True]


def test_several_main_things_or_only_parts_are_refused_with_every_candidate(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)

    for name, candidates in (
        ("Account", [CHARGE, REFUND, TYPED, BILLING, USER]),
        ("$account", [CHARGE, REFUND]),
    ):
        problem = show.run(root, {}, name, 50, None).problems[0]
        assert problem.code == ExitCode.NODE_NOT_FOUND
        assert [c["id"] for c in problem.detail["candidates"]] == candidates


def test_slice_takes_the_main_thing_from_from_and_still_searches_a_word(tmp_path: Path) -> None:
    root, name = _root(tmp_path), "Acme\\Billing\\Account"

    picked = slice.run(root, {}, (), [], depth=0, from_ids=[name]).starts
    searched = slice.run(root, {}, [name], [], depth=0).starts

    assert [s.row.id for s in picked] == [BILLING]
    assert {BILLING, TYPED} <= {s.row.id for s in searched}


def test_the_resolved_warning_prints_the_name_as_rows_print_an_id(tmp_path: Path) -> None:
    report = show.run(_root(tmp_path), {}, "Acme\\Billing\\Account", 50, None)

    assert show.render_text(report).splitlines()[-1] == (
        f"warning: resolved 'Acme\\Billing\\Account' to {BILLING}".replace("\\", "\\\\")
    )
