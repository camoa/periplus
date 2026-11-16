"""``periplus undescribed``: the main things the descriptions file does not describe."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import undescribed

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

NODES = [
    _node("mod::m", "t.module", line=1, file="m/m.info"),
    _node("cls::C", "t.class", line=3, file="m/C.php"),
    _node("meth::C::run", "t.method", line=10, file="m/C.php"),
    _node("par::C::run::$x", "t.param", line=10, file="m/C.php"),
    _node("call::C::run::go", "t.call", line=12, file="m/C.php"),
    _node("meth::C::go", "t.method", line=20, file="m/C.php"),
    _node("par::C::go::$y", "t.param", line=20, file="m/C.php"),
    _node("meth::C::idle", "t.method", line=30, file="m/C.php"),
    _node("fn::helper", "t.function", line=5, file="m/a.php"),
    _node("fn::lost", "t.function", "unresolved"),
    _node("fn::far", "t.function", "boundary", line=2, file="m/a.php"),
    _node("cls::T", "t.class", line=1, file="tests/T.php"),
]
DESCRIBED = """\
nodes:
  cls::C:
    text: The cart.
    file: m/C.php
    line: 3
  fn::helper:
    text: Adds one.
    file: m/a.php
    line: 5
  par::C::run::$x:
    text: A part, described all the same.
    file: m/C.php
    line: 10
  gone::x:
    text: Not in the map.
    file: m/old.php
    line: 1
"""


def _write(root: Path, described: str = DESCRIBED) -> Path:
    document = _document(
        NODES[::-1],
        [_edge("class_in_module", "cls::C", "mod::m", 3)],
        grouping_kinds=["class_in_module"],
        supporting_paths=["tests/**"],
    )
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    (root / "descriptions.yaml").write_text(described, encoding="utf-8")
    return path


def test_the_whole_map_counts_main_things_by_file(tmp_path: Path) -> None:
    report = undescribed.run(tmp_path, {}, [], "file", _write(tmp_path))

    assert undescribed.render_text(report).splitlines() == [
        "periplus undescribed",
        "described 2 of 6 main things; 4 undescribed",
        "left out: 3 parts (t.param 2, t.call 1), 1 in supporting code, "
        "2 not mapped or with no location",
        "part types: t.param 100%, t.call 100%; count them too with --parts-too",
        "by file:",
        "  3  m/C.php",
        "  1  m/m.info",
    ]


def test_a_type_is_a_part_type_when_most_of_its_things_nest_and_hold_nothing(
    tmp_path: Path,
) -> None:
    report = undescribed.run(tmp_path, {}, [], "type", _write(tmp_path))

    assert dict(report.parts) == {"t.call": 1, "t.param": 2}
    assert report.counts == (("t.method", 3), ("t.module", 1))


def test_by_container_counts_under_the_container_of_what_holds_a_thing(tmp_path: Path) -> None:
    report = undescribed.run(tmp_path, {}, [], "container", _write(tmp_path))

    assert undescribed.render_text(report).splitlines()[4:] == [
        "by container:",
        "  3  m",
        "  1  (no container)",
    ]


def test_ids_list_the_undescribed_by_place(tmp_path: Path) -> None:
    report = undescribed.run(tmp_path, {}, [], "file", _write(tmp_path))

    assert undescribed.listed(report) == ("meth::C::run", "meth::C::go", "meth::C::idle", "mod::m")


def test_given_ids_count_only_those(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("cls::C\nmeth::C::go\npar::C::go::$y\n"))

    assert main(["undescribed", "-", "--map", str(path)]) == 0
    assert capsys.readouterr().out.splitlines()[1:3] == [
        "described 1 of 2 main things; 1 undescribed",
        "left out: 1 parts (t.param 1)",
    ]


def test_without_a_descriptions_file_nothing_is_described(tmp_path: Path) -> None:
    path = _write(tmp_path)
    (tmp_path / "descriptions.yaml").unlink()

    report = undescribed.run(tmp_path, {}, [], "file", path)

    assert (report.described, report.main) == (0, 6)


def test_a_descriptions_file_that_breaks_the_schema_exits_30(tmp_path: Path) -> None:
    report = undescribed.run(tmp_path, {}, [], "file", _write(tmp_path, "nodes: [1]\n"))

    assert report.exit_code == 30


def test_the_json_matches_the_schema(tmp_path: Path) -> None:
    text = undescribed.render_json(undescribed.run(tmp_path, {}, [], "container", _write(tmp_path)))

    assert (
        list(Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(json.loads(text)))
        == []
    )
    assert json.loads(text)["counts"] == [{"key": "mod::m", "count": 3}, {"key": None, "count": 1}]
