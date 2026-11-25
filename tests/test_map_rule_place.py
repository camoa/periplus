"""The ``place: edge`` follow step: a map rule's fire sits where the edge it walked was found."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant

from periplus import map as map_module
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

#: ``class <name>`` declares a class, ``use <name>`` a use, and ``guard <name> <class>`` guards a
#: use with a class at its own line, its slot the class name. MAP is the match of the map rule
#: ``joined``, which emits ``reaches``; EXTRA is room for more map rules.
RULES = r"""node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.use, id_namespace: own.use}
edge_kinds:
- {kind: guarded, from: own.use, to: own.class}
- {kind: reaches, from: [own.use, own.class], to: [own.use, own.class]}
- {kind: relayed, from: own.use, to: own.class}
edge_attributes:
- {name: slot, on: [guarded, reaches], description: the class a guard names}
rules:
- rule: class
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^class (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.class}}]
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
  emits:
  - edge:
      kind: guarded
      from: this_node
      to: {from: {capture: class}}
      attributes: {slot: {template: '{class}'}}
  confidence: declared
- rule: joined
  reads: map
  match:
MAP
EMITS
  confidence: inferred
EXTRA"""

REACHES = "  emits: [{edge: {kind: reaches, from: this_node, to: matched_node}}]"

#: A use at line 2, guarded by Engine at line 4.
YARD = "class Engine\nuse a\nclass Wheel\nguard a Engine\n"


def _map(
    root: Path,
    match: str,
    yard: str = YARD,
    extra: str = "",
    output: str = "map.json",
    emits: str = REACHES,
):
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES.replace("MAP", match)
            .replace("EMITS", emits)
            .replace("EXTRA", extra),
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


def _lines(document, kind: str = "reaches") -> list[tuple[str, str, list[int]]]:
    return sorted(
        (e["from"], e["to"], [place["line"] for place in e["locations"]])
        for e in document["edges"]
        if e["kind"] == kind
    )


def _refused(report, reason: str) -> bool:
    return any(
        p.message.endswith(f"the rule joined cannot be executed: {reason}") for p in report.problems
    )


PLACED = "    node_type: own.use\n    follow: [{edge: guarded}, {place: edge}]"


def test_without_place_the_edge_sits_at_the_matched_node(tmp_path: Path) -> None:
    report, document = _map(tmp_path, "    node_type: own.use\n    follow: [{edge: guarded}]")
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.class::Engine", [2])]


def test_place_edge_puts_the_edge_at_the_walked_edge(tmp_path: Path) -> None:
    report, document = _map(tmp_path, PLACED)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.class::Engine", [4])]


def test_place_edge_after_incoming_edge_puts_the_edge_at_the_walked_edge(tmp_path: Path) -> None:
    match = "    node_type: own.class\n    follow: [{incoming_edge: guarded}, {place: edge}]"
    report, document = _map(tmp_path, match)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.class::Engine", "own.use::a", [4])]


def test_a_walked_edge_found_twice_gives_a_record_at_each_place(tmp_path: Path) -> None:
    yard = YARD + "guard a Engine\n"
    report, document = _map(tmp_path, PLACED, yard)
    assert report.problems == (), report
    assert _lines(document) == [("own.use::a", "own.class::Engine", [4, 5])]


def test_place_inside_a_try_that_reaches_a_node_places_the_edge(tmp_path: Path) -> None:
    match = "    node_type: own.use\n    follow: [{try: [{edge: guarded}, {place: edge}]}]"
    report, document = _map(tmp_path, match)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.class::Engine", [4])]


def test_place_inside_a_try_that_misses_leaves_the_matched_node_place(tmp_path: Path) -> None:
    match = (
        "    node_type: own.use\n"
        "    follow: [{node: 'own.class::Wheel'}, {try: [{incoming_edge: guarded}, {place: edge}]}]"
    )
    report, document = _map(tmp_path, match)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.class::Wheel", [2])]


def test_place_and_edge_attribute_read_one_edge_in_either_order(tmp_path: Path) -> None:
    slot = "  emits: [{edge: {kind: reaches, from: this_node, to: matched_node, "
    slot += "attributes: {slot: {template: '{slot}'}}}}]"
    for steps in ("{edge_attribute: slot}, {place: edge}", "{place: edge}, {edge_attribute: slot}"):
        match = f"    node_type: own.use\n    follow: [{{edge: guarded}}, {steps}]"
        report, document = _map(tmp_path, match, emits=slot)
        assert report.problems == () and report.not_executed == (), (steps, report)
        assert _lines(document) == [("own.use::a", "own.class::Engine", [4])], steps
        (edge,) = [e for e in document["edges"] if e["kind"] == "reaches"]
        assert edge["attributes"] == {"slot": "Engine"}, steps


def test_a_later_place_replaces_an_earlier_one(tmp_path: Path) -> None:
    match = (
        "    node_type: own.use\n    where: [{id_matches: 'a$'}]\n"
        "    follow: [{edge: guarded}, {place: edge}, {incoming_edge: guarded}, {place: edge},"
        " {id_matches: 'b$'}]"
    )
    report, document = _map(tmp_path, match, YARD + "use b\nguard b Engine\n")
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.use::b", [6])]


def test_a_try_that_misses_after_a_place_keeps_that_place(tmp_path: Path) -> None:
    match = (
        "    node_type: own.use\n"
        "    follow: [{edge: guarded}, {place: edge},"
        " {try: [{incoming_edge: relayed}, {place: edge}]}]"
    )
    report, document = _map(tmp_path, match)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document) == [("own.use::a", "own.class::Engine", [4])]


def test_place_edge_on_an_edge_a_map_rule_made_takes_that_edge_place(tmp_path: Path) -> None:
    relay = r"""- rule: relay
  reads: map
  match:
    node_type: own.use
    follow: [{edge: reaches}, {place: edge}]
  emits: [{edge: {kind: relayed, from: this_node, to: matched_node}}]
  confidence: inferred
