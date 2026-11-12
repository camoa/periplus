"""A map rule's template end with one ``type`` takes that type's id namespace, as ``types`` with
that one type does, when the type declares a namespace of its own below the kind's type."""

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
  config: ./config
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
"""

#: ``member`` sits below ``fn``, the kind's to type, with a namespace of its own. ``mapped`` maps
#: ``<stem>.found``; ``single`` and ``listed`` each reach ``<stem>.found`` and ``<stem>.missing``.
RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.member, parent: own.fn, id_namespace: own.member}
- {name: own.config, id_namespace: own.config}
edge_kinds:
- {kind: calls, from: own.config, to: own.fn}
rules:
- rule: config
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}'}
  emits: [{node: {type: own.config}}]
  confidence: declared
- rule: mapped
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}.found'}
  emits: [{node: {type: own.member}}]
  confidence: declared
- rule: single
  reads: map
  match:
    node_type: own.config
    where: [{id_matches: '^own\\.config::(?<name>.+)$'}]
  emits:
  - edge: {kind: calls, from: this_node, to: {template: '{name}.found', type: own.member, on_miss: unresolved}}
  - edge: {kind: calls, from: this_node, to: {template: '{name}.missing', type: own.member, on_miss: unresolved}}
  confidence: inferred
- rule: listed
  reads: map
  match:
    node_type: own.config
    where: [{id_matches: '^own\\.config::(?<name>.+)$'}]
  emits:
  - edge: {kind: calls, from: this_node, to: {template: '{name}.found', types: [own.member], on_miss: unresolved}}
  - edge: {kind: calls, from: this_node, to: {template: '{name}.missing', types: [own.member], on_miss: unresolved}}
  confidence: inferred
"""


def test_one_type_mints_in_that_type_namespace_as_the_list_does(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {
            ".periplus/packs/own@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/own@0.0.1/rules/own.yaml": RULES,
            ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
            "config/alpha.yml": "a: 1\n",
        },
    )
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    reached = {
        rule: sorted(
            e["to"]
            for e in document["edges"]
            if rule in {made["rule"] for made in e["provenance"]}
        )
        for rule in ("single", "listed")
    }
    assert reached["single"] == ["own.member::alpha.found", "own.member::alpha.missing"]
    assert reached["single"] == reached["listed"]
    states = {n["id"]: (n["type"], n.get("state")) for n in document["nodes"]}
    assert states["own.member::alpha.found"] == ("own.member", "mapped")
    assert states["own.member::alpha.missing"] == ("own.member", "unresolved")
