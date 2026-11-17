"""A data rule writes attributes on the edges it emits, each read by key path.

A key path under the same list item as the edge's end is read inside each item, so each edge gets
its own item's value; a key path with no star is read once for the fire. The pack is an invented
one: a crate of items, each with labels and parts. Every name here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, pin, plant, rutter

from periplus.engine.packload import _read_rule
from periplus.errors import ExitCode

MANIFEST = """\
pack: crate
version: 0.0.1
depends: []
folders:
  hold: ./hold
files:
  types:
    box:
      endings: [box]
      reader: data
      format: yaml
"""

TYPES = """\
node_types:
- {name: crate.item, id_namespace: crate.item}
- {name: crate.label, id_namespace: crate.label}
edge_kinds:
- {kind: labelled, from: crate.item, to: crate.label}
- {kind: holds, from: crate.item, to: crate.item}
- {kind: elsewhere, from: crate.item, to: crate.item}
rules:
- rule: item
  reads: file
  in: [hold]
  match: {file: '*', filetype: box, each: 'items.*'}
  id: {from: key}
  emits: [{node: {type: crate.item}}]
  confidence: declared
"""

#: The key form: one edge per label item, its color from the same item, its shelf from the fire.
LABELS = """\
- rule: labels
  reads: file
  in: [hold]
  match: {file: '*', filetype: box, each: 'items.*'}
  id: {from: key}
  emits:
  - edge:
      kind: labelled
      from: this_node
      to: {from: {key: labels.*.name}}
      attributes:
        color: {from: {key: labels.*.color}}
        shelf: {from: {key: shelf}}
  confidence: declared
"""

#: The list form: one edge per part, its count from the same part.
PARTS = """\
- rule: parts
  reads: file
  in: [hold]
  match: {file: '*', filetype: box, each: 'items.*'}
  id: {from: key}
  emits:
  - edge:
      kind: holds
      from: this_node
      to: {from: [{each: parts.*}], template: '{key}'}
      attributes: {count: {from: {key: parts.*.count}}}
  confidence: declared
"""

CRATE = """\
items:
  hammer:
    shelf: top
    labels:
    - name: red-tag
      color: red
    - name: blue-tag
      color: blue
    - name: plain-tag
    parts:
      head:
        count: 1
      nail:
        count: 40
  saw:
    labels:
    - name: red-tag
      color: green
