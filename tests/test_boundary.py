"""A pack's boundary groups: an edge end that lands on a listed name becomes a declared node that
pack drew, and a group whose shape the engine cannot use refuses the map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode
from periplus.map import MapReport, render_text, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: {pack}
version: 0.0.1
depends: [{depends}]
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
  resolve: [full_if_prefixed: "\\\\", prefix_with: namespace]
{boundary}"""

TYPES = """\
node_types:
- {name: own.class_like, id_namespace: own.type}
- {name: own.class, parent: own.class_like}
- {name: own.form, parent: own.class}
edge_kinds:
- {kind: inherits, from: own.class_like, to: own.class_like}
"""

RULES = """\
rules:
- rule: find_class
  reads: file
  in: [code]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.class}}]
  confidence: declared
- rule: inherits
  reads: file
  in: [code]
  match: {declaration: base_clause, filetype: php}
  emits: [{edge: {kind: inherits, from: enclosing_class, to: {from: qualified_name}}}]
  confidence: declared
"""

BOUNDARY = """\
boundary:
  framework:
    type: own.class_like
    ancestry: [inherits]
    names:
      "Fw\\\\Base": ~
      "Fw\\\\Unused": own.form
"""

SOURCE = """\
<?php

namespace App;

class Mine extends \\Fw\\Base {}

class Yours extends \\Other\\Plain {}
"""

#: The shape every refusal names, so the author reads how to write the block.
SHAPE = (
    "boundary: {<group>: {type: <node type>, ancestry: [<edge kind>], "
    "names: {<name>: <node type or ~>}}}"
)


def _pack(packs: Path, name: str, manifest: str, rules: str) -> None:
    (packs / f"{name}@0.0.1" / "rules").mkdir(parents=True)
    (packs / f"{name}@0.0.1" / "pack.yaml").write_text(manifest)
    (packs / f"{name}@0.0.1" / "rules" / f"{name}.yaml").write_text(rules)


def _run(
    root: Path,
    boundary: str = BOUNDARY,
    types: str = TYPES,
    base: tuple[str, str] | None = None,
    siblings: tuple[str, str] | None = None,
    source: str = SOURCE,
    rules: str = RULES,
) -> MapReport:
    """Map SOURCE with the pack own; ``base``, a manifest's boundary block and its rule file,
    adds a pack base that own depends on; ``siblings``, two boundary blocks, adds packs fw1 and
    fw2 that depend on base and not on each other, and that own depends on."""
    packs = root / ".periplus" / "packs"
    pins = ["own@0.0.1"]
    if base is not None:
        _pack(packs, "base", MANIFEST.format(pack="base", depends="", boundary=base[0]), base[1])
        pins.append("base@0.0.1")
    depends = "base" if base is not None else ""
    for name, block in zip(("fw1", "fw2"), siblings or (), strict=False):
        _pack(
            packs, name, MANIFEST.format(pack=name, depends="base", boundary=block), "rules: []\n"
        )
        pins.append(f"{name}@0.0.1")
        depends += f", {name}"
    manifest = MANIFEST.format(pack="own", depends=depends, boundary=boundary)
    _pack(packs, "own", manifest, types + rules)
    (root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    )
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(source)
    # The bases' own code sits outside the mapped folders, as a framework's does. The map must
    # neither read it nor go looking for it.
    (root / "vendor" / "Fw").mkdir(parents=True)
    (root / "vendor" / "Fw" / "Base.php").write_text("<?php\nnamespace Fw;\nclass Base {}\n")
    (root / "vendor" / "Other").mkdir()
    (root / "vendor" / "Other" / "Plain.php").write_text(
        "<?php\nnamespace Other;\nclass Plain {}\n"
    )
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _nodes(root: Path) -> dict[str, dict[str, Any]]:
    document = json.loads((root / "map.json").read_text())
    return {node["id"]: node for node in document["nodes"]}


