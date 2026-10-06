"""Tests for the one bare-node-id function in the rules engine, and its four callers."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from periplus.engine import rules
from periplus.engine.packload import Rule
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MISSING = "<_node_id is absent>"

PACK = """\
pack: shapes
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
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
  attribute:
    node: attribute
    list: attribute_list
    arguments: parameters
    argument: argument
    argument_name: name
    literals: [string, encapsed_string]
    literal_content: string_content
"""

RULES = """\
node_types:
- name: shapes.class
  id_namespace: shapes.class
- name: shapes.method
  id_namespace: shapes.method
- name: shapes.function
  id_namespace: shapes.function
- name: shapes.mark
  id_namespace: shapes.mark
edge_kinds:
- kind: contains
  from: shapes.class
  to: shapes.method
- kind: calls
  from: shapes.method
  to: shapes.function
- kind: marks
  from: shapes.method
  to: shapes.mark
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name,
    body_child: declaration_list, filetype: php}
  id:
    from: qualified_name
    normalize: [{replace: '\\\\', with: '.'}]
  emits: [{node: {type: shapes.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: &method_id
    from: [enclosing_type, declared_name, parameters]
    template: '{enclosing_type}::{declared_name}{parameters}'
    normalize: [{replace: ' ?\\$\\w+', with: ''}, {replace: ', ', with: ','},
      {replace: '\\\\', with: '.'}]
  emits: [{node: {type: shapes.method}}]
  confidence: declared
- rule: contains_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: *method_id
  emits: [{edge: {kind: contains, from: enclosing_class, to: this_node}}]
  confidence: declared
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: shapes.function}}]
  confidence: declared
- rule: calls_function
  reads: file
  in: [source]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration,
    to: {types: [shapes.function], on_miss: unresolved}}}]
  confidence: declared
- rule: marks_from_attribute
  reads: file
  in: [source]
  match: {attribute: 'App\\Mark', filetype: php, where: [{applies_to: method_declaration}]}
  emits: [{edge: {kind: marks, from: enclosing_method, to: {from: {attribute_argument: '0'}}}}]
  confidence: declared
"""

SOURCE = """\
<?php

namespace App;

class Thing
{
    #[Mark('tick')]
    public function run(int $times, string $label): void
    {
        helper();
    }
}

function helper()
{
}
"""


def _rule(template: str, *steps: tuple[str, str]) -> Rule:
    return Rule(
        "p",
        "r",
        True,
        (),
        "",
        "",
        "T",
        "declared",
        id_template=template,
        normalize=tuple((re.compile(pattern), with_) for pattern, with_ in steps),
    )


def _call(rule: Rule, values: dict[str, str], *, empty_ok: bool = False) -> Any:
    node_id = getattr(rules, "_node_id", None)
    if node_id is None:
        return MISSING
    return node_id(rule, values, empty_ok=empty_ok)


def _plant(root: Path) -> None:
    pack = root / ".periplus" / "packs" / "shapes@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / "src").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - shapes@0.0.1\n"
    )
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "shapes.yaml").write_text(RULES)
    (root / "src" / "Thing.php").write_text(SOURCE)


def _map(root: Path) -> dict[str, Any]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == ()
    loaded: dict[str, Any] = json.loads((root / "map.json").read_text())
    return loaded


def test_node_id_gives_none_for_a_missing_key_Wo1() -> None:
    result = _call(_rule("{name}::{other}"), {"name": "a"})
    assert result is None


def test_node_id_gives_none_for_empty_text_before_normalize_Wo1() -> None:
    # The step would turn empty text into "X"; it must not run.
    result = _call(_rule("{name}", ("^$", "X")), {"name": ""})
    assert result is None


def test_node_id_with_empty_ok_normalizes_empty_text_Wo1() -> None:
    result = _call(_rule("{name}", ("^$", "X")), {"name": ""}, empty_ok=True)
    assert result == "X"


def test_node_id_applies_steps_in_order_with_no_namespace_Wo1() -> None:
    # Order matters: "a" -> "b" -> "c" only when the steps run first-to-last.
    rule = _rule("{ns}\\{name}", ("a", "b"), ("b", "c"), ("\\\\", "."))
    result = _call(rule, {"ns": "App", "name": "ab"})
    assert result == "App.cc"


def test_four_paths_build_one_id_for_one_thing_c2(tmp_path: Path) -> None:
    _plant(tmp_path)
    doc = _map(tmp_path)
    cls = [n["id"] for n in doc["nodes"] if n["id"].startswith("shapes.class::")]
    meth = [n["id"] for n in doc["nodes"] if n["id"].startswith("shapes.method::")]
    assert len(cls) == 1
    assert len(meth) == 1
    edges = {e["kind"]: e for e in doc["edges"]}
    assert edges["contains"]["from"] == cls[0]
    assert edges["contains"]["to"] == meth[0]
    assert edges["calls"]["from"] == meth[0]
    assert edges["marks"]["from"] == meth[0]


def test_each_of_four_functions_calls_node_id_Wo1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    callers: set[str] = set()
    real = getattr(rules, "_node_id", None)

    if real is not None:

        def spy(*args: Any, **kwargs: Any) -> Any:
            callers.add(sys._getframe(1).f_code.co_name)
            return real(*args, **kwargs)

        monkeypatch.setattr(rules, "_node_id", spy)
    _plant(tmp_path)
    _map(tmp_path)
    wanted = {"_declarations", "_minted", "_holder", "_enclosing"}
    assert wanted <= callers


def test_mypy_exits_zero_on_the_whole_source_c1() -> None:
    root = Path(__file__).resolve().parent.parent
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mypy"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout
