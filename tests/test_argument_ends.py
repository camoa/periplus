"""A reference end and a declaration id from a call's argument, and the name_matches filter on
tree declaration and reference rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

# A rutter that owns the PHP grammar itself, so its identity block alone names the call's
# arguments field: {field} is that line, or nothing for the default.
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
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
  attribute:
    node: attribute
    list: attribute_list
    arguments: parameters
    argument: argument
    argument_name: name
    literals: [string, encapsed_string]
    literal_content: string_content
  call_argument: argument
  call_argument_name: name
  call_literals: [string, encapsed_string]
  call_literal_content: [string_content]
{field}"""

RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.view, id_namespace: own.view}
- {name: own.entry, id_namespace: own.entry}
- {name: own.sig, id_namespace: own.sig}
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
- rule: entry
  reads: file
  in: [code]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: add}]
  id: {from: {argument: 0}}
  emits: [{node: {type: own.entry}}]
  confidence: declared
- rule: sig
  reads: file
  in: [code]
  match:
    declaration: function_definition
    name_child: name
    filetype: php
    where: [{name_matches: 'keep_.*'}]
  id: {from: [declared_name, return_type], template: '{declared_name}:{return_type}'}
  emits: [{node: {type: own.sig}}]
  confidence: declared
"""

SOURCE = """\
<?php
namespace App;

function page()
{
    show('a.b');
    show();
    show($name);
    other('c.d');
    Reg::add('x');
    Reg::add($v);
    Reg::add();
    Reg::drop('y');
    showcase('e.f');
}

function keep_a(): int {}
function drop_d() {}
function keep_b() {}
function drop_c(): int {}

function blank()
{
    show('');
    Reg::add('');
}
"""


def _run(
    root: Path,
    field: str = "  call_arguments: arguments\n",
    rules: str = RULES,
    source: str = SOURCE,
    manifest: str = MANIFEST,
) -> MapReport:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [own@0.0.1]\n")
    (pack / "pack.yaml").write_text(manifest.format(field=field))
    (pack / "rules" / "own.yaml").write_text(rules)
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(source)
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _map(root: Path, field: str = "  call_arguments: arguments\n") -> tuple[MapReport, Any]:
    report = _run(root, field)
    assert report.problems == () and report.not_executed == (), report
    return report, json.loads((root / "map.json").read_text())


def _rows(report: MapReport) -> set[tuple[int, str, str]]:
    return {(line, rule, reason) for _, line, rule, reason in report.skipped}


def test_a_literal_argument_end_skips_the_grammar_resolve(tmp_path: Path) -> None:
    """show('a.b') in the namespace App ends at own.view::a.b, not App\\a.b; the end's own
    on_miss makes it unresolved, searched for as written."""
    _, document = _map(tmp_path)
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == {("shows", "own.fn::page", "own.view::a.b")}, edges
    nodes = {n["id"]: n for n in document["nodes"]}
    assert nodes["own.view::a.b"]["state"] == "unresolved", nodes
    assert nodes["own.view::a.b"]["unresolved_detail"]["searched_for"] == "a.b"


def test_a_missing_or_non_literal_argument_leaves_a_row_and_no_edge_or_node(
    tmp_path: Path,
) -> None:
    """On both rule kinds, and an empty literal on both; other(), showcase() and Reg::drop() fail
    the filter, which matches the whole name, and leave nothing; keep_b lacks the return type its id
    names, and its row stays at its line though drop_d before it, which the filter passes over,
    lacks it too."""
    report, _ = _map(tmp_path)
    assert _rows(report) == {
        (7, "show", "argument 0 is missing"),
        (8, "show", "argument 0 is not a text literal"),
        (11, "entry", "argument 0 is not a text literal"),
        (12, "entry", "argument 0 is missing"),
        (19, "sig", "the id source return_type is absent"),
        (24, "show", "argument 0 is empty"),
        (25, "entry", "argument 0 is empty"),
    }, _rows(report)


def test_an_id_from_an_argument_and_the_name_filter_on_a_declaration(tmp_path: Path) -> None:
    """Reg::add('x') is the one entry; Reg::drop('y') fails the filter and Reg::add('') gives none.
    Of the four functions named keep_ or drop_ only keep_a gets a signature node: keep_b has no
    return type, and drop_c and drop_d fail the filter."""
    _, document = _map(tmp_path)
    ids = sorted(n["id"] for n in document["nodes"] if n["state"] == "mapped")
    assert ids == [
        "own.entry::x",
        "own.fn::blank",
        "own.fn::drop_c",
        "own.fn::drop_d",
        "own.fn::keep_a",
        "own.fn::keep_b",
        "own.fn::page",
        "own.sig::keep_a:int",
    ], ids


@pytest.mark.parametrize(
    ("field", "read"),
    [
        ("  call_arguments: arguments\n", True),
        ("", True),
        ("  call_arguments: parameters\n", False),
    ],
)
def test_the_call_arguments_field_comes_from_the_grammar(
    tmp_path: Path, field: str, read: bool
) -> None:
    """Set to the call's field, or left to its default, the argument is read; set to the
    attribute's field, every argument is missing."""
    report, document = _map(tmp_path, field)
    shows = [e for e in document["edges"] if e["kind"] == "shows"]
    entries = [n for n in document["nodes"] if n["id"].startswith("own.entry::")]
    assert (len(shows), len(entries)) == ((1, 1) if read else (0, 0)), (shows, entries)
    missing = {(6, "show", "argument 0 is missing"), (10, "entry", "argument 0 is missing")}
    assert (missing <= _rows(report)) is not read, _rows(report)


