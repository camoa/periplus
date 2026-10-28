"""Tests for the periplus-map skill: navigation by question and the descriptions file."""

from __future__ import annotations

import copy
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from _skills import ROOT, blocks, example_project, write_example
from jsonschema import Draft202012Validator, ValidationError, validate
from ruamel.yaml import YAML

SKILL = ROOT / "src/periplus/skills/periplus-map/SKILL.md"
SCHEMA = ROOT / "src/periplus/skills/periplus-map/references/descriptions.schema.json"
EXE = str(Path(sys.executable).parent / "periplus")


def _text() -> str:
    return SKILL.read_text(encoding="utf-8") if SKILL.exists() else ""


def _blocks(marker: str) -> list[tuple[str, str]]:
    return blocks(SKILL, marker) if SKILL.exists() else []


def _run(root: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [EXE, *argv], cwd=root, capture_output=True, text=True, check=False
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _mapped_project(tmp_path: Path) -> tuple[Path, dict[str, object], str]:
    """Map the example project; return its root, the parsed map and the map's relative path."""
    root = example_project(tmp_path)
    before = _tree(root)
    done = _run(root, ["map"])
    assert done.returncode == 0, done.stderr
    after = _tree(root)
    for rel in sorted(set(after) - set(before)):
        try:
            data = json.loads(after[rel])
        except ValueError:
            continue
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return root, data, rel
    raise AssertionError("periplus map wrote no map file with nodes and edges")


@pytest.mark.criterion(id="c9")
def test_second_map_run_leaves_map_byte_identical_c9(tmp_path: Path) -> None:
    root, _data, rel = _mapped_project(tmp_path)
    written = write_example(root, _blocks("example"), "descriptions")
    assert written, "the skill holds no example block named descriptions"
    first = (root / rel).read_bytes()
    assert _run(root, ["map"]).returncode == 0
    assert (root / rel).read_bytes() == first


@pytest.mark.criterion(id="c9")
def test_skill_opens_descriptions_file_on_every_navigation_c9() -> None:
    text = _text()
    assert re.search(r"open[^.\n]*descriptions[^.\n]*every navigation", text, re.I) or re.search(
        r"every navigation[^.\n]*open[^.\n]*descriptions", text, re.I
    ), "no sentence tells the reader to open the descriptions file on every navigation"
    assert "references/descriptions.schema.json" in text
    paths = set(re.findall(r"(?<![\w/.-])(docs/[\w./-]+\.md)", text))
    assert paths, "the skill points at no docs path"
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, missing


@pytest.mark.criterion(id="c9")
def test_descriptions_example_matches_map_and_schema_c9(tmp_path: Path) -> None:
    root, data, _rel = _mapped_project(tmp_path)
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


_QUESTIONS = [
    (r"neighbo", ("show", "neighbors")),
    (r"affect", ("affected",)),
    (r"path", ("path",)),
    (r"match", ("find",)),
    (r"kinds", ("types",)),
]


@pytest.mark.criterion(id="c4")
def test_skill_maps_each_question_to_a_command_and_commands_run_c4(tmp_path: Path) -> None:
    rows = [ln for ln in _text().splitlines() if ln.lstrip().startswith("|")]
    for question, commands in _QUESTIONS:
        hit = [r for r in rows if re.search(question, r, re.I)]
        assert hit, f"no table row for the question {question}"
        for command in commands:
            assert any(f"periplus {command}" in r for r in hit), (question, command)
    lines = [
        ln.strip()
        for _arg, body in _blocks("nav-run")
        for ln in body.splitlines()
        if ln.strip().startswith("$ periplus")
    ]
    used = {shlex.split(ln)[2] for ln in lines}
    assert {"show", "neighbors", "affected", "path", "find", "types"} <= used
    root, _data, _rel = _mapped_project(tmp_path)
    for ln in lines:
        argv = shlex.split(ln)[2:]
        if "--format" in argv:
            i = argv.index("--format")
            del argv[i : i + 2]
        done = _run(root, [*argv, "--format", "json"])
        assert done.returncode == 0, (ln, done.stderr)
        report = json.loads(done.stdout)
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


@pytest.mark.criterion(id="wo2")
def test_skill_opens_with_the_five_standing_rules_wo2() -> None:
    text = _text()
    match = re.search(r"^## Standing rules\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, "no Standing rules section"
    assert re.findall(r"^## (.+)$", text, re.M)[:1] == ["Standing rules"]
    section = match.group(1)
    rules = [ln for ln in section.splitlines() if re.match(r"\s*(\d+[.)]|[-*])\s+\S", ln)]
    assert len(rules) == 5, rules
    for phrase in (
        "split by rule file inside one rutter, never by adding rutters",
        "passes by depth",
        "no stack knowledge in the engine",
        "probe before saying a rutter cannot",
        "never names the client site",
    ):
        assert phrase in section, phrase
