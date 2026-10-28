"""The rutter skill: the examples and commands it shows."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest
from _skills import ROOT, Ran, blocks, example_project, run_periplus, write_example

SKILL = ROOT / "src/periplus/skills/periplus-rutter/SKILL.md"


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


def pack_identity(pack_yaml: Path) -> tuple[str, str]:
    text = pack_yaml.read_text(encoding="utf-8")
    name = re.search(r"(?m)^pack:\s*(\S+)", text)
    version = re.search(r"(?m)^version:\s*(\S+)", text)
    assert name and version, f"{pack_yaml} lacks pack: or version:"
    return name.group(1), version.group(1)


def pack_names(packs: list[dict[str, str]]) -> set[str]:
    """Pack names listed under the map's packs key."""
    return {entry["pack"] for entry in packs}


def map_packs(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[Ran, dict]:
    done = run_periplus(["map", "--output", "map.json"], project, monkeypatch, capsys)
    out = project / "map.json"
    return done, json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}


@pytest.mark.criterion(id="c2")
def test_every_section_command_exits_zero_after_its_examples_are_written_c2(
    tmp_path, monkeypatch, capsys
):
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
            done = run_periplus(argv[1:], project, monkeypatch, capsys)
            ran += 1
            verbs.add(argv[1])
            assert done.code == 0, f"{' '.join(argv)} exited {done.code}: {done.err}"
    assert ran > 0, "the skill has no nav-run command"
    assert {"validate", "map"} <= verbs, f"the skill runs only {sorted(verbs)}"


@pytest.mark.criterion(id="c2")
def test_new_rutter_skeleton_validates_and_is_listed_in_the_map_c2(tmp_path, monkeypatch, capsys):
    project = example_project(tmp_path)
    written = write_example(
        project, blocks(SKILL, "example") if SKILL.is_file() else [], "new-rutter"
    )
    packs = [p for p in written if p.name == "pack.yaml" and ".periplus/packs" in p.as_posix()]
    assert packs, "the new-rutter blocks write no pack.yaml under .periplus/packs"
    name, version = pack_identity(packs[0])
    settings = (project / ".periplus/settings.yml").read_text(encoding="utf-8")
    assert f"{name}@{version}" in settings, "the settings do not pin the new rutter"
    checked = run_periplus(["validate", f"{name}@{version}"], project, monkeypatch, capsys)
    assert checked.code == 0, checked.out + checked.err
    done, produced = map_packs(project, monkeypatch, capsys)
    assert done.code == 0, done.out + done.err
    listed = pack_names(produced["packs"])
    assert name in listed, f"the map's packs key lists {sorted(listed)}, not {name}"


@pytest.mark.criterion(id="c2")
def test_custom_rutter_extends_a_bundled_one_and_its_finding_is_mapped_c2(
    tmp_path, monkeypatch, capsys
):
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
    done, produced = map_packs(project, monkeypatch, capsys)
    assert done.code == 0, done.out + done.err
    listed = pack_names(produced["packs"])
    assert name in listed, f"the map's packs key lists {sorted(listed)}, not {name}"
    found = [
        item
        for item in [*produced.get("nodes", []), *produced.get("edges", [])]
        if name in json.dumps(item.get("provenance"))
    ]
    assert found, "no node or edge in the map comes from the custom rutter's rule"
