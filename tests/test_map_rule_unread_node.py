"""A map rule that would start from, or follow a node step to, a node another map rule made with an
id no file rule found is named in the map report's skipped rows, with the file and the reason."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import MapReport, render_json, render_text, run
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: chain
version: 0.0.1
depends: []
folders:
  yard: ./yard
files:
  types:
    fleet:
      endings: [fleet]
      reader: text
"""

RULES = r"""node_types:
- {name: chain.ship, id_namespace: chain.ship}
- {name: chain.copy, id_namespace: chain.copy}
edge_kinds:
- {kind: copied_from, from: chain.copy, to: chain.ship}
- {kind: noted, from: chain.ship, to: chain.copy}
rules:
- rule: ship
  reads: file
  in: [yard]
  match: {file: '*', filetype: fleet, text: '(?m)^ship (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: chain.ship}}]
  confidence: declared
- rule: copy_of_ship
  reads: map
  match:
    node_type: chain.ship
    where: [{id_matches: '^chain\.ship::(?<name>\w+)$'}]
  id: {template: '{name}'}
  emits: [{node: {type: chain.copy}}]
  confidence: declared
- rule: copy_points_back
  reads: map
  match:
    node_type: chain.copy
    where: [{id_matches: '^chain\.copy::(?<name>\w+)$'}]
  emits: [{edge: {kind: copied_from, from: this_node, to: {template: '{name}', type: chain.ship}}}]
  confidence: declared
- rule: ship_reaches_copy
  reads: map
  match:
    node_type: chain.ship
    where: [{id_matches: '^chain\.ship::(?<name>\w+)$'}]
    follow: [{node: 'chain.copy::{name}'}]
  emits: [{edge: {kind: noted, from: this_node, to: matched_node}}]
  confidence: declared
"""

READ_ONLY = "a map rule reads only nodes whose ids the file rules found"


def _map(root: Path) -> MapReport:
    pack = root / ".periplus" / "packs" / "chain@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [chain@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "chain.yaml").write_text(RULES)
    (root / "yard").mkdir()
    (root / "yard" / "one.fleet").write_text("ship Alpha\n")
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def test_both_rules_that_cannot_read_a_map_made_node_are_named_with_file_and_reason(
    tmp_path: Path,
) -> None:
    report = _map(tmp_path)
    assert report.problems == (), report
    assert report.skipped == (
        (
            "yard/one.fleet",
            1,
            "copy_points_back",
            "starts from chain.copy::Alpha, which map rule chain/copy_of_ship made; " + READ_ONLY,
        ),
        (
            "yard/one.fleet",
            1,
            "ship_reaches_copy",
            "follows to chain.copy::Alpha, which map rule chain/copy_of_ship made; " + READ_ONLY,
        ),
    ), report.skipped
    assert "yard/one.fleet:1 copy_points_back starts from chain.copy::Alpha" in render_text(report)
    rows = json.loads(render_json(report))["skipped"]
    assert [r["rule"] for r in rows] == ["copy_points_back", "ship_reaches_copy"]


def test_a_map_made_node_whose_id_a_file_rule_found_is_read_and_gives_no_row(
    tmp_path: Path,
) -> None:
    """The copy's id is one a file rule found, so the later rules read it: no row."""
    (tmp_path / "x").mkdir()
    pack_rules = RULES.replace(
        "- rule: copy_of_ship",
        "- rule: copy_seen\n  reads: file\n  in: [yard]\n"
        "  match: {file: '*', filetype: fleet, text: '(?m)^copy (?<name>\\w+)'}\n"
        "  id: {from: {capture: name}}\n  emits: [{node: {type: chain.copy}}]\n"
        "  confidence: declared\n- rule: copy_of_ship",
    )
    root = tmp_path / "x"
    pack = root / ".periplus" / "packs" / "chain@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [chain@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "chain.yaml").write_text(pack_rules)
    (root / "yard").mkdir()
    (root / "yard" / "one.fleet").write_text("ship Alpha\ncopy Alpha\n")
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report
    assert report.skipped == (), report.skipped
    kinds = sorted(e["kind"] for e in json.loads((root / "map.json").read_text())["edges"])
    assert kinds == ["copied_from", "noted"]
