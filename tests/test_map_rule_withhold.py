"""A map rule that emits ``withhold``: before the passes, it takes out what the file rules found of
the node it names at each location of the node it matched, with each file edge there that has
that node at an end."""

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

#: ``fn <name> <hook> <thing>`` declares a function that implements a hook by its name, at one
#: line: the function, the hook, implements from the function and acts_on from the hook to the
#: thing. ``reg <name>`` registers the function elsewhere. ``hidden`` takes out, at each registered
#: function's place, the hook it implements; ``seen`` reads implements in the passes.
RULES = r"""node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.hook, id_namespace: own.hook}
- {name: own.thing, id_namespace: own.thing}
- {name: own.reg, id_namespace: own.reg}
edge_kinds:
- {kind: implements, from: own.fn, to: own.hook}
- {kind: acts_on, from: own.hook, to: own.thing}
- {kind: seen, from: own.fn, to: own.hook}
rules:
- rule: fn
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^fn (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.fn}}]
  confidence: declared
- rule: hook
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^fn \w+ (?<hook>\w+)'}
  id: {from: {capture: hook}}
  emits: [{node: {type: own.hook}}]
  confidence: declared
- rule: implements
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^fn (?<name>\w+) (?<hook>\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: implements, from: this_node, to: {from: {capture: hook}}}}]
  confidence: declared
- rule: acts_on
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^fn \w+ (?<hook>\w+) (?<thing>\w+)'}
  id: {from: {capture: hook}}
  emits: [{edge: {kind: acts_on, from: this_node, to: {from: {capture: thing}}}}]
  confidence: declared
- rule: reg
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^reg (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.reg}}]
  confidence: declared
- rule: hidden
  reads: map
  match:
    node_type: own.fn
    where: [{id_matches: '^own\.fn::(?<name>\w+)$'}]
    follow:
    - node: 'own.reg::{name}'
    - node: 'own.fn::{name}'
    - edge: implements
  emits: EMITS
  confidence: inferred
- rule: seen
  reads: map
  match:
    node_type: own.fn
    follow: [{edge: implements}]
  emits: [{edge: {kind: seen, from: this_node, to: matched_node}}]
  confidence: inferred
"""

MATCHED = "[{withhold: matched_node}]"

YARD = "fn a ha ta\nfn b hb tb\nfn c ha ta\nreg a\nreg b\n"


def _map(root: Path, yard: str, emits: str = MATCHED, output: str = "map.json"):
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES.replace("EMITS", emits),
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


def _edges(document, kind: str) -> list[tuple[str, str, int]]:
    return sorted(
        (e["from"], e["to"], loc["line"])
        for e in document["edges"]
        if e["kind"] == kind
        for loc in e["locations"]
    )


def _node(document, node_id: str):
    return next((n for n in document["nodes"] if n["id"] == node_id), None)


def test_the_hook_is_taken_out_where_a_registered_function_implements_it(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, YARD)
    assert report.problems == () and report.not_executed == (), report
    assert _edges(doc, "implements") == [("own.fn::c", "own.hook::ha", 3)]
    assert _edges(doc, "acts_on") == [("own.hook::ha", "own.thing::ta", 3)]
    hook = _node(doc, "own.hook::ha")
    assert hook is not None and [loc["line"] for loc in hook["locations"]] == [3]


def test_a_node_withheld_at_its_only_place_leaves_the_map(tmp_path: Path) -> None:
    _, doc = _map(tmp_path, YARD)
    assert _node(doc, "own.hook::hb") is None
    assert _node(doc, "own.thing::tb") is None
    assert _node(doc, "own.fn::b") is not None


def test_the_passes_do_not_read_what_was_withheld(tmp_path: Path) -> None:
    _, doc = _map(tmp_path, YARD)
    assert _edges(doc, "seen") == [("own.fn::c", "own.hook::ha", 3)]


def test_without_the_registration_nothing_is_withheld(tmp_path: Path) -> None:
    report, doc = _map(tmp_path, "fn a ha ta\nfn b hb tb\n")
    assert _edges(doc, "implements") == [
        ("own.fn::a", "own.hook::ha", 1),
        ("own.fn::b", "own.hook::hb", 2),
    ]
    assert ("own", "hidden", 0) in report.executed


def test_the_report_counts_each_withholding_fire(tmp_path: Path) -> None:
    report, _ = _map(tmp_path, YARD)
    assert ("own", "hidden", 2) in report.executed


def test_this_node_withholds_the_matched_node_itself(tmp_path: Path) -> None:
    _, doc = _map(tmp_path, YARD, "[{withhold: this_node}]")
    assert _node(doc, "own.fn::a") is None and _node(doc, "own.fn::b") is None
    assert _edges(doc, "implements") == [("own.fn::c", "own.hook::ha", 3)]
    assert _node(doc, "own.hook::hb") is not None


@pytest.mark.parametrize(
    "emits",
    [
        "[{withhold: matched_node}, {edge: {kind: seen, from: this_node, to: matched_node}}]",
        "[{withhold: elsewhere}]",
        "[{withhold: matched_node}, {withhold: this_node}]",
    ],
)
def test_a_malformed_withhold_is_refused(tmp_path: Path, emits: str) -> None:
    report, _ = _map(tmp_path, YARD, emits)
    messages = [p.message for p in report.problems]
    assert any("withhold" in m for m in messages), messages


def test_a_file_rule_cannot_withhold(tmp_path: Path) -> None:
    rules = RULES.replace("EMITS", MATCHED).replace(
        "  emits: [{node: {type: own.reg}}]", "  emits: [{withhold: this_node}]"
    )
    plant(
        tmp_path,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": rules,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "yard/a.yard": YARD,
        },
    )
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert any("withhold" in p.message for p in report.problems), report.problems


def test_the_map_is_byte_identical_on_two_runs(tmp_path: Path) -> None:
    _map(tmp_path, YARD, output="one.json")
    _map(tmp_path, YARD, output="two.json")
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
