"""``periplus skills install`` and ``install_skills``: the skills reach a person's Claude folder."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
SKILLS_SRC = ROOT / "src" / "periplus" / "skills"
SKILLS = (
    "periplus-rutter",
    "periplus-map",
    "periplus-gaps",
    "periplus-describe",
    "periplus-analyze",
)


def _front_matter(text: str) -> str:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


@pytest.mark.criterion(id="c1")
def test_install_skills_writes_every_skill_folder_and_replaces_stale_files_c1(
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
def test_install_on_an_empty_home_writes_the_describe_skill_with_name_and_description_c1(
    tmp_path: Path,
) -> None:
    install_skills = importlib.import_module("periplus.skills_install").install_skills
    install_skills(home=tmp_path)

    skill_file = tmp_path / ".claude" / "skills" / "periplus-describe" / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else ""
    head = YAML(typ="safe").load(_front_matter(text)) or {}
    assert head.get("name") == "periplus-describe"
    description = head.get("description")
    assert isinstance(description, str)
    assert description.strip() != ""
