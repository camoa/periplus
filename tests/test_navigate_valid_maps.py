"""Navigation commands accept every map the map schema accepts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from _navigate import _edge, _node

from periplus.cli import main

DOCUMENT: dict[str, Any] = {
    "periplus_map_version": 0,
    "packs": [{"pack": "php", "version": "0.1.0"}],
    "roots": ["."],
    "nodes": [
        _node("php.method::A::go", "php.method", line=3),
        _node("php.method::B::run", "php.method", line=3),
    ],
    "edges": [_edge("calls", "php.method::A::go", "php.method::B::run", 7)],
}


def _write(root: Path, document: dict[str, Any]) -> str:
    path = root / "map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def test_a_whole_number_float_line_and_count_is_shown_as_the_map_holds_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = copy.deepcopy(DOCUMENT)
    document["nodes"][0]["locations"][0]["line"] = 7.0
    document["edges"][0]["locations"][0]["line"] = 7.0
    document["edges"][0]["occurrences"] = 2.0
    path = _write(tmp_path, document)

    assert main(["show", "php.method::A::go", "--map", path]) == 0

    out = capsys.readouterr().out
    assert "location: src/a.php:7.0" in out
    assert "src/a.php:7.0  x2.0" in out


def test_a_type_hierarchy_row_without_a_parent_is_a_root_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = copy.deepcopy(DOCUMENT)
    document["type_hierarchy"] = [{"type": "php.method"}]
    path = _write(tmp_path, document)

    assert main(["types", "--map", path]) == 0
    assert main(["find", "run", "--type", "php.method", "--map", path]) == 0
    assert "php.method::B::run" in capsys.readouterr().out
