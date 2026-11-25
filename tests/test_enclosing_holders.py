"""Tests for the ends and conditions that read what encloses a match: ``enclosing_method`` and
``enclosing_class`` take a node of a type the edge allows, ``enclosing_method`` is a member of the
nearest holder, and the ``within`` and ``not_within`` conditions test the tree nodes between a
match and its nearest holder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_demo_b_support import clean_map, edge_set, plant, settings

PACK = """\
pack: probe
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
"""

# Sorts first: a node rule on the method that reads its return type as the name, of an internal
# type no edge below allows.
FIRST = """\
node_types:
- {name: probe.return, id_namespace: probe.return, internal: true}
rules:
- rule: return_type
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: return_type, filetype: php,
    where: [{has_child: named_type}]}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: probe.return}}]
  confidence: declared
"""

MAIN = """\
node_types:
- {name: probe.class, id_namespace: probe.class}
- {name: probe.method, id_namespace: probe.method}
- {name: probe.variable, id_namespace: probe.variable}
edge_kinds:
- {kind: probe_held_by, from: probe.variable, to: probe.method}
- {kind: probe_in_class, from: probe.variable, to: probe.class}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: probe.method}}]
  confidence: declared
- rule: variable
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id:
    from: [enclosing_type, enclosing_method, declared_name]
    template: '{enclosing_type}::{enclosing_method}::{declared_name}'
  emits: [{node: {type: probe.variable}}]
  confidence: declared
- rule: tie
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id:
    from: [enclosing_type, enclosing_method, declared_name]
    template: '{enclosing_type}::{enclosing_method}::{declared_name}'
  emits:
  - edge: {kind: probe_held_by, from: this_node, to: enclosing_method}
  - edge: {kind: probe_in_class, from: this_node, to: enclosing_class}
  confidence: declared
"""

# Sorts last, so its holder rule is listed ahead of find_class on the same class.
SHELL = """\
node_types:
- {name: probe.shell, id_namespace: probe.shell, internal: true}
rules:
- rule: shell
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.shell}}]
  confidence: declared
"""

THING = """\
<?php

namespace App;

class Thing
{
    public function run(Box $box): Reply
    {
    }
}
"""


def _probe(root: Path, rules: dict[str, str], source: str) -> None:
    folder = ".periplus/packs/probe@0.0.1"
    plant(
        root,
        {
            **settings("probe@0.0.1"),
            f"{folder}/pack.yaml": PACK,
            **{f"{folder}/rules/{name}": text for name, text in rules.items()},
            "Thing.php": source,
        },
    )


def _ids(document: Any, node_type: str) -> list[str]:
    return sorted(n["id"] for n in document["nodes"] if n["type"] == node_type)


def test_enclosing_method_takes_the_member_node_of_an_allowed_type(tmp_path: Path) -> None:
    """a_return.yaml sorts before b_main.yaml and fires first on run. The edge to
    enclosing_method still lands on the probe.method node, the type probe_held_by allows, and the
    variable's id reads run, the name the probe.method rule reads, not the internal rule's
    Reply."""
    _probe(tmp_path, {"a_return.yaml": FIRST, "b_main.yaml": MAIN}, THING)
    _, document = clean_map(tmp_path)
    assert _ids(document, "probe.variable") == ["probe.variable::App\\Thing::run::$box"]
    assert edge_set(document, "probe_held_by") == {
        (
            "probe_held_by",
            "probe.variable::App\\Thing::run::$box",
            "probe.method::App\\Thing::run",
        )
    }


def test_enclosing_class_takes_the_holder_node_of_an_allowed_type(tmp_path: Path) -> None:
    """c_shell.yaml loads last, so its holder rule is tried first on Thing. The edge to
    enclosing_class still lands on the probe.class node, the type probe_in_class allows."""
    _probe(tmp_path, {"b_main.yaml": MAIN, "c_shell.yaml": SHELL}, THING)
    _, document = clean_map(tmp_path)
    assert edge_set(document, "probe_in_class") == {
        (
            "probe_in_class",
            "probe.variable::App\\Thing::run::$box",
            "probe.class::App\\Thing",
        )
    }


SHAPES = """\
<?php

namespace App;

class Helper
{
    public function ping() {}
}

class Other
{
    public function ping() {}
}

