"""The rutter skill: the examples and commands it shows."""

from __future__ import annotations

import json
import re
import runpy
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


def map_file(project: Path) -> dict:
    return json.loads((project / ".periplus/map.json").read_text(encoding="utf-8"))


@pytest.mark.criterion(id="wo2")
def test_gap_read_block_prints_the_counts_diff_and_the_new_rules_nodes_and_edges_wo2(
    tmp_path, monkeypatch, capsys
):
    project = example_project(tmp_path)
    first = run_periplus(["map"], project, monkeypatch, capsys)
    assert first.code == 0, first.out + first.err
    before = tmp_path / "before.json"
    before.write_text((project / ".periplus/map.json").read_text(encoding="utf-8"))
    for index, section in enumerate(sections(skill_text())):
        scratch = tmp_path / f"g{index}.md"
        scratch.write_text(section, encoding="utf-8")
        found = blocks(scratch, "example")
        for name in dict.fromkeys(arg.partition(":")[0].strip() for arg, _ in found):
            write_example(project, found, name)
        for argv in commands_of(section, tmp_path):
            done = run_periplus(argv[1:], project, monkeypatch, capsys)
            assert done.code == 0, f"{' '.join(argv)} exited {done.code}: {done.err}"
    after = project / ".periplus/map.json"
    old, new = json.loads(before.read_text(encoding="utf-8")), map_file(project)
    gained = pack_names(new["packs"]) - pack_names(old["packs"])
    assert gained, "the skill's examples add no rutter to the example project"
    found_blocks = blocks(SKILL, "gap-read") if SKILL.is_file() else []
    assert len(found_blocks) == 1, f"the skill holds {len(found_blocks)} gap-read blocks"
    program = tmp_path / "gap_read.py"
    program.write_text(found_blocks[0][1], encoding="utf-8")

    def run(*extra: str) -> str:
        capsys.readouterr()
        monkeypatch.setattr("sys.argv", [str(program), str(before), str(after), *extra])
        runpy.run_path(str(program), run_name="__main__")
        return capsys.readouterr().out

    out = run()
    lines = [line.split() for line in out.splitlines()]
    assert ["Measured"] in lines, out
    old_ids = {n["id"] for n in old["nodes"]}
    old_edges = {(e["from"], e["kind"], e["to"]) for e in old["edges"]}
    added_nodes = [n for n in new["nodes"] if n["id"] not in old_ids]
    added_edges = [e for e in new["edges"] if (e["from"], e["kind"], e["to"]) not in old_edges]
    assert (
        added_nodes
        or added_edges
        or any(
            old["counts"][key] != new["counts"][key]
            for key in ("nodes_by_state", "nodes_by_type", "edges_by_kind")
        )
    ), "the example project's maps before and after do not differ"
    assert ["added", "nodes", str(len(added_nodes))] in lines, out
    assert ["added", "edges", str(len(added_edges))] in lines, out
    for kind_key, group in (
        ("nodes_by_state", "state"),
        ("nodes_by_type", "type"),
        ("edges_by_kind", "kind"),
    ):
        was, now = old["counts"][kind_key], new["counts"][kind_key]
        for key in sorted(set(was) | set(now)):
            a, b = was.get(key, 0), now.get(key, 0)
            row = [group, key, str(a), str(b), f"{b - a:+d}"]
            assert (row in lines) == (a != b), f"{row}: {out}"
    assert not any(line[:1] in (["node"], ["edge"]) for line in lines), "no rule, yet node lines"

    entries = [
        entry
        for e in new["edges"]
        for entry in e.get("provenance", [])
        if entry.get("pack") in gained
    ]
    assert entries, "no edge in the after map comes from the new rutter"
    rule = entries[0]["rule"]
    pack = entries[0]["pack"]
    out = run(f"{pack}/{rule}")
    lines = [line.split() for line in out.splitlines()]

    def names_rule(item: dict) -> bool:
        return any(
            entry.get("pack") == pack and entry.get("rule") == rule
            for entry in item.get("provenance", [])
        )

    want_nodes = sorted(n["id"] for n in new["nodes"] if names_rule(n))
    want_edges = sorted((e["from"], e["kind"], e["to"]) for e in new["edges"] if names_rule(e))
    assert want_edges, "the chosen rule has no edge in the after map"
    assert want_nodes, "the chosen rule has no node in the after map"
    assert [line[1] for line in lines if line[:1] == ["node"]] == want_nodes, out
    assert [tuple(line[1:]) for line in lines if line[:1] == ["edge"]] == want_edges, out


MEASURE_LOOP = (
    "## Measure what the rule added",
    "## Offer the next rule",
    "## Stop with an accepted unknown",
    "## Draft the upstream issue",
)


@pytest.mark.criterion(id="wo2")
def test_loop_sections_run_in_order_on_the_example_project_and_every_periplus_line_exits_zero_wo2(
    tmp_path, monkeypatch, capsys
):
    project = example_project(tmp_path)
    by_heading = {s.splitlines()[0].strip(): s for s in sections(skill_text())}
    ran_in: dict[str, int] = {}
    for index, section in enumerate(sections(skill_text())):
        heading = section.splitlines()[0].strip()
        scratch = tmp_path / f"w{index}.md"
        scratch.write_text(section, encoding="utf-8")
        found = blocks(scratch, "example")
        for name in dict.fromkeys(arg.partition(":")[0].strip() for arg, _ in found):
            write_example(project, found, name)
        for argv in commands_of(section, tmp_path):
            done = run_periplus(argv[1:], project, monkeypatch, capsys)
            ran_in[heading] = ran_in.get(heading, 0) + 1
            assert done.code == 0, f"{' '.join(argv)} exited {done.code}: {done.err}"
    missing = [h for h in MEASURE_LOOP if h not in by_heading]
    assert not missing, f"the skill has no section {missing}"
    order = [s.splitlines()[0].strip() for s in sections(skill_text())]
    positions = [order.index(h) for h in MEASURE_LOOP]
    assert positions == sorted(positions), f"the loop sections run out of order: {positions}"
    assert ran_in.get(MEASURE_LOOP[0], 0) > 0, "the measure section runs no periplus line"
