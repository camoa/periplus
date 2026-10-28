"""Tests for the periplus-map skill: navigation by question and the descriptions file."""

from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path

import pytest
from _skills import ROOT, blocks, example_project, run_periplus, write_example
from jsonschema import Draft202012Validator, ValidationError, validate
from ruamel.yaml import YAML

SKILL = ROOT / "src/periplus/skills/periplus-map/SKILL.md"
SCHEMA = ROOT / "src/periplus/skills/periplus-map/references/descriptions.schema.json"


def _blocks(marker: str) -> list[tuple[str, str]]:
    return blocks(SKILL, marker) if SKILL.exists() else []


def _mapped_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[Path, dict[str, object], str]:
    """Map the example project; return its root, the parsed map and the map's relative path."""
    root = example_project(tmp_path)
    done = run_periplus(["map"], root, monkeypatch, capsys)
    assert done.code == 0, done.err
    rel = ".periplus/map.json"
    return root, json.loads((root / rel).read_text(encoding="utf-8")), rel


@pytest.mark.criterion(id="c9")
def test_second_map_run_leaves_map_byte_identical_c9(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _data, rel = _mapped_project(tmp_path, monkeypatch, capsys)
    written = write_example(root, _blocks("example"), "descriptions")
    assert written, "the skill holds no example block named descriptions"
    first = (root / rel).read_bytes()
    assert run_periplus(["map"], root, monkeypatch, capsys).code == 0
    assert (root / rel).read_bytes() == first


@pytest.mark.criterion(id="c9")
def test_descriptions_example_matches_map_and_schema_c9(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, data, _rel = _mapped_project(tmp_path, monkeypatch, capsys)
    written = write_example(root, _blocks("example"), "descriptions")
    assert [p.relative_to(root).as_posix() for p in written] == [".periplus/descriptions.yaml"]
    doc = YAML(typ="safe").load(written[0].read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert doc.get("nodes"), "no node entry"
    assert doc.get("edges"), "no edge entry"
    assert SCHEMA.exists(), "the schema file is absent"
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validate(doc, schema)
    node_ids = {n["id"] for n in data["nodes"]}  # type: ignore[attr-defined]
    assert set(doc["nodes"]) <= node_ids
    edges = {(e["from"], e["kind"], e["to"]) for e in data["edges"]}  # type: ignore[attr-defined]
    for e in doc["edges"]:
        assert (e["from"], e["kind"], e["to"]) in edges
    entries = [*doc["nodes"].values(), *doc["edges"]]
    for entry in entries:
        assert isinstance(entry.get("file"), str) and entry["file"], entry
        assert isinstance(entry.get("line"), int) and entry["line"] >= 1, entry
    # The schema itself must demand file and line, so a schema of {} cannot pass.
    for kind, key in (("nodes", next(iter(doc["nodes"]))), ("edges", 0)):
        for field in ("file", "line"):
            broken = copy.deepcopy(doc)
            target = broken[kind][key]
            del target[field]
            with pytest.raises(ValidationError):
                validate(broken, schema)


@pytest.mark.criterion(id="c4")
def test_skill_nav_run_commands_exit_zero_with_rows_c4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = [
        ln.strip()
        for _arg, body in _blocks("nav-run")
        for ln in body.splitlines()
        if ln.strip().startswith("$ periplus")
    ]
    used = {shlex.split(ln)[2] for ln in lines}
    assert {"show", "neighbors", "affected", "path", "find", "types"} <= used
    root, _data, _rel = _mapped_project(tmp_path, monkeypatch, capsys)
    for ln in lines:
        argv = shlex.split(ln)[2:]
        if "--format" in argv:
            i = argv.index("--format")
            del argv[i : i + 2]
        done = run_periplus([*argv, "--format", "json"], root, monkeypatch, capsys)
        assert done.code == 0, (ln, done.err)
        report = json.loads(done.out)
        rows = [
            row
            for key in (
                "items",
                "rows",
                "chains",
                "outgoing",
                "incoming",
                "node_types",
                "edge_kinds",
            )
            for row in report.get(key, [])
        ]
        assert len(rows) >= 1, (ln, "the result list is empty")
