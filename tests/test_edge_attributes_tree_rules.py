"""Every tree rule kind writes attributes on the edges it emits, from the values it binds.

The pack is an invented one on the PHP grammar, so it is also the proof that a third-party pack
writes edge attributes from a declaration, an attribute, an annotation and a reference rule with
no engine change. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, pin, plant, rutter

from periplus.errors import ExitCode

MANIFEST = """\
pack: kit
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./src
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
  comment: comment
"""

TYPES = """\
node_types:
- {name: kit.class, id_namespace: kit.class}
- {name: kit.method, id_namespace: kit.method}
- {name: kit.function, id_namespace: kit.function}
- {name: kit.mark, id_namespace: kit.mark}
- {name: kit.kit, id_namespace: kit.kit}
edge_kinds:
- {kind: contains, from: kit.class, to: kit.method}
- {kind: marks, from: kit.method, to: kit.mark}
- {kind: kit_of, from: kit.kit, to: kit.class}
- {kind: calls, from: kit.method, to: kit.function}
- {kind: elsewhere, from: kit.class, to: kit.class}
rules:
- rule: find_class
  reads: file
  in: [source]
  match:
    declaration: class_declaration
    name_child: name
    body_child: declaration_list
    filetype: php
  id: {from: qualified_name}
  emits: [{node: {type: kit.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: kit.method}}]
  confidence: declared
- rule: find_function
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: kit.function}}]
  confidence: declared
"""

#: One rule of each tree kind, each writing one edge attribute from what it binds.
DECLARATION = """\
- rule: contains_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits:
  - edge:
      kind: contains
      from: enclosing_class
      to: this_node
      attributes: {called: {template: '{declared_name}'}}
  confidence: declared
"""

ATTRIBUTE = """\
- rule: marks_from_attribute
  reads: file
  in: [source]
  match: {attribute: 'App\\Mark', filetype: php, where: [{applies_to: method_declaration}]}
  emits:
  - edge:
      kind: marks
      from: enclosing_method
      to: {from: {attribute_argument: '0'}}
      attributes: {weight: {from: {attribute_argument: weight}}}
  confidence: declared
"""

ANNOTATION = """\
- rule: kit_from_annotation
  reads: file
  in: [source]
  match: {annotation: Kit, filetype: php, where: [{applies_to: class_declaration}]}
  id: {from: {annotation_key: id}}
  emits:
  - edge:
      kind: kit_of
      from: this_node
      to: enclosing_class
      attributes: {role: {from: {annotation_key: role}}}
  confidence: declared
"""

REFERENCE = """\
- rule: calls_function
  reads: file
  in: [source]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits:
  - edge:
      kind: calls
      from: enclosing_declaration
      to: {types: [kit.function], on_miss: unresolved}
      attributes: {inside: {template: 'in {enclosing_method}'}}
  confidence: declared
"""

ALL = DECLARATION + ATTRIBUTE + ANNOTATION + REFERENCE

SOURCE = """\
<?php

namespace App;

/**
 * @Kit(id = "k1", role = "lead")
 */
class Thing
{
    #[Mark('tick', weight: 'heavy')]
    public function run(): void
    {
        helper();
    }

    #[Mark('tock')]
    public function stop(): void
    {
    }
}

