"""A declared attribute that spreads reaches the members of a container through grouping kinds.

The map holds the spread value and a provenance row for it, and its header names the mark of each
marked attribute a node holds. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, nodes
from test_map_rule_attribute import DECLARE, LIST_ON, YARD, off, project

#: Parts in items, by a second grouping kind, and ``also <item> <unit>`` putting an item in a second
#: unit; added to the attributes file and the map rules file.
PARTS_TYPES = """\
node_types:
- {name: box.part, id_namespace: box.part}
edge_kinds:
- {kind: part_in_item, from: box.part, to: box.item, groups: true}
"""
PARTS = r"""- rule: part
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^part (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{item}.{name}'}
  emits: [{node: {type: box.part}}]
  confidence: declared
- rule: part_item
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^part (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{item}.{name}'}
  emits: [{edge: {kind: part_in_item, from: this_node, to: {template: '{item}', type: box.item}}}]
  confidence: CONFIDENCE
- rule: also
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^also (?<item>[\w.]+) (?<unit>\w+)'}
  id: {template: '{item}'}
  emits: [{edge: {kind: item_in_unit, from: this_node, to: {template: '{unit}', type: box.unit}}}]
  confidence: declared
"""

#: An item whose name ends in g holds a value of its own.
ITEM_OWN = """\
- rule: item_own
  reads: map
  match:
    node_type: box.item
    where: [{id_matches: 'g$'}]
  emits:
  - attribute: {name: switched, template: own}
  confidence: declared
"""

BOTH = DECLARE.replace("on: [box.unit]", "on: [box.unit, box.item]")


def _parts(confidence: str = "declared") -> str:
    return PARTS.replace("CONFIDENCE", confidence)


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _mapped(root: Path) -> tuple[Any, dict[str, Any]]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def _spread_rows(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in node["provenance"] if row["rule"] == "spread.switched"]


def test_a_container_value_reaches_its_member_with_a_spread_row(tmp_path: Path) -> None:
    project(tmp_path, off())
    _, document = _mapped(tmp_path)
    item = nodes(document)["box.item::B.g"]
    assert item["attributes"] == {"switched": "off"}
    assert _spread_rows(item) == [
        {"pack": "box", "rule": "spread.switched", "confidence": "inferred", "sets": ["switched"]}
    ]
    assert "attributes" not in nodes(document)["box.item::A.f"]


def test_an_attribute_that_does_not_spread_stays_on_its_node(tmp_path: Path) -> None:
    project(tmp_path, off(), declare=DECLARE.replace("spreads: true", "spreads: false"))
    _, document = _mapped(tmp_path)
    assert "attributes" not in nodes(document)["box.item::B.g"]


def test_a_node_keeps_its_own_value_over_its_container(tmp_path: Path) -> None:
    project(tmp_path, off() + ITEM_OWN, declare=BOTH)
    _, document = _mapped(tmp_path)
    item = nodes(document)["box.item::B.g"]
    assert item["attributes"] == {"switched": "own"}
    assert _spread_rows(item) == []


def test_the_value_reaches_a_member_of_a_member(tmp_path: Path) -> None:
    project(tmp_path, off() + _parts(), YARD + "part B.g p\n", DECLARE + PARTS_TYPES)
    _, document = _mapped(tmp_path)
    assert nodes(document)["box.part::B.g.p"]["attributes"] == {"switched": "off"}


def test_the_nearest_container_wins(tmp_path: Path) -> None:
    project(tmp_path, off() + ITEM_OWN + _parts(), YARD + "part B.g p\n", BOTH + PARTS_TYPES)
    _, document = _mapped(tmp_path)
    assert nodes(document)["box.part::B.g.p"]["attributes"] == {"switched": "own"}


def test_two_containers_at_one_distance_with_different_values_differ(tmp_path: Path) -> None:
    project(tmp_path, off() + LIST_ON + _parts(), YARD + "also A.f B\n", DECLARE + PARTS_TYPES)
    report, document = _mapped(tmp_path)
    assert nodes(document)["box.item::A.f"]["attributes"] == {
        "switched": {
            "differs": [
                {"file": "yard/a.box", "line": 1, "value": "on"},
                {"file": "yard/a.box", "line": 2, "value": "off"},
            ]
        }
    }
    assert ("box.item::A.f", "switched") in report.differing


def test_the_spread_row_takes_the_weakest_confidence_on_the_way(tmp_path: Path) -> None:
    project(tmp_path, off() + _parts("mentioned"), YARD + "part B.g p\n", DECLARE + PARTS_TYPES)
    _, document = _mapped(tmp_path)
    assert [r["confidence"] for r in _spread_rows(nodes(document)["box.item::B.g"])] == ["inferred"]
    assert [r["confidence"] for r in _spread_rows(nodes(document)["box.part::B.g.p"])] == [
        "mentioned"
    ]


def test_the_header_names_the_mark_of_an_attribute_a_node_holds(tmp_path: Path) -> None:
    project(tmp_path, off())
    _, document = _mapped(tmp_path)
    assert document["marks"] == {"switched": "switched off"}


def test_no_header_marks_when_no_node_holds_a_marked_attribute(tmp_path: Path) -> None:
    project(tmp_path, off(), yard="unit A\non A\n")
    _, document = _mapped(tmp_path)
    assert "marks" not in document


#: Knobs on items and tags on items, by two kinds that do not group, and ``knob <item> <name>`` and
#: ``tag <item> <name>`` lines; added to the attributes file and the map rules file.
KNOBS_TYPES = """\
node_types:
- {name: box.knob, id_namespace: box.knob}
- {name: box.tag, id_namespace: box.tag}
edge_kinds:
- {kind: has_knob, from: box.item, to: box.knob}
- {kind: tags, from: box.tag, to: box.item}
"""
KNOBS = r"""- rule: knob
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^knob (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{item}.{name}'}
  emits: [{node: {type: box.knob}}]
  confidence: declared
- rule: item_knob
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^knob (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{item}'}
  emits:
  - edge: {kind: has_knob, from: this_node, to: {template: '{item}.{name}', type: box.knob}}
  confidence: CONFIDENCE
- rule: tag
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^tag (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{name}'}
  emits: [{node: {type: box.tag}}]
  confidence: declared
- rule: tag_item
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^tag (?<item>[\w.]+) (?<name>\w+)'}
  id: {template: '{name}'}
  emits: [{edge: {kind: tags, from: this_node, to: {template: '{item}', type: box.item}}}]
  confidence: declared
"""
ALONG = "mark: switched off, spreads_along: [{kind: has_knob, to: to}, {kind: tags, to: from}]}"
KNOB_YARD = YARD + "knob A.f k\nknob B.g k\ntag B.g t\n"


def _knobs(confidence: str = "declared") -> str:
    return KNOBS.replace("CONFIDENCE", confidence)


def _along(declare: str = DECLARE) -> str:
    return declare.replace("mark: switched off}", ALONG) + KNOBS_TYPES


def test_the_value_travels_along_a_listed_kind_toward_its_to_end(tmp_path: Path) -> None:
    project(tmp_path, off() + _knobs("mentioned"), KNOB_YARD, _along())
    _, document = _mapped(tmp_path)
    knob = nodes(document)["box.knob::B.g.k"]
    assert knob["attributes"] == {"switched": "off"}
    assert _spread_rows(knob) == [
        {"pack": "box", "rule": "spread.switched", "confidence": "mentioned", "sets": ["switched"]}
    ]
    assert "attributes" not in nodes(document)["box.knob::A.f.k"]
    first = (tmp_path / "map.json").read_bytes()
    _mapped(tmp_path)
    assert (tmp_path / "map.json").read_bytes() == first


def test_the_value_travels_along_a_listed_kind_toward_its_from_end(tmp_path: Path) -> None:
    project(tmp_path, off() + _knobs(), KNOB_YARD, _along())
    _, document = _mapped(tmp_path)
    assert nodes(document)["box.tag::t"]["attributes"] == {"switched": "off"}


def test_a_kind_the_declaration_does_not_list_carries_nothing(tmp_path: Path) -> None:
    project(tmp_path, off() + _knobs(), KNOB_YARD, DECLARE + KNOBS_TYPES)
    _, document = _mapped(tmp_path)
    assert "attributes" not in nodes(document)["box.knob::B.g.k"]
    assert "attributes" not in nodes(document)["box.tag::t"]


def test_the_nearest_holder_wins_along_a_listed_kind(tmp_path: Path) -> None:
    project(tmp_path, off() + ITEM_OWN + _knobs(), KNOB_YARD, _along(BOTH))
    _, document = _mapped(tmp_path)
    assert nodes(document)["box.knob::B.g.k"]["attributes"] == {"switched": "own"}
