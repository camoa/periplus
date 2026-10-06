"""Tests for id.pattern on a tree declaration rule: search the one source, captures feed the
template, a non-match makes nothing, a {name} is a path or settings value taken as literal text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.engine import packload, rules
from periplus.engine.packload import Rule
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: hooks
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  types:
    module_file:
      endings: [module]
      reader: tree
      path_values:
        module:
          pattern: '^(?:.*/)?(?<name>[^/]+)\\.module$'
          template: '{name}'
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""

RULES = """\
node_types:
- name: hooks.hook
  id_namespace: hooks.hook
rules:
- rule: find_hook
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: module_file}
  id: ID
  emits: [{node: {type: hooks.hook}}]
  confidence: declared
"""

SOURCE = """\
<?php

function FIRST()
{
}

function SECOND()
{
}

function THIRD()
{
}
"""


def _map(root: Path, block: str, file: str, names: tuple[str, ...]) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "hooks@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - hooks@0.0.1\n"
    )
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "hooks.yaml").write_text(RULES.replace("ID", block))
    source = SOURCE
    for slot, name in zip(("FIRST", "SECOND", "THIRD"), names, strict=True):
        source = source.replace(slot, name)
    (root / file).write_text(source)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


def _fires(report: MapReport) -> int:
    return next(fires for _, rule, fires in report.executed if rule == "find_hook")


def test_a_capture_and_template_give_one_node_and_misses_make_nothing(tmp_path: Path) -> None:
    block = r"{from: declared_name, pattern: '^on_(?<event>\w+)$', template: '{event}'}"
    report, document = _map(tmp_path, block, "a.module", ("on_save", "helper", "save_on"))
    assert report.problems == ()
    assert [n["id"] for n in document["nodes"]] == ["hooks.hook::save"]
    assert document["edges"] == []
    assert report.skipped == ()
    assert _fires(report) == 1


def test_a_path_value_in_braces_anchors_the_name(tmp_path: Path) -> None:
    block = r"{from: declared_name, pattern: '^{module}_(?<hook>\w+)$', template: '{hook}'}"
    report, document = _map(
        tmp_path, block, "mymod.module", ("mymod_cron", "helper", "othermod_cron")
    )
    assert report.problems == ()
    assert [n["id"] for n in document["nodes"]] == ["hooks.hook::cron"]
    assert report.skipped == ()
    assert _fires(report) == 1


def test_a_path_value_with_a_dot_matches_only_itself(tmp_path: Path) -> None:
    # Unescaped, the dot of my.mod would let myxmod_cron fit.
    block = r"{from: declared_name, pattern: '^{module}_(?<hook>\w+)$', template: '{hook}'}"
    report, document = _map(tmp_path, block, "my.mod.module", ("myxmod_cron", "helper", "my_cron"))
    assert report.problems == ()
    assert document["nodes"] == []
    assert report.skipped == ()


@pytest.mark.parametrize(
    ("value", "fits", "misses"),
    [("my.mod", "my.mod_cron", "myxmod_cron"), ("a+b", "a+b_cron", "aab_cron")],
)
def test_a_value_in_the_pattern_is_literal_text(value: str, fits: str, misses: str) -> None:
    rule = Rule(
        "p",
        "r",
        True,
        (),
        "",
        "",
        "T",
        "declared",
        id_template="{hook}",
        id_pattern=r"^{module}_(?<hook>\w+)$",
        id_source="declared_name",
    )
    assert rules._node_id(rule, {"module": value, "declared_name": fits}) == "cron"
    assert rules._node_id(rule, {"module": value, "declared_name": misses}) is None


def test_an_absent_source_keeps_its_row(tmp_path: Path) -> None:
    plain = "{from: return_type}"
    patterned = r"{from: return_type, pattern: '^(?<kind>\w+)$', template: '{kind}'}"
    before, _ = _map(tmp_path / "plain", plain, "a.module", ("one", "two", "three"))
    after, _ = _map(tmp_path / "patterned", patterned, "a.module", ("one", "two", "three"))
    assert before.skipped != ()
    assert after.skipped == before.skipped


def _rule(id_block: dict[str, Any], match: dict[str, Any]) -> Rule:
    item = {
        "rule": "r",
        "reads": "file",
        "in": ["source"],
        "match": match,
        "id": id_block,
        "emits": [{"node": {"type": "T"}}],
        "confidence": "declared",
    }
    return packload._read_rule("p", item)


DECLARATION = {"declaration": "function_definition", "name_child": "name", "filetype": "php"}


@pytest.mark.parametrize(
    ("id_block", "match", "reason"),
    [
        (
            {"from": ["declared_name", "namespace"], "pattern": "x", "template": "{x}"},
            DECLARATION,
            "one source",
        ),
        (
            {"from": {"capture": "n"}, "pattern": "x"},
            {"text": "(?<n>a)", "filetype": "t"},
            "pattern",
        ),
        (
            {"from": {"attribute_argument": 0}, "pattern": "x"},
            {"attribute": "A", "filetype": "php", "where": [{"applies_to": "method_declaration"}]},
            "pattern",
        ),
        ({"from": {"argument": 0}, "pattern": "x"}, DECLARATION, "argument"),
    ],
)
def test_a_pattern_off_a_tree_declaration_source_is_refused_at_load(
    id_block: dict[str, Any], match: dict[str, Any], reason: str
) -> None:
    rule = _rule(id_block, match)
    assert not rule.supported
    assert reason in rule.reason
    assert "not executed" not in rule.reason


def test_a_capture_named_like_an_engine_filled_name_is_refused(tmp_path: Path) -> None:
    block = r"{from: declared_name, pattern: '^on_(?<namespace>\w+)$', template: '{namespace}'}"
    report, _ = _map(tmp_path, block, "a.module", ("on_save", "helper", "save_on"))
    assert [p.code for p in report.problems] == [26]
    assert "namespace" in report.problems[0].message
    assert "capture" in report.problems[0].message