"""
    report, document = _map(tmp_path, PLACED, extra=relay)
    assert report.problems == () and report.not_executed == (), report
    assert _lines(document, "relayed") == [("own.use::a", "own.class::Engine", [4])]


def test_place_edge_makes_its_records_in_place_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The places of a walked edge are a set, whose order follows the hash seed of the process;
    the records come out in place order, so the map is the same on any machine."""
    made: list = []
    real = map_module.run_map_rules

    def spy(*args):
        result = real(*args)
        made.extend(result[1])
        return result

    monkeypatch.setattr(map_module, "run_map_rules", spy)
    report, _ = _map(tmp_path, PLACED, "use a\nclass Engine\n" + "guard a Engine\n" * 40)
    assert report.problems == (), report
    assert [edge.line for edge in made] == list(range(3, 43))


def test_place_not_right_after_an_edge_step_is_not_executed(tmp_path: Path) -> None:
    for follow in (
        "[{place: edge}, {edge: guarded}]",
        "[{edge: guarded}, {id_matches: '.'}, {place: edge}]",
        "[{edge: guarded}, {try: [{place: edge}]}]",
    ):
        report, _ = _map(tmp_path, f"    node_type: own.use\n    follow: {follow}")
        assert _refused(report, "the follow step place comes right after an edge step"), follow


def test_place_with_another_value_is_refused(tmp_path: Path) -> None:
    match = "    node_type: own.use\n    follow: [{edge: guarded}, {place: node}]"
    report, _ = _map(tmp_path, match)
    assert any(
        p.message.endswith("follow[1].place: 'node' is not one of ['edge']")
        for p in report.problems
    ), report.problems
    # The schema does not read inside a try; the engine refuses it there.
    match = "    node_type: own.use\n    follow: [{try: [{edge: guarded}, {place: node}]}]"
    report, _ = _map(tmp_path, match)
    assert _refused(report, "the follow step place takes the value edge"), report.problems


PLACE_CHAIN = "[{edge: guarded}, {place: edge}]"


def test_place_in_an_unless_chain_is_not_executed(tmp_path: Path) -> None:
    for key in ("unless", "unless_matched"):
        for chain in (PLACE_CHAIN, f"[{{try: {PLACE_CHAIN}}}]"):
            report, _ = _map(tmp_path, f"{PLACED}\n    {key}: [{chain}]")
            assert _refused(report, "the follow step place sits in follow, not in unless"), chain


def test_place_in_a_rule_that_withholds_is_not_executed(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, PLACED, emits="  emits: [{withhold: matched_node}]")
    assert _refused(report, "a map rule that withholds takes no place step"), report.problems
