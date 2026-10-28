"""The gaps skill: its rule for where a rule belongs, and its runnable commands."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest
from _skills import ROOT, blocks, example_project

SKILL = ROOT / "src" / "periplus" / "skills" / "periplus-gaps" / "SKILL.md"
PERIPLUS = ROOT / ".venv" / "bin" / "periplus"

STANDING_RULES = (
    "split by rule file inside one rutter, never by adding rutters",
    "passes by depth",
    "no stack knowledge in the engine",
    "probe before saying a rutter cannot",
    "never names the client site",
)


def _text() -> str:
    return SKILL.read_text(encoding="utf-8") if SKILL.exists() else ""


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^#{{1,6}} {re.escape(heading)}\s*$(.*?)(?=^#{{1,6}} |\Z)",
        text,
        re.S | re.M,
    )
    return match.group(1) if match else ""


@pytest.mark.criterion(id="c8")
def test_gaps_skill_states_where_a_rule_belongs_c8() -> None:
    text = _text()
    section = _section(text, "Where a rule belongs").lower()
    assert section, "no heading 'Where a rule belongs' in the gaps skill"
    assert ".periplus/packs" in section
    assert "bundled rutter" in section
    assert "rutter skill" in section
    assert "only this project" in section
    assert "any project" in section
    assert "no bundled rutter" in section
    assert "rule file" in section, "the section never names a rule file"
    assert "new rutter" in section, "the section never names a new rutter"
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\s*\n", section)]
    assert any(
        "rule file" in s and "bundled rutter" in s and re.search(r"cover|already", s)
        for s in sentences
    ), "no sentence ties a rule file to a bundled rutter that already covers the stack"
    gap_sentences = [
        s
        for s in re.split(r"(?<=[.!?])\s+|\n\s*\n", text.lower())
        if "node id" in s and "descriptions" in s and "entry" in s and "count" in s
    ]
    assert gap_sentences, "no sentence counts a node id with no descriptions entry"
    assert any(
        not re.search(
            r"\bnot\b|\bnever\b|n't|\bignore|\bskip",
            re.sub(r"\bno (descriptions? )?entry\b", "", s),
        )
        and re.search(r"\bno (descriptions? )?entry\b|without (a |an )?(descriptions? )?entry", s)
        and re.search(r"gap|fill", s)
        for s in gap_sentences
    ), "no un-negated sentence says a node id with no entry counts as one to fill"
    refs = set(re.findall(r"docs/[\w./-]+\.md", text))
    assert "docs/map-report-guide.md" in refs
    missing = sorted(r for r in refs if not (ROOT / r).exists())
    assert not missing, f"dead docs paths: {missing}"


@pytest.mark.criterion(id="c8")
def test_gaps_skill_nav_run_commands_exit_zero_with_rows_c8(tmp_path: Path) -> None:
    found = blocks(SKILL, "nav-run") if SKILL.exists() else []
    commands = [
        shlex.split(line[2:])
        for _, body in found
        for line in body.splitlines()
        if line.startswith("$ periplus")
    ]
    verbs = {c[1] for c in commands if len(c) > 1}
    assert {"check-map", "types", "find"} <= verbs, f"skill names only {sorted(verbs)}"
    project = example_project(tmp_path)
    mapped = subprocess.run(  # noqa: S603 - fixed argv
        [str(PERIPLUS), "map"], cwd=project, capture_output=True, text=True, check=False
    )
    assert mapped.returncode == 0, mapped.stdout + mapped.stderr
    for argv in commands:
        run = subprocess.run(  # noqa: S603 - fixed argv
            [str(PERIPLUS), *argv[1:]], cwd=project, capture_output=True, text=True, check=False
        )
        assert run.returncode == 0, f"{argv}: {run.stdout}{run.stderr}"
        assert run.stdout.strip(), f"{argv} printed no row"


@pytest.mark.criterion(id="wo3")
def test_gaps_skill_opens_with_the_five_standing_rules_wo3() -> None:
    text = _text()
    first = re.search(r"^## (.*)$", text, re.M)
    assert first is not None and first.group(1).strip() == "Standing rules"
    section = _section(text, "Standing rules")
    missing = [p for p in STANDING_RULES if p not in section]
    assert not missing, f"missing key phrases: {missing}"
