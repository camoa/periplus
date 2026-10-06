"""A project that pins no rutter stops before the map is built, with a message that says so."""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.errors import ExitCode
from periplus.map import run
from periplus.preflight import check_runtime_dependencies


@pytest.mark.parametrize("settings", ["periplus_version: 0\n", "periplus_version: 0\npacks: []\n"])
def test_a_project_that_pins_no_rutter_gets_one_problem_and_no_map(
    tmp_path: Path, settings: str
) -> None:
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(settings)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert len(report.problems) == 1, report.problems
    problem = report.problems[0]
    assert problem.code == ExitCode.MAP_INVALID == 17
    assert "no rutter is pinned" in problem.message
    assert "packs" in problem.message
    assert ".periplus/settings.yml" in problem.message
    assert "periplus status" in problem.message
    assert dict(problem.detail) == {"setting": "packs"}
    assert report.map_path is None
    assert not (tmp_path / "map.json").exists()
    assert not (tmp_path / ".periplus" / "map.json").exists()
