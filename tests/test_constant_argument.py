"""A call argument written as a class constant stands for the text the run read declared for it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

ACCESS = """\
  constant_access:
    node: class_constant_access_expression
    scope: [name, qualified_name, relative_scope]
    name: [name]
    enclosing: [self, static]
"""

DECLARATION = """\
  constant_declaration:
    node: const_element
    name: [name]
    value: [string, encapsed_string]
"""

# A rutter that owns the PHP grammar; {constants} is its grammar block's constant keys.
MANIFEST = """\
pack: own
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
{constants}folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
  call_argument: argument
  call_argument_name: name
  call_literals: [string, encapsed_string]
  call_literal_content: [string_content]
"""

RULES = """\
node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.method, id_namespace: own.method}
- {name: own.view, id_namespace: own.view}
edge_kinds:
- {kind: shows, from: own.method, to: own.view}
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts: {alias: alias, use_kind: type}
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\\\"
    skip_when_field_set: use_kind
# show runs first, so the first rule to read a file reads its arguments.
rules:
- rule: show
  reads: file
  in: [code]
  match:
    reference: function_call_expression
    name_child: function
    filetype: php
    where: [{name_matches: show}]
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
- rule: class
  reads: file
  in: [code]
  match:
    {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: method
  reads: file
  in: [code]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: "{enclosing_type}::{declared_name}"}
  emits: [{node: {type: own.method}}]
  confidence: declared
"""

USE = """\
<?php
namespace App\\Controller;

use App\\Entity\\MyType;

class Thing
{
    const OWN = 'own.view';

    public function run()
    {
        show(MyType::ENTITY_TYPE);
        show(self::OWN);
        show(static::OWN);
        show(MyType::BAD);
        show(Missing::X);
    }
}
"""

DECLARE = """\
<?php
namespace App\\Entity;

class MyType
{
    const ENTITY_TYPE = 'my_type';
    const BAD = 'a' . 'b';
}
"""

RUN = "own.method::App\\Controller\\Thing::run"


def _run(root: Path, constants: str, files: dict[str, str]) -> MapReport:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [own@0.0.1]\n")
    (pack / "pack.yaml").write_text(MANIFEST.format(constants=constants))
    (pack / "rules" / "own.yaml").write_text(RULES)
    (root / "src").mkdir()
    for name, source in files.items():
        (root / "src" / name).write_text(source)
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _map(root: Path, files: dict[str, str]) -> tuple[MapReport, Any]:
    report = _run(root, ACCESS + DECLARATION, files)
    assert report.problems == () and report.not_executed == (), report
    return report, json.loads((root / "map.json").read_text())


@pytest.mark.parametrize("names", [("a.php", "z.php"), ("z.php", "a.php")])
def test_a_constant_with_a_text_value_resolves_in_either_file_order(
    tmp_path: Path, names: tuple[str, str]
) -> None:
    """MyType::ENTITY_TYPE, imported from a file read after or before the use, and self::OWN and
    static::OWN of the enclosing class each end at the declared text."""
    _, document = _map(tmp_path, dict(zip(names, (USE, DECLARE), strict=True)))
    edges = sorted(
        (e["from"], e["to"], place["line"]) for e in document["edges"] for place in e["locations"]
    )
    assert edges == [
        (RUN, "own.view::my_type", 12),
        (RUN, "own.view::own.view", 13),
        (RUN, "own.view::own.view", 14),
    ], edges


def test_a_constant_with_no_declared_text_keeps_its_own_row(tmp_path: Path) -> None:
    """A constant declared by an expression, and one no mapped file declares, give no edge and
    the row that names a class constant."""
    report, _ = _map(tmp_path, {"a.php": USE, "z.php": DECLARE})
    rows = {(line, rule, reason) for _, line, rule, reason in report.skipped}
    assert rows == {
        (15, "show", "argument 0 is a class constant with no declared text"),
        (16, "show", "argument 0 is a class constant with no declared text"),
    }, rows


@pytest.mark.parametrize("constants", [ACCESS, DECLARATION])
def test_one_constant_key_without_the_other_is_refused(tmp_path: Path, constants: str) -> None:
    report = _run(tmp_path, constants, {"a.php": USE, "z.php": DECLARE})
    messages = [problem.message for problem in report.problems]
    assert messages and all(
        "constant_access" in m and "constant_declaration" in m for m in messages
    ), messages


def test_a_parent_scope_the_grammar_does_not_list_keeps_the_row(tmp_path: Path) -> None:
    """parent::OWN names no class the key lists, so it gives the row, not the child's text."""
    report, document = _map(tmp_path, {"a.php": USE.replace("self::OWN", "parent::OWN")})
    assert [e for e in document["edges"] if e["locations"][0]["line"] == 13] == [], document
    rows = {(line, reason) for _, line, _, reason in report.skipped}
    assert (13, "argument 0 is a class constant with no declared text") in rows, rows


