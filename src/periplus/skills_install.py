"""Copy the skills this package ships into a person's Claude skills folder.

The skills are read through ``importlib.resources``, as ``packs.py`` reads the bundled rutters, so
the same code copies from a wheel and from a checkout. Each skill folder replaces the folder of the
same name, so an upgrade of the tool refreshes the skills when this is run again.
"""

from __future__ import annotations

import importlib.resources
import shutil
from importlib.resources.abc import Traversable
from pathlib import Path

from periplus.errors import ExitCode, HarnessError

__all__ = ["SkillsUnwritable", "install_skills"]

SKILLS_DIRECTORY = "skills"


class SkillsUnwritable(HarnessError):
    """A skill folder could not be written under the home directory."""

    code = ExitCode.OUTPUT_UNWRITABLE


def install_skills(home: Path) -> list[Path]:
    """Copy every shipped skill folder into ``home/.claude/skills``; return the folders written."""
    source = importlib.resources.files("periplus") / SKILLS_DIRECTORY
    target_root = home / ".claude" / "skills"
    written: list[Path] = []
    for skill in sorted(source.iterdir(), key=lambda entry: entry.name):
        if not skill.is_dir():
            continue
        target = target_root / skill.name
        try:
            if target.is_dir():
                shutil.rmtree(target)
            _copy(skill, target)
        except OSError as error:
            message = f"the skills cannot be written to {target}: {error.strerror or error}"
            raise SkillsUnwritable(message, {"path": str(target)}) from error
        written.append(target)
    return written


def _copy(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True)
    for entry in source.iterdir():
        if entry.is_dir():
            _copy(entry, target / entry.name)
        else:
            (target / entry.name).write_bytes(entry.read_bytes())
