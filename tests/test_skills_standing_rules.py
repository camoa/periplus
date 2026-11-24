"""The rutter skill opens with the standing rules; the other skills carry none."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_SRC = Path(__file__).resolve().parent.parent / "src" / "periplus" / "skills"
OTHER_SKILLS = ("periplus-map", "periplus-gaps", "periplus-describe", "periplus-analyze")
PHRASES = (
    "split by rule file inside one rutter, never by adding rutters",
    "passes by depth",
    "no stack knowledge in the engine",
    "probe before saying a rutter cannot",
    "never names the project it was built on",
)


def _sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"^## +(.*)$", text, flags=re.MULTILINE)
    return list(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.criterion(id="c6")
def test_rutter_skill_opens_with_standing_rules_carrying_the_five_phrases_c6() -> None:
    skill = "periplus-rutter"
    text = (SKILLS_SRC / skill / "SKILL.md").read_text(encoding="utf-8")
    sections = _sections(text)
    assert sections, f"{skill} has no ## section"
    heading, body = sections[0]
    assert heading.strip() == "Standing rules", f"{skill} opens with '{heading}'"
    flat = " ".join(body.lower().split())
    missing = [phrase for phrase in PHRASES if phrase not in flat]
    assert missing == [], f"{skill}: Standing rules lacks {missing}"


@pytest.mark.parametrize("skill", OTHER_SKILLS)
def test_other_skills_carry_no_standing_rules_heading(skill: str) -> None:
    text = (SKILLS_SRC / skill / "SKILL.md").read_text(encoding="utf-8")
    headings = [h.strip() for h, _ in _sections(text)]
    assert "Standing rules" not in headings, f"{skill} still has a Standing rules heading"
