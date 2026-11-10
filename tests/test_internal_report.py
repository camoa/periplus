"""The map report and the written map's counts leave an internal type out, and say so only when it did."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import pin, plant, rutter
from test_internal_types import MANIFEST, RULES, SOURCE

from periplus.cli import main


def _run(root: Path, capsys: pytest.CaptureFixture[str], marks: str, fmt: str) -> tuple[str, dict]:
    rules = RULES.format(marks=marks, reach="", hidden="", within="site.callsite")
    rutter(root, "site", MANIFEST, {"site.yaml": rules})
    pin(root, "site@0.0.1")
    plant(root, {"src/one.sx": SOURCE})
    capsys.readouterr()
    main(["map", "--format", fmt, "--output", str(root / "out.json")])
    printed = capsys.readouterr().out
    return printed, json.loads((root / "out.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


@pytest.mark.criterion(id="c3")
def test_the_json_report_and_the_map_counts_leave_the_internal_type_out_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, written = _run(tmp_path, capsys, ", internal: true", "json")
    report = json.loads(printed)
    assert report["internal"] == {"nodes": 2, "edges": 2}
    assert (report["nodes"], report["edges"]) == (3, 2)
    counts = written["counts"]
    assert counts["nodes_by_type"] == {"site.function": 3}
    assert counts["nodes"] == 3
    assert [h["type"] for h in written["type_hierarchy"]] == ["site.function"]


@pytest.mark.criterion(id="c3")
def test_the_text_summary_prints_no_internal_line_when_nothing_was_left_out_c3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, _ = _run(tmp_path, capsys, "", "text")
    assert "internal:" not in printed