function helper()
{
}
"""

NAMES = ("called", "weight", "role", "inside")
KINDS = {"called": "contains", "weight": "marks", "role": "kit_of", "inside": "calls"}
RULES = {
    "called": "contains_method",
    "weight": "marks_from_attribute",
    "role": "kit_from_annotation",
    "inside": "calls_function",
}


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def project(root: Path, rules: str = ALL, declare: str = "", other: str = "") -> None:
    files = {"kit.yaml": TYPES, "more.yaml": f"rules:\n{rules}"}
    if declare:
        files["attributes.yaml"] = declare
    rutter(root, "kit", MANIFEST, files)
    pins = ["kit@0.0.1"]
    if other:
        manifest = "pack: other\nversion: 0.0.1\ndepends: []\nfolders:\n  none: ./none\n"
        rutter(root, "other", manifest, {"other.yaml": other})
        pins.append("other@0.0.1")
    pin(root, *pins)
    plant(root, {"src/Thing.php": SOURCE})


def _mapped(root: Path) -> dict[str, Any]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def _edges(document: dict[str, Any], kind: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {(e["from"], e["to"]): e for e in document["edges"] if e["kind"] == kind}


def _refused(root: Path) -> list[tuple[ExitCode, str]]:
    report, document = map_project(root)
    assert document == {}
    return [(p.code, p.message) for p in report.problems]


def test_a_declaration_rule_writes_an_edge_attribute_from_its_id_sources(tmp_path: Path) -> None:
    project(tmp_path, DECLARATION)
    found = _edges(_mapped(tmp_path), "contains")
    run = found[("kit.class::App\\Thing", "kit.method::App\\Thing::run")]
    stop = found[("kit.class::App\\Thing", "kit.method::App\\Thing::stop")]
    assert (run["attributes"], stop["attributes"]) == ({"called": "run"}, {"called": "stop"})
    assert run["provenance"] == [
        {"pack": "kit", "rule": "contains_method", "confidence": "declared", "sets": ["called"]}
    ]


def test_an_attribute_rule_writes_an_edge_attribute_from_an_argument(tmp_path: Path) -> None:
    project(tmp_path, ATTRIBUTE)
    found = _edges(_mapped(tmp_path), "marks")
    assert found[("kit.method::App\\Thing::run", "kit.mark::tick")]["attributes"] == {
        "weight": "heavy"
    }
    # An argument the attribute does not give writes nothing.
    assert "attributes" not in found[("kit.method::App\\Thing::stop", "kit.mark::tock")]


def test_an_annotation_rule_writes_an_edge_attribute_from_a_key(tmp_path: Path) -> None:
    project(tmp_path, ANNOTATION)
    found = _edges(_mapped(tmp_path), "kit_of")
    assert found[("kit.kit::k1", "kit.class::App\\Thing")]["attributes"] == {"role": "lead"}


def test_a_reference_rule_writes_an_edge_attribute_from_its_template_values(
    tmp_path: Path,
) -> None:
    project(tmp_path, REFERENCE)
    found = _edges(_mapped(tmp_path), "calls")
    edge = found[("kit.method::App\\Thing::run", "kit.function::App\\helper")]
    assert edge["attributes"] == {"inside": "in run"}
    assert edge["provenance"] == [
        {"pack": "kit", "rule": "calls_function", "confidence": "declared", "sets": ["inside"]}
    ]


def test_without_attributes_the_tree_rules_give_the_same_map_less_the_attributes(
    tmp_path: Path,
) -> None:
    project(tmp_path / "with")
    plain = ALL
    for name in NAMES:
        plain = "\n".join(line for line in plain.split("\n") if f"{{{name}: " not in line)
    project(tmp_path / "without", plain)
    with_ = _mapped(tmp_path / "with")
    without = _mapped(tmp_path / "without")
    assert all("attributes" not in edge for edge in without["edges"])
    for edge in with_["edges"]:
        edge.pop("attributes", None)
        for row in edge["provenance"]:
            row.pop("sets", None)
    assert with_ == without


def test_a_declared_edge_attribute_on_a_kind_outside_on_is_refused_for_each_tree_rule(
    tmp_path: Path,
) -> None:
    declare = "edge_attributes:\n" + "".join(
        f"- {{name: {name}, on: [elsewhere]}}\n" for name in NAMES
    )
    project(tmp_path, declare=declare)
    assert sorted(_refused(tmp_path)) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            f"kit/rules/more.yaml: the rule {RULES[name]} writes the edge attribute {name} on "
            f"{KINDS[name]}, which the declaration of {name} does not list in on: elsewhere",
        )
        for name in ("inside", "called", "role", "weight")
    ]


def test_an_edge_attribute_another_rutter_declares_is_refused_for_each_tree_rule(
    tmp_path: Path,
) -> None:
    other = "edge_kinds:\n- {kind: ties, from: o.a, to: o.a}\nnode_types:\n- {name: o.a}\n"
    other += "edge_attributes:\n" + "".join(f"- {{name: {name}, on: [ties]}}\n" for name in NAMES)
    project(tmp_path, other=other)
    assert sorted(_refused(tmp_path)) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            f"kit/rules/more.yaml: the rule {RULES[name]} writes the edge attribute {name}, "
            "which neither kit nor a pack it depends on declares",
        )
        for name in ("inside", "called", "role", "weight")
    ]


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        (
            DECLARATION.replace("'{declared_name}'}", "'{namespace}'}"),
            "an edge attribute of a declaration rule is a template naming only the sources of "
            "its id",
        ),
        (
            REFERENCE.replace("{enclosing_method}", "{nothing}"),
            "an edge attribute of a reference rule is a template naming only enclosing_type, "
            "enclosing_method and the named groups of its name_matches conditions",
        ),
        (
            ATTRIBUTE.replace("{attribute_argument: weight}", "{annotation_key: weight}"),
            "an edge attribute of an attribute rule is from one attribute_argument",
        ),
        (
            ANNOTATION.replace("{annotation_key: role}}", "{attribute_argument: role}}"),
            "an edge attribute of an annotation rule is from one annotation_key",
        ),
    ],
    ids=["declaration", "reference", "attribute", "annotation"],
)
def test_an_edge_attribute_a_tree_rule_cannot_fill_is_not_executed(
    tmp_path: Path, rules: str, reason: str
) -> None:
    project(tmp_path, rules)
    report, _ = map_project(tmp_path)
    (problem,) = report.problems
    assert problem.code == ExitCode.RULE_NOT_EXECUTABLE
    assert problem.message.endswith(f"cannot be executed: {reason}")
