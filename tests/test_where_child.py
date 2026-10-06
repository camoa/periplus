"""The mapping form of name_matches, ``{child, pattern}``: a condition that tests the whole text of
a named child, by field or by node type, on tree declaration and reference rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  call_arguments: arguments
  call_argument: argument
  call_literals: [string, encapsed_string]
  call_literal_content: [string_content]
"""

RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.view, id_namespace: own.view}
- {name: own.entry, id_namespace: own.entry}
edge_kinds:
- {kind: shows, from: own.fn, to: own.view}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: own.fn}}]
  confidence: declared
- rule: static
  reads: file
  in: [code]
  match:
    reference: scoped_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: scope, pattern: Reg}
    - name_matches: {child: name, pattern: get}
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
- rule: member
  reads: file
  in: [code]
  match:
    reference: member_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: object, pattern: '\\$svc'}
    - name_matches: {child: name, pattern: fetch}
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
- rule: typed
  reads: file
  in: [code]
  match:
    reference: member_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: variable_name, pattern: '\\$box'}
    - name_matches: open
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
- rule: entry
  reads: file
  in: [code]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where:
    - name_matches: {child: scope, pattern: Reg}
    - name_matches: add
  id: {from: {argument: 0}}
  emits: [{node: {type: own.entry}}]
  confidence: declared
"""

SOURCE = """\
<?php
namespace App;

function page()
{
    Reg::get('a');
    Reg::put('b');
    Other::get('c');
    $svc->fetch('m');
    $svc->drop('n');
    $other->fetch('o');
    $box->open('p');
    $this->box->open('q');
    $crate->open('r');
    Reg::add('x');
    Other::add('y');
    Reg::drop('z');
}
"""

ABSENT = """\
- rule: absent
  reads: file
  in: [code]
  match:
    reference: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: {child: nothing_here, pattern: '.*'}}]
  emits:
  - edge:
      kind: shows
      from: enclosing_declaration
      to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}
  confidence: declared
"""


def _map(root: Path, rules: str = RULES) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [own@0.0.1]\n")
    (pack / "pack.yaml").write_text(MANIFEST)
    (pack / "rules" / "own.yaml").write_text(rules)
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    return report, json.loads((root / "map.json").read_text())


def _edges(document: Any) -> set[tuple[str, str, str]]:
    return {(e["kind"], e["from"], e["to"]) for e in document["edges"]}


def _fires(report: MapReport) -> dict[str, int]:
    return {rule: fires for pack, rule, fires in report.executed if pack == "own"}


def test_a_reference_on_a_static_call_tests_its_scope_and_its_name(tmp_path: Path) -> None:
    """Reg::get('a') fits both conditions; Reg::put('b') fits only the scope, Other::get('c') only
    the name, and each makes nothing."""
    _, document = _map(tmp_path)
    assert ("shows", "own.fn::page", "own.view::a") in _edges(document)
    assert not {"own.view::b", "own.view::c"} & {e[2] for e in _edges(document)}, _edges(document)


def test_a_reference_on_a_member_call_tests_its_receiver(tmp_path: Path) -> None:
    """$svc->fetch('m') fits both; $svc->drop('n') fits only the receiver, $other->fetch('o')
    only the name."""
    _, document = _map(tmp_path)
    assert ("shows", "own.fn::page", "own.view::m") in _edges(document)
    assert not {"own.view::n", "own.view::o"} & {e[2] for e in _edges(document)}, _edges(document)


def test_a_child_named_by_node_type(tmp_path: Path) -> None:
    """variable_name is no field of a member call, so the condition reads its first named child of
    that type: $box->open('p') fits; $this->box->open('q') has no such child and $crate does not
    match. The string form beside it still tests the first name child."""
    _, document = _map(tmp_path)
    assert ("shows", "own.fn::page", "own.view::p") in _edges(document)
    assert not {"own.view::q", "own.view::r"} & {e[2] for e in _edges(document)}, _edges(document)


def test_the_whole_map_holds_only_the_matches_that_fit_every_condition(tmp_path: Path) -> None:
    """Three edges and one entry node, from the declaration rule on Reg::add('x'): Other::add('y')
    fails the scope and Reg::drop('z') the name."""
    _, document = _map(tmp_path)
    assert _edges(document) == {
        ("shows", "own.fn::page", "own.view::a"),
        ("shows", "own.fn::page", "own.view::m"),
        ("shows", "own.fn::page", "own.view::p"),
    }, _edges(document)
    entries = sorted(n["id"] for n in document["nodes"] if n["type"] == "own.entry")
    assert entries == ["own.entry::x"], entries


def test_a_match_failing_a_condition_leaves_no_row_and_is_no_fire(tmp_path: Path) -> None:
    """Each rule fires once, on its one fitting match, and no match leaves a skipped row."""
    report, _ = _map(tmp_path)
    assert report.skipped == (), report.skipped
    assert _fires(report) == {"fn": 1, "static": 1, "member": 1, "typed": 1, "entry": 1}, (
        report.executed
    )


def test_a_condition_naming_a_child_the_match_lacks_fails(tmp_path: Path) -> None:
    """No static call has a child nothing_here: the rule makes nothing, leaves no row, raises no
    problem and fires zero times."""
    report, document = _map(tmp_path, RULES + ABSENT)
    assert _fires(report)["absent"] == 0, report.executed
    assert report.skipped == (), report.skipped
    assert len(_edges(document)) == 3, _edges(document)