class Shapes
{
    public function run(Helper $h)
    {
        $f = function (Other $h) {
            $h->ping();
        };
        $g = fn(Other $o) => $o?->ping();
        function nested_helper(Helper $n)
        {
            $n->ping();
            $k = function (Other $n) {
                $n->ping();
            };
        }
        $h->ping();
    }
}
"""


def _shapes(root: Path) -> Any:
    plant(root, {**settings("php_basic@0.3.0"), "src/Shapes.php": SHAPES})
    _, document = clean_map(root)
    return document


def test_a_named_function_inside_a_method_gets_no_method_rules(tmp_path: Path) -> None:
    """nested_helper sits in run. Its call $n->ping() is the function's call site, joined to the
    function, with the function's calls edge to Helper::ping; no rule mints a method
    nested_helper::run or its parameter."""
    document = _shapes(tmp_path)
    ids = {n["id"] for n in document["nodes"]}
    assert not [i for i in ids if "nested_helper::run" in i]
    assert "php.call_site::App\\nested_helper::$n->ping" in ids
    assert {
        (
            "call_site_in",
            "php.call_site::App\\nested_helper::$n->ping",
            "php.function::App\\nested_helper",
        ),
        ("calls", "php.function::App\\nested_helper", "php.method::App\\Helper::ping"),
    } <= edge_set(document)
    assert edge_set(document, "parameter_typed_as") >= {
        (
            "parameter_typed_as",
            "php.parameter::App\\nested_helper::$n",
            "php.parameter_type::App\\nested_helper::$n::App\\Helper",
        )
    }


def test_a_closure_parameter_does_not_join_the_method_parameter(tmp_path: Path) -> None:
    """The closure's Other $h and the arrow function's Other $o make no parameter, so run's $h is
    typed Helper alone and run calls Helper::ping only. Each call in a closure keeps a call site
    in run with no calls edge; so does the closure's call inside nested_helper."""
    document = _shapes(tmp_path)
    assert _ids(document, "php.parameter") == [
        "php.parameter::App\\Shapes::run::$h",
        "php.parameter::App\\nested_helper::$n",
    ]
    typed = {target for _, source, target in edge_set(document, "parameter_typed_as")}
    assert "php.parameter_type::App\\Shapes::$h::App\\Other" not in typed
    calls = {(source, target) for _, source, target in edge_set(document, "calls")}
    assert calls == {
        ("php.method::App\\Shapes::run", "php.method::App\\Helper::ping"),
        ("php.function::App\\nested_helper", "php.method::App\\Helper::ping"),
    }
    sites = {
        "php.call_site::App\\Shapes::run::closure()::$h->ping": "php.method::App\\Shapes::run",
        "php.call_site::App\\Shapes::run::closure()::$o?->ping": "php.method::App\\Shapes::run",
        "php.call_site::App\\nested_helper::closure()::$n->ping": (
            "php.function::App\\nested_helper"
        ),
    }
    assert {(s, o) for _, s, o in edge_set(document, "call_site_in") if s in sites} == set(
        sites.items()
    )


THIRD = """\
node_types:
- {name: own.unit, id_namespace: own.unit}
- {name: own.site, id_namespace: own.site}
rules:
- rule: unit_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.unit}}]
  confidence: declared
- rule: unit_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, body_child: body, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.unit}}]
  confidence: declared
- rule: plain_site
  reads: file
  in: [source]
  match: {declaration: function_call_expression, name_child: function, filetype: php,
    where: [{not_within: [anonymous_function, arrow_function]}]}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: own.site}}]
  confidence: declared
- rule: closure_site
  reads: file
  in: [source]
  match: {declaration: function_call_expression, name_child: function, filetype: php,
    where: [{within: [anonymous_function, arrow_function]}]}
  id: {from: [enclosing_type, declared_name],
    template: '{enclosing_type}::closure::{declared_name}'}
  emits: [{node: {type: own.site}}]
  confidence: declared
- rule: in_function_only
  reads: file
  in: [source]
  match: {declaration: function_call_expression, name_child: function, filetype: php,
    where: [{within: [function_definition]}, {not_within: [anonymous_function]}]}
  id: {from: [enclosing_type, declared_name], template: 'fn:{enclosing_type}::{declared_name}'}
  emits: [{node: {type: own.site}}]
  confidence: declared
"""

THIRD_SOURCE = """\
<?php
class Box
{
    public function run()
    {
        direct();
        $f = function () {
            in_closure();
            function inner()
            {
                in_inner();
            }
        };
        $g = fn() => in_arrow();
    }
}
function outer()
{
    in_outer();
}
"""


