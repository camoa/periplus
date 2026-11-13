"""Map rule chain steps: the kind check at every depth, ``incoming_edge``, captures inside
``id_matches``, and ``unless_matched``."""

from __future__ import annotations

import json
from pathlib import Path

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

#: ``class <name>`` declares a class, ``var <name> <class>`` assigns a variable from a class,
#: ``use <name>`` uses a variable, ``guard <name> <class>`` guards a use with a class and ``stop
#: <name>`` marks a name. MAP is the map rule under test, named ``joined``.
RULES = r"""node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.var, id_namespace: own.var}
- {name: own.use, id_namespace: own.use}
- {name: own.stop, id_namespace: own.stop}
edge_kinds:
- {kind: assigned, from: own.var, to: own.class}
- {kind: guarded, from: own.use, to: own.class}
- {kind: reaches, from: [own.use, own.class, own.var], to: [own.class, own.var]}
rules:
- rule: class
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^class (?<name>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: var
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^var (?<name>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.var}}]
  confidence: declared
- rule: var_assigned
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^var (?<name>[\w.]+) (?<class>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: assigned, from: this_node, to: {from: {capture: class}}}}]
  confidence: declared
- rule: use
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^use (?<name>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.use}}]
  confidence: declared
- rule: guard
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^guard (?<name>[\w.]+) (?<class>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: guarded, from: this_node, to: {from: {capture: class}}}}]
  confidence: declared
- rule: stop
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^stop (?<name>[\w.]+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.stop}}]
  confidence: declared
- rule: joined
  reads: map
  match:
MAP
  emits: [{edge: {kind: reaches, from: this_node, to: matched_node}}]
  confidence: inferred
"""


def _map(root: Path, match: str, yard: str, output: str = "map.json"):
    """The report and map of one run, the map rule's ``match`` given as indented YAML lines."""
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES.replace("MAP", match),
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


def _undeclared(report, kind: str) -> bool:
    return any(
        f"the rule joined follows the edge kind {kind}, which neither own nor a pack it depends "
        "on declares" in p.message
        for p in report.problems
    )


def _twice(root: Path, match: str, yard: str) -> None:
    _map(root, match, yard, "one.json")
    _map(root, match, yard, "two.json")
    assert (root / "one.json").read_bytes() == (root / "two.json").read_bytes()


YARD = "class Engine\nvar a Engine\nuse a\n"

# 4. The kind check reaches every depth.


def test_an_undeclared_kind_inside_try_is_refused(tmp_path: Path) -> None:
    match = "    node_type: own.var\n    follow: [{try: [{edge: nowhere}]}, {edge: assigned}]"
    report, _ = _map(tmp_path, match, YARD)
    assert _undeclared(report, "nowhere"), report.problems


def test_an_undeclared_kind_in_a_try_inside_a_try_inside_unless_is_refused(tmp_path: Path) -> None:
    match = (
        "    node_type: own.var\n    follow: [{edge: assigned}]\n"
        "    unless: [[{try: [{try: [{ancestors: [deep]}]}]}]]"
    )
    report, _ = _map(tmp_path, match, YARD)
    assert _undeclared(report, "deep"), report.problems


def test_a_declared_kind_inside_try_is_not_refused(tmp_path: Path) -> None:
    match = "    node_type: own.var\n    follow: [{try: [{edge: assigned}]}]"
    report, doc = _map(tmp_path, match, YARD)
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.var::a", "own.class::Engine")]


def test_an_undeclared_top_level_kind_is_still_refused(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, "    node_type: own.var\n    follow: [{edge: nowhere}]", YARD)
    assert _undeclared(report, "nowhere"), report.problems


def test_the_refusals_are_the_same_on_two_runs(tmp_path: Path) -> None:
    match = "    node_type: own.var\n    follow: [{try: [{edge: b}, {try: [{edge: a}]}]}]"
    first, _ = _map(tmp_path, match, YARD, "one.json")
    second, _ = _map(tmp_path, match, YARD, "two.json")
    assert _undeclared(first, "a") and _undeclared(first, "b"), first.problems
    assert [p.message for p in first.problems] == [p.message for p in second.problems]

# 3. incoming_edge walks an edge from its target to its sources.

BACK = "    node_type: own.class\n    follow: [{incoming_edge: assigned}]"


