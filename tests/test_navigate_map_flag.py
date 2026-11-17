"""A command a navigation message suggests carries ``--map PATH`` when the run was given one, and
none when the map is the default one."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _navigate import _document, _node

from periplus.navigate import find, show


def _write(path: Path, **header: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _document([_node("t.x::a", line=1)], [], **header)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _show_lines(root: Path, map_path: Path | None) -> list[str]:
    return show.render_text(show.run(root, {}, "nope", 0, map_path)).splitlines()


def test_an_unknown_id_suggests_find_with_the_map_given(tmp_path: Path) -> None:
    given = _write(tmp_path / "other" / "m.json")
    lines = _show_lines(tmp_path, given)

    assert any(f"periplus find --map {given} searches the ids" in line for line in lines)
    assert f"  hint: run periplus find nope --map {given}" in lines


def test_an_unknown_id_suggests_find_alone_on_the_default_map(tmp_path: Path) -> None:
    _write(tmp_path / ".periplus" / "map.json")
    lines = _show_lines(tmp_path, None)

    assert any("periplus find searches the ids" in line for line in lines)
    assert "  hint: run periplus find nope" in lines


def test_an_unknown_type_suggests_types_with_the_map_given(tmp_path: Path) -> None:
    given = _write(tmp_path / "other" / "m.json")
    report = find.run(tmp_path, {}, "a", ["t.none"], 0, given)

    assert any(f"periplus types --map {given} lists them" in w for w in report.warnings)


def test_a_damaged_map_suggests_check_map_with_the_map_given(tmp_path: Path) -> None:
    given = _write(tmp_path / "other" / "m.json", type_hierarchy=[{"parent": None}])
    report = show.run(tmp_path, {}, "t.x::a", 0, given)

    message = report.problems[0].message
    assert f"run periplus check-map --map {given} for the exact error" in message