def test_an_id_from_an_argument_with_a_body_child_is_not_run(tmp_path: Path) -> None:
    """A rule whose id is a call's argument cannot hold the class or method an enclosing id
    names."""
    group = """\
- rule: group
  reads: file
  in: [code]
  match:
    declaration: scoped_call_expression
    name_child: name
    body_child: arguments
    filetype: php
  id: {from: {argument: 0}}
  emits: [{node: {type: own.entry}}]
  confidence: declared
"""
    report = _run(tmp_path, rules=RULES + group)
    assert [p.message for p in report.problems] == [
        "own/rules/own.yaml: the rule group cannot be executed: an id from a call's argument cannot"
        " be combined with match.body_child"
    ], report.problems


def test_an_argument_end_runs_its_own_resolve_steps(tmp_path: Path) -> None:
    """The end's own prefix_with step runs on the literal: show('a.b') in the namespace App ends at
    own.view::App\\a.b."""
    end = "to: {from: {argument: 0}, types: [own.view], on_miss: unresolved}"
    stepped = "to: {from: {argument: 0}, resolve: [prefix_with: namespace], types: [own.view]}"
    report = _run(tmp_path, rules=RULES.replace(end, stepped))
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == {("shows", "own.fn::page", "own.view::App\\a.b")}, edges


def test_a_node_from_an_argument_is_never_a_reference_from_end(tmp_path: Path) -> None:
    """show('v') inside the closure Reg::add('x', ...) holds runs from the function hold, though
    the edge kind allows own.entry at its from end and own.entry::x is mapped."""
    rules = RULES.replace("{kind: shows, from: own.fn,", "{kind: shows, from: [own.fn, own.entry],")
    source = """\
<?php
namespace App;

function hold()
{
    Reg::add('x', function () { show('v'); });
}
"""
    report = _run(tmp_path, rules=rules, source=source)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    assert "own.entry::x" in {n["id"] for n in document["nodes"]}, document["nodes"]
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == {("shows", "own.fn::hold", "own.view::v")}, edges


@pytest.mark.parametrize("declared", [True, False])
def test_a_declared_delimiter_is_skipped_in_a_call_literal(tmp_path: Path, declared: bool) -> None:
    """show("b\\n") holds an escape_sequence beside its text: declared in call_literal_delimiters it
    is skipped and the literal is b; undeclared, argument 0 is not a text literal."""
    field = "  call_arguments: arguments\n"
    if declared:
        field += "  call_literal_delimiters: [escape_sequence]\n"
    source = '<?php\nnamespace App;\n\nfunction page()\n{\n    show("b\\n");\n}\n'
    report = _run(tmp_path, field=field, source=source)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == ({("shows", "own.fn::page", "own.view::b")} if declared else set()), edges
    assert _rows(report) == (
        set() if declared else {(6, "show", "argument 0 is not a text literal")}
    ), _rows(report)


@pytest.mark.parametrize("declared", [True, False])
def test_a_named_call_argument_is_not_at_its_position(tmp_path: Path, declared: bool) -> None:
    """show(x: 'c') passes its argument by name: with call_argument_name it is not argument 0;
    without the key, the same argument is read at position 0."""
    manifest = MANIFEST if declared else MANIFEST.replace("  call_argument_name: name\n", "")
    source = "<?php\nnamespace App;\n\nfunction page()\n{\n    show(x: 'c');\n}\n"
    report = _run(tmp_path, source=source, manifest=manifest)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == (set() if declared else {("shows", "own.fn::page", "own.view::c")}), edges
    missing = {(6, "show", "argument 0 is missing")}
    assert _rows(report) == (missing if declared else set()), _rows(report)
