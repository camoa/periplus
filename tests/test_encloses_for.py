"""``match.encloses_for``: a tree declaration rule of a dependent pack whose node is the enclosing
declaration of the reference rules of a pack it depends on, as that pack's own declaration rules
are, and wins over them at the same tree node."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

BASE = """\
pack: base
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
"""

#: ``fn`` maps each function; ``call`` starts at the nearest one around a call.
BASE_RULES = """\
node_types:
- {name: base.fn, id_namespace: base.fn}
edge_kinds:
- {kind: calls, from: base.fn, to: base.fn}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: base.fn}}]
  confidence: declared
- rule: call
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits: [{edge: {kind: calls, from: enclosing_declaration, to: {types: [base.fn], on_miss: unresolved}}}]
  confidence: declared
"""

EXT = "pack: ext\nversion: 0.0.1\ndepends: [base]\n"

#: ``unit_class`` maps a class, which base maps nothing for; ``unit_fn`` maps a function base's
#: ``fn`` maps too, at the same tree node.
EXT_RULES = """\
node_types:
- {{name: ext.unit, parent: {parent}, id_namespace: ext.unit}}
rules:
- rule: unit_class
  reads: file
  in: [code]
  match: {{declaration: class_declaration, name_child: name, body_child: body, filetype: php{encloses}}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: ext.unit}}}}]
  confidence: declared
- rule: unit_fn
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php, where: [{{name_matches: 'unit_.*'}}]{encloses}}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: ext.unit}}}}]
  confidence: declared
"""

SOURCE = """\
<?php

function alpha()
{
    beta();
}

function unit_one()
{
    beta();
}

class Widget
{
    public function run()
    {
        beta();
    }
}

function beta()
{
}
"""

ENCLOSES = ", encloses_for: [base]"


def _project(
    root: Path, ext_rules: str | None = None, encloses: str = ENCLOSES, parent: str = "base.fn"
) -> None:
    packs = ".periplus/packs"
    files = {
        f"{packs}/base@0.0.1/pack.yaml": BASE,
        f"{packs}/base@0.0.1/rules/base.yaml": BASE_RULES,
        "src/a.php": SOURCE,
    }
    pins = ["base@0.0.1"]
    if ext_rules is not None:
        files[f"{packs}/ext@0.0.1/pack.yaml"] = EXT
        files[f"{packs}/ext@0.0.1/rules/ext.yaml"] = ext_rules.format(
            encloses=encloses, parent=parent
        )
        pins.append("ext@0.0.1")
    files[".periplus/settings.yml"] = f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    plant(root, files)


def _run(root: Path) -> MapReport:
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _calls(root: Path) -> set[tuple[str, str]]:
    """The two ends of each calls edge."""
    report = _run(root)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((root / "map.json").read_text())
    return {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "calls"}


def test_the_dependent_node_starts_the_base_rule_edge(tmp_path: Path) -> None:
    _project(tmp_path, EXT_RULES)
    assert _calls(tmp_path) == {
        ("base.fn::alpha", "base.fn::beta"),
        ("ext.unit::unit_one", "base.fn::beta"),
        ("ext.unit::Widget", "base.fn::beta"),
    }


def test_without_the_key_or_the_dependent_nothing_changes(tmp_path: Path) -> None:
    plain, alone = tmp_path / "plain", tmp_path / "alone"
    _project(plain, EXT_RULES, encloses="")
    _project(alone)
    expected = {("base.fn::alpha", "base.fn::beta"), ("base.fn::unit_one", "base.fn::beta")}
    assert _calls(plain) == expected
    assert _calls(alone) == expected
    assert [s[2:] for s in _run(alone).skipped] == [("call", "no enclosing declaration is mapped")]
    assert (plain / "map.json").read_bytes().count(b"ext.unit::Widget") == 1


def test_the_map_is_the_same_bytes_from_two_folders(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _project(one, EXT_RULES)
    _project(two, EXT_RULES)
    _run(one)
    _run(two)
    assert (one / "map.json").read_bytes() == (two / "map.json").read_bytes()


def _refused(root: Path) -> list[str]:
    return [p.message for p in _run(root).problems]


def test_a_rule_that_is_not_a_tree_declaration_making_a_node_is_refused(tmp_path: Path) -> None:
    reference = """\
edge_kinds:
- {{kind: uses, from: base.fn, to: base.fn}}
rules:
- rule: use
  reads: file
  in: [code]
  match: {{reference: function_call_expression, name_child: function, filetype: php{encloses}}}
  emits: [{{edge: {{kind: uses, from: enclosing_declaration, to: {{types: [base.fn]}}}}}}]
  confidence: declared
"""
    edges_only = """\
edge_kinds:
- {{kind: holds, from: base.fn, to: base.fn}}
rules:
- rule: hold
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php{encloses}}}
  id: {{from: declared_name}}
  emits: [{{edge: {{kind: holds, from: this_node, to: this_node}}}}]
  confidence: declared
"""
    for name, rules, rule, reason in (
        ("reference", reference, "use", "only a tree declaration rule takes match.encloses_for"),
        ("edges", edges_only, "hold", "match.encloses_for needs a rule that emits a node"),
    ):
        root = tmp_path / name
        _project(root, rules)
        assert _refused(root) == [
            f"ext/rules/ext.yaml: the rule {rule} cannot be executed: {reason}"
        ]


def test_a_pack_the_rule_pack_does_not_depend_on_is_refused(tmp_path: Path) -> None:
    for name in ("ext", "other"):
        root = tmp_path / name
        _project(root, EXT_RULES, encloses=f", encloses_for: [{name}]")
        reason = (
            f"cannot be executed: match.encloses_for names the pack {name}, which the rule's pack "
            "does not depend on"
        )
        assert _refused(root) == [
            f"ext/rules/ext.yaml: the rule {rule} {reason}" for rule in ("unit_class", "unit_fn")
        ]


def test_a_type_no_reference_rule_of_the_pack_may_start_at_is_refused(tmp_path: Path) -> None:
    rules = EXT_RULES.replace("parent: {parent}, ", "")
    _project(tmp_path, rules)
    reason = (
        "cannot be executed: match.encloses_for names the pack base, no reference rule of which "
        "reads php, starts an edge at enclosing_declaration and has only edges of kinds that allow "
        "ext.unit at their from end"
    )
    assert _refused(tmp_path) == [
        f"ext/rules/ext.yaml: the rule {rule} {reason}" for rule in ("unit_class", "unit_fn")
    ]
