"""Where ``slice`` cuts, counts instead of listing, or drops rows, it names the small command that
prints that part in full; ``slice --from`` takes ids as starts and searches no words."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from test_slice_dense import ADD, CART, DEEP, SEND, TOTAL, _piece, _site, _text

from periplus.cli import main
from periplus.navigate import slice as slicing
from periplus.navigate import walk

IN_FULL = "in full, each part this slice holds:"


def test_a_node_with_links_left_unwalked_names_show(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD, depth=1))

    assert "      +1 more link: calls -> 1; see periplus show send --limit 0" in lines


def test_a_node_whose_links_are_cut_short_names_show(tmp_path: Path) -> None:
    # Cart is a start too, so every edge of add is in the slice and only the folds cut its links.
    lines = _text(_piece(tmp_path, CART, ADD))
    at = lines.index("  :4  add  t.method")
    block = lines[at : at + 5]

    assert "      calls -> Mailer (3), total (+2 outside the project: dump, write)" in block
    assert "      all links: periplus show add --limit 0" in block


def test_a_cap_names_the_walk_commands_at_the_slice_depth(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, ADD, depth=2, limit=3))

    at = lines.index(IN_FULL)
    assert lines[at + 1 : at + 3] == [
        "  sets off: periplus neighbors add --depth 2 --limit 0",
        "  set off by: periplus affected add --depth 2 --limit 0",
    ]


def test_the_in_full_commands_print_every_thing_the_cap_left_out(tmp_path: Path) -> None:
    cut = _piece(tmp_path, ADD, depth=2, limit=3)
    printed = {
        i
        for toward in ("off", "by")
        for i in walk.listed(walk.run_cause(tmp_path, {}, [ADD], toward, 2, (), 0, None))
    }

    assert cut.rows.truncated
    assert set(cut.held) == printed


def test_more_than_three_starts_name_dash_and_say_which_ids(tmp_path: Path) -> None:
    report = slicing.run(
        _site(tmp_path),
        {},
        (),
        (),
        "both",
        2,
        (),
        1,
        None,
        None,
        from_ids=[ADD, TOTAL, SEND, DEEP],
    )
    lines = _text(report)

    at = lines.index(IN_FULL)
    assert lines[at + 1] == (
        "  sets off: periplus neighbors - --depth 2 --limit 0 (pipe in the 4 starts above)"
    )


def test_starts_read_from_standard_input_say_the_same_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _site(tmp_path)
    monkeypatch.chdir(site)
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{ADD}\n"))

    assert main(["slice", "--from", "-", "--limit", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "  sets off: periplus neighbors - --depth 2 --limit 0 (with the same ids piped in)" in (
        lines
    )


def test_from_starts_at_the_ids_alone_and_searches_no_words(tmp_path: Path) -> None:
    # As words, "Cart" also finds what holds the word: total and add's other methods.
    searched = _piece(tmp_path, "Cart", "add")
    site = _site(tmp_path / "b")
    given = slicing.run(
        site, {}, (), (), "both", None, (), None, None, None, from_ids=["Cart", "add"]
    )

    assert [s.row.id for s in given.starts] == [CART, ADD]
    assert TOTAL in [s.row.id for s in searched.starts]


def test_from_an_id_that_names_nothing_exits_31(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_site(tmp_path))

    assert main(["slice", "--from", "nope"]) == 31
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["slice", "add", "--from", "total"])


def test_the_starts_the_cap_dropped_name_find(tmp_path: Path) -> None:
    # "mail" finds Mailer and its three methods.
    lines = _text(_piece(tmp_path, "mail", starts=2))
    dropped = [line for line in lines if line.startswith("+") and "match the words" in line]

    assert dropped == [
        "+2 more nodes match the words: periplus find WORD --limit 0 for each of: mail;"
        " start from any with periplus slice --from ID"
    ]
    assert not any("match the words" in line for line in _text(_piece(tmp_path / "b", "mail")))


def test_the_byte_budget_names_show_and_legend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(slicing, "BYTE_LIMIT", 700)
    lines = _text(_piece(tmp_path, ADD))
    note = next(line for line in lines if line.startswith("cut to fit 700 bytes"))

    assert note.endswith("a node's links in full: periplus show NAME --limit 0")


def test_a_piece_with_nothing_cut_prints_no_in_full_lines(tmp_path: Path) -> None:
    lines = _text(_piece(tmp_path, "t.method::shop.Far::deeper"))

    assert not any(line.startswith("in full") for line in lines)


def test_supporting_code_left_out_alone_prints_the_in_full_lines(tmp_path: Path) -> None:
    from test_navigate_supporting import RUN as RUNNER
    from test_navigate_supporting import _piece as supporting_piece

    report = supporting_piece(tmp_path, RUNNER)
    lines = _text(report)

    assert not report.rows.truncated
    assert IN_FULL in lines