def test_a_third_party_rutter_tests_what_lies_between_a_match_and_its_holder(
    tmp_path: Path,
) -> None:
    """within and not_within read the tree nodes from the match up to its nearest holder, that
    holder included. inner sits in a closure, but it is in_inner's nearest holder, so the closure
    above it is not read: in_inner is a plain site, and in_function_only takes it with in_outer."""
    plant(
        tmp_path,
        {
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            ".periplus/packs/own@0.0.1/pack.yaml": PACK.replace("pack: probe", "pack: own"),
            ".periplus/packs/own@0.0.1/rules/own.yaml": THIRD,
            "src/Box.php": THIRD_SOURCE,
        },
    )
    report, document = clean_map(tmp_path)
    assert _ids(document, "own.site") == [
        "own.site::Box::closure::in_arrow",
        "own.site::Box::closure::in_closure",
        "own.site::Box::direct",
        "own.site::fn:inner::in_inner",
        "own.site::fn:outer::in_outer",
        "own.site::inner::in_inner",
        "own.site::outer::in_outer",
    ]
    assert report.skipped == ()


REFERENCES = """\
node_types:
- {name: own.unit, id_namespace: own.unit}
- {name: own.box, id_namespace: own.box}
edge_kinds:
- {kind: own_makes, from: [own.unit], to: [own.box]}
- {kind: own_makes_late, from: [own.unit], to: [own.box]}
rules:
- rule: box_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.box}}]
  confidence: declared
- rule: unit_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: own.unit}}]
  confidence: declared
- rule: makes_outside_labels
  reads: file
  in: [source]
  match: {reference: object_creation_expression, name_child: [name], filetype: php,
    where: [{not_within: [attribute_list]}]}
  emits: [{edge: {kind: own_makes, from: enclosing_declaration,
    to: {types: [own.box], on_miss: unresolved}}}]
  confidence: declared
- rule: makes_in_closures
  reads: file
  in: [source]
  match: {reference: object_creation_expression, name_child: [name], filetype: php,
    where: [{within: [anonymous_function]}]}
  emits: [{edge: {kind: own_makes_late, from: enclosing_declaration,
    to: {types: [own.box], on_miss: unresolved}}}]
  confidence: declared
"""

REFERENCES_SOURCE = """\
<?php
#[Label(new Tag('crate'))]
class Crate
{
    public function run()
    {
        new Crate();
        $f = function () {
            new Lid();
        };
    }
}
"""


def test_a_reference_rule_passes_over_a_match_its_within_conditions_leave_out(
    tmp_path: Path,
) -> None:
    """within and not_within on a reference rule read the tree nodes from the match up to its
    nearest holder, as on a declaration rule. new Tag in the class's attribute has no method to
    start an edge, and not_within passes it over with no skipped row; within keeps the closure's
    new Lid alone."""
    plant(
        tmp_path,
        {
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            ".periplus/packs/own@0.0.1/pack.yaml": PACK.replace("pack: probe", "pack: own"),
            ".periplus/packs/own@0.0.1/rules/own.yaml": REFERENCES,
            "src/Crate.php": REFERENCES_SOURCE,
        },
    )
    report, document = clean_map(tmp_path)
    assert report.skipped == ()
    assert edge_set(document, "own_makes") == {
        ("own_makes", "own.unit::Crate::run", "own.box::Crate"),
        ("own_makes", "own.unit::Crate::run", "own.box::Lid"),
    }
    assert edge_set(document, "own_makes_late") == {
        ("own_makes_late", "own.unit::Crate::run", "own.box::Lid"),
    }


def test_without_the_condition_the_reference_outside_any_method_lists_its_row(
    tmp_path: Path,
) -> None:
    """The same rule with no where lists new Tag as a match it could not finish."""
    rules = REFERENCES.replace("\n    where: [{not_within: [attribute_list]}]}", "}")
    plant(
        tmp_path,
        {
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            ".periplus/packs/own@0.0.1/pack.yaml": PACK.replace("pack: probe", "pack: own"),
            ".periplus/packs/own@0.0.1/rules/own.yaml": rules,
            "src/Crate.php": REFERENCES_SOURCE,
        },
    )
    report, _ = clean_map(tmp_path)
    assert report.skipped == (
        ("src/Crate.php", 2, "makes_outside_labels", "no enclosing declaration is mapped"),
    )


def test_the_map_is_the_same_bytes_from_two_folders(tmp_path: Path) -> None:
    """The fixtures of this file mapped in two folders give byte-identical maps."""
    first, second = tmp_path / "one", tmp_path / "two"
    for root in (first, second):
        _shapes(root)
        _probe(
            root / "probe",
            {"a_return.yaml": FIRST, "b_main.yaml": MAIN, "c_shell.yaml": SHELL},
            THING,
        )
        clean_map(root / "probe")
    assert (first / "map.json").read_bytes() == (second / "map.json").read_bytes()
    assert (first / "probe" / "map.json").read_bytes() == (
        second / "probe" / "map.json"
    ).read_bytes()
