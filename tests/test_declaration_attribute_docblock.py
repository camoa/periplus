"""A declaration rule may set an attribute from its id's sources, such as a docblock line."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _own_pack import MANIFEST, PACK, plant

from periplus.cli import main
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

SUMMARY = (
    r"\A/\*\*[ \t]*(?:\n[ \t]*\*)?[ \t]*(?<summary>[^@{\s*][^\n]*?)"
    r"[ \t]*(?:\*/)?[ \t]*(?:\n|\Z)"
)
RULES = """\
node_types:
- name: own.thing
  id_namespace: own.thing
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {{declaration: class_declaration, name_child: name, filetype: php}}
  id: {{from: qualified_name}}
  emits:
  - node: {{type: own.thing}}
  - attribute: {{name: kind, template: 'plain  class'}}
  confidence: declared
- rule: class_summary
  reads: file
  in: [source]
  match: {{declaration: class_declaration, name_child: name, filetype: php}}
  id:
    from: [qualified_name, {{docblock: '{pattern}'}}]
    template: '{{qualified_name}}'
  emits:
  - node: {{type: own.thing}}
  - attribute: {{name: summary, template: '{template}'}}
  confidence: declared
"""
LONG = "word " * 100
SOURCE = f"""<?php
/**
 * Runs the thing.
 */
class Thing {{}}

class Bare {{}}

/**
 * {{@inheritdoc}}
 */
class Inherits {{}}

/**
 * {LONG}
 */
class Long {{}}

/**
 * Spaced \t  out   words.
 */
class Spaced {{}}
"""


def _plant(root: Path, template: str = "{summary}") -> None:
    plant(root, RULES.format(pattern=SUMMARY, template=template), SOURCE)
    (root / PACK / "pack.yaml").write_text(MANIFEST + "  comment: comment\n")


def _map(root: Path) -> dict[str, Any]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-home")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert report.map_path is not None
    document: dict[str, Any] = json.loads(Path(report.map_path).read_text())
    return document


def _nodes(root: Path) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in _map(root)["nodes"]}


def test_a_docblock_first_line_lands_as_an_attribute_with_its_provenance(tmp_path: Path) -> None:
    _plant(tmp_path)
    node = _nodes(tmp_path)["own.thing::Thing"]
    assert node["attributes"]["summary"] == "Runs the thing."
    rows = {row["rule"]: row["sets"] for row in node["provenance"]}
    assert rows["class_summary"] == ["id", "type", "summary"]


def test_a_class_with_no_docblock_gets_no_summary(tmp_path: Path) -> None:
    _plant(tmp_path)
    node = _nodes(tmp_path)["own.thing::Bare"]
    assert "summary" not in node["attributes"]
    assert [row["rule"] for row in node["provenance"]] == ["find_class"]


def test_an_inheritdoc_block_gives_no_summary(tmp_path: Path) -> None:
    _plant(tmp_path)
    assert "summary" not in _nodes(tmp_path)["own.thing::Inherits"]["attributes"]


def test_a_long_summary_is_cut_at_300_characters(tmp_path: Path) -> None:
    _plant(tmp_path)
    summary = _nodes(tmp_path)["own.thing::Long"]["attributes"]["summary"]
    assert summary == LONG.strip()[:300].rstrip()
    assert len(summary) <= 300
    assert len(LONG.strip()) > 300


def test_whitespace_inside_a_summary_collapses_to_single_spaces(tmp_path: Path) -> None:
    _plant(tmp_path)
    assert _nodes(tmp_path)["own.thing::Spaced"]["attributes"]["summary"] == "Spaced out words."


def test_a_constant_attribute_keeps_its_text_as_written(tmp_path: Path) -> None:
    _plant(tmp_path)
    assert _nodes(tmp_path)["own.thing::Bare"]["attributes"] == {"kind": "plain  class"}


def test_an_attribute_naming_a_value_the_id_does_not_read_is_refused_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, template="{declared_name}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-home"))
    code = main(["map", "--output", "bad.json"])
    seen = capsys.readouterr()
    assert code != 0
    assert (
        "a declaration rule's attribute template names only the sources of its id"
        in seen.out + seen.err
    )
    assert not (tmp_path / "bad.json").exists()


def test_two_runs_give_the_same_bytes(tmp_path: Path) -> None:
    _plant(tmp_path)
    _map(tmp_path)
    first = (tmp_path / "map.json").read_bytes()
    _map(tmp_path)
    assert (tmp_path / "map.json").read_bytes() == first
    assert b"Runs the thing." in first
