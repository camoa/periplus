"""What the pack check refuses about declared attributes, before any source file is read.

A map rule writes only an attribute its pack or a pack it depends on declares; any rule that writes
a declared attribute is held to it; one name is declared one way; a mark is short text with no
bracket and no line break. Every name here is invented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import map_project, nodes, pin, plant, rutter
from test_map_rule_attribute import BASE, DECLARE, MANIFEST, off, project

from periplus.errors import ExitCode

#: A second pack with its own type and a text rule that writes ``switched`` on it.
CART = MANIFEST.replace("box", "cart").replace("yard", "carts")
CART_RULES = r"""node_types:
- {name: cart.thing, id_namespace: cart.thing}
rules:
- rule: thing
  reads: file
  in: [carts]
  match: {file: '*', filetype: cart, text: '(?m)^thing (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: cart.thing}}, {attribute: {name: switched, template: 'off'}}]
  confidence: declared
"""


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _refused(root: Path) -> list[tuple[ExitCode, str]]:
    report, document = map_project(root)
    assert document == {}
    return [(p.code, p.message) for p in report.problems]


def _cart(root: Path, rules: str = CART_RULES) -> None:
    rutter(root, "cart", CART, {"a.yaml": rules})
    pin(root, "box@0.0.1", "cart@0.0.1")
    plant(root, {"carts/a.cart": "thing one\n"})


def test_a_map_rule_writing_an_undeclared_attribute_is_refused(tmp_path: Path) -> None:
    project(tmp_path, off(), declare="")
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/map.yaml: the rule unit_off writes the attribute switched, which neither "
            "box nor a pack it depends on declares",
        )
    ]


def test_a_write_on_its_own_node_of_a_type_outside_on_is_refused(tmp_path: Path) -> None:
    project(tmp_path, off(), declare=DECLARE.replace("on: [box.unit]", "on: [box.item]"))
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/map.yaml: the rule unit_off writes the attribute switched on box.unit, "
            "which is not at or below a type the declaration of switched lists in on: box.item",
        )
    ]


def test_an_attribute_declared_differently_in_another_pack_is_refused(tmp_path: Path) -> None:
    project(tmp_path, off())
    declared = CART_RULES.split("rules:")[0] + DECLARE.replace("on: [box.unit]", "on: [cart.thing]")
    _cart(tmp_path, declared)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "the attribute switched is declared with different types, spreads, mark or "
            "description in cart/rules/a.yaml, after box/rules/attributes.yaml",
        )
    ]


@pytest.mark.parametrize("mark", ["", "x" * 41, "a [b", "a] b", "a\nb"])
def test_a_mark_that_is_empty_long_bracketed_or_broken_is_a_schema_error(
    tmp_path: Path, mark: str
) -> None:
    declare = DECLARE.replace("mark: switched off", f"mark: {json.dumps(mark)}")
    project(tmp_path, off(), declare=declare)
    refused = _refused(tmp_path)
    assert [code for code, _ in refused] == [ExitCode.SCHEMA_INVALID], refused


def test_a_file_rule_writing_a_name_another_pack_declares_is_held_to_it(tmp_path: Path) -> None:
    project(tmp_path, off())
    _cart(tmp_path)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "cart/rules/a.yaml: the rule thing writes the attribute switched, which neither cart "
            "nor a pack it depends on declares",
        )
    ]


def test_a_file_rule_writing_an_undeclared_attribute_still_maps(tmp_path: Path) -> None:
    rule = BASE.replace(
        "emits: [{node: {type: box.unit}}]",
        "emits: [{node: {type: box.unit}}, {attribute: {name: note, template: 'kept'}}]",
    )
    rutter(tmp_path, "box", MANIFEST, {"box.yaml": rule})
    pin(tmp_path, "box@0.0.1")
    plant(tmp_path, {"yard/a.box": "unit A\n"})
    report, document = map_project(tmp_path)
    assert report.problems == (), report.problems
    assert nodes(document)["box.unit::A"]["attributes"] == {"note": "kept"}


def test_a_type_in_on_that_no_visible_pack_declares_is_refused(tmp_path: Path) -> None:
    declare = DECLARE.replace("on: [box.unit]", "on: [box.unit, box.nowhere]")
    project(tmp_path, off(), declare=declare)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/attributes.yaml: the attribute switched lists box.nowhere in on, which "
            "neither box nor a pack it depends on declares",
        )
    ]


def test_spreads_along_an_undeclared_kind_is_refused(tmp_path: Path) -> None:
    declare = DECLARE.replace(
        "mark: switched off}", "mark: switched off, spreads_along: [{kind: nowhere, to: to}]}"
    )
    project(tmp_path, off(), declare=declare)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/attributes.yaml: the attribute switched spreads along the edge kind "
            "nowhere, which neither box nor a pack it depends on declares",
        )
    ]


def test_spreads_along_without_spreads_is_refused(tmp_path: Path) -> None:
    declare = DECLARE.replace(
        "spreads: true, mark: switched off}",
        "mark: switched off, spreads_along: [{kind: lists, to: to}]}",
    )
    project(tmp_path, off(), declare=declare)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/attributes.yaml: the attribute switched lists spreads_along, which needs "
            "spreads: true",
        )
    ]
