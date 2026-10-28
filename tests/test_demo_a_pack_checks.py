"""A rutter the schemas accept and the engine cannot execute is reported, never half run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import map_project, mapped, pin, plant, rutter

from periplus.cli import main
from periplus.errors import ExitCode

IDLEKEYS = """\
pack: idlekeys
version: 0.0.1
depends: [yaml_basic]
folders:
  data: ./data
"""

IDLEKEYS_RULES = """\
node_types:
- {name: idlekeys.item, id_namespace: idlekeys.item}
rules:
- {rule: item_file, reads: file, in: [data], match: {file: '*', filetype: yml},
   id: {from: file_stem}, emits: [{node: {type: idlekeys.item}}], confidence: declared}
"""


def _idlekeys(root: Path) -> None:
    rutter(root, "idlekeys", IDLEKEYS, {"item.yaml": IDLEKEYS_RULES})
    pin(root, "idlekeys@0.0.1")
    plant(root, {"data/one.yml": "name: one\n"})


def test_the_same_rutter_without_the_idle_keys_maps(tmp_path: Path) -> None:
    _idlekeys(tmp_path)
    assert "idlekeys.item::one" in {n["id"] for n in mapped(tmp_path)["nodes"]}


def _plant_idle_keys(root: Path) -> None:
    """One key the schemas accept and nothing executes, in the manifest, in a pack file and in a
    rule."""
    _idlekeys(root)
    pack = ".periplus/packs/idlekeys@0.0.1"
    plant(
        root,
        {
            f"{pack}/pack.yaml": IDLEKEYS + "files:\n  cache_key_includes: [x]\n",
            f"{pack}/rules/planted.yaml": """\
recommendations:
- {topic: t, text: x}
rules:
- {rule: planted_rule, reads: file, in: [data], match: {file: '*', filetype: yml},
   id: {from: file_stem, on_miss: unresolved}, emits: [{node: {type: idlekeys.item}}],
   confidence: declared}
""",
        },
    )


def _named(messages: list[str]) -> None:
    for file, rule, key in (
        ("pack.yaml", "", "files.cache_key_includes"),
        ("rules/planted.yaml", "", "recommendations"),
        ("rules/planted.yaml", "the rule planted_rule ", "id.on_miss"),
    ):
        assert [m for m in messages if f"idlekeys/{file}" in m and rule in m and f" {key}" in m], (
            file,
            rule,
            key,
            messages,
        )


def test_a_key_nothing_executes_is_reported_by_map_with_the_key_and_the_file_named(
    tmp_path: Path,
) -> None:
    _plant_idle_keys(tmp_path)
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.RULE_NOT_EXECUTABLE
    _named([p.message for p in report.problems if p.code == ExitCode.RULE_NOT_EXECUTABLE])


def test_a_key_nothing_executes_is_reported_by_status_with_the_same_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant_idle_keys(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))
    assert main(["status", "--format", "json"]) == ExitCode.RULE_NOT_EXECUTABLE
    problems = json.loads(capsys.readouterr().out)["problems"]
    _named([p["message"] for p in problems if p["code"] == ExitCode.RULE_NOT_EXECUTABLE])


SHAPES = "pack: shapes\nversion: 0.0.1\ndepends: [yaml_basic]\nfolders:\n  data: ./data\n"
ABSTRACT = "node_types:\n- {name: shapes.shape, id_namespace: shapes.shape, abstract: true}\n"
SHAPE_RULE = """\
rules:
- {rule: shape_file, reads: file, in: [data], match: {file: '*', filetype: yml},
   id: {from: file_stem}, emits: [{node: {type: shapes.shape}}], confidence: declared}
"""


def test_a_rule_emitting_a_node_of_a_type_its_pack_declares_abstract_is_refused(
    tmp_path: Path,
) -> None:
    rutter(tmp_path, "shapes", SHAPES, {"shape.yaml": ABSTRACT + SHAPE_RULE})
    pin(tmp_path, "shapes@0.0.1")
    plant(tmp_path, {"data/one.yml": "name: one\n"})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    assert [dict(p.detail) for p in report.problems] == [
        {"pack": "shapes", "rule": "shape_file", "type": "shapes.shape", "declared_by": "shapes"}
    ]


def test_a_rule_in_another_rutter_than_the_one_declaring_the_type_abstract_names_both(
    tmp_path: Path,
) -> None:
    declaring = "pack: shapes\nversion: 0.0.1\ndepends: []\n"
    rutter(tmp_path, "shapes", declaring, {"shape.yaml": ABSTRACT})
    rutter(
        tmp_path,
        "circles",
        "pack: circles\nversion: 0.0.1\ndepends: [shapes, yaml_basic]\nfolders:\n  data: ./data\n",
        {"circle.yaml": SHAPE_RULE.replace("shape_file", "circle_file")},
    )
    pin(tmp_path, "shapes@0.0.1", "circles@0.0.1")
    plant(tmp_path, {"data/one.yml": "name: one\n"})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    refused = [p for p in report.problems if p.code == ExitCode.PACK_RULES_UNREADABLE]
    assert len(refused) == 1, report.problems
    assert "circles/rules/circle.yaml" in refused[0].message
    assert dict(refused[0].detail) == {
        "pack": "circles",
        "rule": "circle_file",
        "type": "shapes.shape",
        "declared_by": "shapes",
    }