def test_incoming_edge_reaches_each_source_of_the_kind(tmp_path: Path) -> None:
    yard = "class Engine\nclass Wheel\nvar b Engine\nvar a Engine\nvar c Wheel\n"
    report, doc = _map(tmp_path, BACK, yard)
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [
        ("own.class::Engine", "own.var::a"),
        ("own.class::Engine", "own.var::b"),
        ("own.class::Wheel", "own.var::c"),
    ]


def test_incoming_edge_reaches_nothing_without_an_edge_into_the_node(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, BACK, "class Engine\nclass Wheel\nvar a Wheel\n")
    assert report.problems == (), report
    assert _reaches(doc) == [("own.class::Wheel", "own.var::a")]


def test_edge_still_runs_from_source_to_target(tmp_path: Path) -> None:
    match = "    node_type: own.class\n    follow: [{edge: assigned}]"
    report, doc = _map(tmp_path, match, "class Engine\nvar a Engine\n")
    assert report.problems == (), report
    assert _reaches(doc) == []


def test_incoming_edge_runs_inside_try_and_unless(tmp_path: Path) -> None:
    match = (
        "    node_type: own.class\n    follow: [{try: [{incoming_edge: assigned}]}]\n"
        "    unless: [[{incoming_edge: guarded}]]"
    )
    yard = "class Engine\nclass Wheel\nvar a Engine\nvar b Wheel\nuse u\nguard u Wheel\n"
    report, doc = _map(tmp_path, match, yard)
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.class::Engine", "own.var::a")]


def test_an_undeclared_incoming_edge_kind_is_refused(tmp_path: Path) -> None:
    match = "    node_type: own.class\n    follow: [{try: [{incoming_edge: nowhere}]}]"
    report, _ = _map(tmp_path, match, YARD)
    assert _undeclared(report, "nowhere"), report.problems


def test_incoming_edge_gives_a_byte_identical_map_on_two_runs(tmp_path: Path) -> None:
    yard = "class Engine\nvar d Engine\nvar b Engine\nvar a Engine\nvar c Engine\n"
    _twice(tmp_path, BACK, yard)

# 2. A {name} in an id_matches step is filled from the captures known there, as literal text.

OTHERS = (
    "    node_type: own.var\n    where: [{id_matches: '^own\\.var::(?<name>[\\w.]+)$'}]\n"
    "    follow: [{edge: assigned}, {incoming_edge: assigned}, "
    "{id_matches: '^own\\.var::(?!{name}$)'}]"
)


def test_an_id_matches_step_fills_a_capture_as_literal_text(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, OTHERS, "class Engine\nvar a.b Engine\nvar aXb Engine\n")
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.var::a.b", "own.var::aXb"), ("own.var::aXb", "own.var::a.b")]


def test_an_id_matches_step_with_a_capture_keeps_nothing_it_does_not_fit(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, OTHERS, "class Engine\nclass Wheel\nvar a Engine\nvar b Wheel\n")
    assert report.problems == (), report
    assert _reaches(doc) == []


def test_an_id_matches_step_naming_no_capture_is_not_executed(tmp_path: Path) -> None:
    match = "    node_type: own.var\n    follow: [{edge: assigned}, {id_matches: '{nobody}'}]"
    report, _ = _map(tmp_path, match, YARD)
    assert "joined" not in [rule for _, rule, _ in report.executed]
    messages = [p.message for p in report.problems if "joined" in p.message]
    assert messages and (
        "the follow step id_matches {nobody} names nobody, which no id_matches captures before it"
        in messages[0]
    ), messages


def test_a_quantifier_in_an_id_matches_step_stays_a_quantifier(tmp_path: Path) -> None:
    match = (
        "    node_type: own.var\n"
        "    follow: [{edge: assigned}, {id_matches: '^own\\.class::\\w{2}$|::\\w{4,5}$'}]"
    )
    yard = "class Ab\nclass Abc\nclass Abcd\nvar a Ab\nvar b Abc\nvar c Abcd\n"
    report, doc = _map(tmp_path, match, yard)
    assert report.problems == () and report.not_executed == (), report
    assert _reaches(doc) == [("own.var::a", "own.class::Ab"), ("own.var::c", "own.class::Abcd")]


def test_a_filled_id_matches_step_gives_a_byte_identical_map_on_two_runs(tmp_path: Path) -> None:
    _twice(tmp_path, OTHERS, "class Engine\nvar c Engine\nvar a.b Engine\nvar aXb Engine\n")
