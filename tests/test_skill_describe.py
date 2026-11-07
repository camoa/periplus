"""The periplus-describe worked example stays inside its slice and leaves the map alone."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest
from _skills import (
    ROOT,
    blocks,
    mapped_project,
    remap_keeps_bytes,
    run_periplus,
    skill_blocks,
    validate_descriptions,
    write_example,
)
from ruamel.yaml import YAML

SKILL = ROOT / "src" / "periplus" / "skills" / "periplus-describe" / "SKILL.md"
MAP_SKILL = ROOT / "src" / "periplus" / "skills" / "periplus-map" / "SKILL.md"


def _example() -> list[tuple[str, str]]:
    """The worked example lives in the map skill; this skill points at it."""
    return blocks(MAP_SKILL, "example")


def _slice_lines() -> list[str]:
    runs = skill_blocks(SKILL, "nav-run")
    return [ln for _, body in runs for ln in body.splitlines() if ln.startswith("$ periplus slice")]


def _cut_slice(
    line: str, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> dict:
    args = shlex.split(line)[2:]
    assert run_periplus(args, root, monkeypatch, capsys).code == 0
    return json.loads((root / args[args.index("--out") + 1]).read_text(encoding="utf-8"))


@pytest.mark.criterion(id="c2")
def test_writing_the_example_descriptions_leaves_the_map_byte_identical_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mapped_project(tmp_path, monkeypatch, capsys)
    lines = _slice_lines()
    assert lines != []
    _cut_slice(lines[0], root, monkeypatch, capsys)
    written = write_example(root, _example(), "descriptions")
    assert written != []
    assert remap_keeps_bytes(root, monkeypatch, capsys)


@pytest.mark.criterion(id="c2")
def test_example_descriptions_describe_items_of_the_slice_at_their_locations_c2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mapped_project(tmp_path, monkeypatch, capsys)

    lines = _slice_lines()
    assert len(lines) == 1, lines
    sliced = _cut_slice(lines[0], root, monkeypatch, capsys)

    written = write_example(root, _example(), "descriptions")
    assert [p.relative_to(root).as_posix() for p in written] == [".periplus/descriptions.yaml"]
    doc = YAML(typ="safe").load(written[0].read_text(encoding="utf-8"))

    validate_descriptions(doc)

    assert doc["nodes"], "no node entry"
    assert doc["edges"], "no edge entry"

    node_locations = {
        n["id"]: {(loc["file"], loc["line"]) for loc in n["locations"]} for n in sliced["nodes"]
    }
    for node_id, entry in doc["nodes"].items():
        assert node_id in node_locations, f"{node_id} is not in the slice"
        assert (entry["file"], entry["line"]) in node_locations[node_id], node_id

    edge_locations = {
        (e["from"], e["kind"], e["to"]): {(loc["file"], loc["line"]) for loc in e["locations"]}
        for e in sliced["edges"]
    }
    for entry in doc["edges"]:
        key = (entry["from"], entry["kind"], entry["to"])
        assert key in edge_locations, f"{key} is not in the slice"
        assert (entry["file"], entry["line"]) in edge_locations[key], key
