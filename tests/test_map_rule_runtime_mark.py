"""A map rule marks a place whose target is only known at run time, as a file rule does: it emits
one node and ``resolution: runtime`` beside it, and the map holds the same unknown boundary."""

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

#: ``class <name>`` declares a class, ``holds <class> <part>`` gives a class a part, and
#: ``ask <class> <name>`` an internal ask. ``ask_no_part`` is the map rule under test: an ask on a
#: class that holds no part. EXTRA is room for more rules.
RULES = r"""node_types:
- {name: own.class, id_namespace: own.class}
- {name: own.ask, id_namespace: own.ask, internal: true}
- {name: own.call, id_namespace: own.call}
edge_kinds:
- {kind: holds, from: own.class, to: own.class}
- {kind: calls, from: own.call, to: own.class}
rules:
- rule: class
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^class (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: holds
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^holds (?<name>\w+) (?<part>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: holds, from: this_node, to: {from: {capture: part}}}}]
  confidence: declared
- rule: ask
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^ask (?<owner>\w+) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits: [{node: {type: own.ask}}]
  confidence: declared
- rule: ask_no_part
  reads: map
  match:
    node_type: own.ask
    where: [{id_matches: '^own\.ask::(?<owner>\w+)\.(?<name>\w+)$'}]
    unless: [[{node: 'own.class::{owner}'}, {edge: holds}]]
EMITS
  confidence: inferred
EXTRA"""

MARK = """\
  id: {template: '{owner}.{name}'}
  emits:
  - node: {type: own.call}
  - attribute: {name: resolution, template: runtime}"""

#: ``Car`` holds a part, ``Van`` none: the ask on ``Van`` at line 4 is marked.
YARD = "class Car\nclass Van\nholds Car Engine\nask Van start\nask Car start\n"

#: A file rule that finds ``own.call::<class>.<name>`` and its target, by ``call <class> <name>``.
CALL = r"""- rule: call
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^call (?<owner>\w+) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits: [{node: {type: own.call}}]
  confidence: declared
- rule: call_target
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^call (?<owner>\w+) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits: [{edge: {kind: calls, from: this_node, to: {template: '{owner}', type: own.class}}}]
  confidence: declared
"""


def _map(root: Path, emits: str = MARK, yard: str = YARD, extra: str = "", output: str = "m.json"):
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES.replace("EMITS", emits).replace(
                "EXTRA", extra
            ),
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


def _calls(document) -> list[dict]:
    return [node for node in document["nodes"] if node["type"] == "own.call"]


def _refused(report, reason: str) -> bool:
    return any(
        p.message.endswith(f"the rule ask_no_part cannot be executed: {reason}")
        for p in report.problems
    )


