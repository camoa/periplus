"""``periplus find``: main things before parts, words, counts first, and the budget that folds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _find_site import FORM, LOGIN, RECORD, SUBMIT, site

from periplus.cli import FIND_BUDGET, main
from periplus.navigate import find
from periplus.navigate.nesting import Places

PARTS = ["call::Login::form::render", "call::Login::submit::lock", "par::Login::submit::$name"]
MAIN = [LOGIN, FORM, SUBMIT, RECORD]
EVERY = [*MAIN, *PARTS, "fn::login_check", "cls::LoginTest"]


def _ids(report: find.FindReport) -> list[str]:
    return [row.id for row in report.matches.items]


def test_main_things_come_first_then_parts_then_the_rest(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "login", (), 0, site(tmp_path))

    # Inside each group as before: the name, then the id, then a description alone; then by id.
    assert _ids(report) == EVERY
    assert [row.group for row in report.matches.items] == (
        ["main"] * 4 + ["part"] * 3 + ["unplaced", "supporting"]
    )
    assert find.run(tmp_path, {}, "login", (), 0, tmp_path / "map.json") == report


def test_the_main_rule_is_the_one_undescribed_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Places, "why_not_main", lambda self, node_id: None)

    report = find.run(tmp_path, {}, "login", (), 0, site(tmp_path))

    assert {row.group for row in report.matches.items} == {"main"}


def test_several_words_must_each_match_the_name_or_the_description(tmp_path: Path) -> None:
    path = site(tmp_path)

    assert _ids(find.run(tmp_path, {}, "login blocks", (), 0, path)) == [SUBMIT]
    assert set(_ids(find.run(tmp_path, {}, "login blocks", (), 0, path, any_word=True))) == set(
        EVERY
    )


def test_with_any_word_the_rarest_word_ranks_first(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "login record", (), 0, site(tmp_path), any_word=True)

    # "record" matches two things, "login" nine: a name holding "record" outranks one holding
    # only "login", although "login" was typed first.
    assert _ids(report)[:2] == [RECORD, LOGIN]


def test_every_word_in_the_name_beats_a_closer_name_with_a_word_only_described(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Places, "why_not_main", lambda self, node_id: None)

    report = find.run(tmp_path, {}, "record write", (), 0, site(tmp_path))

    # The method's name is "record" but "write" is only in its description; the call site's id
    # holds both words.
    assert _ids(report) == ["call::Audit::record::write", RECORD]


def test_the_first_line_counts_the_matches_by_group_and_then_by_type(tmp_path: Path) -> None:
    lines = find.render_text(find.run(tmp_path, {}, "login", (), 0, site(tmp_path))).splitlines()

    assert lines[:4] == [
        "periplus find: 9 things (4 main, 3 parts, 1 in supporting code, "
        "1 not mapped or with no location), 0 edges",
        "main by type: t.method 3, t.class 1",
        "not main by type: t.call 2, t.class 1, t.function 1, t.param 1",
        "",
    ]
    assert "not main:" in lines


def test_over_the_budget_the_parts_fold_into_counts_before_a_row_is_cut(tmp_path: Path) -> None:
    path = site(tmp_path)
    whole = find.render_text(find.run(tmp_path, {}, "login", (), 0, path))
    report = find.run(tmp_path, {}, "login", (), len(whole) - 1, path)

    text = find.render_text(report)

    assert len(text) <= len(whole) - 1
    rows = [line.split("  ")[0] for line in text.splitlines()]
    assert all(i in rows for i in MAIN)
    assert not any(i in rows for i in PARTS)
    assert "showing" not in text
    assert "not main, not listed: 5" in text
    assert "  by container: shop 3, (no container) 2" in text
    assert f"  list them: periplus find login --parts --map {path}" in text


def test_when_counts_do_not_fit_the_main_rows_are_cut_and_the_line_says_so(
    tmp_path: Path,
) -> None:
    path = site(tmp_path)
    text = find.render_text(find.run(tmp_path, {}, "login", (), 10, path))

    rows = [line.split("  ")[0] for line in text.splitlines()]
    assert LOGIN in rows
    assert FORM not in rows
    assert f"showing 1 of 4 main things; all: periplus find login --limit 0 --map {path}" in text


def test_parts_lists_only_what_is_not_main_and_never_folds(tmp_path: Path) -> None:
    path = site(tmp_path)
    report = find.run(tmp_path, {}, "login", (), 0, path, parts=True)

    assert _ids(report) == [*PARTS, "fn::login_check", "cls::LoginTest"]
    tight = find.render_text(find.run(tmp_path, {}, "login", (), 10, path, parts=True))
    assert "not listed" not in tight
    assert "showing 1 of 5 things" in tight


def test_a_type_never_folds_its_rows(tmp_path: Path) -> None:
    text = find.render_text(find.run(tmp_path, {}, "login", ("t.call",), 10, site(tmp_path)))

    assert "not listed" not in text
    assert "showing 1 of 2 things" in text


def test_json_lists_every_match_whatever_the_budget(tmp_path: Path) -> None:
    document = json.loads(find.render_json(find.run(tmp_path, {}, "login", (), 10, site(tmp_path))))

    assert [item["id"] for item in document["items"]] == EVERY
    assert document["items"][4]["group"] == "part"
    assert (document["total"], document["shown"], document["truncated"]) == (9, 9, False)


def test_ids_print_every_thing_past_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = site(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["find", "login", "--limit", "10", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out.splitlines() == EVERY


def test_the_cli_budget_is_finds() -> None:
    assert FIND_BUDGET == find.BUDGET
