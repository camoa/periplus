"""Tests for the id source ``{qualified: <field>}`` of a tree declaration rule: the text of the
matched node's field, resolved through the file's imports and namespace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
- {name: probe.parameter, id_namespace: probe.parameter}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
- rule: parameter
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id:
    from: [enclosing_type, declared_name, {qualified: type}]
    template: '{enclosing_type}::{declared_name}:{type}'
  emits: [{node: {type: probe.parameter}}]
  confidence: declared
"""

SOURCE = """\
<?php

namespace App\\Ctl;

use App\\Service\\Registration;

class Thing
{
    public function run(Registration $reg, Helper $help, $loose)
    {
    }
}
"""


def _map(root: Path) -> tuple[MapReport, Any]:
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
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


def test_a_field_resolves_through_the_imports_and_the_namespace(tmp_path: Path) -> None:
    """Registration is imported, so its full name is the use line's; Helper is not, so it takes
    the file's namespace; the untyped $loose makes nothing and leaves one row."""
    report, document = _map(tmp_path)
    assert report.problems == (), report
    assert report.not_executed == ()
    assert ("probe", "parameter", 2) in report.executed
    ids = sorted(n["id"] for n in document["nodes"] if n["type"] == "probe.parameter")
    assert ids == [
        "probe.parameter::App\\Ctl\\Thing::$help:App\\Ctl\\Helper",
        "probe.parameter::App\\Ctl\\Thing::$reg:App\\Service\\Registration",
    ]
    rows = [(line, rule, reason) for _, line, rule, reason in report.skipped]
    assert rows == [(9, "parameter", "the id source type is absent")]
