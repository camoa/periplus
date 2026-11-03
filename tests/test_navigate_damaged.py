"""A malformed row exits 30 with the same pointer to check-map as a damaged field."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _navigate import _node

from periplus.cli import main


def test_a_malformed_edge_row_exits_30_and_points_to_check_map_c1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps(
            {
                "periplus_map_version": 0,
                "packs": [{"pack": "php", "version": "0.1.0"}],
                "roots": ["."],
                "type_hierarchy": [{"type": "php.symbol", "parent": None}],
                "nodes": [_node("php.symbol::a", "php.symbol")],
                "edges": [{"x": 1}],
            }
        ),
        encoding="utf-8",
    )

    code = main(["find", "a", "--map", str(path)])

    captured = capsys.readouterr()
    assert code == 30
    assert "check-map" in captured.out + captured.err
