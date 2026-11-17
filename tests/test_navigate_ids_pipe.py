"""Ids out with ``--ids`` and ids in with ``-``, so one periplus command reads another's list."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.navigate.ids import read_ids, resolve
from periplus.navigate.mapfile import MapIndex

CAUSES = {"from": ["calls"], "none": ["in_module"]}
SPACED = "perm::access content"
BROKEN = "x::two\nlines"
NODES = [
    _node("x::a", line=1),
    _node("x::b", line=2),
    _node("x::c", line=3),
    _node(SPACED, line=4),
    _node(BROKEN, line=5),
    _node("mod::m", line=6),
    _node("php.method::Drupal\\one\\Foo::run", line=7, file="src/one/Foo.php"),
    _node("php.method::Drupal\\two\\Foo::run", line=8, file="src/two/Foo.php"),
]
EDGES = [
    _edge("calls", "x::a", "x::b", 1),
    _edge("calls", "x::b", "x::c", 2),
    _edge("calls", "x::a", SPACED, 3),
    _edge("calls", "x::a", BROKEN, 4),
    _edge("calls", "x::a", "php.method::Drupal\\one\\Foo::run", 5),
    _edge("calls", "x::a", "php.method::Drupal\\two\\Foo::run", 6),
    *(
        _edge("in_module", i, "mod::m", 7)
        for i in ("x::b", "x::c", "php.method::Drupal\\one\\Foo::run")
    ),
]


def _write(root: Path) -> Path:
    document = _document(NODES, EDGES, CAUSES, grouping_kinds=["in_module"])
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _run(
    capsys: pytest.CaptureFixture[str], *argv: str, stdin: str | None = None
) -> tuple[int, str, str]:
    if stdin is not None:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("sys.stdin", io.StringIO(stdin))
            code = main(list(argv))
    else:
        code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- reading ids ----------------------------------------------------------------------------


def test_a_dash_reads_one_id_a_line_keeping_spaces_and_skipping_empty_lines() -> None:
    stream = io.StringIO(f"x::a\r\n\n{SPACED}\n x::padded \n")

    assert read_ids(["x::c", "-"], stream) == ["x::c", "x::a", SPACED, " x::padded "]


def test_a_command_reads_its_ids_from_standard_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    code, out, _ = _run(capsys, "neighbors", "-", "--ids", "--map", path, stdin="x::b\n")

    assert (code, out) == (0, "x::b\nx::c\n")


def test_show_takes_several_ids_and_prints_each_with_a_separator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "show", "-", "--map", path, stdin="x::b\nx::c\n")
    blocks = out.split("---\n")

    assert [b.splitlines()[0] for b in blocks] == ["periplus show x::b", "periplus show x::c"]


def test_show_of_several_ids_in_json_holds_one_document_each(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "show", "x::b", "x::c", "--format", "json", "--map", path)

    assert [d["id"] for d in json.loads(out)["shown"]] == ["x::b", "x::c"]


def test_show_of_several_ids_exits_with_the_code_of_one_that_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    code, out, _ = _run(capsys, "show", "x::b", "nope", "--map", path)

    assert code == ExitCode.NODE_NOT_FOUND
    assert "periplus show x::b" in out


def test_depth_reads_ids_from_standard_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "depth", "-", "--map", path, stdin="x::b\n")

    assert out.splitlines()[0] == "periplus depth x::b"


def test_a_first_line_names_three_starts_and_counts_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "neighbors", "-", "--map", path, stdin="x::a\nx::b\nx::c\nmod::m\n")

    assert out.splitlines()[0] == "periplus neighbors x::a x::b x::c +1 more"


# --- printing ids ---------------------------------------------------------------------------


def test_ids_prints_one_full_id_a_line_and_the_count_on_standard_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    code, out, err = _run(capsys, "neighbors", "x::b", "--depth", "all", "--ids", "--map", path)

    assert (code, out, err) == (0, "x::b\nx::c\n", "2 ids\n")


def test_ids_of_a_walk_stops_at_its_depth(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "neighbors", "x::a", "--depth", "1", "--ids", "--map", path)

    assert "x::c" not in out.splitlines()


def test_ids_of_find_are_not_cut_by_the_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "find", "x::", "--limit", "1", "--ids", "--map", path)

    assert len(out.splitlines()) == 4


def test_ids_of_show_are_the_other_ends_of_its_edges(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, _ = _run(capsys, "show", "x::b", "--ids", "--map", path)

    assert out == "x::c\nmod::m\nx::a\n"


def test_ids_of_a_raw_walk_are_not_cut_by_the_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    argv = ["neighbors", "x::a", "--raw", "--limit", "1", "--ids", "--map", path]
    _, out, _ = _run(capsys, *argv)

    assert len(out.splitlines()) == 6


def test_ids_with_json_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["find", "x", "--ids", "--format", "json", "--map", str(_write(tmp_path))])
    assert raised.value.code == int(ExitCode.USAGE)


def test_a_problem_goes_to_standard_error_and_nothing_to_standard_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    code, out, err = _run(capsys, "neighbors", "nope", "--ids", "--map", path)

    assert (code, out) == (ExitCode.NODE_NOT_FOUND, "")
    assert "31 no node has the id 'nope'" in err


def test_an_id_holding_a_line_break_prints_escaped_says_so_and_reads_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, err = _run(capsys, "find", "lines", "--ids", "--map", path)

    assert out == "x::two\\nlines\n"
    assert "1 of them hold a control character and print escaped" in err
    _, again, _ = _run(capsys, "count", "-", "--map", path, stdin=out)
    assert again.splitlines()[1] == "1 id given: 1 thing in the map"


def test_an_id_holding_a_backslash_prints_as_it_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(_write(tmp_path))
    _, out, err = _run(capsys, "find", "Foo::run", "--ids", "--map", path)

    assert out.splitlines()[0] == "php.method::Drupal\\one\\Foo::run"
    assert err == "2 ids\n"


# --- names that go back ---------------------------------------------------------------------


def _names(text: str) -> list[str]:
    """The first column of each row a list prints: indented, two spaces between columns."""
    return [line.strip().split("  ")[0] for line in text.splitlines() if line.startswith("  ")]


@pytest.mark.parametrize(
    ("argv", "unlisted"),
    [
        (["neighbors", "x::a", "--depth", "all"], {"x::a"}),
        (["only", "x::a"], set()),
        (["members", "mod::m"], set()),
        (["pieces", "x::a", "x::b", "x::c", SPACED, "php.method::Drupal\\one\\Foo::run"], set()),
    ],
)
def test_every_name_a_list_prints_resolves_back_to_the_id_it_lists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], unlisted: set[str]
) -> None:
    """``unlisted`` are the ids ``--ids`` prints that the text prints as no indented row: the
    start of a walk heads the tree unindented."""
    path = _write(tmp_path)
    index = MapIndex(json.loads(path.read_text(encoding="utf-8")))
    _, text, _ = _run(capsys, *argv, "--map", str(path))
    _, ids, _ = _run(capsys, *argv, "--ids", "--map", str(path))
    names = [n for n in _names(text) if n]

    assert sorted(resolve(index, name)[0] for name in names) == sorted(
        resolve(index, i)[0] for i in ids.splitlines() if i and i not in unlisted
    )
