"""Pins the behaviour the engine speed fixes could change: the end check on each written edge,
which nodes a map rule visits and in what order, when a node a map rule made becomes visible, and
which files a rule picks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant

import periplus.map as map_module
from periplus.engine.emit import EdgeIllegal, build_document
from periplus.engine.packload import EdgeKind, TypeInfo
from periplus.engine.rules import FoundEdge, FoundNode
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

TYPES = {
    "t.a": TypeInfo("t.a", "t.a", None, "p"),
    "t.b": TypeInfo("t.b", "t.b", None, "p"),
}
KINDS = {"k": EdgeKind("k", ("t.a",), ("t.a",))}


def _node(node_id: str, kind: str) -> FoundNode:
    return FoundNode(node_id, kind, "f", 1, "p", "r", "declared")


def _build(nodes: list[FoundNode], edges: list[FoundEdge]) -> dict:
    document, _ = build_document(nodes, edges, TYPES, KINDS, [], "0", "s")
    return document


def test_an_edge_from_a_found_node_of_a_type_its_kind_refuses_raises() -> None:
    edge = FoundEdge("k", "t.b::x", "t.a::y", "f", 2, "p", "r", "declared")
    with pytest.raises(EdgeIllegal, match="needs t.b::x to be one of t.a, and it is t.b"):
        _build([_node("t.b::x", "t.b"), _node("t.a::y", "t.a")], [edge])


def test_an_end_no_rule_found_is_not_checked_and_becomes_referenced() -> None:
    edge = FoundEdge("k", "t.a::x", "t.a::y", "f", 2, "p", "r", "declared")
    document = _build([_node("t.a::x", "t.a")], [edge])
    assert [(n["id"], n["state"]) for n in document["nodes"]] == [
        ("t.a::x", "mapped"),
        ("t.a::y", "referenced"),
    ]
    assert [(e["from"], e["to"]) for e in document["edges"]] == [("t.a::x", "t.a::y")]


MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  yard: ./yard
  other: ./other
files:
  types:
    yard:
      endings: [yard]
      reader: text
    note:
      endings: [note]
      reader: text
"""

#: ``base``, ``kid`` and ``alpha`` lines declare nodes; ``alpha`` and ``kid`` sit below ``base``,
#: and their declaration order differs from their ids' order. The line ``kid a`` also draws a
#: ``tagged`` edge to ``own.tag::a``, so the map rules know that id and not ``own.tag::z``.
RULES = r"""node_types:
- {name: own.base, id_namespace: own.base}
- {name: own.kid, parent: own.base, id_namespace: own.kid}
- {name: own.alpha, parent: own.base, id_namespace: own.alpha}
- {name: own.tag, id_namespace: own.tag}
- {name: own.note, id_namespace: own.note}
edge_kinds:
- {kind: seen, from: [own.base, own.tag], to: [own.base, own.tag]}
- {kind: tagged, from: own.kid, to: own.tag}
rules:
- rule: base
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^base (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.base}}]
  confidence: declared
- rule: kid
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^kid (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.kid}}]
  confidence: declared
- rule: kid_tagged
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^kid (?<name>a)$'}
  id: {from: {capture: name}}
  emits: [{edge: {kind: tagged, from: this_node, to: {from: {capture: name}}}}]
  confidence: declared
- rule: alpha
  reads: file
  in: [yard]
  match: {file: '*', filetype: yard, text: '(?m)^alpha (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.alpha}}]
  confidence: declared
- rule: yard_note
  reads: file
  in: [yard]
  match: {file: '*', filetype: note, text: '(?m)^note (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.note}}]
  confidence: declared
- rule: note
  reads: file
  in: [yard, other]
  match: {file: 'n*', filetype: note, text: '(?m)^note (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.note}}]
  confidence: declared
- rule: seen_base
  reads: map
  match:
    node_type: own.base
    follow: [{id_matches: '.'}]
  emits: [{edge: {kind: seen, from: this_node, to: matched_node}}]
  confidence: inferred
- rule: tag
  reads: map
  match:
    node_type: own.kid
    where: [{id_matches: '^own\.kid::(?<name>.+)$'}]
  id: {template: '{name}'}
  emits: [{node: {type: own.tag}}]
  confidence: inferred
- rule: seen_tag
  reads: map
  match:
    node_type: own.tag
    follow: [{id_matches: '.'}]
  emits: [{edge: {kind: seen, from: this_node, to: matched_node}}]
  confidence: inferred
"""


def _run(root: Path, monkeypatch: pytest.MonkeyPatch):
    plant(
        root,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "yard/a.yard": "kid z\nbase m\nalpha q\nkid a\n",
            "yard/n1.note": "note one\n",
            "yard/x.note": "note skipped\n",
            "other/n2.note": "note two\n",
        },
    )
    seen: list = []
    real = map_module.run_map_rules

    def spy(*args):
        result = real(*args)
        seen.append(result)
        return result

    monkeypatch.setattr(map_module, "run_map_rules", spy)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    return report, seen[0], json.loads((root / "map.json").read_text())


def test_a_rule_on_a_parent_type_visits_child_types_in_id_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, made_edges, _, _), _ = _run(tmp_path, monkeypatch)
    sources = [edge.source for edge in made_edges if edge.rule == "seen_base"]
    assert sources == ["own.alpha::q", "own.base::m", "own.kid::a", "own.kid::z"]


def test_a_node_a_map_rule_made_is_read_only_in_a_later_pass_and_only_when_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, (made_nodes, made_edges, fires, passes), _ = _run(tmp_path, monkeypatch)
    assert [node.id for node in made_nodes] == ["own.tag::a", "own.tag::z"]
    assert [(e.rule, e.source) for e in made_edges] == [
        ("seen_base", "own.alpha::q"),
        ("seen_base", "own.base::m"),
        ("seen_base", "own.kid::a"),
        ("seen_base", "own.kid::z"),
        ("seen_tag", "own.tag::a"),
    ]
    assert passes == [
        (1, (("own", "seen_base", 4), ("own", "tag", 2))),
        (2, (("own", "seen_tag", 1),)),
        (3, ()),
    ]
    assert fires[("own", "seen_tag")] == 1
    assert report.map_passes == tuple(passes)


def test_each_rule_picks_its_own_files_by_folder_type_and_glob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, _, document = _run(tmp_path, monkeypatch)
    notes = sorted(
        (n["id"], n["locations"][0]["file"]) for n in document["nodes"] if n["type"] == "own.note"
    )
    assert notes == [
        ("own.note::one", "yard/n1.note"),
        ("own.note::skipped", "yard/x.note"),
        ("own.note::two", "other/n2.note"),
    ]
    assert report.opened == ("other/n2.note", "yard/a.yard", "yard/n1.note", "yard/x.note")
    assert report.selected == 4