"""


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def project(
    root: Path, rules: str, crate: str = CRATE, declare: str = "", other: str = ""
) -> None:
    files = {"crate.yaml": TYPES, "more.yaml": f"rules:\n{rules}"}
    if declare:
        files["attributes.yaml"] = declare
    rutter(root, "crate", MANIFEST, files)
    pins = ["crate@0.0.1"]
    if other:
        manifest = "pack: other\nversion: 0.0.1\ndepends: []\nfolders:\n  none: ./none\n"
        rutter(root, "other", manifest, {"other.yaml": other})
        pins.append("other@0.0.1")
    pin(root, *pins)
    plant(root, {"hold/a.box": crate})


def _mapped(root: Path) -> dict[str, Any]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def _edges(document: dict[str, Any], kind: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {(e["from"], e["to"]): e for e in document["edges"] if e["kind"] == kind}


def _refused(root: Path) -> list[tuple[ExitCode, str]]:
    report, document = map_project(root)
    assert document == {}
    return [(p.code, p.message) for p in report.problems]


def test_each_edge_takes_the_value_of_its_own_list_item(tmp_path: Path) -> None:
    project(tmp_path, LABELS)
    found = _edges(_mapped(tmp_path), "labelled")
    assert found[("crate.item::hammer", "crate.label::red-tag")]["attributes"] == {
        "color": "red",
        "shelf": "top",
    }
    assert found[("crate.item::hammer", "crate.label::blue-tag")]["attributes"] == {
        "color": "blue",
        "shelf": "top",
    }
    # An item without the key writes nothing from it; the whole-fire value still lands.
    assert found[("crate.item::hammer", "crate.label::plain-tag")]["attributes"] == {
        "shelf": "top"
    }
    # A fire whose whole-fire key is absent writes nothing from it.
    assert found[("crate.item::saw", "crate.label::red-tag")]["attributes"] == {"color": "green"}
    assert found[("crate.item::hammer", "crate.label::blue-tag")]["provenance"] == [
        {"pack": "crate", "rule": "labels", "confidence": "declared", "sets": ["color", "shelf"]}
    ]


def test_the_list_form_pairs_each_part_with_its_own_value(tmp_path: Path) -> None:
    project(tmp_path, PARTS)
    found = _edges(_mapped(tmp_path), "holds")
    assert found[("crate.item::hammer", "crate.item::head")]["attributes"] == {"count": 1}
    assert found[("crate.item::hammer", "crate.item::nail")]["attributes"] == {"count": 40}


def test_one_edge_at_two_places_with_two_values_keeps_each_at_its_place(tmp_path: Path) -> None:
    crate = "items:\n  hammer:\n    labels:\n    - name: red-tag\n      color: red\n"
    crate += "    - name: red-tag\n      color: pink\n"
    project(tmp_path, LABELS, crate=crate)
    (edge,) = _edges(_mapped(tmp_path), "labelled").values()
    assert edge["attributes"] == {
        "color": {
            "differs": [
                {"file": "hold/a.box", "line": 4, "value": "red"},
                {"file": "hold/a.box", "line": 6, "value": "pink"},
            ]
        }
    }


def test_without_attributes_a_data_rule_gives_the_same_map_less_the_attributes(
    tmp_path: Path,
) -> None:
    project(tmp_path / "with", LABELS + PARTS)
    plain = (LABELS + PARTS).replace(
        "      attributes:\n        color: {from: {key: labels.*.color}}\n"
        "        shelf: {from: {key: shelf}}\n",
        "",
    )
    plain = plain.replace("      attributes: {count: {from: {key: parts.*.count}}}\n", "")
    assert "attributes" not in plain
    project(tmp_path / "without", plain)
    with_ = _mapped(tmp_path / "with")
    without = _mapped(tmp_path / "without")
    assert all("attributes" not in edge for edge in without["edges"])
    for edge in with_["edges"]:
        edge.pop("attributes", None)
        for row in edge["provenance"]:
            row.pop("sets", None)
    assert with_ == without


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        (
            LABELS.replace("labels.*.color", "boxes.*.color"),
            "the edge attribute color reads boxes.*.color, inside a list item other than the "
            "edge end's labels.*; a key path with a star must start with labels.*",
        ),
        (
            LABELS.replace("labels.*.name", "maker"),
            "the edge attribute color reads labels.*.color, a key path with a star, and the "
            "edge's end maker reads no list item to pair it with",
        ),
        (
            PARTS.replace("parts.*.count", "labels.*.count"),
            "the edge attribute count reads labels.*.count, inside a list item other than the "
            "edge end's parts.*; a key path with a star must start with parts.*",
        ),
    ],
    ids=["other list", "no list at the end", "list form"],
)
def test_a_key_path_in_another_list_is_refused(tmp_path: Path, rules: str, reason: str) -> None:
    project(tmp_path, rules)
    report, _ = map_project(tmp_path)
    (problem,) = report.problems
    assert problem.code == ExitCode.RULE_NOT_EXECUTABLE
    assert problem.message.endswith(f"cannot be executed: {reason}")


def test_a_declared_edge_attribute_on_a_kind_outside_on_is_refused(tmp_path: Path) -> None:
    project(tmp_path, PARTS, declare="edge_attributes:\n- {name: count, on: [elsewhere]}\n")
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "crate/rules/more.yaml: the rule parts writes the edge attribute count on holds, "
            "which the declaration of count does not list in on: elsewhere",
        )
    ]


def test_an_edge_attribute_another_rutter_declares_is_refused(tmp_path: Path) -> None:
    other = "node_types:\n- {name: o.a}\nedge_kinds:\n- {kind: ties, from: o.a, to: o.a}\n"
    other += "edge_attributes:\n- {name: count, on: [ties]}\n"
    project(tmp_path, PARTS, other=other)
    assert _refused(tmp_path) == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "crate/rules/more.yaml: the rule parts writes the edge attribute count, which neither "
            "crate nor a pack it depends on declares",
        )
    ]


@pytest.mark.parametrize(
    ("value", "key"),
    [
        ({"literal": "x"}, "literal"),
        ({"from": {"key": "parts.*.count"}, "pattern": "(?<n>.+)"}, "pattern"),
        (
            {"from": {"key": "parts.*.count"}, "normalize": [{"replace": "a", "with": "b"}]},
            "normalize",
        ),
    ],
)
def test_literal_pattern_and_normalize_are_accepted_and_not_executed(
    value: dict[str, Any], key: str
) -> None:
    item = {
        "rule": "parts",
        "reads": "file",
        "in": ["hold"],
        "match": {"file": "*", "filetype": "box", "each": "items.*"},
        "id": {"from": "key"},
        "emits": [
            {
                "edge": {
                    "kind": "holds",
                    "from": "this_node",
                    "to": {"from": {"key": "parts"}},
                    "attributes": {"count": value},
                }
            }
        ],
        "confidence": "declared",
    }
    rule = _read_rule("crate", item)
    assert not rule.supported
    assert rule.reason == f"the key emits.*.edge.attributes.*.{key} is accepted and not executed"
