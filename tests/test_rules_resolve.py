"""Test for the one resolve routine of the rules engine."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: probe
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
  comment: comment
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
"""

RULES = """\
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts: {alias: alias, use_kind: type}
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\\\"
    skip_when_field_set: use_kind
node_types:
- {name: probe.class, id_namespace: probe.class}
- {name: probe.property, id_namespace: probe.property}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
- rule: property
  reads: file
  in: [source]
  match: {declaration: property_declaration, name_child: [property_element, name], filetype: php}
  id:
    from: [declared_name, {qualified: {docblock: '@var\\s+(?<type>[\\w\\\\]+)'}}]
    template: '{declared_name}:{type}'
  emits: [{node: {type: probe.property}}]
  confidence: declared
"""

SOURCE = """\
<?php

namespace App\\Ctl;

use App\\Service\\Registration as Reg;

class Thing
{
    /** @var Reg */
    protected $reg;

    public function run()
    {
    }
}
"""


def _map(root: Path) -> MapReport:
    pack = root / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [probe@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "probe.yaml").write_text(RULES)
    (root / "Thing.php").write_text(SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    return report


def test_a_docblock_type_resolves_through_an_import_alias(tmp_path: Path) -> None:
    """@var Reg names the alias of the use line, so the id holds the aliased full name."""
    report = _map(tmp_path)
    document = json.loads((tmp_path / "map.json").read_text())
    ids = [n["id"] for n in document["nodes"] if n["type"] == "probe.property"]
    assert ids == ["probe.property::$reg:App\\Service\\Registration"], report
