"""A map rule's ``unless``: chains of follow steps from the matched node; when any reaches a node,
the rule makes nothing for that node."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  yard: ./yard
files:
  types:
    yard:
      endings: [yard]
      reader: text
"""

#: ``var <name> <class>`` assigns a variable, ``again <name>`` assigns it a second time, ``use
#: <name>`` uses it and ``guard <name> <class>`` guards a use. ``joined`` joins a use to the class
#: its variable was assigned from, unless UNLESS.
RULES = r"""node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.var, id_namespace: own.var}
- {name: own.again, id_namespace: own.again}
- {name: own.use, id_namespace: own.use}
edge_kinds:
- {kind: assigned, from: own.var, to: own.class}
- {kind: guarded, from: own.use, to: own.class}
- {kind: reaches, from: own.use, to: own.class}
rules:
- rule: class
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^class (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: var
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^var (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.var}}]
  confidence: declared
- rule: var_assigned
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^var (?<name>\w+) (?<class>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: assigned, from: this_node, to: {from: {capture: class}}}}]
  confidence: declared
- rule: again
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^again (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.again}}]
  confidence: declared
- rule: use
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^use (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.use}}]
  confidence: declared
- rule: guard
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^guard (?<name>\w+) (?<class>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: guarded, from: this_node, to: {from: {capture: class}}}}]
  confidence: declared
- rule: joined
  reads: map
  match:
    node_type: own.use
    where: [{id_matches: '^own\.use::(?<name>\w+)$'}]
    follow:
    - node: 'own.var::{name}'
    - edge: assigned
    unless: UNLESS
  emits: [{edge: {kind: reaches, from: this_node, to: matched_node}}]
  confidence: inferred
"""

AGAIN = "[[{node: 'own.again::{name}'}]]"
BOTH = "[[{node: 'own.again::{name}'}], [{edge: guarded}]]"


def _map(root: Path, unless: str, yard: str, output: str = "map.json"):
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES.replace("UNLESS", unless),
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "yard/a.yard": yard,
        },
    )
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path(output),
    )
    document = json.loads((root / output).read_text()) if report.map_path else {}
    return report, document


def _reaches(document) -> list[tuple[str, str]]:
    return sorted((e["from"], e["to"]) for e in document["edges"] if e["kind"] == "reaches")


def test_the_rule_fires_without_the_blocking_node(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, AGAIN, "class Engine\nvar a Engine\nuse a\n")
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.use::a", "own.class::Engine")]


def test_the_rule_makes_nothing_when_the_unless_chain_reaches_a_node(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, AGAIN, "class Engine\nvar a Engine\nagain a\nuse a\n")
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == []
    assert report.skipped == ()


def test_unless_blocks_one_start_node_and_not_another(tmp_path: Path) -> None:
    yard = "class Engine\nclass Wheel\nvar a Engine\nvar b Wheel\nagain b\nuse a\nuse b\n"
    _, doc = _map(tmp_path, AGAIN, yard)
    assert _reaches(doc) == [("own.use::a", "own.class::Engine")]


@pytest.mark.parametrize("blocker", ["again a\n", "guard a Engine\n"])
def test_either_of_two_unless_chains_blocks(tmp_path: Path, blocker: str) -> None:
    yard = "class Engine\nclass Wheel\nvar a Engine\nvar b Wheel\nuse a\nuse b\n" + blocker
    report, doc = _map(tmp_path, BOTH, yard)
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.use::b", "own.class::Wheel")]


@pytest.mark.parametrize(
    "unless", ["[{node: 'own.again::{name}'}]", "[]", "[[]]", "[[{nope: x}]]"]
)
def test_the_schema_refuses_a_malformed_unless(tmp_path: Path, unless: str) -> None:
    report, doc = _map(tmp_path, unless, "class Engine\nvar a Engine\nagain a\nuse a\n")
    assert report.problems, report
    assert any("unless" in p.message for p in report.problems), report.problems
    assert not doc or _reaches(doc) == []


def test_an_undeclared_kind_inside_unless_is_refused_at_load(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, "[[{edge: nowhere}]]", "class Engine\nvar a Engine\nuse a\n")
    messages = [p.message for p in report.problems]
    assert any(
        "the rule joined follows the edge kind nowhere, which neither own nor a pack it "
        "depends on declares" in m
        for m in messages
    ), messages


def test_an_unless_node_naming_no_capture_is_not_executed(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, "[[{node: 'own.again::{nobody}'}]]", "use a\n")
    assert "joined" not in [rule for _, rule, _ in report.executed]
    messages = [p.message for p in report.problems if "joined" in p.message]
    assert messages and "inside unless names nobody, which no id_matches captures" in messages[0]


def test_the_map_is_byte_identical_on_two_runs(tmp_path: Path) -> None:
    yard = "class Engine\nclass Wheel\nvar a Engine\nvar b Wheel\nagain b\nuse a\nuse b\n"
    _map(tmp_path, BOTH, yard, "one.json")
    _map(tmp_path, BOTH, yard, "two.json")
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