def test_a_map_rule_marks_its_node_as_decided_at_run_time(tmp_path: Path) -> None:
    report, document = _map(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _calls(document) == [
        {
            "id": "own.call::Van.start",
            "type": "own.call",
            "state": "unknown_boundary",
            "locations": [{"file": "yard/a.yard", "line": 4}],
            "provenance": [
                {
                    "pack": "own",
                    "rule": "ask_no_part",
                    "confidence": "inferred",
                    "sets": ["id", "type", "resolution"],
                }
            ],
            "attributes": {"resolution": "runtime"},
        }
    ]


def test_the_map_rule_mark_is_stored_as_a_file_rule_mark(tmp_path: Path) -> None:
    """The same node a file rule marks differs only in the rule that set it."""
    file_rule = r"""- rule: by_file
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^ask (?<owner>Van) (?<name>\w+)'}
  id: {template: '{owner}.{name}'}
  emits:
  - node: {type: own.call}
  - attribute: {name: resolution, template: runtime}
  confidence: inferred
"""
    _, by_map = _map(tmp_path / "map", output="m.json")
    report, by_file = _map(tmp_path / "file", "  emits: [{withhold: this_node}]", extra=file_rule)
    assert report.problems == (), report
    (node,) = _calls(by_file)
    node["provenance"][0]["rule"] = "ask_no_part"
    assert _calls(by_map) == [node]


def test_the_report_counts_the_mark_as_a_run_time_unknown_boundary(tmp_path: Path) -> None:
    report, _ = _map(tmp_path)
    assert report.unknown == (("own", "run-time"),), report.unknown


def test_a_mark_stays_when_another_rule_finds_the_target(tmp_path: Path) -> None:
    """A file rule that finds the same node and its edge adds them; the mark is not taken back."""
    report, document = _map(tmp_path, yard=YARD + "call Van start\n", extra=CALL)
    assert report.problems == (), report
    (node,) = _calls(document)
    assert node["state"] == "unknown_boundary" and node["attributes"] == {"resolution": "runtime"}
    assert [(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "calls"] == [
        ("own.call::Van.start", "own.class::Van")
    ]


def test_the_marked_map_gives_a_byte_identical_map_on_two_runs(tmp_path: Path) -> None:
    _map(tmp_path, output="one.json")
    _map(tmp_path, output="two.json")
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()


def test_a_resolution_template_other_than_runtime_beside_a_node_is_refused(
    tmp_path: Path,
) -> None:
    report, _ = _map(tmp_path, MARK.replace("template: runtime", "template: '{name}'"))
    assert any(
        p.message.endswith("attribute.template: 'runtime' was expected") for p in report.problems
    ), report.problems


def test_another_attribute_beside_a_map_rule_node_is_still_refused(tmp_path: Path) -> None:
    emits = MARK.replace("name: resolution", "name: colour")
    report, _ = _map(tmp_path, emits, extra="attributes:\n- {name: colour, on: [own.call]}\n")
    assert _refused(
        report, "beside its node a map rule writes only the attribute resolution"
    ), report.problems


def test_a_mark_beside_a_node_with_a_target_is_refused_for_the_target(tmp_path: Path) -> None:
    targeted = MARK.replace("template: runtime", "template: runtime, target: this_node")
    report, _ = _map(tmp_path, targeted)
    assert _refused(
        report, "the attribute resolution beside a node takes a name and a template only"
    ), report.problems


def test_resolution_written_on_a_node_the_rule_did_not_make_is_refused(tmp_path: Path) -> None:
    emits = "  emits: [{attribute: {name: resolution, template: runtime}}]"
    for given in (emits, "  id: {template: '{owner}'}\n" + emits):
        report, _ = _map(tmp_path, given)
        assert _refused(
            report, "a map rule writes the attribute resolution only beside the node it emits"
        ), (given, report.problems)


#: A map rule that draws ``holds`` from each class to ``Engine``: the place ``ask_no_part`` would
#: mark in pass 1 is resolved in that same pass.
HOLDS_ALL = r"""- rule: holds_all
  reads: map
  match:
    node_type: own.class
    where: [{id_matches: '^own\.class::(?!Engine$)'}]
    follow: [{node: 'own.class::Engine'}]
  emits: [{edge: {kind: holds, from: this_node, to: matched_node}}]
  confidence: inferred
"""


def test_a_place_another_map_rule_resolves_gets_no_mark(tmp_path: Path) -> None:
    report, document = _map(
        tmp_path, yard="class Engine\nclass Car\nask Car start\n", extra=HOLDS_ALL
    )
    assert report.problems == (), report
    assert _calls(document) == []
    assert report.map_passes == (
        (1, (("own", "holds_all", 1),)),
        (2, ()),
        (3, ()),
    ), report.map_passes


def test_marking_rules_run_in_one_last_pass_after_the_others(tmp_path: Path) -> None:
    report, document = _map(tmp_path, extra=HOLDS_ALL.replace("(?!Engine$)", "Van$"))
    assert report.problems == (), report
    assert [node["id"] for node in _calls(document)] == []
    report, document = _map(tmp_path, yard="class Car\nask Car start\n", extra=HOLDS_ALL)
    assert [node["id"] for node in _calls(document)] == ["own.call::Car.start"]
    assert report.map_passes == ((1, ()), (2, (("own", "ask_no_part", 1),))), report.map_passes
