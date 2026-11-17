"""The raw walk ``walk`` with ``both`` follows an edge either way at every hop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.navigate.mapfile import MapIndex
from periplus.navigate.walk import walk

HIERARCHY = [{"type": t, "parent": None} for t in ("function", "class", "service", "command")]
PROVENANCE = [{"pack": "core", "rule": "r", "confidence": "declared"}]


def _plant(tmp_path: Path, nodes: dict[str, str], edges: list[tuple[str, str, str]]) -> Path:
    document: dict[str, Any] = {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src"],
        "type_hierarchy": HIERARCHY,
        "counts": {},
        "nodes": [
            {
                "id": node_id,
                "type": node_type,
                "state": "mapped",
                "locations": [{"file": "src/" + node_id.split("::")[1] + ".py", "line": 1}],
                "provenance": PROVENANCE,
            }
            for node_id, node_type in sorted(nodes.items())
        ],
        "edges": [
            {
                "kind": kind,
                "from": source,
                "to": target,
                "locations": [{"file": "src/" + source.split("::")[1] + ".py", "line": 2}],
                "provenance": PROVENANCE,
            }
            for kind, source, target in edges
        ],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return path


@pytest.mark.criterion(id="c1")
def test_walk_both_visits_each_item_once_at_its_nearest_depth_in_order_wo1(
    tmp_path: Path,
) -> None:
    map_path = _plant(
        tmp_path,
        {
            "py::A": "function",
            "py::B": "function",
            "py::C": "function",
            "py::D": "function",
            "py::0": "function",
        },
        [
            ("calls", "py::A", "py::B"),
            ("calls", "py::A", "py::D"),
            ("calls", "py::C", "py::B"),
            ("calls", "py::D", "py::C"),
            ("uses", "py::0", "py::A"),
        ],
    )
    index = MapIndex(json.loads(map_path.read_text(encoding="utf-8")))

    rows = walk(index, "py::A", "both", 2, set())

    assert [(r.id, r.depth) for r in rows if r.id != "py::A"] == [
        ("py::0", 1),
        ("py::B", 1),
        ("py::D", 1),
        ("py::C", 2),
    ]
