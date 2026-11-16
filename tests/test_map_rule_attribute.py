"""A map rule writes a declared attribute on the node it matched or on the node it reached.

The pack is a neutral one: a yard of units, items in units, and a list naming the units that are
on. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import edges, map_project, nodes, pin, plant, rutter

from periplus.engine.packload import _read_rule
from periplus.errors import ExitCode

MANIFEST = """\
pack: box
version: 0.0.1
depends: []
folders:
  yard: ./yard
files:
  types:
    box:
      endings: [box]
      reader: text
"""

#: ``unit <name>`` is a unit, ``item <unit> <name>`` an item in a unit, ``on <unit>`` lists a unit.
BASE = r"""node_types:
- {name: box.unit, id_namespace: box.unit}
- {name: box.item, id_namespace: box.item}
- {name: box.list, id_namespace: box.list}
edge_kinds:
- {kind: item_in_unit, from: box.item, to: box.unit, groups: true}
- {kind: lists, from: box.list, to: box.unit}
rules:
- rule: unit
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^unit (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: box.unit}}]
  confidence: declared
- rule: item
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^item (?<unit>\w+) (?<name>\w+)'}
  id: {template: '{unit}.{name}'}
  emits: [{node: {type: box.item}}]
  confidence: declared
- rule: item_unit
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^item (?<unit>\w+) (?<name>\w+)'}
  id: {template: '{unit}.{name}'}
  emits: [{edge: {kind: item_in_unit, from: this_node, to: {template: '{unit}', type: box.unit}}}]
  confidence: declared
- rule: list
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^on (?<name>\w+)'}
  id: {template: 'on'}
  emits: [{node: {type: box.list}}]
  confidence: declared
- rule: list_unit
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^on (?<name>\w+)'}
  id: {template: 'on'}
  emits: [{edge: {kind: lists, from: this_node, to: {template: '{name}', type: box.unit}}}]
  confidence: declared
"""

DECLARE = """\
attributes:
- {name: switched, on: [box.unit], spreads: true, mark: switched off}
"""

#: A unit no list names is switched off.
UNIT_OFF = """\
- rule: {name}
  reads: map
  match:
    node_type: box.unit
    follow: [{{node: 'box.list::on'}}]
    unless: [[{{incoming_edge: lists}}]]
  emits:
  - attribute: {{name: switched, template: '{value}'}}
  confidence: inferred
"""

#: The list writes on each unit it names.
LIST_ON = """\
- rule: list_on
  reads: map
  match:
    node_type: box.list
    follow: [{edge: lists}]
  emits:
  - attribute: {name: switched, template: 'on', target: matched_node}
  confidence: inferred
"""

YARD = "unit A\nunit B\nitem A f\nitem B g\non A\n"


def project(root: Path, rules: str, yard: str = YARD, declare: str = DECLARE) -> None:
    """The box pack with ``rules`` as its map rules and ``declare`` as its attributes file."""
    files = {"box.yaml": BASE, "map.yaml": f"rules:\n{rules}"}
    if declare:
        files["attributes.yaml"] = declare
    rutter(root, "box", MANIFEST, files)
    pin(root, "box@0.0.1")
    plant(root, {"yard/a.box": yard})


def off(name: str = "unit_off", value: str = "off") -> str:
    return UNIT_OFF.format(name=name, value=value)


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _row(node: dict[str, Any], rule: str) -> list[dict[str, Any]]:
    return [row for row in node["provenance"] if row["rule"] == rule]


def test_a_map_rule_writes_the_attribute_on_the_node_it_matched(tmp_path: Path) -> None:
    project(tmp_path, off())
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    unit = nodes(document)["box.unit::B"]
    assert unit["attributes"] == {"switched": "off"}
    assert unit["type"] == "box.unit"
    assert unit["locations"] == [{"file": "yard/a.box", "line": 2}]
    assert _row(unit, "unit_off") == [
        {"pack": "box", "rule": "unit_off", "confidence": "inferred", "sets": ["switched"]}
    ]
    assert "attributes" not in nodes(document)["box.unit::A"]


def test_a_matched_node_target_writes_on_the_reached_node_at_its_own_place(tmp_path: Path) -> None:
    project(tmp_path, LIST_ON)
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    unit = nodes(document)["box.unit::A"]
    assert unit["attributes"] == {"switched": "on"}
    assert unit["locations"] == [{"file": "yard/a.box", "line": 1}]
    assert "attributes" not in nodes(document)["box.list::on"]


def test_a_target_no_rule_found_is_skipped_and_stays_referenced(tmp_path: Path) -> None:
    project(tmp_path, LIST_ON, yard="unit A\non C\n")
    report, document = map_project(tmp_path)
    assert report.problems == (), report
    unit = nodes(document)["box.unit::C"]
    assert unit["state"] == "referenced" and "attributes" not in unit, unit
    assert (
        "yard/a.box",
        2,
        "list_on",
        "attribute switched: box.unit::C is no node a rule found",
    ) in report.skipped


def test_a_target_of_a_type_outside_on_is_skipped(tmp_path: Path) -> None:
    rule = """\
