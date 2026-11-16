"""The compact rows of the walks by cause: short names where unique, a file named once for rows
that follow each other in it, and ``--full`` for full ids and paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _document, _edge, _node

from periplus.cli import main
from periplus.navigate import walk

CAUSES = {"from": ["calls"]}

# s calls a (written in one.php), a calls b (one.php) and c (two.php); c calls d (no place);
# d calls e (two.php). Two nodes share the name "dup".
EDGES = [
    _edge("calls", "x::s", "x::a", 1, file="one.php"),
    _edge("calls", "x::a", "x::b", 2, file="one.php"),
    _edge("calls", "x::a", "y::dup", 3, file="two.php"),
    _edge("calls", "y::dup", "x::d", None),
    _edge("calls", "x::d", "x::e", 5, file="two.php"),
]
NODES = [
    _node("x::s", line=1, file="one.php"),
    _node("x::a", line=1, file="one.php"),
    _node("x::b", line=1, file="one.php"),
    _node("y::dup", line=1, file="two.php"),
    _node("z::dup", line=1, file="two.php"),
    _node("x::d"),
    _node("x::e", line=1, file="two.php"),
]


def _write(root: Path) -> Path:
    path = root / "map.json"
    path.write_text(json.dumps(_document(NODES, EDGES, CAUSES)), encoding="utf-8")
    return path


def _rows(root: Path, **options: Any) -> list[str]:
    report = walk.run_cause(root, {}, ["x::s"], "off", None, [], None, _write(root), **options)
    return walk.render_text(report).splitlines()[2:]


def test_a_row_prints_the_short_name_where_it_is_unique(tmp_path: Path) -> None:
    assert _rows(tmp_path)[1].startswith("  a  t.x  ")


def test_a_row_prints_the_full_id_where_the_short_name_fits_several(tmp_path: Path) -> None:
    assert _rows(tmp_path)[3].startswith("    y::dup  t.x  ")


def test_a_row_in_the_file_of_the_row_above_prints_only_its_line(tmp_path: Path) -> None:
    assert _rows(tmp_path)[2] == "    b  t.x  mapped  calls  :2"


def test_a_row_in_another_file_prints_the_path(tmp_path: Path) -> None:
    assert _rows(tmp_path)[3] == "    y::dup  t.x  mapped  calls  two.php:3"


def test_a_row_after_one_with_no_location_prints_the_path(tmp_path: Path) -> None:
    assert _rows(tmp_path)[4:] == [
        "      d  t.x  mapped  calls  no location",
        "        e  t.x  mapped  calls  two.php:5",
    ]


def test_full_prints_full_ids_and_paths(tmp_path: Path) -> None:
    assert _rows(tmp_path, full=True)[1:3] == [
        "  x::a  t.x  mapped  calls  one.php:1",
        "    x::b  t.x  mapped  calls  one.php:2",
    ]


def test_the_json_carries_full_ids_and_paths(tmp_path: Path) -> None:
    report = walk.run_cause(tmp_path, {}, ["x::s"], "off", None, [], None, _write(tmp_path))
    row = json.loads(walk.render_json(report))["rows"][1]

    assert (row["id"], row["file"], row["line"]) == ("x::b", "one.php", 2)


def test_the_command_line_takes_full(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path)

    assert main(["neighbors", "x::s", "--full", "--map", str(path)]) == 0
    assert "  x::a  t.x  mapped  calls  one.php:1" in capsys.readouterr().out.splitlines()
