"""Tests for the ends that read what encloses a match: ``enclosing_method`` and
``enclosing_class`` take a node of a type the edge allows."""

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
