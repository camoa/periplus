"""Shared helpers for the skill tests: block extraction, the example project, an in-process run."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from periplus.cli import main

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = ("Resolution gaps", "Detail gaps", "Site faults", "Unknown boundaries")
MAP = ".periplus/map.json"
DESCRIPTIONS_SCHEMA = ROOT / "src/periplus/skills/periplus-map/references/descriptions.schema.json"

_BLOCK = r"<!--\s*{marker}(?![\w-])\s*:?\s*(.*?)\s*-->[ \t]*\n```[^\n]*\n(.*?)\n```"


def blocks(path: Path, marker: str) -> list[tuple[str, str]]:
    """Each fenced block directly after `<!-- marker ARG -->`, as (ARG, body)."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(_BLOCK.format(marker=re.escape(marker)), re.DOTALL)
    return [(m.group(1), m.group(2) + "\n") for m in pattern.finditer(text)]


def skill_blocks(skill: Path, marker: str) -> list[tuple[str, str]]:
    """`blocks` of a skill file, or nothing when the file is absent."""
    return blocks(skill, marker) if skill.is_file() else []


def _section(out: str, heading: str) -> list[str]:
    """The lines printed under `heading`, up to the next report heading."""
    inside: list[str] = []
    active = False
    for line in out.splitlines():
        bare = line.strip().lstrip("#").strip().rstrip(":")
        if bare in HEADINGS:
            active = bare == heading
            continue
        if active and line.strip():
            inside.append(line)
    return inside


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


class Ran(NamedTuple):
    code: int
    out: str
    err: str


def run_periplus(
    args: Sequence[str],
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Ran:
    """Run `periplus ARGS` in-process from `project`, with a config folder beside it."""
    monkeypatch.chdir(project)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(project.parent / "config"))
    code = main(list(args))
    captured = capsys.readouterr()
    return Ran(code, captured.out, captured.err)


def mapped_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Path:
    """The example project after one clean `periplus map`."""
    root = example_project(tmp_path)
    done = run_periplus(["map"], root, monkeypatch, capsys)
    assert done.code == 0, done.err
    return root


def remap_keeps_bytes(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> bool:
    """Whether a second `periplus map` leaves the map file byte-identical."""
    first = (root / MAP).read_bytes()
    assert run_periplus(["map"], root, monkeypatch, capsys).code == 0
    return (root / MAP).read_bytes() == first


def validate_descriptions(doc: object) -> dict[str, object]:
    """Check `doc` against the descriptions schema, after checking the schema itself."""
    schema: dict[str, object] = json.loads(DESCRIPTIONS_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    jsonschema.validate(doc, schema)
    return schema
