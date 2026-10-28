"""Shared helpers for the skill tests: block extraction and the example project."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BLOCK = r"<!--\s*{marker}(?![\w-])\s*:?\s*(.*?)\s*-->[ \t]*\n```[^\n]*\n(.*?)\n```"


def blocks(path: Path, marker: str) -> list[tuple[str, str]]:
    """Each fenced block directly after `<!-- marker ARG -->`, as (ARG, body)."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(_BLOCK.format(marker=re.escape(marker)), re.DOTALL)
    return [(m.group(1), m.group(2) + "\n") for m in pattern.finditer(text)]


def write_example(root: Path, found: list[tuple[str, str]], name: str) -> list[Path]:
    """Write every block of one NAME (`NAME: PATH`) at PATH under root."""
    written: list[Path] = []
    for arg, body in found:
        block_name, _, rel = arg.partition(":")
        if block_name.strip() != name or not rel.strip():
            continue
        target = root / rel.strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(target)
    return written


def example_project(tmp_path: Path) -> Path:
    """A project that maps to a non-empty map: second-stack rutters plus navigation sources."""
    root = tmp_path / "project"
    (root / ".periplus").mkdir(parents=True)
    shutil.copytree(ROOT / "examples/second-stack/packs", root / ".periplus/packs")
    shutil.copy(ROOT / "examples/second-stack/settings.yml", root / ".periplus/settings.yml")
    for rel, body in blocks(ROOT / "docs/navigation.md", "nav-file"):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root
