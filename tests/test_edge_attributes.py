"""A text rule or a map rule writes attributes on the edges it emits.

The pack is a neutral one, so it is also the proof that a third-party pack uses edge attributes
with no engine change: a yard of units, hooks that attach a unit to a unit under a slot, and a
list of the units that are on. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, pin, plant, rutter

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

#: ``unit <name>`` is a unit; ``hook <unit> <slot> <other>`` attaches ``other`` to ``unit`` under
#: ``slot``; ``on <unit>`` lists a unit.
BASE = r"""node_types:
- {name: box.unit, id_namespace: box.unit}
- {name: box.hook, id_namespace: box.hook}
edge_kinds:
- {kind: attaches, from: box.unit, to: box.unit}
- {kind: hook_from, from: box.hook, to: box.unit}
- {kind: hooks, from: box.unit, to: box.unit}
rules:
- rule: unit
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^unit (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: box.unit}}]
  confidence: declared
"""

#: The text rule: an edge from the unit to the other, with the slot as written.
ATTACH = r"""- rule: attach
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^hook (?<unit>\w+) (?<slot>[#\w ]+?) (?<other>\w+)$'}
  id: {from: {capture: unit}}
  emits:
  - edge:
      kind: attaches
      from: this_node
      to: {template: '{other}', type: box.unit}
      attributes: {slot: {template: '{slot}'}}
  confidence: declared
"""

#: A hook as a node, ``<unit>|<slot>|<other>``, and the map rule that reads the slot from its id.
HOOK = r"""- rule: hook
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^hook (?<unit>\w+) (?<slot>[#\w ]+?) (?<other>\w+)$'}
  id: {template: '{unit}|{slot}|{other}'}
  emits: [{node: {type: box.hook}}]
  confidence: declared
- rule: hook_unit
  reads: file
  in: [yard]
  match: {file: '*', filetype: box, text: '(?m)^hook (?<unit>\w+) (?<slot>[#\w ]+?) (?<other>\w+)$'}
  id: {template: '{unit}|{slot}|{other}'}
  emits: [{edge: {kind: hook_from, from: this_node, to: {template: '{unit}', type: box.unit}}}]
  confidence: declared
- rule: hooked
  reads: map
  match:
    node_type: box.hook
    where: [{id_matches: '^box\.hook::\w+\|(?<slot>[^|]+)\|(?<other>\w+)$'}]
    follow: [{edge: hook_from}]
  emits:
  - edge:
      kind: hooks
      from: matched_node
      to: {template: '{other}', type: box.unit}
      attributes: {slot: {template: '{slot}'}}
  confidence: inferred
"""

DECLARE = "edge_attributes:\n- {name: slot, on: [hooks], description: the slot as written}\n"

YARD = "unit A\nunit B\nhook A #open B\n"


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def project(root: Path, rules: str, yard: str = YARD, declare: str = DECLARE) -> None:
    files = {"box.yaml": BASE, "more.yaml": f"rules:\n{rules}"}
    if declare:
        files["attributes.yaml"] = declare
    rutter(root, "box", MANIFEST, files)
    pin(root, "box@0.0.1")
    plant(root, {"yard/a.box": yard})


def _edge(document: dict[str, Any], kind: str) -> dict[str, Any]:
    (found,) = [edge for edge in document["edges"] if edge["kind"] == kind]
    return found


def _mapped(root: Path) -> dict[str, Any]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def _refused(root: Path) -> list[tuple[ExitCode, str]]:
    report, document = map_project(root)
    assert document == {}
    return [(p.code, p.message) for p in report.problems]


def test_a_text_rule_writes_the_attribute_on_its_edge(tmp_path: Path) -> None:
    project(tmp_path, ATTACH, declare="")
    edge = _edge(_mapped(tmp_path), "attaches")
    assert edge["attributes"] == {"slot": "#open"}
    assert edge["provenance"] == [
        {"pack": "box", "rule": "attach", "confidence": "declared", "sets": ["slot"]}
    ]


def test_a_map_rule_writes_a_declared_attribute_on_its_edge(tmp_path: Path) -> None:
    project(tmp_path, HOOK, yard="unit A\nunit B\nhook A #ajax callback B\n")
    edge = _edge(_mapped(tmp_path), "hooks")
    assert (edge["from"], edge["to"]) == ("box.unit::A", "box.unit::B")
    assert edge["attributes"] == {"slot": "#ajax callback"}
    assert edge["provenance"] == [
        {"pack": "box", "rule": "hooked", "confidence": "inferred", "sets": ["slot"]}
    ]


def test_an_edge_without_attributes_holds_no_attributes_key(tmp_path: Path) -> None:
    project(tmp_path, HOOK)
    edge = _edge(_mapped(tmp_path), "hook_from")
    assert "attributes" not in edge
    assert edge["provenance"] == [{"pack": "box", "rule": "hook_unit", "confidence": "declared"}]


def test_one_edge_at_two_places_with_two_values_keeps_each_value_at_its_place(
    tmp_path: Path,
) -> None:
    project(tmp_path, HOOK, yard="unit A\nunit B\nhook A #open B\nhook A #close B\n")
    edge = _edge(_mapped(tmp_path), "hooks")
    assert edge["locations"] == [
        {"file": "yard/a.box", "line": 3},
        {"file": "yard/a.box", "line": 4},
    ]
    assert edge["attributes"] == {
        "slot": {
            "differs": [
                {"file": "yard/a.box", "line": 3, "value": "#open"},
                {"file": "yard/a.box", "line": 4, "value": "#close"},
            ]
        }
    }


def test_one_edge_at_two_places_with_one_value_holds_it_once(tmp_path: Path) -> None:
    project(tmp_path, HOOK, yard="unit A\nunit B\nhook A #open B\nhook A #open B\n")
    assert _edge(_mapped(tmp_path), "hooks")["attributes"] == {"slot": "#open"}


def test_two_rules_at_one_place_with_two_values_both_show(tmp_path: Path) -> None:
    other = ATTACH.replace("rule: attach", "rule: attach_too").replace("'{slot}'", "'x{slot}'")
    project(tmp_path, ATTACH + other, declare="")
    assert _edge(_mapped(tmp_path), "attaches")["attributes"] == {
        "slot": {
            "differs": [
                {"file": "yard/a.box", "line": 3, "value": "#open"},
                {"file": "yard/a.box", "line": 3, "value": "x#open"},
            ]
        }
    }


def test_one_rule_giving_two_values_at_one_place_keeps_both(tmp_path: Path) -> None:
    """Two registrations on one line under two keys: one edge, one place, both values."""
    rule = ATTACH.replace(
        r"'(?m)^hook (?<unit>\w+) (?<slot>[#\w ]+?) (?<other>\w+)$'",
        r"'hook (?<unit>\w+) (?<slot>#\w+) (?<other>\w+);'",
    )
    project(tmp_path, rule, yard="unit A\nunit B\nhook A #open B; hook A #close B;\n", declare="")
    assert _edge(_mapped(tmp_path), "attaches")["attributes"] == {
        "slot": {
            "differs": [
                {"file": "yard/a.box", "line": 3, "value": "#close"},
                {"file": "yard/a.box", "line": 3, "value": "#open"},
            ]
        }
    }


def test_a_map_rule_writing_an_undeclared_edge_attribute_is_refused(tmp_path: Path) -> None:
    project(tmp_path, HOOK, declare="")
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/more.yaml: the rule hooked writes the edge attribute slot, which neither "
            "box nor a pack it depends on declares",
        )
    ]


def test_a_declared_edge_attribute_on_a_kind_outside_on_is_refused(tmp_path: Path) -> None:
    project(tmp_path, HOOK, declare=DECLARE.replace("on: [hooks]", "on: [attaches]"))
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/more.yaml: the rule hooked writes the edge attribute slot on hooks, which "
            "the declaration of slot does not list in on: attaches",
        )
    ]


def test_a_file_rule_writing_a_declared_edge_attribute_is_held_to_it(tmp_path: Path) -> None:
    project(tmp_path, ATTACH)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "box/rules/more.yaml: the rule attach writes the edge attribute slot on attaches, "
            "which the declaration of slot does not list in on: hooks",
        )
    ]


def test_an_edge_attribute_on_an_undeclared_kind_is_refused(tmp_path: Path) -> None:
    project(tmp_path, ATTACH, declare=DECLARE.replace("on: [hooks]", "on: [hooks, pulls]"))
    assert (
        ExitCode.PACK_RULES_UNREADABLE,
        "box/rules/attributes.yaml: the edge attribute slot lists pulls in on, which neither box "
        "nor a pack it depends on declares",
    ) in _refused(tmp_path)


@pytest.mark.parametrize("name", ["resolution", "type_conflict"])
def test_a_reserved_name_is_refused_on_an_edge(tmp_path: Path, name: str) -> None:
    declared = DECLARE.replace("name: slot", f"name: {name}")
    project(tmp_path, ATTACH.replace("slot: {", f"{name}: {{"), declare=declared)
    refused = _refused(tmp_path)
    assert (
        ExitCode.PACK_RULES_UNREADABLE,
        f"box/rules/attributes.yaml: the edge attribute {name} is declared, and the name is "
        "reserved for the engine",
    ) in refused
    assert (
        ExitCode.PACK_RULES_UNREADABLE,
        f"box/rules/more.yaml: the rule attach writes the edge attribute {name}, and the name is "
        "reserved for the engine",
    ) in refused


def test_an_edge_attribute_declared_differently_twice_is_refused(tmp_path: Path) -> None:
    again = DECLARE.replace("on: [hooks]", "on: [attaches]").replace("edge_attributes:\n", "")
    project(tmp_path, HOOK, declare=DECLARE + again)
    assert (
        ExitCode.PACK_RULES_UNREADABLE,
        "the edge attribute slot is declared with different kinds or description in "
        "box/rules/attributes.yaml, after box/rules/attributes.yaml",
    ) in _refused(tmp_path)


def test_a_template_naming_no_capture_is_not_executed(tmp_path: Path) -> None:
    project(tmp_path, HOOK.replace("'{slot}'", "'{nothing}'"))
    report, _ = map_project(tmp_path)
    (problem,) = report.problems
    assert problem.code == ExitCode.RULE_NOT_EXECUTABLE
    assert problem.message.endswith(
        "the rule hooked cannot be executed: a template names nothing, which no id_matches of the "
        "rule captures"
    )


def test_an_edge_attribute_from_a_capture_is_accepted_and_not_executed() -> None:
    item = {
        "rule": "attach",
        "reads": "file",
        "in": ["yard"],
        "match": {"file": "*", "filetype": "box", "text": r"(?<unit>\w+) (?<other>\w+)"},
        "id": {"from": {"capture": "unit"}},
        "emits": [
            {
                "edge": {
                    "kind": "attaches",
                    "from": "this_node",
                    "to": {"from": {"capture": "other"}},
                    "attributes": {"slot": {"from": {"capture": "other"}}},
                }
            }
        ],
        "confidence": "declared",
    }
    rule = _read_rule("box", item)
    assert not rule.supported
    assert rule.reason.startswith(
        "the key emits.*.edge.attributes.*.from.capture is accepted and not executed"
    )


def test_a_template_edge_attribute_on_a_data_rule_is_not_executed() -> None:
    item = {
        "rule": "listed",
        "reads": "file",
        "in": ["yard"],
        "match": {"file": "*.yml", "filetype": "yaml", "each": "units.*"},
        "id": {"template": "{key}"},
        "emits": [
            {
                "edge": {
                    "kind": "attaches",
                    "from": "this_node",
                    "to": {"from": {"key": "other"}},
                    "attributes": {"slot": {"template": "{key}"}},
                }
            }
        ],
        "confidence": "declared",
    }
    rule = _read_rule("box", item)
    assert not rule.supported
    assert rule.reason == "an edge attribute of a data rule is from one key"


#: A map rule that reads the slot off each attaches edge it walks and writes it on its own edge.
CARRY = r"""- rule: carried
  reads: map
  match:
    node_type: box.unit
    follow: [{edge: attaches}, {edge_attribute: slot}]
  emits:
  - edge:
      kind: hooks
      from: this_node
      to: matched_node
      attributes: {slot: {template: '{slot}'}}
  confidence: inferred
"""

BOTH = DECLARE.replace("on: [hooks]", "on: [attaches, hooks]")


def test_a_map_rule_reads_the_attribute_of_the_edge_it_walked(tmp_path: Path) -> None:
    project(tmp_path, ATTACH + CARRY, yard="unit A\nunit B\nunit C\nhook A #open B\n", declare=BOTH)
    document = _mapped(tmp_path)
    assert _edge(document, "hooks")["attributes"] == {"slot": "#open"}


def test_each_value_of_the_walked_edge_gives_its_own_result(tmp_path: Path) -> None:
    yard = "unit A\nunit B\nhook A #open B\nhook A #close B\n"
    project(tmp_path, ATTACH + CARRY, yard=yard, declare=BOTH)
    edge = _edge(_mapped(tmp_path), "hooks")
    # The unit A sits at line 1, so both results write at that place.
    assert edge["attributes"] == {
        "slot": {
            "differs": [
                {"file": "yard/a.box", "line": 1, "value": "#close"},
                {"file": "yard/a.box", "line": 1, "value": "#open"},
            ]
        }
    }


def test_a_walked_edge_without_the_attribute_gives_nothing(tmp_path: Path) -> None:
    plain = ATTACH.replace("      attributes: {slot: {template: '{slot}'}}\n", "")
    project(tmp_path, plain + CARRY, declare=BOTH)
    assert [e for e in _mapped(tmp_path)["edges"] if e["kind"] == "hooks"] == []


def test_edge_attribute_not_right_after_an_edge_step_is_not_executed(tmp_path: Path) -> None:
    moved = CARRY.replace(
        "[{edge: attaches}, {edge_attribute: slot}]",
        "[{edge: attaches}, {id_matches: '.'}, {edge_attribute: slot}]",
    )
    project(tmp_path, ATTACH + moved, declare=BOTH)
    report, _ = map_project(tmp_path)
    (problem,) = report.problems
    assert problem.code == ExitCode.RULE_NOT_EXECUTABLE
    assert problem.message.endswith(
        "the rule carried cannot be executed: the follow step edge_attribute comes right after "
        "an edge step"
    )


def test_edge_attribute_reads_no_value_a_map_rule_wrote(tmp_path: Path) -> None:
    """A map rule's value read back could grow every pass; only the file rules' values are read."""
    again = CARRY.replace("rule: carried", "rule: again").replace("edge: attaches}", "edge: hooks}")
    again = again.replace("kind: hooks", "kind: attaches")
    project(tmp_path, HOOK + again, yard="unit A\nunit B\nhook A #open B\n", declare=BOTH)
    document = _mapped(tmp_path)
    assert _edge(document, "hooks")["attributes"] == {"slot": "#open"}
    assert [e for e in document["edges"] if e["kind"] == "attaches"] == []
