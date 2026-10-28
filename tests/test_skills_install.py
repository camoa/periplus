"""``periplus skills install`` and ``install_skills``: the skills reach a person's Claude folder."""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS_SRC = ROOT / "src" / "periplus" / "skills"
SKILLS = ("periplus-rutter", "periplus-map", "periplus-gaps")
SCRIPT = Path(sys.executable).parent / "periplus"


def _front_matter(text: str) -> str:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


@pytest.mark.criterion(id="c1")
def test_install_skills_writes_three_skill_folders_and_replaces_stale_files_c1(
    tmp_path: Path,
) -> None:
    install_skills = importlib.import_module("periplus.skills_install").install_skills
    written = install_skills(home=tmp_path)

    skills_dir = tmp_path / ".claude" / "skills"
    assert sorted(path.name for path in written) == sorted(SKILLS)
    for name in SKILLS:
        skill_file = skills_dir / name / "SKILL.md"
        assert skill_file.is_file(), f"{skill_file} was not written"
        head = _front_matter(skill_file.read_text(encoding="utf-8"))
        assert re.search(r"^name:\s*\S", head, re.MULTILINE), f"{name}: no name in front matter"
        assert re.search(r"^description:", head, re.MULTILINE), f"{name}: no description"

    target = skills_dir / "periplus-map"
    shipped = (SKILLS_SRC / "periplus-map" / "SKILL.md").read_bytes()
    (target / "SKILL.md").write_text("STALE", encoding="utf-8")
    (target / "left-behind.txt").write_text("stale", encoding="utf-8")
    install_skills(home=tmp_path)
    assert (target / "SKILL.md").read_bytes() == shipped
    assert not (target / "left-behind.txt").exists()


@pytest.mark.criterion(id="c1")
def test_skills_install_command_writes_the_skills_and_refuses_an_unwritable_home_c1(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home)}
    done = subprocess.run(  # noqa: S603
        [str(SCRIPT), "skills", "install"], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    assert len(lines) == len(SKILLS), done.stdout
    for name in SKILLS:
        assert (home / ".claude" / "skills" / name / "SKILL.md").is_file()

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / ".claude").write_text("a plain file", encoding="utf-8")
    refused = subprocess.run(  # noqa: S603
        [str(SCRIPT), "skills", "install"],
        env={**os.environ, "HOME": str(blocked)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 27, refused.stderr
    assert str(blocked / ".claude") in refused.stderr


@pytest.mark.criterion(id="c1")
def test_readme_names_the_skills_install_command_after_the_tool_install_c1() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    start = readme.index("### 1. Install Periplus")
    end = readme.index("### 2.", start)
    step = readme[start:end]
    tool = step.index("uv tool install")
    assert "periplus skills install" in step, "step 1 does not name periplus skills install"
    assert step.index("periplus skills install") > tool
