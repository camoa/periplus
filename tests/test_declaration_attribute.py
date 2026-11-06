"""A declaration rule may mark its node with a constant attribute (wo1)."""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from _own_pack import plant

from periplus.cli import main
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

RULES = """\
node_types:
- name: own.thing
  id_namespace: own.thing
rules:
- rule: thing_from_call
  reads: file
  in:
  - source
  match:
    declaration: member_call_expression
    name_child: name
    filetype: php
  id:
    from: declared_name
  emits:
  - node:
      type: own.thing
{attribute}  confidence: declared
"""
MARK = "  - attribute:\n      name: resolution\n      template: {template}\n"


def _plant(root: Path, attribute: str = "") -> None:
    plant(root, RULES.format(attribute=attribute))


@pytest.mark.criterion(id="wo1")
def test_constant_attribute_lands_on_the_found_node_and_its_provenance_wo1(tmp_path: Path) -> None:
    _plant(tmp_path, MARK.format(template="runtime"))
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-home")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    assert report.map_path is not None
    document = json.loads(Path(report.map_path).read_text())
    (node,) = document["nodes"]
    assert node["attributes"]["resolution"] == "runtime"
    assert "resolution" in node["provenance"][0]["sets"]


@pytest.mark.criterion(id="wo1")
def test_attribute_template_with_a_placeholder_is_refused_at_load_wo1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "  - attribute:\n      name: kind\n      template: '{name}'\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config-home"))
    code = main(["map", "--output", "bad.json"])
    seen = capsys.readouterr()
    assert code != 0
    assert "a declaration rule's attribute template is constant text" in seen.out + seen.err
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.criterion(id="wo1")
def test_map_schema_allows_only_runtime_for_the_resolution_attribute_wo1(tmp_path: Path) -> None:
    _plant(tmp_path)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-home")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.map_path is not None
    document: dict[str, Any] = json.loads(Path(report.map_path).read_text())
    schema = json.loads(
        (resources.files("periplus.contract") / "schema" / "map.schema.json").read_text()
    )
    validator = jsonschema.Draft202012Validator(schema)
    marked = copy.deepcopy(document)
    marked["nodes"][0]["attributes"] = {"resolution": "runtime"}
    other = copy.deepcopy(document)
    other["nodes"][0]["attributes"] = {"resolution": "static"}
    assert validator.is_valid(marked)
    assert not validator.is_valid(other)
