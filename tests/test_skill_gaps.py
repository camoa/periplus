"""The gaps skill: its runnable commands."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
from _skills import ROOT, blocks, example_project, run_periplus

SKILL = ROOT / "src" / "periplus" / "skills" / "periplus-gaps" / "SKILL.md"


@pytest.mark.criterion(id="c8")
def test_gaps_skill_nav_run_commands_exit_zero_with_rows_c8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commands = [
        shlex.split(line[2:])
        for _, body in blocks(SKILL, "nav-run")
        for line in body.splitlines()
        if line.startswith("$ periplus")
    ]
    verbs = {c[1] for c in commands if len(c) > 1}
    assert {"check-map", "types", "find"} <= verbs, f"skill names only {sorted(verbs)}"
    project = example_project(tmp_path)
    mapped = run_periplus(["map"], project, monkeypatch, capsys)
    assert mapped.code == 0, mapped.out + mapped.err
    for argv in commands:
        run = run_periplus(argv[1:], project, monkeypatch, capsys)
        assert run.code == 0, f"{argv}: {run.out}{run.err}"
        assert run.out.strip(), f"{argv} printed no row"
