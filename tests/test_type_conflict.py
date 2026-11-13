"""Two rules type one node as two types on different branches of one declared ancestor.

The node keeps the nearest type both branches descend from, carries the candidates in its
``type_conflict`` attribute, and the rest of the map is written. Two types that share no ancestor
are an id collision and still refuse the map. Every name here is invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, nodes, pin, plant, rutter

from periplus.errors import ExitCode
from periplus.map import render_json, render_text
from periplus.navigate.find import run as run_find

MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    code:
      endings: [sx]
      reader: text
"""

TYPES = """\
node_types:
- {name: own.thing, id_namespace: own.thing}
- {name: own.form, parent: own.thing}
- {name: own.edit_form, parent: own.form}
- {name: own.list_form, parent: own.form}
- {name: own.stray, id_namespace: own.thing}
- {name: own.view_form, parent: own.form}
edge_kinds:
- {kind: uses, from: own.thing, to: own.thing}
- {kind: saves, from: own.edit_form, to: own.thing}
- {kind: extends, from: own.thing, to: own.thing}
rules:
- rule: thing_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^thing (?<name>\\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.thing}}]
  confidence: declared
- rule: uses_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^(?<name>\\w+) uses (?<to>\\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: uses, from: this_node, to: {from: {capture: to}}}}]
  confidence: declared
- rule: saves_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^(?<name>\\w+) saves (?<to>\\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: saves, from: this_node, to: {from: {capture: to}}}}]
  confidence: declared
- rule: extends_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^(?<name>\\w+) extends (?<to>\\w+)'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: extends, from: this_node, to: {from: {capture: to}}}}]
  confidence: declared
"""

#: A boundary group whose listed base classifies what extends it as a third kind of form.
BOUNDARY = """\
boundary:
  framework:
    type: own.thing
    ancestry: [extends]
    names:
      Base: own.view_form
"""

#: One rule that types a node; ``{word}`` starts its line and ``{type}`` is the type it gives.
TYPING = """\
rules:
- rule: {word}_line
  reads: file
  in: [src]
  match: {{file: '*', filetype: code, text: '(?m)^{word} (?<name>\\w+)'}}
  id: {{from: {{capture: name}}}}
  emits: [{{node: {{type: {type}}}}}]
  confidence: inferred
"""

EDIT = TYPING.format(word="edit", type="own.edit_form")
LIST = TYPING.format(word="list", type="own.list_form")
STRAY = TYPING.format(word="stray", type="own.stray")

SOURCE = "thing gamma\nedit gamma\nlist gamma\nthing delta\ngamma uses delta\ngamma saves delta\n"


def _project(
    root: Path, first: str, second: str, source: str = SOURCE, manifest: str = MANIFEST
) -> None:
    rutter(root, "own", manifest, {"types.yaml": TYPES, "a.yaml": first, "b.yaml": second})
    pin(root, "own@0.0.1")
    plant(root, {"src/one.sx": source})


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _edge_keys(document: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(e["kind"], e["from"], e["to"]) for e in document["edges"]}


def test_the_node_keeps_the_shared_ancestor_and_names_each_candidate(tmp_path: Path) -> None:
    maps = []
    for order, root in ((0, tmp_path / "ab"), (1, tmp_path / "ba")):
        _project(root, *((EDIT, LIST) if order == 0 else (LIST, EDIT)))
        report, document = map_project(root)
        assert report.problems == (), report.problems
        node = nodes(document)["own.thing::gamma"]
        assert node["type"] == "own.form", node
        assert node["state"] == "mapped", node
        assert node["attributes"]["type_conflict"] == [
            "own.edit_form by own/edit_line",
            "own.list_form by own/list_line",
        ], node
        # The rest of the map is written.
        assert nodes(document)["own.thing::delta"]["type"] == "own.thing"
        # An edge the ancestor type can carry stays; one only a candidate can carry does not.
        keys = _edge_keys(document)
        assert ("uses", "own.thing::gamma", "own.thing::delta") in keys, keys
        assert not any(k[0] == "saves" for k in keys), keys
        assert report.internal.unclear_edges == 1, report.internal
        assert report.conflicts == (
            (
                "own.thing::gamma",
                ("own.edit_form by own/edit_line", "own.list_form by own/list_line"),
            ),
        ), report.conflicts
        maps.append((root / "map.json").read_bytes())
    assert maps[0] == maps[1]


def test_find_reaches_the_node_by_a_candidate_type(tmp_path: Path) -> None:
    _project(tmp_path, EDIT, LIST)
    map_project(tmp_path)
    found = run_find(tmp_path, {}, "edit_form", (), 10, tmp_path / "map.json").matches.items
    assert [(r.id, r.matched, r.matched_attribute) for r in found] == [
        ("own.thing::gamma", "attribute", "type_conflict")
    ], found


def test_types_with_no_shared_ancestor_still_refuse_the_map(tmp_path: Path) -> None:
    _project(tmp_path, EDIT, STRAY, "thing gamma\nstray gamma\n")
    report, document = map_project(tmp_path)
    assert document == {}
    assert [(p.code, p.message) for p in report.problems] == [
        (
            ExitCode.TYPE_COLLISION,
            "own.thing::gamma was found as own.stray, own.thing, which do not lie on one type "
            "chain",
        )
    ]


def test_the_report_lists_each_conflict_with_its_candidates(tmp_path: Path) -> None:
    _project(tmp_path, EDIT, LIST)
    report, _ = map_project(tmp_path)
    text = render_text(report)
    assert (
        "Type conflicts:\n"
        "  total 1\n"
        "  edges left out 1\n"
        "  own.thing::gamma: own.edit_form by own/edit_line; own.list_form by own/list_line\n"
    ) in text, text
    assert json.loads(render_json(report))["type_conflicts"] == {
        "total": 1,
        "edges_left_out": 1,
        "by_node": [
            {
                "node": "own.thing::gamma",
                "candidates": [
                    "own.edit_form by own/edit_line",
                    "own.list_form by own/list_line",
                ],
            }
        ],
    }


def test_a_boundary_classification_adds_a_candidate_and_keeps_the_ancestor(tmp_path: Path) -> None:
    maps = []
    for order, root in ((0, tmp_path / "ab"), (1, tmp_path / "ba")):
        _project(
            root,
            *((EDIT, LIST) if order == 0 else (LIST, EDIT)),
            source=SOURCE + "gamma extends Base\n",
            manifest=MANIFEST + BOUNDARY,
        )
        report, document = map_project(root)
        assert report.problems == (), report.problems
        node = nodes(document)["own.thing::gamma"]
        assert node["type"] == "own.form", node
        assert node["attributes"]["type_conflict"] == [
            "own.edit_form by own/edit_line",
            "own.list_form by own/list_line",
            "own.view_form by own/boundary.framework",
        ], node
        maps.append((root / "map.json").read_bytes())
    assert maps[0] == maps[1]


def test_a_rule_that_writes_the_type_conflict_attribute_is_refused(tmp_path: Path) -> None:
    writes = EDIT.replace(
        "emits: [{node: {type: own.edit_form}}]",
        "emits: [{node: {type: own.edit_form}}, {attribute: {name: type_conflict, template: x}}]",
    )
    _project(tmp_path, writes, LIST)
    report, document = map_project(tmp_path)
    assert document == {}
    assert [(p.code, p.message) for p in report.problems] == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "own/rules/a.yaml: the rule edit_line writes the attribute type_conflict, which "
            "only the engine writes, on a node rules type as conflicting types",
        )
    ]
