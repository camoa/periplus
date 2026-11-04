"""periplus slice --direction: both follows an edge either way at every hop, out and in one way."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.navigate import slice as slicing
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


def _slice(
    tmp_path: Path, map_path: Path, start: str, direction: str, depth: int
) -> tuple[int, set[str], set[tuple[str, str, str]]]:
    out = tmp_path / f"piece-{direction}-{depth}-{start.split(chr(58))[-1]}.json"
    report = slicing.run(
        tmp_path,
        {},
        out=out,
        map_path=map_path,
        ids=(start,),
        prefix=None,
        direction=direction,
        depth=depth,
        kinds=(),
        limit=500,
    )
    if report.exit_code != 0:
        return report.exit_code, set(), set()
    document = json.loads(out.read_text(encoding="utf-8"))
    return (
        report.exit_code,
        {n["id"] for n in document["nodes"]},
        {(e["kind"], e["from"], e["to"]) for e in document["edges"]},
    )


@pytest.fixture
def abcd(tmp_path: Path) -> Path:
    return _plant(
        tmp_path,
        {"py::A": "function", "py::B": "function", "py::C": "function", "py::D": "function"},
        [("calls", "py::A", "py::B"), ("calls", "py::C", "py::B"), ("calls", "py::A", "py::D")],
    )


@pytest.mark.criterion(id="c1")
def test_both_follows_an_edge_either_way_at_every_hop_and_keeps_edges_between_kept_c1(
    tmp_path: Path, abcd: Path
) -> None:
    code1, ids1, edges1 = _slice(tmp_path, abcd, "py::A", "both", 1)
    code2, ids2, edges2 = _slice(tmp_path, abcd, "py::A", "both", 2)

    assert (code1, code2) == (0, 0)
    assert ids1 == {"py::A", "py::B", "py::D"}
    assert edges1 == {("calls", "py::A", "py::B"), ("calls", "py::A", "py::D")}
    assert ids2 == {"py::A", "py::B", "py::C", "py::D"}
    assert edges2 == {
        ("calls", "py::A", "py::B"),
        ("calls", "py::C", "py::B"),
        ("calls", "py::A", "py::D"),
    }


@pytest.mark.criterion(id="c1")
def test_both_from_a_service_keeps_the_command_that_reaches_its_class_c1(
    tmp_path: Path,
) -> None:
    map_path = _plant(
        tmp_path,
        {"py::svc": "service", "py::cls": "class", "py::cmd": "command"},
        [("service_class", "py::svc", "py::cls"), ("command_class", "py::cmd", "py::cls")],
    )

    code, ids, _ = _slice(tmp_path, map_path, "py::svc", "both", 2)

    assert code == 0
    assert "py::cmd" in ids


@pytest.mark.criterion(id="c2")
def test_out_and_in_keep_their_one_way_meaning_c2(tmp_path: Path, abcd: Path) -> None:
    _, out_ids, _ = _slice(tmp_path, abcd, "py::A", "out", 2)
    _, in_ids, _ = _slice(tmp_path, abcd, "py::A", "in", 2)

    assert out_ids == {"py::A", "py::B", "py::D"}
    assert in_ids == {"py::A"}


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