def test_a_listed_base_becomes_a_declared_node_the_listing_pack_drew(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert _nodes(tmp_path)["own.type::Fw\\Base"] == {
        "id": "own.type::Fw\\Base",
        "type": "own.class_like",
        "state": "declared",
        "locations": [],
        "provenance": [
            {
                "pack": "own",
                "rule": "boundary.framework",
                "confidence": "declared",
                "sets": ["id", "type"],
            }
        ],
    }
    # The base's file under vendor/ was neither read (no location) nor listed as unread.
    assert not [f for f in (*report.unread, *report.unlisted) if "Base" in f], report


def test_an_unlisted_base_stays_referenced(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == (), report
    node = _nodes(tmp_path)["own.type::Other\\Plain"]
    assert node["state"] == "referenced", node
    assert node["provenance"] == [
        {"pack": "own", "rule": "inherits", "confidence": "declared", "sets": ["id"]}
    ], node
    assert node["locations"] == [], node
    assert not [f for f in (*report.unread, *report.unlisted) if "Plain" in f], report


def test_a_listed_name_no_edge_reaches_leaves_nothing(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.problems == (), report
    assert not any("Unused" in node for node in _nodes(tmp_path))
    assert "Unused" not in render_text(report)


def test_a_group_a_dependency_declares_is_visible(tmp_path: Path) -> None:
    report = _run(tmp_path, boundary="", types="", base=(BOUNDARY, TYPES))
    assert report.problems == (), report
    node = _nodes(tmp_path)["own.type::Fw\\Base"]
    assert node["state"] == "declared", node
    assert node["provenance"][0]["pack"] == "base", node


def test_two_sibling_packs_groups_of_one_name_both_apply(tmp_path: Path) -> None:
    """fw1 and fw2 do not depend on each other and each declare a group framework; own depends on
    both, and neither group hides the other."""
    fw2 = BOUNDARY.replace("Fw\\\\Base", "Other\\\\Plain").replace(
        "Fw\\\\Unused", "Other\\\\Unused"
    )
    report = _run(tmp_path, boundary="", types="", base=("", TYPES), siblings=(BOUNDARY, fw2))
    assert report.problems == (), report
    nodes = _nodes(tmp_path)
    for name, pack in (("Fw\\Base", "fw1"), ("Other\\Plain", "fw2")):
        node = nodes[f"own.type::{name}"]
        assert node["state"] == "declared", node
        assert node["provenance"][0]["pack"] == pack, node
        assert node["provenance"][0]["rule"] == "boundary.framework", node


def test_two_packs_listing_one_name_refuse_the_map(tmp_path: Path) -> None:
    """own and base both list Fw\\Base; which pack draws it is not decided, so the map refuses
    and names both packs."""
    own = BOUNDARY.replace('      "Fw\\\\Unused": own.form\n', "")
    report = _run(tmp_path, boundary=own, types="", base=(BOUNDARY, TYPES))
    _refused(report, "framework", "own.type::Fw\\Base")
    message = report.problems[0].message
    assert ("own/pack.yaml" in message and "the pack base" in message) or (
        "base/pack.yaml" in message and "the pack own" in message
    ), message


def _refused(report: MapReport, *words: str) -> None:
    assert report.exit_code == ExitCode.RULE_NOT_EXECUTABLE, report.problems
    assert report.map_path is None
    messages = [p.message for p in report.problems if p.code == ExitCode.RULE_NOT_EXECUTABLE]
    assert len(messages) == 1, report.problems
    assert SHAPE in messages[0], messages
    assert all(word in messages[0] for word in words), messages


def test_a_group_type_no_visible_pack_declares_is_refused(tmp_path: Path) -> None:
    report = _run(tmp_path, boundary=BOUNDARY.replace("type: own.class_like", "type: own.nope"))
    _refused(report, "framework", "own.nope")


def test_a_names_value_no_pack_declares_is_refused(tmp_path: Path) -> None:
    report = _run(tmp_path, boundary=BOUNDARY.replace("own.form", "own.missing"))
    _refused(report, "framework", "Fw\\Unused", "own.missing")


def test_an_ancestry_kind_no_pack_declares_is_refused(tmp_path: Path) -> None:
    report = _run(tmp_path, boundary=BOUNDARY.replace("[inherits]", "[extends_from]"))
    _refused(report, "framework", "extends_from")


def test_the_path_based_keys_are_refused_by_the_schema(tmp_path: Path) -> None:
    old = (
        "boundary:\n  applies_to_paths: [vendor/**]\n  emit_boundary_nodes: on_reference\n"
        "  type_hierarchy: [{type: Fw}]\n"
    )
    report = _run(tmp_path, boundary=old)
    assert report.exit_code == ExitCode.SCHEMA_INVALID, report.problems


#: own declares an interface type and an implements rule; the boundary block lists the interface.
CONTRACT_TYPES = (
    TYPES.replace(
        "- {name: own.form, parent: own.class}\n",
        "- {name: own.form, parent: own.class}\n- {name: own.interface, parent: own.class_like}\n",
    )
    + "- {kind: implements, from: own.class, to: own.interface}\n"
)

CONTRACT_RULES = (
    RULES
    + """\
- rule: implements
  reads: file
  in: [code]
  match: {declaration: class_interface_clause, filetype: php}
  emits: [{edge: {kind: implements, from: enclosing_class, to: {from: qualified_name}}}]
  confidence: declared
"""
)

CONTRACT_BOUNDARY = """\
boundary:
  framework:
    type: {type}
    ancestry: [implements]
    names:
      "Fw\\\\Contract": ~
"""


def _contract(root: Path, group_type: str) -> MapReport:
    """A first-party class implements Fw\\Contract, which own lists in a group of ``group_type``."""
    return _run(
        root,
        boundary=CONTRACT_BOUNDARY.format(type=group_type),
        types=CONTRACT_TYPES,
        rules=CONTRACT_RULES,
        source="<?php\n\nnamespace App;\n\nclass Mine implements \\Fw\\Contract {}\n",
    )


def test_a_name_in_a_group_whose_type_shares_no_chain_with_its_edge_is_refused(
    tmp_path: Path,
) -> None:
    """An interface filed among classes, a sibling type, would end an implements edge on a class."""
    report = _contract(tmp_path, "own.class")
    assert [p.code for p in report.problems] == [ExitCode.EDGE_ILLEGAL], report.problems
    assert report.map_path is None
    message = report.problems[0].message
    for word in ("implements", "to end", "own.type::Fw\\Contract", "framework", "own.class"):
        assert word in message, message


def test_a_name_in_an_ancestor_group_takes_the_type_its_edge_needs(tmp_path: Path) -> None:
    """An interface filed among class-likes, reached by implements, reads as an interface."""
    report = _contract(tmp_path, "own.class_like")
    assert report.problems == (), report.problems
    node = _nodes(tmp_path)["own.type::Fw\\Contract"]
    assert (node["type"], node["state"]) == ("own.interface", "declared"), node
    assert [(p["pack"], p["sets"]) for p in node["provenance"]] == [("own", ["id", "type"])], node


def test_the_same_name_in_a_group_of_an_allowed_type_maps(tmp_path: Path) -> None:
    report = _contract(tmp_path, "own.interface")
    assert report.problems == (), report.problems
    node = _nodes(tmp_path)["own.type::Fw\\Contract"]
    assert (node["type"], node["state"]) == ("own.interface", "declared"), node


def test_a_kind_ending_on_a_class_types_a_class_like_name_a_class(tmp_path: Path) -> None:
    """A services-style kind names a concrete class; a listed class-like base it reaches maps."""
    report = _run(
        tmp_path,
        types=TYPES + "- {kind: serves_as, from: own.class, to: own.class}\n",
        rules=RULES.replace("kind: inherits", "kind: serves_as"),
    )
    assert report.problems == (), report.problems
    node = _nodes(tmp_path)["own.type::Fw\\Base"]
    assert (node["type"], node["state"]) == ("own.class", "declared"), node
    assert node["provenance"] == [
        {
            "pack": "own",
            "rule": "boundary.framework",
            "confidence": "declared",
            "sets": ["id", "type"],
        }
    ], node