- rule: unit_list
  reads: map
  match:
    node_type: box.unit
    follow: [{node: 'box.list::on'}]
  emits:
  - attribute: {name: switched, template: 'x', target: matched_node}
  confidence: inferred
"""
    project(tmp_path, rule)
    report, document = map_project(tmp_path)
    assert report.problems == (), report
    assert "attributes" not in nodes(document)["box.list::on"]
    assert (
        "yard/a.box",
        1,
        "unit_list",
        "attribute switched: box.list::on is a box.list, which the attribute's on does not list",
    ) in report.skipped


def test_two_rules_giving_one_value_write_it_once_with_two_rows(tmp_path: Path) -> None:
    project(tmp_path, off() + off("unit_off_too"))
    report, document = map_project(tmp_path)
    assert report.problems == (), report
    unit = nodes(document)["box.unit::B"]
    assert unit["attributes"] == {"switched": "off"}
    assert len(_row(unit, "unit_off")) == 1 and len(_row(unit, "unit_off_too")) == 1


def test_two_rules_at_one_place_with_different_values_both_show(tmp_path: Path) -> None:
    project(tmp_path, off() + off("unit_dim", "dim"))
    report, document = map_project(tmp_path)
    assert report.problems == (), report
    assert nodes(document)["box.unit::B"]["attributes"] == {
        "switched": {
            "differs": [
                {"file": "yard/a.box", "line": 2, "value": "dim"},
                {"file": "yard/a.box", "line": 2, "value": "off"},
            ]
        }
    }
    assert ("box.unit::B", "switched") in report.differing


def test_a_map_rule_writing_on_the_containing_node_is_not_executed(tmp_path: Path) -> None:
    rule = LIST_ON.replace("target: matched_node", "target: containing_node")
    project(tmp_path, rule)
    report, document = map_project(tmp_path)
    assert document == {}
    assert [p.code for p in report.problems] == [ExitCode.RULE_NOT_EXECUTABLE], report.problems


def test_an_attribute_rule_with_an_attribute_target_is_not_executed() -> None:
    """An attribute rule reads no other key of its attribute emits, so it would drop a target."""
    item = {
        "rule": "unit_note",
        "reads": "file",
        "in": ["yard"],
        "match": {"attribute": "Unit", "filetype": "box", "where": [{"applies_to": "class"}]},
        "id": {"from": {"attribute_argument": "name"}},
        "emits": [
            {"node": {"type": "box.unit"}},
            {
                "attribute": {
                    "name": "note",
                    "from": {"attribute_argument": "note"},
                    "target": "this_node",
                }
            },
        ],
        "confidence": "declared",
    }
    rule = _read_rule("box", item)
    assert not rule.supported
    assert rule.reason == "only a map rule takes attribute.target"


def test_a_map_rule_writes_an_attribute_beside_an_edge(tmp_path: Path) -> None:
    kind = "edge_kinds:\n- {kind: off_by, from: box.unit, to: box.list}\n"
    rule = off().replace(
        "  - attribute:",
        "  - edge: {kind: off_by, from: this_node, to: matched_node}\n  - attribute:",
    )
    project(tmp_path, rule, declare=DECLARE + kind)
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert nodes(document)["box.unit::B"]["attributes"] == {"switched": "off"}
    assert ("off_by", "box.unit::B", "box.list::on") in edges(document)
