"""periplus slice refuses an --out that is the map it reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from periplus.errors import ExitCode


def test_slice_refuses_an_out_that_is_the_map_it_reads_and_writes_nothing(tmp_path: Path) -> None:
    from periplus.navigate import slice as slicing

    node = {
        "id": "py::a",
        "type": "function",
        "state": "mapped",
        "locations": [{"file": "src/a.py", "line": 1}],
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }
    document = {
        "periplus_map_version": 3,
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [node],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    (tmp_path / "sub").mkdir()
    spelled = tmp_path / "sub" / ".." / "full-map.json"

    report = slicing.run(tmp_path, {}, ("py::a",), None, "both", 1, (), 500, spelled, path)

    assert report.exit_code == ExitCode.OUTPUT_UNWRITABLE
    assert len(report.problems) == 1
    assert "full-map.json" in report.problems[0].message
    assert report.out is None
    assert path.read_bytes() == before


def test_slice_with_no_ids_and_no_prefix_writes_nothing_and_exits_usage(tmp_path: Path) -> None:
    from periplus.navigate import slice as slicing

    document = {
        "periplus_map_version": 3,
        "type_hierarchy": [],
        "counts": {},
        "nodes": [],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "piece.json"

    report = slicing.run(tmp_path, {}, (), None, "both", 1, (), 500, out, path)

    assert report.exit_code == ExitCode.USAGE
    assert report.out is None
    assert not out.exists()


def test_slice_writes_a_relative_out_under_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from periplus.navigate import slice as slicing

    node = {
        "id": "py::a",
        "type": "function",
        "state": "mapped",
        "locations": [{"file": "src/a.py", "line": 1}],
        "provenance": [{"pack": "core", "rule": "r", "confidence": "declared"}],
    }
    document = {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src"],
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [node],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    report = slicing.run(
        tmp_path, {}, ("py::a",), None, "both", 1, (), 500, Path("piece.json"), path
    )

    assert report.out == str(tmp_path / "piece.json")
    assert (tmp_path / "piece.json").exists()
