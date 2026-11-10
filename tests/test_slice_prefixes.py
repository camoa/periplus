"""periplus slice with several path prefixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.errors import ExitCode

PROVENANCE = [{"pack": "core", "rule": "r", "confidence": "declared"}]
FILES = {"py::a": "src/a/one.py", "py::b": "src/b/one.py", "py::c": "src/c/one.py"}


@pytest.fixture
def planted(tmp_path: Path) -> Path:
    document: dict[str, Any] = {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src"],
        "type_hierarchy": [{"type": "function", "parent": None}],
        "counts": {},
        "nodes": [
            {
                "id": node_id,
                "type": "function",
                "state": "mapped",
                "locations": [{"file": file, "line": 1}],
                "provenance": PROVENANCE,
            }
            for node_id, file in sorted(FILES.items())
        ],
        "edges": [],
    }
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _run(tmp_path: Path, planted: Path, prefixes: tuple[str, ...], out: Path) -> Any:
    from periplus.navigate import slice as slicing

    return slicing.run(tmp_path, {}, (), prefixes, "both", 1, (), 500, out, planted)


def test_slice_with_two_prefixes_keeps_the_nodes_under_both_wo6(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    report = _run(tmp_path, planted, ("src/a/", "src/b/"), out)

    assert report.exit_code == 0
    kept = {n["id"] for n in json.loads(out.read_text(encoding="utf-8"))["nodes"]}
    assert kept == {"py::a", "py::b"}


def test_slice_refuses_a_missing_prefix_even_when_another_matches_wo6(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    report = _run(tmp_path, planted, ("src/a/", "src/typo/"), out)

    assert report.exit_code == ExitCode.NODE_NOT_FOUND
    assert any("src/typo/" in p.message for p in report.problems)
    assert not out.exists()


def test_cli_slice_passes_every_path_value_wo6(
    tmp_path: Path, planted: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from periplus.cli import main

    out = tmp_path / "piece.json"
    code = main(
        [
            "slice",
            "--path",
            "src/a/",
            "--path",
            "src/c/",
            "--out",
            str(out),
            "--map",
            str(planted),
            "--format",
            "json",
        ]
    )

    assert code == 0
    kept = {n["id"] for n in json.loads(out.read_text(encoding="utf-8"))["nodes"]}
    assert kept == {"py::a", "py::c"}
