"""The rutter skill: its standing rules, its references, and the examples and commands it shows."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from _skills import ROOT, blocks, example_project, write_example

SKILL = ROOT / "src/periplus/skills/periplus-rutter/SKILL.md"
PERIPLUS = str(Path(sys.executable).parent / "periplus")

STANDING_PHRASES = [
    "split by rule file inside one rutter, never by adding rutters",
    "passes by depth",
    "no stack knowledge in the engine",
    "probe before saying a rutter cannot",
    "never names the client site",
]


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8") if SKILL.is_file() else ""


def sections(text: str) -> list[str]:
    """The `## ` sections of the skill in document order."""
    parts = re.split(r"(?m)^(?=## )", text)
    return [p for p in parts if p.startswith("## ")]


def commands_of(section: str, tmp: Path) -> list[list[str]]:
    scratch = tmp / "section.md"
    scratch.write_text(section, encoding="utf-8")
    found: list[list[str]] = []
    for _, body in blocks(scratch, "nav-run"):
        for line in body.splitlines():
            if line.startswith("$ periplus"):
                found.append(shlex.split(line[2:]))
    return found


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv
        [PERIPLUS, *argv[1:]], cwd=cwd, capture_output=True, text=True
    )


def pack_identity(pack_yaml: Path) -> tuple[str, str]:
    text = pack_yaml.read_text(encoding="utf-8")
    name = re.search(r"(?m)^pack:\s*(\S+)", text)
    version = re.search(r"(?m)^version:\s*(\S+)", text)
    assert name and version, f"{pack_yaml} lacks pack: or version:"
    return name.group(1), version.group(1)


def pack_names(packs: object) -> set[str]:
    """Pack names listed under the map's packs key, each without its @version."""
    names: set[str] = set()

    def take(item: object) -> None:
        if isinstance(item, str):
            names.add(item.split("@")[0])
        elif isinstance(item, dict):
            for key, value in item.items():
                names.add(str(key).split("@")[0])
                take(value) if isinstance(value, str) else None
        elif isinstance(item, list):
            for sub in item:
                take(sub)

    take(packs)
    return names


def map_packs(project: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    done = run(["periplus", "map", "--output", "map.json"], project)
    out = project / "map.json"
    return done, json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}


@pytest.mark.criterion(id="c2")
def test_every_section_command_exits_zero_after_its_examples_are_written_c2(tmp_path):
    project = example_project(tmp_path)
    ran = 0
    verbs: set[str] = set()
    for index, section in enumerate(sections(skill_text())):
        scratch = tmp_path / f"s{index}.md"
        scratch.write_text(section, encoding="utf-8")
        found = blocks(scratch, "example")
        for name in dict.fromkeys(arg.partition(":")[0].strip() for arg, _ in found):
            write_example(project, found, name)
        for argv in commands_of(section, tmp_path):
            done = run(argv, project)
            ran += 1
            verbs.add(argv[1])
            assert done.returncode == 0, f"{' '.join(argv)} exited {done.returncode}: {done.stderr}"
    assert ran > 0, "the skill has no nav-run command"
    assert {"validate", "map"} <= verbs, f"the skill runs only {sorted(verbs)}"


@pytest.mark.criterion(id="c2")
def test_new_rutter_skeleton_validates_and_is_listed_in_the_map_c2(tmp_path):
    project = example_project(tmp_path)
    written = write_example(
        project, blocks(SKILL, "example") if SKILL.is_file() else [], "new-rutter"
    )
    packs = [p for p in written if p.name == "pack.yaml" and ".periplus/packs" in p.as_posix()]
    assert packs, "the new-rutter blocks write no pack.yaml under .periplus/packs"
    name, version = pack_identity(packs[0])
    settings = (project / ".periplus/settings.yml").read_text(encoding="utf-8")
    assert f"{name}@{version}" in settings, "the settings do not pin the new rutter"
    checked = run(["periplus", "validate", f"{name}@{version}"], project)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    done, produced = map_packs(project)
    assert done.returncode == 0, done.stdout + done.stderr
    listed = pack_names(produced.get("packs"))
    assert name in listed, f"the map's packs key lists {sorted(listed)}, not {name}"


@pytest.mark.criterion(id="c2")
def test_custom_rutter_extends_a_bundled_one_and_its_finding_is_mapped_c2(tmp_path):
    project = tmp_path / "custom"
    project.mkdir()
    written = write_example(
        project, blocks(SKILL, "example") if SKILL.is_file() else [], "custom-rutter"
    )
    packs = [p for p in written if p.name == "pack.yaml" and ".periplus/packs" in p.as_posix()]
    assert packs, "the custom-rutter blocks write no pack.yaml under .periplus/packs"
    name, version = pack_identity(packs[0])
    depends = re.search(r"(?m)^depends:\s*\[(.*?)\]", packs[0].read_text(encoding="utf-8"))
    assert depends and depends.group(1).strip(), "the custom pack depends on nothing"
    for dep in (d.strip() for d in depends.group(1).split(",")):
        assert list((ROOT / "src/periplus/packs").glob(f"{dep}@*")), (
            f"{dep} is not a bundled rutter"
        )
    done, produced = map_packs(project)
    assert done.returncode == 0, done.stdout + done.stderr
    listed = pack_names(produced.get("packs"))
    assert name in listed, f"the map's packs key lists {sorted(listed)}, not {name}"
    found = [
        item
        for item in [*produced.get("nodes", []), *produced.get("edges", [])]
        if name in json.dumps(item.get("provenance"))
    ]
    assert found, "no node or edge in the map comes from the custom rutter's rule"


@pytest.mark.criterion(id="wo1")
def test_skill_opens_with_the_five_standing_rules_wo1():
    text = skill_text()
    parts = sections(text)
    assert parts and parts[0].startswith("## Standing rules"), (
        "first section is not ## Standing rules"
    )
    first = parts[0].lower()
    absent = [p for p in STANDING_PHRASES if p not in first]
    assert not absent, f"standing rules missing their key phrase: {absent}"