def test_without_enclosing_no_scope_stands_for_the_enclosing_class(tmp_path: Path) -> None:
    """A manifest with no enclosing key gives self::OWN and static::OWN the row."""
    no_key = ACCESS.replace("    enclosing: [self, static]\n", "")
    report = _run(tmp_path, no_key + DECLARATION, {"a.php": USE, "z.php": DECLARE})
    assert report.problems == () and report.not_executed == (), report
    rows = {(line, reason) for _, line, _, reason in report.skipped}
    assert rows == {
        (line, "argument 0 is a class constant with no declared text") for line in (13, 14, 15, 16)
    }, rows


FUNCTION = """\
<?php
namespace App\\Controller;

use App\\Entity\\MyType;

function run()
{
    show(MyType::ENTITY_TYPE);
}
"""

# The first pack's rules come first and see no class rule; only the second pack's finds MyType.
FIRST_RULES = """\
node_types:
- {name: own.function, id_namespace: own.function}
- {name: own.view, id_namespace: own.view}
edge_kinds:
- {kind: shows, from: own.function, to: own.view}
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts: {alias: alias, use_kind: type}
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\\\"
    skip_when_field_set: use_kind
rules:
- rule: show
  reads: file
  in: [code]
  match:
    reference: function_call_expression
    name_child: function
    filetype: php
    where: [{name_matches: show}]
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
- rule: function
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.function}}]
  confidence: declared
"""

SECOND_RULES = """\
node_types:
- {name: other.class, id_namespace: other.class}
rules:
- rule: class
  reads: file
  in: [ocode]
  match:
    {declaration: class_declaration, name_child: name, body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: other.class}}]
  confidence: declared
"""


def test_constants_are_collected_with_a_class_rule_the_first_pack_cannot_see(
    tmp_path: Path,
) -> None:
    """The first PHP rule's pack does not depend on the pack whose rule finds MyType, and
    MyType::ENTITY_TYPE still ends at the declared text."""
    first = tmp_path / ".periplus" / "packs" / "own@0.0.1"
    second = tmp_path / ".periplus" / "packs" / "other@0.0.1"
    (first / "rules").mkdir(parents=True)
    (second / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [own@0.0.1, other@0.0.1]\n"
    )
    (first / "pack.yaml").write_text(MANIFEST.format(constants=ACCESS + DECLARATION))
    (first / "rules" / "own.yaml").write_text(FIRST_RULES)
    (second / "pack.yaml").write_text(
        "pack: other\nversion: 0.0.1\ndepends: [own]\nfolders:\n  ocode: ./src\n"
    )
    (second / "rules" / "other.yaml").write_text(SECOND_RULES)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.php").write_text(FUNCTION)
    (tmp_path / "src" / "z.php").write_text(DECLARE)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    edges = [(e["from"], e["to"]) for e in document["edges"]]
    assert edges == [("own.function::App\\Controller\\run", "own.view::my_type")], (
        edges,
        report.skipped,
    )
