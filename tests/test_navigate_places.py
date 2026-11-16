"""``periplus in``, ``periplus at`` and ``periplus files``: from a file to the map and back."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import at, files, inside

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

NODES = [
    _node("mod::m", "t.module", line=1, file="m/m.info"),
    _node("cls::C", "t.class", line=3, file="m/C.php"),
    _node("meth::C::run", "t.method", line=10, file="m/C.php"),
    _node("par::C::run::$x", "t.param", line=10, file="m/C.php"),
    _node("call::C::run::go", "t.call", line=12, file="m/C.php"),
    _node("call::C::run::$f", "t.call", "unknown_boundary", line=14, file="m/C.php"),
    _node("meth::C::go", "t.method", line=20, file="m/C.php"),
    _node("fn::helper", "t.function", line=5, file="m/a.php"),
    _node("fn::lost", "t.function", "unresolved"),
    _node("fn::late", "t.function", line=9, file="m/z.php"),
    _node("fn::later", "t.function", line=7, file="m/z.php"),
]
EDGES = [
    _edge("class_in_module", "cls::C", "mod::m", 3),
    _edge("calls", "call::C::run::go", "meth::C::go", 12),
]


def _write(root: Path) -> Path:
    # Listed backward, so no order below comes from the map's own.
    document = _document(
        NODES[::-1],
        EDGES,
        grouping_kinds=["class_in_module"],
        type_hierarchy=[{"type": "t.method", "parent": None}, {"type": "t.class", "parent": None}],
    )
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _valid(text: str) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(json.loads(text))) == []


# periplus in


def test_in_lists_a_files_things_in_line_order(tmp_path: Path) -> None:
    report = inside.run(tmp_path, {}, ["m/C.php"], [], _write(tmp_path))

    assert inside.render_text(report).splitlines() == [
        "periplus in",
        "m/C.php: 6 things",
        "  C  t.class  mapped  :3",
        "  run  t.method  mapped  :10",
        "  x  t.param  mapped  :10",
        "  run::go  t.call  mapped  :12",
        "  f  t.call  unknown_boundary  :14",
        "  C::go  t.method  mapped  :20",
    ]


def test_in_keeps_one_type_and_its_subtypes(tmp_path: Path) -> None:
    report = inside.run(tmp_path, {}, ["./m/C.php"], ["t.method"], _write(tmp_path))

    assert inside.listed(report) == ("meth::C::run", "meth::C::go")


def test_in_says_a_file_holds_nothing(tmp_path: Path) -> None:
    report = inside.run(tmp_path, {}, ["m/none.php"], [], _write(tmp_path))

    assert report.exit_code == 0
    assert inside.render_text(report).splitlines()[1] == "m/none.php: nothing mapped"


def test_in_json_matches_the_schema(tmp_path: Path) -> None:
    text = inside.render_json(inside.run(tmp_path, {}, ["m/a.php"], [], _write(tmp_path)))

    _valid(text)
    assert json.loads(text)["files"][0]["things"][0]["location"] == "m/a.php:5"


def test_in_prints_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path)

    assert main(["in", "m/a.php", "m/m.info", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out == "fn::helper\nmod::m\n"


# periplus at


def test_at_gives_the_thing_nearest_above_then_what_holds_it(tmp_path: Path) -> None:
    report = at.run(tmp_path, {}, [("m/C.php", 15)], _write(tmp_path))

    assert at.render_text(report).splitlines() == [
        "periplus at",
        "m/C.php:15  nearest above: :12",
        "  run::go  t.call  mapped  :12",
        "  in run  t.method  mapped  :10",
        "  in C  t.class  mapped  :3",
        "  in m  t.module  mapped  m/m.info:1",
    ]


def test_at_a_line_with_two_things_puts_the_inner_one_first(tmp_path: Path) -> None:
    report = at.run(tmp_path, {}, [("m/C.php", 10)], _write(tmp_path))

    assert at.listed(report) == ("par::C::run::$x", "meth::C::run", "cls::C", "mod::m")
    assert at.render_text(report).splitlines()[1] == "m/C.php:10"


def test_at_says_when_nothing_is_at_or_above_the_line(tmp_path: Path) -> None:
    report = at.run(tmp_path, {}, [("m/C.php", 2), ("./m/none.php", 4)], _write(tmp_path))

    assert at.render_text(report).splitlines()[1:] == [
        "m/C.php:2  nothing mapped at or above this line",
        "m/none.php:4  nothing mapped in this file",
    ]


def test_at_json_matches_the_schema(tmp_path: Path) -> None:
    text = at.render_json(at.run(tmp_path, {}, [("m/C.php", 15)], _write(tmp_path)))

    _valid(text)
    first = json.loads(text)["places"][0]
    assert (first["found_line"], [c["id"] for c in first["containers"]]) == (
        12,
        ["meth::C::run", "cls::C", "mod::m"],
    )


def test_at_without_a_line_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as refused:
        main(["at", "m/C.php", "--map", str(_write(tmp_path))])

    assert refused.value.code == 2


# periplus files


def test_files_counts_the_set_by_file_most_first(tmp_path: Path) -> None:
    ids = ["meth::C::run", "cls::C", "fn::helper", "fn::lost", "mod::m", "meth::C::go"]
    report = files.run(tmp_path, {}, ids, _write(tmp_path))

    assert files.render_text(report).splitlines() == [
        "periplus files",
        "6 things in 3 files",
        "  3  m/C.php",
        "  1  m/a.php",
        "  1  m/m.info",
        "no location: 1",
    ]


def test_files_puts_the_file_with_most_first_whatever_its_name(tmp_path: Path) -> None:
    report = files.run(tmp_path, {}, ["cls::C", "fn::late", "fn::later"], _write(tmp_path))

    assert report.files == (("m/z.php", 2), ("m/C.php", 1))


def test_files_reads_ids_from_standard_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("fn::helper\ncls::C\n"))

    assert main(["files", "-", "--format", "json", "--map", str(path)]) == 0
    text = capsys.readouterr().out
    _valid(text)
    assert json.loads(text)["files"] == [
        {"file": "m/C.php", "count": 1},
        {"file": "m/a.php", "count": 1},
    ]
